"""
Classifier Agent — "Deep Consistency" Version.
Phân loại ngữ nghĩa cho từng câu để đảm bảo sự nhất quán và chính xác tuyệt đối.

Improvements v2:
- Fixed: dialogue_ratio now correctly computed
- Fixed: Distributed sentence sampling across chapters (not just first 30)
- Added: recommended_voice_style via cosine similarity on voice labels
"""

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
import re
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

try:
    from .base import BaseAgent, AgentResult
except ImportError:
    BaseAgent = object

    class AgentResult:
        def __init__(self, success, data=None, error=None):
            self.success, self.data, self.error = success, data, error


class ClassifierInput:
    def __init__(
        self,
        context_buffer=None,
        text: Optional[str] = None,
        file_path: Optional[str] = None,
        chapters: Optional[
            List[Any]
        ] = None,  # List[ChapterBlock] — for distributed sampling
    ):
        self.context_buffer = context_buffer
        self.text = text
        self.file_path = file_path
        self.chapters = chapters or []


class ClassifierOutput:
    def __init__(
        self,
        genre: Optional[str] = None,
        mood: Optional[str] = None,
        dialogue_ratio: float = 0.0,
        recommended_voice_style: Optional[str] = None,
        sentences: Optional[List[dict]] = None,
    ):
        self.genre = genre
        self.mood = mood
        self.dialogue_ratio = dialogue_ratio
        self.recommended_voice_style = recommended_voice_style
        self.sentences = sentences or []


