# Sistem Deteksi Kebakaran Modular (Multi-Kamera & Edge AI)

Sistem pendeteksi kebakaran komprehensif berbasis Internet of Things (ESP32), Computer Vision (YOLOv11), dan Decision Fusion berbasis Machine Learning (XGBoost), yang diperlengkapi tambahan asisten cerdas K3 (TinyLlama RAG Chatbot Lokal) berkecepatan tinggi.

## Fitur Utama
1. **Multi-Camera RTSP/ONVIF Flow** – Sinkronisasi dan threading per-kamera.
2. **ESP32 + 6x Sensor Gas MQ** – Membaca Polusi (MQ135), Asap (MQ2), Etanol(MQ3), Metana(MQ4), LPG(MQ5), dan Karbon Monoksida(MQ7).
3. **AI Decision Fusion** – Penggabungan analisis YOLOv11 secara Visual dan Probabilitas XGBoost berbasis Rasio Udara.
4. **Chatbot SLM Offline** – Local TinyLlama-1.1B GGUF dengan dokumen RAG untuk modul Kesehatan dan Keselamatan Kerja tanpa API luar.
5. **Konfigurasi Web Dinamis** – Manajemen ambang batas (Threshold), Setup Camera, & Data History.

---

## ⚠️ Perhatian Seputar Model AI (Cloudflare R2 Assets)
Semua model berukuran besar (`.gguf`) **TIDAK** didistribusikan melalui repository Git ini. Model-model tersebut disimpan secara terpisah
Apabila Anda men-clone repository ini, silakan ikuti petunjuk berikut:

1. Unduh model SLM Chatbot `tinyllama-1.1b-chat.Q4_K_M.gguf`
2. Letakkan file tersebut di dalam folder `models/`.
```text
./
 └── models/
     └── tinyllama-1.1b-chat.Q4_K_M.gguf
```

*(Catatan: Folder/extension model ini diblokir secara eksplisit di `.gitignore` untuk mencegah blob berukuran raksasa terunggah ke Git).*

---

## 🚀 Panduan Instalasi dan Menjalankan Server

### 1. Prasyarat Backend
- Disarankan menggunakan Python 3.9 sampai 3.11.
- Aktifkan fitur Virtual Environment (venv) Anda:
  ```bash
  python -m venv venv
  # Aktifkan di Windows:
  venv\Scripts\activate
  # Aktifkan di Linux/Mac:
  source venv/bin/activate
  ```

### 2. Install Dependensi
```bash
pip install -r requirements.txt
```
*(Catatan: pastikan menginstal wheel / SDK khusus `llama-cpp-python` yang kompatibel dengan Arsitektur CPU/GPU Hardware anda. Standarnya otomatis diinstal tanpa CUDA).*

### 3. Konfigurasi Variabel Lingkungan
Salin `.env.example` ke `.env` baru dan isikan kunci Rahasia / Telegram Anda.
```bash
cp .env.example .env
```

### 4. Mulai Server (FastAPI Uvicorn)
Sistem sekarang bersifat modular ke dalam folder `/app`. Masuk ke *root directory* dan eksekusi Uvicorn via Terminal Utama:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8500
```
Server Web UI Dashboard akan berjalan sepenuhnya di `http://localhost:8500`.

---

## 🔌 Panduan Firmware ESP32 (Sensor Node)
Sistem membutuhkan *node* pengirim data sensor secara asinkronus ke server web.
1. Buka file `esp32/fire_sensor.ino` melalui Arduino IDE.
2. Setel Target Board URL ke standard library `ESP32 Dev Module`.
3. Ganti Variabel Konstanta jaringan WiFi anda `ssid`, `password`, dan set properti IP Host Server di variabel `SERVER_IP`.
4. Kompilasi & Burn script Firmware tersebut. Data akan diproses langsung ketika ESP32 menyala.
