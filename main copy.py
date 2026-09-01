import os
import re
import json
import time
import asyncio
from typing import Optional, List, Dict, Any, Tuple

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import pymupdf as fitz
import pymupdf4llm

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_qdrant import QdrantVectorStore

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
)

# =========================================================
# 1) UYGULAMA / DİZİNLER
# =========================================================
app = FastAPI(title="Akademik Makale Asistanı API")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "qdrant_db")
COLLECTION_NAME = "dokumanlar"

os.makedirs(UPLOAD_DIR, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# 2) MODELLER
# =========================================================
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "qwen2.5:7b"

cevirmen = OllamaEmbeddings(model=EMBED_MODEL)

llm = Ollama(
    model=CHAT_MODEL,
    temperature=0.1,
    num_ctx=8192,
)

# =========================================================
# 3) YARDIMCI FONKSİYONLAR
# =========================================================
class SoruIstegi(BaseModel):
    question: str
    dosya_adi: str
    theme_color: Optional[str] = "#2563EB"

def temizle_model_cevabi(text: Any) -> str:
    if not text:
        return ""
    text = str(text)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.replace("\x00", "").replace("\ufffd", "").strip()

def hex_to_rgb_float(hex_str: str):
    try:
        hex_str = (hex_str or "").lstrip("#")
        if len(hex_str) == 6:
            r = int(hex_str[0:2], 16) / 255.0
            g = int(hex_str[2:4], 16) / 255.0
            b = int(hex_str[4:6], 16) / 255.0
            return (r, g, b)
    except Exception:
        pass
    return (0.145, 0.388, 0.921)

def dosya_guvenli_adi(filename: str) -> str:
    filename = os.path.basename(filename or "makale.pdf")
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)

def get_vector_store(client: QdrantClient) -> QdrantVectorStore:
    return QdrantVectorStore(client=client, collection_name=COLLECTION_NAME, embedding=cevirmen)

# =========================================================
# 4) ENDPOINTLER
# =========================================================
@app.get("/pdf/{dosya_adi}")
async def pdf_getir(dosya_adi: str):
    dosya_adi = dosya_guvenli_adi(dosya_adi)
    dosya_yolu = os.path.join(UPLOAD_DIR, dosya_adi)
    if not os.path.exists(dosya_yolu):
        raise HTTPException(status_code=404, detail="PDF dosyası bulunamadı.")
    return FileResponse(dosya_yolu, media_type="application/pdf")

@app.post("/documents_stream")
async def belge_yukle_stream(file: UploadFile = File(...)):
    async def ilerleme_uretici():
        client = None
        try:
            dosya_adi = dosya_guvenli_adi(file.filename)
            if not dosya_adi.lower().endswith(".pdf"):
                yield f"data: {json.dumps({'error': 'Sadece PDF yükleyebilirsiniz.'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'step': 1, 'percent': 10, 'msg': 'PDF kaydediliyor...'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.05)

            dosya_yolu = os.path.join(UPLOAD_DIR, dosya_adi)
            icerik = await file.read()
            with open(dosya_yolu, "wb") as f:
                f.write(icerik)

            yield f"data: {json.dumps({'step': 2, 'percent': 25, 'msg': 'Metin çıkarılıyor...'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.05)

            sayfa_verileri = pymupdf4llm.to_markdown(dosya_yolu, page_chunks=True)
            belgeler = []
            for idx, sayfa in enumerate(sayfa_verileri):
                metin = sayfa.get("text", "")
                if not metin.strip():
                    continue
                belgeler.append(Document(
                    page_content=metin,
                    metadata={"dosya_adi": dosya_adi, "page": idx}
                ))

            if not belgeler:
                yield f"data: {json.dumps({'error': 'PDF içinden okunabilir metin çıkarılamadı.'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'step': 3, 'percent': 40, 'msg': 'Metin parçalanıyor...'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.05)

            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
            parcalar = splitter.split_documents(belgeler)
            toplam_parca = len(parcalar)

            for p in parcalar:
                p.metadata["dosya_adi"] = dosya_adi

            client = QdrantClient(path=DB_PATH)
            if not client.collection_exists(collection_name=COLLECTION_NAME):
                client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE)
                )

            try:
                client.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=Filter(must=[FieldCondition(key="metadata.dosya_adi", match=MatchValue(value=dosya_adi))])
                )
            except Exception:
                pass

            store = get_vector_store(client)

            batch_size = 2
            for start in range(0, toplam_parca, batch_size):
                batch = parcalar[start:start + batch_size]
                store.add_documents(documents=batch)
                
                ilerleme = 40 + int((min(start + batch_size, toplam_parca) / toplam_parca) * 55)
                yield f"data: {json.dumps({'step': 4, 'percent': ilerleme, 'msg': f'Embedding oluşturuluyor ({min(start + batch_size, toplam_parca)}/{toplam_parca})...'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)

            client.close()
            client = None

            yield f"data: {json.dumps({'step': 5, 'percent': 100, 'done': True, 'dosya_adi': dosya_adi, 'eklenen_parca_sayisi': toplam_parca}, ensure_ascii=False)}\n\n"

        except Exception as e:
            if client:
                try: client.close()
                except: pass
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(ilerleme_uretici(), media_type="text/event-stream")

