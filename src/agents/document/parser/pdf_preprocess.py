"""
Audio preprocessing utilities for PDF input.

This module prepares clean text for the agentic audiobook pipeline:
- Read PDF text only (ignores images)
- Remove repeated headers/footers and page numbers
- Group content into chapters and paragraphs
- Return voice-planning JSON list structure
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple
import argparse
import json
import re


CHAPTER_PATTERNS = [
    re.compile(r"^\s*(chuong|ch\.)\s*([0-9ivxlcdm]+)\b", re.IGNORECASE),
    re.compile(r"^\s*chapter\s*([0-9ivxlcdm]+)\b", re.IGNORECASE),
]


def _require_pdfplumber():
    try:
        import pdfplumber  # type: ignore

        return pdfplumber
    except ImportError as exc:
        raise ImportError(
            "Missing dependency 'pdfplumber'. Install with: pip install pdfplumber"
        ) from exc


@dataclass
class RawLine:
    text: str
    page: int
    top: float
    bottom: float


@dataclass
class ParagraphItem:
    paragraph_index: int
    text: str
    page_start: int
    page_end: int


@dataclass
class ChapterItem:
    chapter_index: int
    chapter_title: str
    paragraphs: List[ParagraphItem]


def _normalize_line(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def _is_page_number_only(text: str) -> bool:
    t = text.strip().lower()
    return bool(re.fullmatch(r"(trang\s*)?[0-9]+", t))


def _is_footer_noise(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return True

    patterns = [
        r"https?://",
        r"www\.",
        r"ebook",
        r"download",
        r"pdf",
        r"@",
    ]
    return any(re.search(p, t) for p in patterns)


def _looks_like_chapter_title(text: str) -> bool:
    return any(p.search(text) for p in CHAPTER_PATTERNS)


def _extract_pdf_lines(pdf_path: Path, top_margin: float = 40.0, bottom_margin: float = 40.0) -> Tuple[List[RawLine], int]:
    """
    Extract text lines from PDF pages.

    Note: We only extract words/text from the page, so image blocks are skipped.
    """
    pdfplumber = _require_pdfplumber()
    lines: List[RawLine] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages, start=1):
            page_height = float(page.height)
            words = page.extract_words() or []
            if not words:
                continue

            grouped: Dict[float, List[Dict[str, Any]]] = defaultdict(list)
            for w in words:
                top = float(w.get("top", 0.0))
                bottom = float(w.get("bottom", top))
                if top < top_margin or bottom > (page_height - bottom_margin):
                    continue

                key = round(top, 1)
                grouped[key].append(w)

            for key in sorted(grouped.keys()):
                row_words = sorted(grouped[key], key=lambda x: float(x.get("x0", 0.0)))
                text = _normalize_line(" ".join(str(x.get("text", "")) for x in row_words))
                if not text:
                    continue

                top = min(float(x.get("top", 0.0)) for x in row_words)
                bottom = max(float(x.get("bottom", top)) for x in row_words)
                lines.append(RawLine(text=text, page=page_idx, top=top, bottom=bottom))

    return lines, total_pages


def _detect_repeated_header_footer(lines: List[RawLine], total_pages: int, min_ratio: float = 0.6) -> Tuple[set[str], set[str]]:
    if total_pages <= 1:
        return set(), set()

    per_page: Dict[int, List[RawLine]] = defaultdict(list)
    for line in lines:
        per_page[line.page].append(line)

    top_lines: List[str] = []
    bottom_lines: List[str] = []

    for page in sorted(per_page.keys()):
        page_lines = sorted(per_page[page], key=lambda x: x.top)
        if not page_lines:
            continue
        top_lines.append(page_lines[0].text)
        bottom_lines.append(page_lines[-1].text)

    top_counter = Counter(top_lines)
    bottom_counter = Counter(bottom_lines)

    threshold = max(2, int(total_pages * min_ratio))
    repeated_top = {t for t, c in top_counter.items() if c >= threshold}
    repeated_bottom = {t for t, c in bottom_counter.items() if c >= threshold}

    return repeated_top, repeated_bottom


def _clean_lines(lines: List[RawLine], total_pages: int) -> List[RawLine]:
    repeated_top, repeated_bottom = _detect_repeated_header_footer(lines, total_pages)
    cleaned: List[RawLine] = []

    for line in lines:
        text = _normalize_line(line.text)
        if not text:
            continue
        if text in repeated_top or text in repeated_bottom:
            continue
        if _is_page_number_only(text):
            continue
        if _is_footer_noise(text):
            continue

        cleaned.append(RawLine(text=text, page=line.page, top=line.top, bottom=line.bottom))

    return cleaned


def _group_paragraphs(lines: List[RawLine]) -> List[ParagraphItem]:
    paragraphs: List[ParagraphItem] = []
    buffer: List[RawLine] = []
    paragraph_index = 0

    def flush_buffer() -> None:
        nonlocal paragraph_index
        if not buffer:
            return

        paragraph_index += 1
        text = " ".join(item.text for item in buffer)
        page_start = min(item.page for item in buffer)
        page_end = max(item.page for item in buffer)
        paragraphs.append(
            ParagraphItem(
                paragraph_index=paragraph_index,
                text=_normalize_line(text),
                page_start=page_start,
                page_end=page_end,
            )
        )
        buffer.clear()

    for current in lines:
        if not buffer:
            buffer.append(current)
            continue

        prev = buffer[-1]
        same_page = current.page == prev.page
        vertical_gap = current.top - prev.bottom

        # New paragraph when line gap is large or page changed.
        if (not same_page) or (vertical_gap > 18.0):
            flush_buffer()
        buffer.append(current)

    flush_buffer()
    return paragraphs


def _split_chapters(paragraphs: List[ParagraphItem]) -> List[ChapterItem]:
    if not paragraphs:
        return []

    chapters: List[ChapterItem] = []
    current_chapter = ChapterItem(chapter_index=1, chapter_title="Chapter 1", paragraphs=[])

    for para in paragraphs:
        if _looks_like_chapter_title(para.text):
            if current_chapter.paragraphs:
                chapters.append(current_chapter)
            current_chapter = ChapterItem(
                chapter_index=len(chapters) + 1,
                chapter_title=para.text,
                paragraphs=[],
            )
            continue

        current_chapter.paragraphs.append(para)

    if current_chapter.paragraphs or not chapters:
        chapters.append(current_chapter)

    # Re-number paragraph index inside each chapter for cleaner downstream use.
    for chapter in chapters:
        for idx, para in enumerate(chapter.paragraphs, start=1):
            para.paragraph_index = idx

    return chapters


def _split_sentences(text: str) -> List[str]:
    """Split paragraph text into sentence-level items."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _is_dialogue_sentence(sentence: str) -> bool:
    """Heuristic dialogue detection for initial preprocessing output."""
    return sentence.startswith("-") or ('"' in sentence) or ("“" in sentence) or ("”" in sentence)


