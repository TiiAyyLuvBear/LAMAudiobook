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


@app.on_event("startup")
async def startup() -> None:
    await queue_service.start()


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "queue": queue_service.get_queue_stats()}
