from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama

# 1. Motorların Kurulumu
cevirmen = OllamaEmbeddings(model="nomic-embed-text")
llm = Ollama(model="qwen3:8b") 

# 2. Veritabanının Hazırlanması (Kiler)
bilgiler = [
    "Sistem testleri bu hafta yapılamayacaktır çünkü panonun sigortaları henüz teslim edilmemiştir.",
    "Kablo pabuçlama ve PLC ağı yapılandırma işlemleri standartlara uygun tamamlanmıştır."
]
veritabani = Chroma.from_texts(texts=bilgiler, embedding=cevirmen)

# 3. Anlamsal Arama (Komi malzemeyi buluyor)
soru = "Sistem testlerine neden başlayamadık?"
bulunan_sonuc = veritabani.similarity_search(soru, k=1)
baglam = bulunan_sonuc[0].page_content

# 4. Prompt Mühendisliği (Tarifin ve malzemenin aşçıya verilmesi)
nihai_prompt = f"""
Sen profesyonel bir mühendislik asistanısın. 
Kullanıcının sorusunu SADECE aşağıdaki bağlamda verilen bilgileri kullanarak yanıtla. Yorum katma.

BAĞLAM:
{baglam}

SORU:
{soru}
"""

print("Sistem Düşünüyor...\n")

# 5. Üretim (Aşçı yemeği yapıyor)
cevap = llm.invoke(nihai_prompt)
print("Yapay Zeka Yanıtı:\n", cevap)