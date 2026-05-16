"""
Convert a sample PDF into a simple EPUB for preprocessing experiments.

Usage:
    python tests/convert_pdf_to_epub.py
    python tests/convert_pdf_to_epub.py book_pdf/403-dac-nhan-tam-thuviensach.vn.pdf
    python tests/convert_pdf_to_epub.py book_pdf/1.pdf tests/pdf_to_epub_output/book.epub

The script extracts text with PyMuPDF and writes one XHTML chapter per PDF page
that contains text. It is intended as a lightweight conversion test before
feeding converted files into the multi-agent audiobook pipeline.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from typing import Iterable, List

import fitz
from ebooklib import epub


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "book_pdf" / "1.pdf"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "pdf_to_epub_output"


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_paragraphs(page_text: str) -> List[str]:
    raw_blocks = re.split(r"\n\s*\n+", page_text)
    paragraphs: List[str] = []

    for block in raw_blocks:
        lines = [normalize_space(line) for line in block.splitlines()]
        text = normalize_space(" ".join(line for line in lines if line))
        if text:
            paragraphs.append(text)

    if paragraphs:
        return paragraphs

    text = normalize_space(page_text)
    return [text] if text else []


def extract_pages(pdf_path: Path) -> List[List[str]]:
    pages: List[List[str]] = []
    with fitz.open(pdf_path) as document:
        for page in document:
            text = page.get_text("text")
            paragraphs = split_paragraphs(text)
            if paragraphs:
                pages.append(paragraphs)
    return pages


def build_chapter_html(title: str, paragraphs: Iterable[str]) -> str:
    body = "\n".join(f"    <p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="vi" xml:lang="vi">
<head>
  <title>{html.escape(title)}</title>
  <meta charset="utf-8"/>
</head>
<body>
  <section epub:type="chapter">
    <h1>{html.escape(title)}</h1>
{body}
  </section>
</body>
</html>
"""


def pdf_to_epub(pdf_path: Path, epub_path: Path, title: str | None = None) -> Path:
    pdf_path = pdf_path.resolve()
    epub_path = epub_path.resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages = extract_pages(pdf_path)
    if not pages:
        raise RuntimeError(
            "No extractable text found. This PDF may be scanned and needs OCR first."
        )

    book_title = title or pdf_path.stem
    book = epub.EpubBook()
    book.set_identifier(f"pdf-conversion-{pdf_path.stem}")
    book.set_title(book_title)
    book.set_language("vi")
    book.add_author("PDF conversion script")

    chapters = []
    for index, paragraphs in enumerate(pages, start=1):
        chapter_title = f"Page {index}"
        chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=f"page_{index:04d}.xhtml",
            lang="vi",
        )
        chapter.set_content(build_chapter_html(chapter_title, paragraphs).encode("utf-8"))
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = tuple(chapters)
    book.spine = ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(epub_path), book)
    return epub_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert PDF text into a simple EPUB.")
    parser.add_argument(
        "input_pdf",
        nargs="?",
        default=str(DEFAULT_INPUT),
        help=f"PDF input path. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "output_epub",
        nargs="?",
        default=None,
        help="EPUB output path. Default: tests/pdf_to_epub_output/<pdf-name>.epub",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional EPUB title. Defaults to the PDF file name.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_pdf = Path(args.input_pdf)
    if not input_pdf.is_absolute():
        input_pdf = PROJECT_ROOT / input_pdf

    output_epub = Path(args.output_epub) if args.output_epub else DEFAULT_OUTPUT_DIR / f"{input_pdf.stem}.epub"
    if not output_epub.is_absolute():
        output_epub = PROJECT_ROOT / output_epub

    result = pdf_to_epub(input_pdf, output_epub, title=args.title)
    print(f"Created EPUB: {result}")


if __name__ == "__main__":
    main()
