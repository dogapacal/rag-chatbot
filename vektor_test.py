from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings

# 1. Metinleri sayılara çevirecek olan çevirmen modelimizi seçiyoruz
cevirmen = OllamaEmbeddings(model="nomic-embed-text")

# 2. Veritabanına kaydedeceğimiz örnek metin
bilgiler = [
    "Dün yaşanan sorun sözcüksel eşleşme yanılgısıdır.",
    "Staj defterine yazılacak not: Vektör veritabanları metinlerin anlamlarını koordinatlara dönüştürür."
]

print("Metinler vektöre çevriliyor ve Chroma DB'ye kaydediliyor...")
# Chroma DB'yi kurup metinleri içine atıyoruz
veritabani = Chroma.from_texts(texts=bilgiler, embedding=cevirmen)
print("Kayıt başarılı!\n")

# 3. Veritabanında birebir kelime eşleşmesi OLMADAN anlamsal arama yapıyoruz
soru = "Staj dosyasına ne yazmalıyım?"
print(f"Sorulan Soru: {soru}")

# Soruyu veritabanına sorup en yakın 1 cevabı getir diyoruz
bulunan_sonuc = veritabani.similarity_search(soru, k=1)

print("\nVeritabanından Bulunan En Yakın Sonuç:")
print(bulunan_sonuc[0].page_content)