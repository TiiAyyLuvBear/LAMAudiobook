"""
Audiobook HTTP routes.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
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
SUPPORTED_VOICE_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
VOICE_MODES = {"default", "system_voice", "upload_voice"}


def _tts_runtime_info() -> Dict[str, str]:
    engine = os.getenv("TTS_ENGINE", "xtts_gpu")
    device = os.getenv("VIENEU_DEVICE") or os.getenv("TTS_DEVICE", "auto")
    model = os.getenv("XTTS_MODEL_NAME_OR_PATH") or "aiMy144/XTTSv2VietAudiobook"
    lora_adapter = ""
    mode = ""
    codec_repo = ""
    codec_device = ""

    if engine.lower() in {"vieneu", "vieneu_tts", "direct_vieneu"}:
        model = os.getenv("VIENEU_MODEL_NAME", "pnnbao-ump/VieNeu-TTS-0.3B")
        device = os.getenv("VIENEU_DEVICE") or os.getenv("TTS_DEVICE", "auto")
        lora_adapter = os.getenv("VIENEU_LORA_ADAPTER", "")
        mode = os.getenv("VIENEU_MODE", "standard")
        codec_repo = os.getenv("VIENEU_CODEC_REPO") or (
            "neuphonic/neucodec"
            if os.getenv("VIENEU_ENABLE_VOICE_CLONING", "0").lower() in {"1", "true", "yes"}
            else "neuphonic/neucodec-onnx-decoder-int8"
        )
        codec_device = os.getenv("VIENEU_CODEC_DEVICE", "")
    elif engine.lower() in {"xtts", "xtts_gpu", "direct_xtts"}:
        device = os.getenv("XTTS_DEVICE") or os.getenv("TTS_DEVICE", "auto")

    return {
        "engine": engine,
        "model": model,
        "device": device,
        "mode": mode,
        "lora_adapter": lora_adapter,
        "codec_repo": codec_repo,
        "codec_device": codec_device,
    }


def _voice_samples_dir() -> Path:
    return Path(os.getenv("XTTS_VOICE_DIR", "data/voice_samples"))


def _is_temporary_voice_id(voice_id: str) -> bool:
    return Path(voice_id or "").stem.startswith("custom_")


def _sanitize_voice_id(value: str) -> str:
    voice_id = Path(value or "").stem.lower()
    voice_id = re.sub(r"[^a-z0-9_-]+", "_", voice_id).strip("_-")
    return voice_id


def _available_voice_ids() -> list[str]:
    voice_dir = _voice_samples_dir()
    if not voice_dir.exists():
        return []
    return sorted(
        path.stem
        for path in voice_dir.glob("*.wav")
        if path.is_file() and not _is_temporary_voice_id(path.stem)
    )


def _cleanup_uploaded_voice_sample(job_id: str, payload: Dict[str, Any]) -> None:
    if payload.get("voice_mode") != "upload_voice":
        return
    voice_id = payload.get("narrator_voice_override") or ""
    if not _is_temporary_voice_id(voice_id):
        return
    voice_path = Path(payload.get("uploaded_voice_path") or "")
    try:
        resolved_voice_path = voice_path.resolve()
        voice_dir = _voice_samples_dir().resolve()
    except OSError:
        return
    if not voice_path.is_file() or resolved_voice_path.parent != voice_dir:
        return
    try:
        voice_path.unlink()
        storage_service.append_log(job_id, f"Temporary uploaded voice removed from voice index: {voice_path.name}")
        _save_job_metadata(job_id, {"uploaded_voice_cleaned": True})
    except OSError as exc:
        storage_service.append_log(job_id, f"Warning: failed to remove temporary uploaded voice {voice_path.name}: {exc}")


def _voice_source_label(metadata: Dict[str, Any]) -> str:
    mode = metadata.get("voice_mode") or "default"
    if mode == "upload_voice":
        uploaded = metadata.get("uploaded_voice_filename")
        override = metadata.get("narrator_voice_override")
        processed = Path(metadata.get("uploaded_voice_path") or "").name
        parts = ["uploaded"]
        if uploaded:
            parts.append(f"source={uploaded}")
        if override:
            parts.append(f"voice_id={override}")
        if processed:
            parts.append(f"processed={processed}")
        return " | ".join(parts)
    if mode == "system_voice":
        selected = metadata.get("selected_voice_filename") or metadata.get("selected_voice_id") or metadata.get("narrator_voice_override")
        return f"system voice | source={selected or '-'}"
    return "auto-selected by system"


def _preprocess_voice_sample(input_path: Path, output_path: Path) -> Dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(
            status_code=400,
            detail="ffmpeg is required to preprocess uploaded voice samples",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_filter = (
        "highpass=f=80,"
        "lowpass=f=12000,"
        "afftdn=nf=-25,"
        "areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,"
        "areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,"
        "loudnorm=I=-20:TP=-2:LRA=11"
    )
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-af",
        audio_filter,
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
        return {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "sample_rate_hz": 24000,
            "channels": 1,
            "filters": [
                "highpass=f=80",
                "lowpass=f=12000",
                "afftdn=nf=-25",
                "silenceremove=start_threshold=-45dB:start_silence=0.2",
                "loudnorm=I=-20:TP=-2:LRA=11",
            ],
            "ffmpeg_filter": audio_filter,
            "output_size_bytes": output_path.stat().st_size if output_path.exists() else 0,
        }
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise HTTPException(status_code=400, detail=f"Voice preprocessing failed: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=400, detail="Voice preprocessing timed out") from exc


def _record_uploaded_voice_clean_outputs(
    job_id: str,
    raw_voice_path: Path,
    cleaned_voice_path: Path,
    voice_filename: str,
    voice_id: str,
    cleaning_info: Dict[str, Any],
) -> Dict[str, Any]:
    clean_dir = storage_service.stage_output_dir(job_id, "clean")
    audit_voice_path = clean_dir / "voice_cleaned_sample.wav"
    shutil.copy2(cleaned_voice_path, audit_voice_path)
    payload = {
        "kind": "uploaded_voice_cleaning",
        "source_filename": voice_filename,
        "voice_id": voice_id,
        "raw_voice_path": str(raw_voice_path),
        "temporary_voice_path": str(cleaned_voice_path),
        "clean_stage_voice_path": str(audit_voice_path),
        "noise_reduction": cleaning_info,
        "temporary_voice": True,
    }
    storage_service.save_stage_json(job_id, "clean", "voice_cleaning.json", payload)
    return payload


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
    job_status["tts_runtime"] = metadata.get("tts_runtime")
    job_status["voice_mode"] = metadata.get("voice_mode")
    job_status["narrator_voice_override"] = metadata.get("narrator_voice_override")
    job_status["uploaded_voice_path"] = metadata.get("uploaded_voice_path")
    job_status["uploaded_voice_filename"] = metadata.get("uploaded_voice_filename")
    job_status["uploaded_voice_cleaning"] = metadata.get("uploaded_voice_cleaning")
    job_status["selected_voice_id"] = metadata.get("selected_voice_id")
    job_status["selected_voice_filename"] = metadata.get("selected_voice_filename")
    job_status["voice_source"] = metadata.get("voice_source") or _voice_source_label(metadata)
    result_stats = result.get("pipeline_stats") if isinstance(result, dict) else None
    job_status["pipeline_stats"] = metadata.get("pipeline_stats") or result_stats
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
    chapter_segment = state.get("chapter_segment") or {}
    global_segment = state.get("global_segment") or {}
    chapter_segment_text = (
        f"{chapter_segment.get('current') or state.get('chapter_segment_current') or 0}/"
        f"{chapter_segment.get('total') or state.get('chapter_segment_total') or 0}"
    )
    global_segment_text = (
        f"{global_segment.get('current') or state.get('global_segment_current') or state.get('current_segment') or 0}/"
        f"{global_segment.get('total') or state.get('global_segment_total') or state.get('total_segments') or 0}"
    )
    progress = round(float(state.get("progress") or 0.0) * 100, 1)
    return (
        f"[{stage}] {progress}% | chapter {chapter} | "
        f"chapter_segment {chapter_segment_text} | global_segment {global_segment_text} | {message}"
    ).rstrip()


def _format_seconds(value: Any) -> str:
    try:
        seconds = float(value or 0.0)
    except (TypeError, ValueError):
        seconds = 0.0
    return f"{seconds:.2f}s"


def _build_pipeline_report(job_id: str) -> str:
    metadata = storage_service.load_metadata(job_id) or {}
    stats = metadata.get("pipeline_stats") or (metadata.get("result") or {}).get("pipeline_stats") or {}
    logs = storage_service.read_logs(job_id, max_lines=10000)
    book = stats.get("book") or {}
    execution = stats.get("execution") or {}
    tts = stats.get("tts") or metadata.get("tts_runtime") or {}
    voice_source = metadata.get("voice_source") or _voice_source_label(metadata)
    device = tts.get("device_diagnostics") or {}
    rtf_summary = tts.get("rtf_summary") or {}
    chapters = stats.get("chapters") or []
    segment_timings = tts.get("segment_timings") or []
    tts_warnings = tts.get("warnings") or []

    lines = [
        "Audiobook Pipeline Report",
        f"Job ID: {job_id}",
        "",
        "Book",
        f"- Source: {book.get('source_filename') or metadata.get('source_filename') or '-'}",
        f"- Format: {book.get('input_format') or metadata.get('source_extension') or '-'} -> {book.get('output_format') or metadata.get('output_format') or '-'}",
        f"- Title: {book.get('title') or '-'}",
        f"- Chapters: {book.get('chapter_count') or metadata.get('total_chapters') or 0}",
        f"- Sentences/segments: {book.get('sentence_count') or metadata.get('total_segments') or 0}",
        f"- Paragraphs: {book.get('paragraph_count') or 0}",
        f"- Words: {book.get('word_count') or 0}",
        f"- Characters: {book.get('character_count') or 0}",
        "",
        "TTS",
        f"- Engine: {tts.get('engine') or '-'}",
        f"- Model: {tts.get('model') or '-'}",
        f"- Requested device: {tts.get('requested_device') or device.get('requested_device') or '-'}",
        f"- Resolved device: {tts.get('device') or device.get('resolved_device') or '-'}",
        f"- CUDA available: {device.get('cuda_available')}",
        f"- CUDA device: {device.get('cuda_device_name') or '-'}",
        f"- Model device: {device.get('model_device') or '-'}",
        f"- Model dtype: {device.get('model_dtype') or '-'}",
        f"- LoRA adapter: {tts.get('lora_adapter') or '-'}",
        f"- Codec repo: {tts.get('codec_repo') or '-'}",
        f"- Codec device: {tts.get('codec_device') or '-'}",
        f"- Voice mode: {metadata.get('voice_mode') or '-'}",
        f"- Voice source: {voice_source}",
        f"- Narrator voice: {metadata.get('narrator_voice_override') or '-'}",
        f"- Uploaded voice cleaning: {(metadata.get('uploaded_voice_cleaning') or {}).get('clean_stage_voice_path') or '-'}",
        f"- Audio duration: {_format_seconds(tts.get('audio_duration_seconds') or (metadata.get('result') or {}).get('duration'))}",
        f"- Avg segment RTF: {rtf_summary.get('avg_segment_rtf') if rtf_summary.get('avg_segment_rtf') is not None else '-'}",
        f"- Max segment RTF: {rtf_summary.get('max_segment_rtf') if rtf_summary.get('max_segment_rtf') is not None else '-'}",
        "",
        "Execution",
        f"- Total wall time: {_format_seconds(execution.get('total_wall_seconds'))}",
    ]

    stage_seconds = execution.get("stage_wall_seconds") or {}
    for name, seconds in stage_seconds.items():
        lines.append(f"- {name}: {_format_seconds(seconds)}")

    lines.extend(["", "Chapters"])
    if chapters:
        for chapter in chapters:
            lines.append(
                "- "
                f"{chapter.get('chapter_index')}. {chapter.get('title') or '-'} | "
                f"segments={chapter.get('segment_count') or 0} | "
                f"words={chapter.get('word_count') or 0} | "
                f"audio={_format_seconds(chapter.get('audio_duration_seconds'))} | "
                f"tts_wall={_format_seconds(chapter.get('tts_wall_seconds'))} | "
                f"status={chapter.get('status') or '-'}"
            )
    else:
        lines.append("- No chapter timing data available.")

    lines.extend(["", "Slowest Segment"])
    slowest = rtf_summary.get("slowest_segment")
    if slowest:
        lines.append(
            "- "
            f"segment={slowest.get('segment_index')} | "
            f"chapter={slowest.get('chapter_index')} | "
            f"rtf={slowest.get('rtf')} | "
            f"tts_wall={_format_seconds(slowest.get('tts_wall_seconds'))} | "
            f"audio={_format_seconds(slowest.get('audio_duration_seconds'))} | "
            f"text={slowest.get('text_preview') or '-'}"
        )
    else:
        lines.append("- No segment timing data available.")

    if tts_warnings:
        lines.extend(["", "TTS Warnings"])
        for warning in tts_warnings:
            lines.append(f"- {warning}")

    if segment_timings:
        lines.extend(["", "Segment Timings"])
        for item in segment_timings[:100]:
            lines.append(
                "- "
                f"global={item.get('global_segment_index')}/{item.get('global_segment_total')} | "
                f"chapter={item.get('chapter_index')} "
                f"segment={item.get('chapter_segment_index')}/{item.get('chapter_segment_total')} | "
                f"rtf={item.get('rtf') if item.get('rtf') is not None else '-'} | "
                f"tts_wall={_format_seconds(item.get('tts_wall_seconds'))} | "
                f"audio={_format_seconds(item.get('audio_duration_seconds'))} | "
                f"status={item.get('status') or '-'}"
            )

    lines.extend(["", "Logs", logs or "-"])
    return "\n".join(lines).rstrip() + "\n"


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
            f"VIENEU_LORA_ADAPTER={os.getenv('VIENEU_LORA_ADAPTER') or ''}, "
            f"VIENEU_CODEC_REPO={os.getenv('VIENEU_CODEC_REPO') or ''}, "
            f"voice_mode={payload.get('voice_mode', 'default')}, "
            f"narrator_voice_override={payload.get('narrator_voice_override') or ''}, "
            f"voice_source={payload.get('voice_source') or ''}, "
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
            voice_mode=payload.get("voice_mode", "default"),
            narrator_voice_override=payload.get("narrator_voice_override"),
            xtts_model_name_or_path=os.getenv("XTTS_MODEL_NAME_OR_PATH") or None,
            xtts_config_path=os.getenv("XTTS_CONFIG_PATH") or None,
            xtts_vocab_path=os.getenv("XTTS_VOCAB_PATH") or None,
            xtts_voice_dir=os.getenv("XTTS_VOICE_DIR", "data/voice_samples"),
            vieneu_model_name=os.getenv("VIENEU_MODEL_NAME", "pnnbao-ump/VieNeu-TTS-0.3B"),
            vieneu_mode=os.getenv("VIENEU_MODE", "standard"),
            vieneu_emotion=os.getenv("VIENEU_EMOTION", "storytelling"),
            vieneu_api_base=os.getenv("VIENEU_API_BASE") or None,
            vieneu_device=os.getenv("VIENEU_DEVICE", os.getenv("TTS_DEVICE", "auto")),
            vieneu_lora_adapter=os.getenv("VIENEU_LORA_ADAPTER") or None,
            vieneu_codec_repo=os.getenv("VIENEU_CODEC_REPO") or None,
            vieneu_codec_device=os.getenv("VIENEU_CODEC_DEVICE") or None,
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
        "pipeline_stats": result.get("pipeline_stats"),
        "error": result.get("error"),
        "stage": result.get("stage"),
    }
    _save_job_metadata(
        job_id,
        {
            **pipeline.get_state(),
            "pipeline_stats": result.get("pipeline_stats"),
            "tts_runtime": (result.get("pipeline_stats") or {}).get("tts") or _tts_runtime_info(),
            "result": safe_result,
        },
    )

    if result.get("success"):
        output_path = result.get("output_path")
        if not output_path or not Path(output_path).exists():
            raise RuntimeError("Pipeline completed but output audio file is missing")
        for warning in ((result.get("pipeline_stats") or {}).get("tts") or {}).get("warnings", []) or []:
            storage_service.append_log(job_id, f"TTS warning: {warning}")
        storage_service.append_log(job_id, f"Completed: {output_path}")
    elif result.get("cancelled"):
        storage_service.append_log(job_id, "Cancelled")
    else:
        storage_service.append_log(job_id, f"Failed: {result.get('error')}")

    await progress_callback(1.0 if result.get("success") else pipeline.get_state().get("progress", 0), None)
    _cleanup_uploaded_voice_sample(job_id, payload)
    return safe_result


queue_service.register_handler("audiobook_generation", audiobook_generation_handler)


@router.post("/jobs", response_model=CreateJobResponse)
async def create_audiobook_job(
    file: UploadFile = File(...),
    voice_file: Optional[UploadFile] = File(None),
    output_format: str = "mp3",
    normalize_audio: bool = True,
    add_chapters: bool = True,
    analysis_enabled: bool = True,
    voice_mode: str = "default",
    selected_voice_id: Optional[str] = None,
):
    source_filename = Path(file.filename or "").name
    source_extension = Path(source_filename).suffix.lower()
    if not source_filename or source_extension not in SUPPORTED_INPUT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .epub, .pdf, and .txt uploads are supported")
    if output_format not in {"mp3", "wav"}:
        raise HTTPException(status_code=400, detail="output_format must be mp3 or wav")
    voice_mode = (voice_mode or "default").strip().lower()
    if voice_mode not in VOICE_MODES:
        raise HTTPException(status_code=400, detail="voice_mode must be default, system_voice, or upload_voice")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > _max_upload_bytes():
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    job_id = str(uuid.uuid4())
    input_file = storage_service.save_input_file(job_id, content, filename=source_filename)
    output_dir = str(storage_service.job_dir(job_id) / "output")
    narrator_voice_override = None
    uploaded_voice_path = None
    uploaded_voice_filename = None
    uploaded_voice_cleaning = None
    selected_voice_id_meta = None
    selected_voice_filename = None
    voice_dir = _voice_samples_dir()

    if voice_mode == "system_voice":
        narrator_voice_override = _sanitize_voice_id(selected_voice_id or "")
        if not narrator_voice_override:
            raise HTTPException(status_code=400, detail="selected_voice_id is required for system_voice mode")
        if _is_temporary_voice_id(narrator_voice_override):
            raise HTTPException(status_code=400, detail="Uploaded custom voices are temporary. Use upload_voice mode instead.")
        if narrator_voice_override not in _available_voice_ids():
            raise HTTPException(status_code=400, detail=f"Unknown voice sample: {narrator_voice_override}")
        selected_voice_id_meta = narrator_voice_override
        selected_voice_filename = f"{narrator_voice_override}.wav"
    elif voice_mode == "upload_voice":
        if voice_file is None:
            raise HTTPException(status_code=400, detail="voice_file is required for upload_voice mode")
        voice_filename = Path(voice_file.filename or "").name
        uploaded_voice_filename = voice_filename
        voice_extension = Path(voice_filename).suffix.lower()
        if voice_extension not in SUPPORTED_VOICE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Voice upload must be wav, mp3, m4a, aac, flac, or ogg")
        voice_content = await voice_file.read()
        if not voice_content:
            raise HTTPException(status_code=400, detail="Uploaded voice file is empty")
        if len(voice_content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Uploaded voice file is too large")

        raw_voice_dir = storage_service.job_dir(job_id) / "input" / "voice"
        raw_voice_dir.mkdir(parents=True, exist_ok=True)
        raw_voice_path = raw_voice_dir / f"raw{voice_extension}"
        raw_voice_path.write_bytes(voice_content)

        narrator_voice_override = f"custom_{job_id.replace('-', '')[:12]}"
        processed_voice_path = voice_dir / f"{narrator_voice_override}.wav"
        cleaning_info = _preprocess_voice_sample(raw_voice_path, processed_voice_path)
        uploaded_voice_path = str(processed_voice_path)
        uploaded_voice_cleaning = _record_uploaded_voice_clean_outputs(
            job_id=job_id,
            raw_voice_path=raw_voice_path,
            cleaned_voice_path=processed_voice_path,
            voice_filename=voice_filename,
            voice_id=narrator_voice_override,
            cleaning_info=cleaning_info,
        )

    voice_metadata = {
        "voice_mode": voice_mode,
        "narrator_voice_override": narrator_voice_override,
        "uploaded_voice_path": uploaded_voice_path,
        "uploaded_voice_filename": uploaded_voice_filename,
        "uploaded_voice_cleaning": uploaded_voice_cleaning,
        "selected_voice_id": selected_voice_id_meta,
        "selected_voice_filename": selected_voice_filename,
        "temporary_voice_id": narrator_voice_override if voice_mode == "upload_voice" else None,
    }
    voice_metadata["voice_source"] = _voice_source_label(voice_metadata)

    storage_service.save_metadata(
        job_id,
        {
            "source_filename": source_filename,
            "source_extension": source_extension,
            "detected_input_type": source_extension.lstrip("."),
            "output_format": output_format,
            "tts_runtime": _tts_runtime_info(),
            **voice_metadata,
            "status": "pending",
        },
    )
    storage_service.append_log(job_id, f"Queued upload: {source_filename}")
    storage_service.append_log(job_id, f"Voice source: {voice_metadata['voice_source']}")

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
            **voice_metadata,
        },
        job_id=job_id,
    )
    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/voices")
async def list_voice_samples():
    voice_dir = _voice_samples_dir()
    voices = [
        {
            "voice_id": path.stem,
            "filename": path.name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(voice_dir.glob("*.wav"))
        if path.is_file() and not _is_temporary_voice_id(path.stem)
    ] if voice_dir.exists() else []
    return {"voice_dir": str(voice_dir), "voices": voices}


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


@router.get("/jobs/{job_id}/report/download", response_class=PlainTextResponse)
async def download_audiobook_job_report(job_id: str):
    if not await queue_service.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return PlainTextResponse(
        _build_pipeline_report(job_id),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="pipeline_report_{job_id}.txt"'},
    )


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
