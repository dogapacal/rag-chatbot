# ⚡ Local RAG Document Assistant API

A robust, fully local Retrieval-Augmented Generation (RAG) backend API built with FastAPI. This system allows users to upload PDF documents, process them into vector embeddings, and query their content using local Large Language Models (LLMs) without relying on external APIs or risking data privacy.

---

## 🚀 Key Features

* **100% Local Execution:** Processes documents and generates answers entirely on your local machine.
* **RESTful API Architecture:** Clean and well-documented endpoints powered by FastAPI.
* **Advanced Vector Search:** Utilizes Qdrant for fast, semantic similarity retrieval.
* **Local LLM Integration:** Employs Ollama for generating context-aware, accurate responses.
* **Automated Chunking:** Uses LangChain and PyPDF to efficiently split and embed large documents.

---

## 🛠️ Architecture & Tech Stack

* **Framework:** FastAPI (Python 3.10+)
* **LLM Engine:** Ollama (Model: qwen3:8b)
* **Vector Database:** Qdrant (Local Storage)
* **Embeddings:** nomic-embed-text
* **Document Processing:** LangChain & PyPDFLoader

---

## 📡 API Endpoints

Once the server is running, you can access the interactive Swagger UI documentation at `/docs` to test the capabilities:

* `POST /upload`: Upload a PDF document for processing and vectorization.
* `POST /query`: Send a question to the LLM and retrieve a context-aware answer based on the uploaded document.
* `GET /health`: Check the status of the API and vector database connection.

---

## 📦 Installation & Setup

### 1. Prerequisites
Ensure you have **Ollama** installed and running in the background:

    ollama serve

Pull the required models for generation and embeddings:

    ollama pull qwen3:8b
    ollama pull nomic-embed-text

### 2. Clone and Install
Clone the repository and install the required dependencies:

    git clone [https://github.com/dogapacal/rag-chatbot.git](https://github.com/dogapacal/rag-chatbot.git)
    cd rag-chatbot
    pip install -r requirements.txt

### 3. Run the API Server
Start the FastAPI application using Uvicorn:

    uvicorn main:app --reload

* **Base URL:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
* **API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 📄 License
This project is open-source and available under the MIT License.