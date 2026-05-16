"""
Experimental PDF preprocessing pipeline for chapter-aware TTS input.

Goal:
    PDF -> detected chapters -> paragraphs/plain_text -> optional chapter EPUB

Usage:
    python tests/preprocess_pdf_chapters.py
    python tests/preprocess_pdf_chapters.py book_pdf/403-dac-nhan-tam-thuviensach.vn.pdf
    python tests/preprocess_pdf_chapters.py book_pdf/1.pdf tests/pdf_chapter_pipeline_output

Outputs:
    tests/pdf_chapter_pipeline_output/<pdf-name>/chapters.json
    tests/pdf_chapter_pipeline_output/<pdf-name>/chapters.txt
    tests/pdf_chapter_pipeline_output/<pdf-name>/<pdf-name>.epub
"""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

import fitz
from ebooklib import epub


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "book_pdf" / "1.pdf"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "tests" / "pdf_chapter_pipeline_output"


VIETNAMESE_ORDINAL = (
    "NHẤT|NHÌ|HAI|BA|BỐN|TƯ|TƢ|NĂM|SÁU|BẢY|TÁM|CHÍN|MƯỜI|MƢỜI|MỘT|MỐT|"
    "MƯƠI|MƢƠI|ĐỘC NHẤT"
)
ROMAN_OR_NUMBER = r"[IVXLCDM]+|\d+"

CHAPTER_MARKER_RE = re.compile(
    rf"^\s*(?:CHƯƠNG|CHƢƠNG|CHUONG)\s+(?:{VIETNAMESE_ORDINAL}|{ROMAN_OR_NUMBER})\s*:?\s*$",
    re.IGNORECASE,
)
INLINE_CHAPTER_RE = re.compile(
    rf"^\s*(?:Chương|Chƣơng|CHƯƠNG|CHƢƠNG)\s+(?:{VIETNAMESE_ORDINAL}|{ROMAN_OR_NUMBER})\s*[:.\-]",
    re.IGNORECASE,
)
INTRO_HEADING_RE = re.compile(
    r"^\s*(LỜI\s+NHÀ\s+XUẤT\s+BẢN|VÀI\s+LỜI\s+THƯA\s+TRƯỚC|VÀI\s+LỜI\s+THƢA\s+TRƢỚC|TỰA|GIỚI\s+THIỆU|BẢNG\s+THUẬT\s+NGỮ|PHỤ\s+LỤC.*)\s*$",
    re.IGNORECASE,
)
PART_HEADING_RE = re.compile(
    r"^\s*(PHẦN\s+(?:THỨ\s+.+|\d{1,2})|Phần\s+thứ\s+.+)\s*$",
    re.IGNORECASE,
)
NUMERIC_CHAPTER_MARKER_RE = re.compile(r"^\s*\d{1,2}\s*$")


@dataclass
class PreprocessedChapter:
    index: int
    title: str
    page_start: int
    page_end: int
    paragraphs: List[str] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        return "\n".join(self.paragraphs)

    @property
    def word_count(self) -> int:
        return len(self.plain_text.split())


def normalize_space(value: str) -> str:
    value = value.replace("Ƣ", "Ư").replace("ƣ", "ư")
    return re.sub(r"\s+", " ", value).strip()


def strip_noise_line(line: str) -> Optional[str]:
    text = normalize_space(line)
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("https://") or lowered.startswith("http://"):
        return None
    if "tinyurl" in lowered or lowered.startswith("m. me/"):
        return None
    if "ebook miễn phí" in lowered or "webtietkiem.com" in lowered:
        return None
    if re.fullmatch(r"\d{3,4}", text):
        return None
    if text in {"ĐẮC NHÂN TÂM", "MỤC LỤC", "DALE CARNEGIE"}:
        return None
    return text


def is_toc_page(lines: List[str]) -> bool:
    joined = "\n".join(lines)
    dot_leaders = len(re.findall(r"\.{4,}\s*\d+", joined))
    toc_chapters = len(re.findall(r"Chương|Chƣơng", joined, re.IGNORECASE))
    has_toc = any(normalize_space(line).upper() == "MỤC LỤC" for line in lines)
    numbered_entries = sum(1 for line in lines if re.match(r"^\d{1,2}\s+\S+", line))
    bare_numbers = sum(1 for line in lines if NUMERIC_CHAPTER_MARKER_RE.match(line))
    part_entries = sum(1 for line in lines if line_is_part_heading(line))
    return (
        has_toc
        or dot_leaders >= 2
        or toc_chapters >= 4
        or numbered_entries >= 4
        or (bare_numbers >= 4 and part_entries >= 1)
        or part_entries >= 3
    )


