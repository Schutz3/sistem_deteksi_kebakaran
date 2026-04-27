# ==============================================================================
# Tujuan       : AI Engine - YOLO inference, XGBoost prediction, decision fusion
# Caller       : app.websocket_handler
# Dependensi   : ultralytics (YOLO), joblib/xgboost, numpy, app.config
# Main Functions: predict_yolo(), predict_xgboost(), decision_fusion()
# Side Effects : Load model files dari disk saat import
# ==============================================================================

import os
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

# --- Load Models ---
yolo_model = None
xgb_model = None

def load_models():
    """Load YOLO dan XGBoost model. Dipanggil saat startup."""
    global yolo_model, xgb_model

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

    # Load XGBoost (atau fallback ke model lama RF jika XGB belum ada)
    try:
        if os.path.exists(XGBOOST_MODEL_PATH):
            xgb_model = joblib.load(XGBOOST_MODEL_PATH)
            print(f"[AI] XGBoost loaded: {XGBOOST_MODEL_PATH}")
        elif os.path.exists("models/fire_detection_rf.pkl"):
            xgb_model = joblib.load("models/fire_detection_rf.pkl")
            print("[AI] Fallback: Random Forest loaded (XGBoost belum tersedia)")
        else:
            print("[AI] Tidak ada model sensor prediction ditemukan")
    except Exception as e:
        print(f"[AI] Error loading sensor model: {e}")


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
    Input: dict dengan keys mq135, mq2, mq3, mq4, mq5, mq7
    Return: probabilitas kebakaran (0-100).
    """
    if xgb_model is None:
        return 0.0
    try:
        features = np.array([[
            sensor_data.get("mq135", 0),
            sensor_data.get("mq2", 0),
            sensor_data.get("mq3", 0),
            sensor_data.get("mq4", 0),
            sensor_data.get("mq5", 0),
            sensor_data.get("mq7", 0),
        ]])
        prob = xgb_model.predict_proba(features)[0][1] * 100
        return round(prob, 1)
    except Exception as e:
        print(f"[AI] XGBoost error: {e}")
        return 0.0


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
