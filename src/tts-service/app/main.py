from fastapi import FastAPI
from .routers import tts

app = FastAPI(title="TTS Microservice")

app.include_router(tts.router, prefix="/api/tts")

@app.get("/health")
def health_check():
    return {"status": "ok"}
