"""
Cleaner Agent — Removes headers, footers, page numbers, noise.
"""

import re
import sys
import json
import argparse
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .base import BaseAgent, AgentResult
    from src.schema.pipeline import TextBlock, ChapterBlock
except ImportError:
    # Allow running this file directly: python src/agents/cleaner.py
    import importlib.util

    repo_root = Path(__file__).resolve().parents[2]

    base_spec = importlib.util.spec_from_file_location(
        "agents.base",
        str(repo_root / "src" / "agents" / "base.py"),
    )
    base_mod = importlib.util.module_from_spec(base_spec)
    base_spec.loader.exec_module(base_mod)

    types_spec = importlib.util.spec_from_file_location(
        "schema.pipeline",
        str(repo_root / "src" / "schema" / "pipeline.py"),
    )
    types_mod = importlib.util.module_from_spec(types_spec)
    types_spec.loader.exec_module(types_mod)

    BaseAgent = base_mod.BaseAgent
    AgentResult = base_mod.AgentResult
    TextBlock = types_mod.TextBlock
    ChapterBlock = types_mod.ChapterBlock


class CleanerInput:
    """Input for Cleaner Agent"""

    def __init__(
        self,
        text_blocks: List[Any],
        remove_headers: bool = True,
        remove_footers: bool = True,
        remove_page_numbers: bool = True,
    ):
        self.text_blocks = text_blocks
        self.remove_headers = remove_headers
        self.remove_footers = remove_footers
        self.remove_page_numbers = remove_page_numbers


class CleanerOutput:
    """Output from Cleaner Agent"""

    def __init__(
        self,
        cleaned_blocks: List[TextBlock],
        removed_count: int,
        metadata: Dict[str, Any],
        plain_text: Optional[str] = None,
        chapters: Optional[List[Any]] = None,  # List[ChapterBlock]
        chapter_plain_texts: Optional[List[str]] = None,
    ):
        self.cleaned_blocks = cleaned_blocks
        self.removed_count = removed_count
        self.metadata = metadata
        self.plain_text = plain_text
        self.chapters = chapters or []
        self.chapter_plain_texts = chapter_plain_texts or []


