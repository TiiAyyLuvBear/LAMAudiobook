"""
TTS Engine and Cache abstractions for Audio generation.
"""
from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path
import hashlib

class CacheManager:
    """Manages audio cache for exact deterministic generation paths"""
    def __init__(self, cache_dir: str = "data/audio_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def _generate_key(self, text: str, voice_id: str, speed: float, pitch: float) -> str:
        # Create deterministic key based on synthesis inputs
        key_str = f"{text}|{voice_id}|{speed}|{pitch}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()
        
    def get_audio_path(self, text: str, voice_id: str, speed: float, pitch: float) -> Optional[str]:
        """Check if audio already exists in cache"""
        key = self._generate_key(text, voice_id, speed, pitch)
        path = self.cache_dir / f"{key}.wav"
        if path.exists():
            return str(path)
        return None
        
    def get_cache_path_for_generation(self, text: str, voice_id: str, speed: float, pitch: float) -> str:
        """Get the destination path to generate to"""
        key = self._generate_key(text, voice_id, speed, pitch)
        return str(self.cache_dir / f"{key}.wav")


class XTTSEngine(ABC):
    """Abstract interface for XTTS Core Model to prevent leakage"""
    @abstractmethod
    def synthesize(self, text: str, voice_id: str, speed: float, pitch: float, output_path: str) -> None:
        pass


class MockXTTSEngine(XTTSEngine):
    """Stub engine for testing architecture without GPU"""
    def synthesize(self, text: str, voice_id: str, speed: float, pitch: float, output_path: str) -> None:
        self._write_mock_wav(output_path)
        
    def _write_mock_wav(self, output_path: str) -> None:
        with open(output_path, "wb") as f:
            # write a minimal 44-byte valid wav header
            import struct
            f.write(b'RIFF')
            f.write(struct.pack('<L', 36))
            f.write(b'WAVE')
            f.write(b'fmt ')
            f.write(struct.pack('<L', 16))
            f.write(struct.pack('<H', 1)) 
            f.write(struct.pack('<H', 1))
            f.write(struct.pack('<L', 24000))
            f.write(struct.pack('<L', 48000))
            f.write(struct.pack('<H', 2))
            f.write(struct.pack('<H', 16))
            f.write(b'data')
            f.write(struct.pack('<L', 0))

class RealXTTSEngine(XTTSEngine):
    """Production XTTS Engine integrating with local reference wavs"""
    def __init__(self, voice_dir: str = "data/voice_samples"):
        self.voice_dir = Path(voice_dir)
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        # TODO: Bỏ comment khi chạy với GPU thật
        # from TTS.api import TTS
        # self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")

    def synthesize(self, text: str, voice_id: str, speed: float, pitch: float, output_path: str) -> None:
        speaker_wav = self.voice_dir / f"{voice_id}.wav"
        
        if not speaker_wav.exists():
            print(f"WARNING: Reference audio {speaker_wav} not found! Thả fallback về Mock.")
            MockXTTSEngine().synthesize(text, voice_id, speed, pitch, output_path)
            return

        print(f"Synthesizing [Voice: {voice_id}] [Speed: {speed:.1f}]...")
        print(f" -> Using reference audio: {speaker_wav}")
        
        # TODO: Bỏ comment để gọi XTTS thật
        # self.tts.tts_to_file(
        #     text=text,
        #     speaker_wav=str(speaker_wav),
        #     language="vi",
        #     file_path=output_path,
        #     speed=speed
        # )
        
        # Xóa dòng này khi dùng model thật:
        MockXTTSEngine().synthesize(text, voice_id, speed, pitch, output_path)
