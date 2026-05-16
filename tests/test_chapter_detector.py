import asyncio
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agents.parser import ParserAgent, ParserInput  # noqa: E402
from preprocessing.chapter_detector import SourcePage, detect_chapters, text_to_pages  # noqa: E402


def test_detector_handles_pdf_style_chapter_heading():
    pages = [
        SourcePage(
            page_number=1,
            lines=[
                "MỤC LỤC",
                "Chương I ................................ 10",
                "Chương II ............................... 20",
                "Chương III .............................. 30",
                "Chương IV ............................... 40",
            ],
        ),
        SourcePage(
            page_number=2,
            lines=[
                "CHƯƠNG NHẤT",
                "MUỐN LẤY MẬT ĐỪNG PHÁ TỔ ONG",
                "Đây là nội dung chương đầu tiên.",
            ],
        ),
    ]

    chapters = detect_chapters(pages, source_type="pdf")

    assert len(chapters) == 1
    assert chapters[0].title == "MUỐN LẤY MẬT ĐỪNG PHÁ TỔ ONG"
    assert chapters[0].paragraphs == ["Đây là nội dung chương đầu tiên."]


def test_detector_handles_inline_and_numeric_txt_headings():
    text = """
LỜI NHÀ XUẤT BẢN
Phần phụ này không đưa vào TTS.

Chương 1: Mở đầu
Đây là chương một.

01
CHƯƠNG HAI
Đây là chương hai.
"""

    chapters = detect_chapters(text_to_pages(text), source_type="txt")

    assert [chapter.title for chapter in chapters] == ["Chương 1: Mở đầu", "CHƯƠNG HAI"]
    assert chapters[0].plain_text == "Đây là chương một."
    assert chapters[1].plain_text == "Đây là chương hai."


def test_detector_falls_back_to_single_chapter_without_headings():
    chapters = detect_chapters(
        text_to_pages("Một đoạn văn không có tiêu đề chương.\nMột đoạn khác."),
        source_type="txt",
    )

    assert len(chapters) == 1
    assert chapters[0].title == "Nội dung"
    assert "Một đoạn văn" in chapters[0].plain_text


def test_parser_detects_chapters_from_txt(tmp_path):
    txt_path = tmp_path / "book.txt"
    txt_path.write_text(
        "Chương 1: Bắt đầu\nNội dung một.\n\nChương 2: Tiếp tục\nNội dung hai.",
        encoding="utf-8",
    )

    result = asyncio.run(ParserAgent().run(ParserInput(str(txt_path), "txt")))

    assert result.success
    assert result.data.metadata["total_chapters"] == 2
    assert [block.block_type for block in result.data.blocks].count("heading") == 2


def test_parser_detects_chapters_from_sample_pdf():
    pdf_path = ROOT_DIR / "book_pdf" / "1.pdf"

    result = asyncio.run(ParserAgent().run(ParserInput(str(pdf_path), "pdf")))

    assert result.success
    assert result.data.metadata["total_chapters"] > 1
    assert any(block.block_type == "heading" for block in result.data.blocks)
    assert any(block.block_type == "paragraph" for block in result.data.blocks)
