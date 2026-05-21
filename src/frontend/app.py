"""
Streamlit frontend for the audiobook service.
"""

from __future__ import annotations

import base64
import io
import os
import re
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


def _label(value: str | None) -> str:
    return STATUS_LABELS.get(value or "unknown", value or "-")


def _selected_status_value(label: str) -> str:
    reverse = {_label(value): value for value in STATUS_FILTERS}
    return reverse.get(label, "all")


def _display_value(value: str | None) -> str:
    value = (value or "").strip()
    return value if value else "-"


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


def render_tts_runtime(tts: dict | None) -> None:
    st.subheader("Cấu hình TTS")
    if not tts:
        st.caption("Chưa đọc được cấu hình TTS từ dịch vụ backend.")
        return

    st.metric("Bộ máy", _display_value(tts.get("engine")))
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
    if status == "running":
        container.info(label)
    elif status in {"pending", "queued"}:
        container.warning(label)
    elif status == "failed":
        container.error(label)
    elif status == "completed":
        container.success(label)
    else:
        container.caption(label)


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


def render_upload_tab(output_format: str, normalize_audio: bool, add_chapters: bool) -> None:
    st.markdown(
        """
        <div class="section-intro">
          <span class="section-kicker">Khởi tạo</span>
          <h2>Tạo sách nói mới</h2>
          <p>Tải sách lên, chọn kiểu giọng đọc và gửi tác vụ vào hàng đợi xử lý.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader("Chọn tệp EPUB, PDF hoặc TXT", type=["epub", "pdf", "txt"], key="book_upload")
    if not uploaded:
        st.info("Tải sách lên để bắt đầu tạo âm thanh và EPUB3 đồng bộ theo từng chương.")
        return

    size_mb = len(uploaded.getvalue()) / 1024 / 1024
    c1, c2 = st.columns([2.2, 1])
    c1.markdown(f"**Tệp nguồn**  \n`{uploaded.name}`")
    c2.metric("Dung lượng", f"{size_mb:.2f} MB")

    if size_mb > MAX_FILE_SIZE_MB:
        st.error(f"Tệp vượt quá giới hạn {MAX_FILE_SIZE_MB} MB.")
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
            selected_voice_id = st.selectbox("Chọn giọng kể", voices, index=0)
        else:
            st.warning("Chưa có tệp mẫu WAV trong thư mục giọng.")
            return
    elif voice_mode == "upload_voice":
        uploaded_voice = st.file_uploader(
            "Tải tệp giọng mẫu",
            type=["wav", "mp3", "m4a", "aac", "flac", "ogg"],
            key="uploaded_voice_sample",
        )
        if uploaded_voice:
            voice_size_mb = len(uploaded_voice.getvalue()) / 1024 / 1024
            st.caption(f"Tệp giọng: {uploaded_voice.name} | {voice_size_mb:.2f} MB")

    if st.button("Tạo sách nói", type="primary", width="stretch", key="create_audiobook_job"):
        if voice_mode == "upload_voice" and uploaded_voice is None:
            st.error("Hãy tải lên một tệp giọng mẫu trước khi tạo sách nói.")
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


def render_queue_tab(payload: dict, selected_status: str) -> list[dict]:
    jobs = payload.get("jobs") or []
    stats = payload.get("stats") or {}

    st.markdown(
        """
        <div class="section-intro">
          <span class="section-kicker">Giám sát</span>
          <h2>Hàng đợi xử lý</h2>
          <p>Theo dõi tiến độ, mở nhanh kết quả và hủy những tác vụ không còn cần thiết.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
        with st.container(border=True):
            top = st.columns([1.2, 1.2, 2.8, 1.0])
            if top[0].button(_short_id(job_id), key=f"select-{job_id}", width="stretch"):
                if st.session_state.get("job_id") != job_id:
                    _select_job(job_id)
                st.session_state["page_target"] = "Kết quả"
                st.session_state["_pending_page_target"] = "Kết quả"
                st.rerun()
            _status_badge(top[1], job.get("status", "unknown"))
            top[2].progress(_progress(job), text=job.get("status_message") or f"{_progress(job):.0%}")
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

            bottom = st.columns(4)
            total = int(job.get("total_chapters") or 0)
            current = int(job.get("current_chapter") or 0)
            global_segment = job.get("global_segment") or {}
            segment_total = int(global_segment.get("total") or job.get("total_segments") or 0)
            segment_current = int(global_segment.get("current") or job.get("current_segment") or 0)
            bottom[0].caption(f"Bước: {_label(job.get('stage') or job.get('status'))}")
            bottom[1].caption(f"Chương: {current}/{total}" if total else "Chương: -")
            bottom[2].caption(f"Câu tổng: {segment_current}/{segment_total}" if segment_total else "Câu tổng: -")
            bottom[3].caption(f"Tệp: {len(job.get('artifacts') or [])}")

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


def render_job_summary(job: dict) -> None:
    status = job.get("status", "unknown")
    stage = job.get("stage") or status
    st.subheader(f"Mã {_short_id(job.get('job_id', ''))}")
    render_stage(stage if stage in STAGES else status)
    st.progress(_progress(job), text=job.get("status_message") or f"{_label(status)} / {_label(stage)}")

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
    c4.metric("Câu tổng", f"{segment_current}/{segment_total}" if segment_total else "-")
    if chapter_segment_total:
        st.caption(f"Câu chương hiện tại: {chapter_segment_current}/{chapter_segment_total}")

    tts_runtime = job.get("tts_runtime")
    if tts_runtime:
        st.caption(_format_tts_runtime(tts_runtime))
        for warning in tts_runtime.get("warnings", []) or []:
            st.warning(f"TTS: {warning}")
    if job.get("voice_mode"):
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
        st.subheader("Thống kê quy trình")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Tổng thời gian", _format_seconds(execution.get("total_wall_seconds")))
        e2.metric("Số chương", book.get("chapter_count") or job.get("total_chapters") or "-")
        e3.metric("Số câu", book.get("sentence_count") or job.get("total_segments") or "-")
        e4.metric("Số từ", book.get("word_count") or "-")

        stage_seconds = execution.get("stage_wall_seconds") or {}
        if stage_seconds:
            st.caption(
                " | ".join(
                    f"{name}: {_format_seconds(seconds)}"
                    for name, seconds in stage_seconds.items()
                )
            )

        chapters = stats.get("chapters") or []
        if chapters:
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
        st.info("Kết quả sẽ xuất hiện khi tác vụ hoàn tất từng phần.")
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
        st.info("Âm thanh tổng sẽ xuất hiện khi bước hoàn thiện kết thúc.")

    epub_bytes = None
    book_epub = _book_epub(job)
    if book_epub:
        epub_response = download_job_epub(job["job_id"])
        if epub_response.ok:
            epub_bytes = epub_response.content
            epub_filename = Path(book_epub.get("path") or "audiobook.epub").name
            st.download_button(
                "Tải EPUB3 tổng",
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
        st.info("EPUB3 tổng sẽ xuất hiện sau khi các chương đã sinh xong.")

    chapter_epubs = _sorted_chapter_epubs(job)
    if chapter_epubs:
        st.caption(f"Đã sẵn sàng {len(chapter_epubs)} EPUB chương.")
        with st.expander("EPUB theo từng chương", expanded=True):
            for artifact in chapter_epubs:
                chapter_index = int(artifact.get("chapter_index") or 0)
                title = artifact.get("title") or f"Chương {chapter_index}"
                response = download_chapter_epub(job["job_id"], chapter_index)
                if response.ok:
                    st.download_button(
                        f"Chương {chapter_index}: {title}",
                        data=response.content,
                        file_name=Path(artifact.get("path") or f"chapter_{chapter_index:04d}.epub").name,
                        mime="application/epub+zip",
                        width="stretch",
                        key=f"chapter-epub-download-{job['job_id']}-{chapter_index}",
                    )
                else:
                    st.caption(f"Chương {chapter_index}: chưa tải được tệp.")
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
          padding: 0.25rem 0.5rem 2rem;
          color: #172033;
          font-family: "Segoe UI", Roboto, Arial, "Helvetica Neue", sans-serif;
          font-size: 18px;
          line-height: 1.78;
          letter-spacing: 0;
          text-rendering: optimizeLegibility;
          -webkit-font-smoothing: antialiased;
        }}
        h1, h2, h3 {{
          margin: 0 0 1rem;
          color: #101828;
          font-family: "Segoe UI", Roboto, Arial, "Helvetica Neue", sans-serif;
          font-weight: 750;
          line-height: 1.22;
          letter-spacing: 0;
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
    <body>{body}</body>
    </html>
    """
    return html_doc, audio


def render_epub_preview(epub_bytes: bytes | None, job: dict) -> None:
    job_id = job["job_id"]
    st.subheader("Xem trước EPUB3")
    preview_source = "book"
    chapter_options = _chapter_preview_options(job)
    if epub_bytes:
        if chapter_options and job.get("status") != "completed":
            st.caption("Đang xem EPUB chương đã hoàn tất. EPUB tổng sẽ thay thế khi sách hoàn tất.")
            preview_source = "chapter"
        else:
            st.caption("Đang xem EPUB3 tổng.")
    elif chapter_options:
        st.caption(f"Có thể xem trước {len(chapter_options)} chương đã sinh xong.")
        preview_source = "chapter"
    else:
        st.info("Chưa có EPUB chương nào để xem trước.")
        return

    try:
        if preview_source == "chapter":
            labels = [option["label"] for option in chapter_options]
            selected = st.selectbox("Chọn chương", labels, index=0, key=f"epub-preview-chapter-artifact-{job_id}")
            chapter_index = chapter_options[labels.index(selected)]["chapter_index"]
            response = download_chapter_epub(job_id, chapter_index)
            if not response.ok:
                st.warning("Chương này chưa tải được để xem trước.")
                return
            epub_bytes = response.content

        entries = _epub_chapter_entries(epub_bytes)
        if not entries:
            st.warning("Không tìm thấy nội dung XHTML trong EPUB3.")
            return
        labels = [title for title, _ in entries]
        if preview_source == "book":
            selected = st.selectbox("Chọn chương", labels, index=0, key=f"epub-preview-book-chapter-{job_id}")
            chapter_path = entries[labels.index(selected)][1]
        else:
            chapter_path = entries[0][1]
        html_doc, chapter_audio = _preview_html_from_epub(epub_bytes, chapter_path)
        if chapter_audio:
            data, mime = chapter_audio
            st.audio(data, format=mime)
        encoded_html = base64.b64encode(html_doc.encode("utf-8")).decode("ascii")
        st.iframe(f"data:text/html;base64,{encoded_html}", width="stretch", height=620)
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
        render_queue_tab(queue_payload, selected_status)
    elif page == "Kết quả":
        if not job:
            st.info("Chọn một tác vụ trong mục Theo dõi hoặc nhập mã tác vụ ở thanh bên.")
        else:
            st.caption(f"Kết quả của tác vụ: {job['job_id']}")
            render_job_summary(job)
            st.divider()
            left, right = st.columns([0.9, 1.4])
            with left:
                epub_bytes = render_downloads(job)
            with right:
                render_epub_preview(epub_bytes, job)
    elif page == "Nhật ký":
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
          padding-top: 2rem;
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
        div[data-testid="stAlert"] {
          border-radius: 14px;
          border-width: 1px;
        }
        div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"] div[data-testid="stButton"] > button,
        div[data-testid="stDownloadButton"] > button {
          border-radius: 12px;
        }
        div[role="radiogroup"] label {
          border-radius: 999px !important;
        }
        .stTabs [data-baseweb="tab-list"] {
          gap: 0.5rem;
        }
        .stCodeBlock, .stDataFrame, div[data-testid="stExpander"] {
          border-radius: 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="AI Sách nói", page_icon="🎧", layout="wide")
    apply_style()
    st.markdown(
        f"""
        <div class="app-hero">
          <h1>Audiobook Generation System </h1>
          <p>Giao diện điều phối quy trình chuyển sách thành sách nói, theo dõi tiến độ xử lý và xem trước EPUB3 có âm thanh ngay trong một màn hình.</p>
          <div class="hero-meta">Máy chủ đang kết nối: {API_BASE_URL}</div>
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
        st.header("Thiết lập xử lý")
        render_tts_runtime((health_payload or {}).get("tts"))
        st.divider()
        output_format = st.selectbox("Định dạng âm thanh đầu ra", ["mp3", "wav"], index=0)
        normalize_audio = st.checkbox("Chuẩn hóa âm lượng", value=True)
        add_chapters = st.checkbox("Thêm mốc chương", value=True)
        st.divider()
        st.header("Theo dõi tác vụ")
        status_label = st.selectbox("Lọc trạng thái", [_label(value) for value in STATUS_FILTERS], index=0)
        selected_status = _selected_status_value(status_label)
        auto_refresh = st.checkbox("Tự làm mới", value=True)
        refresh_seconds = st.number_input("Chu kỳ làm mới (giây)", min_value=1, max_value=30, value=2)
        st.divider()
        remembered = st.text_input("Mã tác vụ đang theo dõi", key="job_id_input")
        remembered_job_id = remembered.strip()
        if remembered_job_id != selected_job_id:
            _select_job(remembered_job_id)
            st.session_state["_job_id_input_synced"] = remembered_job_id
            st.rerun()

    page_options = ["Tạo sách nói", "Theo dõi", "Kết quả", "Nhật ký"]
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
        render_page_content(page, output_format, normalize_audio, add_chapters, selected_status)

    with page_host.container():
        page_fragment()


if __name__ == "__main__":
    main()
