# 🤖 Local RAG Document Assistant

A fully local Retrieval-Augmented Generation (RAG) system that allows users to upload PDF documents and ask questions directly from their content. The system processes the document, stores vector embeddings in a local vector database, and generates context-aware answers using a local Large Language Model (LLM).

---

## 🚀 Key Features

* **100% Local Execution:** Runs entirely on your local machine with zero external API dependencies or data leakage.
* **Vector Search:** Fast and semantic similarity retrieval powered by **Qdrant**.
* **Local LLM Integration:** Powered by **Ollama** for embeddings and text generation.
* **Interactive UI:** Clean and intuitive web interface built with **Streamlit**.

---

## 🛠️ Architecture & Tech Stack

* **Frontend:** Streamlit
* **LLM Engine:** Ollama
* **Vector Database:** Qdrant (Local Storage)
* **Document Processing:** PyPDF
* **Language:** Python 3.10+

---

## 📦 Installation & Setup

### 1. Prerequisites
Ensure you have **Ollama** installed and running on your system:
```bash
ollama serve