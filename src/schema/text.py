"""
Text-processing data types for the pipeline.
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from enum import Enum

if TYPE_CHECKING:
    from .pipeline import Chapter, Sentence


class TextType(Enum):
    """Type of text segment"""
    NARRATION = "narration"
    DIALOGUE = "dialogue"
    MIXED = "mixed"


@dataclass
class AnnotatedSegment:
    """A text segment with narration/dialogue annotation"""
    text: str
    text_type: TextType
    confidence: float
    speaker: str = "narrator"
    emotion: str = "neutral"
    intensity: float = 0.5
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ClassifierInput:
    """Input for the classifier agent (combines narrative + dialogue analysis)"""
    chapters: List["Chapter"]
    emotion_level: str = "basic"  # "none", "basic", "full"


@dataclass
class ClassifierOutput:
    """Output from the classifier agent"""
    annotated_chapters: List[Dict[str, Any]]
    sentences: List["Sentence"]
    speakers: List[str]
    speaker_count: int
    dialogue_ratio: float
    metadata: Dict[str, Any] = field(default_factory=dict)
