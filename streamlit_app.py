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

STAGES = ["queued", "running", "parsing", "cleaning", "analyzing", "generating", "finalizing", "completed"]


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


def render_job(job: dict) -> None:
    status = job.get("status", "unknown")
    stage = job.get("stage") or status
    progress = float(job.get("progress") or 0.0)

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

    if job.get("error"):
        st.error(job["error"])

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

    job_id = st.session_state.get("job_id")
    if not job_id:
        st.info("Upload an EPUB or enter an existing job ID to view progress.")
        return

    st.subheader("Job Progress")
    try:
        job = get_job(job_id)
        render_job(job)
        if job.get("status") in {"pending", "running"}:
            time.sleep(2)
            st.rerun()
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        st.error(f"Job lookup failed: {detail}")
    except requests.RequestException as exc:
        st.error(f"Cannot reach API: {exc}")


if __name__ == "__main__":
    main()
