"""
Voice Agent — Assigns TTS voice IDs and prosody to speakers.
"""
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from qdrant_client import QdrantClient
except ImportError:
    QdrantClient = None

try:
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer, AutoModel
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from .base import BaseAgent, AgentResult
from schema.audio import VoiceAssignment


class VoiceInput:
    """Input for Voice Agent"""
    def __init__(self, speakers: List[str], speaker_mode: str = "multi",
                 book_summary: str = "", book_mood: str = "",
                 character_emotions: Optional[Dict[str, str]] = None):
        self.speakers = speakers
        self.speaker_mode = speaker_mode
        self.book_summary = book_summary
        self.book_mood = book_mood
        self.character_emotions = character_emotions or {}


class VoiceOutput:
    """Output from Voice Agent"""
    def __init__(self, voice_assignments: List[VoiceAssignment], narrator_voice: str):
        self.voice_assignments = voice_assignments
        self.narrator_voice = narrator_voice


class VoiceAgent(BaseAgent):
    """
    Assigns TTS voice IDs and parameters (speed, pitch) to speakers.
    Supports both 'single' mode (only narrator) and 'multi' mode.
    """

    name = "voice"

    def __init__(self, name: str = "voice", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.narrator_fallback = self.config.get("narrator_voice", "female_hn_01")
        self.db_path = "data/qdrant_voice_db"
        self.collection_name = "voices"
        self.voice_dir = Path(self.config.get("voice_dir", "data/voice_samples"))
        self.qdrant = None
        
        if QdrantClient:
            try:
                print(f"[VoiceAgent] Connecting to Qdrant at {self.db_path}...")
                self.qdrant = QdrantClient(path=self.db_path)
                if self.qdrant.collection_exists(self.collection_name):
                    print(f"[VoiceAgent] Connected to collection '{self.collection_name}'.")
                else:
                    print(f"[VoiceAgent] Collection '{self.collection_name}' not found. Vector search disabled.")
                    self.qdrant = None
            except Exception as e:
                print(f"[VoiceAgent] Qdrant connection failed: {e}")
                self.qdrant = None
        else:
            print("[VoiceAgent] QdrantClient not installed. Vector search disabled.")

        self.model_name = "keepitreal/vietnamese-sbert"
        self._tokenizer = None
        self._model = None
        
        # Fallback pool
        self.voice_pool = self.config.get("voice_pool", [
            "female_hcm_01", "female_hn_02", 
            "male_hn_01", "male_hn_02"
        ])
        self.available_voices = {
            wav.stem for wav in self.voice_dir.glob("*.wav")
        } if self.voice_dir.exists() else set()

    def _voice_exists(self, voice_id: str) -> bool:
        voice_name = Path(voice_id).stem
        if self.available_voices:
            return voice_name in self.available_voices
        return (self.voice_dir / f"{voice_name}.wav").exists()

    def _safe_voice(self, voice_id: str, fallback_voice: str) -> str:
        voice_name = Path(voice_id).stem
        if self._voice_exists(voice_name):
            return voice_name

        fallback_name = Path(fallback_voice).stem
        if self._voice_exists(fallback_name):
            print(f"[VoiceAgent] Voice '{voice_id}' has no WAV sample. Falling back to '{fallback_name}'.")
            return fallback_name

        if self.available_voices:
            first_available = sorted(self.available_voices)[0]
            print(f"[VoiceAgent] Voice '{voice_id}' has no WAV sample. Falling back to '{first_available}'.")
            return first_available

        return fallback_name

    def _load_model(self):
        if HAS_TORCH and self._model is None:
            try:
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self._model = AutoModel.from_pretrained(self.model_name)
                self._model.eval()
            except Exception:
                pass

    def _get_embedding(self, text: str):
        self._load_model()
        if not HAS_TORCH or not self._model:
            return None
        inputs = self._tokenizer([text], padding=True, truncation=True, max_length=128, return_tensors="pt")
        with torch.no_grad():
            outputs = self._model(**inputs)
        return outputs.last_hidden_state.mean(dim=1)

    def _select_voice_by_rules(self, text_context: str) -> Optional[str]:
        """Pick a narrator voice from explicit genre/mood hints before vector fallback."""
        normalized = (text_context or "").lower()
        rules = [
            (
                ("trinh thám", "kinh dị", "bí ẩn", "hồi hộp", "kịch tính", "căng thẳng", "mạnh mẽ"),
                "male_hn_02",
            ),
            (
                ("chiến tranh", "lịch sử", "trang nghiêm", "u buồn", "chiêm nghiệm", "suy ngẫm", "kiếm hiệp"),
                "male_hn_01",
            ),
            (
                ("hài hước", "vui", "vui tươi", "thanh xuân", "hào hứng", "trẻ trung"),
                "female_hcm_02",
            ),
            (
                ("ngôn tình", "tình cảm", "lãng mạn", "ấm áp", "dịu dàng"),
                "female_hn_01",
            ),
            (
                ("nhẹ nhàng", "trung tính", "kể chuyện"),
                "female_hn_02",
            ),
        ]
        for keywords, voice_id in rules:
            if any(keyword in normalized for keyword in keywords):
                return self._safe_voice(voice_id, self.narrator_fallback)
        return None

    def _select_voice_by_vector(self, text_context: str, fallback_voice: str) -> str:
        """Sử dụng Qdrant để tìm voice phù hợp nhất từ Voice DB."""
        fallback_voice = self._safe_voice(fallback_voice, self.narrator_fallback)
        if self.qdrant is None:
            return fallback_voice
            
        emb = self._get_embedding(text_context)
        if emb is None:
            return fallback_voice
            
        try:
            # emb is a tensor if HAS_TORCH is true, so we convert it to list
            query_vector = emb.squeeze().tolist() if hasattr(emb, "squeeze") else emb
            
            if hasattr(self.qdrant, "search"):
                search_result = self.qdrant.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=1,
                )
            else:
                response = self.qdrant.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=1,
                )
                search_result = getattr(response, "points", response)
            if search_result:
                voice_id = search_result[0].payload.get("voice_id", fallback_voice)
                score = search_result[0].score
                voice_id = self._safe_voice(voice_id, fallback_voice)
                print(f"[VoiceAgent] Vector match: {voice_id} (score: {score:.3f}) for context: '{text_context[:50]}...'")
                return voice_id
            else:
                print(f"[VoiceAgent] No vector match found for context: '{text_context[:50]}...'")
        except Exception as e:
            print(f"[VoiceAgent] Search error: {e}")
        
        return self._safe_voice(fallback_voice, self.narrator_fallback)

    def _map_speaker(self, speaker: Optional[str]) -> str:
        """Deterministic Voice ID assignment fallback using SHA-256 Modulo Map"""
        if not speaker or speaker.lower() == "narrator":
            return self._safe_voice(self.narrator_fallback, self.narrator_fallback)
            
        speaker_hash = hashlib.sha256(speaker.lower().encode("utf-8")).hexdigest()
        hash_int = int(speaker_hash, 16)
        
        if not self.voice_pool:
            return self.narrator_fallback
            
        assigned_index = hash_int % len(self.voice_pool)
        return self._safe_voice(self.voice_pool[assigned_index], self.narrator_fallback)

    @staticmethod
    def map_prosody(emotion: str, intensity: float) -> Tuple[float, float]:
        """Calculates (speed, pitch) modifiers from emotion and intensity"""
        speed, pitch = 1.0, 1.0
        emotion = emotion.lower() if emotion else "neutral"

        if emotion == "angry":
            speed += 0.5 * intensity
            pitch += 0.5 * intensity
        elif emotion == "sad":
            speed -= 0.3 * intensity
            pitch -= 0.3 * intensity
        elif emotion == "happy":
            speed += 0.4 * intensity

        return round(speed, 2), round(pitch, 2)

    async def run(self, input_data: VoiceInput) -> AgentResult:
        try:
            assignments: List[VoiceAssignment] = []
            
            # 1. Chọn giọng Narrator dựa trên mood/genre trước, rồi mới dùng vector fallback.
            narrator_context = f"Tóm tắt: {input_data.book_summary}. Cảm xúc: {input_data.book_mood}"
            narrator_voice = self._select_voice_by_rules(narrator_context)
            if narrator_voice:
                print(f"[VoiceAgent] Rule narrator match: {narrator_voice} for context: '{narrator_context[:80]}...'")
            else:
                narrator_voice = self._select_voice_by_vector(narrator_context, self.narrator_fallback)

            for speaker in input_data.speakers:
                if input_data.speaker_mode == "single" or speaker.lower() == "narrator":
                    vid = narrator_voice
                else:
                    # 2. Chọn giọng nhân vật dựa trên cảm xúc chủ đạo
                    char_emo = input_data.character_emotions.get(speaker, "")
                    char_context = f"Nhân vật: {speaker}. Cảm xúc chủ đạo: {char_emo}"
                    fallback_vid = self._map_speaker(speaker)
                    vid = self._select_voice_by_vector(char_context, fallback_vid)
                
                assignments.append(
                    VoiceAssignment(
                        speaker=speaker,
                        voice_id=vid,
                        voice_params={"base_speed": 1.0, "base_pitch": 1.0},
                    )
                )

            return AgentResult(
                success=True,
                data=VoiceOutput(
                    voice_assignments=assignments,
                    narrator_voice=narrator_voice,
                ),
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return AgentResult(success=False, error=str(e))
