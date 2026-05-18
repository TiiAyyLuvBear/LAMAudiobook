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
SUPPORTED_INPUT_EXTENSIONS = {".epub", ".pdf", ".txt"}


class CreateJobResponse(BaseModel):
    job_id: str
    status: str


def _max_upload_bytes() -> int:
    return int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024


def _attach_job_metadata(job_status: Dict[str, Any], include_logs: bool = False) -> Dict[str, Any]:
    job_id = job_status["job_id"]
    metadata = storage_service.load_metadata(job_id) or {}
    result = job_status.get("result") or metadata.get("result") or {}
    job_status["result"] = result or job_status.get("result")
    artifacts = list(metadata.get("artifacts") or result.get("chapter_epubs", []))
    book_epub = result.get("book_epub") if isinstance(result, dict) else None
    if isinstance(book_epub, dict) and not any(artifact.get("type") == "book_epub" for artifact in artifacts):
        artifacts.append(book_epub)
    job_status["artifacts"] = artifacts
    job_status["source_filename"] = metadata.get("source_filename")
    job_status["output_format"] = metadata.get("output_format")
    if include_logs:
        job_status["logs"] = storage_service.read_logs(job_id)
    return job_status


def _save_job_metadata(job_id: str, metadata: Dict[str, Any]) -> None:
    existing = storage_service.load_metadata(job_id) or {}
    storage_service.save_metadata(job_id, {**existing, **metadata})


def _state_log_line(state: Dict[str, Any]) -> str:
    stage = state.get("stage") or "unknown"
    message = state.get("status_message") or ""
    chapter = f"{state.get('current_chapter') or 0}/{state.get('total_chapters') or 0}"
    segment = f"{state.get('current_segment') or 0}/{state.get('total_segments') or 0}"
    progress = round(float(state.get("progress") or 0.0) * 100, 1)
    return f"[{stage}] {progress}% | chapter {chapter} | segment {segment} | {message}".rstrip()


async def audiobook_generation_handler(
    payload: Dict[str, Any],
    progress_callback: Callable[[float, Optional[str]], Awaitable[None]],
    state_callback: Callable[[Dict[str, Any]], Awaitable[None]],
    should_cancel: Callable[[], bool],
) -> Dict[str, Any]:
    job_id = payload["job_id"]
    output_format = payload.get("output_format", "mp3")
    storage_service.append_log(job_id, "Starting audiobook pipeline")
    storage_service.append_log(
        job_id,
        (
            "Config: "
            f"TTS_ENGINE={os.getenv('TTS_ENGINE', 'xtts_gpu')}, "
            f"TTS_DEVICE={os.getenv('TTS_DEVICE', 'auto')}, "
            f"VIENEU_DEVICE={os.getenv('VIENEU_DEVICE', os.getenv('TTS_DEVICE', 'auto'))}, "
            f"output_format={output_format}"
        ),
    )

    def _record_stage_output(stage: str, filename: str, data: Any) -> None:
        try:
            if filename.lower().endswith(".txt"):
                storage_service.save_stage_text(job_id, stage, filename, str(data))
            else:
                storage_service.save_stage_json(job_id, stage, filename, data)
        except Exception as exc:
            storage_service.append_log(
                job_id,
                f"Warning: failed to write debug output {stage}/{filename}: {exc}",
            )

    pipeline = AudiobookPipeline(
        PipelineConfig(
            input_file=payload["input_file"],
            output_dir=payload["output_dir"],
            source_filename=payload.get("source_filename"),
            output_format=output_format,
            normalize_audio=bool(payload.get("normalize_audio", True)),
            add_chapters=bool(payload.get("add_chapters", True)),
            analysis_enabled=bool(payload.get("analysis_enabled", True)),
            tts_engine=os.getenv("TTS_ENGINE", "xtts_gpu"),
            tts_device=os.getenv("TTS_DEVICE", "auto"),
            tts_speaker_mode=os.getenv("TTS_SPEAKER_MODE", "single"),
            xtts_model_name_or_path=os.getenv("XTTS_MODEL_NAME_OR_PATH") or None,
            xtts_config_path=os.getenv("XTTS_CONFIG_PATH") or None,
            xtts_vocab_path=os.getenv("XTTS_VOCAB_PATH") or None,
            xtts_voice_dir=os.getenv("XTTS_VOICE_DIR", "data/voice_samples"),
            vieneu_model_name=os.getenv("VIENEU_MODEL_NAME", "pnnbao-ump/VieNeu-TTS-0.3B"),
            vieneu_mode=os.getenv("VIENEU_MODE", "standard"),
            vieneu_emotion=os.getenv("VIENEU_EMOTION", "storytelling"),
            vieneu_api_base=os.getenv("VIENEU_API_BASE") or None,
            vieneu_device=os.getenv("VIENEU_DEVICE", os.getenv("TTS_DEVICE", "auto")),
            stage_output_callback=_record_stage_output,
        )
    )

    task = asyncio.create_task(pipeline.run())
    last_log_line = ""
    while not task.done():
        if should_cancel():
            pipeline.request_cancel()
        state = pipeline.get_state()
        await state_callback(state)
        _save_job_metadata(job_id, state)
        log_line = _state_log_line(state)
        if log_line and log_line != last_log_line:
            storage_service.append_log(job_id, log_line)
            last_log_line = log_line
        await asyncio.sleep(0.5)

    result = await task
    final_state = pipeline.get_state()
    await state_callback(final_state)
    final_log_line = _state_log_line(final_state)
    if final_log_line and final_log_line != last_log_line:
        storage_service.append_log(job_id, final_log_line)
    safe_result = {
        "success": bool(result.get("success")),
        "output_path": result.get("output_path"),
        "chapter_epubs": result.get("chapter_epubs", []),
        "book_epub": result.get("book_epub"),
        "duration": result.get("duration", 0),
        "chapter_count": result.get("chapter_count", 0),
        "error": result.get("error"),
        "stage": result.get("stage"),
    }
    _save_job_metadata(job_id, {**pipeline.get_state(), "result": safe_result})

    if result.get("success"):
        output_path = result.get("output_path")
        if not output_path or not Path(output_path).exists():
            raise RuntimeError("Pipeline completed but output audio file is missing")
        storage_service.append_log(job_id, f"Completed: {output_path}")
    elif result.get("cancelled"):
        storage_service.append_log(job_id, "Cancelled")
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
    source_filename = Path(file.filename or "").name
    source_extension = Path(source_filename).suffix.lower()
    if not source_filename or source_extension not in SUPPORTED_INPUT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .epub, .pdf, and .txt uploads are supported")
    if output_format not in {"mp3", "wav"}:
        raise HTTPException(status_code=400, detail="output_format must be mp3 or wav")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > _max_upload_bytes():
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    job_id = str(uuid.uuid4())
    input_file = storage_service.save_input_file(job_id, content, filename=source_filename)
    output_dir = str(storage_service.job_dir(job_id) / "output")
    storage_service.save_metadata(
        job_id,
        {
            "source_filename": source_filename,
            "source_extension": source_extension,
            "detected_input_type": source_extension.lstrip("."),
            "output_format": output_format,
            "status": "pending",
        },
    )
    storage_service.append_log(job_id, f"Queued upload: {source_filename}")

    await queue_service.enqueue(
        "audiobook_generation",
        {
            "job_id": job_id,
            "input_file": input_file,
            "output_dir": output_dir,
            "source_filename": source_filename,
            "output_format": output_format,
            "normalize_audio": normalize_audio,
            "add_chapters": add_chapters,
            "analysis_enabled": analysis_enabled,
        },
        job_id=job_id,
    )
    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/jobs")
