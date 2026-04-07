"""
Queue Service - Manages job queue for audiobook generation.
"""

import asyncio
import uuid
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import deque


class JobStatus(Enum):
    """Job execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """A job in the queue"""
    id: str
    job_type: str
    payload: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: float = 0.0


class QueueService:
    """
    Service for managing job queue.
    
    Features:
    - FIFO job queue
    - Job status tracking
    - Async job execution
    - Progress updates
    """
    
    def __init__(self, max_concurrent: int = 2):
        self._queue: deque[Job] = deque()
        self._jobs: Dict[str, Job] = {}
        self._handlers: Dict[str, Callable] = {}
        self._max_concurrent = max_concurrent
        self._running_count = 0
        self._lock = asyncio.Lock()
    
    def register_handler(self, job_type: str, handler: Callable) -> None:
        """Register a handler for a job type"""
        self._handlers[job_type] = handler
    
    async def enqueue(self, job_type: str, payload: Dict[str, Any]) -> str:
        """Add a job to the queue"""
        job = Job(
            id=str(uuid.uuid4()),
            job_type=job_type,
            payload=payload
        )
        
        async with self._lock:
            self._queue.append(job)
            self._jobs[job.id] = job
        
        # Try to process queue
        asyncio.create_task(self._process_queue())
        
        return job.id
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        return self._jobs.get(job_id)
    
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status"""
        job = self._jobs.get(job_id)
        if not job:
            return None
        
        return {
            "id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error": job.error
        }
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job"""
        job = self._jobs.get(job_id)
        if job and job.status == JobStatus.PENDING:
            job.status = JobStatus.CANCELLED
            return True
        return False
    
    async def update_progress(self, job_id: str, progress: float) -> None:
        """Update job progress"""
        job = self._jobs.get(job_id)
        if job:
            job.progress = progress
    
    async def _process_queue(self) -> None:
        """Process jobs in the queue"""
        async with self._lock:
            if self._running_count >= self._max_concurrent:
                return
            
            while self._queue and self._running_count < self._max_concurrent:
                job = self._queue.popleft()
                if job.status == JobStatus.CANCELLED:
                    continue
                
                self._running_count += 1
                asyncio.create_task(self._execute_job(job))
    
    async def _execute_job(self, job: Job) -> None:
        """Execute a single job"""
        try:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            
            handler = self._handlers.get(job.job_type)
            if not handler:
                raise ValueError(f"No handler for job type: {job.job_type}")
            
            result = await handler(job.payload, lambda p: self._update_progress(job, p))
            
            job.status = JobStatus.COMPLETED
            job.result = result
            
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            
        finally:
            job.completed_at = datetime.utcnow()
            job.progress = 1.0 if job.status == JobStatus.COMPLETED else job.progress
            
            async with self._lock:
                self._running_count -= 1
            
            # Process more jobs
            asyncio.create_task(self._process_queue())
    
    def _update_progress(self, job: Job, progress: float) -> None:
        """Internal progress update"""
        job.progress = progress
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get queue statistics"""
        stats = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0
        }
        
        for job in self._jobs.values():
            stats[job.status.value] += 1
        
        return stats
