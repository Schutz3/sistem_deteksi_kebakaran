# ==============================================================================
# Tujuan       : Endpoint HTTP untuk terima data sensor dari ESP32
#                Menyediakan API CRUD kamera & threshold untuk dashboard
# Caller       : ESP32 via HTTP POST, dashboard via fetch()
# Dependensi   : app.config, app.camera
# Main Functions: POST /api/sensor, GET/POST /api/cameras, GET/POST /api/thresholds
# Side Effects : Update state di app.config, sync kamera
# ==============================================================================

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.config import (
    get_cameras, add_camera, remove_camera,
    get_thresholds, set_thresholds,
    update_sensor_data, get_sensor_data,
)
from app.camera import camera_manager

router = APIRouter()


# --- Model Pydantic ---

class SensorPayload(BaseModel):
    """Data yang dikirim ESP32 setiap 2 detik."""
    camera_id: str
    mq135: float = 0.0  # Kualitas udara
    mq2: float = 0.0    # Asap / gas mudah terbakar
    mq3: float = 0.0    # Alkohol
    mq4: float = 0.0    # Metana / gas alam
    mq5: float = 0.0    # LPG / gas alam
    mq7: float = 0.0    # Karbon monoksida (CO)


class CameraPayload(BaseModel):
    cam_id: str
    name: str
    rtsp_url: str


class ThresholdPayload(BaseModel):
    prob_aman: Optional[float] = None
    prob_waspada: Optional[float] = None
    yolo_weight_high: Optional[float] = None
    yolo_weight_low: Optional[float] = None
    yolo_threshold: Optional[float] = None
    yolo_interval: Optional[float] = None
    sensor_interval: Optional[float] = None


# --- Endpoint Sensor ESP32 ---

@router.post("/api/sensor")
async def receive_sensor_data(payload: SensorPayload):
    """
    Terima data dari ESP32 dan simpan ke memory.
    ESP32 mengirim POST setiap 2 detik.
    """
    data = {
        "mq135": payload.mq135,
        "mq2": payload.mq2,
        "mq3": payload.mq3,
        "mq4": payload.mq4,
        "mq5": payload.mq5,
        "mq7": payload.mq7,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    update_sensor_data(payload.camera_id, data)
    return {"status": "ok", "camera_id": payload.camera_id}


@router.get("/api/sensor/{camera_id}")
async def get_latest_sensor(camera_id: str):
    """Ambil data sensor terbaru untuk kamera tertentu."""
    data = get_sensor_data(camera_id)
    if not data:
        return {"status": "no_data", "camera_id": camera_id}
    return {"status": "ok", "camera_id": camera_id, "data": data}


# --- Endpoint Kamera CRUD ---

@router.get("/api/cameras")
async def list_cameras():
    """Daftar semua kamera yang terdaftar."""
    return {"cameras": get_cameras()}


@router.post("/api/cameras")
async def add_new_camera(payload: CameraPayload):
    """Tambah kamera baru dan langsung start stream."""
    add_camera(payload.cam_id, payload.name, payload.rtsp_url)
    camera_manager.add_camera(payload.cam_id, payload.rtsp_url)
    return {"status": "added", "cam_id": payload.cam_id}


@router.delete("/api/cameras/{cam_id}")
async def delete_camera(cam_id: str):
    """Hapus kamera."""
    remove_camera(cam_id)
    camera_manager.remove_camera(cam_id)
    return {"status": "removed", "cam_id": cam_id}


# --- Endpoint Threshold ---

@router.get("/api/thresholds")
async def get_current_thresholds():
    """Ambil semua threshold yang aktif."""
    return {"thresholds": get_thresholds()}


@router.post("/api/thresholds")
async def update_thresholds(payload: ThresholdPayload):
    """Update threshold dari dashboard."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        set_thresholds(updates)
    return {"status": "updated", "thresholds": get_thresholds()}
