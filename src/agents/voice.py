"""
Voice Agent — Assigns TTS voice IDs to speakers.
"""
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult
from types.audio import VoiceAssignment


class VoiceInput:
    """Input for Voice Agent"""
    def __init__(self, speakers: List[str], speaker_mode: str = "single"):
        self.speakers = speakers
        self.speaker_mode = speaker_mode


class VoiceOutput:
    """Output from Voice Agent"""
    def __init__(self, voice_assignments: List[VoiceAssignment], narrator_voice: str):
        self.voice_assignments = voice_assignments
        self.narrator_voice = narrator_voice


class VoiceAgent(BaseAgent):
    """
    Assigns TTS voice IDs to speakers for consistent voice across the audiobook.
    Considers speaker gender/age, available TTS voices, and consistency.
    """

    name = "voice"

    # Default voice pool — extend via config
    DEFAULT_VOICES = {
        "narrator": {"voice_id": "narrator_vi_female", "speed": 1.0, "pitch": 0},
        "unknown": {"voice_id": "unknown_vi_male", "speed": 1.0, "pitch": 0},
    }

    async def run(self, input_data: VoiceInput) -> AgentResult:
        try:
            assignments: List[VoiceAssignment] = []
            narrator_voice = "narrator_vi_female"

            # Assign voices to speakers
            for speaker in input_data.speakers:
                if speaker == "narrator":
                    voice_params = self.DEFAULT_VOICES.get("narrator", {"voice_id": "narrator_vi_female"})
                else:
                    voice_params = self.DEFAULT_VOICES.get("unknown", {"voice_id": "unknown_vi_male"})

                assignments.append(
                    VoiceAssignment(
                        speaker=speaker,
                        voice_id=voice_params["voice_id"],
                        voice_params=voice_params,
                    )
                )

            return AgentResult(
                success=True,
                data=VoiceOutput(
                    voice_assignments=assignments,
                    narrator_voice=narrator_voice,
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))