class CleanerAgent(BaseAgent):
    """Cleans extracted text by removing headers, footers, page numbers, noise."""

    name = "cleaner"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name=self.name, config=config)

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\S+@\S+\.\S+", "", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\u200b", "", text)
        text = self._normalize_for_tts(text)
        return text.strip()

    @staticmethod
    def _normalize_for_tts(text: str) -> str:
        """Chu\u1ea9n ho\u00e1 k\u00fd t\u1ef1 \u0111\u1eb7c bi\u1ec7t cho TTS engine."""
        # Curly quotes → straight
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u00ab", '"').replace("\u00bb", '"')
        # Ellipsis → 3 dots
        text = text.replace("\u2026", "...")
        # Em/en dash → hyphen
        text = text.replace("\u2014", " - ").replace("\u2013", " - ")
        # Remove decorative chars
        text = re.sub(r"[\u2022\u25cf\u25cb\u2605\u2606\u00a7]+", "", text)
        return text

    def _is_noise_line(self, text: str) -> bool:
        if re.search(r"https?://", text):
            return True
        if re.search(r"www\.|\.com|\.org|\.net", text) and len(text) > 20:
            return True
        if re.fullmatch(r"[-–—_=~]{3,}", text):
            return True
        if len(text) <= 2 and not re.search(r"[a-zA-Zà-žÀ-Ž]", text):
            return True
        if re.search(r"\.{3,}\s*\d+\s*$", text):
            return True
        if text.lower().strip() in ("trang", "page"):
            return True
        # --- TTS-unfriendly patterns for Vietnamese books ---
        if re.search(r"ISBN[\s:\-]*[\d\-X]{10,}", text, re.IGNORECASE):
            return True
        if re.search(r"Nhà xuất bản|NXB|In\s+\d+\s+bản|Khổ\s+\d+", text, re.IGNORECASE):
            return True
        if re.search(r"Bản quyền|Copyright|©|All rights reserved", text, re.IGNORECASE):
            return True
        if re.search(r"Liên hệ.*\d{4,}|Điện thoại|Fax\s*:", text, re.IGNORECASE):
            return True
        if re.search(r"Mục lục|Table of Contents", text, re.IGNORECASE) and len(text) < 30:
            return True
        if re.fullmatch(r"\s*\[\d+\].*", text):
            return True
        if re.search(r"Chịu trách nhiệm xuất bản|Biên tập|Trình bày bìa", text, re.IGNORECASE):
            return True
        return False

    def _expand_abbreviations(self, text: str) -> str:
        abbr_map = {
            r"\bđ/c\b": "đồng chí",
            r"\bĐ/C\b": "Đồng chí",
            r"\bTP\b": "Thành phố",
            r"\bTT\b": "Thị trấn",
            r"\bQĐ\b": "Quyết định",
            r"\bTTCP\b": "Thủ tướng Chính phủ",
            r"\bCP\b": "Chính phủ",
            r"\bTNHH\b": "Trách nhiệm hữu hạn",
            r"\bCổ phần\b": "Cổ phần",
            r"\bv\.v\.\b": "vân vân",
            r"\bv\.v\b": "vân vân",
        }
        for pattern, replacement in abbr_map.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _is_sentence_ending(self, text: str) -> bool:
        if not text:
            return False
        return text.strip()[-1] in ".?!。！？"

    def _merge_paragraph(self, sentences: List[str]) -> str:
        merged = " ".join(sentences)
        return re.sub(r"\s+", " ", merged).strip()

    def _split_sentences_for_txt(self, text: str) -> List[str]:
        text = text.strip()
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?。！？])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _merge_body_blocks(
        self,
        blocks: List[TextBlock],
        start_i: int,
    ) -> tuple[Optional[str], int]:
        sentences: List[str] = []
        i = start_i
        consecutive_non_ending = 0

        while i < len(blocks) and len(sentences) < 50:
            block = blocks[i]
            if block.block_type == "heading":
                break

            text = self._clean_text(block.text)
            if not text:
                i += 1
                continue

            text = self._expand_abbreviations(text)
            if self._is_sentence_ending(text):
                sentences.append(text)
                consecutive_non_ending = 0
            else:
                if sentences and not self._is_sentence_ending(sentences[-1]):
                    sentences[-1] += " " + text
                    consecutive_non_ending += 1
                else:
                    sentences.append(text)
                    consecutive_non_ending += 1

                if consecutive_non_ending >= 3:
                    break

            i += 1

        if not sentences:
            return None, start_i + 1

        return self._merge_paragraph(sentences), i

    def _remove_duplicate_headers(
        self,
        blocks: List[TextBlock],
        remove_headers: bool,
        remove_footers: bool,
    ) -> tuple[List[TextBlock], int]:
        if not remove_headers and not remove_footers:
            return blocks, 0

        header_counts: Dict[str, int] = {}
        page_last_seen: Dict[str, int] = {}
        result: List[TextBlock] = []
        removed = 0

        for block in blocks:
            text_key = block.text[:50].strip().lower()
            if not text_key:
                result.append(block)
                continue

            header_counts[text_key] = header_counts.get(text_key, 0) + 1
            page_last_seen[text_key] = block.page or 0

            if header_counts[text_key] > 3:
                if block.page and page_last_seen[text_key] != block.page:
                    removed += 1
                    continue

            result.append(block)

        return result, removed

    def _to_plain_text(self, blocks: List[TextBlock]) -> str:
        lines: List[str] = []
        for block in blocks:
            text = block.text.strip()
            if not text:
                continue

            if block.block_type == "heading":
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(text)
                continue

            for sentence in self._split_sentences_for_txt(text):
                lines.append(sentence)

        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _to_cleaned_block(self, block: Any) -> Optional[TextBlock]:
        raw_text = (
            getattr(block, "text", str(block))
            if not isinstance(block, dict)
            else block.get("text", "")
        )
        text = self._clean_text(raw_text)
        if not text or self._is_noise_line(text):
            return None

        # Get existing block_type or default to paragraph
        block_type = (
            getattr(block, "block_type", "paragraph")
            if not isinstance(block, dict)
            else block.get("block_type", "paragraph")
        )

        # Heuristic: If it's a paragraph but looks like a chapter header, promote it
        # Criteria: Short ( < 10 words) and starts with Chapter/Chương keywords
        if block_type == "paragraph" and len(text.split()) < 10:
            if re.match(
                r"^\s*(Chương|Chapter|Tiết|Phần|Mục|Hồi)\s+(\d+|[IVXLCDM]+|[MộtHaiBaBốnNămSáuBảyTámChínMười]+)",
                text,
                re.IGNORECASE,
            ):
                block_type = "heading"

        return TextBlock(
            text=text,
            page=(
                getattr(block, "page", 1)
                if not isinstance(block, dict)
                else block.get("page", 1)
            ),
            block_type=block_type,
        )

    def _group_into_chapters(
        self, blocks: List[TextBlock]
    ) -> List[Any]:  # List[ChapterBlock]
        """
        Group cleaned TextBlocks into ChapterBlocks using headings as chapter boundaries.
        If no headings exist, the entire text becomes a single chapter.
        """
        chapters = []
        current_title = "Mở đầu"
        current_paragraphs: List[str] = []
        current_blocks: List[TextBlock] = []

        for block in blocks:
            if block.block_type == "heading":
                # Save previous chapter if it has content
                if current_paragraphs:
                    chapters.append(
                        ChapterBlock(
                            index=len(chapters),
                            title=current_title,
                            paragraphs=current_paragraphs,
                            paragraph_blocks=current_blocks,
                        )
                    )
                # Start new chapter
                current_title = block.text.strip()
                current_paragraphs = []
                current_blocks = []
            else:
                text = block.text.strip()
                if text:
                    current_paragraphs.append(text)
                    current_blocks.append(block)

        # Flush last chapter
        if current_paragraphs:
            chapters.append(
                ChapterBlock(
                    index=len(chapters),
                    title=current_title,
                    paragraphs=current_paragraphs,
                    paragraph_blocks=current_blocks,
                )
            )

        # Fallback: no headings found → single chapter
        if not chapters:
            all_text = self._to_plain_text(blocks)
            if all_text.strip():
                chapters.append(
                    ChapterBlock(
                        index=0,
                        title="Nội dung",
                        paragraphs=[all_text],
                        paragraph_blocks=blocks,
                    )
                )

        return chapters

    async def run(self, input_data: CleanerInput) -> AgentResult:
        try:
            if isinstance(input_data, dict):
                input_data = CleanerInput(
                    text_blocks=input_data.get("text_blocks", []),
                    remove_headers=bool(input_data.get("remove_headers", True)),
                    remove_footers=bool(input_data.get("remove_footers", True)),
                    remove_page_numbers=bool(
                        input_data.get("remove_page_numbers", True)
                    ),
                )

            cleaned: List[TextBlock] = []
            removed = 0

            for block in input_data.text_blocks:
                text_block = self._to_cleaned_block(block)
                if text_block is None:
                    removed += 1
                    continue

                if input_data.remove_page_numbers and re.fullmatch(
                    r"\s*\d{1,5}\s*", text_block.text
                ):
                    removed += 1
                    continue

                cleaned.append(text_block)

            merged: List[TextBlock] = []
            i = 0
            while i < len(cleaned):
                block = cleaned[i]
                if block.block_type == "heading":
                    merged.append(block)
                    i += 1
                    continue

                merged_text, next_i = self._merge_body_blocks(cleaned, i)
                if merged_text:
                    merged.append(
                        TextBlock(
                            text=merged_text,
                            page=cleaned[i].page,
                            block_type="paragraph",
                        )
                    )
                i = next_i

            merged, duplicates_removed = self._remove_duplicate_headers(
                merged,
                remove_headers=input_data.remove_headers,
                remove_footers=input_data.remove_footers,
            )
            removed += duplicates_removed

            plain_text = self._to_plain_text(merged)
            chapters = self._group_into_chapters(merged)
            chapter_plain_texts = [ch.plain_text for ch in chapters]

            metadata: Dict[str, Any] = {
                "removed_count": removed,
                "cleaned_blocks": len(merged),
                "chapter_count": len(chapters),
            }

            return AgentResult(
                success=True,
                data=CleanerOutput(
                    cleaned_blocks=merged,
                    removed_count=removed,
                    metadata=metadata,
                    plain_text=plain_text,
                    chapters=chapters,
                    chapter_plain_texts=chapter_plain_texts,
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))


