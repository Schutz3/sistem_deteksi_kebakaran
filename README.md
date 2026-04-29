# 🔥 Sistem Deteksi Kebakaran Modular

Sistem deteksi kebakaran berbasis IoT (ESP32 + 6 Sensor Gas MQ), Computer Vision (YOLOv11), Machine Learning (XGBoost Decision Fusion), dan Chatbot K3 lokal (Qwen 2.5 1.5B GGUF + RAG).

**Dikembangkan oleh:** Ervin, Akmal, Jascon, Farhan — PBL Semester 6

## Fitur Utama
- **Multi-Camera RTSP/ONVIF** — Streaming dan analisis per-kamera secara paralel.
- **ESP32 + 6x Sensor Gas MQ** — MQ-2 (Gas), MQ-4 (CH4), MQ-5 (LPG), MQ-7 (CO), MQ-135 (Air Quality), MQ-3 (Alkohol).
- **AI Decision Fusion** — YOLOv11 (visual api/asap) + XGBoost (data sensor RAW→PPM) digabungkan.
- **Chatbot K3 Offline** — Qwen 2.5 1.5B / Gemma 3 / Llama 3.2 GGUF + RAG ChromaDB, GPU auto-detect (CUDA/Vulkan/CPU).
- **Dashboard Web Dinamis** — Konfigurasi kamera, threshold, dan monitoring real-time.
- **Notifikasi Telegram** — Kirim alert otomatis saat terdeteksi bahaya.
- **ESP32 Captive Portal** — Konfigurasi WiFi, URL server, dan Camera ID via portal web, tersimpan di NVS.

---

## 📂 Struktur Proyek

```
.
├── main.py                  # Entry point FastAPI
├── app/
│   ├── config.py            # Konfigurasi global & state dinamis
│   ├── auth.py              # Login / JWT authentication
│   ├── camera.py            # Manager multi-kamera RTSP
│   ├── sensor.py            # Endpoint data sensor ESP32
│   ├── ai_engine.py         # YOLO + XGBoost + Decision Fusion + RAW→PPM
│   ├── chatbot.py           # RAG chatbot (llama-cpp-python, GPU auto-detect)
│   ├── websocket_handler.py # WebSocket monitoring real-time
│   ├── notification.py      # Telegram notification
│   └── pdf_export.py        # Export laporan PDF
├── esp32/fire_sensor/
│   └── fire_sensor.ino      # Firmware ESP32 (Captive Portal + NVS)
├── models/
│   ├── best.pt              # Model YOLOv11
│   ├── fire_detection_rf.pkl # Model XGBoost sensor
│   ├── scaler.pkl           # StandardScaler untuk fitur XGBoost
│   ├── qwen2.5-1.5b-k3.gguf        # Model chatbot Qwen 2.5 GGUF
│   ├── train_chatbot/       # Notebook fine-tuning chatbot
│   │   ├── Finetune_K3_Qwen_1.5B_Kaggle.ipynb  # Qwen (utama)
│   │   └── Finetune_K3_Gemma.ipynb              # Gemma (legacy)
│   ├── train_sensor/        # Notebook Colab training sensor
│   │   └── model_performance_training.ipynb
│   └── train_yolo/          # Training YOLOv11
├── docs/                    # PDF panduan K3 untuk RAG
├── ingest_pdf.py            # Script ingest PDF ke ChromaDB
├── templates/index.html     # Dashboard UI
├── static/js/dashboard.js   # Frontend logic
├── requirements.txt
└── .env.example
```

---

## ⚠️ Model AI (Git-Ignored)

File model berukuran besar **tidak** disertakan di repository.

### Download Model Chatbot

