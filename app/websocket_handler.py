# ==============================================================================
# Tujuan       : WebSocket handler untuk real-time monitoring multi-kamera
#                Stream MJPEG per kamera + data sensor + AI inference
# Caller       : main.py (router include), frontend via WebSocket
# Dependensi   : app.camera, app.ai_engine, app.config, app.notification
# Main Functions: websocket_monitor(), mjpeg_stream()
# Side Effects : Membaca frame kamera, mengirim notifikasi Telegram
# ==============================================================================

import asyncio
import json
import base64
import cv2
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.camera import camera_manager
from app.ai_engine import predict_yolo, predict_xgboost, decision_fusion, get_status_label
from app.notification import kirim_notifikasi_telegram
from app.config import get_thresholds, get_sensor_data, get_cameras

router = APIRouter()


@router.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    """
    WebSocket utama: kirim data semua kamera + sensor + AI ke client.
    Client terima JSON per cycle (setiap ~2 detik).
    """
    await websocket.accept()
    last_yolo_time: dict = {}   # per camera
    last_yolo_prob: dict = {}   # per camera

    try:
        while True:
            loop_start = asyncio.get_event_loop().time()
            thresholds = get_thresholds()
            cameras = get_cameras()
            current_time = asyncio.get_event_loop().time()

            cameras_data = []

            for cam_id, cam_cfg in cameras.items():
                if not cam_cfg.get("enabled", True):
                    continue

                cam_name = cam_cfg.get("name", cam_id)

                # --- Sensor data dari ESP32 ---
                sensor = get_sensor_data(cam_id)
                has_sensor = bool(sensor)

                # --- YOLO inference (rate limited) ---
                yolo_interval = thresholds.get("yolo_interval", 3.0)
                last_t = last_yolo_time.get(cam_id, 0)

                if current_time - last_t >= yolo_interval:
                    frame = camera_manager.get_frame(cam_id)
                    if frame is not None:
                        prob_yolo = await asyncio.to_thread(predict_yolo, frame)
                        last_yolo_prob[cam_id] = prob_yolo

                        # Encode frame ke base64 JPEG untuk live view
                        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                        frame_b64 = base64.b64encode(jpeg.tobytes()).decode('utf-8')
                    else:
                        last_yolo_prob.setdefault(cam_id, 0.0)
                        frame_b64 = None
                    last_yolo_time[cam_id] = current_time
                else:
                    frame_b64 = None  # Tidak kirim frame setiap cycle

                prob_yolo = last_yolo_prob.get(cam_id, 0.0)

                # --- XGBoost prediction ---
                prob_xgb = 0.0
                if has_sensor:
                    prob_xgb = await asyncio.to_thread(predict_xgboost, sensor)

                # --- Decision Fusion ---
                prob_akhir = decision_fusion(prob_yolo, prob_xgb)
                status = get_status_label(prob_akhir)

                # --- Log & Notification ---
                log_message = ""
                if status != "Aman":
                    sensor_str = f"MQ2:{sensor.get('mq2', 0)} MQ7:{sensor.get('mq7', 0)}" if has_sensor else "No sensor"
                    log_message = f"[{cam_name}] Prob {prob_akhir}%. {sensor_str}"

                    if status == "Bahaya":
                        asyncio.create_task(asyncio.to_thread(
                            kirim_notifikasi_telegram,
                            cam_name, status, prob_akhir, sensor_str
                        ))

                cam_data = {
                    "cam_id": cam_id,
                    "cam_name": cam_name,
                    "prob_yolo": prob_yolo,
                    "prob_xgboost": prob_xgb,
                    "prob_akhir": prob_akhir,
                    "status": status,
                    "sensor": sensor if has_sensor else None,
                    "log_message": log_message,
                }
                if frame_b64:
                    cam_data["frame"] = frame_b64

                cameras_data.append(cam_data)

            # Kirim data semua kamera ke client
            await websocket.send_text(json.dumps({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "cameras": cameras_data,
                "thresholds": thresholds,
            }))

            # Sleep interval
            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_time = max(0, thresholds.get("sensor_interval", 2.0) - elapsed)
            await asyncio.sleep(sleep_time)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WebSocket] Error: {e}")


# --- Legacy WebSocket (backward compatibility) ---
@router.websocket("/ws/sensor")
async def websocket_legacy(websocket: WebSocket):
    """
    Backward-compatible WebSocket untuk single kamera.
    Mengirim data kamera pertama yang aktif.
    """
    await websocket.accept()
    last_yolo_time = 0
    last_yolo_prob = 0.0

    try:
        while True:
            loop_start = asyncio.get_event_loop().time()
            thresholds = get_thresholds()
            cameras = get_cameras()
            current_time = asyncio.get_event_loop().time()

            # Ambil kamera pertama
            cam_id = None
            cam_name = "Default"
            for cid, cfg in cameras.items():
                if cfg.get("enabled", True):
                    cam_id = cid
                    cam_name = cfg.get("name", cid)
                    break

            # Sensor data
            sensor = get_sensor_data(cam_id) if cam_id else {}
            mq2_val = sensor.get("mq2", 0)
            mq7_val = sensor.get("mq7", 0)

            # YOLO
            yolo_interval = thresholds.get("yolo_interval", 3.0)
            if current_time - last_yolo_time >= yolo_interval and cam_id:
                frame = camera_manager.get_frame(cam_id)
                if frame is not None:
                    prob_yolo = await asyncio.to_thread(predict_yolo, frame)
                    last_yolo_prob = prob_yolo
                last_yolo_time = current_time

            prob_yolo = last_yolo_prob

            # XGBoost
            prob_xgb = 0.0
            if sensor:
                prob_xgb = await asyncio.to_thread(predict_xgboost, sensor)

            # Fusion
            prob_akhir = decision_fusion(prob_yolo, prob_xgb)
            status = get_status_label(prob_akhir)

            log_message = ""
            if status != "Aman":
                log_message = f"Anomali: MQ2 {mq2_val}, CO {mq7_val}. Prob {prob_akhir}%."
                if status == "Bahaya":
                    sensor_str = f"MQ2:{mq2_val} MQ7:{mq7_val}"
                    asyncio.create_task(asyncio.to_thread(
                        kirim_notifikasi_telegram,
                        cam_name, status, prob_akhir, sensor_str
                    ))

            await websocket.send_text(json.dumps({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "sensor": sensor if sensor else None,
                "prob_yolo": prob_yolo,
                "prob_xgboost": prob_xgb,
                "prob_akhir": prob_akhir,
                "status": status,
                "log_message": log_message,
            }))

            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_time = max(0, thresholds.get("sensor_interval", 2.0) - elapsed)
            await asyncio.sleep(sleep_time)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS Legacy] Error: {e}")
