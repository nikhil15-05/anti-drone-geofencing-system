import asyncio
import logging
import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import serial
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("rf_sentinel")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
MODEL_PATH = PROJECT_ROOT / "Models_and_Dataset" / "Models" / "rf_drone_model.pkl"
SERIAL_PORT = os.getenv("SERIAL_PORT")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
CLASS_NAMES = {0: "Background / non-target", 1: "Target RF source"}

try:
    model = joblib.load(MODEL_PATH)
    logger.info("Loaded model artifact: %s", MODEL_PATH.name)
except Exception:
    logger.exception("Could not load model artifact: %s", MODEL_PATH.name)
    model = None


def extract_features(window: list[np.ndarray]) -> np.ndarray:
    """Build the 129 features expected by the trained model."""
    latest = window[-1]
    tot_active = np.sum(latest)
    mid_upper_hits = np.sum(latest[31:])
    spectral_delta = np.sum(np.abs(window[-1] - window[-2]))
    active_indices = np.where(latest == 1)[0]
    dispersion = np.std(active_indices) if len(active_indices) > 0 else 0.0
    return np.hstack(
        [latest, tot_active, mid_upper_hits, spectral_delta, dispersion]
    )


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, data: dict[str, Any]) -> None:
        disconnected: list[WebSocket] = []
        for websocket in tuple(self.connections):
            try:
                await websocket.send_json(data)
            except (RuntimeError, OSError, WebSocketDisconnect) as exc:
                logger.debug("Removing disconnected WebSocket client: %s", exc)
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)


class SerialMonitor:
    def __init__(self, port: str, baud_rate: int, loop: asyncio.AbstractEventLoop):
        self.port = port
        self.baud_rate = baud_rate
        self.loop = loop
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._read_serial_stream, name="serial-reader", daemon=True
        )
        self.frame_history: deque[np.ndarray] = deque(maxlen=5)
        self.prediction_window: deque[int] = deque(maxlen=15)
        self.frame_sequence = 0
        self.serial_connected = False

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            logger.warning("Serial reader thread did not stop within 3 seconds")

    def health(self) -> dict[str, Any]:
        return {
            "model_loaded": model is not None,
            "serial_connected": self.serial_connected,
            "sequence": self.frame_sequence,
        }

    def _read_serial_stream(self) -> None:
        while not self.stop_event.is_set():
            if not self.port:
                logger.error(
                    "SERIAL_PORT is not configured. Set it to the connected device's port."
                )
                self.stop_event.wait(10)
                continue
            try:
                with serial.Serial(
                    self.port, self.baud_rate, timeout=1
                ) as connection:
                    self.serial_connected = True
                    logger.info("Connected to serial port %s", self.port)
                    while not self.stop_event.is_set():
                        line = connection.readline().decode(
                            "utf-8", errors="ignore"
                        ).strip()
                        if len(line) != 125 or any(bit not in "01" for bit in line):
                            continue
                        self._process_frame(line)
            except (serial.SerialException, OSError) as exc:
                if not self.stop_event.is_set():
                    logger.error(
                        "Serial error on %s: %s; retrying in 2 seconds",
                        self.port,
                        exc,
                    )
                    self.frame_history.clear()
                    self.prediction_window.clear()
                    self.stop_event.wait(2)
            finally:
                self.serial_connected = False

    def _process_frame(self, line: str) -> None:
        frame_data = np.fromiter((int(bit) for bit in line), dtype=int)
        self.frame_history.append(frame_data)

        drone_detected = False
        confidence = 0.0
        class_name = "Warming up"
        probabilities = {str(label): 0.0 for label in CLASS_NAMES}
        inference_error = False

        if model is not None and len(self.frame_history) == self.frame_history.maxlen:
            try:
                features = extract_features(list(self.frame_history))
                raw_prediction = model.predict([features])[0]
                predicted_probabilities = model.predict_proba([features])[0]
                self.prediction_window.append(int(raw_prediction))
                class_name = CLASS_NAMES.get(
                    int(raw_prediction), f"Class {raw_prediction}"
                )
                probabilities = {
                    str(int(label)): round(float(probability) * 100, 1)
                    for label, probability in zip(
                        model.classes_, predicted_probabilities
                    )
                }
                drone_frame_count = sum(
                    prediction == 1 for prediction in self.prediction_window
                )
                drone_detected = (
                    len(self.prediction_window) == self.prediction_window.maxlen
                    and drone_frame_count / self.prediction_window.maxlen >= 0.30
                )
                confidence = float(probabilities.get("1", 0.0)) / 100
            except Exception:
                logger.exception(
                    "Model inference failed for frame %s", self.frame_sequence + 1
                )
                self.prediction_window.clear()
                class_name = "Inference error"
                inference_error = True

        self.frame_sequence += 1
        payload = {
            "channels": frame_data.tolist(),
            "drone_detected": drone_detected,
            "confidence": round(confidence * 100, 1),
            "active_channels": int(np.sum(frame_data)),
            "class_name": class_name,
            "probabilities": probabilities,
            "timestamp": time.time(),
            "sequence": self.frame_sequence,
            "model_loaded": model is not None,
            "inference_error": inference_error,
        }
        future = asyncio.run_coroutine_threadsafe(
            manager.broadcast(payload), self.loop
        )
        future.add_done_callback(self._log_broadcast_error)

    @staticmethod
    def _log_broadcast_error(future: Any) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("Failed to broadcast spectrum data")


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    monitor = SerialMonitor(SERIAL_PORT, BAUD_RATE, asyncio.get_running_loop())
    monitor.start()
    app.state.monitor = monitor
    logger.info("RF Sentinel backend started")
    try:
        yield
    finally:
        monitor.stop()
        logger.info("RF Sentinel backend stopped")


app = FastAPI(title="RF Sentinel API", lifespan=lifespan)

if (FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )


@app.get("/api/health")
async def health() -> dict[str, Any]:
    monitor: SerialMonitor | None = getattr(app.state, "monitor", None)
    if monitor is None:
        return {
            "model_loaded": model is not None,
            "serial_connected": False,
            "sequence": 0,
        }
    return monitor.health()


@app.websocket("/ws")
async def spectrum_stream(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/")
async def frontend() -> FileResponse:
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                "React frontend is not built. Run `npm run build` in "
                "rf_web_dashboard/frontend, or use the Vite development server."
            ),
        )
    return FileResponse(index_file)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=False)
