"""
Classifier Agent — Classifies narration/dialogue + detects speakers/emotions.
Combines NarrativeAgent and DialogueAgent into one agent for parallel execution.
"""
import re
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult
from types.pipeline import Chapter, Sentence
from types.audio import VoiceAssignment


class ClassifierInput:
    """Input for Classifier Agent"""
    def __init__(self, chapters: List[Any], emotion_level: str = "basic"):
        self.chapters = chapters
        self.emotion_level = emotion_level


class ClassifierOutput:
    """Output from Classifier Agent"""
    def __init__(
        self,
        annotated_chapters: List[Dict[str, Any]],
        sentences: List[Sentence],
        speakers: List[str],
        speaker_count: int,
        dialogue_ratio: float,
    ):
        self.annotated_chapters = annotated_chapters
        self.sentences = sentences
        self.speakers = speakers
        self.speaker_count = speaker_count
        self.dialogue_ratio = dialogue_ratio


class ClassifierAgent(BaseAgent):
    """
    Analyzes text to classify narration vs dialogue and detect speakers/emotions.
    Combines the responsibilities of the original NarrativeAgent and DialogueAgent.
    """

    name = "classifier"

    def _detect_dialogue(self, text: str) -> bool:
        """Heuristic: detect if text contains dialogue markers."""
        patterns = [
            r'"[^"]+?"',
            r'["\u201c\u201d]',
            r"-\s*[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ]",
        ]
        return any(re.search(p, text) for p in patterns)

    def _split_sentences(self, text: str) -> List[str]:
        """Split paragraph text into sentence-level items."""
        if not text:
            return []
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _classify_sentence(self, sentence: str) -> tuple[str, str, float]:
        """Classify a sentence as narration or dialogue, detect emotion."""
        is_dialogue = self._detect_dialogue(sentence)
        text_type = "dialogue" if is_dialogue else "narration"
        speaker = "unknown" if is_dialogue else "narrator"
        emotion = "neutral"
        if is_dialogue:
            lower = sentence.lower()
            if any(w in lower for w in ["tuyệt vời", "vui", "hạnh phúc", "mừng"]):
                emotion = "happy"
            elif any(w in lower for w in ["buồn", "đau", "thất vọng"]):
                emotion = "sad"
            elif any(w in lower for w in ["giận", "憎", "bực"]):
                emotion = "angry"
        return text_type, speaker, emotion

    async def run(self, input_data: ClassifierInput) -> AgentResult:
        try:
            chapters = input_data.chapters
            sentences: List[Sentence] = []
            annotated_chapters: List[Dict[str, Any]] = []
            dialogue_count = 0
            total_count = 0
            speakers_set = set()

            for chapter in chapters:
                chapter_dict: Dict[str, Any] = {
                    "chapter_index": getattr(chapter, "chapter_index", 1),
                    "chapter_title": getattr(chapter, "chapter_title", ""),
                    "paragraphs": [],
                }

                paragraphs = getattr(chapter, "paragraphs", [])
                for para in paragraphs:
                    para_text = getattr(para, "text", "") if not isinstance(para, dict) else para.get("text", "")
                    if not para_text:
                        continue

                    para_sents = self._split_sentences(para_text)
                    para_sentences = []
                    for sent_text in para_sents:
                        total_count += 1
                        text_type, speaker, emotion = self._classify_sentence(sent_text)
                        if text_type == "dialogue":
                            dialogue_count += 1
                        speakers_set.add(speaker)

                        sentences.append(
                            Sentence(
                                text=sent_text,
                                type=text_type,
                                speaker=speaker,
                                emotion=emotion,
                                intensity=0.5,
                                chapter_index=chapter_dict["chapter_index"],
                                paragraph_index=getattr(para, "paragraph_index", 1) if not isinstance(para, dict) else para.get("paragraph_index", 1),
                            )
                        )
                        para_sentences.append({"text": sent_text, "type": text_type, "speaker": speaker, "emotion": emotion})
                    chapter_dict["paragraphs"].append({"text": para_text, "sentences": para_sentences})

                annotated_chapters.append(chapter_dict)

            dialogue_ratio = dialogue_count / total_count if total_count > 0 else 0.0

            return AgentResult(
                success=True,
                data=ClassifierOutput(
                    annotated_chapters=annotated_chapters,
                    sentences=sentences,
                    speakers=list(speakers_set),
                    speaker_count=len(speakers_set),
                    dialogue_ratio=dialogue_ratio,
                ),
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))