"""
Planner Agent — Decides processing strategy for the document.
"""
from typing import Any, Dict, Optional

from .base import BaseAgent, AgentResult


class PlannerInput:
    """Input for Planner Agent"""
    def __init__(self, file_path: str, file_type: str, metadata: Optional[Dict] = None):
        self.file_path = file_path
        self.file_type = file_type
        self.metadata = metadata or {}


class PlannerOutput:
    """Output from Planner Agent"""
    def __init__(
        self,
        needs_ocr: bool,
        speaker_mode: str,
        emotion_level: str,
        language: str,
        processing_hints: Optional[Dict] = None,
    ):
        self.needs_ocr = needs_ocr
        self.speaker_mode = speaker_mode  # "single" or "multi"
        self.emotion_level = emotion_level  # "none", "basic", "full"
        self.language = language
        self.processing_hints = processing_hints or {}


class PlannerAgent(BaseAgent):
    """Analyzes document and decides processing strategy."""

    name = "planner"

    async def run(self, input_data: PlannerInput) -> AgentResult:
        try:
            # TODO: implement actual planning logic
            # - Detect if OCR needed (scanned PDF)
            # - Analyze content for dialogue (multi-speaker)
            # - Detect language
            output = PlannerOutput(
                needs_ocr=False,
                speaker_mode="single",
                emotion_level="basic",
                language="vi",
                processing_hints={},
            )
            return AgentResult(
                success=True,
                data=output,
                metadata={"file": input_data.file_path},
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))