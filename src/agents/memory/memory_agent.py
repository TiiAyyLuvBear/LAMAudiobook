"""
Memory Agent - Maintains consistency across the pipeline.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from ..base import BaseAgent, AgentResult


@dataclass
class SpeakerMemory:
    """Memory of a speaker's voice characteristics"""
    speaker_id: str
    voice_id: str
    characteristics: Dict[str, Any]
    sample_segments: List[int] = field(default_factory=list)


@dataclass
class MemoryInput:
    """Input for Memory Agent"""
    action: str  # "store", "retrieve", "update"
    speaker_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class MemoryOutput:
    """Output from Memory Agent"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    all_speakers: Optional[List[SpeakerMemory]] = None


class MemoryAgent(BaseAgent):
    """
    Maintains speaker voice consistency across chapters.
    
    Stores:
    - Speaker voice assignments
    - Voice characteristics
    - Reference segments for consistency
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="memory", config=config)
        self._speaker_memory: Dict[str, SpeakerMemory] = {}
    
    async def run(self, input_data: MemoryInput) -> AgentResult:
        """
        Store or retrieve speaker memory.
        
        Args:
            input_data: MemoryInput with action and data
            
        Returns:
            AgentResult with MemoryOutput
        """
        try:
            if input_data.action == "store":
                return await self._store(input_data)
            elif input_data.action == "retrieve":
                return await self._retrieve(input_data)
            elif input_data.action == "update":
                return await self._update(input_data)
            else:
                raise ValueError(f"Unknown action: {input_data.action}")
                
        except Exception as e:
            return AgentResult(success=False, error=str(e))
    
    async def _store(self, input_data: MemoryInput) -> AgentResult:
        """Store new speaker memory"""
        if not input_data.speaker_id or not input_data.data:
            raise ValueError("speaker_id and data required for store")
        
        memory = SpeakerMemory(
            speaker_id=input_data.speaker_id,
            voice_id=input_data.data.get("voice_id", "default"),
            characteristics=input_data.data.get("characteristics", {})
        )
        self._speaker_memory[input_data.speaker_id] = memory
        
        return AgentResult(
            success=True,
            data=MemoryOutput(success=True, data={"stored": input_data.speaker_id})
        )
    
    async def _retrieve(self, input_data: MemoryInput) -> AgentResult:
        """Retrieve speaker memory"""
        if input_data.speaker_id:
            memory = self._speaker_memory.get(input_data.speaker_id)
            return AgentResult(
                success=True,
                data=MemoryOutput(
                    success=True,
                    data={"speaker": memory} if memory else None
                )
            )
        else:
            return AgentResult(
                success=True,
                data=MemoryOutput(
                    success=True,
                    all_speakers=list(self._speaker_memory.values())
                )
            )
    
    async def _update(self, input_data: MemoryInput) -> AgentResult:
        """Update existing speaker memory"""
        if not input_data.speaker_id:
            raise ValueError("speaker_id required for update")
        
        if input_data.speaker_id in self._speaker_memory:
            memory = self._speaker_memory[input_data.speaker_id]
            if input_data.data:
                memory.characteristics.update(input_data.data.get("characteristics", {}))
        
        return AgentResult(
            success=True,
            data=MemoryOutput(success=True)
        )
