"""
Summarizer Agent — "Map-Reduce" Version.
Nhiệm vụ: Tạo Context Buffer (Summary, Mood, Keywords, Entities) cho Audiobook Pipeline.
Tối ưu hóa cho văn bản dài bằng Map-Reduce theo chương (chapter-aware).
"""

import asyncio
import torch
import re
from typing import Any, Dict, List, Optional
from collections import Counter
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

try:
    from .base import BaseAgent, AgentResult
    from schema.pipeline import ChapterBlock
except ImportError:
    # Fallback cho môi trường dev/test độc lập
    BaseAgent = object
    ChapterBlock = None

    class AgentResult:
        def __init__(self, success, data=None, error=None, metadata=None):
            self.success = success
            self.data = data
            self.error = error
            self.metadata = metadata or {}


class SummarizerInput:
    def __init__(
        self,
        text: str,
        chapters: Optional[List[Any]] = None,
        status_callback: Optional[Any] = None,
    ):
        self.text = text
        self.chapters = chapters or []
        self.status_callback = status_callback


class SummarizerOutput:
    def __init__(
        self,
        summary: str,
        primary_mood: str,
        keywords: List[str],
        entities: List[str],
        chapter_summaries: Optional[List[str]] = None,
    ):
        self.summary = summary
        self.primary_mood = primary_mood
        self.keywords = keywords
        self.entities = entities
        self.chapter_summaries = chapter_summaries or []


