# ==============================================================================
# Tujuan       : AI Engine - YOLO inference, XGBoost prediction, decision fusion
#                Termasuk konversi RAW ADC (ESP32) → PPM sebelum prediksi model.
#                TIDAK memerlukan resistor eksternal (RL cancel out di Rs/Ro).
# Caller       : app.websocket_handler
# Dependensi   : ultralytics (YOLO), joblib/xgboost, numpy, app.config
# Main Functions: predict_yolo(), predict_xgboost(), decision_fusion(),
#                 raw_adc_to_ppm(), convert_sensor_to_model_features()
# Side Effects : Load model files dari disk saat import
# ==============================================================================

import os
import math
import warnings
import numpy as np
import joblib

from app.config import YOLO_MODEL_PATH, XGBOOST_MODEL_PATH, get_thresholds

# Suppress sklearn version warning
try:
    from sklearn.exceptions import InconsistentVersionWarning
    warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
except ImportError:
    pass

# ==============================================================================
# Konfigurasi konversi RAW ADC → PPM
# ==============================================================================
# Rumus: PPM = a * (Rs/Ro)^b
#
# PENTING: RL (Load Resistor) TIDAK diperlukan dalam perhitungan!
# RL cancel out saat menghitung rasio Rs/Ro:
#   Rs = RL * (VCC - Vout) / Vout
#   Ro = RL * (VCC - Vout_clean) / Vout_clean
#   Rs/Ro = [(VCC - Vout) / Vout] / [(VCC - Vout_clean) / Vout_clean]
# Sehingga RL hilang. Cocok untuk modul breakout MQ (RL bawaan board)
# maupun rangkaian tanpa resistor eksternal.
#
# Mapping sensor MQ → gas type di dataset training:
#   MQ-4  → cng   (Methane/CNG)
#   MQ-7  → co    (Carbon Monoxide)
#   MQ-5  → lpg   (LPG)
#   MQ-135 → smoke (Air Quality / Smoke)
#   MQ-2  → flame (Combustible gas, proxy for fire intensity)
# ==============================================================================

VCC_SENSOR = 5.0    # Supply voltage ke modul sensor MQ (5V)
VCC_ADC = 3.3       # Referensi tegangan ADC ESP32 (3.3V)
ADC_MAX = 4095.0    # ESP32 12-bit ADC
# CATATAN: RL tidak diperlukan — cancel out di rasio Rs/Ro

# Clean air resistance ratio (Rs/Ro di udara bersih) dari datasheet
# Digunakan untuk menghitung Ro dari RAW kalibrasi
CLEAN_AIR_FACTORS = {
    "mq4":  4.4,   # MQ-4 Rs/Ro di udara bersih ≈ 4.4
    "mq5":  6.5,   # MQ-5 Rs/Ro di udara bersih ≈ 6.5
    "mq135": 3.6,  # MQ-135 Rs/Ro di udara bersih ≈ 3.6
    "mq2":  9.8,   # MQ-2 Rs/Ro di udara bersih ≈ 9.8
    "mq7":  27.0,  # MQ-7 Rs/Ro di udara bersih ≈ 27.0
}

# Normal RAW ADC values dari kalibrasi ESP32 (clean air)
NORMAL_RAW = {
    "mq4":  1357,
    "mq5":  2966,
    "mq135": 758,
    "mq2":  230,
    "mq7":  280,
}

# Koefisien kurva karakteristik sensor: PPM = a * (Rs/Ro)^b
# Nilai a dan b dari datasheet masing-masing sensor untuk gas target
SENSOR_CURVES = {
    "mq4":  {"a": 1012.7, "b": -2.786},   # MQ-4 → Methane (CNG)
    "mq7":  {"a": 99.042, "b": -1.518},    # MQ-7 → CO
    "mq5":  {"a": 1000.5, "b": -2.186},    # MQ-5 → LPG
    "mq135": {"a": 110.47, "b": -2.862},   # MQ-135 → Smoke/Air Quality
    "mq2":  {"a": 574.25, "b": -2.222},    # MQ-2 → Combustible gas (flame proxy)
}


def _raw_to_voltage_ratio(raw_adc: float) -> float:
    """
    Konversi RAW ADC → rasio tegangan (VCC - Vout) / Vout.

    Sirkuit sensor MQ:
        VCC_SENSOR (5V) --- Rs --- Vout --- RL (bawaan modul) --- GND

    Vout dibaca oleh ESP32 ADC (referensi 3.3V):
        Vout = (RAW_ADC / ADC_MAX) * VCC_ADC

    Rasio = (VCC_SENSOR - Vout) / Vout
    Ini proporsional dengan Rs/RL, dan RL cancel out di Rs/Ro.
    Tidak perlu tahu nilai RL!
    """
    if raw_adc <= 0:
        raw_adc = 1  # Hindari division by zero
    if raw_adc >= ADC_MAX:
        raw_adc = ADC_MAX - 1

    vout = (raw_adc / ADC_MAX) * VCC_ADC
    return (VCC_SENSOR - vout) / vout


