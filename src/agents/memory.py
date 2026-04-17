"""
Memory Agent — Maintains speaker voice consistency across chapters.
"""
from typing import Dict, List, Optional, Any

from .base import BaseAgent, AgentResult


class SpeakerMemory:
    """Memory of a speaker's voice characteristics"""
    def __init__(self, speaker_id: str, voice_id: str, characteristics: Optional[Dict] = None):
        self.speaker_id = speaker_id
        self.voice_id = voice_id
        self.characteristics = characteristics or {}
        self.sample_segments: List[int] = []


class MemoryInput:
    """Input for Memory Agent"""
    def __init__(self, action: str, speaker_id: Optional[str] = None, data: Optional[Dict] = None):
        self.action = action  # "store", "retrieve", "update", "clear"
        self.speaker_id = speaker_id
        self.data = data or {}


class MemoryOutput:
    """Output from Memory Agent"""
    def __init__(self, success: bool, data: Optional[Dict] = None, all_speakers: Optional[List[SpeakerMemory]] = None):
        self.success = success
        self.data = data
        self.all_speakers = all_speakers


class MemoryAgent(BaseAgent):
    """
    Maintains speaker voice consistency across chapters.

    Actions:
    - store: Save a new speaker's voice assignment
    - retrieve: Get speaker memory (single or all)
    - update: Update existing speaker characteristics
    - clear: Clear all memory (new document)
    """

    name = "memory"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="memory", config=config)
        self._speaker_memory: Dict[str, SpeakerMemory] = {}

    async def run(self, input_data: MemoryInput) -> AgentResult:
        try:
            if input_data.action == "store":
                return await self._store(input_data)
            elif input_data.action == "retrieve":
                return await self._retrieve(input_data)
            elif input_data.action == "update":
                return await self._update(input_data)
            elif input_data.action == "clear":
                return await self._clear(input_data)
            else:
                raise ValueError(f"Unknown action: {input_data.action}")
        except Exception as e:
            return AgentResult(success=False, error=str(e))

    async def _store(self, input_data: MemoryInput) -> AgentResult:
        if not input_data.speaker_id:
            raise ValueError("speaker_id required for store action")
        memory = SpeakerMemory(
            speaker_id=input_data.speaker_id,
            voice_id=input_data.data.get("voice_id", "default"),
            characteristics=input_data.data.get("characteristics", {}),
        )
        self._speaker_memory[input_data.speaker_id] = memory
        return AgentResult(
            success=True,
            data=MemoryOutput(success=True, data={"stored": input_data.speaker_id}),
        )

    async def _retrieve(self, input_data: MemoryInput) -> AgentResult:
        if input_data.speaker_id:
            memory = self._speaker_memory.get(input_data.speaker_id)
            return AgentResult(
                success=True,
                data=MemoryOutput(
                    success=True,
                    data={"speaker": {
                        "speaker_id": memory.speaker_id,
                        "voice_id": memory.voice_id,
                        "characteristics": memory.characteristics,
                    } if memory else None},
                ),
            )
        else:
            return AgentResult(
                success=True,
                data=MemoryOutput(
                    success=True,
                    all_speakers=list(self._speaker_memory.values()),
                ),
            )

    async def _update(self, input_data: MemoryInput) -> AgentResult:
        if not input_data.speaker_id:
            raise ValueError("speaker_id required for update action")
        if input_data.speaker_id in self._speaker_memory:
            memory = self._speaker_memory[input_data.speaker_id]
            memory.characteristics.update(input_data.data.get("characteristics", {}))
            if "voice_id" in input_data.data:
                memory.voice_id = input_data.data["voice_id"]
        return AgentResult(success=True, data=MemoryOutput(success=True))

    async def _clear(self, input_data: MemoryInput) -> AgentResult:
        self._speaker_memory.clear()
        return AgentResult(success=True, data=MemoryOutput(success=True))