def _blocks_to_ssml(blocks: List[TextBlock]) -> str:
    """Render cleaned blocks to simple SSML for TTS."""
    parts = [
        '<speak version="1.0" xmlns="http://www.w3.org/2006/10/ssml" xml:lang="vi">'
    ]

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        if block.block_type == "heading":
            parts.append(f'<s>{text}</s><break time="1.5s"/>')
            continue

        sentences = re.split(r"(?<=[.?!])\s+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if sentence.endswith("."):
                sentence = sentence[:-1]
            parts.append(f'<s>{sentence}</s><break time="0.5s"/>')

    parts.append("</speak>")
    return "\n".join(parts)


def _default_output_path(input_path: str, output_format: str) -> str:
    src = Path(input_path)
    return str(src.with_suffix(f".{output_format}"))


async def _run_cli() -> int:
    parser = argparse.ArgumentParser(
        description="Cleaner CLI: input EPUB, output TXT/JSON/SSML"
    )
    parser.add_argument("-i", "--input", required=True, help="Input EPUB file path")
    parser.add_argument(
        "-f",
        "--format",
        required=True,
        choices=["txt", "json", "ssml"],
        help="Output format",
    )
    parser.add_argument("-o", "--output", default=None, help="Output file path")
    parser.add_argument(
        "--keep-headers", action="store_true", help="Keep repeated headers"
    )
    parser.add_argument(
        "--keep-footers", action="store_true", help="Keep repeated footers"
    )
    parser.add_argument(
        "--keep-page-numbers", action="store_true", help="Keep page numbers"
    )
    args = parser.parse_args()

    input_path = args.input
    if not Path(input_path).exists():
        print(f"Input not found: {input_path}")
        return 1
    if Path(input_path).suffix.lower() != ".epub":
        print("Only EPUB input is supported by this CLI mode")
        return 1

    output_path = args.output or _default_output_path(input_path, args.format)

    try:
        from .parser import ParserAgent, ParserInput

        parser_agent = ParserAgent()
        parse_res = await parser_agent.run(
            ParserInput(file_path=input_path, file_type="epub")
        )
        if not parse_res.success:
            print(f"Extraction failed: {parse_res.error}")
            return 1
        raw_blocks = parse_res.data.blocks
    except Exception as e:
        print(f"Extraction failed: {e}")
        return 1

    agent = CleanerAgent()
    result = await agent.run(
        CleanerInput(
            text_blocks=raw_blocks,
            remove_headers=not args.keep_headers,
            remove_footers=not args.keep_footers,
            remove_page_numbers=not args.keep_page_numbers,
        )
    )

    if not result.success:
        print(f"Cleaner failed: {result.error}")
        return 1

    data: CleanerOutput = result.data
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "txt":
        output_file.write_text(data.plain_text or "", encoding="utf-8")
    elif args.format == "ssml":
        ssml = _blocks_to_ssml(data.cleaned_blocks)
        output_file.write_text(ssml, encoding="utf-8")
    else:
        payload = {
            "metadata": data.metadata,
            "removed_count": data.removed_count,
            "plain_text": data.plain_text,
            "blocks": [
                {
                    "text": b.text,
                    "page": b.page,
                    "block_type": b.block_type,
                }
                for b in data.cleaned_blocks
            ],
        }
        output_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"Input: {input_path}")
    print(f"Output: {output_file}")
    print(f"Format: {args.format}")
    print(f"Blocks: {len(data.cleaned_blocks)} | Removed: {data.removed_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run_cli()))
