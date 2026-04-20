from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import APIRouter
from pydantic import BaseModel
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import asyncio
import json
import jwt
import joblib
import numpy as np
import cv2
from ultralytics import YOLO
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
from contextlib import asynccontextmanager
import os

# --- KONFIGURASI KEAMANAN & JWT ---
SECRET_KEY = "pbl-sem-6-rahasia-banget"
ALGORITHM = "HS256"

# --- KONFIGURASI TELEGRAM ---
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
CHAT_ID = "YOUR_CHAT_ID_HERE"
THROTTLE_SECONDS = 30
last_telegram_sent_time = None

# ==========================================
# LOAD MODELS (Global)
# ==========================================
# Memuat model sekali saat startup agar efisien
try:
    rf_model = joblib.load("models/fire_detection_rf.pkl")
    yolo_model = YOLO("models/best.pt")
    print("AI Models loaded successfully.")
except Exception as e:
    print(f"Error loading models: {e}")
    rf_model = None
    yolo_model = None

app = FastAPI(title="PBL Sem 6 - Sistem Risiko Kebakaran")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# FUNGSI BACKEND: NOTIFIKASI TELEGRAM
# ==========================================
def kirim_notifikasi_telegram(status_alert: str, prob: float, suhu: float, asap: float):
    global last_telegram_sent_times
    now = datetime.now()
    
    if last_telegram_sent_time is not None:
        if (now - last_telegram_sent_time).total_seconds() < THROTTLE_SECONDS:
            return

    pesan = (
        f"🚨 PERINGATAN {status_alert.upper()}! 🚨\n\n"
        f"Sensor mendeteksi anomali tinggi di ruangan.\n"
        f"Probabilitas Akhir : {prob}%\n"
        f"Suhu Lingkungan    : {suhu}°C\n"
        f"Kepadatan Asap     : {asap}%\n"
        f"Waktu Kejadian     : {now.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    if TELEGRAM_TOKEN != "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": pesan}).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req) as response:
                last_telegram_sent_time = now
        except Exception as e:
            print(f"Gagal mengirim ke Telegram: {e}")

# ==========================================
# LOGIN & AUTH LOGIC
# ==========================================
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=2)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token: return None
    try:
        if token.startswith("Bearer "): token = token[7:]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except: return None

@app.get("/")
async def get_dashboard(request: Request):
    user = await get_current_user_from_cookie(request)
    if not user: return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request, "username": user})

@app.get("/login")
async def get_login_page(request: Request):
    user = await get_current_user_from_cookie(request)
    if user: return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})

@app.post("/login")
async def login_process(request: Request):
    form = await request.form()
    if form.get("username") == "admin" and form.get("password") == "admin":
        access_token = create_access_token(data={"sub": "admin"})
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
        return response
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": "Invalid credentials."})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response

# ==========================================
# WEBSOCKET: REAL AI INTEGRATION
# ==========================================
@app.websocket("/ws/sensor")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Inisialisasi kamera (Ganti URL untuk ESP32-CAM)
    cap = cv2.VideoCapture(0) 
    
    try:
        while True:
            # 1. BACA SENSOR (Simulasi data dari ESP32)
            suhu = round(np.random.uniform(25.0, 45.0), 1)
            asap = round(np.random.uniform(0.0, 30.0), 1)
            co = round(np.random.uniform(0.0, 50.0), 1)      # Contoh: Gas CO
            lpg = round(np.random.uniform(0.0, 20.0), 1)     # Contoh: Gas LPG
            humidity = round(np.random.uniform(30.0, 70.0), 1) # Contoh: Kelembapan (Suhu DHT22)

            # 2. RANDOM FOREST PREDICTION (Sensor)
            prob_rf = 0.0
            if rf_model:
                # Menggunakan urutan fitur: [suhu, asap]
                input_features = np.array([[suhu, asap, co, lpg, humidity]])
                pred = rf_model.predict_proba(input_features)
                prob_rf = round(pred[0][1] * 100, 1)

            # 3. YOLOv8 PREDICTION (Visual)
            prob_yolo = 0.0
            ret, frame = cap.read()
            if ret and yolo_model:
                results = yolo_model.predict(frame, verbose=False)
                for r in results:
                    for box in r.boxes:
                        if int(box.cls[0]) == 0: # ID Kelas Api
                            conf = float(box.conf[0]) * 100
                            if conf > prob_yolo: prob_yolo = round(conf, 1)

            # 4. DECISION FUSION (Weighted Voting)
            # Implementasi logika Bobot Dinamis
            if prob_yolo > 50:
                # Visi dominan saat api terlihat
                prob_akhir = round((prob_yolo * 0.7) + (prob_rf * 0.3), 1)
            else:
                # Sensor lebih dipercaya pada fase awal
                prob_akhir = round((prob_yolo * 0.3) + (prob_rf * 0.7), 1)

            # 5. PENENTUAN STATUS (3 Kelas)
            if prob_akhir < 30: status = "Aman"
            elif prob_akhir < 70: status = "Waspada"
            else: status = "Bahaya"

            log_message = ""
            if status != "Aman":
                log_message = f"Anomali: Suhu {suhu}°C, Asap {asap}%. Prob {prob_akhir}%."
                if status == "Bahaya":
                    asyncio.create_task(asyncio.to_thread(kirim_notifikasi_telegram, status, prob_akhir, suhu, asap))

            await websocket.send_text(json.dumps({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "suhu": suhu,
                "asap": asap,
                "prob_yolo": prob_yolo,
                "prob_xgboost": prob_rf, # Tetap gunakan key ini agar dashboard tidak error
                "prob_akhir": prob_akhir,
                "status": status,
                "log_message": log_message
            }))
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        cap.release()
    except Exception as e:
        cap.release()
        print(f"Error: {e}")
        
