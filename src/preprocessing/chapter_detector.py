"""
Chapter-aware preprocessing for PDF/TXT inputs.

The detector is intentionally heuristic. It normalizes noisy extracted text into
chapter dictionaries that ParserAgent can convert into TextBlocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional


VIETNAMESE_ORDINAL = (
    "NHẤT|NHÌ|HAI|BA|BỐN|TƯ|TƢ|NĂM|SÁU|BẢY|TÁM|CHÍN|MƯỜI|MƢỜI|MỘT|MỐT|"
    "MƯƠI|MƢƠI|ĐỘC NHẤT"
)
ROMAN_OR_NUMBER = r"[IVXLCDM]+|\d+"

CHAPTER_MARKER_RE = re.compile(
    rf"^\s*(?:CHƯƠNG|CHƢƠNG|CHUONG|CHAPTER)\s+(?:{VIETNAMESE_ORDINAL}|{ROMAN_OR_NUMBER})\s*:?\s*$",
    re.IGNORECASE,
)
INLINE_CHAPTER_RE = re.compile(
    rf"^\s*(?:Chương|Chƣơng|CHƯƠNG|CHƢƠNG|Chapter)\s+(?:{VIETNAMESE_ORDINAL}|{ROMAN_OR_NUMBER})\s*[:.\-]",
    re.IGNORECASE,
)
PART_HEADING_RE = re.compile(
    r"^\s*(PHẦN\s+(?:THỨ\s+.+|\d{1,2})|Phần\s+thứ\s+.+|PART\s+\d{1,2})\s*$",
    re.IGNORECASE,
)
SUPPLEMENTARY_HEADING_RE = re.compile(
    r"^\s*(LỜI\s+NHÀ\s+XUẤT\s+BẢN|VÀI\s+LỜI\s+THƯA\s+TRƯỚC|VÀI\s+LỜI\s+THƢA\s+TRƢỚC|"
    r"TỰA|GIỚI\s+THIỆU|BẢNG\s+THUẬT\s+NGỮ|PHỤ\s+LỤC.*|PREFACE|INTRODUCTION|APPENDIX.*|GLOSSARY)\s*$",
    re.IGNORECASE,
)
NUMERIC_CHAPTER_MARKER_RE = re.compile(r"^\s*\d{1,2}\s*$")


@dataclass
class SourcePage:
    page_number: int
    lines: List[str]


@dataclass
class DetectedChapter:
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

    def to_dict(self) -> dict:
        return {
            "chapter_index": self.index,
            "chapter_title": self.title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "paragraphs": [
                {
                    "text": paragraph,
                    "page_start": self.page_start,
                    "page_end": self.page_end,
                }
                for paragraph in self.paragraphs
            ],
            "plain_text": self.plain_text,
            "word_count": self.word_count,
        }


def normalize_space(value: str) -> str:
    value = value.replace("Ƣ", "Ư").replace("ƣ", "ư")
    return re.sub(r"\s+", " ", value).strip()


def _strip_noise_line(line: str) -> Optional[str]:
    text = normalize_space(line)
    if not text:
        return None

    lowered = text.lower()
    if lowered.startswith(("https://", "http://")):
        return None
    if "tinyurl" in lowered or lowered.startswith("m. me/"):
        return None
    if "ebook miễn phí" in lowered or "webtietkiem.com" in lowered:
        return None
    if re.search(r"\b(?:thuviensach|download|đăng ký kho sách|facebook|fanpage)\b", lowered):
        return None
    if re.fullmatch(r"\d{3,4}", text):
        return None
    if text in {"ĐẮC NHÂN TÂM", "MỤC LỤC", "DALE CARNEGIE", "THÔNG TIN EBOOK"}:
        return None
    return text


def clean_lines(lines: Iterable[str]) -> List[str]:
    cleaned: List[str] = []
    for line in lines:
        text = _strip_noise_line(line)
        if text:
            cleaned.append(text)
    return cleaned


def text_to_pages(text: str) -> List[SourcePage]:
    return [SourcePage(page_number=1, lines=clean_lines(text.splitlines()))]


def is_toc_page(lines: List[str]) -> bool:
    joined = "\n".join(lines)
    dot_leaders = len(re.findall(r"\.{4,}\s*\d+", joined))
    toc_chapters = sum(
        1
        for line in lines
        if re.match(r"^\s*(?:Chương|Chƣơng|Chapter)\s+", line, re.IGNORECASE)
    )
    has_toc = any(normalize_space(line).upper() in {"MỤC LỤC", "TABLE OF CONTENTS"} for line in lines)
    numbered_entries = sum(1 for line in lines if re.match(r"^\d{1,2}\s+\S+", line))
    bare_numbers = sum(1 for line in lines if NUMERIC_CHAPTER_MARKER_RE.match(line))
    part_entries = sum(1 for line in lines if PART_HEADING_RE.match(line))
    return (
        has_toc
        or dot_leaders >= 2
        or toc_chapters >= 4
        or numbered_entries >= 4
        or (bare_numbers >= 4 and part_entries >= 1)
        or part_entries >= 3
    )


def _is_chapter_marker(line: str) -> bool:
    return bool(CHAPTER_MARKER_RE.match(line))


def _is_numeric_marker(line: str) -> bool:
    return bool(NUMERIC_CHAPTER_MARKER_RE.match(line))


def _is_part_heading(line: str) -> bool:
    return bool(PART_HEADING_RE.match(line))


def _is_supplementary_heading(line: str) -> bool:
    return bool(SUPPLEMENTARY_HEADING_RE.match(line))


def _is_heading_like(line: str) -> bool:
    if _is_supplementary_heading(line) or _is_part_heading(line):
        return True
    if len(line.split()) > 16:
        return False
    if line.strip().casefold() == "action":
        return True
    letters = re.sub(r"[^A-Za-zÀ-ỹƢƣĐđ]", "", line)
    return bool(letters) and letters.upper() == letters


def _finish_paragraph(lines: List[str], chapter: Optional[DetectedChapter]) -> None:
    if not chapter or not lines:
        lines.clear()
        return
    paragraph = normalize_space(" ".join(lines))
    if paragraph:
        chapter.paragraphs.append(paragraph)
    lines.clear()


def _start_chapter(
    chapters: List[DetectedChapter],
    title: str,
    page_number: int,
    current: Optional[DetectedChapter],
    paragraph_lines: List[str],
) -> DetectedChapter:
    _finish_paragraph(paragraph_lines, current)
    chapter = DetectedChapter(
        index=len(chapters),
        title=normalize_space(title),
        page_start=page_number,
        page_end=page_number,
    )
    chapters.append(chapter)
    return chapter


def _collect_heading_title(lines: List[str], start_index: int) -> tuple[str, int]:
    title_lines: List[str] = []
    i = start_index
    while i < len(lines):
        candidate = lines[i]
        if (
            _is_chapter_marker(candidate)
            or _is_numeric_marker(candidate)
            or _is_supplementary_heading(candidate)
            or _is_part_heading(candidate)
        ):
            break
        if not _is_heading_like(candidate):
            break
        title_lines.append(candidate)
        i += 1
    return normalize_space(" ".join(title_lines)), i


def _reindex(chapters: List[DetectedChapter]) -> List[DetectedChapter]:
    filtered = [chapter for chapter in chapters if chapter.paragraphs]
    for index, chapter in enumerate(filtered):
        chapter.index = index
    return filtered


def detect_chapters(
    pages: Iterable[SourcePage],
    *,
    source_type: str,
    drop_supplementary: bool = True,
) -> List[DetectedChapter]:
    pages = list(pages)
    chapters: List[DetectedChapter] = []
    current: Optional[DetectedChapter] = None
    paragraph_lines: List[str] = []
    pending_marker: Optional[str] = None
    current_part: Optional[str] = None
    allow_numeric_without_part = source_type.lower() in {"txt", "text"}

    for page in pages:
        lines = clean_lines(page.lines)
        if not lines or is_toc_page(lines):
            continue

        i = 0
        while i < len(lines):
            line = lines[i]
            if current and normalize_space(line).casefold() == current.title.casefold():
                i += 1
                continue

            if _is_supplementary_heading(line) and drop_supplementary:
                _finish_paragraph(paragraph_lines, current)
                current = None
                pending_marker = None
                i += 1
                continue

            if _is_part_heading(line):
                current_part = line
                _finish_paragraph(paragraph_lines, current)
                i += 1
                continue

            if pending_marker:
                title, next_i = _collect_heading_title(lines, i)
                if not title:
                    title = line
                    next_i = i + 1
                if current_part:
                    title = f"{current_part} - {title}"
                current = _start_chapter(chapters, title, page.page_number, current, paragraph_lines)
                pending_marker = None
                i = next_i
                continue

            if _is_chapter_marker(line) or (
                (current_part or allow_numeric_without_part)
                and _is_numeric_marker(line)
                and i + 1 < len(lines)
                and _is_heading_like(lines[i + 1])
            ):
                pending_marker = line
                _finish_paragraph(paragraph_lines, current)
                i += 1
                continue

            if INLINE_CHAPTER_RE.match(line) and len(line.split()) <= 18:
                title = re.sub(r"\.{3,}.*$", "", line).strip()
                if current_part:
                    title = f"{current_part} - {title}"
                current = _start_chapter(chapters, title, page.page_number, current, paragraph_lines)
                i += 1
                continue

            if current:
                current.page_end = page.page_number
                paragraph_lines.append(line)
                if re.search(r"[.!?…”\"]$", line):
                    _finish_paragraph(paragraph_lines, current)
            i += 1

    _finish_paragraph(paragraph_lines, current)
    detected = _reindex(chapters)
    if detected:
        return detected

    fallback_lines: List[str] = []
    for page in pages:
        if not is_toc_page(page.lines):
            fallback_lines.extend(clean_lines(page.lines))
    fallback_text = normalize_space(" ".join(fallback_lines))
    if not fallback_text:
        return []
    return [
        DetectedChapter(
            index=0,
            title="Nội dung",
            page_start=1,
            page_end=max((page.page_number for page in pages), default=1),
            paragraphs=[fallback_text],
        )
    ]
