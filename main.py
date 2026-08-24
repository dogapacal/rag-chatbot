import os
import shutil
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

app = FastAPI(title="Kurumsal Doküman Asistanı API")

# Ortak Yapılandırma
DB_PATH = "./qdrant_db"
COLLECTION_NAME = "dokumanlar"
cevirmen = OllamaEmbeddings(model="nomic-embed-text")
llm = Ollama(model="qwen3:8b")

# İstek Modelleri
class SearchIstegi(BaseModel):
    query: str

class SoruIstegi(BaseModel):
    question: str

@app.get("/")
def anasayfa():
    return {"durum": "Sistem aktif ve çalışıyor!"}

# 1. PDF YÜKLEME ENDPOINT'İ (POST /documents)
@app.post("/documents")
async def belge_yukle(file: UploadFile = File(...)):
    temp_dosya = f"temp_{file.filename}"
    try:
        with open(temp_dosya, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        yukleyici = PyMuPDFLoader(temp_dosya)
        belgeler = yukleyici.load()
        
        parcalayici = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        parcalar = parcalayici.split_documents(belgeler)
        
        client = QdrantClient(path=DB_PATH)
        if not client.collection_exists(collection_name=COLLECTION_NAME):
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )
        
        veritabani = QdrantVectorStore(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding=cevirmen,
        )
        veritabani.add_documents(documents=parcalar)
        client.close()
        
    finally:
        if os.path.exists(temp_dosya):
            os.remove(temp_dosya)
        
    return {
        "durum": "Başarılı",
        "dosya_adi": file.filename,
        "eklenen_parca_sayisi": len(parcalar)
    }

# 2. VEKTÖREL ARAMA ENDPOINT'İ (POST /search)
@app.post("/search")
def vektorel_arama(istek: SearchIstegi):
    client = QdrantClient(path=DB_PATH)
    veritabani = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding=cevirmen,
    )
    
    # 1. Türkçe sorguyu veritabanında aratabilmek için İngilizceye çevir
    arama_sorgusu = llm.invoke(
        f"Translate the following search query to English directly without any explanation:\n{istek.query}"
    ).strip()
    
    # 2. Qdrant'tan en yakın 3 sonucu (İngilizce olarak) çek
    sonuclar = veritabani.similarity_search_with_score(arama_sorgusu, k=3)
    client.close()
    
    # 3. Çekilen her bir İngilizce sonucu LLM ile Türkçeye çevirerek listeye ekle
    donus_listesi = []
    for doc, score in sonuclar:
        ceviri_prompt = f"Aşağıdaki İngilizce metni hiçbir açıklama yapmadan doğrudan Türkçeye çevir:\n{doc.page_content}"
        turkce_metin = llm.invoke(ceviri_prompt).strip()
        
        donus_listesi.append({
            "content": turkce_metin,
            "score": round(float(score), 4)
        })
    
    return donus_listesi

# 3. SORU-CEVAP ENDPOINT'İ (POST /ask)
@app.post("/ask")
def soru_sor(istek: SoruIstegi):
    client = QdrantClient(path=DB_PATH)
    veritabani = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding=cevirmen,
    )
    
    ingilizce_arama_sorgusu = llm.invoke(
        f"Translate the following search query or question to English directly without any explanation:\n{istek.question}"
    ).strip()
    
    bulunan_sonuc = veritabani.similarity_search(ingilizce_arama_sorgusu, k=10)
    baglam = "\n\n".join([sonuc.page_content for sonuc in bulunan_sonuc])
    
    nihai_prompt = f"""
Sen profesyonel bir teknik asistansın.
Aşağıdaki BAĞLAM İngilizce bir makaleden alınmıştır. 
Kullanıcının sorusunu verilen BAĞLAMDAKİ bilgileri kullanarak ve MUTLAKA TÜRKÇE olarak yanıtla.
Eğer kullanıcı "özetle", "genel olarak ne anlatıyor" gibi makalenin tamamına yönelik bir soru soruyorsa, bağlamdaki parçaları harmanlayıp genel bir özet paragrafı çıkar.
Ancak kullanıcının sorduğu spesifik bir teknik detay bağlamda HİÇ yoksa uydurma, doğrudan "Bu bilgi dokümanda bulunamadı." de.

BAĞLAM:
{baglam}

SORU:
{istek.question}
"""
    
    cevap = llm.invoke(nihai_prompt)
    client.close()
    
    return {
        "orijinal_soru": istek.question,
        "cevap": cevap
    }