def reindex_chapters(chapters: List[PreprocessedChapter]) -> List[PreprocessedChapter]:
    filtered = [chapter for chapter in chapters if chapter.paragraphs]
    for index, chapter in enumerate(filtered):
        chapter.index = index
    return filtered


def line_is_chapter_marker(line: str) -> bool:
    return bool(CHAPTER_MARKER_RE.match(line))


def line_is_numeric_chapter_marker(line: str) -> bool:
    return bool(NUMERIC_CHAPTER_MARKER_RE.match(line))


def line_is_intro_heading(line: str) -> bool:
    return bool(INTRO_HEADING_RE.match(line))


def line_is_part_heading(line: str) -> bool:
    return bool(PART_HEADING_RE.match(line))


def line_is_heading_like(line: str) -> bool:
    if line_is_intro_heading(line) or line_is_part_heading(line):
        return True
    if len(line.split()) > 14:
        return False
    if line.strip().casefold() == "action":
        return True
    letters = re.sub(r"[^A-Za-zÀ-ỹƢƣĐđ]", "", line)
    if not letters:
        return False
    return letters.upper() == letters


def page_lines(page: fitz.Page) -> List[str]:
    lines: List[str] = []
    for block in page.get_text("blocks"):
        block_text = block[4]
        for raw_line in block_text.splitlines():
            cleaned = strip_noise_line(raw_line)
            if cleaned:
                lines.append(cleaned)
    return lines


def finish_paragraph(lines: List[str], chapter: Optional[PreprocessedChapter]) -> None:
    if not chapter or not lines:
        lines.clear()
        return
    paragraph = normalize_space(" ".join(lines))
    if paragraph:
        chapter.paragraphs.append(paragraph)
    lines.clear()


def start_chapter(
    chapters: List[PreprocessedChapter],
    title: str,
    page_number: int,
    current: Optional[PreprocessedChapter],
    paragraph_lines: List[str],
) -> PreprocessedChapter:
    finish_paragraph(paragraph_lines, current)

    chapter = PreprocessedChapter(
        index=len(chapters),
        title=normalize_space(title),
        page_start=page_number,
        page_end=page_number,
    )
    chapters.append(chapter)
    return chapter


def collect_heading_title(lines: List[str], start_index: int) -> tuple[str, int]:
    title_lines: List[str] = []
    i = start_index
    while i < len(lines):
        candidate = lines[i]
        if (
            line_is_chapter_marker(candidate)
            or line_is_numeric_chapter_marker(candidate)
            or line_is_intro_heading(candidate)
            or line_is_part_heading(candidate)
        ):
            break
        if not line_is_heading_like(candidate):
            break
        title_lines.append(candidate)
        i += 1
    return normalize_space(" ".join(title_lines)), i


def detect_chapters(pdf_path: Path) -> List[PreprocessedChapter]:
    chapters: List[PreprocessedChapter] = []
    current: Optional[PreprocessedChapter] = None
    paragraph_lines: List[str] = []
    pending_marker: Optional[str] = None
    current_part: Optional[str] = None

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document, start=1):
            lines = page_lines(page)
            if not lines or is_toc_page(lines):
                continue

            i = 0
            while i < len(lines):
                line = lines[i]
                if current and normalize_space(line).casefold() == current.title.casefold():
                    i += 1
                    continue

                if line_is_part_heading(line):
                    current_part = line
                    finish_paragraph(paragraph_lines, current)
                    i += 1
                    continue

                if line_is_chapter_marker(line) or (
                    current_part
                    and line_is_numeric_chapter_marker(line)
                    and i + 1 < len(lines)
                    and line_is_heading_like(lines[i + 1])
                ):
                    pending_marker = line
                    finish_paragraph(paragraph_lines, current)
                    i += 1
                    continue

                if pending_marker:
                    title, next_i = collect_heading_title(lines, i)
                    if not title:
                        title = line
                        next_i = i + 1
                    if current_part:
                        title = f"{current_part} - {title}"
                    current = start_chapter(
                        chapters, title, page_index, current, paragraph_lines
                    )
                    pending_marker = None
                    i = next_i
                    continue

                if line_is_intro_heading(line):
                    current = start_chapter(
                        chapters, line, page_index, current, paragraph_lines
                    )
                    i += 1
                    continue

                if INLINE_CHAPTER_RE.match(line) and len(line.split()) <= 18:
                    title = re.sub(r"\.{3,}.*$", "", line).strip()
                    current = start_chapter(
                        chapters, title, page_index, current, paragraph_lines
                    )
                    i += 1
                    continue

                if current:
                    current.page_end = page_index

                paragraph_lines.append(line)
                if re.search(r"[.!?…”\"]$", line):
                    finish_paragraph(paragraph_lines, current)
                i += 1

    finish_paragraph(paragraph_lines, current)

    return reindex_chapters(chapters)


