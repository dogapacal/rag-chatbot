# ⚡ RAG Document Assistant API

A fully local Retrieval-Augmented Generation (RAG) backend API built with FastAPI. It allows users to upload PDF documents and query their content using local vector search (Qdrant) and local LLMs (Ollama).

---

## 🚀 Tech Stack

* **Framework:** FastAPI
* **LLM Engine:** Ollama (qwen3:8b)
* **Vector Database:** Qdrant (Local Storage)
* **Embeddings:** nomic-embed-text
* **Document Processing:** PyPDF & LangChain

---

## 📦 Installation & Setup

### 1. Prerequisites
Ensure you have **Ollama** installed and running on your system:
ollama serve

Pull the required models:
ollama pull qwen3:8b
ollama pull nomic-embed-text

### 2. Install Dependencies
pip install -r requirements.txt

### 3. Run the API Server
uvicorn main:app --reload

Once running, access the interactive API documentation at:
**http://127.0.0.1:8000/docs**
