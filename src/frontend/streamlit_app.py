"""
Streamlit frontend for the audiobook service.
"""

from __future__ import annotations

import base64
import io
import os
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import requests
import streamlit as st
from bs4 import BeautifulSoup, NavigableString
from dotenv import load_dotenv


load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

STAGES = ["queued", "running", "parsing", "cleaning", "analyzing", "generating", "finalizing", "cancelling", "completed", "failed"]
STATUS_FILTERS = ["all", "pending", "running", "failed", "completed", "cancelled"]
STATUS_LABELS = {
    "all": "Tất cả",
    "pending": "Đang chờ",
    "queued": "Đang chờ",
    "running": "Đang chạy",
    "parsing": "Đọc sách",
    "cleaning": "Làm sạch",
    "analyzing": "Phân tích",
    "generating": "Sinh giọng",
    "finalizing": "Hoàn thiện",
    "cancelling": "Đang hủy",
    "completed": "Hoàn tất",
    "failed": "Lỗi",
    "cancelled": "Đã hủy",
    "unknown": "Không rõ",
}
VOICE_MODE_LABELS = {
    "default": "Hệ thống tự chọn",
    "system_voice": "Chọn giọng có sẵn",
    "upload_voice": "Tải giọng riêng",
}
UPLOAD_MIME_TYPES = {
    ".epub": "application/epub+zip",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}
EPUB_AUDIO_LIMIT_BYTES = 35 * 1024 * 1024


def is_debug_mode() -> bool:
    args = {arg.strip().lower() for arg in sys.argv[1:]}
    env_value = os.getenv("STREAMLIT_DEBUG", "").strip().lower()
    return bool(args.intersection({"-debug", "--debug"}) or env_value in {"1", "true", "yes", "on"})


def _select_job(job_id: str) -> None:
    next_job_id = job_id.strip()
    previous_job_id = (st.session_state.get("job_id") or "").strip()
    if next_job_id != previous_job_id:
        for key in list(st.session_state.keys()):
            if str(key).startswith(("epub-preview-", "result-panel-", "logs-panel-", "audio-download-", "book-epub-download-", "report-download-", "chapter-epub-download-")):
                del st.session_state[key]
    st.session_state["job_id"] = next_job_id


def _clear_page_ui_state() -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith(
            (
                "epub-preview-",
                "result-panel-",
                "logs-panel-",
                "audio-download-",
                "book-epub-download-",
                "report-download-",
                "chapter-epub-download-",
            )
        ):
            del st.session_state[key]


def api_url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


