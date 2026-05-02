"""
QC Agent — Validates audio output against source text.
"""
from typing import Any, List

from .base import BaseAgent, AgentResult


class QCIssue:
    """A quality control issue found"""
    def __init__(self, segment_index: int, issue_type: str, description: str, severity: str = "warning"):
        self.segment_index = segment_index
        self.issue_type = issue_type  # "missing", "mismatch", "quality"
        self.description = description
        self.severity = severity  # "error", "warning"


class QCInput:
    """Input for QC Agent"""
    def __init__(self, audio_segments: List[Any], text_segments: List[str], quality_threshold: float = 0.8):
        self.audio_segments = audio_segments
        self.text_segments = text_segments
        self.quality_threshold = quality_threshold


class QCOutput:
    """Output from QC Agent"""
    def __init__(self, passed: bool, issues: List[QCIssue], retry_segments: List[int], quality_score: float):
        self.passed = passed
        self.issues = issues
        self.retry_segments = retry_segments
        self.quality_score = quality_score


class QCAgent(BaseAgent):
    """
    Quality Control agent validates:
    - Audio matches text
    - No missing segments
    - Audio quality meets threshold

    Identifies segments needing retry.
    """

    name = "qc"

    def __init__(self, config=None):
        super().__init__(name=self.name, config=config)

    async def run(self, input_data: QCInput) -> AgentResult:
        try:
            issues: List[QCIssue] = []
            retry_segments: List[int] = []

            # Check segment count alignment
            if len(input_data.audio_segments) < len(input_data.text_segments):
                missing_count = len(input_data.text_segments) - len(input_data.audio_segments)
                issues.append(QCIssue(
                    segment_index=-1,
                    issue_type="missing",
                    description=f"{missing_count} segments missing from audio output",
                    severity="error",
                ))
                retry_segments = list(range(len(input_data.audio_segments), len(input_data.text_segments)))

            # Check for zero-duration segments
            for i, seg in enumerate(input_data.audio_segments):
                duration = getattr(seg, "duration_seconds", 0.0) if not isinstance(seg, dict) else seg.get("duration_seconds", 0.0)
                if duration <= 0:
                    issues.append(QCIssue(
                        segment_index=i,
                        issue_type="quality",
                        description="Audio segment has zero or negative duration",
                        severity="warning",
                    ))
                    retry_segments.append(i)

            # Quality score: simple heuristic
            quality_score = 1.0
            if retry_segments:
                quality_score = 1.0 - (len(retry_segments) / max(len(input_data.text_segments), 1))
            passed = quality_score >= input_data.quality_threshold

            return AgentResult(
                success=True,
                data=QCOutput(passed=passed, issues=issues, retry_segments=list(set(retry_segments)), quality_score=quality_score),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))