def _compute_rs_ro_clean(sensor_key: str) -> float:
    """
    Hitung rasio tegangan di udara bersih (proporsional Rs_clean/RL).
    Digunakan sebagai baseline untuk menghitung Rs/Ro.
    """
    raw_clean = NORMAL_RAW.get(sensor_key, 1)
    return _raw_to_voltage_ratio(raw_clean)


# Pre-compute rasio tegangan clean air untuk semua sensor saat module di-load
_CLEAN_RATIOS = {key: _compute_rs_ro_clean(key) for key in NORMAL_RAW}


def _compute_clean_ppm(sensor_key: str) -> float:
    """Hitung PPM baseline di udara bersih untuk dikurangi saat konversi."""
    if sensor_key not in SENSOR_CURVES or sensor_key not in _CLEAN_RATIOS:
        return 0.0
    rs_ro = CLEAN_AIR_FACTORS.get(sensor_key, 1.0)
    a = SENSOR_CURVES[sensor_key]["a"]
    b = SENSOR_CURVES[sensor_key]["b"]
    try:
        return a * math.pow(rs_ro, b)
    except (ValueError, OverflowError):
        return 0.0


# Pre-compute baseline PPM udara bersih (akan dikurangi dari hasil konversi)
_CLEAN_PPM = {key: _compute_clean_ppm(key) for key in SENSOR_CURVES}


def raw_adc_to_ppm(sensor_key: str, raw_adc: float) -> float:
    """
    Konversi satu sensor RAW ADC → PPM.
    TIDAK memerlukan resistor eksternal (RL cancel out).

    Matematika:
        Rs/Ro = [(VCC-Vout)/Vout] / [(VCC-Vout_clean)/Vout_clean] / clean_air_factor
        PPM   = a * (Rs/Ro)^b

    Args:
        sensor_key: "mq4", "mq5", "mq135", "mq2", "mq7"
        raw_adc: Nilai RAW ADC dari ESP32 (0-4095)

    Returns:
        Estimasi PPM (bisa sangat kecil untuk udara bersih)
    """
    if sensor_key not in SENSOR_CURVES or sensor_key not in _CLEAN_RATIOS:
        return raw_adc  # Fallback: return raw jika sensor tidak dikenali

    # Rasio tegangan saat ini
    current_ratio = _raw_to_voltage_ratio(raw_adc)
    clean_ratio = _CLEAN_RATIOS[sensor_key]
    clean_air_factor = CLEAN_AIR_FACTORS.get(sensor_key, 1.0)

    if clean_ratio <= 0:
        return 0.0

    # Rs/Ro = (current_ratio / clean_ratio) * clean_air_factor
    # Karena clean_ratio = Rs_clean/RL, current_ratio = Rs/RL
    # Rs/Ro = (Rs/RL) / (Rs_clean/RL) * (Rs_clean/Ro)
    #       = (Rs/Rs_clean) * clean_air_factor
    rs_ro = (current_ratio / clean_ratio) * clean_air_factor

    a = SENSOR_CURVES[sensor_key]["a"]
    b = SENSOR_CURVES[sensor_key]["b"]

    # PPM = a * (Rs/Ro)^b
    try:
        ppm = a * math.pow(rs_ro, b)
    except (ValueError, OverflowError):
        ppm = 0.0

    # Kurangi baseline PPM udara bersih agar clean air ≈ 0 PPM.
    # Tanpa ini, MQ-2 (flame) menghasilkan 3.6 PPM di udara bersih
    # yang oleh model dianggap 11.87 std deviasi di atas mean → false positive.
    baseline = _CLEAN_PPM.get(sensor_key, 0.0)
    ppm -= baseline

    return max(0.0, ppm)  # PPM tidak bisa negatif


def convert_sensor_to_model_features(sensor_data: dict) -> dict:
    """
    Konversi data sensor MQ (RAW ADC) → fitur model (PPM).

    Input:  {"mq135": 758, "mq2": 230, "mq4": 1357, "mq5": 2966, "mq7": 280, ...}
    Output: {"cng": ..., "co": ..., "flame": ..., "lpg": ..., "smoke": ...}

    Mapping:
        MQ-4  → cng
        MQ-7  → co
        MQ-5  → lpg
        MQ-135 → smoke
        MQ-2  → flame
    """
    return {
        "cng":   raw_adc_to_ppm("mq4",  sensor_data.get("mq4",  0)),
        "co":    raw_adc_to_ppm("mq7",  sensor_data.get("mq7",  0)),
        "lpg":   raw_adc_to_ppm("mq5",  sensor_data.get("mq5",  0)),
        "smoke": raw_adc_to_ppm("mq135", sensor_data.get("mq135", 0)),
        "flame": raw_adc_to_ppm("mq2",  sensor_data.get("mq2",  0)),
    }


# ==============================================================================
# Load Models
# ==============================================================================
yolo_model = None
xgb_model = None
scaler = None    # StandardScaler dari training (scaler.pkl)

SCALER_PATH = "models/scaler.pkl"