def create_job(
    uploaded_file,
    output_format: str,
    normalize_audio: bool,
    add_chapters: bool,
    voice_mode: str = "default",
    selected_voice_id: str | None = None,
    uploaded_voice_file=None,
) -> dict:
    suffix = Path(uploaded_file.name).suffix.lower()
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            UPLOAD_MIME_TYPES.get(suffix, "application/octet-stream"),
        )
    }
    if uploaded_voice_file is not None:
        files["voice_file"] = (
            uploaded_voice_file.name,
            uploaded_voice_file.getvalue(),
            "application/octet-stream",
        )
    params = {
        "output_format": output_format,
        "normalize_audio": normalize_audio,
        "add_chapters": add_chapters,
        "analysis_enabled": True,
        "voice_mode": voice_mode,
    }
    if selected_voice_id:
        params["selected_voice_id"] = selected_voice_id
    response = requests.post(api_url("/api/v1/audiobook/jobs"), files=files, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def get_job(job_id: str) -> dict:
    response = requests.get(api_url(f"/api/v1/audiobook/jobs/{job_id}"), timeout=60)
    response.raise_for_status()
    return response.json()


def list_jobs(limit: int = 50) -> dict:
    response = requests.get(api_url("/api/v1/audiobook/jobs"), params={"limit": limit}, timeout=60)
    response.raise_for_status()
    return response.json()


def get_health() -> dict:
    response = requests.get(api_url("/health"), timeout=10)
    response.raise_for_status()
    return response.json()


def list_voice_samples() -> dict:
    response = requests.get(api_url("/api/v1/audiobook/voices"), timeout=20)
    response.raise_for_status()
    return response.json()


def cancel_job(job_id: str) -> dict:
    response = requests.delete(api_url(f"/api/v1/audiobook/jobs/{job_id}"), timeout=60)
    response.raise_for_status()
    return response.json()


def download_job_audio(job_id: str) -> requests.Response:
    return requests.get(api_url(f"/api/v1/audiobook/jobs/{job_id}/download"), timeout=60)


def download_job_epub(job_id: str) -> requests.Response:
    return requests.get(api_url(f"/api/v1/audiobook/jobs/{job_id}/epub/download"), timeout=60)


def download_chapter_epub(job_id: str, chapter_index: int) -> requests.Response:
    return requests.get(api_url(f"/api/v1/audiobook/jobs/{job_id}/chapters/{chapter_index}/download"), timeout=60)


def download_job_report(job_id: str) -> requests.Response:
    return requests.get(api_url(f"/api/v1/audiobook/jobs/{job_id}/report/download"), timeout=60)


def _short_id(job_id: str) -> str:
    return job_id[:8]


def _job_display_name(job: dict) -> str:
    filename = _display_value(job.get("source_filename"))
    if filename != "-":
        return filename
    return f"Tác vụ {_short_id(job.get('job_id', ''))}"


def _label(value: str | None) -> str:
    return STATUS_LABELS.get(value or "unknown", value or "-")


def _selected_status_value(label: str) -> str:
    reverse = {_label(value): value for value in STATUS_FILTERS}
    return reverse.get(label, "all")


def _display_value(value: str | None) -> str:
    value = (value or "").strip()
    return value if value else "-"


def _status_text(job: dict, fallback: str) -> str:
    raw = (job.get("status_message") or "").strip()
    if not raw:
        return fallback

    normalized = raw.lower()
    simple_messages = {
        "cancelled": "Đã hủy",
        "cancelled before execution": "Đã hủy trước khi xử lý",
        "cancellation requested. waiting for the current step to stop.": "Đã yêu cầu hủy, đang chờ bước hiện tại dừng lại.",
    }
    if normalized in simple_messages:
        return simple_messages[normalized]

    match = re.match(r"^(mp3|wav) audiobook ready:\s*(.+)$", raw, re.IGNORECASE)
    if match:
        return "Audiobook đã hoàn thành"

    match = re.match(r"^audiobook ready:\s*(.+)$", raw, re.IGNORECASE)
    if match:
        return "Audiobook đã hoàn thành"

    match = re.match(r"^generating tts segment\s+(\d+)/(\d+)\s+\(global\s+(\d+)/(\d+)\)$", raw, re.IGNORECASE)
    if match:
        total = int(job.get("total_chapters") or 0)
        current = int(job.get("current_chapter") or 0)
        return f"Đang thực hiện tới chương {current}/{total}" if total else "Đang thực hiện"

    match = re.match(r"^preparing tts for\s+(\d+)\s+segments across\s+(\d+)\s+chapters$", raw, re.IGNORECASE)
    if match:
        return "Đang chuẩn bị sinh giọng"

    match = re.match(r"^generating chapter\s+(\d+)/(\d+)\s+(?:with\s+(\d+)\s+segments|\((\d+)\s+segments?\))$", raw, re.IGNORECASE)
    if match:
        current, total, _segments_a, _segments_b = match.groups()
        return f"Đang thực hiện tới chương {current}/{total}"

    match = re.match(r"^chapter\s+(\d+)/(\d+)\s+epub ready:\s*(.+)$", raw, re.IGNORECASE)
    if match:
        current, total, filename = match.groups()
        return f"EPUB chương {current}/{total} đã sẵn sàng: {filename}"

    match = re.match(r"^book epub3 artifact ready:\s*(.+)$", raw, re.IGNORECASE)
    if match:
        return f"EPUB3 tổng đã sẵn sàng: {match.group(1)}"

    return raw


def _voice_source_text(job: dict) -> str:
    source = _display_value(job.get("voice_source"))
    if source != "-":
        return source
    mode = job.get("voice_mode")
    if mode == "upload_voice":
        uploaded = _display_value(job.get("uploaded_voice_filename"))
        narrator = _display_value(job.get("narrator_voice_override"))
        return f"Tệp mẫu: {uploaded} | Mã giọng: {narrator}"
    if mode == "system_voice":
        selected = _display_value(job.get("selected_voice_filename") or job.get("selected_voice_id"))
        return f"Giọng đã chọn: {selected}"
    return "hệ thống tự chọn"


def _format_seconds(value) -> str:
    try:
        seconds = float(value or 0.0)
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds >= 3600:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}g {minutes}p"
    if seconds >= 60:
        minutes = int(seconds // 60)
        remain = seconds % 60
        return f"{minutes}p {remain:.0f}s"
    return f"{seconds:.1f}s"


def _format_tts_runtime(tts: dict | None) -> str:
    if not tts:
        return "TTS: -"
    device_info = tts.get("device_diagnostics") or {}
    parts = [
        f"Bộ máy: {_display_value(tts.get('engine'))}",
        f"Mô hình: {_display_value(tts.get('model'))}",
        f"Thiết bị: {_display_value(tts.get('device') or device_info.get('resolved_device'))}",
    ]
    if tts.get("lora_adapter"):
        parts.append(f"LoRA: {tts['lora_adapter']}")
    if tts.get("codec_repo"):
        parts.append(f"Bộ mã hóa: {tts['codec_repo']}")
    return " | ".join(parts)


def render_tts_runtime(tts: dict | None, debug: bool = False) -> None:
    st.subheader("Trạng thái đọc")
    if not tts:
        st.caption("Chưa kết nối được dịch vụ đọc.")
        return

    st.metric("Bộ đọc", _display_value(tts.get("engine")))
    if not debug:
        st.caption("Hệ thống tự chọn cấu hình phù hợp cho sách nói.")
        return

    st.caption(f"Mô hình: {_display_value(tts.get('model'))}")
    device_info = tts.get("device_diagnostics") or {}
    st.caption(f"Thiết bị: {_display_value(tts.get('device') or device_info.get('resolved_device'))}")
    if device_info:
        st.caption(f"CUDA: {_display_value(str(device_info.get('cuda_available')))} | GPU: {_display_value(device_info.get('cuda_device_name'))}")
    if tts.get("mode"):
        st.caption(f"Chế độ: {tts['mode']}")
    if tts.get("lora_adapter"):
        st.caption(f"LoRA: {tts['lora_adapter']}")
    if tts.get("codec_repo"):
        st.caption(f"Bộ mã hóa: {tts['codec_repo']}")


def _status_badge(container, status: str) -> None:
    label = _label(status)
    badge_class = {
        "running": "status-running",
        "pending": "status-pending",
        "queued": "status-pending",
        "failed": "status-failed",
        "completed": "status-completed",
        "cancelled": "status-cancelled",
        "cancelling": "status-cancelled",
    }.get(status, "status-muted")
    container.markdown(
        f'<div class="queue-status-badge {badge_class}">{label}</div>',
        unsafe_allow_html=True,
    )


def _progress(job: dict) -> float:
    return min(1.0, max(0.0, float(job.get("progress") or 0.0)))


def render_stage(stage: str) -> None:
    compact_stages = ["parsing", "cleaning", "analyzing", "generating", "finalizing", "completed"]
    active = compact_stages.index(stage) if stage in compact_stages else 0
    cols = st.columns(len(compact_stages))
    for index, name in enumerate(compact_stages):
        if index < active:
            cols[index].success(_label(name))
        elif index == active:
            cols[index].info(_label(name))
        else:
            cols[index].caption(_label(name))


def render_section_header(title: str, kicker: str | None = None, compact: bool = False) -> None:
    compact_class = " section-heading-compact" if compact else ""
    kicker_html = f'<span class="section-kicker">{kicker}</span>' if kicker else ""
    st.markdown(
        f"""
        <div class="section-heading{compact_class}">
          {kicker_html}
          <h2>{title}</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_upload_tab(output_format: str, normalize_audio: bool, add_chapters: bool) -> None:
    # render_section_header("Tạo sách nói mới")
    uploaded = st.file_uploader("Chọn tệp EPUB, PDF hoặc TXT", type=["epub", "pdf", "txt"], key="book_upload")
    if not uploaded:
        st.info("Tải sách lên để bắt đầu tạo Audiobook.")
        return

    size_mb = len(uploaded.getvalue()) / 1024 / 1024
    safe_filename = uploaded.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    st.markdown(
        f"""
        <div class="upload-summary-grid">
          <div class="upload-summary-card upload-file-card">
            <div class="upload-summary-label">File đã tải</div>
            <div class="upload-summary-value upload-file-name">{safe_filename}</div>
          </div>
          <div class="upload-summary-card">
            <div class="upload-summary-label">Dung lượng</div>
            <div class="upload-summary-value">{size_mb:.2f} MB</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if size_mb > MAX_FILE_SIZE_MB:
        st.error(f"File vượt quá giới hạn {MAX_FILE_SIZE_MB} MB.")
        return

    voice_mode_label = st.radio(
        "Giọng đọc",
        list(VOICE_MODE_LABELS.values()),
        horizontal=True,
        key="voice_mode",
    )
    voice_mode = {label: key for key, label in VOICE_MODE_LABELS.items()}[voice_mode_label]
    selected_voice_id = None
    uploaded_voice = None

    if voice_mode == "system_voice":
        try:
            voice_payload = list_voice_samples()
            voices = [item.get("voice_id") for item in voice_payload.get("voices", []) if item.get("voice_id")]
        except requests.RequestException as exc:
            voices = []
            st.warning(f"Không đọc được danh sách giọng: {exc}")
        if voices:
            selected_voice_id = st.selectbox("", voices, index=0)
        else:
            st.warning("Chưa có tệp mẫu WAV trong thư mục giọng.")
            return
    elif voice_mode == "upload_voice":
        uploaded_voice = st.file_uploader(
            "Tải file giọng tham chiếu",
            type=["wav", "mp3", "m4a", "aac", "flac", "ogg"],
            key="uploaded_voice_sample",
        )
        if uploaded_voice:
            voice_size_mb = len(uploaded_voice.getvalue()) / 1024 / 1024
            st.caption(f"Tệp giọng: {uploaded_voice.name} | {voice_size_mb:.2f} MB")

    if st.button("Tạo sách nói", type="primary", width="stretch", key="create_audiobook_job"):
        if voice_mode == "upload_voice" and uploaded_voice is None:
            st.error("Hãy tải lên một file giọng mẫu trước khi tạo sách nói.")
            return
        try:
            created = create_job(
                uploaded,
                output_format,
                normalize_audio,
                add_chapters,
                voice_mode=voice_mode,
                selected_voice_id=selected_voice_id,
                uploaded_voice_file=uploaded_voice,
            )
            _select_job(created["job_id"])
            st.session_state["job_created_message"] = f"Đã đưa vào hàng đợi: {created['job_id']}"
            st.rerun()
        except requests.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            st.error(f"Không tải được tệp: {detail}")
        except requests.RequestException as exc:
            st.error(f"Không kết nối được máy chủ: {exc}")


def render_queue_tab(payload: dict, selected_status: str, debug: bool = False) -> list[dict]:
    jobs = payload.get("jobs") or []
    stats = payload.get("stats") or {}

    render_section_header("Trạng thái")

    cols = st.columns(5)
    cols[0].metric("Đang chạy", stats.get("running", 0))
    cols[1].metric("Đang chờ", stats.get("pending", 0))
    cols[2].metric("Hoàn tất", stats.get("completed", 0))
    cols[3].metric("Lỗi", stats.get("failed", 0))
    cols[4].metric("Đã hủy", stats.get("cancelled", 0))

    if selected_status != "all":
        jobs = [job for job in jobs if job.get("status") == selected_status]

    if not jobs:
        st.info("Không có tác vụ phù hợp với bộ lọc.")
        return []

    st.divider()
    for job in jobs:
        job_id = job.get("job_id", "")
        with st.container(border=True, key=f"queue-card-{job_id}"):
            top = st.columns([2.0, 1.0, 2.6, 1.0])
            display_name = _job_display_name(job)
            if top[0].button(display_name, key=f"select-{job_id}", width="stretch"):
                if st.session_state.get("job_id") != job_id:
                    _select_job(job_id)
                st.session_state["page_target"] = "Kết quả"
                st.session_state["_pending_page_target"] = "Kết quả"
                st.rerun()
            if debug:
                top[0].caption(f"Mã: {_short_id(job_id)}")
            _status_badge(top[1], job.get("status", "unknown"))
            top[2].progress(_progress(job), text=_status_text(job, f"{_progress(job):.0%}"))
            if job.get("cancel_requested"):
                top[3].caption("Đang hủy")
            elif job.get("status") in {"pending", "running"}:
                if top[3].button("Hủy", key=f"cancel-row-{job_id}", width="stretch"):
                    cancel_job(job_id)
                    if st.session_state.get("job_id") != job_id:
                        _select_job(job_id)
                    st.rerun()
            else:
                top[3].caption("-")

            total = int(job.get("total_chapters") or 0)
            current = int(job.get("current_chapter") or 0)
            global_segment = job.get("global_segment") or {}
            segment_total = int(global_segment.get("total") or job.get("total_segments") or 0)
            segment_current = int(global_segment.get("current") or job.get("current_segment") or 0)
            if debug:
                bottom = st.columns(4)
                bottom[0].caption(f"Bước: {_label(job.get('stage') or job.get('status'))}")
                bottom[1].caption(f"Chương: {current}/{total}" if total else "Chương: -")
                bottom[2].caption(f"Tổng số câu: {segment_current}/{segment_total}" if segment_total else "Câu tổng: -")
                bottom[3].caption(f"Tệp: {len(job.get('artifacts') or [])}")
            else:
                st.caption(f"Đã xử lý {current}/{total} chương" if total else _label(job.get('stage') or job.get('status')))

    return jobs


def _chapter_epubs(job: dict) -> list[dict]:
    return [artifact for artifact in (job.get("artifacts") or []) if artifact.get("type") == "chapter_epub"]


def _sorted_chapter_epubs(job: dict) -> list[dict]:
    return sorted(_chapter_epubs(job), key=lambda item: int(item.get("chapter_index") or 0))


def _book_epub(job: dict) -> dict | None:
    result = job.get("result") or {}
    if isinstance(result.get("book_epub"), dict):
        return result["book_epub"]
    for artifact in job.get("artifacts") or []:
        if artifact.get("type") == "book_epub":
            return artifact
    return None


def render_job_summary(job: dict, debug: bool = False) -> None:
    status = job.get("status", "unknown")
    stage = job.get("stage") or status
    if debug:
        st.subheader(f"Mã {_short_id(job.get('job_id', ''))}")
        render_stage(stage if stage in STAGES else status)
        st.progress(_progress(job), text=_status_text(job, f"{_label(status)} / {_label(stage)}"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trạng thái", _label(status))
    c2.metric("Bước", _label(stage))
    total = int(job.get("total_chapters") or 0)
    current = int(job.get("current_chapter") or 0)
    c3.metric("Chương", f"{current}/{total}" if total else "-")
    chapter_segment = job.get("chapter_segment") or {}
    global_segment = job.get("global_segment") or {}
    segment_total = int(global_segment.get("total") or job.get("total_segments") or 0)
    segment_current = int(global_segment.get("current") or job.get("current_segment") or 0)
    chapter_segment_total = int(chapter_segment.get("total") or 0)
    chapter_segment_current = int(chapter_segment.get("current") or 0)
    c4.metric("Tổng số câu", f"{segment_current}/{segment_total}" if segment_total else "-")
    if debug and chapter_segment_total:
        st.caption(f"Đã xử lý: {chapter_segment_current}/{chapter_segment_total} của chương hiện tại")

    tts_runtime = job.get("tts_runtime")
    if debug and tts_runtime:
        st.caption(_format_tts_runtime(tts_runtime))
        for warning in tts_runtime.get("warnings", []) or []:
            st.warning(f"TTS: {warning}")
    if debug and job.get("voice_mode"):
        voice_label = VOICE_MODE_LABELS.get(job.get("voice_mode"), job.get("voice_mode"))
        st.caption(
            f"Giọng đọc: {voice_label} | Giọng kể: {_display_value(job.get('narrator_voice_override'))}"
        )
        st.caption(f"Nguồn giọng: {_voice_source_text(job)}")

    stats = job.get("pipeline_stats") or {}
    execution = stats.get("execution") or {}
    book = stats.get("book") or {}
    if stats:
        st.divider()
        st.subheader("Tổng quan" if not debug else "Thống kê quy trình")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Tổng thời gian", _format_seconds(execution.get("total_wall_seconds")))
        e2.metric("Số chương", book.get("chapter_count") or job.get("total_chapters") or "-")
        e3.metric("Số câu", book.get("sentence_count") or job.get("total_segments") or "-")
        e4.metric("Số từ", book.get("word_count") or "-")

        stage_seconds = execution.get("stage_wall_seconds") or {}
        if debug and stage_seconds:
            st.caption(
                " | ".join(
                    f"{name}: {_format_seconds(seconds)}"
                    for name, seconds in stage_seconds.items()
                )
            )

        chapters = stats.get("chapters") or []
        if debug and chapters:
            rows = [
                {
                    "Chương": chapter.get("chapter_index"),
                    "Tiêu đề": chapter.get("title"),
                    "Câu": chapter.get("segment_count"),
                    "Từ": chapter.get("word_count"),
                    "Audio": _format_seconds(chapter.get("audio_duration_seconds")),
                    "Thực thi TTS": _format_seconds(chapter.get("tts_wall_seconds")),
                    "Trạng thái": chapter.get("status"),
                }
                for chapter in chapters
            ]
            st.dataframe(rows, width="stretch", hide_index=True)

    if job.get("cancel_requested"):
        st.warning("Đã yêu cầu hủy. Quy trình sẽ dừng ở điểm an toàn gần nhất.")
    elif status in {"pending", "running"}:
        if st.button("Hủy tác vụ", type="secondary", width="stretch", key=f"cancel-detail-{job['job_id']}"):
            try:
                cancel_job(job["job_id"])
                st.warning("Đã gửi yêu cầu hủy.")
                st.rerun()
            except requests.HTTPError as exc:
                detail = exc.response.text if exc.response is not None else str(exc)
                st.error(f"Hủy thất bại: {detail}")
            except requests.RequestException as exc:
                st.error(f"Không kết nối được máy chủ: {exc}")

    if job.get("error"):
        st.error(job["error"])


def _audio_mime(filename: str) -> str:
    return "audio/mpeg" if filename.lower().endswith(".mp3") else "audio/wav"


def render_downloads(job: dict) -> bytes | None:
    result = job.get("result") or {}
    has_partial_outputs = bool(_chapter_epubs(job) or _book_epub(job))
    if job.get("status") != "completed" and not has_partial_outputs:
        return None

    if job.get("status") == "completed":
        audio_response = download_job_audio(job["job_id"])
        if audio_response.ok:
            filename = Path(result.get("output_path") or "audiobook.mp3").name
            mime = _audio_mime(filename)
            st.audio(audio_response.content, format=mime)
            st.download_button(
                "Tải âm thanh",
                data=audio_response.content,
                file_name=filename,
                mime=mime,
                width="stretch",
                key=f"audio-download-{job['job_id']}",
            )
        else:
            st.warning("Tác vụ đã hoàn tất nhưng chưa tìm thấy tệp âm thanh.")
    elif has_partial_outputs:
        pass

    epub_bytes = None
    book_epub = _book_epub(job)
    if book_epub:
        epub_response = download_job_epub(job["job_id"])
        if epub_response.ok:
            epub_bytes = epub_response.content
            epub_filename = Path(book_epub.get("path") or "audiobook.epub").name
            st.download_button(
                "Tải Audiobook",
                data=epub_bytes,
                file_name=epub_filename,
                mime="application/epub+zip",
                width="stretch",
                key=f"book-epub-download-{job['job_id']}",
            )
        else:
            st.warning("Đã có thông tin EPUB3 tổng nhưng chưa tải được tệp.")
    elif job.get("status") == "completed":
        epub_response = download_job_epub(job["job_id"])
        if epub_response.ok:
            epub_bytes = epub_response.content
            book_epub = result.get("book_epub") or {}
            epub_filename = Path(book_epub.get("path") or "audiobook.epub").name
            st.download_button(
                "Tải EPUB3 tổng",
                data=epub_bytes,
                file_name=epub_filename,
                mime="application/epub+zip",
                width="stretch",
                key=f"book-epub-download-fallback-{job['job_id']}",
            )
    else:
        pass

    return epub_bytes


def _chapter_preview_options(job: dict) -> list[dict]:
    options = []
    for artifact in _sorted_chapter_epubs(job):
        chapter_index = int(artifact.get("chapter_index") or 0)
        if not chapter_index:
            continue
        title = artifact.get("title") or f"Chương {chapter_index}"
        options.append(
            {
                "label": f"Chương {chapter_index}: {title}",
                "chapter_index": chapter_index,
            }
        )
    return options


def _epub_chapter_entries(epub_bytes: bytes) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(epub_bytes)) as zf:
        names = [name for name in zf.namelist() if name.lower().endswith((".xhtml", ".html"))]
        names = [name for name in names if not name.lower().endswith("nav.xhtml")]
        names = sorted(names, key=lambda value: ("chapter" not in value.lower(), value))
        for name in names:
            soup = BeautifulSoup(zf.read(name), "html.parser")
            title_node = soup.find(["h1", "title"])
            title = title_node.get_text(" ", strip=True) if title_node else Path(name).stem
            entries.append((unicodedata.normalize("NFC", title or Path(name).stem), name))
    return entries


def _normalize_soup_text(soup: BeautifulSoup) -> None:
    for node in soup.find_all(string=True):
        if isinstance(node, NavigableString):
            normalized = unicodedata.normalize("NFC", str(node))
            if normalized != str(node):
                node.replace_with(normalized)


def _chapter_audio_from_epub(zf: zipfile.ZipFile, soup: BeautifulSoup, chapter_path: str) -> tuple[bytes, str] | None:
    audio_node = soup.find("audio", id="chapter-player") or soup.find("audio", attrs={"src": True})
    if not audio_node or not audio_node.get("src"):
        return None
    src = audio_node.get("src", "")
    base = Path(chapter_path).parent
    audio_path = str((base / src).as_posix()) if str(base) != "." else src
    audio_path = re.sub(r"^/+", "", audio_path)
    if audio_path not in zf.namelist():
        return None
    info = zf.getinfo(audio_path)
    if info.file_size > EPUB_AUDIO_LIMIT_BYTES:
        return None
    data = zf.read(audio_path)
    mime = "audio/wav" if audio_path.lower().endswith(".wav") else "audio/mpeg"
    return data, mime


def _preview_html_from_epub(epub_bytes: bytes, chapter_path: str) -> tuple[str, tuple[bytes, str] | None]:
    with zipfile.ZipFile(io.BytesIO(epub_bytes)) as zf:
        soup = BeautifulSoup(zf.read(chapter_path), "html.parser")
        _normalize_soup_text(soup)
        audio = _chapter_audio_from_epub(zf, soup, chapter_path)
        for tag in soup.find_all(["script", "audio"]):
            tag.decompose()
        for tag in soup.find_all(class_=re.compile("audio|player", re.IGNORECASE)):
            tag.decompose()
        for tag in soup.find_all("a"):
            tag.name = "span"
            tag.attrs = {"class": "sentence"}
        body = soup.body.decode_contents() if soup.body else str(soup)
        body = unicodedata.normalize("NFC", body)
    html_doc = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        :root {{ color-scheme: light; }}
        body {{
          margin: 0;
          padding: 0.75rem 0.5rem 2rem;
          color: #172033;
          background: transparent;
          font-family: "Segoe UI", Roboto, Arial, "Helvetica Neue", sans-serif;
          font-size: 18px;
          line-height: 1.78;
          letter-spacing: 0;
          text-rendering: optimizeLegibility;
          -webkit-font-smoothing: antialiased;
        }}
        .reader-shell {{
          max-width: 78ch;
          margin: 0 auto;
          padding: 1.45rem 1.55rem 2rem;
          border: 1px solid #dfd4c2;
          border-radius: 16px;
          background: rgba(255, 253, 248, 0.96);
          box-shadow: 0 18px 42px rgba(31, 41, 55, 0.09);
        }}
        h1, h2, h3 {{
          margin: 0 0 1rem;
          color: #0f172a;
          font-family: "Segoe UI", Roboto, Arial, "Helvetica Neue", sans-serif;
          font-weight: 760;
          line-height: 1.18;
          letter-spacing: 0;
        }}
        h1 {{
          padding-bottom: 0.75rem;
          border-bottom: 1px solid rgba(223, 212, 194, 0.95);
          font-size: 2.35rem;
        }}
        p {{
          max-width: 72ch;
          margin: 0 0 1rem;
        }}
        .sentence {{
          border-bottom: 1px dotted #c5cad3;
          text-decoration: none;
        }}
      </style>
    </head>
    <body><main class="reader-shell">{body}</main></body>
    </html>
    """
    return html_doc, audio


def _chapter_artifact_by_index(job: dict, chapter_index: int) -> dict | None:
    for artifact in _sorted_chapter_epubs(job):
        if int(artifact.get("chapter_index") or 0) == chapter_index:
            return artifact
    return None


def _render_selected_chapter_download(job_id: str, chapter_index: int, artifact: dict | None, data: bytes | None = None) -> None:
    if not artifact and data is None:
        st.button(
            "Tải",
            icon=":material/download:",
            disabled=True,
            width="stretch",
            help="Chưa có tệp chương để tải",
            key=f"chapter-download-disabled-{job_id}-{chapter_index}",
        )
        return

    if data is None:
        response = download_chapter_epub(job_id, chapter_index)
        if not response.ok:
            st.button(
                "Tải",
                icon=":material/download:",
                disabled=True,
                width="stretch",
                help="Chưa tải được chương này",
                key=f"chapter-download-unavailable-{job_id}-{chapter_index}",
            )
            return
        data = response.content

    filename = Path((artifact or {}).get("path") or f"chapter_{chapter_index:04d}.epub").name
    st.download_button(
        "Tải",
        data=data,
        file_name=filename,
        mime="application/epub+zip",
        icon=":material/download:",
        width="stretch",
        help="Tải audiobook của chương đang chọn",
        on_click="ignore",
        key=f"chapter-epub-download-{job_id}-{chapter_index}",
    )


def render_epub_preview(epub_bytes: bytes | None, job: dict) -> None:
    job_id = job["job_id"]
    render_section_header("Xem trước EPUB3", "Xem trước", compact=True)
    preview_source = "book"
    chapter_options = _chapter_preview_options(job)
    if epub_bytes:
        if chapter_options and job.get("status") != "completed":
            # st.caption("Đang xem EPUB chương đã hoàn tất. EPUB tổng sẽ thay thế khi sách hoàn tất.")
            preview_source = "chapter"
        else:
            pass
            # st.caption("Đang xem EPUB3 tổng.")
    elif chapter_options:
        st.caption(f"Có thể xem trước {len(chapter_options)} chương đã sinh xong.")
        preview_source = "chapter"
    else:
        return

    try:
        selected_chapter_index = 0
        selected_artifact = None
        selected_chapter_data = None

        if preview_source == "chapter":
            labels = [option["label"] for option in chapter_options]
            selector_col, download_col = st.columns([0.88, 0.12], vertical_alignment="bottom")
            with selector_col:
                selected = st.selectbox("Chọn chương", labels, index=0, key=f"epub-preview-chapter-artifact-{job_id}")
            selected_chapter_index = chapter_options[labels.index(selected)]["chapter_index"]
            selected_artifact = _chapter_artifact_by_index(job, selected_chapter_index)
            response = download_chapter_epub(job_id, selected_chapter_index)
            if not response.ok:
                with download_col:
                    _render_selected_chapter_download(job_id, selected_chapter_index, selected_artifact)
                st.warning("Chương này chưa tải được để xem trước.")
                return
            selected_chapter_data = response.content
            with download_col:
                _render_selected_chapter_download(job_id, selected_chapter_index, selected_artifact, selected_chapter_data)
            epub_bytes = selected_chapter_data

        entries = _epub_chapter_entries(epub_bytes)
        if not entries:
            st.warning("Không tìm thấy nội dung XHTML trong EPUB3.")
            return
        labels = [title for title, _ in entries]
        if preview_source == "book":
            selector_col, download_col = st.columns([0.88, 0.12], vertical_alignment="bottom")
            with selector_col:
                selected = st.selectbox("Chọn chương", labels, index=0, key=f"epub-preview-book-chapter-{job_id}")
            selected_entry_index = labels.index(selected)
            chapter_path = entries[selected_entry_index][1]
            selected_chapter_index = selected_entry_index + 1
            selected_artifact = _chapter_artifact_by_index(job, selected_chapter_index)
            with download_col:
                _render_selected_chapter_download(job_id, selected_chapter_index, selected_artifact)
        else:
            chapter_path = entries[0][1]
        html_doc, chapter_audio = _preview_html_from_epub(epub_bytes, chapter_path)
        if chapter_audio:
            data, mime = chapter_audio
            st.audio(data, format=mime)
        encoded_html = base64.b64encode(html_doc.encode("utf-8")).decode("ascii")
        st.iframe(f"data:text/html;base64,{encoded_html}", width="stretch", height=720)
    except zipfile.BadZipFile:
        st.warning("Tệp EPUB3 không đọc được.")
    except Exception as exc:
        st.warning(f"Không xem trước được EPUB3: {exc}")


def render_logs_tab(job: dict | None) -> None:
    if not job:
        st.info("Chọn một tác vụ để xem nhật ký.")
        return
    job_id = job["job_id"]
    st.caption(f"Nhật ký của tác vụ: {job_id}")
    report_response = download_job_report(job_id)
    if report_response.ok:
        st.download_button(
            "Tải nhật ký và thống kê quy trình",
            data=report_response.content,
            file_name=f"pipeline_report_{job_id}.txt",
            mime="text/plain",
            width="stretch",
            key=f"report-download-{job_id}",
        )
    else:
        st.warning("Chưa tải được report thống kê.")

    logs = job.get("logs") or ""
    if logs:
        st.code(logs, language="", height=520, wrap_lines=True)
    else:
        st.info("Chưa có nhật ký.")


def render_page_content(
    page: str,
    output_format: str,
    normalize_audio: bool,
    add_chapters: bool,
    selected_status: str,
    debug: bool = False,
) -> None:
    try:
        queue_payload = list_jobs()
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        st.error(f"Không đọc được hàng đợi: {detail}")
        return
    except requests.RequestException as exc:
        st.error(f"Không kết nối được máy chủ: {exc}")
        return

    job = None
    job_id = (st.session_state.get("job_id") or "").strip()
    if job_id:
        try:
            job = get_job(job_id)
        except requests.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            st.error(f"Không đọc được tác vụ: {detail}")
        except requests.RequestException as exc:
            st.error(f"Không kết nối được máy chủ: {exc}")

    if page == "Tạo sách nói":
        render_upload_tab(output_format, normalize_audio, add_chapters)
    elif page == "Theo dõi":
        render_queue_tab(queue_payload, selected_status, debug=debug)
    elif page == "Kết quả":
        if not job:
            st.info("Chọn một tác vụ trong mục Theo dõi hoặc nhập mã tác vụ ở thanh bên.")
        else:
            if debug:
                st.caption(f"Kết quả của tác vụ: {job['job_id']}")
            render_job_summary(job, debug=debug)
            preview_available = bool(_chapter_preview_options(job) or _book_epub(job))
            if preview_available:
                st.divider()
                left, right = st.columns([0.68, 1.82], gap="large")
                with left:
                    epub_bytes = render_downloads(job)
                with right:
                    render_epub_preview(epub_bytes, job)
            else:
                epub_bytes = render_downloads(job)
                if epub_bytes:
                    st.divider()
                    render_epub_preview(epub_bytes, job)
    elif page == "Nhật ký" and debug:
        render_logs_tab(job)


def apply_style() -> None:
    st.markdown(
        """
        <style>
        :root {
          --bg: #f4efe7;
          --surface: rgba(255, 252, 246, 0.92);
          --surface-strong: #fffdf8;
          --line: #dfd4c2;
          --ink: #1f2937;
          --muted: #6b7280;
          --accent: #0f766e;
          --accent-soft: rgba(15, 118, 110, 0.10);
          --warm: #c2410c;
          --shadow: 0 18px 48px rgba(31, 41, 55, 0.08);
        }
        .stApp {
          background:
            radial-gradient(circle at top left, rgba(194, 65, 12, 0.09), transparent 24%),
            radial-gradient(circle at top right, rgba(15, 118, 110, 0.12), transparent 26%),
            linear-gradient(180deg, #f8f4ec 0%, #f4efe7 46%, #efe7da 100%);
          color: var(--ink);
        }
        .block-container {
          padding-top: 3.25rem;
          padding-bottom: 2.5rem;
          max-width: 1180px;
        }
        section[data-testid="stSidebar"] {
          background: linear-gradient(180deg, #f8f2e8 0%, #f2e9dc 100%);
          border-right: 1px solid rgba(146, 64, 14, 0.08);
        }
        .app-hero {
          padding: 1.35rem 1.4rem;
          border: 1px solid var(--line);
          border-radius: 20px;
          background:
            linear-gradient(135deg, rgba(255,255,255,0.94), rgba(255,248,240,0.90)),
            linear-gradient(135deg, rgba(15,118,110,0.06), rgba(194,65,12,0.07));
          box-shadow: var(--shadow);
          margin-bottom: 1rem;
        }
        .app-hero h1 {
          margin: 0;
          font-size: 2rem;
          line-height: 1.15;
          color: #102a27;
        }
        .app-hero p {
          margin: 0.55rem 0 0;
          max-width: 70ch;
          color: var(--muted);
          font-size: 0.98rem;
        }
        .hero-meta {
          margin-top: 0.85rem;
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.38rem 0.7rem;
          border-radius: 999px;
          background: var(--accent-soft);
          color: #115e59;
          font-size: 0.88rem;
          font-weight: 600;
        }
        .section-intro {
          margin-bottom: 0.8rem;
        }
        .section-intro h2 {
          margin: 0.15rem 0 0.35rem;
          font-size: 1.42rem;
          color: #172033;
        }
        .section-intro p {
          margin: 0;
          color: var(--muted);
        }
        .section-heading {
          width: 100%;
          margin: 0 0 1rem;
          padding: 0.9rem 1rem 0.95rem;
          border-left: 5px solid var(--accent);
          border-radius: 12px;
          background: rgba(255, 253, 248, 0.78);
          box-shadow: 0 12px 30px rgba(31, 41, 55, 0.055);
        }
        .section-heading h2 {
          margin: 0.35rem 0 0;
          color: #0f172a;
          font-size: 1.58rem;
          line-height: 1.16;
          letter-spacing: 0;
        }
        .section-heading-compact {
          margin-bottom: 0.85rem;
          padding: 0.82rem 1rem 0.9rem;
        }
        .section-heading-compact h2 {
          font-size: 2rem;
        }
        .section-kicker {
          display: inline-block;
          padding: 0.28rem 0.58rem;
          border-radius: 999px;
          background: rgba(194, 65, 12, 0.11);
          color: var(--warm);
          font-size: 0.76rem;
          font-weight: 700;
          letter-spacing: 0.04em;
          text-transform: uppercase;
        }
        div[data-testid="stMetric"] {
          background: var(--surface);
          border: 1px solid var(--line);
          padding: 0.8rem;
          border-radius: 14px;
          box-shadow: 0 10px 26px rgba(31, 41, 55, 0.04);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
          background: rgba(255, 253, 248, 0.97) !important;
          border: 1px solid rgba(199, 181, 153, 0.98) !important;
          border-radius: 14px !important;
          box-shadow: 0 15px 36px rgba(31, 41, 55, 0.09) !important;
          transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease, background-color 140ms ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
          transform: translateY(-1px);
          background: rgba(255, 255, 255, 0.99) !important;
          border-color: rgba(15, 118, 110, 0.32) !important;
          box-shadow: 0 20px 46px rgba(31, 41, 55, 0.14) !important;
        }
        .queue-status-badge {
          min-height: 3.35rem;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 10px;
          padding: 0.45rem 0.7rem;
          font-size: 1rem;
          font-weight: 650;
          text-align: center;
          line-height: 1.2;
        }
        .queue-status-badge.status-failed {
          background: #f8ded7;
          color: #b91c1c;
        }
        .queue-status-badge.status-completed {
          background: #dcebd4;
          color: #047857;
        }
        .queue-status-badge.status-cancelled {
          background: #f8e7b8;
          color: #92400e;
        }
        .queue-status-badge.status-pending {
          background: #f8e7b8;
          color: #92400e;
        }
        .queue-status-badge.status-running {
          background: #dbeafe;
          color: #075985;
        }
        .queue-status-badge.status-muted {
          background: #ebe6dd;
          color: #6b7280;
        }
        div[data-testid="stFileUploader"] {
          width: fit-content;
          max-width: 100%;
        }
        div[data-testid="stFileUploader"] section,
        div[data-testid="stFileUploaderDropzone"] {
          width: fit-content !important;
          min-width: 18.5rem !important;
          max-width: 100%;
          min-height: 4.25rem !important;
          padding: 0.45rem 0.7rem !important;
          align-items: center;
        }
        div[data-testid="stFileUploader"] section > div,
        div[data-testid="stFileUploaderDropzone"] > div {
          padding: 0 !important;
        }
        .upload-summary-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 1rem;
          margin: 0.95rem 0 1.05rem;
        }
        .upload-summary-card {
          min-height: 7.15rem;
          display: flex;
          flex-direction: column;
          justify-content: center;
          border: 1px solid var(--line);
          border-radius: 14px;
          background: var(--surface);
          box-shadow: 0 10px 26px rgba(31, 41, 55, 0.04);
          padding: 1rem 1.1rem;
          overflow: hidden;
        }
        .upload-summary-label {
          color: #172033;
          font-size: 1rem;
          line-height: 1.25;
          margin-bottom: 0.7rem;
        }
        .upload-summary-value {
          color: #303240;
          font-size: 2.35rem;
          line-height: 1.05;
          font-weight: 500;
          letter-spacing: 0;
        }
        .upload-file-card {
          align-items: flex-start;
        }
        .upload-file-name {
          max-width: 100%;
          color: #047857;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
          font-size: clamp(1.35rem, 2.4vw, 2.15rem);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          background: rgba(248, 250, 252, 0.72);
          padding: 0.15rem 0.45rem;
          border-radius: 4px;
        }
        @media (max-width: 760px) {
          .upload-summary-grid {
            grid-template-columns: 1fr;
          }
          .upload-summary-card {
            min-height: 6.7rem;
          }
          .upload-summary-value {
            font-size: 2rem;
          }
        }
        div[data-testid="stAlert"] {
          border-radius: 14px;
          border-width: 1px;
        }
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
          border: 1px solid var(--line);
          border-radius: 12px;
          background: rgba(255, 253, 248, 0.94);
          box-shadow: 0 10px 24px rgba(31, 41, 55, 0.045);
        }
        audio {
          width: 100%;
          border: 1px solid rgba(223, 212, 194, 0.8);
          border-radius: 999px;
          box-shadow: 0 10px 24px rgba(31, 41, 55, 0.045);
        }
        div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"] div[data-testid="stButton"] > button,
        div[data-testid="stDownloadButton"] > button {
          border-radius: 12px;
        }
        div[role="radiogroup"] {
          gap: 0.55rem;
        }
        div[role="radiogroup"] label {
          min-height: 2.35rem;
          padding: 0.32rem 0.78rem 0.32rem 0.42rem !important;
          border: 1px solid rgba(223, 212, 194, 0.95) !important;
          border-radius: 999px !important;
          background: rgba(255, 253, 248, 0.78) !important;
          box-shadow: 0 8px 18px rgba(31, 41, 55, 0.055);
          transition: transform 140ms ease, box-shadow 140ms ease, background-color 140ms ease, border-color 140ms ease;
        }
        div[role="radiogroup"] label:hover {
          transform: translateY(-1px);
          border-color: rgba(15, 118, 110, 0.34) !important;
          background: rgba(255, 255, 255, 0.94) !important;
          box-shadow: 0 12px 26px rgba(31, 41, 55, 0.10);
        }
        div[role="radiogroup"] label:active {
          transform: translateY(0) scale(0.985);
          box-shadow: 0 5px 14px rgba(31, 41, 55, 0.09);
        }
        div[role="radiogroup"] label:has(input:checked) {
          border-color: rgba(255, 82, 82, 0.36) !important;
          background: rgba(255, 82, 82, 0.11) !important;
          box-shadow: 0 12px 28px rgba(255, 82, 82, 0.16);
          color: #111827 !important;
          font-weight: 700;
        }
        div[role="radiogroup"] label:has(input:checked) [data-testid="stMarkdownContainer"] p {
          color: #111827 !important;
          font-weight: 700;
        }
        .stTabs [data-baseweb="tab-list"] {
          gap: 0.5rem;
        }
        .stTabs [data-baseweb="tab"] {
          border-radius: 999px;
          background: rgba(255, 253, 248, 0.62);
          border: 1px solid rgba(223, 212, 194, 0.9);
          padding: 0.35rem 0.8rem;
          font-weight: 650;
        }
        .stTabs [aria-selected="true"] {
          background: var(--accent-soft);
          color: #115e59;
          border-color: rgba(15, 118, 110, 0.24);
        }
        .stCodeBlock, .stDataFrame, div[data-testid="stExpander"] {
          border-radius: 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    debug = is_debug_mode()
    st.set_page_config(page_title="LAMAudiobook", page_icon="🎧", layout="wide")
    apply_style()
    st.markdown(
        f"""
        <div class="app-hero">
          <h1>LAMAudiobook - Hệ thống tạo sách nói tự động</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )
    created_message = st.session_state.pop("job_created_message", None)
    if created_message:
        st.success(created_message)

    health_payload = None
    try:
        health_payload = get_health()
    except requests.RequestException:
        health_payload = None

    selected_job_id = (st.session_state.get("job_id") or "").strip()
    if st.session_state.get("_job_id_input_synced") != selected_job_id:
        st.session_state["job_id_input"] = selected_job_id
        st.session_state["_job_id_input_synced"] = selected_job_id

    with st.sidebar:
        st.header("Tùy chọn")
        if debug:
            render_tts_runtime((health_payload or {}).get("tts"), debug=True)
            st.divider()
        output_format = st.selectbox("Định dạng âm thanh đầu ra", ["mp3", "wav"], index=0)
        normalize_audio = st.checkbox("Chuẩn hóa âm lượng", value=True)
        add_chapters = st.checkbox("Thêm mốc chương", value=True)
        st.divider()
        st.header("Theo dõi tác vụ")
        status_label = st.selectbox("Lọc trạng thái", [_label(value) for value in STATUS_FILTERS], index=0)
        selected_status = _selected_status_value(status_label)
        auto_refresh = st.checkbox("Tự làm mới", value=True)
        if debug:
            refresh_seconds = st.number_input("Chu kỳ làm mới (giây)", min_value=1, max_value=30, value=2)
        else:
            refresh_seconds = 2
        st.divider()
        remembered = st.text_input("Tra cứu phiên làm việc", key="job_id_input")
        remembered_job_id = remembered.strip()
        if remembered_job_id != selected_job_id:
            _select_job(remembered_job_id)
            st.session_state["_job_id_input_synced"] = remembered_job_id
            st.rerun()

    page_options = ["Tạo sách nói", "Theo dõi", "Kết quả"]
    if debug:
        page_options.append("Nhật ký")
    if "page_target" not in st.session_state:
        st.session_state["page_target"] = page_options[0]
    if st.session_state["page_target"] not in page_options:
        st.session_state["page_target"] = page_options[0]
    pending_page = st.session_state.pop("_pending_page_target", None)
    if pending_page in page_options:
        st.session_state["page_target"] = pending_page
        st.session_state["main_page_widget"] = pending_page
    elif st.session_state.get("main_page_widget") not in page_options:
        st.session_state["main_page_widget"] = st.session_state["page_target"]

    page = st.radio(
        "Trang",
        page_options,
        index=page_options.index(st.session_state["page_target"]),
        horizontal=True,
        label_visibility="collapsed",
        key="main_page_widget",
    )
    previous_page = st.session_state.get("_active_page")
    if previous_page != page:
        st.session_state["page_target"] = page
        st.session_state["_active_page"] = page
        _clear_page_ui_state()

    st.session_state["page_target"] = page
    page_host = st.empty()
    fragment_options = {}
    if auto_refresh and page != "Tạo sách nói":
        fragment_options["run_every"] = f"{max(1, int(refresh_seconds))}s"

    @st.fragment(**fragment_options)
    def page_fragment() -> None:
        render_page_content(page, output_format, normalize_audio, add_chapters, selected_status, debug=debug)

    with page_host.container():
        page_fragment()


if __name__ == "__main__":
    main()
