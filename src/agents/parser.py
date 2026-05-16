"""
Parser Agent — Extracts text blocks from PDF/EPUB/TXT.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult
from schema.pipeline import TextBlock
from preprocessing.chapter_detector import SourcePage, clean_lines, detect_chapters, is_toc_page, normalize_space, text_to_pages
from ebooklib import epub
from bs4 import BeautifulSoup
import re


EPUB_FRONTMATTER_RE = re.compile(
    r"^(?:"
    r"mục\s*lục|table\s+of\s+contents|toc|nav|"
    r"bìa|cover|title\s*page|trang\s+bìa|"
    r"lời\s+(?:giới\s+thiệu|nói\s+đầu|tựa|nhà\s+xuất\s+bản|cảm\s+ơn)|"
    r"giới\s+thiệu|tựa|preface|foreword|introduction|acknowledg(?:e)?ments?|"
    r"copyright|bản\s+quyền|credits?|imprint|colophon|thông\s+tin\s+ebook"
    r")\b",
    re.IGNORECASE,
)
EPUB_BACKMATTER_RE = re.compile(
    r"^(?:phụ\s*lục|appendix|glossary|bibliography|tài\s+liệu\s+tham\s+khảo|"
    r"chú\s+thích|footnotes?|endnotes?)\b",
    re.IGNORECASE,
)
EPUB_CHAPTER_HINT_RE = re.compile(
    r"^(?:chương|chuong|chapter|hồi|hoi|phần\s+(?:thứ|\d+)|part\s+\d+|\d{1,3}[.:\-]\s+\S)",
    re.IGNORECASE,
)


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
                blocks, epub_metadata = self._extract_epub_blocks(parsed.file_path)
                metadata.update(epub_metadata)
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

    def _ordered_epub_items(self, book: Any) -> List[Any]:
        id_map = {item.get_id(): item for item in book.get_items() if item is not None}
        ordered: List[Any] = []
        seen = set()
        for spine_entry in getattr(book, "spine", []) or []:
            item_id = spine_entry[0] if isinstance(spine_entry, (tuple, list)) else spine_entry
            item = id_map.get(item_id)
            if item is not None and item.get_id() not in seen:
                ordered.append(item)
                seen.add(item.get_id())
        for item in book.get_items():
            if item is None:
                continue
            item_id = item.get_id()
            if item_id not in seen:
                ordered.append(item)
                seen.add(item_id)
        return ordered

    def _clean_epub_soup(self, soup: BeautifulSoup) -> None:
        _SKIP_TAGS = {
            "aside", "footer", "figcaption", "table", "nav", "script", "style",
            "sup", "sub", "form", "iframe", "noscript", "svg", "metadata",
        }
        skip_attr_re = re.compile(
            r"(header|footer|footnote|endnote|note|annotation|copyright|"
            r"breadcrumb|nav|toc|pagebreak|pagenum|advert|ads|share|social)",
            re.IGNORECASE,
        )
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

    def _epub_identity_text(self, item: Any, soup: BeautifulSoup) -> str:
        values = [item.get_name() or ""]
        title = soup.find("title")
        if title:
            values.append(title.get_text(" ", strip=True))
        first_heading = soup.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if first_heading:
            values.append(first_heading.get_text(" ", strip=True))
        return normalize_space(" ".join(values))

    def _is_epub_frontmatter(self, identity: str, lines: List[str]) -> bool:
        normalized_identity = normalize_space(identity).lower()
        basename = Path(normalized_identity).stem
        if EPUB_FRONTMATTER_RE.search(normalized_identity) or EPUB_FRONTMATTER_RE.search(basename):
            return True
        if is_toc_page(lines):
            return True
        short_lines = [line for line in lines if len(line.split()) <= 14]
        if lines and len(short_lines) / max(1, len(lines)) > 0.85 and len(lines) >= 8:
            chapter_entries = sum(1 for line in lines if EPUB_CHAPTER_HINT_RE.match(line))
            if chapter_entries >= 4:
                return True
        return False

    def _is_epub_backmatter(self, identity: str, lines: List[str]) -> bool:
        normalized_identity = normalize_space(identity).lower()
        basename = Path(normalized_identity).stem
        first_line = normalize_space(lines[0]).lower() if lines else ""
        return bool(
            EPUB_BACKMATTER_RE.search(normalized_identity)
            or EPUB_BACKMATTER_RE.search(basename)
            or EPUB_BACKMATTER_RE.search(first_line)
        )

    def _has_epub_chapter_hint(self, blocks: List[TextBlock]) -> bool:
        for block in blocks[:4]:
            if block.block_type == "heading" and EPUB_CHAPTER_HINT_RE.match(normalize_space(block.text)):
                return True
        if blocks and EPUB_CHAPTER_HINT_RE.match(normalize_space(blocks[0].text)):
            return True
        return False

    def _extract_epub_blocks(self, file_path: str) -> tuple[List[TextBlock], Dict[str, Any]]:
        """Extract rough text blocks from EPUB, filtering TTS-unfriendly front/back matter."""
        book = epub.read_epub(file_path)
        text_types = {1, 7, 8, 9}
        item_payloads: List[Dict[str, Any]] = []
        skipped_frontmatter = 0
        skipped_backmatter = 0

        for item in self._ordered_epub_items(book):
            if item is None or item.get_type() not in text_types:
                continue

            try:
                content = item.get_content()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")

                soup = BeautifulSoup(content, "html.parser")
                identity = self._epub_identity_text(item, soup)
                self._clean_epub_soup(soup)

                tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "li"]
                blocks: List[TextBlock] = []
                lines: List[str] = []
                for tag in soup.find_all(tags):
                    if tag.find(tags):
                        continue
                    text = tag.get_text(separator=" ", strip=True)
                    text = normalize_space(text)
                    if not text:
                        continue
                    block_type = (
                        "heading"
                        if tag.name.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"}
                        else "paragraph"
                    )
                    blocks.append(TextBlock(text=text, page=len(item_payloads) + 1, block_type=block_type))
                    lines.append(text)

                lines = clean_lines(lines)
                if not blocks or self._is_epub_frontmatter(identity, lines):
                    skipped_frontmatter += 1
                    continue
                if self._is_epub_backmatter(identity, lines):
                    skipped_backmatter += 1
                    continue
                item_payloads.append(
                    {
                        "name": item.get_name(),
                        "identity": identity,
                        "blocks": blocks,
                        "has_chapter_hint": self._has_epub_chapter_hint(blocks),
                    }
                )
            except Exception:
                continue

        first_chapter_index = next(
            (index for index, payload in enumerate(item_payloads) if payload["has_chapter_hint"]),
            None,
        )
        if first_chapter_index and first_chapter_index > 0:
            skipped_frontmatter += first_chapter_index
            item_payloads = item_payloads[first_chapter_index:]

        blocks: List[TextBlock] = []
        for page, payload in enumerate(item_payloads, start=1):
            for block in payload["blocks"]:
                blocks.append(TextBlock(text=block.text, page=page, block_type=block.block_type))

        metadata = {
            "total_chapters": sum(1 for block in blocks if block.block_type == "heading") or 1,
            "epub_items_kept": len(item_payloads),
            "epub_frontmatter_skipped": skipped_frontmatter,
            "epub_backmatter_skipped": skipped_backmatter,
        }
        return blocks, metadata

