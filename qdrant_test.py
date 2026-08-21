from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
import msvcrt

# 1. PDF Yükleme ve Parçalama
yukleyici = PyMuPDFLoader("goruntu_isleme.pdf")
belge = yukleyici.load()

parcalayici = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
parcalar = parcalayici.split_documents(belge)

# 2. Embedding ve LLM Motorları
cevirmen = OllamaEmbeddings(model="nomic-embed-text")
llm = Ollama(model="qwen3:8b")

# 3. Qdrant Yerel Veritabanını Başlatma (Klasöre Kaydeder)
client = QdrantClient(path="./qdrant_db")
koleksiyon_adi = "dokumanlar"

# Koleksiyon yoksa oluştur (nomic-embed-text vektör boyutu: 768)
if not client.collection_exists(collection_name=koleksiyon_adi):
    client.create_collection(
        collection_name=koleksiyon_adi,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )

# 4. Belgeleri Qdrant'a Kaydetme
veritabani = QdrantVectorStore(
    client=client,
    collection_name=koleksiyon_adi,
    embedding=cevirmen,
)
veritabani.add_documents(documents=parcalar)

# 5. Arama ve Yanıt Üretimi
soru = "Sualtı görüntü restorasyonu için hangi yöntemler kullanılıyor?"
bulunan_sonuc = veritabani.similarity_search(soru, k=4)
baglam = "\n\n".join([sonuc.page_content for sonuc in bulunan_sonuc])

nihai_prompt = f"""
Sen profesyonel bir asistansın. 
Kullanıcının sorusunu SADECE aşağıdaki bağlamda verilen PDF bilgilerini kullanarak yanıtla. 
Cevap bağlamda yoksa uydurma, "Bu bilgi dokümanda bulunamadı." de.

BAĞLAM:
{baglam}

SORU:
{soru}
"""

print("Qdrant taranıyor ve model çalıştırılıyor...\n")
cevap = llm.invoke(nihai_prompt)
print("Cevap:\n", cevap)
client.close()