async def list_audiobook_jobs(limit: int = 50):
    limit = max(1, min(200, int(limit)))
    statuses = await queue_service.list_job_statuses(limit=limit)
    return {
        "jobs": [_attach_job_metadata(status) for status in statuses],
        "stats": queue_service.get_queue_stats(),
    }


@router.get("/jobs/{job_id}")
async def get_audiobook_job(job_id: str):
    status = await queue_service.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return _attach_job_metadata(status, include_logs=True)


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


@router.get("/jobs/{job_id}/epub/download")
async def download_book_epub(job_id: str):
    job = await queue_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    metadata = storage_service.load_metadata(job_id) or {}
    artifacts = metadata.get("artifacts", [])
    match = next((artifact for artifact in artifacts if artifact.get("type") == "book_epub"), None)
    if not match:
        result = (job.result or {}) or metadata.get("result") or {}
        match = result.get("book_epub") if isinstance(result.get("book_epub"), dict) else None
    if not match:
        raise HTTPException(status_code=404, detail="Book EPUB3 is not ready")

    epub_path = match.get("path")
    if not epub_path or not Path(epub_path).exists():
        raise HTTPException(status_code=404, detail="Book EPUB3 file not found")

    return FileResponse(
        epub_path,
        media_type="application/epub+zip",
        filename=Path(epub_path).name,
    )


@router.get("/jobs/{job_id}/chapters/{chapter_index}/download")
async def download_chapter_epub(job_id: str, chapter_index: int):
    job = await queue_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    metadata = storage_service.load_metadata(job_id) or {}
    artifacts = metadata.get("artifacts", [])
    match = next(
        (
            artifact
            for artifact in artifacts
            if artifact.get("type") == "chapter_epub"
            and int(artifact.get("chapter_index") or 0) == chapter_index
        ),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="Chapter EPUB is not ready")

    epub_path = match.get("path")
    if not epub_path or not Path(epub_path).exists():
        raise HTTPException(status_code=404, detail="Chapter EPUB file not found")

    return FileResponse(
        epub_path,
        media_type="application/epub+zip",
        filename=Path(epub_path).name,
    )


@router.delete("/jobs/{job_id}")
async def cancel_audiobook_job(job_id: str):
    success = await queue_service.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Only pending or running jobs can be cancelled")
    storage_service.append_log(job_id, "Cancellation requested")
    return {"job_id": job_id, "status": "cancelling"}
