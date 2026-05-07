"""
TTS Engine and Cache abstractions for Audio generation.
"""
from abc import ABC, abstractmethod
import os
import sys
from typing import Optional
from pathlib import Path
import hashlib
import shutil

DEFAULT_XTTS_HF_REPO = "aiMy144/XTTSv2VietAudiobook"

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
        # Write 1 second of silence at 24kHz, 16-bit mono
        sample_rate = 24000
        duration = 1.0
        num_samples = int(sample_rate * duration)
        data_size = num_samples * 2
        
        with open(output_path, "wb") as f:
            import struct
            f.write(b'RIFF')
            f.write(struct.pack('<L', 36 + data_size))
            f.write(b'WAVE')
            f.write(b'fmt ')
            f.write(struct.pack('<L', 16))
            f.write(struct.pack('<H', 1))  # PCM
            f.write(struct.pack('<H', 1))  # Mono
            f.write(struct.pack('<L', sample_rate))
            f.write(struct.pack('<L', sample_rate * 2))
            f.write(struct.pack('<H', 2))
            f.write(struct.pack('<H', 16))
            f.write(b'data')
            f.write(struct.pack('<L', data_size))
            # Write 1 second of zero-byte silence
            f.write(b'\x00' * data_size)

class RealXTTSEngine(XTTSEngine):
    """Production XTTS Engine integrating with local reference wavs"""
    _tts_instances = {}

    def __init__(
        self,
        voice_dir: str = "data/voice_samples",
        model_name_or_path: Optional[str] = None,
        config_path: Optional[str] = None,
        vocab_path: Optional[str] = None,
    ):
        self.voice_dir = Path(voice_dir)
        if not self.voice_dir.exists():
            raise RuntimeError(f"XTTS reference voice directory not found: {self.voice_dir}")
        env_model = model_name_or_path or os.getenv("XTTS_MODEL_NAME_OR_PATH")
        self.model_name_or_path = env_model or DEFAULT_XTTS_HF_REPO
        self.config_path = config_path or os.getenv("XTTS_CONFIG_PATH")
        self.vocab_path = vocab_path or os.getenv("XTTS_VOCAB_PATH")
        self.model_cache_key = "|".join(
            [
                self.model_name_or_path or "",
                self.config_path or "",
                self.vocab_path or "",
            ]
        )
        self._load_tts()

    @staticmethod
    def _find_first_existing(base_dir: Path, candidates: list[str]) -> Optional[Path]:
        for pattern in candidates:
            matches = sorted(base_dir.glob(pattern))
            for match in matches:
                if match.is_file():
                    return match
        return None

    def _resolve_local_model_files(self, model_dir: Path) -> tuple[Path, Path, Optional[Path]]:
        config = Path(self.config_path) if self.config_path else (
            self._find_first_existing(model_dir, ["config.json", "**/config.json"])
            or model_dir / "config.json"
        )
        if not config.exists():
            raise RuntimeError(
                f"XTTS config file not found: {config}. "
                "Set XTTS_CONFIG_PATH or provide a folder containing config.json."
            )

        model_path = self._find_first_existing(
            model_dir,
            ["model.pth", "best_model*.pth", "*.pth", "*.pth.tar", "**/model.pth", "**/best_model*.pth", "**/*.pth"],
        )
        if model_path is None:
            dvc_pointer = self._find_first_existing(model_dir, ["*.pth.dvc", "**/*.pth.dvc"])
            hint = (
                f" Found DVC pointer {dvc_pointer}; run dvc pull or set XTTS_MODEL_NAME_OR_PATH "
                "to the downloaded checkpoint path."
                if dvc_pointer
                else ""
            )
            raise RuntimeError(f"No XTTS checkpoint .pth found in {model_dir}.{hint}")

        vocab = Path(self.vocab_path) if self.vocab_path else self._find_first_existing(
            model_dir,
            ["vocab.json", "vocab*.json", "**/vocab.json", "**/vocab*.json"],
        )
        if vocab and not vocab.exists():
            raise RuntimeError(f"XTTS vocab file not found: {vocab}")
        return model_path, config, vocab

    def _load_from_local_path(self, model_path: Path):
        if model_path.is_dir():
            checkpoint, config, vocab = self._resolve_local_model_files(model_path)
            print(f"[XTTS] Loading local fine-tuned checkpoint: {checkpoint}")
            return self._load_xtts_checkpoint(checkpoint, config, vocab)

        if model_path.is_file():
            config = Path(self.config_path) if self.config_path else model_path.with_name("config.json")
            if not config.exists():
                raise RuntimeError(
                    f"XTTS_CONFIG_PATH is required because config file was not found next to {model_path}"
                )
            vocab = Path(self.vocab_path) if self.vocab_path else model_path.with_name("vocab.json")
            return self._load_xtts_checkpoint(model_path, config, vocab if vocab.exists() else None)

        raise RuntimeError(f"XTTS local model path does not exist: {model_path}")

    def _load_from_huggingface(self, repo_id: str):
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "huggingface_hub is required for XTTS Hugging Face repo loading. "
                "Install huggingface_hub or set XTTS_MODEL_NAME_OR_PATH to a local path."
            ) from exc

        print(f"[XTTS] Downloading Hugging Face model repo: {repo_id}")
        local_dir = Path(
            snapshot_download(
                repo_id=repo_id,
                token=os.getenv("HF_TOKEN") or None,
            )
        )
        return self._load_from_local_path(local_dir)

    @staticmethod
    def _preprocess_text(text: str, language: str = "vi") -> list[str]:
        if language == "vi":
            try:
                from vinorm import TTSnorm
                text = TTSnorm(text, unknown=False, lower=False, rule=True)
            except Exception:
                pass

        try:
            if language in ["ja", "zh-cn"]:
                sentences = [item for item in text.split("。") if item.strip()]
            else:
                from underthesea import sent_tokenize
                sentences = sent_tokenize(text)
        except Exception:
            sentences = [text]

        chunks = []
        chunk = ""
        word_count = 0
        for sentence in sentences:
            chunk += " " + sentence
            word_count += len(sentence.split())
            if word_count > 30:
                chunks.append(chunk.strip())
                chunk = ""
                word_count = 0

        if chunk.strip():
            if chunks and word_count < 15:
                chunks[-1] += " " + chunk.strip()
            else:
                chunks.append(chunk.strip())
        return chunks or [text]

    def _load_xtts_checkpoint(self, checkpoint: Path, config_path: Path, vocab_path: Optional[Path]):
        model_dir = str(config_path.parent.resolve())
        if model_dir not in sys.path:
            sys.path.insert(0, model_dir)

        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        config = XttsConfig()
        config.load_json(str(config_path))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(
            config,
            checkpoint_path=str(checkpoint),
            vocab_path=str(vocab_path) if vocab_path else None,
            use_deepspeed=False,
        )
        return model

    def _load_tts(self):
        if self.model_cache_key not in RealXTTSEngine._tts_instances:
            try:
                import torch
                if not torch.cuda.is_available():
                    raise RuntimeError("CUDA is not available. Set TTS_ENGINE=mock for tests or install GPU runtime for XTTS.")
                print(f"[XTTS] Loading direct XTTS checkpoint to CUDA: {self.model_name_or_path}")
                model_ref = Path(self.model_name_or_path)
                if model_ref.exists():
                    tts = self._load_from_local_path(model_ref)
                else:
                    tts = self._load_from_huggingface(self.model_name_or_path)
                RealXTTSEngine._tts_instances[self.model_cache_key] = tts.to("cuda")
            except ImportError as exc:
                raise RuntimeError(
                    "Direct XTTS imports failed. This runtime must match models/XTTSv2.ipynb and provide "
                    "`TTS.tts.configs.xtts_config.XttsConfig` plus `TTS.tts.models.xtts.Xtts`. "
                    f"Original import error: {exc}"
                ) from exc
            except Exception as e:
                raise RuntimeError(f"Failed to load XTTS model: {e}") from e
        self._tts_instance = RealXTTSEngine._tts_instances[self.model_cache_key]

    def synthesize(self, text: str, voice_id: str, speed: float, pitch: float, output_path: str) -> None:
        speaker_wav = self.voice_dir / f"{voice_id}.wav"
        
        if not speaker_wav.exists():
            raise RuntimeError(f"Reference audio not found for voice_id={voice_id}: {speaker_wav}")

        if self._tts_instance:
            import torch
            import torchaudio

            print(f"Synthesizing direct XTTS [Voice: {voice_id}] [Speed: {speed:.1f}]...")
            gpt_cond_latent, speaker_embedding = self._tts_instance.get_conditioning_latents(
                audio_path=str(speaker_wav),
                gpt_cond_len=self._tts_instance.config.gpt_cond_len,
                max_ref_length=self._tts_instance.config.max_ref_len,
                sound_norm_refs=self._tts_instance.config.sound_norm_refs,
            )
            wav_chunks = []
            for chunk in self._preprocess_text(text, "vi"):
                if not chunk.strip():
                    continue
                wav_chunk = self._tts_instance.inference(
                    text=chunk,
                    language="vi",
                    gpt_cond_latent=gpt_cond_latent,
                    speaker_embedding=speaker_embedding,
                    length_penalty=1.0,
                    repetition_penalty=10.0,
                    top_k=10,
                    top_p=0.5,
                )
                wav_chunks.append(torch.tensor(wav_chunk["wav"]))

            if not wav_chunks:
                raise RuntimeError("XTTS received empty text after preprocessing")

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = output_file.with_suffix(output_file.suffix + ".tmp.wav")
            torchaudio.save(str(tmp_path), torch.cat(wav_chunks, dim=0).unsqueeze(0).cpu(), 24000)
            shutil.move(str(tmp_path), str(output_file))
            return

        raise RuntimeError("XTTS model is not loaded")
