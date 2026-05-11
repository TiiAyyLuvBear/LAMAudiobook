"""
Pipeline configuration and state types.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional
from enum import Enum


class PipelineStage(Enum):
    """Pipeline execution stages"""
    PLANNING = "planning"
    PARSING = "parsing"
    CLEANING = "cleaning"
    SPLITTING = "splitting"
    ANALYZING = "analyzing"       # parallel: classifier + voice + memory
    GENERATING = "generating"    # parallel: TTS segment batches
    FINALIZING = "finalizing"    # sequential: QC + audio concat
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineState:
    """Current state of the pipeline"""
    stage: PipelineStage = PipelineStage.PLANNING
    progress: float = 0.0
    current_chapter: int = 0
    total_chapters: int = 0
    current_segment: int = 0
    total_segments: int = 0
    status_message: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "progress": self.progress,
            "current_chapter": self.current_chapter,
            "total_chapters": self.total_chapters,
            "current_segment": self.current_segment,
            "total_segments": self.total_segments,
            "status_message": self.status_message,
            "error": self.error,
        }


@dataclass
class PipelineConfig:
    """Configuration for the audiobook pipeline"""
    input_file: str
    output_dir: str
    output_format: str = "mp3"
    max_retries: int = 3
    normalize_audio: bool = True
    add_chapters: bool = True
    analysis_enabled: bool = True
    tts_engine: str = "xtts_gpu"
    xtts_model_name_or_path: Optional[str] = None
    xtts_config_path: Optional[str] = None
    xtts_vocab_path: Optional[str] = None
    xtts_voice_dir: str = "data/voice_samples"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_file": self.input_file,
            "output_dir": self.output_dir,
            "output_format": self.output_format,
            "max_retries": self.max_retries,
            "normalize_audio": self.normalize_audio,
            "add_chapters": self.add_chapters,
            "analysis_enabled": self.analysis_enabled,
            "tts_engine": self.tts_engine,
            "xtts_model_name_or_path": self.xtts_model_name_or_path,
            "xtts_config_path": self.xtts_config_path,
            "xtts_vocab_path": self.xtts_vocab_path,
            "xtts_voice_dir": self.xtts_voice_dir,
        }
