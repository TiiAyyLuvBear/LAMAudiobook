"""
Shared types package.
"""
from .pipeline import (
    PipelineConfig,
    PipelineState,
    PipelineStage,
    Chapter,
    Paragraph,
    TextBlock,
    Sentence,
)
from .audio import (
    TTSSegment,
    AudioSegment,
    VoiceAssignment,
    TTSGeneratorInput,
    TTSGeneratorOutput,
    AudioFinalizeInput,
    AudioFinalizeOutput,
)

__all__ = [
    # pipeline
    "PipelineConfig",
    "PipelineState",
    "PipelineStage",
    "Chapter",
    "Paragraph",
    "TextBlock",
    "Sentence",
    # audio
    "TTSSegment",
    "AudioSegment",
    "VoiceAssignment",
    "TTSGeneratorInput",
    "TTSGeneratorOutput",
    "AudioFinalizeInput",
    "AudioFinalizeOutput",
]
