"""
Classifier Agent — "Deep Consistency" Version.
Phân loại ngữ nghĩa cho từng câu để đảm bảo sự nhất quán và chính xác tuyệt đối.

Improvements v2:
- Fixed: dialogue_ratio now correctly computed
- Fixed: Distributed sentence sampling across chapters (not just first 30)
- Added: recommended_voice_style via cosine similarity on voice labels
"""

try:
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer, AutoModel
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
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

    # Vietnamese query phrases dùng để embed khi classify voice style
    # (tránh so sánh tiếng Việt vs tiếng Anh trong không gian embedding)
    VOICE_STYLE_QUERY = [
        "giọng nhẹ nhàng, ấm áp, bình yên, thư thái",
        "giọng mạnh mẽ, kịch tính, căng thẳng, hào hùng",
        "giọng vui tươi, nhẹ nhõm, tươi sáng, hóm hỉnh",
        "giọng trầm, trang nghiêm, sâu lắng, u uẩn",
        "giọng huyền bí, hồi hộp, bí ẩn, rùng rợn",
        "giọng lãng mạn, dịu dàng, tình cảm, êm đềm",
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
            if not HAS_TORCH:
                cls._model = "MOCK"
                return
            try:
                cls._tokenizer = AutoTokenizer.from_pretrained(cls._model_name)
                cls._model = AutoModel.from_pretrained(cls._model_name)
                cls._model.eval()
            except Exception:
                cls._model = "MOCK"

    def _get_embeddings(self, texts: List[str]) -> Any:
        self._load_model()
        if self._model == "MOCK" or self._model is None or not HAS_TORCH:
            return None
        inputs = self._tokenizer(
            texts, padding=True, truncation=True, max_length=128, return_tensors="pt"
        )
        with torch.no_grad():
            outputs = self._model(**inputs)
        return outputs.last_hidden_state.mean(dim=1)

    def _semantic_classify_batch(
        self, texts: List[str], labels: List[str],
        query_labels: Optional[List[str]] = None,
        temperature: float = 0.1,
        threshold: float = 0.30,
        default_label: str = 'Bình thường',
    ) -> List[str]:
        """Batch cosine-similarity classification.

        Args:
            query_labels: nếu khác None, dùng để embed thay vì labels
                          (tránh lệch ngôn ngữ Việt/Anh).
            temperature:  softmax(sim / T) — T nhỏ hơn = sắc nét hơn.
            threshold:    nếu max_cosine_sim < threshold → trả default_label
                          thay vì ép chọn nhãn gần nhất dù text trung tính.
            default_label: nhãn trả về khi không vượt threshold.
        """
        import random
        text_embs = self._get_embeddings(texts)  # (N, D)
        if text_embs is None:
            # MOCK: trả ngẫu nhiên để không bị thiên vị về labels[0]
            return [random.choice(labels) for _ in texts]

        embed_targets = query_labels if query_labels else labels
        label_embs = self._get_embeddings(embed_targets)  # (M, D)

        sim_matrix = F.cosine_similarity(
            text_embs.unsqueeze(1), label_embs.unsqueeze(0), dim=2
        )  # (N, M)

        # Threshold check: câu nào không rõ ràng → gán default_label
        max_sims, best_indices_raw = sim_matrix.max(dim=1)  # (N,)

        # Softmax trên các câu vượt threshold (tránh hard argmax)
        weights = torch.softmax(sim_matrix / temperature, dim=1)  # (N, M)
        best_indices = torch.argmax(weights, dim=1)              # (N,)

        results = []
        for i in range(len(texts)):
            if max_sims[i].item() < threshold:
                results.append(default_label)
            else:
                results.append(labels[best_indices[i].item()])
        return results

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

        # ── 1. Sentence sampling ────────────────────────────────
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

        # ── 2. Voice style from book summary (Vietnamese queries) ──
        # D\u00f9ng VOICE_STYLE_QUERY (ti\u1ebfng Vi\u1ec7t) thay v\u00ec VOICE_STYLES (ti\u1ebfng Anh)
        # \u0111\u1ec3 tr\u00e1nh l\u1ec7ch ng\u00f4n ng\u1eef khi embed v\u1edbi vietnamese-sbert
        style_results = self._semantic_classify_batch(
            [ctx.summary],
            labels=self.VOICE_STYLES,
            query_labels=self.VOICE_STYLE_QUERY,
        )
        style_en = style_results[0]
        style_idx = self.VOICE_STYLES.index(style_en)
        recommended_voice_style = self.VOICE_STYLE_VI[style_idx]

        if not raw_sentences:
            return ClassifierOutput(
                genre=None,
                mood="Bình thường",
                dialogue_ratio=0.0,
                recommended_voice_style=recommended_voice_style,
            )

        # ── 3. Sentence mood classification (model-based) ───────
        sent_moods = self._semantic_classify_batch(raw_sentences, self.MOODS)

        # ── 4. Dialogue detection & speaker tagging ─────────────
        dialogue_pattern = re.compile(r'^\s*[-–—"\'\u2018\u2019\u201c\u201d\u00ab\u00bb\u276c\u276d]')
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

        # ── 5. Dialogue ratio ───────────────────────────────────
        dialogue_ratio = dialogue_count / len(raw_sentences) if raw_sentences else 0.0

        # ── 6. Primary mood = majority vote (model-based, 1 mood cho toàn sách)
        mood_counts = Counter(sent_moods)
        primary_mood = mood_counts.most_common(1)[0][0] if sent_moods else "Bình thường"

        return ClassifierOutput(
            genre=None,  # Genre đã bỏ, tập trung vào mood/voice
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
