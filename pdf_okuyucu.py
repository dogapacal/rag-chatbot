from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama

# 1. PDF'yi Yükleme ve Parçalama
yukleyici = PyPDFLoader("basari_chatbot/goruntu_isleme.pdf")
belge = yukleyici.load()

parcalayici = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
parcalar = parcalayici.split_documents(belge)

# 2. Motorların Kurulumu
cevirmen = OllamaEmbeddings(model="nomic-embed-text")
llm = Ollama(model="qwen3:8b") 

# 3. Veritabanının Hazırlanması
veritabani = Chroma.from_documents(documents=parcalar, embedding=cevirmen)

print("\n--- PDF Asistanı Hazır (Çıkmak için 'q' yazın) ---")

while True:
    soru = input("\nSorunuzu yazın: ")
    
    if soru.lower() == 'q':
        print("Çıkış yapılıyor...")
        break
        
    bulunan_sonuc = veritabani.similarity_search(soru, k=4)
    baglam = "\n\n".join([sonuc.page_content for sonuc in bulunan_sonuc])
    
    nihai_prompt = f"""
    Sen profesyonel bir asistansın. 
    Kullanıcının sorusunu SADECE aşağıdaki bağlamda verilen PDF bilgilerini kullanarak yanıtla. Eğer cevap bağlamda yoksa uydurma.

    BAĞLAM:
    {baglam}

    SORU:
    {soru}
    """
    
    cevap = llm.invoke(nihai_prompt)
    print("\nCevap:", cevap)