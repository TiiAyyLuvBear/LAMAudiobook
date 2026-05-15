import os
from typing import Optional
from pathlib import Path
from .base import BaseTTSEngine

class VieNeuEngine(BaseTTSEngine):
    """
    VieNeu CPU-optimized TTS Engine.
    Automatically downloads the model from HuggingFace via the `vieneu` package.
    """
    _instance = None
    _instance_key = None
    _voices_cache = {}
    _preset_voice_map = {
        "female_hn_01": "Ngoc",
        "female_hn_02": "Ly",
        "female_hcm_01": "Doan",
        "female_hcm_02": "Doan",
        "male_hn_01": "Binh",
        "male_hn_02": "Tuyen",
        "male_hcm_01": "Vinh",
        "male_hcm_02": "Son",
        "child_voice_01": "Ly",
    }

    def __init__(
        self,
        mode: str = "standard",
        model_name: str = "pnnbao-ump/VieNeu-TTS-0.3B",
        emotion: str = "storytelling",
        api_base: Optional[str] = None,
        voice_dir: str = "data/voice_samples",
        device: str = "auto",
    ):
        self.mode = mode
        self.model_name = model_name
        self.emotion = emotion
        self.api_base = api_base
        self.voice_dir = Path(voice_dir)
        self.device = self._normalize_device(device or os.getenv("VIENEU_DEVICE") or os.getenv("TTS_DEVICE") or "auto")
        self.enable_voice_cloning = os.getenv("VIENEU_ENABLE_VOICE_CLONING", "0").lower() in {"1", "true", "yes"}
        self.reference_text = os.getenv(
            "VIENEU_REFERENCE_TEXT",
            "Tác phẩm dự thi bảo đảm tính khoa học, tính đảng, tính chiến đấu, tính định hướng.",
        )
        self._load_tts()

    @staticmethod
    def _normalize_device(device: str) -> str:
        requested = (device or "auto").strip().lower()
        if requested in {"gpu", "cuda:0"}:
            return "cuda"
        return requested

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch

            return torch.cuda.is_available()
        except Exception:
            return False

    def _load_tts(self):
        instance_key = (self.mode, self.model_name, self.emotion, self.api_base, self.device)
        if VieNeuEngine._instance is None or VieNeuEngine._instance_key != instance_key:
            try:
                from vieneu import Vieneu
                if self.device == "cuda" and not self._cuda_available():
                    raise RuntimeError("VIENEU_DEVICE=cuda was requested but CUDA is not available.")
                print(
                    f"[VieNeu] Initializing VieNeu TTS engine mode={self.mode} "
                    f"model={self.model_name} emotion={self.emotion} device={self.device}..."
                )
                # VieNeu SDK >=1.2 uses backbone_repo/backbone_device. Older builds used
                # model_name/device, so keep those as fallbacks after the preferred forms.
                base_variants = [
                    {"emotion": self.emotion, "backbone_device": self.device},
                    {"emotion": self.emotion, "device": self.device},
                ]
                if self.device != "auto":
                    base_variants.append({"emotion": self.emotion})
                else:
                    base_variants = [{"emotion": self.emotion}]

                candidate_kwargs = []
                for base in base_variants:
                    if self.mode == "remote":
                        remote_kwargs = {**base, "mode": "remote", "model_name": self.model_name}
                        if self.api_base:
                            remote_kwargs["api_base"] = self.api_base
                        candidate_kwargs.append(remote_kwargs)
                    candidate_kwargs.extend(
                        [
                            {**base, "mode": self.mode, "backbone_repo": self.model_name},
                            {**base, "backbone_repo": self.model_name},
                            {**base, "mode": self.mode, "model_name": self.model_name},
                            {**base, "model_name": self.model_name},
                            base,
                        ]
                    )

                last_type_error = None
                for kwargs in candidate_kwargs:
                    try:
                        VieNeuEngine._instance = Vieneu(**kwargs)
                        VieNeuEngine._instance_key = instance_key
                        print(f"[VieNeu] Constructor kwargs: {kwargs}")
                        break
                    except TypeError as exc:
                        last_type_error = exc
                if VieNeuEngine._instance is None:
                    raise last_type_error or RuntimeError("No compatible VieNeu constructor was found")
                print("[VieNeu] Engine initialized successfully.")
            except ImportError as exc:
                raise RuntimeError(
                    "The `vieneu` package is required to use VieNeuEngine. "
                    "Install it via `pip install vieneu`. Note that `espeak-ng` system dependency is also required."
                ) from exc
            except Exception as e:
                raise RuntimeError(f"Failed to load VieNeu model: {e}") from e
        self.tts = VieNeuEngine._instance

    def _get_voice_data(self, voice_id: str):
        if voice_id in self._voices_cache:
            return self._voices_cache[voice_id]
            
        try:
            preset_id = self._preset_voice_map.get(Path(voice_id).stem, voice_id)
            voice_data = self.tts.get_preset_voice(preset_id)
                
            self._voices_cache[voice_id] = voice_data
            return voice_data
        except Exception as e:
            print(f"[VieNeu] Warning: Could not load voice '{voice_id}': {e}. Using default voice.")
            return None

    def _get_reference_audio(self, voice_id: str) -> Optional[Path]:
        if os.path.isfile(voice_id):
            return Path(voice_id)
        sample_path = self.voice_dir / f"{Path(voice_id).stem}.wav"
        return sample_path if sample_path.is_file() else None

    def synthesize(self, text: str, voice_id: str, speed: float, pitch: float, output_path: str) -> None:
        if not self.tts:
            raise RuntimeError("VieNeu model is not loaded")

        print(f"Synthesizing direct VieNeu [Voice: {voice_id}] [Speed: {speed:.1f}]...")
        
        try:
            ref_audio = self._get_reference_audio(voice_id)
            if self.enable_voice_cloning and ref_audio:
                try:
                    audio = self.tts.infer(
                        text=text,
                        ref_audio=str(ref_audio),
                        ref_text=self.reference_text,
                    )
                except TypeError:
                    voice_data = self._get_voice_data(voice_id)
                    audio = self.tts.infer(text=text, voice=voice_data)
            else:
                voice_data = self._get_voice_data(voice_id)
                audio = self.tts.infer(text=text, voice=voice_data)
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Use SDK to save output
            self.tts.save(audio, str(output_file))
        except Exception as e:
            raise RuntimeError(f"VieNeu generation failed: {e}") from e
