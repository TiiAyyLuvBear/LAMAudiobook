"""
Agents Module — Agentic AI System (flat structure).

Each agent has:
- Clear input/output via .run() method
- No side effects (unless explicitly needed)
- Never call each other directly (orchestrated by pipeline)

Agent Index:
- planner    : Decides OCR need, speaker mode, emotion level, language
- parser     : Extracts text from PDF/EPUB/TXT
- cleaner    : Removes headers, footers, page numbers, noise
- splitter   : Detects and splits document into chapters
- classifier : Classifies narration/dialogue + detects speakers/emotions
- voice      : Assigns TTS voice IDs to speakers
- tts        : Converts annotated text → audio (XTTSv2)
- audio      : Concatenate, normalize, add chapter markers
- qc         : Validates audio quality, flags segments for retry
- memory     : Maintains speaker voice consistency across chapters
"""

from .base import BaseAgent, AgentResult, AgentStatus

# Expose all flat agents
from .planner import PlannerAgent, PlannerInput, PlannerOutput
from .parser import ParserAgent, ParserInput, ParserOutput
from .cleaner import CleanerAgent, CleanerInput, CleanerOutput
from .splitter import SplitterAgent, SplitterInput, SplitterOutput
from .classifier import ClassifierAgent, ClassifierInput, ClassifierOutput
from .voice import VoiceAgent, VoiceInput, VoiceOutput
from .tts import TTSAgent, TTSGeneratorInput, TTSGeneratorOutput
from .audio import AudioAgent, AudioFinalizeInput, AudioFinalizeOutput
from .qc import QCAgent, QCInput, QCOutput, QCIssue
from .memory import MemoryAgent, MemoryInput, MemoryOutput, SpeakerMemory

__all__ = [
    # base
    "BaseAgent",
    "AgentResult",
    "AgentStatus",
    # agents
    "PlannerAgent",
    "PlannerInput",
    "PlannerOutput",
    "ParserAgent",
    "ParserInput",
    "ParserOutput",
    "CleanerAgent",
    "CleanerInput",
    "CleanerOutput",
    "SplitterAgent",
    "SplitterInput",
    "SplitterOutput",
    "ClassifierAgent",
    "ClassifierInput",
    "ClassifierOutput",
    "VoiceAgent",
    "VoiceInput",
    "VoiceOutput",
    "TTSAgent",
    "TTSGeneratorInput",
    "TTSGeneratorOutput",
    "AudioAgent",
    "AudioFinalizeInput",
    "AudioFinalizeOutput",
    "QCAgent",
    "QCInput",
    "QCOutput",
    "QCIssue",
    "MemoryAgent",
    "MemoryInput",
    "MemoryOutput",
    "SpeakerMemory",
]