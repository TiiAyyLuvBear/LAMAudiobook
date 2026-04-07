"""
Agents Module - Agentic AI System

Agents are internal execution units with:
- Clear input/output via .run() method
- No side effects (unless explicitly needed)
- Never call each other directly (orchestrated by workflows)

Agent Categories:
- Planner: Decides OCR, speaker mode, emotion level
- Document: Parser, Cleaner, Chapter detector
- Understanding: Narrative, Dialogue analysis
- Audio: Voice planner, TTS generator, Post-processing
- QC: Quality control validation
- Memory: Speaker voice consistency
"""

from .base import BaseAgent, AgentResult, AgentStatus

__all__ = ["BaseAgent", "AgentResult", "AgentStatus"]
