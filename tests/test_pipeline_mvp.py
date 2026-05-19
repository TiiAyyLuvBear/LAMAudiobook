import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_tts_split_keeps_one_audio_per_sentence_without_packing():
    from pipeline.audiobook import AudiobookPipeline

    pipeline = object.__new__(AudiobookPipeline)
    assert pipeline._split_tts_text("Xin chào. Đây là câu hai!") == ["Xin chào.", "Đây là câu hai!"]


def test_tts_split_does_not_split_long_sentence():
    from pipeline.audiobook import AudiobookPipeline

    pipeline = object.__new__(AudiobookPipeline)
    sentence = "Đây là " + "một câu rất dài " * 80 + "nhưng vẫn là một audio."
    assert pipeline._split_tts_text(sentence) == [sentence]


def test_state_progress_is_monotonic_and_structured():
    from pipeline.state import StateManager
    from pipeline.config import PipelineStage

    state = StateManager()
    state.set_stage(PipelineStage.GENERATING)
    first = state.state.progress
    state.set_stage(PipelineStage.CLEANING)
    assert state.state.progress == first

    state.set_global_segments(16)
    state.update_global_segment(11)
    state.set_chapter_segments(6)
    state.update_chapter_segment(5)
    payload = state.to_dict()
    assert payload["global_segment"] == {"current": 11, "total": 16}
    assert payload["chapter_segment"] == {"current": 5, "total": 6}


def test_mock_job_system_voice_uses_one_segment_per_sentence(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TTS_ENGINE", "mock")
    monkeypatch.setenv("TTS_SPEAKER_MODE", "single")
    monkeypatch.setenv("XTTS_VOICE_DIR", str(ROOT / "data" / "voice_samples"))
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    from src.backend.app import app

    book = tmp_path / "book.txt"
    book.write_text("Chương 1: Test\nXin chào. Đây là một đoạn kiểm thử.", encoding="utf-8")

    with TestClient(app) as client:
        with book.open("rb") as fh:
            response = client.post(
                "/api/v1/audiobook/jobs",
                params={
                    "output_format": "wav",
                    "normalize_audio": False,
                    "add_chapters": False,
                    "analysis_enabled": False,
                    "voice_mode": "system_voice",
                    "selected_voice_id": "male_hn_02",
                },
                files={"file": ("book.txt", fh, "text/plain")},
            )
        response.raise_for_status()
        job_id = response.json()["job_id"]

        final = {}
        for _ in range(60):
            final = client.get(f"/api/v1/audiobook/jobs/{job_id}").json()
            if final["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.25)

    assert final["status"] == "completed"
    assert final["progress"] == pytest.approx(1.0)
    assert final["global_segment"]["current"] == final["global_segment"]["total"]

    outputs = tmp_path / "storage" / "jobs" / job_id / "outputs"
    segments = json.loads(next(outputs.rglob("segments.json")).read_text(encoding="utf-8"))
    assert [segment["voice_id"] for segment in segments] == ["male_hn_02", "male_hn_02"]
    assert [segment["text"] for segment in segments] == ["Xin chào.", "Đây là một đoạn kiểm thử."]

    logs = (tmp_path / "storage" / "jobs" / job_id / "logs" / "logs.txt").read_text(encoding="utf-8")
    assert "segment 11/6" not in logs
    assert "global_segment" in logs