class ClassifierAgent(BaseAgent):
    name = "classifier"
    _tokenizer = None
    _model = None
    _model_name = "keepitreal/vietnamese-sbert"

    # Genre labels for zero-shot classification
    GENRES = [
        "Trinh thám / Kinh dị",
        "Chiến tranh / Lịch sử",
        "Kiếm hiệp / Tiên hiệp",
        "Kỹ năng / Tư duy",
        "Ngôn tình",
        "Văn học / Đời sống",
    ]

    # Emotion labels for sentence classification
    MOODS = [
        "Bí ẩn / Hồi hộp",
        "Căng thẳng",
        "U buồn / Bi thương",
        "Vui vẻ / Hào hứng",
        "Lãng mạn / Nhẹ nhàng",
        "Chiêm nghiệm / Suy ngẫm",
    ]

    # Voice style labels for TTS recommendation
    VOICE_STYLES = [
        "calm and warm",
        "dramatic and intense",
        "light and playful",
        "deep and solemn",
        "mysterious and tense",
        "romantic and gentle",
    ]

    # Vietnamese labels matching VOICE_STYLES order
    VOICE_STYLE_VI = [
        "Nhẹ nhàng & Ấm áp",
        "Mạnh mẽ & Kịch tính",
        "Nhẹ nhàng & Vui tươi",
        "Trầm & Trang nghiêm",
        "Huyền bí & Căng thẳng",
        "Lãng mạn & Dịu dàng",
    ]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if BaseAgent is not object:
            super().__init__(name=self.name, config=config)

    # ─────────────────────────────────────────────
    # Model
    # ─────────────────────────────────────────────

    @classmethod
    def _load_model(cls):
        if cls._model is None:
            cls._tokenizer = AutoTokenizer.from_pretrained(cls._model_name)
            cls._model = AutoModel.from_pretrained(cls._model_name)
            cls._model.eval()

    def _get_embeddings(self, texts: List[str]) -> torch.Tensor:
        self._load_model()
        inputs = self._tokenizer(
            texts, padding=True, truncation=True, max_length=128, return_tensors="pt"
        )
        with torch.no_grad():
            outputs = self._model(**inputs)
        return outputs.last_hidden_state.mean(dim=1)

    def _semantic_classify_batch(
        self, texts: List[str], labels: List[str]
    ) -> List[str]:
        """Batch cosine-similarity classification against label embeddings."""
        text_embs = self._get_embeddings(texts)  # (N, D)
        label_embs = self._get_embeddings(labels)  # (M, D)
        sim_matrix = F.cosine_similarity(
            text_embs.unsqueeze(1), label_embs.unsqueeze(0), dim=2
        )
        best_indices = torch.argmax(sim_matrix, dim=1)
        return [labels[i.item()] for i in best_indices]

    # ─────────────────────────────────────────────
    # Sampling helpers
    # ─────────────────────────────────────────────

    @staticmethod
    def _extract_sentences_from_text(text: str, max_sentences: int = 30) -> List[str]:
        """Split text into sentences and return up to max_sentences."""
        sentences = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 10
        ]
        return sentences[:max_sentences]

    @staticmethod
    def _distributed_sample(chapters: List[Any], total: int = 60) -> List[str]:
        """
        Sample sentences evenly distributed across chapters.
        Each chapter contributes roughly (total / num_chapters) sentences.
        """
        if not chapters:
            return []

        per_chapter = max(1, total // len(chapters))
        sampled: List[str] = []

        for ch in chapters:
            ch_text = ch.plain_text if hasattr(ch, "plain_text") else ""
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[.!?])\s+", ch_text)
                if len(s.strip()) > 10
            ]
            # Take evenly spaced sentences from the chapter
            step = max(1, len(sentences) // per_chapter)
            sampled.extend(sentences[::step][:per_chapter])

        return sampled[:total]

    # ─────────────────────────────────────────────
    # Core classification (sync, runs in thread)
    # ─────────────────────────────────────────────

    def _classify(self, input_data: ClassifierInput) -> ClassifierOutput:
        self._load_model()
        ctx = input_data.context_buffer

        # ── 1. Genre from book summary ──────────────────────────
        genre_results = self._semantic_classify_batch([ctx.summary], self.GENRES)
        genre = genre_results[0]

        # ── 2. Recommended voice style from book summary ────────
        style_results = self._semantic_classify_batch([ctx.summary], self.VOICE_STYLES)
        style_en = style_results[0]
        style_idx = self.VOICE_STYLES.index(style_en)
        recommended_voice_style = self.VOICE_STYLE_VI[style_idx]

        # ── 3. Sentence sampling ────────────────────────────────
        if input_data.chapters:
            raw_sentences = self._distributed_sample(input_data.chapters, total=60)
        elif input_data.text:
            raw_sentences = self._extract_sentences_from_text(
                input_data.text, max_sentences=60
            )
        elif input_data.file_path:
            text = Path(input_data.file_path).read_text(
                encoding="utf-8", errors="ignore"
            )
            raw_sentences = self._extract_sentences_from_text(text, max_sentences=60)
        else:
            raw_sentences = []

        if not raw_sentences:
            return ClassifierOutput(
                genre=genre,
                mood=ctx.primary_mood,
                dialogue_ratio=0.0,
                recommended_voice_style=recommended_voice_style,
            )

        # ── 4. Sentence emotion classification ──────────────────
        sent_moods = self._semantic_classify_batch(raw_sentences, self.MOODS)

        # ── 5. Dialogue detection & speaker tagging ─────────────
        dialogue_pattern = re.compile(r'^\s*[-–—"\'\"]')
        entities = ctx.entities or []
        processed_sentences = []
        dialogue_count = 0

        for i, s in enumerate(raw_sentences):
            is_dialogue = bool(dialogue_pattern.match(s))
            if is_dialogue:
                dialogue_count += 1

            speaker = "Người kể chuyện"
            s_lower = s.lower()
            for ent in entities:
                if ent.lower() in s_lower:
                    speaker = ent
                    break

            processed_sentences.append(
                {
                    "text": s,
                    "type": "dialogue" if is_dialogue else "narration",
                    "emotion": sent_moods[i],
                    "speaker": speaker,
                }
            )

        # ── 6. Dialogue ratio (fixed bug) ───────────────────────
        dialogue_ratio = dialogue_count / len(raw_sentences) if raw_sentences else 0.0

        # ── 7. Primary mood = majority vote across all sentences ─
        mood_counts = Counter(sent_moods)
        primary_mood = (
            mood_counts.most_common(1)[0][0] if sent_moods else ctx.primary_mood
        )

        return ClassifierOutput(
            genre=genre,
            mood=primary_mood,
            dialogue_ratio=dialogue_ratio,
            recommended_voice_style=recommended_voice_style,
            sentences=processed_sentences,
        )

    # ─────────────────────────────────────────────
    # Agent interface
    # ─────────────────────────────────────────────

    async def run(self, input_data: ClassifierInput) -> AgentResult:
        try:
            result = await asyncio.to_thread(self._classify, input_data)
            return AgentResult(success=True, data=result)
        except Exception as e:
            return AgentResult(success=False, error=str(e))
