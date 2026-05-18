import asyncio
import httpx
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    async def run(self, input_data: TTSGeneratorInput) -> AgentResult:
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
            
            async with httpx.AsyncClient(timeout=300.0) as client:
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
            return AgentResult(success=False, error=repr(e))