def _to_voice_planning_items(chapters: List[ChapterItem]) -> List[Dict[str, Any]]:
    """Convert chapter/paragraph structure into voice-planning sentence items."""
    items: List[Dict[str, Any]] = []
    for chapter in chapters:
        for para in chapter.paragraphs:
            for sentence in _split_sentences(para.text):
                is_dialogue = _is_dialogue_sentence(sentence)
                items.append(
                    {
                        "sentence": sentence,
                        "type": "dialogue" if is_dialogue else "narration",
                        "speaker": "unknown" if is_dialogue else "narrator",
                        "emotion": "neutral",
                        "intensity": 0.5,
                    }
                )
    return items


def preprocess_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Preprocess PDF into voice-planning sentence list.

    Returns a JSON-ready list:
    [
      {
        "sentence": "...",
        "type": "narration" | "dialogue",
        "speaker": "narrator" | "unknown",
        "emotion": "neutral",
        "intensity": 0.5
      }
    ]
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("Input must be a PDF file")

    raw_lines, total_pages = _extract_pdf_lines(path)
    cleaned_lines = _clean_lines(raw_lines, total_pages)
    paragraphs = _group_paragraphs(cleaned_lines)
    chapters = _split_chapters(paragraphs)

    return _to_voice_planning_items(chapters)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess PDF for audiobook pipeline")
    parser.add_argument("--input", "-i", required=True, help="Input PDF path")
    parser.add_argument("--output", "-o", default="", help="Optional output JSON file")
    args = parser.parse_args()

    result = preprocess_pdf(args.input)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved preprocessing output to: {output_path}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
