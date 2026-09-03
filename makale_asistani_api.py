"""İki dilli, yapısal akademik makale asistanı API'si."""
from __future__ import annotations
import asyncio, hashlib, json, os, re, shutil, time, unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pymupdf as fitz
import pymupdf4llm
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchAny, MatchValue, VectorParams

# --- .env Dosyasını Okuma ve API Anahtarını Yükleme ---
from dotenv import load_dotenv
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# --------------------------------------------------------

try:
    from langchain_ollama import OllamaEmbeddings, OllamaLLM
except ImportError:
    from langchain_community.embeddings import OllamaEmbeddings
    from langchain_community.llms import Ollama as OllamaLLM

app = FastAPI(title="Akademik Makale Asistanı API", version="2.3")
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "qdrant_db"
DATA_DIR = BASE_DIR / "article_data"
COLLECTION_NAME = "dokumanlar"
SCHEMA_VERSION = 5
CHUNK_SIZE = 1400
CHUNK_OVERLAP = 180
REQUEST_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="article_request")


for directory in (UPLOAD_DIR, DATA_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b")
embeddings = OllamaEmbeddings(model=EMBED_MODEL)
llm = OllamaLLM(model=CHAT_MODEL, temperature=0.0, num_ctx=8192)

class SoruIstegi(BaseModel):
    question: str
    dosya_adlari: List[str] = Field(default_factory=list)
    dosya_adi: Optional[str] = None
    theme_color: str = "#2563EB"
    model: str = "local"

def temizle_model_cevabi(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.I | re.S)
    text = re.sub(r"<think>.*", "", text, flags=re.I | re.S)
    text = re.sub(r"【.*?】", "", text)
    text = re.sub(r"\[s\.\s*[^\]]+\]", "", text, flags=re.I)
    
    # Türkçe veya İngilizce dışındaki Asya/Çince karakter bloklarını temizler
    text = re.sub(r"[\u4e00-\u9fff]+", "", text)
    
    return text.replace("\x00", "").replace("\ufffd", "").strip()
import requests
import os

def llm_metni(prompt: str, model: str = "local") -> str:
    try:
        # Eğer arayüzden "Yerel Qwen 7B" seçildiyse mevcut Ollama altyapısını kullan
        if model == "local":
            return temizle_model_cevabi(llm.invoke(prompt))
        
        # Eğer arayüzden bulut modellerinden biri seçildiyse OpenRouter'a git
        else:
            # API anahtarı değişken olmadan doğrudan header içine gömüldü
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            if model == "meta-llama/llama-3.1-8b-instruct:free":
               model = "meta-llama/llama-3.1-8b-instruct:free"

            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0
            }
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=120
)
            
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    answer = response_json["choices"][0]["message"]["content"]
                    return temizle_model_cevabi(answer)
                return "API'den boş yanıt döndü."
            else:
                return f"Bulut API Hatası ({response.status_code}) - Gönderilen model: {model}: {response.text}"
                
    except Exception as e:
        return f"Sistem Hatası: {str(e)}"

def dosya_guvenli_adi(filename: str) -> str:
    value = os.path.basename(filename or "makale.pdf")
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip()
    return value or "makale.pdf"

def makale_anahtari(dosya_adi: str) -> str:
    return hashlib.sha256(dosya_adi.encode("utf-8")).hexdigest()[:24]

def belge_hashi(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()

def profil_yolu(dosya_adi: str, document_id: Optional[str] = None) -> Path:
    key = document_id or makale_anahtari(dosya_adi)
    return DATA_DIR / f"{key}.profile.json"

def parca_yolu(dosya_adi: str, document_id: Optional[str] = None) -> Path:
    key = document_id or makale_anahtari(dosya_adi)
    return DATA_DIR / f"{key}.chunks.json"

def json_yaz(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
    os.replace(temporary, path)

def json_oku(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as input_file:
            return json.load(input_file)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default

def normalize(text: Any) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.casefold().replace("ı", "i")).strip()

def temiz_metin(text: str) -> str:
    text = re.sub(r"!?(?:\[[^\]]*\])\([^)]*\)", " ", text)
    text = re.sub(r"^[#>*\-]+\s*", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text.replace("`", " ")).strip()

def ilk_cumle(text: str) -> str:
    text = temiz_metin(text)
    if not text:
        return ""
    return re.split(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9])", text, maxsplit=1)[0].strip()

def hex_to_rgb_float(color: Optional[str]) -> Tuple[float, float, float]:
    try:
        value = (color or "").lstrip("#")
        if len(value) == 6:
            return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except (TypeError, ValueError):
        pass
    return 0.145, 0.388, 0.921

def ilk_json_nesnesi(text: str) -> Dict[str, Any]:
    fence = "`" * 3
    text = re.sub(r"^" + fence + r"(?:json)?\s*|\s*" + fence + r"$", "", text.strip(), flags=re.I)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:index + 1])
                        return value if isinstance(value, dict) else {}
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return {}

# ============================================================
# VEKTÖR VERİTABANI
# ============================================================

def vector_filter(aktif_doc_ids: List[str]) -> Filter:
    return Filter(must=[
        FieldCondition(key="metadata.document_id", match=MatchAny(any=aktif_doc_ids)),
        FieldCondition(key="metadata.schema_version", match=MatchValue(value=SCHEMA_VERSION)),
    ])

def get_vector_store(client: QdrantClient) -> QdrantVectorStore:
    return QdrantVectorStore(client=client, collection_name=COLLECTION_NAME, embedding=embeddings)

def ensure_collection(client: QdrantClient) -> None:
    if not client.collection_exists(collection_name=COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )

qdrant_client = QdrantClient(path=str(DB_PATH))
ensure_collection(qdrant_client)

def index_ready(client: QdrantClient, document_id: str) -> bool:
    try:
        if not client.collection_exists(collection_name=COLLECTION_NAME):
            return False
        return client.count(
            collection_name=COLLECTION_NAME,
            count_filter=vector_filter([document_id]),
            exact=True,
        ).count > 0
    except Exception:
        return False

# ============================================================
# TOKEN / SORU YÖNLENDİRME
# ============================================================

STOPWORDS = {
    "a","an","and","article","bir","bu","by","da","de","for","from","gibi","icin","ile","in","is",
    "makale","makalede","makalenin","mi","mı","mu","mü","ne","nedir","of","on","olan","olarak",
    "paper","the","this","to","ve","veya","what","which","with","yazar","hangi","nasıl","how",
    "does","was","were","are","is","the"
}

def tokens(text: str) -> List[str]:
    return [
        item for item in re.findall(r"[\wÀ-ÖØ-öø-ÿα-ωΑ-Ω]+", normalize(text))
        if len(item) > 1 and item not in STOPWORDS
    ]

