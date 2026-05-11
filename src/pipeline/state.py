"""
Pipeline state management.
"""

from .config import PipelineState, PipelineStage


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
        """Update current stage and recalculate progress."""
        self._state.stage = stage
        try:
            idx = self.STAGE_ORDER.index(stage)
            # Exclude COMPLETED from progress calc
            total = len(self.STAGE_ORDER) - 1
            self._state.progress = idx / total
        except ValueError:
            self._state.progress = 0.0

    def set_error(self, error: str) -> None:
        self._state.stage = PipelineStage.FAILED
        self._state.error = error

    def set_chapters(self, total: int) -> None:
        self._state.total_chapters = total

    def update_chapter(self, current: int) -> None:
        self._state.current_chapter = current

    def set_segments(self, total: int) -> None:
        self._state.total_segments = total

    def update_segment(self, current: int) -> None:
        self._state.current_segment = current

    def set_progress(self, progress: float) -> None:
        self._state.progress = max(0.0, min(1.0, float(progress)))

    def set_status(self, message: str) -> None:
        self._state.status_message = message

    def to_dict(self) -> dict:
        return self._state.to_dict()
