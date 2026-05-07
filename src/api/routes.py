"""
Audiobook HTTP routes.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from pipeline import AudiobookPipeline, PipelineConfig
from services.queue import JobStatus, QueueService
from services.storage import StorageService


router = APIRouter(prefix="/api/v1/audiobook", tags=["audiobook"])

queue_service = QueueService()
storage_service = StorageService()


class CreateJobResponse(BaseModel):
    job_id: str
    status: str


def _max_upload_bytes() -> int:
    return int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024


async def audiobook_generation_handler(
    payload: Dict[str, Any],
    progress_callback: Callable[[float, Optional[str]], Awaitable[None]],
    state_callback: Callable[[Dict[str, Any]], Awaitable[None]],
) -> Dict[str, Any]:
    job_id = payload["job_id"]
    output_format = payload.get("output_format", "mp3")
    storage_service.append_log(job_id, "Starting audiobook pipeline")

    pipeline = AudiobookPipeline(
        PipelineConfig(
            input_file=payload["input_file"],
            output_dir=payload["output_dir"],
            output_format=output_format,
            normalize_audio=bool(payload.get("normalize_audio", True)),
            add_chapters=bool(payload.get("add_chapters", True)),
            analysis_enabled=bool(payload.get("analysis_enabled", True)),
            tts_engine=os.getenv("TTS_ENGINE", "xtts_gpu"),
            xtts_model_name_or_path=os.getenv("XTTS_MODEL_NAME_OR_PATH") or None,
            xtts_config_path=os.getenv("XTTS_CONFIG_PATH") or None,
            xtts_vocab_path=os.getenv("XTTS_VOCAB_PATH") or None,
            xtts_voice_dir=os.getenv("XTTS_VOICE_DIR", "data/voice_samples"),
        )
    )

    task = asyncio.create_task(pipeline.run())
    while not task.done():
        state = pipeline.get_state()
        await state_callback(state)
        storage_service.save_metadata(job_id, state)
        await asyncio.sleep(0.5)

    result = await task
    await state_callback(pipeline.get_state())
    safe_result = {
        "success": bool(result.get("success")),
        "output_path": result.get("output_path"),
        "duration": result.get("duration", 0),
        "chapter_count": result.get("chapter_count", 0),
        "error": result.get("error"),
        "stage": result.get("stage"),
    }
    storage_service.save_metadata(job_id, {**pipeline.get_state(), "result": safe_result})

    if result.get("success"):
        output_path = result.get("output_path")
        if not output_path or not Path(output_path).exists():
            raise RuntimeError("Pipeline completed but output audio file is missing")
        storage_service.append_log(job_id, f"Completed: {output_path}")
    else:
        storage_service.append_log(job_id, f"Failed: {result.get('error')}")

    await progress_callback(1.0 if result.get("success") else pipeline.get_state().get("progress", 0), None)
    return safe_result


queue_service.register_handler("audiobook_generation", audiobook_generation_handler)


@router.post("/jobs", response_model=CreateJobResponse)
async def create_audiobook_job(
    file: UploadFile = File(...),
    output_format: str = "mp3",
    normalize_audio: bool = True,
    add_chapters: bool = True,
    analysis_enabled: bool = True,
):
    if not file.filename or not file.filename.lower().endswith(".epub"):
        raise HTTPException(status_code=400, detail="Only .epub uploads are supported")
    if output_format not in {"mp3", "wav"}:
        raise HTTPException(status_code=400, detail="output_format must be mp3 or wav")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > _max_upload_bytes():
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    job_id = str(uuid.uuid4())
    input_file = storage_service.save_input_file(job_id, content)
    output_dir = str(storage_service.job_dir(job_id) / "output")
    storage_service.save_metadata(
        job_id,
        {
            "source_filename": Path(file.filename).name,
            "output_format": output_format,
            "status": "pending",
        },
    )
    storage_service.append_log(job_id, f"Queued upload: {Path(file.filename).name}")

    await queue_service.enqueue(
        "audiobook_generation",
        {
            "job_id": job_id,
            "input_file": input_file,
            "output_dir": output_dir,
            "output_format": output_format,
            "normalize_audio": normalize_audio,
            "add_chapters": add_chapters,
            "analysis_enabled": analysis_enabled,
        },
        job_id=job_id,
    )
    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/jobs/{job_id}")
async def get_audiobook_job(job_id: str):
    status = await queue_service.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    status["logs"] = storage_service.read_logs(job_id)
    return status


@router.get("/jobs/{job_id}/logs", response_class=PlainTextResponse)
async def get_audiobook_job_logs(job_id: str):
    if not await queue_service.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return storage_service.read_logs(job_id)


@router.get("/jobs/{job_id}/download")
async def download_audiobook(job_id: str):
    job = await queue_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job is not completed")

    output_path = (job.result or {}).get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output audio not found")

    media_type = "audio/mpeg" if Path(output_path).suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(
        output_path,
        media_type=media_type,
        filename=Path(output_path).name,
    )


@router.delete("/jobs/{job_id}")
async def cancel_audiobook_job(job_id: str):
    success = await queue_service.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Only pending jobs can be cancelled")
    storage_service.append_log(job_id, "Cancelled before execution")
    return {"job_id": job_id, "status": "cancelled"}
