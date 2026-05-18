"""
FastAPI entrypoint for the audiobook service.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv()

from api.routes import queue_service, router as audiobook_router  # noqa: E402


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501")
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(title="Audiobook AI Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audiobook_router)


def _tts_runtime_info() -> dict:
    engine = os.getenv("TTS_ENGINE", "xtts_gpu")
    device = os.getenv("VIENEU_DEVICE") or os.getenv("TTS_DEVICE", "auto")
    model = os.getenv("XTTS_MODEL_NAME_OR_PATH") or "aiMy144/XTTSv2VietAudiobook"
    lora_adapter = ""
    mode = ""

    if engine.lower() in {"vieneu", "vieneu_tts", "direct_vieneu"}:
        model = os.getenv("VIENEU_MODEL_NAME", "pnnbao-ump/VieNeu-TTS-0.3B")
        device = os.getenv("VIENEU_DEVICE") or os.getenv("TTS_DEVICE", "auto")
        lora_adapter = os.getenv("VIENEU_LORA_ADAPTER", "")
        mode = os.getenv("VIENEU_MODE", "standard")
    elif engine.lower() in {"xtts", "xtts_gpu", "direct_xtts"}:
        device = os.getenv("XTTS_DEVICE") or os.getenv("TTS_DEVICE", "auto")

    return {
        "engine": engine,
        "model": model,
        "device": device,
        "mode": mode,
        "lora_adapter": lora_adapter,
    }


@app.on_event("startup")
async def startup() -> None:
    await queue_service.start()


@app.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "queue": queue_service.get_queue_stats(),
        "tts": _tts_runtime_info(),
    }