# Load Database Vektor yang tadi dibuat
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3}) # Ambil 3 paragraf paling relevan

# Skema data untuk menerima pesan dari frontend
class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat_with_bot(req: ChatRequest):
    pertanyaan = req.message
    
    # 1. Cari paragraf SOP/K3 yang relevan dari pertanyaan user
    dokumen_relevan = retriever.invoke(pertanyaan)
    konteks_sop = "\n\n".join([doc.page_content for doc in dokumen_relevan])
    
    # 2. Susun Prompt (Prompt Engineering)
    # Ini yang akan dikirim ke LLM (seperti GPT/Gemini)
    system_prompt = f"""Anda adalah Asisten Tanggap Darurat Cerdas.
    Jawab pertanyaan pengguna secara profesional HANYA berdasarkan panduan SOP K3 berikut:
    
    [DOKUMEN SOP K3]
    {konteks_sop}
    
    Pertanyaan: {pertanyaan}
    Jawaban:"""
    
    # 3. Panggil LLM di sini (misal OpenAI API, Gemini API, atau Groq API)
    # response_llm = panggil_llm(system_prompt) 
    
    # Mockup balasan sementara sebelum LLM disambungkan:
    balasan = f"Berdasarkan SOP K3 kami menemukan info ini:\n{konteks_sop[:200]}..."
    
    return {"reply": balasan, "context_used": konteks_sop}

# ==========================================
# SETUP KNOWLEDGE BASE & GEMINI LLM
# ==========================================

# 1. Load semua variabel rahasia dari file .env
load_dotenv() 
# (Sekarang kamu tidak perlu menulis os.environ["GOOGLE_API_KEY"] = "AIza..." lagi!)

# 2. Inisialisasi Model Gemini
# Library ChatGoogleGenerativeAI akan otomatis mencari GOOGLE_API_KEY dari .env
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.3)

# 3. Load Vector Database (Knowledge Base SOP K3)
try:
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    print("Knowledge Base K3 & Gemini LLM berhasil dimuat!")
except Exception as e:
    print(f"Peringatan: ChromaDB belum dibuat atau error. {e}")
    retriever = None

# ==========================================
# ENDPOINT CHATBOT RAG
# ==========================================
class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat_with_bot(req: ChatRequest):
    pertanyaan = req.message
    
    if not retriever:
        return {"reply": "Maaf, sistem Knowledge Base K3 belum siap.", "context_used": ""}
        
    # 1. Cari paragraf SOP/K3 yang paling relevan dengan pertanyaan
    dokumen_relevan = retriever.invoke(pertanyaan)
    konteks_sop = "\n\n".join([doc.page_content for doc in dokumen_relevan])
    
    # 2. Prompt Engineering (Menyuruh Gemini membaca SOP sebelum menjawab)
    system_prompt = f"""Anda adalah Asisten Tanggap Darurat Keselamatan & Kebakaran (K3) yang profesional.
    Tugas Anda adalah menjawab pertanyaan pengguna secara DETAIL, KOMPREHENSIF, dan TERSTRUKTUR.
    
    ATURAN SANGAT PENTING:
    1. Anda HANYA boleh menjawab berdasarkan [DOKUMEN SOP K3] di bawah ini.
    2. Jika jawaban tidak ada di dalam dokumen, katakan: "Maaf, panduan untuk hal tersebut tidak ditemukan dalam SOP K3 saat ini." Jangan pernah mengarang jawaban sendiri.
    3. Jabarkan jawaban Anda selengkap mungkin. Gunakan poin-poin (bullet points) jika terdapat langkah-langkah atau prosedur agar mudah dibaca.
    
    [DOKUMEN SOP K3]
    {konteks_sop}
    
    Pertanyaan Pengguna: {pertanyaan}
    Jawaban:"""
    
    try:
        # 3. Panggil Gemini API untuk men-generate jawaban (MENGGANTIKAN KODE MOCKUP)
        response = llm.invoke(system_prompt)
        balasan_bot = response.content
    except Exception as e:
        # Jika API Key salah atau kuota habis, pesan error ini yang akan muncul
        balasan_bot = f"Terjadi kesalahan saat menghubungi AI Gemini: {e}"
    
    return {"reply": balasan_bot, "context_used": konteks_sop}