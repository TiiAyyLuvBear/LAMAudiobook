import asyncio
from pathlib import Path
import sys

from ebooklib import epub

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



def test_parser_epub_skips_frontmatter_and_toc(tmp_path):
    epub_path = tmp_path / "sample.epub"
    book = epub.EpubBook()
    book.set_identifier("sample")
    book.set_title("Sample")
    book.set_language("vi")

    toc = epub.EpubHtml(title="Mục lục", file_name="toc.xhtml", lang="vi")
    toc.set_content(
        """<html><body><h1>MỤC LỤC</h1><p>Chương 1 ........ 5</p><p>Chương 2 ........ 20</p><p>Chương 3 ........ 40</p><p>Chương 4 ........ 60</p></body></html>""".encode("utf-8")
    )
    intro = epub.EpubHtml(title="Giới thiệu", file_name="intro.xhtml", lang="vi")
    intro.set_content(
        """<html><body><h1>GIỚI THIỆU</h1><p>Đoạn giới thiệu này không nên đưa vào audiobook.</p></body></html>""".encode("utf-8")
    )
    chapter = epub.EpubHtml(title="Chương 1", file_name="chapter1.xhtml", lang="vi")
    chapter.set_content(
        """<html><body><h1>Chương 1: Bắt đầu</h1><p>Nội dung chương đầu tiên cần được đọc.</p></body></html>""".encode("utf-8")
    )

    for item in (toc, intro, chapter):
        book.add_item(item)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [toc, intro, chapter]
    epub.write_epub(str(epub_path), book)

    result = asyncio.run(ParserAgent().run(ParserInput(str(epub_path), "epub")))

    assert result.success
    parsed_text = "\n".join(block.text for block in result.data.blocks)
    assert "MỤC LỤC" not in parsed_text
    assert "Đoạn giới thiệu" not in parsed_text
    assert "Nội dung chương đầu tiên" in parsed_text
    assert result.data.metadata["epub_frontmatter_skipped"] >= 2
