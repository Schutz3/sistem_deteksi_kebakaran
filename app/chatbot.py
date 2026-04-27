# ==============================================================================
# Tujuan       : Chatbot K3 independen menggunakan SLM lokal (llama-cpp-python)
#                RAG pipeline: ChromaDB search → SLM generate response
#                TIDAK memerlukan gateway LLM (Ollama, dll)
# Caller       : main.py (router include), frontend chat
# Dependensi   : llama_cpp, chromadb, sentence_transformers
# Main Functions: POST /api/chat, load_chatbot()
# Side Effects : Load model GGUF ke RAM (~600MB), query ChromaDB
# ==============================================================================

import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Optional

from app.config import (
    CHATBOT_MODEL_PATH, CHROMA_DB_PATH,
    CHROMA_COLLECTION, EMBEDDING_MODEL_NAME,
)

router = APIRouter()

# --- Global handles ---
_llm = None
_embedding_model = None
_collection = None


def load_chatbot():
    """
    Load semua komponen chatbot saat startup:
    1. SLM (Small Language Model) via llama-cpp-python
    2. Embedding model (sentence-transformers)
    3. ChromaDB collection (knowledge base K3)
    """
    global _llm, _embedding_model, _collection

    # 1. Load SLM
    if os.path.exists(CHATBOT_MODEL_PATH):
        try:
            from llama_cpp import Llama
            _llm = Llama(
                model_path=CHATBOT_MODEL_PATH,
                n_ctx=2048,       # Context window
                n_threads=4,      # CPU threads
                n_gpu_layers=0,   # 0 = CPU only, set > 0 jika ada GPU
                verbose=False,
            )
            print(f"[Chatbot] SLM loaded: {CHATBOT_MODEL_PATH}")
        except ImportError:
            print("[Chatbot] llama-cpp-python belum diinstall. pip install llama-cpp-python")
        except Exception as e:
            print(f"[Chatbot] Error loading SLM: {e}")
    else:
        print(f"[Chatbot] Model GGUF tidak ditemukan: {CHATBOT_MODEL_PATH}")
        print("[Chatbot] Download model: https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF")
        print("[Chatbot] Taruh file .gguf di: chatbot_model/tinyllama-1.1b-chat.Q4_K_M.gguf")

    # 2. Load Embedding Model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print(f"[Chatbot] Embedding model loaded: {EMBEDDING_MODEL_NAME}")
    except Exception as e:
        print(f"[Chatbot] Error loading embedding model: {e}")

    # 3. Load ChromaDB
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _collection = client.get_collection(name=CHROMA_COLLECTION)
        print(f"[Chatbot] ChromaDB loaded: {CHROMA_COLLECTION}")
    except Exception as e:
        print(f"[Chatbot] ChromaDB belum ada atau error: {e}")
        print("[Chatbot] Jalankan: python ingest_pdf.py")


# --- RAG Pipeline ---

def _search_knowledge(query: str, n_results: int = 3) -> str:
    """Cari dokumen relevan di knowledge base K3."""
    if not _collection or not _embedding_model:
        return ""
    try:
        query_emb = _embedding_model.encode([query]).tolist()
        results = _collection.query(
            query_embeddings=query_emb,
            n_results=n_results,
        )
        docs = results["documents"][0] if results["documents"] else []
        return "\n\n".join(docs)
    except Exception as e:
        print(f"[Chatbot] Search error: {e}")
        return ""


def _generate_response(system_prompt: str, user_message: str, history: list) -> str:
    """Generate response menggunakan SLM lokal."""
    if not _llm:
        return "Maaf, model chatbot belum dimuat. Pastikan file GGUF tersedia."

    # Build messages dalam format ChatML
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        # Ambil max 4 pesan terakhir untuk hemat context
        messages.extend(history[-4:])
    messages.append({"role": "user", "content": user_message})

    try:
        response = _llm.create_chat_completion(
            messages=messages,
            max_tokens=512,
            temperature=0.4,
            top_p=0.9,
            stop=["</s>", "<|im_end|>", "\nUser:"],
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Chatbot] Generation error: {e}")
        return "Maaf, terjadi kendala saat memproses jawaban."


# --- API Endpoint ---

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []


@router.post("/api/chat")
async def chat_with_bot(req: ChatRequest):
    """
    Endpoint chatbot RAG:
    1. Cari dokumen relevan di ChromaDB
    2. Susun system prompt dengan context
    3. Generate jawaban menggunakan SLM lokal
    """
    pertanyaan = req.message

    # 1. RAG: Cari konteks dari knowledge base
    konteks_sop = _search_knowledge(pertanyaan)

    # 2. Susun System Prompt
    system_prompt = f"""Anda adalah "Asisten K3 Pintar", seorang profesional K3 (Keselamatan dan Kesehatan Kerja) dan Tanggap Darurat yang ramah dan sigap.
Tugas Anda adalah memberikan jawaban dan panduan yang mudah dipahami, luwes, namun tetap akurat dan tegas.

ATURAN SANGAT PENTING:
1. SUMBER INFORMASI: Anda HANYA diizinkan menjawab berdasarkan teks pada [DOKUMEN REFERENSI] di bawah ini. Jangan mengarang informasi.
2. ANTI-HALUSINASI: Jika pertanyaan pengguna menanyakan sesuatu yang TIDAK TERCANTUM di dalam [DOKUMEN REFERENSI], jawab: "Maaf, informasi terkait hal tersebut tidak ditemukan dalam Pedoman K3 yang terdaftar di sistem kami."
3. FORMAT JAWABAN: Jelaskan poin-poin dengan luwes namun maknanya harus sama persis dengan dokumen. Gunakan poin-poin (bullet points) jika menjelaskan prosedur.
4. FITUR EKSPOR: Jika pengguna meminta "cetak laporan" atau "unduh history", beri tahu mereka bisa mengunduh PDF via [Unduh Laporan PDF](/api/download-history).

[DOKUMEN REFERENSI]
{konteks_sop if konteks_sop else "Tidak ada dokumen referensi yang ditemukan untuk pertanyaan ini."}"""

    # 3. Generate jawaban
    import asyncio
    balasan = await asyncio.to_thread(
        _generate_response, system_prompt, pertanyaan, req.history or []
    )

    return {"reply": balasan, "context_used": konteks_sop}