@app.post("/pdf_search_advanced")
async def pdf_search_advanced(istek: SoruIstegi):
    try:
        dosya_adi = dosya_guvenli_adi(istek.dosya_adi)
        dosya_yolu = os.path.join(UPLOAD_DIR, dosya_adi)
        if not os.path.exists(dosya_yolu):
            return {"success": False, "matches": []}

        doc = fitz.open(dosya_yolu)
        matches = []
        theme_rgb = hex_to_rgb_float(istek.theme_color)

        for page_num in range(len(doc)):
            page = doc[page_num]
            rects = page.search_for(istek.question)
            if rects:
                for r in rects:
                    annot = page.add_highlight_annot(r)
                    annot.set_colors(stroke=theme_rgb)
                    annot.set_opacity(0.35)
                    annot.update()
                matches.append(page_num + 1)

        if not matches:
            doc.close()
            return {"success": False, "matches": []}

        ts = int(time.time() * 1000)
        search_filename = f"search_{ts}_{dosya_adi}"
        search_filepath = os.path.join(UPLOAD_DIR, search_filename)
        doc.save(search_filepath)
        doc.close()

        return {"success": True, "search_file": search_filename, "matches": matches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask")
async def soru_sor(istek: SoruIstegi):
    client = None
    try:
        dosya_adi = dosya_guvenli_adi(istek.dosya_adi)
        if not dosya_adi:
            return {"answer": "Lütfen önce bir PDF makalesi yükleyin."}

        client = QdrantClient(path=DB_PATH)
        if not client.collection_exists(collection_name=COLLECTION_NAME):
            client.close()
            return {"answer": "Henüz indekslenmiş bir makale bulunmuyor. Lütfen PDF yükleyin."}

        store = get_vector_store(client)
        arama_filtresi = Filter(must=[FieldCondition(key="metadata.dosya_adi", match=MatchValue(value=dosya_adi))])

        # Çeviri Adımı
        ceviri_prompt = f"Translate the following Turkish query to English search keywords. Return ONLY the English keywords, no commentary.\nQuery: {istek.question}"
        raw_ceviri = llm.invoke(ceviri_prompt)
        ingilizce_arama = temizle_model_cevabi(raw_ceviri).strip() or istek.question

        bulunan_sonuclar = store.similarity_search(ingilizce_arama, k=6, filter=arama_filtresi)

        # KESİN BAŞLIK VE ÖZET GARANTİSİ
        q_lower = istek.question.lower()
        is_metadata_query = any(w in q_lower for w in ["başlık", "title", "yazar", "author", "kim yazdı", "özet", "abstract", "giriş", "introduction", "ne anlat", "konu", "amaç"])
        
        if is_metadata_query:
            sayfa1_filtresi = Filter(
                must=[
                    FieldCondition(key="metadata.dosya_adi", match=MatchValue(value=dosya_adi)),
                    FieldCondition(key="metadata.page", match=MatchAny(any=[0, 1]))
                ]
            )
            ek_sonuclar = store.similarity_search("title abstract authors introduction keywords paper name", k=3, filter=sayfa1_filtresi)
            for doc in reversed(ek_sonuclar):
                if doc.page_content not in [d.page_content for d in bulunan_sonuclar]:
                    bulunan_sonuclar.insert(0, doc)

        client.close()
        client = None

        if not bulunan_sonuclar:
            return {"answer": "Makalede bu bilgi bulunamadı.", "sources": [], "highlighted_file": None}

        bulunan_sonuclar.sort(key=lambda d: d.metadata.get("page", 0))

        baglam_listesi = []
        kullanilan_sayfalar = set()
        highlighted_filename = None
        theme_rgb = hex_to_rgb_float(istek.theme_color)

        try:
            ts = int(time.time() * 1000)
            hl_filename = f"hl_{ts}_{dosya_adi}"
            hl_filepath = os.path.join(UPLOAD_DIR, hl_filename)
            pdf_doc = fitz.open(os.path.join(UPLOAD_DIR, dosya_adi))

            for chunk in bulunan_sonuclar:
                sayfa_idx = int(chunk.metadata.get("page", 0))
                gorunen_sayfa = sayfa_idx + 1
                kullanilan_sayfalar.add(gorunen_sayfa)
                baglam_listesi.append(f"[Sayfa {gorunen_sayfa}]\n{chunk.page_content}")

                if 0 <= sayfa_idx < len(pdf_doc):
                    page = pdf_doc[sayfa_idx]
                    temiz_metin = re.sub(r'[#*_`>\[\]\(\)\-\+]', ' ', chunk.page_content)
                    kelimeler = temiz_metin.split()
                    for i in range(0, len(kelimeler), 6):
                        arama_obegi = " ".join(kelimeler[i:i+6])
                        if len(arama_obegi) > 10:
                            rects = page.search_for(arama_obegi)
                            for r in rects:
                                annot = page.add_highlight_annot(r)
                                annot.set_colors(stroke=theme_rgb)
                                annot.set_opacity(0.35)
                                annot.update()

            pdf_doc.save(hl_filepath)
            pdf_doc.close()
            highlighted_filename = hl_filename
        except Exception as e:
            print("Highlight hatası:", e)

        baglam = "\n\n---\n\n".join(baglam_listesi)

        # Eğer başlık soruluyorsa 1. sayfanın ham metnini doğrudan ek bağlam olarak ekleyelim ki kaçırma ihtimali kalmasın
        if is_metadata_query:
            try:
                pdf_doc_raw = fitz.open(os.path.join(UPLOAD_DIR, dosya_adi))
                if len(pdf_doc_raw) > 0:
                    baglam = "=== SAYFA 1 ORİJİNAL METİN ===\n" + pdf_doc_raw[0].get_text() + "\n\n" + baglam
                pdf_doc_raw.close()
            except:
                pass

        nihai_prompt = f"""Sen kıdemli bir akademik araştırma asistanısın. Aşağıdaki bağlamı (CONTEXT) kullanarak kullanıcının sorusunu profesyonel ve akıcı bir Türkçe ile yanıtla.

CONTEXT:
{baglam}

SORU:
{istek.question}

KURALLAR:
1. Makale başlığı, yazarı veya abstract'ı sorulduğunda CONTEXT içinde yer alan [Sayfa 1] veya [SAYFA 1 ORİJİNAL METİN] kısmındaki ilk satırları (en büyük puntolarla yazılan ana başlığı) kesinlikle bul ve doğrudan yaz. Asla "bilgi bulunamadı" deme.
2. Formülleri ve değişkenleri bağlamda açıklandığı şekliyle net biçimde ifade et.
3. Terimlerin akademik karşılıklarını koru (Örn: "Color Correction" -> "Renk Düzeltme").
4. Bağlamda kesinlikle yer almayan hiçbir bilgiyi ekleme.
"""
        raw_response = llm.invoke(nihai_prompt)
        cevap = temizle_model_cevabi(raw_response) or "Model geçerli bir yanıt üretemedi."

        return {
            "answer": cevap,
            "sources": sorted(list(kullanilan_sayfalar)),
            "highlighted_file": highlighted_filename
        }

    except Exception as e:
        if client:
            try: client.close()
            except: pass
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok", "chat_model": CHAT_MODEL, "embedding_model": EMBED_MODEL}