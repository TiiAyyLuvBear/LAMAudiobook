"""
Pipeline state management.
"""

from .config import PipelineState, PipelineStage
from .progress import STAGE_PROGRESS_FLOORS


class StateManager:
    """Manages pipeline state transitions and progress tracking."""

    STAGE_ORDER = [
        PipelineStage.PLANNING,
        PipelineStage.PARSING,
        PipelineStage.CLEANING,
        PipelineStage.SPLITTING,
        PipelineStage.ANALYZING,
        PipelineStage.GENERATING,
        PipelineStage.FINALIZING,
        PipelineStage.COMPLETED,
    ]

    def __init__(self):
        self._state = PipelineState()

    @property
    def state(self) -> PipelineState:
        return self._state

    def set_stage(self, stage: PipelineStage) -> None:
        """Update current stage and advance progress monotonically."""
        self._state.stage = stage
        self.set_progress(STAGE_PROGRESS_FLOORS.get(stage, self._state.progress))

    def set_error(self, error: str) -> None:
        self._state.stage = PipelineStage.FAILED
        self._state.error = error

    def set_chapters(self, total: int) -> None:
        self._state.total_chapters = total

    def update_chapter(self, current: int) -> None:
        self._state.current_chapter = current

    def set_segments(self, total: int) -> None:
        self._state.total_segments = total
        self._state.global_segment_total = total

    def update_segment(self, current: int) -> None:
        self._state.current_segment = current
        self._state.global_segment_current = current

    def set_chapter_segments(self, total: int) -> None:
        self._state.chapter_segment_total = total

    def update_chapter_segment(self, current: int) -> None:
        self._state.chapter_segment_current = current

    def set_global_segments(self, total: int) -> None:
        self._state.total_segments = total
        self._state.global_segment_total = total

    def update_global_segment(self, current: int) -> None:
        self._state.current_segment = current
        self._state.global_segment_current = current

    def add_artifact(self, artifact: dict) -> None:
        self._state.artifacts.append(artifact)

    def set_progress(self, progress: float) -> None:
        clamped = max(0.0, min(1.0, float(progress)))
        self._state.progress = max(self._state.progress, clamped)

    def set_status(self, message: str) -> None:
        self._state.status_message = message

    def to_dict(self) -> dict:
        return self._state.to_dict()
