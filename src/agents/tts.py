"""
TTS Agent — Converts annotated text segments into audio.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
import wave
import contextlib

from .base import BaseAgent, AgentResult
from schema.audio import (
    TTSSegment,
    AudioSegment,
    TTSGeneratorInput,
    TTSGeneratorOutput,
)
from utils.tts_engine import CacheManager, XTTSEngine, MockXTTSEngine
from .voice import VoiceAgent


class TTSAgent(BaseAgent):
    """
    Generates speech audio using XTTS engine combined with Caching.
    Dynamically maps emotions to final speed and pitch.
    """

    name = "tts"

    def __init__(self, name: str = "tts", config: Optional[Dict[str, Any]] = None, 
                 engine: Optional[XTTSEngine] = None, cache_manager: Optional[CacheManager] = None):
        super().__init__(name, config)
        self.engine = engine or MockXTTSEngine()
        self.cache_manager = cache_manager or CacheManager()

    async def run(self, input_data: TTSGeneratorInput) -> AgentResult:
        try:
            segments = input_data.segments
            output_dir = Path(input_data.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            audio_segments: List[AudioSegment] = []
            failed: List[int] = []
            
            # Temporary voice agent core to calculate prosody per segment
            voice_agent_core = VoiceAgent()

            for seg in segments:
                try:
                    # 1. Dynamic Prosody inference
                    intensity = getattr(seg, 'intensity', 1.0) 
                    speed_mod, pitch = voice_agent_core.map_prosody(seg.emotion or "neutral", intensity)
                    final_speed = speed_mod * getattr(seg, 'speed', 1.0)

                    # 2. Cache Checking
                    cached_path = self.cache_manager.get_audio_path(
                        text=seg.text, 
                        voice_id=seg.voice_id, 
                        speed=final_speed, 
                        pitch=pitch
                    )
                    
                    if cached_path:
                        final_path = cached_path
                    else:
                        # 3. Cache Miss -> Synthesize
                        final_path = self.cache_manager.get_cache_path_for_generation(
                            text=seg.text, 
                            voice_id=seg.voice_id, 
                            speed=final_speed, 
                            pitch=pitch
                        )
                        self.engine.synthesize(
                            text=seg.text, 
                            voice_id=seg.voice_id, 
                            speed=final_speed, 
                            pitch=pitch, 
                            output_path=str(final_path)
                        )

                    # 4. Measure duration and compile output
                    duration = 0.0
                    try:
                        with contextlib.closing(wave.open(str(final_path),'r')) as f:
                            frames = f.getnframes()
                            rate = f.getframerate()
                            duration = frames / float(rate) if rate > 0 else 1.0
                    except Exception:
                        duration = 1.0
                    
                    audio_segments.append(AudioSegment(
                        file_path=str(final_path),
                        duration_seconds=duration,
                        segment_index=seg.segment_index,
                        chapter_index=seg.chapter_index,
                        text=seg.text[:50],
                        voice_id=seg.voice_id
                    ))

                except Exception as e:
                    failed.append(seg.segment_index)

            total_duration = sum(s.duration_seconds for s in audio_segments)
            success_rate = (len(segments) - len(failed)) / len(segments) if segments else 0.0

            return AgentResult(
                success=True,
                data=TTSGeneratorOutput(
                    audio_segments=audio_segments,
                    total_duration=total_duration,
                    failed_segments=failed,
                    metadata={"segment_count": len(segments), "success_rate": success_rate},
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))