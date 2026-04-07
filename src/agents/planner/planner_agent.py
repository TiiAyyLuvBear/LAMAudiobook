"""
Planner Agent - Decides processing strategy for the document.
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass

from ..base import BaseAgent, AgentResult


@dataclass
class PlannerInput:
    """Input for Planner Agent"""
    file_path: str
    file_type: str  # pdf, epub, txt
    metadata: Optional[Dict[str, Any]] = None


@dataclass  
class PlannerOutput:
    """Output from Planner Agent"""
    needs_ocr: bool
    speaker_mode: str  # "single" or "multi"
    emotion_level: str  # "none", "basic", "full"
    language: str
    processing_hints: Dict[str, Any]


class PlannerAgent(BaseAgent):
    """
    Analyzes document and decides processing strategy.
    
    Outputs:
    - OCR requirements
    - Speaker mode (single voice vs multi-voice)
    - Emotion detection level
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="planner", config=config)
    
    async def run(self, input_data: PlannerInput) -> AgentResult:
        """
        Analyze document and create processing plan.
        
        Args:
            input_data: PlannerInput with file info
            
        Returns:
            AgentResult with PlannerOutput
        """
        try:
            # TODO: Implement actual planning logic
            # - Detect if OCR needed (scanned PDF)
            # - Analyze content for dialogue (multi-speaker)
            # - Detect language
            
            output = PlannerOutput(
                needs_ocr=False,
                speaker_mode="single",
                emotion_level="basic",
                language="vi",
                processing_hints={}
            )
            
            return AgentResult(
                success=True,
                data=output,
                metadata={"file": input_data.file_path}
            )
            
        except Exception as e:
            return AgentResult(success=False, error=str(e))
