"""
Base Agent class for the Agentic AI system.

All agents must inherit from this class and implement:
- run(): Main processing logic with clear I/O
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass
from enum import Enum


class AgentStatus(Enum):
    """Agent execution status"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Standard result object for all agents"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BaseAgent(ABC):
    """
    Base class for all agents in the audiobook pipeline.
    
    Each agent must have:
    - Clear input specification
    - Clear output specification  
    - .run() method for execution
    - No direct calls to other agents
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self.status = AgentStatus.IDLE
    
    @abstractmethod
    async def run(self, input_data: Any) -> AgentResult:
        """
        Execute the agent's main processing logic.
        
        Args:
            input_data: Input data for processing
            
        Returns:
            AgentResult with success status and output data
        """
        pass
    
    def validate_input(self, input_data: Any) -> bool:
        """Override to add input validation"""
        return True
    
    def validate_output(self, output_data: Any) -> bool:
        """Override to add output validation"""
        return True
    
    async def execute(self, input_data: Any) -> AgentResult:
        """
        Run the agent with validation and error handling.
        Called by workflow - do not call directly from other agents.
        """
        try:
            self.status = AgentStatus.RUNNING
            
            if not self.validate_input(input_data):
                raise ValueError(f"Invalid input for agent {self.name}")
            
            result = await self.run(input_data)
            
            if result.success and result.data:
                if not self.validate_output(result.data):
                    raise ValueError(f"Invalid output from agent {self.name}")
            
            self.status = AgentStatus.COMPLETED if result.success else AgentStatus.FAILED
            return result
            
        except Exception as e:
            self.status = AgentStatus.FAILED
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"agent": self.name}
            )
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, status={self.status.value})"
