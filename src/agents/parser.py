"""
Parser Agent — Extracts text blocks from PDF/EPUB/TXT.
"""
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult
from schema.pipeline import TextBlock


class ParserInput:
    """Input for Parser Agent"""
    def __init__(self, file_path: str, file_type: str, needs_ocr: bool = False):
        self.file_path = file_path
        self.file_type = file_type
        self.needs_ocr = needs_ocr


class ParserOutput:
    """Output from Parser Agent"""
    def __init__(self, blocks: List[TextBlock], total_pages: int, metadata: Dict):
        self.blocks = blocks
        self.total_pages = total_pages
        self.metadata = metadata


class ParserAgent(BaseAgent):
    """Extracts text blocks from documents (PDF, EPUB, TXT)."""

    name = "parser"

    def _to_parser_input(self, input_data: Any) -> ParserInput:
        if isinstance(input_data, ParserInput):
            return input_data
        if isinstance(input_data, dict):
            return ParserInput(
                file_path=input_data.get("file_path", ""),
                file_type=input_data.get("file_type", ""),
                needs_ocr=bool(input_data.get("needs_ocr", False)),
            )
        raise ValueError("ParserInput must be ParserInput or dict")

    def _parse_txt(self, file_path: str) -> List[TextBlock]:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return [
            TextBlock(text=p, page=1, block_type="paragraph")
            for p in paragraphs
        ]

    def _parse_pdf(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            from agents.document.parser.pdf_preprocess import preprocess_pdf
            return preprocess_pdf(file_path)
        except Exception:
            # fallback: minimal TXT parse
            return self._parse_txt_as_chapters(file_path)

    def _parse_txt_as_chapters(self, file_path: str) -> List[Dict]:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        return [{"chapter_title": "Chapter 1", "paragraphs": [{"text": text, "page_start": 1, "page_end": 1}]}]

    async def run(self, input_data: ParserInput) -> AgentResult:
        try:
            parsed = self._to_parser_input(input_data)
            file_type = parsed.file_type.lower()
            blocks: List[TextBlock] = []
            metadata: Dict[str, Any] = {
                "file": parsed.file_path,
                "file_type": file_type,
                "needs_ocr": parsed.needs_ocr,
            }

            if file_type == "pdf":
                chapters = self._parse_pdf(parsed.file_path)
                for chapter in chapters:
                    title = chapter.get("chapter_title", "")
                    for para in chapter.get("paragraphs", []):
                        p_text = para.get("text", "").strip()
                        if not p_text:
                            continue
                        page = int(para.get("page_start", 1))
                        block_type = "heading" if p_text == title else "paragraph"
                        blocks.append(TextBlock(text=p_text, page=page, block_type=block_type))
                metadata["chapters"] = chapters
                metadata["total_chapters"] = len(chapters)

            elif file_type in ("txt", "text"):
                blocks = self._parse_txt(parsed.file_path)
                metadata["total_chapters"] = 1

            elif file_type == "epub":
                # minimal fallback
                blocks = self._parse_txt(parsed.file_path)
                metadata["total_chapters"] = 1

            else:
                raise ValueError(f"Unsupported file_type: {file_type}")

            total_pages = max((b.page for b in blocks), default=0)
            return AgentResult(
                success=True,
                data=ParserOutput(blocks=blocks, total_pages=total_pages, metadata=metadata),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))