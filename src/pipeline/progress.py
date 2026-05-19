"""Progress helpers for monotonic audiobook pipeline state."""

from __future__ import annotations

from dataclasses import dataclass

from .config import PipelineStage


STAGE_PROGRESS_FLOORS = {
    PipelineStage.PLANNING: 0.00,
    PipelineStage.PARSING: 0.03,
    PipelineStage.CLEANING: 0.08,
    PipelineStage.SPLITTING: 0.10,
    PipelineStage.ANALYZING: 0.12,
    PipelineStage.GENERATING: 0.15,
    PipelineStage.FINALIZING: 0.95,
    PipelineStage.COMPLETED: 1.00,
    PipelineStage.FAILED: 0.00,
}


@dataclass
class SegmentProgress:
    chapter_index: int = 0
    total_chapters: int = 0
    chapter_completed_segments: int = 0
    chapter_total_segments: int = 0
    completed_segments: int = 0
    total_segments: int = 0

    def generation_progress(self) -> float:
        if self.total_segments <= 0:
            return STAGE_PROGRESS_FLOORS[PipelineStage.GENERATING]
        completed = max(0, min(self.completed_segments, self.total_segments))
        return 0.15 + (completed / self.total_segments) * 0.80

    def status(self) -> str:
        return (
            f"Generating TTS segment {self.chapter_completed_segments}/{self.chapter_total_segments} "
            f"(global {self.completed_segments}/{self.total_segments})"
        )
