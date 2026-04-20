from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import os

print("1. Membaca Buku Panduan K3 dari folder 'docs'...")
loader = PyPDFDirectoryLoader("docs/")
documents = loader.load()

print(f"2. Memotong teks menjadi bagian kecil... (Total Halaman: {len(documents)})")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(documents)

print("3. Mengubah teks menjadi vektor dan menyimpan ke ChromaDB lokal...")
# Kita pakai model embedding gratis dan ringan dari HuggingFace
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Simpan database di folder 'chroma_db'
vectorstore = Chroma.from_documents(documents=chunks, embedding=embeddings, persist_directory="./chroma_db")

print("Selesai! Knowledge Base (SOP K3) sudah siap digunakan oleh Chatbot.")