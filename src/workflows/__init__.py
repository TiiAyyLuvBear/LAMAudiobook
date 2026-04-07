"""
Workflows Module - Centralized Pipeline Orchestration

Rules:
- Only workflows call agents
- Agents never call each other directly
- Workflow controls execution flow
"""

from .audiobook_pipeline import AudiobookPipeline

__all__ = ["AudiobookPipeline"]
