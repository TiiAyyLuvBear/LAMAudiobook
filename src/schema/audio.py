"""
Audio-related data types for the pipeline.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TTSSegment:
    """A segment to be synthesized by TTS"""
    text: str
    voice_id: str
    emotion: Optional[str] = None
    intensity: float = 1.0
    speed: float = 1.0
    chapter_index: int = 1
    segment_index: int = 0
    speaker: str = "narrator"


@dataclass
class AudioSegment:
    """Generated audio segment"""
    file_path: str
    duration_seconds: float
    segment_index: int
    chapter_index: int = 1
    text: str = ""
    voice_id: str = "default"


@dataclass
class VoiceAssignment:
    """Voice assignment for a speaker"""
    speaker: str
    voice_id: str
    voice_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSGeneratorInput:
    """Input for TTS generation stage"""
    segments: List[TTSSegment]
    output_dir: str
    format: str = "wav"
    global_total_segments: int = 0
    completed_segment_offset: int = 0
    chapter_total_segments: int = 0


@dataclass
class TTSGeneratorOutput:
    """Output from TTS generation"""
    audio_segments: List[AudioSegment]
    total_duration: float
    failed_segments: List[int]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AudioFinalizeInput:
    """Input for final audio processing stage"""
    audio_segments: List[AudioSegment]
    output_path: str
    normalize: bool = True
    add_chapter_markers: bool = True
    output_format: str = "mp3"


@dataclass
class AudioFinalizeOutput:
    """Output from final audio processing"""
    final_audio_path: str
    total_duration: float
    chapters: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