def question_route(question: str) -> Dict[str, Any]:
    q = normalize(question)
    route = {
        "title": any(v in q for v in ("baslik", "basligi", "title", "paper name", "makalenin adi", "makalenin ismi")),
        "authors": any(v in q for v in ("kim yaz", "yazar", "author", "authors", "written by", "yazarlari")),
        "date": any(v in q for v in ("ne zaman yayinlandi", "yayin tarihi", "yayın tarihi", "publication date", "published when", "hangi yil yayinlandi", "year of publication")),
        "abstract": any(v in q for v in ("abstract", "abstract nedir", "makalenin abstracti", "makalenin abstracti nedir")),
        "intro_first": ("giris" in q or "introduction" in q) and any(v in q for v in ("ilk cumle", "first sentence", "baslangic cumlesi")),
        "summary": any(v in q for v in (
            "ozetle", "ozet cikar", "ozetini cikar", "genel ozet", "genel olarak ozet", "summary", "summarize",
            "overall", "makale ne anlatiyor", "makale ne anlatiyor", "konusu ne", "ana fikir", "calismanin amaci",
            "calismanin konusu", "amac nedir", "study aim", "purpose of the study", "what is this paper about",
            "paper overview", "main idea"
        )),
        "conclusion": any(v in q for v in ("sonuc", "sonuclari", "cikarilan", "conclusion", "conclusions", "finding", "findings")),
        "formula": any(v in q for v in (
            "formul", "formula", "formulleri", "formuller", "denklem", "denklemler", "equation", "equations",
            "degisken", "variable", "variables", "katsayi", "coefficient"
        )),
        "theory": any(v in q for v in (
            "teori", "teorik", "kuram", "theory", "theoretical", "model ne anlama", "yaklasim ne anlama",
            "hangi teori", "hangi model"
        )),
        "references": any(v in q for v in (
            "kaynakca", "kaynakcasi", "kaynaklar", "references", "bibliography", "literature cited", "literatur"
        )),
        "methods": any(v in q for v in (
            "yontem", "metodoloji", "method", "methodology", "materials and methods", "kullanilan yontem",
            "hangi yontem", "how was the study conducted", "experimental setup"
        )),
        "results": any(v in q for v in ("bulgu", "bulgular", "sonuclar ne", "results", "result", "finding", "findings", "deney sonucu", "performance")),
        "limitations": any(v in q for v in ("sinirlam", "limitations", "limitation", "kisiti", "kisitlari", "zayif yon", "weakness")),
        "dataset": any(v in q for v in ("veri seti", "dataset", "data set", "kullanilan veri", "hangi veri", "hangi dataset")),
        "contribution": any(v in q for v in ("katki", "katkilari", "contribution", "contributions", "yenilik", "novelty", "yenilikci")),
        "comparison": any(v in q for v in (
            "karsilastir", "karsilastirma", "kiyasla", "kiyaslama", "farklari", "farkliliklari",
            "ortak noktalari", "ortak yonleri", "benzerlikleri", "hangisi daha iyi",
            "hangi makale daha iyi", "makaleleri karsilastir", "compare", "comparison",
            "compare the papers", "differences", "similarities", "common points",
            "which paper is better"
        )),
        "synthesis": any(v in q for v in (
            "sentezle", "sentez", "birlikte degerlendir", "birlikte ele al", "birlestir",
            "bir arada degerlendir", "ortak bir sonuc cikar", "genel bir sonuc cikar",
            "bu makalelerden ortak bir sonuc", "synthesize", "synthesis", "combine",
            "integrate", "integrated analysis", "jointly analyze"
        )),
        "last_page": any(v in q for v in ("son sayfa", "last page", "final page")),
        "all_items": any(v in q for v in ("tum ", "tumunu", "butun", "hepsi", "all ", "every ", "each ")),
        "page": None,
    }
    match = re.search(r"(?:sayfa|page)\s*(?:no\.?\s*)?(\d{1,4})", q)
    if match:
        route["page"] = int(match.group(1))
    route["metadata"] = any(route[k] for k in ("title", "authors", "date"))
    route["multi_document"] = route["comparison"] or route["synthesis"]
    return route

# ============================================================
# İKİ DİLLİ RETRIEVAL
# ============================================================

def soru_turkce_mi(question: str) -> bool:
    q = normalize(question)
    turkish_markers = {"nedir", "nasil", "hangi", "neden", "amac", "ozet", "sonuc", "yontem", "bulgu", "kaynakca", "makale", "calisma", "kullanilan", "ne"}
    return bool(re.search(r"[çğıöşü]", question.lower())) or any(item in q.split() for item in turkish_markers)

def bilingual_queries(question: str) -> List[str]:
    return [question]

def lexical_rank(chunks: Sequence[Dict[str, Any]], queries: Sequence[str], limit: int = 50) -> List[str]:
    wanted = {token for query in queries for token in tokens(query)}
    if not wanted:
        return []
    scored = []
    normalized_queries = [normalize(q) for q in queries]
    for chunk in chunks:
        body = normalize(chunk["text"])
        counts = Counter(tokens(body))
        found = wanted.intersection(counts)
        if not found:
            continue
        score = sum(1 + min(counts[item], 4) * 0.2 for item in found)
        score += len(found) / max(len(wanted), 1)
        score += sum(1.5 for query in normalized_queries if len(query) > 6 and query in body)
        scored.append((score, str(chunk["metadata"]["chunk_id"])))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in scored[:limit]]

def semantic_rank(store: QdrantVectorStore, document_id: str, queries: Sequence[str], limit: int = 30) -> List[str]:
    result, seen = [], set()
    for query in queries:
        try:
            matches = store.similarity_search_with_score(query, k=limit, filter=vector_filter(document_id))
        except Exception:
            continue
        for document, _score in matches:
            chunk_id = str(document.metadata.get("chunk_id", ""))
            if chunk_id and chunk_id not in seen:
                seen.add(chunk_id)
                result.append(chunk_id)
    return result

def semantic_rank_multi(store: QdrantVectorStore, document_ids: Sequence[str], queries: Sequence[str], limit: int = 40) -> List[str]:
    result, seen = [], set()
    active_ids = [str(item) for item in document_ids if item]
    if not active_ids:
        return result

    for query in queries:
        try:
            matches = store.similarity_search_with_score(
                query,
                k=limit,
                filter=vector_filter(active_ids),
            )
        except Exception:
            continue

        for document, _score in matches:
            chunk_id = str(document.metadata.get("chunk_id", ""))
            if chunk_id and chunk_id not in seen:
                seen.add(chunk_id)
                result.append(chunk_id)

    return result

def rrf(rankings: Sequence[Sequence[str]], limit: int = 14) -> List[str]:
    scores = defaultdict(float)
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            scores[item] += 1 / (60 + position)
    return [item for item, _ in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:limit]]

