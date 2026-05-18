"""
Pipeline configuration and state types.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
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
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
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
            "artifacts": self.artifacts or [],
            "status_message": self.status_message,
            "error": self.error,
        }


@dataclass
class PipelineConfig:
    """Configuration for the audiobook pipeline"""
    input_file: str
    output_dir: str
    source_filename: Optional[str] = None
    output_format: str = "mp3"
    max_retries: int = 3
    normalize_audio: bool = True
    add_chapters: bool = True
    analysis_enabled: bool = True
    tts_engine: str = "xtts_gpu"
    tts_device: str = "auto"
    tts_speaker_mode: str = "single"
    xtts_model_name_or_path: Optional[str] = None
    xtts_config_path: Optional[str] = None
    xtts_vocab_path: Optional[str] = None
    xtts_voice_dir: str = "data/voice_samples"
    vieneu_model_name: str = "pnnbao-ump/VieNeu-TTS-0.3B"
    vieneu_mode: str = "standard"
    vieneu_emotion: str = "storytelling"
    vieneu_api_base: Optional[str] = None
    vieneu_device: str = "auto"
    vieneu_lora_adapter: Optional[str] = None
    stage_output_callback: Optional[Callable[[str, str, Any], None]] = None

    def __post_init__(self) -> None:
        self.tts_speaker_mode = (self.tts_speaker_mode or "single").strip().lower()
        if self.tts_speaker_mode not in {"single", "multi"}:
            raise ValueError("tts_speaker_mode must be 'single' or 'multi'.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_file": self.input_file,
            "output_dir": self.output_dir,
            "source_filename": self.source_filename,
            "output_format": self.output_format,
            "max_retries": self.max_retries,
            "normalize_audio": self.normalize_audio,
            "add_chapters": self.add_chapters,
            "analysis_enabled": self.analysis_enabled,
            "tts_engine": self.tts_engine,
            "tts_device": self.tts_device,
            "tts_speaker_mode": self.tts_speaker_mode,
            "xtts_model_name_or_path": self.xtts_model_name_or_path,
            "xtts_config_path": self.xtts_config_path,
            "xtts_vocab_path": self.xtts_vocab_path,
            "xtts_voice_dir": self.xtts_voice_dir,
            "vieneu_model_name": self.vieneu_model_name,
            "vieneu_mode": self.vieneu_mode,
            "vieneu_emotion": self.vieneu_emotion,
            "vieneu_api_base": self.vieneu_api_base,
            "vieneu_device": self.vieneu_device,
            "vieneu_lora_adapter": self.vieneu_lora_adapter,
            "stage_output_callback": bool(self.stage_output_callback),
        }
