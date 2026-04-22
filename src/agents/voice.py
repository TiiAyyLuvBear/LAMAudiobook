"""
Voice Agent — Assigns TTS voice IDs and prosody to speakers.
"""
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAgent, AgentResult
from schema.audio import VoiceAssignment


class VoiceInput:
    """Input for Voice Agent"""
    def __init__(self, speakers: List[str], speaker_mode: str = "multi"):
        self.speakers = speakers
        self.speaker_mode = speaker_mode


class VoiceOutput:
    """Output from Voice Agent"""
    def __init__(self, voice_assignments: List[VoiceAssignment], narrator_voice: str):
        self.voice_assignments = voice_assignments
        self.narrator_voice = narrator_voice


class VoiceAgent(BaseAgent):
    """
    Assigns TTS voice IDs and parameters (speed, pitch) to speakers.
    Supports both 'single' mode (only narrator) and 'multi' mode.
    """

    name = "voice"

    def __init__(self, name: str = "voice", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.narrator_fallback = "narrator_vi_fallback"
        # Voice Pool (Voice DB List) - Trong dự án thật sẽ nạp từ file JSON/YAML
        self.voice_pool = self.config.get("voice_pool", [
            "female_hcm_01", "female_hn_02", 
            "male_hcm_01", "male_hn_02", 
            "child_voice_01"
        ])

    def _map_speaker(self, speaker: Optional[str]) -> str:
        """Deterministic Voice ID assignment using SHA-256 Modulo Map"""
        if not speaker or speaker.lower() == "narrator":
            return self.narrator_fallback
            
        # 1. Băm SHA-256 ra chuỗi Hex
        speaker_hash = hashlib.sha256(speaker.lower().encode("utf-8")).hexdigest()
        
        # 2. Chuyển Base-16 String sang Integer khổng lồ
        hash_int = int(speaker_hash, 16)
        
        # 3. Thuật toán Modulo (chia lấy dư) dựa trên kích thước Voice DB
        if not self.voice_pool:
            return self.narrator_fallback
            
        assigned_index = hash_int % len(self.voice_pool)
        
        # 4. Trả về đúng tên Voice ID của file vật lý
        return self.voice_pool[assigned_index]

    def map_prosody(self, emotion: str, intensity: float) -> Tuple[float, float]:
        """Calculates (speed, pitch) modifiers from emotion and intensity"""
        speed, pitch = 1.0, 1.0
        emotion = emotion.lower() if emotion else "neutral"

        if emotion == "angry":
            speed += 0.5 * intensity
            pitch += 0.5 * intensity
        elif emotion == "sad":
            speed -= 0.3 * intensity
            pitch -= 0.3 * intensity
        elif emotion == "happy":
            speed += 0.4 * intensity

        return round(speed, 2), round(pitch, 2)

    async def run(self, input_data: VoiceInput) -> AgentResult:
        try:
            assignments: List[VoiceAssignment] = []

            for speaker in input_data.speakers:
                # Support the hybrid Single/Multi switch logic
                if input_data.speaker_mode == "single":
                    vid = self.narrator_fallback
                else:
                    vid = self._map_speaker(speaker)
                
                assignments.append(
                    VoiceAssignment(
                        speaker=speaker,
                        voice_id=vid,
                        voice_params={"base_speed": 1.0, "base_pitch": 1.0},
                    )
                )

            return AgentResult(
                success=True,
                data=VoiceOutput(
                    voice_assignments=assignments,
                    narrator_voice=self.narrator_fallback,
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))