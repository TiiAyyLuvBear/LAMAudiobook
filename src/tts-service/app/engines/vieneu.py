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
    _voices_cache = {}

    def __init__(self, mode: str = "turbo"):
        self.mode = mode
        self._load_tts()

    def _load_tts(self):
        if VieNeuEngine._instance is None:
            try:
                from vieneu import Vieneu
                print(f"[VieNeu] Initializing VieNeu TTS engine in {self.mode} mode...")
                # The SDK automatically downloads models from HuggingFace on first use.
                VieNeuEngine._instance = Vieneu(mode=self.mode)
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
            # Check if voice_id is a path to a reference audio file for zero-shot cloning
            if os.path.isfile(voice_id):
                voice_data = self.tts.encode_reference(voice_id)
            else:
                # Check if it matches a .wav file in the mounted voice_samples directory
                sample_path = os.path.join("data/voice_samples", f"{voice_id}.wav")
                if os.path.isfile(sample_path):
                    voice_data = self.tts.encode_reference(sample_path)
                else:
                    # Retrieve preset voice data
                    voice_data = self.tts.get_preset_voice(voice_id)
                
            self._voices_cache[voice_id] = voice_data
            return voice_data
        except Exception as e:
            print(f"[VieNeu] Warning: Could not load voice '{voice_id}': {e}. Using default voice.")
            return None

    def synthesize(self, text: str, voice_id: str, speed: float, pitch: float, output_path: str) -> None:
        if not self.tts:
            raise RuntimeError("VieNeu model is not loaded")

        print(f"Synthesizing direct VieNeu [Voice: {voice_id}] [Speed: {speed:.1f}]...")
        
        # Determine voice config
        voice_data = self._get_voice_data(voice_id)

        # Note: 'speed' and 'pitch' adjustments might require manual post-processing 
        # or specific parameters if `infer` supports them. 
        # For now, we rely on the base TTS inference.
        try:
            audio = self.tts.infer(text=text, voice=voice_data)
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Use SDK to save output
            self.tts.save(audio, str(output_file))
        except Exception as e:
            raise RuntimeError(f"VieNeu generation failed: {e}") from e