class SummarizerAgent(BaseAgent):
    name = "summarizer"
    _model = None
    _tokenizer = None
    _model_name = "VietAI/vit5-base-vietnews-summarization"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if BaseAgent is not object:
            super().__init__(name=self.name, config=config)
        self.chunk_size = 700  # Max words per chunk (safe for 1024 ViT5 tokens)

    # ─────────────────────────────────────────────
    # Model loading
    # ─────────────────────────────────────────────

    @classmethod
    def _load_model(cls):
        if cls._model is None:
            print(f"[Summarizer] Loading model {cls._model_name}...")
            cls._tokenizer = AutoTokenizer.from_pretrained(cls._model_name)
            cls._model = AutoModelForSeq2SeqLM.from_pretrained(cls._model_name)

            if torch.cuda.is_available():
                cls._model = cls._model.to("cuda")
                print("[Summarizer] Using CUDA")
            elif hasattr(torch, "xpu") and torch.xpu.is_available():
                cls._model = cls._model.to("xpu")
                print("[Summarizer] Using XPU")

            cls._model.eval()

    # ─────────────────────────────────────────────
    # Lightweight heuristic extractors (no model needed)
    # ─────────────────────────────────────────────

    def _extract_entities(self, text: str) -> List[str]:
        """Trích xuất tên riêng bằng regex heuristic (viết hoa liên tiếp)."""
        candidates = re.findall(
            r"\b[A-ZÀ-Ỹ][a-zà-ỹ]+\s[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s[A-ZÀ-Ỹ][a-zà-ỹ]+)*\b", text
        )
        return list(set([e[0] for e in Counter(candidates).most_common(5)]))

    def _detect_primary_mood(self, text: str) -> str:
        """Xác định tông giọng chủ đạo dựa trên mật độ từ khóa cảm xúc."""
        mood_weights = {
            "Bí ẩn / Hồi hộp": [
                "giết",
                "vụ_án",
                "chết",
                "hung_thủ",
                "bí_ẩn",
                "thủ_phạm",
                "nghi_phạm",
                "án_mạng",
                "điều_tra",
            ],
            "Căng thẳng": [
                "nguy_hiểm",
                "truy_đuổi",
                "khẩn_cấp",
                "kinh_hoàng",
                "đấu_tranh",
                "tấn_công",
                "súng",
                "đạn",
            ],
            "U buồn": [
                "đau_đớn",
                "khóc",
                "mất_mát",
                "tuyệt_vọng",
                "bi_kịch",
                "bi_thương",
                "chia_ly",
                "đau_khổ",
                "tang_tóc",
            ],
            "Vui vẻ": [
                "hạnh_phúc",
                "niềm_vui",
                "phấn_khích",
                "hào_hứng",
                "chiến_thắng",
                "vui_vẻ",
            ],
            "Lãng mạn": [
                "dịu_dàng",
                "êm_đềm",
                "lãng_mạn",
                "ấm_áp",
                "bình_yên",
                "ngọt_ngào",
                "hôn",
                "nhớ_nhung",
            ],
            "Chiêm nghiệm": [
                "triết_lý",
                "suy_ngẫm",
                "sâu_sắc",
                "nhân_sinh",
                "cuộc_đời",
                "ý_nghĩa",
            ],
        }
        text_lower = text.lower()
        scores = {
            m: sum(text_lower.count(kw) for kw in kws)
            for m, kws in mood_weights.items()
        }
        max_mood = max(scores, key=scores.get)
        return max_mood if scores[max_mood] > 0 else "Bình thường"

    def _extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """Trích xuất từ khóa có loại bỏ Stopwords tiếng Việt."""
        stopwords = {
            "và",
            "là",
            "của",
            "để",
            "có",
            "không",
            "trong",
            "một",
            "đã",
            "được",
            "người",
            "với",
            "cho",
            "những",
            "này",
            "khi",
            "thì",
            "mà",
            "nhưng",
            "cũng",
            "như",
            "lại",
            "còn",
            "về",
            "ra",
            "vào",
            "lên",
            "xuống",
        }
        words = re.findall(r"\b[a-zà-ỹ_]+\b", text.lower())
        meaningful_words = [w for w in words if len(w) > 2 and w not in stopwords]
        return [w for w, c in Counter(meaningful_words).most_common(top_k)]

    # ─────────────────────────────────────────────
    # Model inference: single chunk
    # ─────────────────────────────────────────────

    def _summarize_single_chunk(self, chunk_text: str) -> str:
        """Run ViT5 inference on a single text chunk."""
        device = next(self._model.parameters()).device
        inputs = self._tokenizer(
            chunk_text,
            return_tensors="pt",
            max_length=1024,
            truncation=True,
        ).to(device)

        with torch.no_grad():
            outputs = self._model.generate(
                inputs["input_ids"],
                max_length=256,
                min_length=40,
                length_penalty=1.5,
                num_beams=4,
                early_stopping=True,
            )

        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)

    # ─────────────────────────────────────────────
    # Map-Reduce strategies
    # ─────────────────────────────────────────────

    def _split_into_word_chunks(self, text: str) -> List[str]:
        """Fallback: split plain text into fixed-size word chunks."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), self.chunk_size):
            chunks.append(" ".join(words[i : i + self.chunk_size]))
        return chunks or [text]

    def _map_reduce_chunks(self, chunks: List[str]) -> str:
        """
        Map-Reduce over a list of text chunks.
        Map: summarize each chunk independently (Sequential).
        Reduce: summarize the combined intermediate summaries.
        """
        if len(chunks) == 1:
            return self._summarize_single_chunk(chunks[0])

        print(f"[Summarizer] Map Phase: {len(chunks)} chunks...")

        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            summary = self._summarize_single_chunk(chunk)
            chunk_summaries.append(summary)
            print(f"  -> Chunk {i+1}/{len(chunks)} done")

        # Reduce
        print("[Summarizer] Reduce Phase: aggregating...")
        combined = " \n ".join(chunk_summaries)

        # Recursive if still too long
        if len(combined.split()) > self.chunk_size:
            print("  -> Still quá dài, đang chạy tóm tắt đệ quy...")
            return self._map_reduce_chunks(self._split_into_word_chunks(combined))

        return self._summarize_single_chunk(combined)

    def _summarize_single_chapter(self, ch: Any) -> str:
        """Helper to summarize a single chapter object, handling internal chunking if needed."""
        ch_text = ch.plain_text if hasattr(ch, "plain_text") else str(ch)
        if not ch_text.strip():
            return ""

        words = ch_text.split()
        if len(words) <= self.chunk_size:
            return self._summarize_single_chunk(ch_text)
        else:
            chunks = self._split_into_word_chunks(ch_text)
            # This might trigger further parallel map-reduce
            return self._map_reduce_chunks(chunks)

    def _summarize_by_chapters(
        self, chapters: List[Any], status_callback: Optional[Any] = None
    ) -> tuple:
        """
        Chapter-aware Map-Reduce:
        1. Summarize each chapter individually (Sequential).
        2. Combine chapter summaries → final book summary.
        Returns: (book_summary, chapter_summaries_list)
        """
        import time

        chapter_summaries = []
        total_chapters = len(chapters)

        print(f"[Summarizer] Bắt đầu tóm tắt theo chương: {total_chapters} chương")

        for i, ch in enumerate(chapters):
            start_ch = time.time()
            title = getattr(ch, "title", f"Chương {i+1}")
            msg = f"[{i+1}/{total_chapters}] Đang tóm tắt: {title}..."
            print(f"[Summarizer] {msg}")

            if status_callback:
                status_callback(msg, i + 1, total_chapters)

            ch_summary = self._summarize_single_chapter(ch)
            chapter_summaries.append(ch_summary)

            elapsed = time.time() - start_ch
            done_msg = f"  -> Xong {title} trong {elapsed:.2f}s"
            print(f"[Summarizer] {done_msg}")
            if status_callback:
                status_callback(done_msg, i + 1, total_chapters)

        # Final reduce across all chapter summaries
        final_msg = "Đang tổng hợp tóm tắt toàn bộ sách..."
        print(f"[Summarizer] {final_msg}")
        if status_callback:
            status_callback(final_msg, total_chapters, total_chapters)
        non_empty = [s for s in chapter_summaries if s.strip()]
        if not non_empty:
            book_summary = ""
        elif len(non_empty) == 1:
            book_summary = non_empty[0]
        else:
            combined = " \n ".join(non_empty)
            if len(combined.split()) > self.chunk_size:
                book_summary = self._map_reduce_chunks(
                    self._split_into_word_chunks(combined)
                )
            else:
                book_summary = self._summarize_single_chunk(combined)

        return book_summary, chapter_summaries

    # ─────────────────────────────────────────────
    # Main pipeline entry
    # ─────────────────────────────────────────────

    def _run_pipeline(
        self,
        text: str,
        chapters: Optional[List[Any]] = None,
        status_callback: Optional[Any] = None,
    ) -> SummarizerOutput:
        """Run the full summarization pipeline (blocking)."""
        self._load_model()

        # 1. Fast heuristic extraction from raw text
        primary_mood = self._detect_primary_mood(text)
        entities = self._extract_entities(text[:50000])
        keywords = self._extract_keywords(text)

        # 2. Chapter-aware summarization if chapters provided, else word-chunk fallback
        if chapters is not None and len(chapters) > 0:
            book_summary, chapter_summaries = self._summarize_by_chapters(
                chapters, status_callback
            )
        else:
            print(
                "[Summarizer] Không tìm thấy chương, chuyển sang tóm tắt theo đoạn văn (word-chunks)."
            )
            chunks = self._split_into_word_chunks(text)
            book_summary = self._map_reduce_chunks(chunks)
            chapter_summaries = []

        return SummarizerOutput(
            summary=book_summary,
            primary_mood=primary_mood,
            keywords=keywords,
            entities=entities,
            chapter_summaries=chapter_summaries,
        )

    # ─────────────────────────────────────────────
    # Agent interface
    # ─────────────────────────────────────────────

    async def run(self, input_data: SummarizerInput) -> AgentResult:
        try:
            if isinstance(input_data, dict):
                input_data = SummarizerInput(
                    text=input_data.get("text", ""),
                    chapters=input_data.get("chapters"),
                    status_callback=input_data.get("status_callback"),
                )

            # Run heavy inference in a thread pool to not block the event loop
            output = await asyncio.to_thread(
                self._run_pipeline,
                input_data.text,
                input_data.chapters,
                input_data.status_callback,
            )
            return AgentResult(
                success=True,
                data=output,
                metadata={
                    "method": "chapter-aware" if input_data.chapters else "word-chunk",
                    "chapter_count": (
                        len(input_data.chapters) if input_data.chapters else 0
                    ),
                },
            )

        except Exception as e:
            import traceback

            traceback.print_exc()
            return AgentResult(success=False, error=str(e))


# ==========================================
# Quick test (python src/agents/summarizer.py)
# ==========================================
if __name__ == "__main__":

    async def test_agent():
        agent = SummarizerAgent()

        mock_text = (
            "Trương Tiểu Phàm tỉnh dậy trong một căn phòng tối om. "
            "Hắn cảm thấy đau nhức khắp cơ thể, ký ức về trận chiến tại núi Thanh Vân vẫn còn mồn một. "
            "Máu chảy lênh láng, tiếng gươm đao va chạm chát chúa. "
            "Hắn nhớ Bích Dao đã đỡ cho hắn một đòn chí mạng. "
        ) * 40  # Force multi-chunk

        print("Starting test...")
        res = await agent.run(SummarizerInput(text=mock_text))

        if res.success:
            print("\n--- RESULT ---")
            print(f"Entities: {res.data.entities}")
            print(f"Keywords: {res.data.keywords}")
            print(f"Mood: {res.data.primary_mood}")
            print(f"Summary:\n{res.data.summary}")
        else:
            print(f"Error: {res.error}")

    asyncio.run(test_agent())
