from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import APIRouter
from pydantic import BaseModel
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
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
TELEGRAM_TOKEN = "8732833109:AAGTRzTrQ8S0HM5ATBf9dT_PFIGpyqn_tkY"
CHAT_ID = "8093955878"
THROTTLE_SECONDS = 50
last_telegram_sent_time = None   # FIX: variabel global yang benar

# ==========================================
# LOAD MODELS (Global)
# ==========================================
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
    global last_telegram_sent_time
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
# WEBSOCKET: REAL AI INTEGRATION (FIXED)
# ==========================================
@app.websocket("/ws/sensor")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Inisialisasi kamera (gunakan 0 untuk webcam lokal, ganti dengan URL ESP32 jika perlu)
    cap = cv2.VideoCapture(0)
    last_yolo_time = 0          # untuk rate limiting YOLO
    last_yolo_prob = 0.0        # simpan hasil YOLO terakhir
    
    try:
        while True:
            loop_start = asyncio.get_event_loop().time()
            
            # 1. SIMULASI SENSOR (ringan)
            suhu = round(np.random.uniform(25.0, 45.0), 1)
            asap = round(np.random.uniform(0.0, 30.0), 1)
            co = round(np.random.uniform(0.0, 50.0), 1)
            lpg = round(np.random.uniform(0.0, 20.0), 1)
            humidity = round(np.random.uniform(30.0, 70.0), 1)

            # 2. RANDOM FOREST PREDICTION (dijalankan di thread)
            prob_rf = 0.0
            if rf_model:
                input_features = np.array([[suhu, asap, co, lpg, humidity]])
                # blocking call -> pindah ke thread
                prob_rf = await asyncio.to_thread(
                    lambda: round(rf_model.predict_proba(input_features)[0][1] * 100, 1)
                )

            # 3. YOLO INFERENCE (hanya setiap 5 detik, di thread)
            current_time = asyncio.get_event_loop().time()
            if current_time - last_yolo_time >= 5.0:
                ret, frame = cap.read()
                if ret and yolo_model:
                    # Jalankan YOLO di thread agar tidak memblokir
                    prob_yolo = await asyncio.to_thread(_run_yolo_inference, frame)
                    last_yolo_prob = prob_yolo
                else:
                    last_yolo_prob = 0.0
                last_yolo_time = current_time
            
            prob_yolo = last_yolo_prob

            # 4. DECISION FUSION
            if prob_yolo > 50:
                prob_akhir = round((prob_yolo * 0.7) + (prob_rf * 0.3), 1)
            else:
                prob_akhir = round((prob_yolo * 0.3) + (prob_rf * 0.7), 1)

            # 5. STATUS
            if prob_akhir < 30: status = "Aman"
            elif prob_akhir < 70: status = "Waspada"
            else: status = "Bahaya"

            log_message = ""
            if status != "Aman":
                log_message = f"Anomali: Suhu {suhu}°C, Asap {asap}%. Prob {prob_akhir}%."
                if status == "Bahaya":
                    asyncio.create_task(asyncio.to_thread(kirim_notifikasi_telegram, status, prob_akhir, suhu, asap))

            # Kirim data ke client
            await websocket.send_text(json.dumps({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "suhu": suhu,
                "asap": asap,
                "prob_yolo": prob_yolo,
                "prob_xgboost": prob_rf,
                "prob_akhir": prob_akhir,
                "status": status,
                "log_message": log_message
            }))

            # Tidur 2 detik, namun sisa waktu dihitung agar drift minimal
            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_time = max(0, 2.0 - elapsed)
            await asyncio.sleep(sleep_time)

    except WebSocketDisconnect:
        cap.release()
    except Exception as e:
        cap.release()
        print(f"Error: {e}")

def _run_yolo_inference(frame):
    """Helper untuk menjalankan YOLO di thread terpisah"""
    try:
        results = yolo_model.predict(frame, verbose=False)
        max_conf = 0.0
        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    if int(box.cls[0]) == 0:   # kelas api
                        conf = float(box.conf[0]) * 100
                        if conf > max_conf:
                            max_conf = conf
        return round(max_conf, 1)
    except Exception as e:
        print(f"YOLO error: {e}")
        return 0.0

# ==========================================
# SETUP KNOWLEDGE BASE & LLM (sekali saja)
# ==========================================
load_dotenv(override=True)
raw_groq_key = os.getenv("GROQ_API_KEY")
groq_api_key = raw_groq_key.strip() if raw_groq_key else None

print("\n" + "="*40)
print(f"Kunci Groq bersih: '{groq_api_key}'")
print("="*40 + "\n")

llm = ChatGroq(
    model_name="llama-3.1-8b-instant",
    temperature=0.3,
    api_key=groq_api_key 
)

# Load Vector Database (Knowledge Base SOP K3)
try:
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    print("Knowledge Base K3 & Groq LLM berhasil dimuat!")
except Exception as e:
    print(f"Peringatan: ChromaDB belum dibuat atau error. {e}")
    retriever = None

# ==========================================
# ENDPOINT CHATBOT RAG (hanya satu)
# ==========================================
class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat_with_bot(req: ChatRequest):
    pertanyaan = req.message
    
    if not retriever:
        return {"reply": "Maaf, sistem Knowledge Base K3 belum siap.", "context_used": ""}
        
    dokumen_relevan = retriever.invoke(pertanyaan)
    konteks_sop = "\n\n".join([doc.page_content for doc in dokumen_relevan])
    
    system_prompt = f"""Anda adalah Asisten Ahli K3 (Keselamatan dan Kesehatan Kerja), Tanggap Darurat, dan Penanggulangan Kebakaran.
    Tugas Anda adalah memberikan petunjuk yang AKURAT, CEPAT, dan TERSTRUKTUR berdasarkan dokumen pedoman resmi yang diberikan.
    
    ATURAN SANGAT PENTING:
    1. SUMBER INFORMASI: Anda HANYA diizinkan menjawab berdasarkan teks pada [DOKUMEN REFERENSI] di bawah ini.
    2. ANTI-HALUSINASI: Jika pertanyaan pengguna menanyakan sesuatu yang TIDAK TERCANTUM di dalam [DOKUMEN REFERENSI], Anda WAJIB menjawab persis seperti ini: "Maaf, informasi atau prosedur terkait hal tersebut tidak ditemukan dalam Pedoman K3, Tanggap Darurat, maupun Pedoman Kebakaran yang terdaftar di sistem kami."
    3. FORMAT JAWABAN: Gunakan poin-poin (bullet points) atau urutan angka untuk menjelaskan prosedur.
    
    [DOKUMEN REFERENSI]
    {konteks_sop}
    
    Pertanyaan Pengguna: {pertanyaan}
    Jawaban:"""
    
    try:
        response = llm.invoke(system_prompt)
        balasan_bot = response.content
    except Exception as e:
        balasan_bot = f"Terjadi kesalahan saat menghubungi AI: {e}"
    
    return {"reply": balasan_bot, "context_used": konteks_sop}