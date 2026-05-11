from abc import ABC, abstractmethod

class BaseTTSEngine(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice_id: str, speed: float, pitch: float, output_path: str) -> None:
        """
        Synthesize audio from text and save to output_path.
        """
        pass
