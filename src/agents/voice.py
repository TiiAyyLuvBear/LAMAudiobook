"""
Voice Agent — Assigns TTS voice IDs and prosody to speakers.
"""
import hashlib
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

    def _select_voice_by_vector(self, text_context: str, fallback_voice: str) -> str:
        """Sử dụng Qdrant để tìm voice phù hợp nhất từ Voice DB."""
        if self.qdrant is None:
            return fallback_voice
            
        emb = self._get_embedding(text_context)
        if emb is None:
            return fallback_voice
            
        try:
            # emb is a tensor if HAS_TORCH is true, so we convert it to list
            query_vector = emb.squeeze().tolist() if hasattr(emb, "squeeze") else emb
            
            search_result = self.qdrant.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=1
            )
            if search_result:
                voice_id = search_result[0].payload.get("voice_id", fallback_voice)
                score = search_result[0].score
                print(f"[VoiceAgent] Vector match: {voice_id} (score: {score:.3f}) for context: '{text_context[:50]}...'")
                return voice_id
            else:
                print(f"[VoiceAgent] No vector match found for context: '{text_context[:50]}...'")
        except Exception as e:
            print(f"[VoiceAgent] Search error: {e}")
        
        return fallback_voice

    def _map_speaker(self, speaker: Optional[str]) -> str:
        """Deterministic Voice ID assignment fallback using SHA-256 Modulo Map"""
        if not speaker or speaker.lower() == "narrator":
            return self.narrator_fallback
            
        speaker_hash = hashlib.sha256(speaker.lower().encode("utf-8")).hexdigest()
        hash_int = int(speaker_hash, 16)
        
        if not self.voice_pool:
            return self.narrator_fallback
            
        assigned_index = hash_int % len(self.voice_pool)
        return self.voice_pool[assigned_index]

    def map_prosody(self, emotion: str, intensity: float) -> Tuple[float, float]:
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
            
            # 1. Chọn giọng Narrator dựa trên book_summary và book_mood
            narrator_context = f"Tóm tắt: {input_data.book_summary}. Cảm xúc: {input_data.book_mood}"
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
