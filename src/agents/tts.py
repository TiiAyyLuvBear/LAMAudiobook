import asyncio
import importlib
import os
import sys
import types
import httpx
import contextlib
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base import BaseAgent, AgentResult
from schema.audio import (
    TTSSegment,
    AudioSegment,
    TTSGeneratorInput,
    TTSGeneratorOutput,
)
from .voice import VoiceAgent


class TTSAgent(BaseAgent):
    """
    TTS Agent that delegates synthesis to a dedicated TTS Microservice
    using HTTP and an async polling mechanism.
    """

    name = "tts"

    def __init__(self, name: str = "tts", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.service_url = config.get("tts_service_url", "http://localhost:8001") if config else "http://localhost:8001"
        self.engine = (self.config.get("tts_engine") or os.getenv("TTS_ENGINE") or "http").lower()
        self.progress_callback: Optional[Callable[[int, int, int], None]] = self.config.get("progress_callback")
        self._xtts_engine = None
        self._vieneu_engine = None

    async def run(self, input_data: TTSGeneratorInput) -> AgentResult:
        if self.engine in {"xtts", "xtts_gpu", "xtts_cpu", "direct_xtts"}:
            return await asyncio.to_thread(self._run_direct_engine_sync, input_data, self._get_xtts_engine, self.engine)
        if self.engine in {"vieneu", "vieneu_tts", "direct_vieneu"}:
            return await asyncio.to_thread(self._run_direct_engine_sync, input_data, self._get_vieneu_engine, "vieneu")

        try:
            segments = input_data.segments
            output_dir = Path(input_data.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            payload_segments = []
            
            for seg in segments:
                intensity = getattr(seg, 'intensity', 1.0) 
                speed_mod, pitch = VoiceAgent.map_prosody(seg.emotion or "neutral", intensity)
                final_speed = speed_mod * getattr(seg, 'speed', 1.0)
                
                # Shared volume mounted at same path in worker container
                final_path = output_dir / f"seg_{seg.segment_index:04d}_{seg.voice_id}.wav"
                
                payload_segments.append({
                    "text": seg.text,
                    "voice_id": seg.voice_id,
                    "speed": final_speed,
                    "pitch": pitch,
                    "output_path": str(final_path),
                    "segment_index": seg.segment_index,
                    "chapter_index": seg.chapter_index
                })
                
            payload = {
                "segments": payload_segments,
                "output_dir": str(output_dir)
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Enqueue job
                resp = await client.post(f"{self.service_url}/api/tts/batch", json=payload)
                resp.raise_for_status()
                job_id = resp.json()["job_id"]
                
                # 2. Poll for job completion
                while True:
                    status_resp = await client.get(f"{self.service_url}/api/tts/job/{job_id}")
                    status_resp.raise_for_status()
                    status = status_resp.json()
                    
                    if status["state"] == "finished":
                        result = status["result"]
                        audio_segments_raw = result.get("audio_segments", [])
                        
                        audio_segments = []
                        for s in audio_segments_raw:
                            audio_segments.append(AudioSegment(
                                file_path=s["file_path"],
                                duration_seconds=s["duration_seconds"],
                                segment_index=s["segment_index"],
                                chapter_index=s["chapter_index"],
                                text=s["text"],
                                voice_id=s["voice_id"]
                            ))
                            
                        return AgentResult(
                            success=True,
                            data=TTSGeneratorOutput(
                                audio_segments=audio_segments,
                                total_duration=result.get("total_duration", 0),
                                failed_segments=result.get("failed_segments", []),
                                metadata=result.get("metadata", {}),
                            ),
                        )
                    elif status["state"] == "failed":
                        return AgentResult(success=False, error=status.get("error", "TTS Job Failed"))
                        
                    await asyncio.sleep(2.0)

        except Exception as e:
            return AgentResult(success=False, error=str(e))

    def _get_xtts_engine(self):
        if self._xtts_engine is None:
            service_app_dir = Path(__file__).resolve().parents[1] / "tts-service" / "app"
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

            xtts_module = importlib.import_module(f"{engines_package_name}.xtts")
            XTTSEngine = xtts_module.XTTSEngine

            self._xtts_engine = XTTSEngine(
                voice_dir=self.config.get("xtts_voice_dir") or os.getenv("XTTS_VOICE_DIR", "data/voice_samples"),
                model_name_or_path=self.config.get("xtts_model_name_or_path") or os.getenv("XTTS_MODEL_NAME_OR_PATH"),
                config_path=self.config.get("xtts_config_path") or os.getenv("XTTS_CONFIG_PATH"),
                vocab_path=self.config.get("xtts_vocab_path") or os.getenv("XTTS_VOCAB_PATH"),
                device=self.config.get("tts_device") or os.getenv("XTTS_DEVICE") or os.getenv("TTS_DEVICE", "auto"),
            )
        return self._xtts_engine

    def _get_vieneu_engine(self):
        if self._vieneu_engine is None:
            service_app_dir = Path(__file__).resolve().parents[1] / "tts-service" / "app"
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

            vieneu_module = importlib.import_module(f"{engines_package_name}.vieneu")
            VieNeuEngine = vieneu_module.VieNeuEngine

            self._vieneu_engine = VieNeuEngine(
                mode=self.config.get("vieneu_mode") or os.getenv("VIENEU_MODE", "standard"),
                model_name=self.config.get("vieneu_model_name") or os.getenv("VIENEU_MODEL_NAME", "pnnbao-ump/VieNeu-TTS-0.3B"),
                emotion=self.config.get("vieneu_emotion") or os.getenv("VIENEU_EMOTION", "storytelling"),
                api_base=self.config.get("vieneu_api_base") or os.getenv("VIENEU_API_BASE") or None,
                voice_dir=self.config.get("xtts_voice_dir") or os.getenv("XTTS_VOICE_DIR", "data/voice_samples"),
                device=self.config.get("vieneu_device") or os.getenv("VIENEU_DEVICE") or os.getenv("TTS_DEVICE", "auto"),
            )
        return self._vieneu_engine

    def _run_direct_engine_sync(
        self,
        input_data: TTSGeneratorInput,
        engine_factory: Callable[[], Any],
        engine_name: str,
    ) -> AgentResult:
        try:
            segments = input_data.segments
            output_dir = Path(input_data.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            engine = engine_factory()
            audio_segments: List[AudioSegment] = []
            failed_segments: List[int] = []
            failure_details: List[str] = []

            total_segments = len(segments)
            for position, seg in enumerate(segments, start=1):
                try:
                    intensity = getattr(seg, "intensity", 1.0)
                    speed_mod, pitch = VoiceAgent.map_prosody(seg.emotion or "neutral", intensity)
                    final_speed = speed_mod * getattr(seg, "speed", 1.0)
                    output_path = output_dir / f"seg_{seg.segment_index:04d}_{seg.voice_id}.wav"

                    engine.synthesize(
                        text=seg.text,
                        voice_id=seg.voice_id,
                        speed=final_speed,
                        pitch=pitch,
                        output_path=str(output_path),
                    )

                    duration = 1.0
                    try:
                        with contextlib.closing(wave.open(str(output_path), "r")) as audio_file:
                            frames = audio_file.getnframes()
                            rate = audio_file.getframerate()
                            duration = frames / float(rate) if rate > 0 else 1.0
                    except Exception:
                        pass

                    audio_segments.append(
                        AudioSegment(
                            file_path=str(output_path),
                            duration_seconds=duration,
                            segment_index=seg.segment_index,
                            chapter_index=seg.chapter_index,
                            text=seg.text,
                            voice_id=seg.voice_id,
                        )
                    )
                except Exception as exc:
                    failed_segments.append(seg.segment_index)
                    detail = f"segment {seg.segment_index} voice={seg.voice_id}: {exc}"
                    failure_details.append(detail)
                    print(f"[TTSAgent] Failed to synthesize {detail}")
                finally:
                    if self.progress_callback:
                        self.progress_callback(position, total_segments, seg.chapter_index)

            if not audio_segments:
                preview = "; ".join(failure_details[:5])
                return AgentResult(
                    success=False,
                    error=f"No TTS segments were synthesized. First errors: {preview}",
                )

            total_duration = sum(segment.duration_seconds for segment in audio_segments)
            return AgentResult(
                success=True,
                data=TTSGeneratorOutput(
                    audio_segments=audio_segments,
                    total_duration=total_duration,
                    failed_segments=failed_segments,
                    metadata={
                        "engine": engine_name,
                        "segment_count": len(segments),
                        "succeeded_count": len(audio_segments),
                    },
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))
