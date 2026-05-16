"""
Streamlit frontend for the audiobook service.
"""

from __future__ import annotations

import io
import os
import re
import time
import zipfile
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup
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
UPLOAD_MIME_TYPES = {
    ".epub": "application/epub+zip",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}
EPUB_AUDIO_LIMIT_BYTES = 35 * 1024 * 1024


def api_url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


def create_job(uploaded_file, output_format: str, normalize_audio: bool, add_chapters: bool) -> dict:
    suffix = Path(uploaded_file.name).suffix.lower()
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            UPLOAD_MIME_TYPES.get(suffix, "application/octet-stream"),
        )
    }
    params = {
        "output_format": output_format,
        "normalize_audio": normalize_audio,
        "add_chapters": add_chapters,
        "analysis_enabled": True,
    }
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


def cancel_job(job_id: str) -> dict:
    response = requests.delete(api_url(f"/api/v1/audiobook/jobs/{job_id}"), timeout=60)
    response.raise_for_status()
    return response.json()


def download_job_audio(job_id: str) -> requests.Response:
    return requests.get(api_url(f"/api/v1/audiobook/jobs/{job_id}/download"), timeout=60)


def download_job_epub(job_id: str) -> requests.Response:
    return requests.get(api_url(f"/api/v1/audiobook/jobs/{job_id}/epub/download"), timeout=60)


def _short_id(job_id: str) -> str:
    return job_id[:8]


def _label(value: str | None) -> str:
    return STATUS_LABELS.get(value or "unknown", value or "-")


def _selected_status_value(label: str) -> str:
    reverse = {_label(value): value for value in STATUS_FILTERS}
    return reverse.get(label, "all")


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
    st.subheader("Tạo sách nói mới")
    uploaded = st.file_uploader("Chọn tệp EPUB, PDF hoặc TXT", type=["epub", "pdf", "txt"])
    if not uploaded:
        st.info("Tải sách lên để bắt đầu tạo tệp âm thanh và EPUB3 có âm thanh.")
        return

    size_mb = len(uploaded.getvalue()) / 1024 / 1024
    c1, c2 = st.columns([2, 1])
    c1.write(uploaded.name)
    c2.write(f"{size_mb:.2f} MB")

    if size_mb > MAX_FILE_SIZE_MB:
        st.error(f"Tệp vượt quá giới hạn {MAX_FILE_SIZE_MB} MB.")
        return

    if st.button("Tạo sách nói", type="primary", use_container_width=True):
        try:
            created = create_job(uploaded, output_format, normalize_audio, add_chapters)
            st.session_state["job_id"] = created["job_id"]
            st.success(f"Đã đưa vào hàng đợi: {created['job_id']}")
        except requests.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            st.error(f"Không tải được tệp: {detail}")
        except requests.RequestException as exc:
            st.error(f"Không kết nối được máy chủ: {exc}")


def render_queue_tab(payload: dict, selected_status: str) -> list[dict]:
    jobs = payload.get("jobs") or []
    stats = payload.get("stats") or {}

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
            if top[0].button(_short_id(job_id), key=f"select-{job_id}", use_container_width=True):
                st.session_state["job_id"] = job_id
                st.rerun()
            _status_badge(top[1], job.get("status", "unknown"))
            top[2].progress(_progress(job), text=job.get("status_message") or f"{_progress(job):.0%}")
            if job.get("cancel_requested"):
                top[3].caption("Đang hủy")
            elif job.get("status") in {"pending", "running"}:
                if top[3].button("Hủy", key=f"cancel-row-{job_id}", use_container_width=True):
                    cancel_job(job_id)
                    st.session_state["job_id"] = job_id
                    st.rerun()
            else:
                top[3].caption("-")

            bottom = st.columns(4)
            total = int(job.get("total_chapters") or 0)
            current = int(job.get("current_chapter") or 0)
            segment_total = int(job.get("total_segments") or 0)
            segment_current = int(job.get("current_segment") or 0)
            bottom[0].caption(f"Bước: {_label(job.get('stage') or job.get('status'))}")
            bottom[1].caption(f"Chương: {current}/{total}" if total else "Chương: -")
            bottom[2].caption(f"Câu: {segment_current}/{segment_total}" if segment_total else "Câu: -")
            bottom[3].caption(f"Tệp: {len(job.get('artifacts') or [])}")

    return jobs