def retrieve_hybrid(store, profile: Dict[str, Any], chunks: Sequence[Dict[str, Any]], question: str, route: Dict[str, Any], aktif_doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    allowed = [c for c in chunks if not aktif_doc_ids or str(c["metadata"].get("document_id")) in set(aktif_doc_ids)]
    if not allowed:
        return []

    if route["page"]:
        allowed = [c for c in allowed if int(c["metadata"]["page"]) == int(route["page"])]
    if not allowed:
        return []

    queries = bilingual_queries(question)
    semantic = semantic_rank_multi(store, aktif_doc_ids or [str(profile["document_id"])], queries, limit=40)
    lexical = lexical_rank(allowed, queries, limit=60)
    allowed_ids = {str(c["metadata"]["chunk_id"]) for c in allowed}
    semantic_allowed = [item for item in semantic if item in allowed_ids]
    selected_ids = rrf([lexical, semantic_allowed], limit=10)
    by_id = {str(c["metadata"]["chunk_id"]): c for c in allowed}

    selected = [by_id[item] for item in selected_ids if item in by_id]

    if len(aktif_doc_ids) > 1:
        balanced = []
        per_document = defaultdict(int)

        for chunk in selected:
            document_id = str(chunk["metadata"].get("document_id", ""))
            if per_document[document_id] < 5:
                balanced.append(chunk)
                per_document[document_id] += 1

        selected = balanced

    return selected

# ============================================================
# MAKALE İLE İLGİLİLİK KONTROLÜ
# ============================================================

def soru_makale_ile_ilgili_mi(question: str, context: str) -> bool:
    if not context.strip():
        return False
    q_tokens = set(tokens(question))
    context_tokens = set(tokens(context))
    overlap = len(q_tokens.intersection(context_tokens)) if q_tokens else 0
    if overlap >= 1:
        return True
    prompt = f"""Sen akademik makale soru uygunluk denetleyicisisin.

Kullanıcının sorusu, aşağıdaki MAKALE BAĞLAMI içindeki bilgiler kullanılarak doğrudan veya makaledeki bilgilerden makul bir sentez/çıkarım yapılarak cevaplanabiliyorsa RELATED yaz.
Soru makaledeki kelimeleri birebir kullanmak zorunda değildir.
Kullanıcının makalede geçen bir kavramın anlamını sorması RELATED'dir.
Kullanıcı makaleyle ilgisi olmayan genel bir konu sorarsa UNRELATED yaz.


Örnek:
Görüntü işleme konulu bir makalede "Bilgisayar nedir?" ve makale bilgisayar kullanımını anlatıyorsa RELATED.
Aynı makalede "Aşk nedir?" ve makalede aşk hakkında bilgi yoksa UNRELATED.

Sadece RELATED veya UNRELATED yaz.

MAKALE BAĞLAMI:
{context}

SORU:
{question}"""
    return normalize(llm_metni(prompt)).startswith("related")

# ============================================================
# CONTEXT / TÜRKÇE CEVAP
# ============================================================

def context_from_chunks(chunks: Sequence[Dict[str, Any]], per_chunk: int = 2300) -> str:
    return "\n\n---\n\n".join(
        f"[Dosya: {c['metadata'].get('dosya_adi', 'Bilinmiyor')} | Kaynak: s. {c['metadata']['page']} | Bölüm: {c['metadata'].get('section','')}]\n{str(c['text'])[:per_chunk]}"
        for c in chunks
    )

def ingilizce_cumle_var_mi(text: str) -> bool:
    if not text.strip():
        return False
    lines = [line.strip() for line in re.split(r"\n+", text) if line.strip()]
    patterns = (
        r"^(the|this|these|those|in this|the study|the paper|according to|results show|figure|table|conclusion|abstract|we |our |it is |they )\b",
        r"\b(the study|this paper|in this study|results indicate|can be seen|was used|were used)\b",
    )
    hits = sum(any(re.search(pattern, line, flags=re.I) for pattern in patterns) for line in lines)
    return hits >= 1 or sum(len(re.findall(r"\b(the|this|that|with|from|which|were|was|used|study|paper|results)\b", text, flags=re.I)) for _ in [0]) >= 4

def turkce_cevap_duzelt(question: str, context: str, answer: str, force: bool = False) -> str:
    if not answer or (not force and not ingilizce_cumle_var_mi(answer)):
        return answer
    prompt = f"""Aşağıdaki akademik cevabı anlamını değiştirmeden doğal, düzgün ve anlaşılır TÜRKÇE ile yeniden yaz.

Kurallar:
- Cevabın açıklama kısmı tamamen Türkçe olsun.
- İngilizce bir cümleyi Türkçeye çevir.
- Kısaltma açılımlarını sadece CONTEXT içinde geçtiği şekliyle koru; bağlamda yer almayan yabancı terim açılımlarını cevaba ekleme.
- Yazar adlarını, makale başlığını, özel isimleri, sayıları, formülleri, değişkenleri ve kaynak künyelerini değiştirme.
- [s. X] kaynak etiketlerini koru.
- Yeni bilgi ekleme.

SORU:
{question}

CONTEXT:
{context}

CEVAP:
{answer}

SADECE DÜZELTİLMİŞ CEVABI VER."""
    corrected = llm_metni(prompt)
    return corrected or answer

def answer_from_evidence(question: str, context: str, task: str = "", model: str = "local") -> str:
    prompt = f"""Sen teknik ve mühendislik makalelerini inceleyen bir araştırma asistanısın.

TEMEL YAZIM PRENSİPLERİ (HER ALAN İÇİN GEÇERLİ):
1. ÇEVİRİ DEĞİL, ANLATIM YAP: Verilen İngilizce parçaları kelime kelime çevirmeye çalışma. Önce teknik mantığı anla, ardından bir mühendisin ekip arkadaşına anlatacağı gibi doğal, modern ve akıcı bir Türkçe ile ifade et.
2. DİL VE TERİM STANDARDI:
   - Eski, ağdalı veya yapay sözlük karşılıkları (artalan, kestirim, sadakat vb.) yerine modern mühendislikte kullanılan yalın karşılıkları (arka plan, tahmin/hesaplama, doğruluk vb.) seç.
   - Türkçede doğal bir karşılığı bulunmayan veya zorlama duran özel teknik terimleri (örn. 'watershed', 'convolution', 'transformer') zorla Türkçeleştirmek yerine doğrudan kabul görmüş teknik haliyle kullan.
   - Parantez içinde gereksiz iki dilli tekrarlar (ör. "kelime (word)") yapma.
3. BAĞLAM VE GÜVENİLİRLİK:
   - Yalnızca CONTEXT içindeki bilgilere dayan, dışarıdan uydurma bilgi ekleme.
   - Metne [s. 1] gibi atıf etiketleri ekleme.

EK GÖREV:
{task}

CONTEXT:
{context}

SORU:
{question}

SADECE DOĞAL, ANLAŞILIR VE PROFESYONEL TÜRKÇE İLE CEVAP VER:"""
    
    draft = llm_metni(prompt, model=model)
    if not draft:
        return "Verilen makalelerden geçerli bir sonuç üretilemedi."
    return draft
def multi_document_answer(question: str, context: str, task: str = "") -> str:
    prompt = f"""Sen birden fazla akademik makaleyi birlikte analiz eden araştırma asistanısın.

Kurallar:
- Cevabı doğal ve düzgün TÜRKÇE yaz.
- Teknik terimleri, özel isimleri, kısaltmaları, formülleri, değişkenleri ve sayıları değiştirme.
- Yalnızca verilen makale bağlamlarını kullan; dış bilgi ekleme.
- Her önemli bilginin hangi makaleden geldiğini açıkça belirt.
- Karşılaştırmada makaleleri ayrı ayrı değerlendir, ardından benzerlik ve farklılıkları belirt.
- Sentezde makalelerdeki bilgileri ortak bir değerlendirmede birleştir.
- Çelişki varsa açıkça belirt.
- Makul çıkarımları yalnızca verilen bilgilerden yap.
- Kaynak etiketlerini [Dosya: X | s. Y] biçiminde koru.
- Yeterli kanıt yoksa bunu belirt.

EK GÖREV:
{task}

MAKALELER:
{context}

SORU:
{question}

SADECE TÜRKÇE CEVAP VER."""
    draft = llm_metni(prompt)
    if not draft:
        return "Verilen makalelerden geçerli bir karşılaştırma veya sentez üretilemedi."
    return turkce_cevap_duzelt(question, context, draft, force=True)

# ============================================================
# METADATA
# ============================================================


def metadata_answer(route: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[Optional[str], List[int]]:
    lines = []
    if route["title"]:
        title = profile.get("title")
        lines.append(f"Makalenin başlığı: {title}." if title else "Makalenin başlığı güvenilir biçimde saptanamadı.")
    if route["authors"]:
        authors = profile.get("authors") or []
        lines.append("Makalenin yazarları: " + ", ".join(authors) + "." if authors else "Yazar bilgisi PDF'nin ön bilgisinde açıkça saptanamadı.")
    if route["date"]:
        date = profile.get("publication_date")
        venue = profile.get("journal_or_venue")
        if date:
            line = f"Makalenin PDF'de görünen yayın tarihi: {date}."
            if venue:
                line += f" Yayın yeri/dergi: {venue}."
            lines.append(line)
        else:
            lines.append("Yayın tarihi PDF'nin ön bilgisinde açıkça saptanamadı.")
    return (("\n\n".join(lines) + "\n\n[s. 1]", [1]) if lines else (None, []))

# ============================================================
# ÖZEL BÖLÜMLER
# ============================================================

def ozet_context(profile: Dict[str, Any], chunks: Sequence[Dict[str, Any]], max_chars: int = 22000) -> Tuple[str, List[int]]:
    sections = [
        ("Özet", profile.get("abstract"), profile.get("abstract_pages", []), 3500),
        ("Giriş", section_text(chunks, "introduction", 4500)[0], section_text(chunks, "introduction", 4500)[1], 4000),
        ("Yöntem", section_text(chunks, "methods", 4500)[0], section_text(chunks, "methods", 4500)[1], 4500),
        ("Bulgular", section_text(chunks, "results", 4500)[0], section_text(chunks, "results", 4500)[1], 5000),
        ("Sonuç", profile.get("conclusion"), profile.get("conclusion_pages", []), 3500),
    ]
    parts, pages = [], []
    total = 0
    for name, body, source_pages, local_limit in sections:
        if not body:
            continue
        body = str(body)[:local_limit]
        if total + len(body) > max_chars:
            body = body[:max(0, max_chars - total)]
        if not body:
            break
        source_label = ", ".join(f"s. {p}" for p in source_pages) or "sayfa bilinmiyor"
        parts.append(f"[Kaynak: {source_label} | {name}]\n{body}")
        pages.extend(source_pages)
        total += len(body)
        if total >= max_chars:
            break
    if not parts:
        sampled = tum_makale_context(chunks, max_chars)
        return sampled[0], sampled[1]
    return "\n\n---\n\n".join(parts), sorted(set(pages))

def multi_document_context(profiller: Sequence[Dict[str, Any]], chunks: Sequence[Dict[str, Any]], max_chars: int = 12000) -> Tuple[str, List[int]]:
    parts, pages, used = [], [], 0
    chunks_by_document = defaultdict(list)
    for chunk in chunks:
        document_id = str(chunk["metadata"].get("document_id", ""))
        chunks_by_document[document_id].append(chunk)

    for profile in profiller:
        document_id = str(profile.get("document_id", ""))
        file_name = profile.get("dosya_adi", "Bilinmeyen PDF")
        document_chunks = chunks_by_document.get(document_id, [])
        body_parts = [f"[Makale: {file_name}]"]

        if profile.get("title"):
            body_parts.append(f"[Başlık]\n{profile['title']}")
        if profile.get("authors"):
            body_parts.append(f"[Yazarlar]\n{', '.join(profile['authors'])}")
        if profile.get("abstract"):
            body_parts.append(f"[Özet]\n{str(profile['abstract'])[:2200]}")
            pages.extend(profile.get("abstract_pages", []))

        intro, intro_pages = section_text(document_chunks, "introduction", 1800)
        methods, methods_pages = section_text(document_chunks, "methods", 2200)
        results, results_pages = section_text(document_chunks, "results", 2400)

        if intro:
            body_parts.append(f"[Giriş]\n{intro}")
            pages.extend(intro_pages)
        if methods:
            body_parts.append(f"[Yöntem]\n{methods}")
            pages.extend(methods_pages)
        if results:
            body_parts.append(f"[Bulgular]\n{results}")
            pages.extend(results_pages)
        if profile.get("conclusion"):
            body_parts.append(f"[Sonuç]\n{str(profile['conclusion'])[:2200]}")
            pages.extend(profile.get("conclusion_pages", []))

        if len(body_parts) == 1 and document_chunks:
            fallback = context_from_chunks(document_chunks[:8], per_chunk=1800)
            body_parts.append(fallback)

        remaining = max_chars - used
        if remaining <= 0:
            break

        document_text = "\n\n".join(body_parts)[:remaining]
        parts.append(document_text)
        used += len(document_text)

    return "\n\n---\n\n".join(parts)[:max_chars], sorted(set(int(p) for p in pages))

def tum_makale_context(chunks: Sequence[Dict[str, Any]], max_chars: int = 22000) -> Tuple[str, List[int]]:
    if not chunks:
        return "", []
    if sum(len(str(c.get("text", ""))) for c in chunks) <= max_chars:
        selected = list(chunks)
    else:
        count = max(8, min(18, max_chars // 1200))
        step = max(1, len(chunks) // count)
        selected = [chunks[min(i, len(chunks) - 1)] for i in range(0, len(chunks), step)][:count]
    text = context_from_chunks(selected, per_chunk=max(1000, max_chars // max(len(selected), 1)))
    return text[:max_chars], sorted({int(c["metadata"]["page"]) for c in selected})

def ozel_bolum_yaniti(question: str, route: Dict[str, Any], profile: Dict[str, Any], chunks: Sequence[Dict[str, Any]]) -> Tuple[Optional[str], List[int]]:
    if route["intro_first"] and profile.get("introduction_first_sentence"):
        pages = list(profile.get("introduction_pages") or [1])
        context = f"[Kaynak: s. {pages[0]} | Giriş]\n{profile['introduction_first_sentence']}"
        return answer_from_evidence(question, context, "Giriş bölümünün ilk cümlesini anlamını koruyarak Türkçe açıkla."), pages
    if route["abstract"] and profile.get("abstract"):
        pages = list(profile.get("abstract_pages") or [])
        context = "\n".join(f"[Kaynak: s. {p} | Özet]" for p in pages) + "\n" + profile["abstract"]
        return answer_from_evidence(question, context, "Makalenin abstract bölümünü Türkçe anlat."), pages
    if route["summary"]:
        context, pages = ozet_context(profile, chunks)
        if context:
            return answer_from_evidence(
                question,
                context,
                "Makalenin genel özetini çıkar. Konuyu, amacı, kullanılan yöntemi, veri setini/deney düzenini, önemli bulguları, temel katkıları ve sonucunu mümkün olduğunca eksiksiz ama anlaşılır biçimde birleştir.",
            ), pages
    if route["conclusion"] and profile.get("conclusion"):
        pages = list(profile.get("conclusion_pages") or [])
        context = "\n".join(f"[Kaynak: s. {p} | Sonuç]" for p in pages) + "\n" + profile["conclusion"]
        return answer_from_evidence(question, context, "Makalenin sonuç bölümünü Türkçe olarak açıkla; sonuç bölümündeki temel bulguları ve çıkarımları belirt."), pages
    if route["references"] and profile.get("references"):
        pages = list(profile.get("references_pages") or [])
        context = "\n".join(f"[Kaynakça: s. {p}]" for p in pages) + "\n" + profile["references"]
        answer = "Makalede yer alan kaynakça aşağıdadır:\n\n" + str(profile["references"]).strip()
        return answer, pages
    return None, []

# ============================================================
# FORMÜLLER
# ============================================================

def formula_number(question: str) -> Optional[str]:
    match = re.search(r"(?:formul|formula|denklem|equation)\s*(?:no\.?\s*)?[\[(]?(\d{1,4})", normalize(question))
    return match.group(1) if match else None

def formula_multiple_intent(question: str) -> bool:
    q = normalize(question)
    return any(v in q for v in (
        "hangi formul", "hangi formuller", "hangi formula", "hangi formulas", "hangi equation", "hangi equations",
        "hangi denklem", "hangi denklemler", "tum formul", "tum formuller", "butun formul", "butun formuller",
        "hepsi", "all formula", "all formulas", "all equation", "all equations", "kullanilan formuller",
        "kullanilan formul", "used formulas", "used equations"
    ))

def formula_candidates(profile: Dict[str, Any], question: str, route: Dict[str, Any]) -> List[Dict[str, Any]]:
    formulas = list(profile.get("formulas") or [])
    if not formulas:
        return []
    number = formula_number(question)
    if number:
        found = [f for f in formulas if str(f.get("label") or "").strip("()[] ") == number]
        if found:
            return found
    if route["last_page"]:
        return [f for f in formulas if int(f["page"]) == int(profile["page_count"])]
    if route["page"]:
        return [f for f in formulas if int(f["page"]) == int(route["page"])]
    if route["all_items"] or formula_multiple_intent(question):
        return formulas
    wanted = set(tokens(question))
    ranked = []
    for formula in formulas:
        corpus = f"{formula.get('formula','')} {formula.get('context','')} {formula.get('label','')}"
        ranked.append((len(wanted.intersection(tokens(corpus))), formula))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in ranked[:5]]

def formula_context(formulas: Sequence[Dict[str, Any]]) -> str:
    return "\n\n---\n\n".join(
        f"[Kaynak: s. {f['page']}{' ' + f['label'] if f.get('label') else ''}]\nFormül: {f['formula']}\nYakın metin: {f.get('context','')}"
        for f in formulas
    )

def formula_answer(question: str, formulas: list, multiple: bool = False) -> str:
    formula_context = "\n\n".join([
        f"Formül (Sayfa {f.get('page', '?')}):\n{f.get('text', '')}" 
        for f in formulas
    ])
    
    prompt = f"""Sen akademik makalelerdeki matematiksel modelleri analiz eden bir mühendissin.

KESİN SINIRLANDIRMA VE ÇEVİRİ KURALLARI:
1. SADECE BAĞLAMA SADIK KAL: Yalnızca aşağıdaki "FORMÜLLER" bölümünde verilen metne ve denklemlere dayanarak cevap ver. Dışarıdan genel geçer ders kitabı bilgisi, kontrol teorisi veya "Çıktı/Giriş" gibi jenerik formüller UYDURMA.
2. DOĞRU TERMİNOLOJİ: "Gain" kelimesini ASLA "gelir" olarak çevirme; görüntü işleme ve sinyal bağlamında bunun karşılığı "kazanç"tır (Örn: kanal kazancı / channel gain).
3. EKSİK BİLGİ DURUMU: Eğer sorulan formülün ne işe yaradığı verilen metinde açıkça yazmıyorsa veya formül metni eksikse, genel bilgi vermek yerine "Makaledeki metinde bu formülün detayı/bağlamı bulunmamaktadır" diyerek yanıtı reddet.
4. ÇEVİRİ YAKLAŞIMI: İngilizce metni kelime kelime çevirme. Makalenin asıl amacını kavrayarak denklemin işlevini doğal bir Türkçe ile açıkla.

FORMÜLLER (Sadece bu içeriği kullan):
{formula_context}

SORU:
{question}

SADECE BAĞLAMA SADIK VE DOĞAL TÜRKÇE İLE AÇIKLA:"""

    return llm_metni(prompt)

# ============================================================
# PDF VURGULAMA
# ============================================================

def highlighted_pdf(dosya_adi: str, chunks: Sequence[Dict[str, Any]], color: Optional[str]) -> Optional[str]:
    if not chunks:
        return None
    output_name = f"hl_{int(time.time() * 1000)}_{dosya_adi}"
    pdf = None
    try:
        pdf = fitz.open(str(UPLOAD_DIR / dosya_adi))
        rgb = hex_to_rgb_float(color)
        for chunk in chunks:
            page_number = int(chunk["metadata"]["page"])
            if not 1 <= page_number <= len(pdf):
                continue
            needle = ilk_cumle(temiz_metin(str(chunk["text"])))[:180]
            if len(needle) < 12:
                continue
            for rect in pdf[page_number - 1].search_for(needle):
                annotation = pdf[page_number - 1].add_highlight_annot(rect)
                annotation.set_colors(stroke=rgb)
                annotation.set_opacity(0.35)
                annotation.update()
        pdf.save(str(UPLOAD_DIR / output_name))
        return output_name
    except Exception:
        return None
    finally:
        if pdf is not None:
            pdf.close()

# ============================================================
# PDF
# ============================================================

@app.get("/pdf/{dosya_adi}")
async def pdf_getir(dosya_adi: str):
    path = UPLOAD_DIR / dosya_guvenli_adi(dosya_adi)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF dosyası bulunamadı.")
    return FileResponse(path, media_type="application/pdf")

@app.get("/documents/{dosya_adi}/profile")
async def profil_getir(dosya_adi: str):
    safe_name = dosya_guvenli_adi(dosya_adi)
    pdf_path = UPLOAD_DIR / safe_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF dosyası bulunamadı.")
    document_id = await asyncio.get_running_loop().run_in_executor(REQUEST_EXECUTOR, belge_hashi, pdf_path)
    profile = json_oku(profil_yolu(safe_name, document_id), {})
    if not profile:
        raise HTTPException(status_code=404, detail="Makale profili bulunamadı. PDF'yi yeniden yükleyin.")
    return profile

# ============================================================
# PDF İÇİ ARAMA
# ============================================================

def pdf_search_sync(istek: SoruIstegi) -> Dict[str, Any]:
    dosya_adi = dosya_guvenli_adi(istek.dosya_adi)
    path = UPLOAD_DIR / dosya_adi
    if not path.exists():
        return {"success": False, "matches": []}
    pdf = None
    try:
        pdf = fitz.open(str(path))
        matches = []
        color = hex_to_rgb_float(istek.theme_color)
        query = istek.question.strip()
        if not query:
            return {"success": False, "matches": []}

        for index in range(len(pdf)):
            page = pdf[index]
            rects = page.search_for(query, quads=True)

            if not rects and any(ord(char) > 127 for char in query):
                query_normalized = unicodedata.normalize("NFKD", query)
                query_normalized = "".join(
                    char for char in query_normalized if not unicodedata.combining(char)
                )

                page_text = unicodedata.normalize("NFKD", page.get_text("text"))
                page_text = "".join(
                    char for char in page_text if not unicodedata.combining(char)
                )

                if normalize(query_normalized) in normalize(page_text):
                    words = page.get_text("words")
                    query_tokens = tokens(query_normalized)

                    if query_tokens:
                        for word in words:
                            word_text = normalize(str(word[4]))
                            if any(token in word_text for token in query_tokens):
                                rects.append(fitz.Rect(word[:4]))

            if not rects:
                continue

            page.add_highlight_annot(rects)
            for annotation in page.annots() or []:
                annotation.set_colors(stroke=color)
                annotation.set_opacity(0.35)
                annotation.update()

            matches.append(index + 1)

        if not matches:
            return {"success": False, "matches": []}

        result_name = f"search_{int(time.time() * 1000)}_{dosya_adi}"
        pdf.save(str(UPLOAD_DIR / result_name))
        return {"success": True, "search_file": result_name, "matches": matches}
    finally:
        if pdf is not None:
            pdf.close()

@app.post("/pdf_search_advanced")
async def pdf_search_advanced(istek: SoruIstegi):
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(REQUEST_EXECUTOR, pdf_search_sync, istek)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# ============================================================
# ANA SORU
# ============================================================

def soru_sor_sync(istek: SoruIstegi) -> Dict[str, Any]:
    dosya_listesi = list(getattr(istek, "dosya_adlari", []) or [])
    eski_dosya = getattr(istek, "dosya_adi", None)
    if not dosya_listesi and eski_dosya:
        dosya_listesi = [eski_dosya]
    dosya_listesi = list(dict.fromkeys(dosya_listesi))

    if not dosya_listesi:
        return {"answer": "Lütfen önce bir PDF makalesi yükleyin.", "sources": [], "highlighted_file": None, "out_of_context": True}

    tum_chunks, profiller, aktif_doc_ids = [], [], []
    for d_adi in dosya_listesi:
        guvenli_ad = dosya_guvenli_adi(d_adi)
        p_path = UPLOAD_DIR / guvenli_ad
        if not p_path.exists():
            continue
        d_id = belge_hashi(p_path)
        if d_id in aktif_doc_ids:
            continue
        profile = json_oku(profil_yolu(guvenli_ad, d_id), {})
        chunks_for_file = json_oku(parca_yolu(guvenli_ad, d_id), [])
        if not profile or not chunks_for_file:
            continue
        aktif_doc_ids.append(d_id)
        profiller.append(profile)
        tum_chunks.extend(chunks_for_file)

    if not profiller or not tum_chunks:
        return {"answer": "Seçilen makalelerden en az biri için güncel analiz indeksi bulunamadı. Lütfen ilgili PDF'yi yeniden yükleyin.", "sources": [], "highlighted_file": None, "out_of_context": True}

    question = istek.question.strip()
    if not question:
        return {"answer": "Lütfen bir soru yazın.", "sources": [], "highlighted_file": None, "out_of_context": True}

    route = question_route(question)
    profile = profiller[0]
    chunks = tum_chunks

    # Birden fazla PDF aktifse bütün sorular belge bazlı ortak bağlamdan cevaplanır.
    if len(profiller) > 1:
        if route["metadata"]:
            lines, meta_pages = [], []
            for item in profiller:
                file_name = item.get("dosya_adi", "Bilinmeyen PDF")
                lines.append(f"### {file_name}")
                if route["title"]:
                    lines.append(f"Başlık: {item.get('title') or 'Saptanamadı'}")
                if route["authors"]:
                    authors = item.get("authors") or []
                    lines.append("Yazarlar: " + (", ".join(authors) if authors else "Saptanamadı"))
                if route["date"]:
                    lines.append(f"Yayın tarihi: {item.get('publication_date') or 'Saptanamadı'}")
                meta_pages.append(1)
            return {"answer": "\n\n".join(lines), "sources": sorted(set(meta_pages)), "highlighted_file": None, "out_of_context": False}

        if route["formula"] and route["all_items"]:
            formula_parts, formula_pages = [], []
            for item in profiller:
                formulas = item.get("formulas") or []
                if formulas:
                    formula_parts.append(f"### {item.get('dosya_adi', 'Bilinmeyen PDF')}\n{formula_answer(question, formulas, True)}")
                    formula_pages.extend(int(f["page"]) for f in formulas)
            if formula_parts:
                return {"answer": "\n\n".join(formula_parts), "sources": sorted(set(formula_pages)), "highlighted_file": None, "out_of_context": False}

        multi_context, multi_pages = multi_document_context(profiller, chunks, max_chars=10000)
        selected = retrieve_hybrid(get_vector_store(qdrant_client), profile, chunks, question, route, aktif_doc_ids)
        retrieval_context = context_from_chunks(selected, per_chunk=1600) if selected else ""

        if retrieval_context:
            context = retrieval_context
        else:
            context = multi_context

        article_intent = route["multi_document"] or any(route[k] for k in ("metadata", "abstract", "intro_first", "summary", "conclusion", "formula", "theory", "references", "methods", "results", "limitations", "dataset", "contribution"))
        if not article_intent and not soru_makale_ile_ilgili_mi(question, context):
            return {"answer": "Seçilen makalelerde bu bilgi bulunamadı.", "sources": [], "highlighted_file": None, "out_of_context": True}

        tasks = []
        if route["comparison"]:
            tasks.append("Makaleleri ayrı ayrı değerlendir ve ardından yöntem, veri, bulgu, katkı ve sonuçları karşılaştır.")
        if route["synthesis"]:
            tasks.append("Makalelerdeki bilgileri birleştirerek ortak bir sentez oluştur ve birlikte değerlendirilebilecek sonuçları çıkar.")
        if route["summary"]:
            tasks.append("Her makalenin konusunu, amacını, yöntemini, önemli bulgularını ve sonucunu verip ardından ortak bir genel değerlendirme yap.")
        if route["methods"]:
            tasks.append("Her makalenin yöntemini ayrı ayrı açıklayıp aralarındaki farkları belirt.")
        if route["results"]:
            tasks.append("Her makalenin bulgularını ve performans sonuçlarını ayrı ayrı verip karşılaştır.")
        if route["dataset"]:
            tasks.append("Veri setlerini makale bazında karşılaştır.")
        if route["limitations"]:
            tasks.append("Makalelerin belirtilen sınırlılıklarını ayrı ayrı ver ve varsa ortak sınırlılıkları belirt.")
        if route["contribution"]:
            tasks.append("Çalışmaların temel katkı ve yeniliklerini ayrı ayrı açıklayıp karşılaştır.")
        if route["theory"]:
            tasks.append("Kullanılan teori, model veya yaklaşımları makale bazında açıklayıp karşılaştır.")

        answer = multi_document_answer(question, context, "\n".join(tasks))
        return {"answer": answer, "sources": multi_pages, "highlighted_file": None, "out_of_context": False}

    # Tek PDF akışı mevcut davranışını korur.
    meta, meta_pages = metadata_answer(route, profile)
    only_meta = route["metadata"] and not any(route[k] for k in ("abstract", "intro_first", "summary", "conclusion", "formula", "theory", "references", "methods", "results", "limitations", "dataset", "contribution", "comparison", "synthesis"))
    if meta and only_meta:
        return {"answer": meta, "sources": meta_pages, "highlighted_file": None, "out_of_context": False}

    if route["formula"]:
        formulas = formula_candidates(profile, question, route)
        answer = formula_answer(question, formulas, bool(route["all_items"] or formula_multiple_intent(question) or route["last_page"]))
        return {"answer": f"{meta}\n\n{answer}" if meta else answer, "sources": sorted({int(f["page"]) for f in formulas} | set(meta_pages)), "highlighted_file": None, "out_of_context": False}

    special, special_pages = ozel_bolum_yaniti(question, route, profile, chunks)
    if special:
        return {"answer": f"{meta}\n\n{special}" if meta else special, "sources": sorted(set(meta_pages + special_pages)), "highlighted_file": None, "out_of_context": False}

    store = get_vector_store(qdrant_client)
    selected = retrieve_hybrid(store, profile, chunks, question, route, aktif_doc_ids)
    if not selected:
        return {"answer": "Makalede bu bilgi bulunamadı.", "sources": [], "highlighted_file": None, "out_of_context": True}

    context = context_from_chunks(selected)
    
    # Türkçe soru - İngilizce makale uyuşmazlığında hatalı bloklamayı engellemek için
    # kontrolü doğrudan context'in doluluğuna ve LLM'e bırakıyoruz:
    known_article_intent = any(route[k] for k in ("metadata", "abstract", "intro_first", "summary", "conclusion", "formula", "theory", "references", "methods", "results", "limitations", "dataset", "contribution", "comparison", "synthesis"))
    
    # Eğer özel bir niyet yoksa ve soru makaleyle tamamen alakasız görünüyorsa kontrol et (ama hata fırlatmak yerine bağlamı modele ilet)
    if not known_article_intent and not soru_makale_ile_ilgili_mi(question, context):
        # Katı bloklama kaldırıldı; kararı LLM modeline devrediyoruz
        pass

    tasks = []
    if route["theory"]: tasks.append("Soruda geçen teori, model veya yaklaşımı yalnızca makalenin onu kullandığı anlam üzerinden açıkla. Tanım ve kullanım amacını makaledeki bilgilerden çıkar. Dışarıdan ders kitabı bilgisi ekleme.")
    if route["methods"]: tasks.append("Makalenin kullandığı yöntemi adım adım ve anlaşılır Türkçe ile açıkla. Veri, işlem sırası, model/algoritma ve değerlendirme adımlarını bağlamda bulunduğu ölçüde belirt.")
    if route["results"]: tasks.append("Makalenin bulgularını ve performans sonuçlarını soruyla ilişkili biçimde açıkla. Sayısal değerleri aynen koru ve hangi deney/karşılaştırmaya ait olduklarını belirt.")
    if route["limitations"]: tasks.append("Makalenin açıkça belirttiği veya makaledeki bulgulardan doğrudan çıkarılabilen sınırlılıkları belirt; dışarıdan eleştiri ekleme.")
    if route["dataset"]: tasks.append("Kullanılan veri seti/verileri, veri kaynağı, örnek sayısı ve ilgili özellikleri makalede bulunduğu ölçüde açıkla.")
    if route["contribution"]: tasks.append("Çalışmanın temel katkılarını ve yeniliklerini, yalnızca makaledeki kanıtlara dayanarak açıkla.")
    if route["conclusion"]: tasks.append("Makaledeki sonuç ve bulguları soruyla ilişkili biçimde açıkla.")
    if route["title"]: tasks.append("Makale başlığını kaynakta geçtiği biçimde koru; başlığı çevirme. Başlığın etrafındaki açıklamalar Türkçe olsun.")
    if route["authors"]: tasks.append("Yazar isimlerini kaynakta göründüğü biçimde koru. Açıklamalar Türkçe olsun.")
    if route["comparison"]: tasks.append("Tek makale bağlamında sorulan karşılaştırmayı yalnızca makaledeki karşılaştırmalar varsa açıkla.")
    if route["synthesis"]: tasks.append("Makaledeki bilgileri birleştirerek kanıta dayalı bir sentez yap.")

    # DÜZELTME: Sıfırlamak yerine biriken görevleri birleştiriyoruz
    task = "\n".join(tasks)
    
    answer = answer_from_evidence(question, context, task, model=getattr(istek, "model", "local"))
    
    # Model "Yeterli kanıt yok" veya "bulunamadı" derse out_of_context bayrağını belirle
    is_out_of_context = "yeterli bilgi bulunmamaktadır" in answer.lower() or "bilgi bulunamadı" in answer.lower()
    
    hedef_dosya = selected[0]["metadata"].get("dosya_adi", dosya_listesi[-1]) if selected else dosya_listesi[-1]
    return {
        "answer": f"{meta}\n\n{answer}" if meta else answer, 
        "sources": sorted({int(c["metadata"]["page"]) for c in selected} | set(meta_pages)), 
        "highlighted_file": highlighted_pdf(hedef_dosya, selected, getattr(istek, "theme_color", "#2563EB")), 
        "out_of_context": is_out_of_context
    }

def pdf_sayfalari_ve_parcalari(dosya_yolu, dosya_adi, dosya_id):
    doc = fitz.open(str(dosya_yolu))
    pages = []
    chunks = []
    
    for sayfa_idx in range(len(doc)):
        sayfa = doc[sayfa_idx]
        sayfa_no = sayfa_idx + 1
        metin = sayfa.get_text().encode("utf-8", "ignore").decode("utf-8")
        pages.append({"sayfa": sayfa_no, "metin": metin})
        
        # Metni yaklaşık 500'er karakterlik bloklara böl
        chunk_boyutu = 500
        adim = 400  # 100 karakter örtüşme (overlap)
        for i in range(0, len(metin), adim):
            parca_metin = metin[i:i + chunk_boyutu].strip()
            if parca_metin:
                chunks.append({
                    "metin": parca_metin,
                    "sayfa": sayfa_no,
                    "dosya_adi": dosya_adi,
                    "dosya_id": dosya_id
                })
                
    doc.close()
    return pages, chunks

@app.post("/upload")
async def dosya_yukle(file: UploadFile = File(...)):
    try:
        guvenli_ad = dosya_guvenli_adi(file.filename)
        hedef_yol = UPLOAD_DIR / guvenli_ad
        
        # 1. Dosyayı diske kaydet
        with open(hedef_yol, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        d_id = belge_hashi(hedef_yol)
        profile_path = profil_yolu(guvenli_ad, d_id)
        chunks_path = parca_yolu(guvenli_ad, d_id)
        
        loop = asyncio.get_running_loop()
        
        # 2. PDF sayfalarını oku ve parçala (Eğer önceden indekslenmemişse)
        if not profile_path.exists() or not chunks_path.exists():
            # Sayfaları ve chunk'ları çıkaran fonksiyonları çalıştır
            pages, chunks = await loop.run_in_executor(REQUEST_EXECUTOR, pdf_sayfalari_ve_parcalari, hedef_yol, guvenli_ad, d_id)
            
            # Profili oluştur
            profile = await loop.run_in_executor(REQUEST_EXECUTOR, makale_profili, hedef_yol, pages, chunks, d_id, guvenli_ad)
            
            # JSON dosyalarını diske kaydet
            await loop.run_in_executor(REQUEST_EXECUTOR, json_yaz, profile_path, profile)
            await loop.run_in_executor(REQUEST_EXECUTOR, json_yaz, chunks_path, chunks)
            
            # Qdrant vektör tabanına ekle
            store = get_vector_store(qdrant_client)
            await loop.run_in_executor(REQUEST_EXECUTOR, store.add_documents, [
                Document(page_content=c["text"], metadata=c["metadata"]) for c in chunks
            ])

        return {
            "status": "success",
            "dosya_adi": guvenli_ad,
            "doc_id": d_id,
            "message": "Dosya başarıyla yüklendi ve indekslendi."
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dosya yükleme/indeksleme hatası: {str(exc)}") from exc

@app.post("/ask")
async def soru_sor(istek: SoruIstegi):
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(REQUEST_EXECUTOR, soru_sor_sync, istek)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# ============================================================
# PDF YÜKLEME
# ============================================================

SECTION_ALIASES = {
    "abstract": ("abstract", "ozet"),
    "introduction": ("introduction", "giris", "background", "arka plan"),
    "conclusion": ("conclusion", "conclusions", "sonuc", "sonuclar", "tartisma ve sonuc", "discussion and conclusion"),
    "methods": ("method", "methods", "methodology", "yontem", "metot", "materyal ve yontem", "materials and methods"),
    "results": ("result", "results", "findings", "bulgular"),
    "references": ("references", "bibliography", "kaynakca", "kaynaklar", "literature cited", "literatur")
}

def normalize_heading(text: str) -> str:
    text = re.sub(r"^\s*(?:#{1,6}|\d+(?:\.\d+)*[.)]?)\s*", "", text)
    return normalize(re.sub(r"[^\wçğıöşüÇĞİÖŞÜ -]", " ", text))

def heading_kind(line: str) -> Optional[str]:
    raw = line.strip()
    candidate = normalize_heading(raw)
    known = any(candidate == alias or candidate.startswith(alias + " ") for aliases in SECTION_ALIASES.values() for alias in aliases)
    numbered = bool(re.match(r"^\s*\d+(?:\.\d+)*[.)]?\s+[A-ZÇĞİÖŞÜ]", raw))
    upper = len(raw) < 90 and raw.isupper() and len(raw.split()) <= 10
    if not (raw.startswith("#") or known or numbered or upper):
        return None
    return temiz_metin(re.sub(r"^\s*#+\s*", "", raw))[:180] or None

def sayfalari_cikar(pdf_path: Path) -> List[Dict[str, Any]]:
    markdown_pages = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    if not isinstance(markdown_pages, list):
        markdown_pages = []
    pdf = fitz.open(str(pdf_path))
    pages = []
    try:
        for index in range(len(pdf)):
            markdown = ""
            if index < len(markdown_pages) and isinstance(markdown_pages[index], dict):
                markdown = str(markdown_pages[index].get("text") or "")
            raw = pdf[index].get_text("text", sort=True)
            pages.append({"page": index + 1, "raw": raw, "markdown": markdown, "text": markdown.strip() or raw.strip()})
    finally:
        pdf.close()
    return pages

def title_candidates(pdf_path: Path) -> List[str]:
    pdf = fitz.open(str(pdf_path))
    candidates = []
    try:
        if not pdf:
            return []
        for block in pdf[0].get_text("dict", sort=True).get("blocks", []):
            if block.get("type") != 0:
                continue
            spans = [span for line in block.get("lines", []) for span in line.get("spans", [])]
            text = "".join(str(span.get("text", "")) for span in spans).strip()
            if not 8 <= len(text) <= 500:
                continue
            lowered = normalize(text)
            if any(v in lowered for v in ("doi", "http", "www.", "@", "issn", "copyright")):
                continue
            sizes = [float(span.get("size", 0)) for span in spans if str(span.get("text", "")).strip()]
            if sizes:
                candidates.append((max(sizes), float(block.get("bbox", [0, 9999])[1]), text))
    finally:
        pdf.close()
    candidates.sort(key=lambda row: (-row[0], row[1]))
    unique = []
    for _, _, value in candidates:
        if normalize(value) not in {normalize(item) for item in unique}:
            unique.append(value)
        if len(unique) == 8:
            break
    return unique

def paragraflar(text: str) -> List[str]:
    text = text.replace("\r", "")
    values = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    return values if len(values) > 1 else [line.strip() for line in text.split("\n") if line.strip()]

def formullu_mu(text: str) -> bool:
    value = text.strip()
    if any(m in value for m in ("$$", r"\[", r"\]", r"\frac", r"\sum", r"\int", r"\begin{equation")):
        return True
    return len(value) <= 600 and "=" in value and bool(re.search(r"[A-Za-zα-ωΑ-Ω]\s*(?:[_^]|=)|[_^]", value))

def uzun_parcayi_bol(text: str) -> List[str]:
    if len(text) <= CHUNK_SIZE or formullu_mu(text):
        return [text]
    pieces = []
    remaining = text.strip()
    while len(remaining) > CHUNK_SIZE:
        cut = max(remaining.rfind("\n", 0, CHUNK_SIZE), remaining.rfind(". ", 0, CHUNK_SIZE), remaining.rfind("; ", 0, CHUNK_SIZE), remaining.rfind(" ", 0, CHUNK_SIZE))
        if cut < CHUNK_SIZE // 3:
            cut = CHUNK_SIZE
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces

def bolum_duyarli_parcalar(pages: Sequence[Dict[str, Any]], document_id: str, dosya_adi: str) -> List[Dict[str, Any]]:
    chunks = []
    section = "Ön Bilgiler"
    counter = 0
    for page in pages:
        page_number = int(page["page"])
        buffer = []
        buffer_section = section
        size = 0
        def flush():
            nonlocal buffer, size, counter
            body = "\n\n".join(buffer).strip()
            if len(temiz_metin(body)) >= 20:
                counter += 1
                chunk_id = f"{document_id}:c{counter}"
                chunks.append({
                    "id": chunk_id,
                    "text": body,
                    "metadata": {
                        "document_id": document_id,
                        "dosya_adi": dosya_adi,
                        "page": page_number,
                        "section": buffer_section,
                        "chunk_id": chunk_id,
                        "schema_version": SCHEMA_VERSION,
                    },
                })
            overlap = temiz_metin(body)[-CHUNK_OVERLAP:]
            buffer = [overlap] if overlap else []
            size = len(overlap)
        for paragraph in paragraflar(str(page.get("text", ""))):
            possible_heading = heading_kind(paragraph)
            if possible_heading:
                if buffer:
                    flush()
                section = possible_heading
                buffer_section = possible_heading
                buffer = ["# " + section]
                size = len(section) + 2
                continue
            for part in uzun_parcayi_bol(paragraph):
                if buffer and (buffer_section != section or size + len(part) > CHUNK_SIZE) and not formullu_mu(part):
                    flush()
                buffer_section = section
                buffer.append(part)
                size += len(part)
        if buffer:
            flush()
    return chunks

MATH_BLOCK = re.compile(r"(?s)(" r"\$\$.*?\$\$" r"|\\\[.*?\\\]" r"|\\begin\{(?:equation\\*?|align\\*?|gather\\*?)\}.*?\\end\{(?:equation\\*?|align\\*?|gather\\*?)\}" r")")

def formulleri_cikar(pages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output = []
    seen = set()
    for page in pages:
        text = str(page.get("text", ""))
        lines = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
        candidates = [(match.group(0), text[:match.start()].count("\n")) for match in MATH_BLOCK.finditer(text)]
        candidates.extend((line, index) for index, line in enumerate(lines) if formullu_mu(line))
        for formula, index in candidates:
            formula = re.sub(r"\s+", " ", re.sub(r"^[-*]\s*", "", formula)).strip()
            key = (int(page["page"]), normalize(formula))
            if key in seen or not 3 <= len(formula) <= 5000:
                continue
            seen.add(key)
            match = re.search(r"(?:\(|\[)?\s*(\d{1,4})\s*(?:\)|\])?\s*$", formula)
            label = f"({match.group(1)})" if match else None
            context = " ".join(line for line in lines[max(0, index-2):min(len(lines), index+3)] if normalize(line) != normalize(formula))[:1800]
            output.append({"id": f"f{len(output)+1}", "label": label, "page": int(page["page"]), "formula": formula, "context": context})
    return output

def section_chunks(chunks: Sequence[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    aliases = SECTION_ALIASES[kind]
    return [chunk for chunk in chunks if any(alias in normalize_heading(str(chunk["metadata"].get("section", ""))) for alias in aliases)]

def section_text(chunks: Sequence[Dict[str, Any]], kind: str, limit: int = 12000) -> Tuple[str, List[int]]:
    selected, pages, size = [], [], 0
    for chunk in section_chunks(chunks, kind):
        body = str(chunk["text"])
        if selected and size + len(body) > limit:
            break
        selected.append(body)
        pages.append(int(chunk["metadata"]["page"]))
        size += len(body)
    return "\n\n".join(selected), sorted(set(pages))

def source_value(value: Any, source: str) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = re.sub(r"\s+", " ", value).strip()
    if not value or normalize(value) in {"unknown", "bilinmiyor", "none", "null", "n/a"}:
        return None
    return value if normalize(value) in normalize(source) else None

def references_fallback(chunks: Sequence[Dict[str, Any]], pages: Sequence[Dict[str, Any]]) -> Tuple[str, List[int]]:
    text, source_pages = section_text(chunks, "references", 22000)
    if text:
        return text, source_pages
    candidates = []
    for page in pages[-5:]:
        raw = str(page.get("text", ""))
        if re.search(r"\breferences\b|\bkaynakça\b|\bkaynaklar\b|\bbibliography\b", raw, flags=re.I):
            candidates.append((int(page["page"]), raw))
    if candidates:
        return "\n\n".join(text for _, text in candidates)[:22000], [page for page, _ in candidates]
    return "", []

def makale_profili(pdf_path: Path, pages: Sequence[Dict[str, Any]], chunks: Sequence[Dict[str, Any]], document_id: str, dosya_adi: str) -> Dict[str, Any]:
    front = "\n\n".join(str(page.get("raw", "")) for page in pages[:2])[:18000]
    candidates = title_candidates(pdf_path)
    prompt = f"""You extract literal bibliographic facts from a research paper.

Return ONLY valid JSON:
{{\"title\": string|null, \"authors\": [string], \"publication_date\": string|null,
\"journal_or_venue\": string|null, \"language\": \"tr\"|\"en\"|\"other\"}}

Use only SOURCE.
Copy title and author names exactly.
Do not translate.
Do not infer.
Do not invent.

TITLE CANDIDATES:
{json.dumps(candidates, ensure_ascii=False)}

SOURCE:
{front}"""
    extracted = ilk_json_nesnesi(llm_metni(prompt))
    title = source_value(extracted.get("title"), front) or (candidates[0] if candidates else None)
    raw_authors = extracted.get("authors") if isinstance(extracted.get("authors"), list) else []
    authors = [item for item in (source_value(author, front) for author in raw_authors) if item]
    abstract, abstract_pages = section_text(chunks, "abstract")
    intro, intro_pages = section_text(chunks, "introduction")
    conclusion, conclusion_pages = section_text(chunks, "conclusion")
    references, references_pages = references_fallback(chunks, pages)
    sections = defaultdict(list)
    for chunk in chunks:
        sections[str(chunk["metadata"].get("section", "Ön Bilgiler"))].append(int(chunk["metadata"]["page"]))
    language = str(extracted.get("language") or "other").lower()
    if language not in {"tr", "en", "other"}:
        language = "other"
    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "dosya_adi": dosya_adi,
        "page_count": len(pages),
        "title": title,
        "authors": authors,
        "publication_date": source_value(extracted.get("publication_date"), front),
        "journal_or_venue": source_value(extracted.get("journal_or_venue"), front),
        "language": language,
        "abstract": abstract,
        "abstract_pages": abstract_pages,
        "introduction_first_sentence": ilk_cumle(intro),
        "introduction_pages": intro_pages,
        "conclusion": conclusion,
        "conclusion_pages": conclusion_pages,
        "references": references,
        "references_pages": references_pages,
        "sections": [{"name": name, "pages": sorted(set(values))} for name, values in sections.items()],
        "formulas": formulleri_cikar(pages),
        "created_at": int(time.time()),
    }

# ============================================================
# YÜKLEME
# ============================================================

async def sse_event(data: Dict[str, Any]):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

@app.post("/documents_stream")
async def belge_yukle_stream(file: UploadFile = File(...)):
    async def ilerleme():
        client = None
        try:
            dosya_adi = dosya_guvenli_adi(file.filename or "makale.pdf")
            if not dosya_adi.lower().endswith(".pdf"):
                yield await sse_event({"error": "Sadece PDF yükleyebilirsiniz."})
                return
            yield await sse_event({"step": 1, "percent": 8, "msg": "PDF kaydediliyor..."})
            content = await file.read()
            if not content:
                yield await sse_event({"error": "Yüklenen PDF boş."})
                return
            pdf_path = UPLOAD_DIR / dosya_adi
            with pdf_path.open("wb") as output:
                output.write(content)
            document_id = hashlib.sha256(content).hexdigest()
            profile_path = profil_yolu(dosya_adi, document_id)
            chunks_path = parca_yolu(dosya_adi, document_id)
            cached_profile = json_oku(profile_path, {})
            cached_chunks = json_oku(chunks_path, [])
            cache_valid = bool(cached_profile and cached_chunks and cached_profile.get("schema_version") == SCHEMA_VERSION and cached_profile.get("document_id") == document_id)
            client = qdrant_client
            await asyncio.get_running_loop().run_in_executor(REQUEST_EXECUTOR, ensure_collection, client)
            if cache_valid and index_ready(client, document_id):
                for payload in (
                    {"step": 2, "percent": 30, "msg": "Bu makale daha önce analiz edildi; kayıtlı metin kullanılıyor..."},
                    {"step": 3, "percent": 55, "msg": "Kayıtlı parçalar kullanılıyor..."},
                    {"step": 4, "percent": 90, "msg": "Mevcut embedding indeksi kullanılıyor..."},
                ):
                    yield await sse_event(payload)
                    await asyncio.sleep(0)
                yield await sse_event({"step": 5, "percent": 100, "done": True, "dosya_adi": dosya_adi, "document_id": document_id, "eklenen_parca_sayisi": len(cached_chunks), "formul_sayisi": len(cached_profile.get("formulas", [])), "cached": True})
                return
            if cache_valid:
                pages = None
                chunks = cached_chunks
                profile = cached_profile
                yield await sse_event({"step": 2, "percent": 35, "msg": "Daha önce çıkarılmış metin kullanılıyor..."})
                yield await sse_event({"step": 3, "percent": 48, "msg": "Kayıtlı bölüm ve formül bilgileri kullanılıyor..."})
            else:
                yield await sse_event({"step": 2, "percent": 20, "msg": "Metin ve sayfa düzeni çıkarılıyor..."})
                pages = await asyncio.get_running_loop().run_in_executor(REQUEST_EXECUTOR, sayfalari_cikar, pdf_path)
                if not any(page["text"].strip() for page in pages):
                    yield await sse_event({"error": "Okunabilir metin bulunamadı. Taranmış PDF için OCR gerekir."})
                    return
                yield await sse_event({"step": 3, "percent": 40, "msg": "Bölümler, profil ve formüller hazırlanıyor..."})
                chunks = await asyncio.get_running_loop().run_in_executor(REQUEST_EXECUTOR, bolum_duyarli_parcalar, pages, document_id, dosya_adi)
                if not chunks:
                    yield await sse_event({"error": "PDF metni anlamlı parçalara ayrılamadı."})
                    return
                profile = await asyncio.get_running_loop().run_in_executor(REQUEST_EXECUTOR, makale_profili, pdf_path, pages, chunks, document_id, dosya_adi)
                await asyncio.get_running_loop().run_in_executor(REQUEST_EXECUTOR, json_yaz, profile_path, profile)
                await asyncio.get_running_loop().run_in_executor(REQUEST_EXECUTOR, json_yaz, chunks_path, chunks)
            if not cache_valid:
                yield await sse_event({"step": 4, "percent": 55, "msg": "İki dilli arama indeksi oluşturuluyor..."})
            else:
                yield await sse_event({"step": 4, "percent": 55, "msg": "Eksik embedding indeksi tamamlanıyor..."})
            if not index_ready(client, document_id):
                await asyncio.get_running_loop().run_in_executor(
                    REQUEST_EXECUTOR,
                    lambda: client.delete(
                        collection_name=COLLECTION_NAME,
                        points_selector=Filter(must=[FieldCondition(key="metadata.document_id", match=MatchValue(value=document_id))]),
                    ),
                )
                store = get_vector_store(client)
                documents = [Document(page_content=chunk["text"], metadata=chunk["metadata"]) for chunk in chunks]
                batch_size = 32
                for start in range(0, len(documents), batch_size):
                    batch = documents[start:start + batch_size]
                    await asyncio.get_running_loop().run_in_executor(REQUEST_EXECUTOR, store.add_documents, batch)
                    percent = 55 + int(min(start + batch_size, len(documents)) / len(documents) * 42)
                    yield await sse_event({"step": 4, "percent": percent, "msg": f"Embedding oluşturuluyor ({min(start + batch_size, len(documents))}/{len(documents)})..."})
                    await asyncio.sleep(0)
            yield await sse_event({"step": 5, "percent": 100, "done": True, "dosya_adi": dosya_adi, "document_id": document_id, "eklenen_parca_sayisi": len(chunks), "formul_sayisi": len(profile.get("formulas", [])), "cached": cache_valid})
        except Exception as exc:
            yield await sse_event({"error": f"{type(exc).__name__}: {exc}"})
        finally:
            pass
    return StreamingResponse(ilerleme(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

@app.get("/health")
async def health():
    return {"status": "ok", "chat_model": CHAT_MODEL, "embedding_model": EMBED_MODEL, "schema_version": SCHEMA_VERSION}
