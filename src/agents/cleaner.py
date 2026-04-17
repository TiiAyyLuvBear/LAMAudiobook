"""
Cleaner Agent — Removes headers, footers, page numbers, noise.
"""
from typing import Any, List

from .base import BaseAgent, AgentResult
from types.pipeline import TextBlock


class CleanerInput:
    """Input for Cleaner Agent"""
    def __init__(self, text_blocks: List[Any], remove_headers: bool = True,
                 remove_footers: bool = True, remove_page_numbers: bool = True):
        self.text_blocks = text_blocks
        self.remove_headers = remove_headers
        self.remove_footers = remove_footers
        self.remove_page_numbers = remove_page_numbers


class CleanerOutput:
    """Output from Cleaner Agent"""
    def __init__(self, cleaned_blocks: List[TextBlock], removed_count: int, metadata: dict):
        self.cleaned_blocks = cleaned_blocks
        self.removed_count = removed_count
        self.metadata = metadata


class CleanerAgent(BaseAgent):
    """Cleans extracted text by removing headers, footers, page numbers, noise."""

    name = "cleaner"

    async def run(self, input_data: CleanerInput) -> AgentResult:
        try:
            # TODO: implement cleaning logic
            # - Detect repeated headers/footers across pages
            # - Remove page numbers
            # - Clean OCR artifacts
            cleaned = []
            removed = 0

            for block in input_data.text_blocks:
                text = getattr(block, "text", str(block)) if not isinstance(block, dict) else block.get("text", "")
                if not text:
                    removed += 1
                    continue
                # Fallback: pass through with basic filtering
                t = text.strip()
                if t and not t.lower() in ("trang", "page"):
                    cleaned.append(
                        TextBlock(text=t, page=getattr(block, "page", 1) if not isinstance(block, dict) else block.get("page", 1), block_type=getattr(block, "block_type", "paragraph") if not isinstance(block, dict) else block.get("block_type", "paragraph"))
                    )
                else:
                    removed += 1

            return AgentResult(
                success=True,
                data=CleanerOutput(cleaned_blocks=cleaned, removed_count=removed, metadata={}),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))