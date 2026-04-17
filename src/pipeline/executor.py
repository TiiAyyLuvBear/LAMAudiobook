"""
Parallel executor — runs agents concurrently using asyncio.gather().
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from agents.base import AgentResult
from .config import PipelineStage


logger = logging.getLogger(__name__)


class ParallelExecutor:
    """
    Executes multiple agents concurrently.
    All agents in a group run simultaneously via asyncio.gather().
    Failed agents do NOT abort other agents (fire-and-forget per group).
    """

    def __init__(self):
        self._results: Dict[str, AgentResult] = {}

    async def execute_group(
        self,
        agents: List[Tuple[str, Any]],  # [(name, agent_instance), ...]
        input_data: Any,
        raise_on_error: bool = False,
    ) -> Dict[str, AgentResult]:
        """
        Run a group of (name, agent) pairs concurrently.

        Args:
            agents: List of (agent_name, agent_instance) tuples
            input_data: Data to pass to each agent's execute()
            raise_on_error: If True, raise immediately on first failure

        Returns:
            Dict mapping agent_name -> AgentResult
        """
        tasks = []
        names = []

        for name, agent in agents:
            task = asyncio.create_task(agent.execute(input_data))
            tasks.append(task)
            names.append(name)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(names, results):
            if isinstance(result, Exception):
                logger.error(f"[{name}] raised exception: {result}")
                self._results[name] = AgentResult(success=False, error=str(result))
                if raise_on_error:
                    raise result
            else:
                self._results[name] = result

        return self._results

    async def execute_single(
        self,
        name: str,
        agent: Any,
        input_data: Any,
    ) -> AgentResult:
        """
        Execute a single agent (used for sequential stages).
        """
        result = await agent.execute(input_data)
        self._results[name] = result
        return result

    def get_result(self, name: str) -> Optional[AgentResult]:
        return self._results.get(name)

    def get_all_results(self) -> Dict[str, AgentResult]:
        return dict(self._results)

    def clear(self) -> None:
        self._results.clear()