def chapter_to_tts_payload(chapter: PreprocessedChapter) -> dict:
    payload = asdict(chapter)
    payload["plain_text"] = chapter.plain_text
    payload["word_count"] = chapter.word_count
    return payload


def write_json(chapters: List[PreprocessedChapter], output_dir: Path, source: Path) -> Path:
    payload = {
        "source_pdf": str(source),
        "chapter_count": len(chapters),
        "chapters": [chapter_to_tts_payload(chapter) for chapter in chapters],
    }
    path = output_dir / "chapters.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_txt(chapters: List[PreprocessedChapter], output_dir: Path) -> Path:
    parts: List[str] = []
    for chapter in chapters:
        parts.append(f"# {chapter.index + 1}. {chapter.title}")
        parts.append(f"pages={chapter.page_start}-{chapter.page_end} words={chapter.word_count}")
        parts.extend(chapter.paragraphs)
        parts.append("")
    path = output_dir / "chapters.txt"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def build_chapter_html(chapter: PreprocessedChapter) -> str:
    body = "\n".join(f"    <p>{html.escape(p)}</p>" for p in chapter.paragraphs)
    title = html.escape(chapter.title)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi" xml:lang="vi">
<head>
  <title>{title}</title>
  <meta charset="utf-8"/>
</head>
<body>
  <section epub:type="chapter">
    <h1>{title}</h1>
{body}
  </section>
</body>
</html>
"""


def write_epub(chapters: List[PreprocessedChapter], output_dir: Path, source: Path) -> Path:
    book = epub.EpubBook()
    book.set_identifier(f"chapter-preprocess-{source.stem}")
    book.set_title(source.stem)
    book.set_language("vi")
    book.add_author("PDF chapter preprocessing script")

    epub_chapters = []
    for chapter in chapters:
        item = epub.EpubHtml(
            title=chapter.title,
            file_name=f"chapter_{chapter.index + 1:04d}.xhtml",
            lang="vi",
        )
        item.set_content(build_chapter_html(chapter).encode("utf-8"))
        book.add_item(item)
        epub_chapters.append(item)

    book.toc = tuple(epub_chapters)
    book.spine = ["nav", *epub_chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    path = output_dir / f"{source.stem}.epub"
    epub.write_epub(str(path), book)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect PDF chapters for TTS input.")
    parser.add_argument(
        "input_pdf",
        nargs="?",
        default=str(DEFAULT_INPUT),
        help=f"Input PDF. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="Output directory. Default: tests/pdf_chapter_pipeline_output/<pdf-name>",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_pdf = Path(args.input_pdf)
    if not input_pdf.is_absolute():
        input_pdf = PROJECT_ROOT / input_pdf

    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / input_pdf.stem
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    chapters = detect_chapters(input_pdf)
    if not chapters:
        raise RuntimeError("No chapters detected. The PDF may need OCR or custom rules.")

    json_path = write_json(chapters, output_dir, input_pdf)
    txt_path = write_txt(chapters, output_dir)
    epub_path = write_epub(chapters, output_dir, input_pdf)

    print(f"Source PDF: {input_pdf}")
    print(f"Detected chapters: {len(chapters)}")
    for chapter in chapters[:10]:
        print(
            f"  {chapter.index + 1:02d}. {chapter.title} "
            f"(pages {chapter.page_start}-{chapter.page_end}, words {chapter.word_count})"
        )
    if len(chapters) > 10:
        print(f"  ... {len(chapters) - 10} more")
    print(f"JSON: {json_path}")
    print(f"TXT: {txt_path}")
    print(f"EPUB: {epub_path}")


if __name__ == "__main__":
    main()
