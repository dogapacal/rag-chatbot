from langchain_community.llms import Ollama

llm = Ollama(model="tarih-asistani")
print("Soru gönderiliyor...")
cevap = llm.invoke("Fatih Sultan Mehmet İstanbul'u ne zaman fethetti?")
print("Cevap:", cevap)