def _chapter_epubs(job: dict) -> list[dict]:
    return [artifact for artifact in (job.get("artifacts") or []) if artifact.get("type") == "chapter_epub"]


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
    segment_total = int(job.get("total_segments") or 0)
    segment_current = int(job.get("current_segment") or 0)
    c4.metric("Câu", f"{segment_current}/{segment_total}" if segment_total else "-")

    if job.get("cancel_requested"):
        st.warning("Đã yêu cầu hủy. Quy trình sẽ dừng ở điểm an toàn gần nhất.")
    elif status in {"pending", "running"}:
        if st.button("Hủy tác vụ", type="secondary", use_container_width=True, key=f"cancel-detail-{job['job_id']}"):
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
    if job.get("status") != "completed":
        st.info("Kết quả sẽ xuất hiện khi tác vụ hoàn tất.")
        return None

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
            use_container_width=True,
        )
    else:
        st.warning("Tác vụ đã hoàn tất nhưng chưa tìm thấy tệp âm thanh.")

    epub_bytes = None
    epub_response = download_job_epub(job["job_id"])
    if epub_response.ok:
        epub_bytes = epub_response.content
        book_epub = result.get("book_epub") or {}
        epub_filename = Path(book_epub.get("path") or "audiobook.epub").name
        st.download_button(
            "Tải EPUB3",
            data=epub_bytes,
            file_name=epub_filename,
            mime="application/epub+zip",
            use_container_width=True,
        )
    else:
        artifacts = job.get("artifacts") or []
        if any(artifact.get("type") == "book_epub" for artifact in artifacts) or result.get("book_epub"):
            st.warning("Tác vụ đã hoàn tất nhưng chưa tìm thấy tệp EPUB3.")

    chapter_epubs = _chapter_epubs(job)
    if chapter_epubs:
        with st.expander("EPUB theo từng chương", expanded=False):
            for artifact in sorted(chapter_epubs, key=lambda item: int(item.get("chapter_index") or 0)):
                chapter_index = int(artifact.get("chapter_index") or 0)
                title = artifact.get("title") or f"Chương {chapter_index}"
                response = requests.get(
                    api_url(f"/api/v1/audiobook/jobs/{job['job_id']}/chapters/{chapter_index}/download"),
                    timeout=60,
                )
                if response.ok:
                    st.download_button(
                        f"Chương {chapter_index}: {title}",
                        data=response.content,
                        file_name=Path(artifact.get("path") or f"chapter_{chapter_index:04d}.epub").name,
                        mime="application/epub+zip",
                        use_container_width=True,
                    )
    return epub_bytes


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
            entries.append((title or Path(name).stem, name))
    return entries


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
        audio = _chapter_audio_from_epub(zf, soup, chapter_path)
        for tag in soup.find_all(["script", "audio"]):
            tag.decompose()
        for tag in soup.find_all(class_=re.compile("audio|player", re.IGNORECASE)):
            tag.decompose()
        for tag in soup.find_all("a"):
            tag.name = "span"
            tag.attrs = {"class": "sentence"}
        body = soup.body.decode_contents() if soup.body else str(soup)
    html_doc = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        body {{ font-family: ui-serif, Georgia, serif; line-height: 1.7; color: #202124; padding: 0 0.25rem; }}
        h1, h2, h3 {{ font-family: ui-sans-serif, system-ui, sans-serif; line-height: 1.25; }}
        p {{ margin: 0 0 0.85rem; }}
        .sentence {{ border-bottom: 1px dotted #b8b8b8; }}
      </style>
    </head>
    <body>{body}</body>
    </html>
    """
    return html_doc, audio


def render_epub_preview(epub_bytes: bytes | None) -> None:
    st.subheader("Xem EPUB3")
    if not epub_bytes:
        st.info("Chưa có EPUB3 để xem trực tiếp.")
        return
    try:
        entries = _epub_chapter_entries(epub_bytes)
        if not entries:
            st.warning("Không tìm thấy nội dung XHTML trong EPUB3.")
            return
        labels = [title for title, _ in entries]
        selected = st.selectbox("Chọn chương", labels, index=0)
        chapter_path = entries[labels.index(selected)][1]
        html_doc, chapter_audio = _preview_html_from_epub(epub_bytes, chapter_path)
        if chapter_audio:
            data, mime = chapter_audio
            st.audio(data, format=mime)
        components.html(html_doc, height=620, scrolling=True)
    except zipfile.BadZipFile:
        st.warning("Tệp EPUB3 không đọc được.")
    except Exception as exc:
        st.warning(f"Không xem trước được EPUB3: {exc}")


def render_logs_tab(job: dict | None) -> None:
    if not job:
        st.info("Chọn một tác vụ để xem nhật ký.")
        return
    logs = job.get("logs") or ""
    if logs:
        st.code(logs, language="")
    else:
        st.info("Chưa có nhật ký.")


def apply_style() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2rem; max-width: 1180px; }
        div[data-testid="stMetric"] { background: #fafafa; border: 1px solid #eeeeee; padding: 0.75rem; border-radius: 8px; }
        div[data-testid="stAlert"] { border-radius: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Audiobook AI", page_icon="🎧", layout="wide")
    apply_style()
    st.title("Audiobook AI")
    st.caption(f"Máy chủ: {API_BASE_URL}")

    with st.sidebar:
        st.header("Thiết lập")
        output_format = st.selectbox("Định dạng âm thanh", ["mp3", "wav"], index=0)
        normalize_audio = st.checkbox("Chuẩn hóa âm lượng", value=True)
        add_chapters = st.checkbox("Gắn mốc chương", value=True)
        st.divider()
        st.header("Theo dõi")
        status_label = st.selectbox("Lọc trạng thái", [_label(value) for value in STATUS_FILTERS], index=0)
        selected_status = _selected_status_value(status_label)
        auto_refresh = st.checkbox("Tự làm mới", value=True)
        refresh_seconds = st.number_input("Số giây", min_value=1, max_value=30, value=2)
        st.divider()
        remembered = st.text_input("Mã tác vụ", value=st.session_state.get("job_id", ""))
        if remembered:
            st.session_state["job_id"] = remembered.strip()

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
    job_id = st.session_state.get("job_id")
    if job_id:
        try:
            job = get_job(job_id)
        except requests.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            st.error(f"Không đọc được tác vụ: {detail}")
        except requests.RequestException as exc:
            st.error(f"Không kết nối được máy chủ: {exc}")

    tab_create, tab_queue, tab_result, tab_logs = st.tabs(["Tạo sách nói", "Theo dõi", "Kết quả", "Nhật ký"])

    with tab_create:
        render_upload_tab(output_format, normalize_audio, add_chapters)

    with tab_queue:
        render_queue_tab(queue_payload, selected_status)

    with tab_result:
        if not job:
            st.info("Chọn một tác vụ trong tab Theo dõi hoặc nhập mã tác vụ ở thanh bên.")
        else:
            render_job_summary(job)
            st.divider()
            left, right = st.columns([0.9, 1.4])
            with left:
                epub_bytes = render_downloads(job)
            with right:
                render_epub_preview(epub_bytes)

    with tab_logs:
        render_logs_tab(job)

    if auto_refresh and any(item.get("status") in {"pending", "running"} for item in queue_payload.get("jobs", [])):
        time.sleep(float(refresh_seconds))
        st.rerun()


if __name__ == "__main__":
    main()