| Model | URL | Ukuran | Keterangan |
|-------|-----|--------|------------|
| Qwen 2.5 1.5B **Clean** (tanpa fine-tune) | [Download](http://data.scz.my.id/qwen2.5-1.5b-instruct-q4_k_m.gguf) | ~950MB | Langsung pakai, bahasa Indonesia OK |
| Qwen 2.5 1.5B **Fine-Tuned K3** | [Download](http://data.scz.my.id/qwen2.5-1.5b-k3.gguf) | ~950MB | Sudah dilatih domain K3, **rekomendasi** |

> Taruh file `.gguf` di folder `models/` lalu rename sesuai `.env` (`qwen2.5-1.5b-k3.gguf`).
> **Penting:** Nama file harus mengandung `qwen`, `gemma`, atau `llama` agar chatbot otomatis memilih format prompt yang benar.

### Download Dataset Training

| File | URL |
|------|-----|
| `dataset_100k.jsonl` (100K Q&A K3) | [Download](http://data.scz.my.id/dataset_100k.jsonl) |

### Model AI Lainnya

| File | Taruh di | Keterangan |
|------|----------|------------|
| `best.pt` | `models/` | YOLOv11 deteksi api & asap |
| `fire_detection_rf.pkl` | `models/` | XGBoost sensor prediction |
| `scaler.pkl` | `models/` | StandardScaler fitur sensor |

---

## 🚀 Cara Menjalankan

### 1. Setup Environment
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. Install Dependencies Utama
```bash
pip install -r requirements.txt
```

### 3. Install llama-cpp-python (Chatbot)

> **PENTING:** `llama-cpp-python` perlu di-install **terpisah** karena memerlukan compile flag sesuai GPU.

#### Opsi A: NVIDIA GPU (CUDA) — Performa Terbaik
```bash
# Windows (butuh Visual Studio Build Tools)
set CMAKE_ARGS=-DGGML_CUDA=ON
pip install llama-cpp-python --no-cache-dir

# Linux
CMAKE_ARGS="-DGGML_CUDA=ON" pip install llama-cpp-python --no-cache-dir
```

#### Opsi B: AMD/Intel GPU (Vulkan) — Rekomendasi untuk AMD
```bash
# Windows (butuh Visual Studio Build Tools + Vulkan SDK)
set CMAKE_ARGS=-DGGML_VULKAN=ON
pip install llama-cpp-python --no-cache-dir

# Linux
CMAKE_ARGS="-DGGML_VULKAN=ON" pip install llama-cpp-python --no-cache-dir
```

#### Opsi C: CPU Only — Tanpa GPU
```bash
pip install llama-cpp-python --no-cache-dir
```

> **Windows:** Jika gagal compile, install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) terlebih dahulu (pilih "Desktop development with C++").

### 4. Download Embedding Model (Satu Kali)
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); print('OK')"
```

### 5. Konfigurasi Environment
```bash
cp .env.example .env
```
Edit file `.env`:
- `TELEGRAM_TOKEN` dan `CHAT_ID` — untuk notifikasi
- `CHATBOT_MODEL_PATH` — path ke file GGUF chatbot

### 6. Ingest Dokumen K3 (RAG Knowledge Base)
Letakkan file PDF panduan K3 ke folder `docs/`, lalu:
```bash
python ingest_pdf.py
```

### 7. Jalankan Server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8500
```
Buka **http://localhost:8500** di browser.

Chatbot otomatis mendeteksi GPU:
```
[Chatbot] SLM loaded: models/qwen2.5-1.5b-k3.gguf (CUDA (GeForce RTX 3060))
# atau
[Chatbot] SLM loaded: models/qwen2.5-1.5b-k3.gguf (Vulkan/GPU)
# atau
[Chatbot] SLM loaded: models/qwen2.5-1.5b-k3.gguf (CPU fallback)
```

---

## 🔌 Firmware ESP32

ESP32 menggunakan **Captive Portal** untuk konfigurasi WiFi dan server URL.

### Pertama Kali (Setup)
1. Buka `esp32/fire_sensor/fire_sensor.ino` di **Arduino IDE**.
2. Install board **ESP32 Dev Module** dan library **ArduinoJson**, **Preferences**.
3. Upload firmware.
4. ESP32 akan membuat WiFi AP: **FireSensor_XXXX** (tanpa password).
5. Hubungkan ke AP tersebut → browser otomatis buka halaman konfigurasi.
6. Isi **WiFi SSID**, **Password**, **Server URL**, dan **Camera ID**.
7. Klik Save → ESP32 restart dan mulai kirim data.

### Reset Konfigurasi
Tahan tombol **BOOT** selama **5 detik** saat ESP32 menyala → konfigurasi akan di-reset dan portal muncul kembali.

### Kalibrasi Sensor (Nilai Normal di Udara Bersih)
| Sensor | Pin GPIO | Normal RAW ADC |
|--------|----------|----------------|
| MQ-4 (CH4) | GPIO32 | ~1357 |
| MQ-5 (LPG) | GPIO33 | ~2966 |
| MQ-135 (Air Quality) | GPIO34 | ~758 |
| MQ-2 (Gas) | GPIO35 | ~230 |
| MQ-7 (CO) | GPIO36 | ~280 |
| MQ-3 (Alkohol) | GPIO39 | ~721 |

> Sensor di-supply 5V, ESP32 ADC membaca 3.3V. **Tidak perlu resistor eksternal** — modul breakout MQ sudah punya RL bawaan, dan RL cancel out secara matematis dalam rasio Rs/Ro. Backend otomatis mengkonversi RAW ADC → PPM.

---

## 🤖 Fine-Tuning Chatbot

### Opsi A: Qwen 2.5 1.5B (Rekomendasi — Kaggle)
Model terbaik di kelasnya, fasih bahasa Indonesia. Kaggle gratis 2x T4 GPU.

1. Upload `Finetune_K3_Qwen_1.5B_Kaggle.ipynb` ke **Kaggle Notebooks**.
2. Setting: **Accelerator** = GPU T4 x2, **Internet** = On.
3. Tambahkan **Kaggle Secret**: `HF_TOKEN` = token Hugging Face Anda.
4. Dataset otomatis di-download dari `data.scz.my.id` di Cell 3.
5. Jalankan Cell 1 → **Restart Session** → Lanjut Cell 2 sampai selesai.
6. Download `qwen2.5-1.5b-k3.gguf` dari tab Output → taruh di `models/`.

> **Estimasi:** Training ~5 jam, Convert ~10 menit. Total ~5.5 jam.

### Opsi B: Gemma 3 270M (Ringan — Colab/Kaggle)
Model kecil, cocok untuk hardware terbatas.

1. Upload `Finetune_K3_Gemma.ipynb` ke **Google Colab** atau Kaggle.
2. Atur runtime ke **GPU (T4)**.
3. Jalankan Cell 1 → **Restart Session** → Lanjutkan dari Cell 2.
4. Download file `.gguf` → taruh di `models/`.

---

## 📊 Training Model Sensor (XGBoost)

1. Buka `models/train_sensor/model_performance_training.ipynb` di **Google Colab**.
2. Upload file `Sensor Gas.xlsx` (dataset dari Kaggle, unit PPM).
3. Notebook akan:
   - Load dan merge 5 jenis gas (CNG, CO, Flame, LPG, Smoke)
   - Training XGBoost dengan StandardScaler
   - Evaluasi dengan cross-validation dan SMOTE
4. Download `fire_detection_rf.pkl` + `scaler.pkl` → taruh di `models/`.

### Mapping Sensor

| Gas Type (Dataset PPM) | Sensor MQ (ESP32 RAW) | Keterangan |
|-------------------------|-----------------------|------------|
| CNG (Metana) | MQ-4 | Gas alam |
| LPG | MQ-5 | Gas LPG |
| Smoke | MQ-135 | Kualitas udara |
| Flame (proxy) | MQ-2 | Gas mudah terbakar |
| CO | MQ-7 | Karbon monoksida |

### Konversi RAW ADC → PPM (Backend)
Backend `ai_engine.py` melakukan konversi otomatis:
```
RAW ADC (12-bit) → Voltage → Rs/Ro → PPM (kurva log-log sensor MQ) → PPM - Baseline
```
Memperhitungkan: VCC Sensor = 5V, VCC ADC ESP32 = 3.3V.
Baseline clean-air PPM otomatis dikurangi agar udara bersih = 0 PPM (mencegah false positive).
