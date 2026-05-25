import json
import os
import sys
import time
import wave
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


def test_tts_agent_surfaces_engine_warnings(tmp_path):
    from agents.tts import TTSAgent
    from schema.audio import TTSSegment, TTSGeneratorInput

    class FakeWarningEngine:
        enable_voice_cloning = True

        def __init__(self):
            self.device = "cpu"
            self._warnings = ["Voice cloning fell back to preset voice."]

        def consume_warnings(self):
            warnings = list(self._warnings)
            self._warnings.clear()
            return warnings

        def synthesize(self, text, voice_id, speed, pitch, output_path):
            with wave.open(str(output_path), "wb") as audio_file:
                audio_file.setnchannels(1)
                audio_file.setsampwidth(2)
                audio_file.setframerate(16000)
                audio_file.writeframes(b"\x00\x00" * 1600)

    agent = TTSAgent(config={"tts_engine": "vieneu", "tts_device": "cpu"})
    result = agent._run_direct_engine_sync(
        TTSGeneratorInput(
            segments=[
                TTSSegment(
                    text="Xin chào.",
                    voice_id="custom_voice",
                    chapter_index=1,
                    segment_index=1,
                )
            ],
            output_dir=str(tmp_path),
        ),
        engine_factory=FakeWarningEngine,
        engine_name="vieneu",
    )

    assert result.success
    assert result.data.metadata["warnings"] == ["Voice cloning fell back to preset voice."]
    assert result.data.metadata["voice_cloning"] is True



def test_tts_engine_name_accepts_hyphen_alias():
    from agents.tts import TTSAgent

    agent = TTSAgent(config={"tts_engine": "xtts-gpu"})

    assert agent.engine == "xtts_gpu"

def test_uploaded_custom_voices_are_not_listed_as_system_voices(tmp_path, monkeypatch):
    voice_dir = tmp_path / "voices"
    voice_dir.mkdir()
    (voice_dir / "female_hn_01.wav").write_bytes(b"system")
    (voice_dir / "custom_deadbeef1234.wav").write_bytes(b"temporary")
    monkeypatch.setenv("XTTS_VOICE_DIR", str(voice_dir))

    from api.routes import _available_voice_ids, _is_temporary_voice_id

    assert _is_temporary_voice_id("custom_deadbeef1234")
    assert _available_voice_ids() == ["female_hn_01"]


def test_vieneu_custom_voice_requires_reference_encoder(tmp_path):
    from importlib import import_module
    import types

    service_app_dir = SRC / "tts-service" / "app"
    package_name = "_local_tts_service_app"
    engines_package_name = f"{package_name}.engines"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(service_app_dir)]
        sys.modules[package_name] = package
    if engines_package_name not in sys.modules:
        engines_package = types.ModuleType(engines_package_name)
        engines_package.__path__ = [str(service_app_dir / "engines")]
        sys.modules[engines_package_name] = engines_package

    module = import_module("_local_tts_service_app.engines.vieneu")
    engine = object.__new__(module.VieNeuEngine)
    engine.tts = object()
    engine.voice_dir = tmp_path
    engine.enable_voice_cloning = True
    engine.codec_repo = "neuphonic/neucodec-onnx-decoder-int8"
    engine.reference_text = "Xin chào."
    engine._runtime_warnings = []
    (tmp_path / "custom_deadbeef1234.wav").write_bytes(b"not-a-real-wav")

    with pytest.raises(RuntimeError, match="cannot encode reference audio"):
        engine.synthesize(
            text="Xin chào.",
            voice_id="custom_deadbeef1234",
            speed=1.0,
            pitch=1.0,
            output_path=str(tmp_path / "out.wav"),
        )


def test_xtts_runtime_auto_setup_clones_and_installs_requirements(tmp_path, monkeypatch):
    from importlib import import_module
    import types

    service_app_dir = SRC / "tts-service" / "app"
    package_name = "_local_tts_service_app"
    engines_package_name = f"{package_name}.engines"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(service_app_dir)]
        sys.modules[package_name] = package
    if engines_package_name not in sys.modules:
        engines_package = types.ModuleType(engines_package_name)
        engines_package.__path__ = [str(service_app_dir / "engines")]
        sys.modules[engines_package_name] = engines_package

    module = import_module("_local_tts_service_app.engines.xtts")
    runtime_dir = tmp_path / "models" / "XTTSv2-Finetuning-for-New-Languages"
    calls = []

    def fake_run(command, check):
        calls.append(command)
        if command[:3] == ["git", "clone", "--depth"]:
            runtime_dir.mkdir(parents=True)
            (runtime_dir / "requirements.txt").write_text("coqui-tts\n", encoding="utf-8")
        return None

    monkeypatch.setenv("XTTS_RUNTIME_REPO", "https://example.test/xtts-runtime.git")
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    engine = object.__new__(module.XTTSEngine)
    engine.runtime_dir = runtime_dir
    engine._ensure_runtime_available()

    assert calls == [
        ["git", "clone", "--depth", "1", "https://example.test/xtts-runtime.git", str(runtime_dir)],
        [sys.executable, "-m", "pip", "install", "-r", str(runtime_dir / "requirements.txt")],
    ]


def test_uploaded_voice_clean_outputs_are_written_to_clean_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    import api.routes as routes
    from services.storage import StorageService

    routes.storage_service = StorageService(str(tmp_path / "storage"))

    raw_voice = tmp_path / "raw.wav"
    cleaned_voice = tmp_path / "cleaned.wav"
    raw_voice.write_bytes(b"raw")
    cleaned_voice.write_bytes(b"cleaned")

    payload = routes._record_uploaded_voice_clean_outputs(
        job_id="job-1",
        raw_voice_path=raw_voice,
        cleaned_voice_path=cleaned_voice,
        voice_filename="sample.wav",
        voice_id="custom_job1",
        cleaning_info={"filters": ["afftdn=nf=-25"], "sample_rate_hz": 24000},
    )

    clean_dir = tmp_path / "storage" / "jobs" / "job-1" / "outputs" / "02_clean"
    assert (clean_dir / "voice_cleaned_sample.wav").read_bytes() == b"cleaned"
    metadata = json.loads((clean_dir / "voice_cleaning.json").read_text(encoding="utf-8"))
    assert metadata["voice_id"] == "custom_job1"
    assert metadata["noise_reduction"]["filters"] == ["afftdn=nf=-25"]
    assert payload["clean_stage_voice_path"].endswith("voice_cleaned_sample.wav")
