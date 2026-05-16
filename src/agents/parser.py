"""
Parser Agent — Extracts text blocks from PDF/EPUB/TXT.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult
from schema.pipeline import TextBlock
from preprocessing.chapter_detector import SourcePage, clean_lines, detect_chapters, text_to_pages
from ebooklib import epub
from bs4 import BeautifulSoup
import re


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

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name=self.name, config=config)

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

    def _chapters_to_blocks(self, chapters: List[Any]) -> List[TextBlock]:
        blocks: List[TextBlock] = []
        for chapter in chapters:
            title = getattr(chapter, "title", None) or chapter.get("chapter_title", "")
            page_start = int(getattr(chapter, "page_start", None) or chapter.get("page_start", 1))
            if title:
                blocks.append(TextBlock(text=title, page=page_start, block_type="heading"))
            paragraphs = getattr(chapter, "paragraphs", None) or chapter.get("paragraphs", [])
            for paragraph in paragraphs:
                if isinstance(paragraph, dict):
                    text = paragraph.get("text", "")
                    page = int(paragraph.get("page_start", page_start))
                else:
                    text = str(paragraph)
                    page = page_start
                text = text.strip()
                if text:
                    blocks.append(TextBlock(text=text, page=page, block_type="paragraph"))
        return blocks

    def _parse_txt(self, file_path: str) -> List[Dict[str, Any]]:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        chapters = detect_chapters(text_to_pages(text), source_type="txt", drop_supplementary=True)
        return [chapter.to_dict() for chapter in chapters]

    def _parse_pdf(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            import fitz
        except Exception as exc:
            raise RuntimeError("PyMuPDF is required to parse PDF inputs") from exc

        pages: List[SourcePage] = []
        with fitz.open(file_path) as document:
            for page_index, page in enumerate(document, start=1):
                lines: List[str] = []
                for block in page.get_text("blocks"):
                    lines.extend(str(block[4]).splitlines())
                pages.append(SourcePage(page_number=page_index, lines=clean_lines(lines)))

        chapters = detect_chapters(pages, source_type="pdf", drop_supplementary=True)
        if not chapters:
            raise RuntimeError("No extractable text found. This PDF may be scanned and needs OCR first.")
        return [chapter.to_dict() for chapter in chapters]

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
                blocks = self._chapters_to_blocks(chapters)
                metadata["chapters"] = chapters
                metadata["total_chapters"] = len(chapters)
                metadata["source_type"] = "pdf"
                metadata["chapter_detection"] = "heuristic"

            elif file_type in ("txt", "text"):
                chapters = self._parse_txt(parsed.file_path)
                blocks = self._chapters_to_blocks(chapters)
                metadata["chapters"] = chapters
                metadata["total_chapters"] = len(chapters)
                metadata["source_type"] = "txt"
                metadata["chapter_detection"] = "heuristic"

            elif file_type == "epub":
                blocks = self._extract_epub_blocks(parsed.file_path)
                metadata["total_chapters"] = 1  # Simplified for now
                metadata["source_type"] = "epub"
                metadata["chapter_detection"] = "epub_blocks"

            else:
                raise ValueError(f"Unsupported file_type: {file_type}")

            total_pages = max((b.page for b in blocks), default=0)
            return AgentResult(
                success=True,
                data=ParserOutput(
                    blocks=blocks, total_pages=total_pages, metadata=metadata
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))

    def _extract_epub_blocks(self, file_path: str) -> List[TextBlock]:
        """Extract rough text blocks from EPUB, filtering TTS-unfriendly content."""
        blocks: List[TextBlock] = []
        book = epub.read_epub(file_path)
        text_types = {1, 7, 8, 9}

        # Files to skip entirely
        _SKIP_NAMES = {"nav", "cover", "titlepage", "toc", "colophon",
                        "appendix", "footnote", "endnote", "bibliography",
                        "copyright", "credits", "imprint"}
        # HTML tags to ignore (not useful for TTS)
        _SKIP_TAGS = {"aside", "footer", "figcaption", "table", "nav",
                       "script", "style", "sup", "sub", "form", "iframe",
                       "noscript", "svg", "metadata"}
        skip_attr_re = re.compile(
            r"(header|footer|footnote|endnote|note|annotation|copyright|"
            r"breadcrumb|nav|toc|pagebreak|pagenum|advert|ads|share|social)",
            re.IGNORECASE,
        )

        for item in book.get_items():
            if item.get_type() not in text_types:
                continue

            name = item.get_name().lower()
            if any(x in name for x in _SKIP_NAMES):
                continue

            try:
                content = item.get_content()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")

                soup = BeautifulSoup(content, "html.parser")

                # Remove unwanted tags before extracting text
                for tag in soup.find_all(_SKIP_TAGS):
                    tag.decompose()
                for tag in soup.find_all(attrs={"epub:type": skip_attr_re}):
                    tag.decompose()
                for tag in soup.find_all(attrs={"role": skip_attr_re}):
                    tag.decompose()
                for tag in soup.find_all(attrs={"class": skip_attr_re}):
                    tag.decompose()
                for tag in soup.find_all(attrs={"id": skip_attr_re}):
                    tag.decompose()
                for tag in soup.find_all("a"):
                    href = tag.get("href", "")
                    link_text = tag.get_text(" ", strip=True)
                    if href.startswith(("http://", "https://", "mailto:")):
                        if not link_text or link_text == href:
                            tag.decompose()
                        else:
                            tag.unwrap()

                tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "li"]
                for tag in soup.find_all(tags):
                    if tag.find(tags):
                        continue
                    text = tag.get_text(separator=" ", strip=True)
                    if not text:
                        continue
                    block_type = (
                        "heading"
                        if tag.name.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"}
                        else "paragraph"
                    )
                    blocks.append(TextBlock(text=text, page=1, block_type=block_type))
            except Exception:
                continue

        return blocks
