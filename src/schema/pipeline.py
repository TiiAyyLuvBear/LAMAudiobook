"""
Shared data types for the audiobook pipeline.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class PipelineStage(Enum):
    """Pipeline execution stages"""

    PLANNING = "planning"
    PARSING = "parsing"
    CLEANING = "cleaning"
    SPLITTING = "splitting"
    ANALYZING = "analyzing"  # parallel: classifier + voice
    GENERATING = "generating"  # parallel: TTS chunks
    FINALIZING = "finalizing"  # QC + audio concat
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineState:
    """Current state of the pipeline"""

    stage: PipelineStage = PipelineStage.PLANNING
    progress: float = 0.0
    current_chapter: int = 0
    total_chapters: int = 0
    status_message: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "progress": self.progress,
            "current_chapter": self.current_chapter,
            "total_chapters": self.total_chapters,
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_file": self.input_file,
            "output_dir": self.output_dir,
            "output_format": self.output_format,
            "max_retries": self.max_retries,
            "normalize_audio": self.normalize_audio,
            "add_chapters": self.add_chapters,
        }


@dataclass
class Chapter:
    """A chapter extracted from the document"""

    chapter_index: int
    chapter_title: str
    paragraphs: List["Paragraph"] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        if not self.paragraphs:
            return 0
        return max(p.page_end for p in self.paragraphs)

    def get_text_blocks(self) -> List["TextBlock"]:
        blocks = []
        for p in self.paragraphs:
            blocks.append(
                TextBlock(
                    text=p.text,
                    page=p.page_start,
                    block_type=(
                        "heading" if p.text == self.chapter_title else "paragraph"
                    ),
                )
            )
        return blocks


@dataclass
class Paragraph:
    """A paragraph within a chapter"""

    paragraph_index: int
    text: str
    page_start: int
    page_end: int


@dataclass
class TextBlock:
    """A block of text extracted from document"""

    text: str
    page: int
    block_type: str = "paragraph"  # "paragraph", "heading", "list"
    position: Optional[Dict[str, int]] = None


@dataclass
class ChapterBlock:
    """
    A chapter extracted from the document by the Cleaner agent.
    Used as the canonical chapter representation shared between
    Cleaner → Summarizer → Classifier.
    """

    index: int  # 0-based chapter index
    title: str  # Heading text; "Chapter 0" if no heading found
    paragraphs: List[str]  # Plain-text paragraphs (cleaned)
    paragraph_blocks: List[TextBlock] = field(
        default_factory=list
    )  # Original blocks for re-use

    @property
    def plain_text(self) -> str:
        """Concatenated plain text of this chapter."""
        return "\n".join(self.paragraphs)

    @property
    def word_count(self) -> int:
        return len(self.plain_text.split())


@dataclass
class Sentence:
    """A single sentence with analysis metadata"""

    text: str
    type: str = "narration"  # "narration" or "dialogue"
    speaker: str = "narrator"
    emotion: str = "neutral"  # "neutral", "happy", "sad", "angry", etc.
    intensity: float = 0.5  # 0.0 - 1.0
    chapter_index: int = 1
    paragraph_index: int = 1
