"""
Summarizer Agent — "Map-Reduce" Version (Patched).
Nhiệm vụ: Tạo Context Buffer (Summary, Mood, Keywords, Entities) cho Audiobook Pipeline.
Tối ưu hóa:
  - Threading (max_workers=2) cho T4 GPU (1 GPU thread + 1 prep thread).
  - fp16 để tiết kiệm VRAM.
  - num_beams=2 (giảm từ 4) để tăng tốc.
  - Fix mood keywords (bỏ dấu gạch dưới → khoảng trắng).
  - Language gate: dừng pipeline nếu không phải tiếng Việt.
"""

import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from collections import Counter
import logging

logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
except ImportError:
    pass

# ─────────────────────────────────────────────
# Vietnamese Language Detection
# ─────────────────────────────────────────────

_VIET_CHARS = set(
    'àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ'
    'ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ'
)


def detect_language(text: str, threshold: float = 0.015) -> str:
    """Trả về 'vi' nếu là tiếng Việt, ngược lại trả mã ước tính."""
    sample = text[:5000]
    if not sample.strip():
        return 'unknown'
    vi_count = sum(1 for c in sample if c in _VIET_CHARS)
    ratio = vi_count / len(sample)
    logger.info(f'[LangDetect] Vi-char ratio: {ratio:.4f} (threshold={threshold})')
    if ratio >= threshold:
        return 'vi'
    cjk = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff')
    if cjk / len(sample) > 0.1:
        return 'zh'
    return 'en'


def assert_vietnamese(text: str) -> None:
    """Raise LanguageError nếu văn bản không phải tiếng Việt."""
    lang = detect_language(text)
    if lang != 'vi':
        names = {'zh': 'Tiếng Trung', 'en': 'Tiếng Anh', 'unknown': 'Không xác định'}
        raise ValueError(
            f'LANGUAGE_ERROR:{names.get(lang, lang)}'
        )

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
        keywords: List[str],
        entities: List[str],
        chapter_summaries: Optional[List[str]] = None,
        primary_mood: str = '',
    ):
        self.summary = summary
        self.primary_mood = primary_mood  # kept for backward compat, filled by Classifier
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
            logger.info(f'[Summarizer] Loading {cls._model_name} (fp16 + T4 optimized)...')
            try:
                cls._tokenizer = AutoTokenizer.from_pretrained(cls._model_name)
                dtype = torch.float16 if torch.cuda.is_available() else torch.float32
                cls._model = AutoModelForSeq2SeqLM.from_pretrained(
                    cls._model_name, torch_dtype=dtype
                )
                if torch.cuda.is_available():
                    cls._model = cls._model.to('cuda')
                    gpu_name = torch.cuda.get_device_name(0)
                    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
                    logger.info(f'[Summarizer] GPU: {gpu_name} ({vram_gb:.1f}GB VRAM), fp16=True')
                elif hasattr(torch, 'xpu') and torch.xpu.is_available():
                    cls._model = cls._model.to('xpu')
                    logger.info('[Summarizer] Using XPU')
                cls._model.eval()
                logger.info('[Summarizer] Model ready.')
            except NameError:
                logger.warning('[Summarizer] Transformers not available → MOCK mode.')
                cls._model = 'MOCK'
            except Exception as e:
                logger.error(f'[Summarizer] Load failed → MOCK. Error: {e}')
                cls._model = 'MOCK'

    # ─────────────────────────────────────────────
    # Lightweight heuristic extractors (no model needed)
    # ─────────────────────────────────────────────

    def _extract_entities(self, text: str) -> List[str]:
        """Trích xuất tên riêng bằng regex heuristic (viết hoa liên tiếp)."""
        candidates = re.findall(
            r"\b[A-ZÀ-Ỹ][a-zà-ỹ]+\s[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s[A-ZÀ-Ỹ][a-zà-ỹ]+)*\b", text
        )
        return list(set([e[0] for e in Counter(candidates).most_common(5)]))

    # _detect_primary_mood đã bị xoá.
    # Mood giờ do ClassifierAgent quyết định bằng vietnamese-sbert (model-based).

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
        if self._model == "MOCK" or self._model is None:
            return chunk_text[:200] + " [MOCK SUMMARY]"

        device = next(self._model.parameters()).device
        inputs = self._tokenizer(
            chunk_text,
            return_tensors="pt",
            max_length=1024,
            truncation=True,
        ).to(device)

        with torch.no_grad():
            outputs = self._model.generate(
                inputs['input_ids'],
                max_length=200,
                min_length=30,
                length_penalty=1.2,
                num_beams=2,       # T4 patch: 4→2, ~2x faster
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

    @staticmethod
    def _extractive_chapter_summary(ch: Any, max_sentences: int = 3) -> str:
        """Trích 3 câu đầu tiên của chương làm tóm tắt (extractive, không cần model)."""
        ch_text = ch.plain_text if hasattr(ch, 'plain_text') else str(ch)
        if not ch_text.strip():
            return ''
        sentences = re.split(r'(?<=[.!?])\s+', ch_text.strip())
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 15]
        return ' '.join(meaningful[:max_sentences])

    def _summarize_by_chapters(
        self, chapters: List[Any], status_callback: Optional[Any] = None
    ) -> tuple:
        """
        Fast extractive chapter summaries + 1 ViT5 call for book summary.
        Thay vì chạy ViT5 trên mỗi chương (~8s × N), chỉ trích 3 câu đầu (~0s × N)
        rồi gộp lại → 1 lần ViT5 duy nhất cho tóm tắt toàn sách.
        """
        total_chapters = len(chapters)
        logger.info(f'[Summarizer] Extractive mode: {total_chapters} chương')

        # Phase 1: extractive summaries (instant, no model)
        chapter_summaries = []
        for i, ch in enumerate(chapters):
            title = getattr(ch, 'title', f'Chương {i+1}')
            msg = f'[{i+1}/{total_chapters}] Trích tóm tắt: {title}'
            if status_callback:
                status_callback(msg, i + 1, total_chapters)
            summary = self._extractive_chapter_summary(ch)
            chapter_summaries.append(summary)
            logger.info(f'[Summarizer] ✓ {title} (extractive)')

        # Phase 2: 1 ViT5 call for book summary
        final_msg = 'Đang tóm tắt toàn sách (1 lần ViT5)...'
        logger.info(f'[Summarizer] {final_msg}')
        if status_callback:
            status_callback(final_msg, total_chapters, total_chapters)

        non_empty = [s for s in chapter_summaries if s.strip()]
        if not non_empty:
            book_summary = ''
        else:
            combined = ' '.join(non_empty)
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
        # Language gate
        assert_vietnamese(text)

        self._load_model()

        # 1. Fast heuristic extraction (no model)
        entities = self._extract_entities(text[:50000])
        keywords = self._extract_keywords(text)

        # 2. Summarization: extractive per-chapter + 1 ViT5 for book
        if chapters is not None and len(chapters) > 0:
            book_summary, chapter_summaries = self._summarize_by_chapters(
                chapters, status_callback
            )
        else:
            logger.info('[Summarizer] Không tìm thấy chương → word-chunk fallback.')
            chunks = self._split_into_word_chunks(text)
            book_summary = self._map_reduce_chunks(chunks)
            chapter_summaries = []

        return SummarizerOutput(
            summary=book_summary,
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
