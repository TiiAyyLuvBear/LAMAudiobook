import asyncio
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agents.cleaner import CleanerAgent, CleanerInput  # noqa: E402
from schema.pipeline import TextBlock  # noqa: E402


def test_cleaner_removes_links_tags_and_repeated_footers():
    agent = CleanerAgent()
    blocks = [
        TextBlock("<p>Chương 1</p>", page=1, block_type="heading"),
        TextBlock("Đây là câu chuyện đầu tiên. Xem tại https://example.com/book", page=1),
        TextBlock("www.example.vn", page=1),
        TextBlock("Bản quyền © 2024 Nhà xuất bản Test", page=1),
        TextBlock("Footer website đọc sách online", page=1),
        TextBlock("Nội dung thật của chương. Liên hệ test@example.com", page=2),
        TextBlock("Footer website đọc sách online", page=2),
        TextBlock("Footer website đọc sách online", page=3),
    ]

    result = asyncio.run(agent.run(CleanerInput(blocks)))

    assert result.success
    text = result.data.plain_text
    assert "https://" not in text
    assert "www.example" not in text
    assert "test@example.com" not in text
    assert "<p>" not in text
    assert "Bản quyền" not in text
    assert "Footer website" not in text
    assert "Đây là câu chuyện đầu tiên." in text
    assert "Nội dung thật của chương." in text