def load_models():
    """Load YOLO, XGBoost/RF, dan Scaler. Dipanggil saat startup."""
    global yolo_model, xgb_model, scaler

    # Load YOLO
    try:
        from ultralytics import YOLO
        if os.path.exists(YOLO_MODEL_PATH):
            yolo_model = YOLO(YOLO_MODEL_PATH)
            print(f"[AI] YOLOv11 loaded: {YOLO_MODEL_PATH}")
        else:
            print(f"[AI] YOLO model tidak ditemukan: {YOLO_MODEL_PATH}")
    except Exception as e:
        print(f"[AI] Error loading YOLO: {e}")

    # Load XGBoost (atau fallback ke model lama RF)
    try:
        if os.path.exists(XGBOOST_MODEL_PATH):
            xgb_model = joblib.load(XGBOOST_MODEL_PATH)
            print(f"[AI] Sensor model loaded: {XGBOOST_MODEL_PATH}")
        elif os.path.exists("models/fire_detection_rf.pkl"):
            xgb_model = joblib.load("models/fire_detection_rf.pkl")
            print("[AI] Fallback: Random Forest loaded")
        else:
            print("[AI] Tidak ada model sensor prediction ditemukan")
    except Exception as e:
        print(f"[AI] Error loading sensor model: {e}")

    # Load Scaler (StandardScaler dari training notebook)
    try:
        if os.path.exists(SCALER_PATH):
            scaler = joblib.load(SCALER_PATH)
            print(f"[AI] Scaler loaded: {SCALER_PATH}")
        else:
            print(f"[AI] Scaler tidak ditemukan: {SCALER_PATH} (prediksi tanpa scaling)")
    except Exception as e:
        print(f"[AI] Error loading scaler: {e}")


# ==============================================================================
# Prediction Functions
# ==============================================================================

def predict_yolo(frame) -> float:
    """
    Jalankan YOLO pada frame kamera.
    Return: confidence tertinggi deteksi api/asap (0-100).
    """
    if yolo_model is None or frame is None:
        return 0.0
    try:
        results = yolo_model.predict(frame, verbose=False)
        max_conf = 0.0
        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    conf = float(box.conf[0]) * 100
                    if conf > max_conf:
                        max_conf = conf
        return round(max_conf, 1)
    except Exception as e:
        print(f"[AI] YOLO error: {e}")
        return 0.0


def predict_xgboost(sensor_data: dict) -> float:
    """
    Prediksi probabilitas kebakaran dari data sensor MQ.

    Pipeline:
        1. RAW ADC (ESP32) → PPM (konversi kurva karakteristik sensor MQ)
        2. PPM → fitur model: [cng, co, flame, lpg, smoke]
        3. StandardScaler transform (jika scaler tersedia)
        4. Model predict_proba → probabilitas kebakaran (0-100)

    Input: dict dengan keys mq135, mq2, mq3, mq4, mq5, mq7 (RAW ADC)
    Return: probabilitas kebakaran (0-100).
    """
    if xgb_model is None:
        return 0.0
    try:
        # Step 1-2: Konversi RAW ADC → PPM → fitur model
        ppm_features = convert_sensor_to_model_features(sensor_data)

        # Urutan fitur HARUS sama dengan saat training:
        # ['cng', 'co', 'flame', 'lpg', 'smoke']
        features = np.array([[
            ppm_features["cng"],
            ppm_features["co"],
            ppm_features["flame"],
            ppm_features["lpg"],
            ppm_features["smoke"],
        ]])

        # Step 3: Scaling (jika scaler tersedia dari training)
        if scaler is not None:
            features = scaler.transform(features)

        # Step 4: Prediksi
        prob = xgb_model.predict_proba(features)[0][1] * 100
        return round(prob, 1)
    except Exception as e:
        print(f"[AI] XGBoost error: {e}")
        return 0.0


# ==============================================================================
# Decision Fusion & Status
# ==============================================================================

def decision_fusion(yolo_prob: float, xgb_prob: float) -> float:
    """
    Fusi keputusan: gabungkan hasil YOLO dan XGBoost.
    Jika YOLO confidence tinggi → YOLO dominan (visual confirmed).
    Jika YOLO rendah → sensor dominan.
    """
    thresholds = get_thresholds()
    yolo_thresh = thresholds.get("yolo_threshold", 50)
    w_high = thresholds.get("yolo_weight_high", 0.7)
    w_low = thresholds.get("yolo_weight_low", 0.3)

    if yolo_prob > yolo_thresh:
        return round((yolo_prob * w_high) + (xgb_prob * (1 - w_high)), 1)
    else:
        return round((yolo_prob * w_low) + (xgb_prob * (1 - w_low)), 1)


def get_status_label(prob_akhir: float) -> str:
    """Tentukan label status berdasarkan probabilitas dan threshold."""
    thresholds = get_thresholds()
    if prob_akhir < thresholds.get("prob_aman", 30):
        return "Aman"
    elif prob_akhir < thresholds.get("prob_waspada", 70):
        return "Waspada"
    else:
        return "Bahaya"
