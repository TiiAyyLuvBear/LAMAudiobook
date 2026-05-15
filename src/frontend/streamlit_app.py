"""
Streamlit frontend for the audiobook service.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

STAGES = ["queued", "running", "parsing", "cleaning", "analyzing", "generating", "finalizing", "cancelling", "completed", "failed"]
STATUS_FILTERS = ["all", "pending", "running", "failed", "completed", "cancelled"]


def api_url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


def create_job(uploaded_file, output_format: str, normalize_audio: bool, add_chapters: bool) -> dict:
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            "application/epub+zip",
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


def render_stage(stage: str) -> None:
    active = STAGES.index(stage) if stage in STAGES else 0
    cols = st.columns(len(STAGES))
    for i, name in enumerate(STAGES):
        label = name.title()
        if i < active:
            cols[i].success(label)
        elif i == active:
            cols[i].info(label)
        else:
            cols[i].caption(label)


def _short_id(job_id: str) -> str:
    return job_id[:8]


def _status_badge(container, status: str, label: str) -> None:
    if status == "running":
        container.info(label)
    elif status == "pending":
        container.warning(label)
    elif status == "failed":
        container.error(label)
    elif status == "completed":
        container.success(label)
    else:
        container.caption(label)


def render_queue_overview(payload: dict, selected_status: str) -> list[dict]:
    jobs = payload.get("jobs") or []
    stats = payload.get("stats") or {}

    cols = st.columns(5)
    cols[0].metric("Running", stats.get("running", 0))
    cols[1].metric("Pending", stats.get("pending", 0))
    cols[2].metric("Failed", stats.get("failed", 0))
    cols[3].metric("Completed", stats.get("completed", 0))
    cols[4].metric("Cancelled", stats.get("cancelled", 0))

    if selected_status != "all":
        jobs = [job for job in jobs if job.get("status") == selected_status]

    if not jobs:
        st.info("No jobs match the selected filter.")
        return []

    st.subheader("Jobs")
    header = st.columns([1.1, 1.2, 1.2, 2.0, 1.0, 1.0, 1.0])
    header[0].caption("Job")
    header[1].caption("Status")
    header[2].caption("Stage")
    header[3].caption("Progress")
    header[4].caption("Chapter")
    header[5].caption("Artifacts")
    header[6].caption("Action")

    for job in jobs:
        cols = st.columns([1.1, 1.2, 1.2, 2.0, 1.0, 1.0, 1.0])
        job_id = job.get("job_id", "")
        if cols[0].button(_short_id(job_id), key=f"select-{job_id}", use_container_width=True):
            st.session_state["job_id"] = job_id
        _status_badge(cols[1], job.get("status", "unknown"), job.get("status", "unknown"))
        cols[2].write(job.get("stage") or "-")
        progress = min(1.0, max(0.0, float(job.get("progress") or 0.0)))
        cols[3].progress(progress, text=job.get("status_message") or f"{progress:.0%}")
        total = int(job.get("total_chapters") or 0)
        current = int(job.get("current_chapter") or 0)
        cols[4].write(f"{current}/{total}" if total else "-")
        artifact_count = len(job.get("artifacts") or [])
        cols[5].write(str(artifact_count))
        if job.get("cancel_requested"):
            cols[6].caption("Cancelling")
        elif job.get("status") in {"pending", "running"}:
            if cols[6].button("Cancel", key=f"cancel-row-{job_id}", use_container_width=True):
                cancel_job(job_id)
                st.session_state["job_id"] = job_id
                st.rerun()
        else:
            cols[6].caption("-")

    return jobs


def render_job(job: dict) -> None:
    status = job.get("status", "unknown")
    stage = job.get("stage") or status
    progress = float(job.get("progress") or 0.0)

    st.subheader(f"Job {_short_id(job.get('job_id', ''))}")
    render_stage(stage if stage in STAGES else status)
    status_message = job.get("status_message") or f"{status} / {stage}"
    st.progress(min(1.0, max(0.0, progress)), text=status_message)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", status)
    c2.metric("Stage", stage)
    total = int(job.get("total_chapters") or 0)
    current = int(job.get("current_chapter") or 0)
    c3.metric("Chapter", f"{current}/{total}" if total else "-")
    segment_total = int(job.get("total_segments") or 0)
    segment_current = int(job.get("current_segment") or 0)
    c4.metric("Segment", f"{segment_current}/{segment_total}" if segment_total else "-")

    if job.get("cancel_requested"):
        st.warning("Cancellation requested. The current step will stop at the next safe checkpoint.")
    elif status in {"pending", "running"}:
        if st.button("Cancel job", type="secondary", use_container_width=True, key=f"cancel-detail-{job['job_id']}"):
            try:
                cancel_job(job["job_id"])
                st.warning("Cancellation requested.")
                st.rerun()
            except requests.HTTPError as exc:
                detail = exc.response.text if exc.response is not None else str(exc)
                st.error(f"Cancel failed: {detail}")
            except requests.RequestException as exc:
                st.error(f"Cannot reach API: {exc}")

    if job.get("error"):
        st.error(job["error"])

    chapter_epubs = [
        artifact
        for artifact in (job.get("artifacts") or [])
        if artifact.get("type") == "chapter_epub"
    ]
    if chapter_epubs:
        st.subheader("Ready Chapters")
        for artifact in sorted(chapter_epubs, key=lambda item: int(item.get("chapter_index") or 0)):
            chapter_index = int(artifact.get("chapter_index") or 0)
            title = artifact.get("title") or f"Chapter {chapter_index}"
            download_url = api_url(f"/api/v1/audiobook/jobs/{job['job_id']}/chapters/{chapter_index}/download")
            response = requests.get(download_url, timeout=60)
            if response.ok:
                st.download_button(
                    f"Chapter {chapter_index}: {title}",
                    data=response.content,
                    file_name=Path(artifact.get("path") or f"chapter_{chapter_index:04d}.epub").name,
                    mime="application/epub+zip",
                    use_container_width=True,
                )

    logs = job.get("logs") or ""
    if logs:
        with st.expander("Logs", expanded=status in {"running", "failed"}):
            st.code(logs, language="")

    if status == "completed":
        download_url = api_url(f"/api/v1/audiobook/jobs/{job['job_id']}/download")
        audio_response = requests.get(download_url, timeout=60)
        if audio_response.ok:
            result = job.get("result") or {}
            filename = Path(result.get("output_path") or "audiobook.mp3").name
            mime = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
            st.audio(audio_response.content, format=mime)
            st.download_button(
                "Download audiobook",
                data=audio_response.content,
                file_name=filename,
                mime=mime,
                use_container_width=True,
            )
        else:
            st.warning("Job completed, but the audio file is not available.")


def main() -> None:
    st.set_page_config(page_title="Audiobook AI", page_icon="🎧", layout="wide")
    st.title("Audiobook AI")
    st.caption(f"Backend: {API_BASE_URL}")

    with st.sidebar:
        st.header("Audio")
        output_format = st.selectbox("Output format", ["mp3", "wav"], index=0)
        normalize_audio = st.checkbox("Normalize audio", value=True)
        add_chapters = st.checkbox("Chapter markers", value=True)
        st.divider()
        st.header("Queue")
        selected_status = st.selectbox("Status filter", STATUS_FILTERS, index=0)
        auto_refresh = st.checkbox("Auto refresh", value=True)
        refresh_seconds = st.number_input("Refresh seconds", min_value=1, max_value=30, value=2)
        st.divider()
        remembered = st.text_input("Job ID", value=st.session_state.get("job_id", ""))
        if remembered:
            st.session_state["job_id"] = remembered.strip()

    uploaded = st.file_uploader("Upload Vietnamese EPUB", type=["epub"])
    if uploaded:
        size_mb = len(uploaded.getvalue()) / 1024 / 1024
        st.info(f"{uploaded.name} - {size_mb:.2f} MB")
        if size_mb > MAX_FILE_SIZE_MB:
            st.error(f"File is larger than {MAX_FILE_SIZE_MB} MB.")
        elif st.button("Create audiobook job", type="primary", use_container_width=True):
            try:
                created = create_job(uploaded, output_format, normalize_audio, add_chapters)
                st.session_state["job_id"] = created["job_id"]
                st.success(f"Queued job {created['job_id']}")
            except requests.HTTPError as exc:
                detail = exc.response.text if exc.response is not None else str(exc)
                st.error(f"Upload failed: {detail}")
            except requests.RequestException as exc:
                st.error(f"Cannot reach API: {exc}")

    try:
        queue_payload = list_jobs()
        render_queue_overview(queue_payload, selected_status)
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        st.error(f"Queue lookup failed: {detail}")
    except requests.RequestException as exc:
        st.error(f"Cannot reach API: {exc}")
        return

    job_id = st.session_state.get("job_id")
    if not job_id:
        st.info("Select a job from the queue or enter a job ID to view details.")
        if auto_refresh:
            time.sleep(float(refresh_seconds))
            st.rerun()
        return

    try:
        job = get_job(job_id)
        render_job(job)
        if auto_refresh and any(
            item.get("status") in {"pending", "running"}
            for item in queue_payload.get("jobs", [])
        ):
            time.sleep(float(refresh_seconds))
            st.rerun()
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        st.error(f"Job lookup failed: {detail}")
    except requests.RequestException as exc:
        st.error(f"Cannot reach API: {exc}")


if __name__ == "__main__":
    main()
