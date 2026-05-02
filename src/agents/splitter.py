"""
Splitter Agent — Detects and splits document into chapters.
"""
from typing import Any, List

from .base import BaseAgent, AgentResult
from schema.pipeline import Chapter, Paragraph


class SplitterInput:
    """Input for Splitter Agent"""
    def __init__(self, text_blocks: List[Any]):
        self.text_blocks = text_blocks


class SplitterOutput:
    """Output from Splitter Agent"""
    def __init__(self, chapters: List[Chapter], total_chapters: int):
        self.chapters = chapters
        self.total_chapters = total_chapters


class SplitterAgent(BaseAgent):
    """
    Detects and splits document into chapters.

    Detection methods:
    - Heading-based (detect "Chương X" / "Chapter X" patterns)
    - Structure-based (large gaps, style changes)
    - Pattern matching (regex)
    """

    name = "splitter"

    def __init__(self, config=None):
        super().__init__(name=self.name, config=config)

    async def run(self, input_data: SplitterInput) -> AgentResult:
        try:
            # TODO: implement chapter detection
            # - Find chapter headings via regex
            # - Split blocks into Chapter objects

            # Fallback: put all blocks into one chapter
            blocks = input_data.text_blocks
            paragraphs = []
            for i, block in enumerate(blocks, 1):
                text = getattr(block, "text", str(block)) if not isinstance(block, dict) else block.get("text", "")
                page = getattr(block, "page", 1) if not isinstance(block, dict) else block.get("page", 1)
                paragraphs.append(
                    Paragraph(
                        paragraph_index=i,
                        text=text,
                        page_start=page,
                        page_end=page,
                    )
                )

            chapter = Chapter(
                chapter_index=1,
                chapter_title="Chapter 1",
                paragraphs=paragraphs,
            )

            return AgentResult(
                success=True,
                data=SplitterOutput(chapters=[chapter], total_chapters=1),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))