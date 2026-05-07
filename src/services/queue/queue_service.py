"""
SQLite-backed FIFO queue for audiobook generation jobs.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    job_type: str
    payload: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: float = 0.0
    stage: str = "queued"
    current_chapter: int = 0
    total_chapters: int = 0


class QueueService:
    """Persistent single-process async queue with SQLite metadata."""

    def __init__(self, db_path: Optional[str] = None, max_concurrent: Optional[int] = None):
        storage_dir = Path(os.getenv("STORAGE_DIR", "./storage"))
        storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path or storage_dir / "jobs.sqlite")
        self._queue: deque[str] = deque()
        self._jobs: Dict[str, Job] = {}
        self._handlers: Dict[str, Callable] = {}
        self._max_concurrent = int(max_concurrent or os.getenv("MAX_CONCURRENT_JOBS", "1"))
        self._running_count = 0
        self._lock = asyncio.Lock()
        self._started = False
        self._init_db()
        self._load_existing_jobs()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL DEFAULT 'queued',
                    current_chapter INTEGER NOT NULL DEFAULT 0,
                    total_chapters INTEGER NOT NULL DEFAULT 0,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
                """
            )
            conn.commit()

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(value) if value else None

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            job_type=row["job_type"],
            payload=json.loads(row["payload"]),
            status=JobStatus(row["status"]),
            created_at=self._parse_dt(row["created_at"]) or datetime.utcnow(),
            started_at=self._parse_dt(row["started_at"]),
            completed_at=self._parse_dt(row["completed_at"]),
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            progress=float(row["progress"]),
            stage=row["stage"],
            current_chapter=int(row["current_chapter"]),
            total_chapters=int(row["total_chapters"]),
        )

    def _load_existing_jobs(self) -> None:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at ASC").fetchall()
            for row in rows:
                job = self._row_to_job(row)
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.FAILED
                    job.error = "Server restarted while job was running."
                    job.completed_at = datetime.utcnow()
                    job.stage = "failed"
                    self._persist_job(job)
                elif job.status == JobStatus.PENDING:
                    self._queue.append(job.id)
                self._jobs[job.id] = job

    def _persist_job(self, job: Job) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, job_type, payload, status, progress, stage,
                    current_chapter, total_chapters, result, error,
                    created_at, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload=excluded.payload,
                    status=excluded.status,
                    progress=excluded.progress,
                    stage=excluded.stage,
                    current_chapter=excluded.current_chapter,
                    total_chapters=excluded.total_chapters,
                    result=excluded.result,
                    error=excluded.error,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at
                """,
                (
                    job.id,
                    job.job_type,
                    json.dumps(job.payload, ensure_ascii=False),
                    job.status.value,
                    job.progress,
                    job.stage,
                    job.current_chapter,
                    job.total_chapters,
                    json.dumps(job.result, ensure_ascii=False) if job.result else None,
                    job.error,
                    job.created_at.isoformat(),
                    job.started_at.isoformat() if job.started_at else None,
                    job.completed_at.isoformat() if job.completed_at else None,
                ),
            )
            conn.commit()

    def register_handler(self, job_type: str, handler: Callable) -> None:
        self._handlers[job_type] = handler

    async def start(self) -> None:
        self._started = True
        await self._process_queue()

    async def enqueue(
        self,
        job_type: str,
        payload: Dict[str, Any],
        job_id: Optional[str] = None,
    ) -> str:
        job = Job(id=job_id or str(uuid.uuid4()), job_type=job_type, payload=payload)
        async with self._lock:
            self._jobs[job.id] = job
            self._queue.append(job.id)
            self._persist_job(job)
        if self._started:
            asyncio.create_task(self._process_queue())
        return job.id

    async def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self._jobs.get(job_id)
        if not job:
            return None
        return {
            "job_id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "stage": job.stage,
            "current_chapter": job.current_chapter,
            "total_chapters": job.total_chapters,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error": job.error,
            "result": job.result,
        }

    async def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return False
        job.status = JobStatus.CANCELLED
        job.stage = "cancelled"
        job.completed_at = datetime.utcnow()
        self._persist_job(job)
        try:
            self._queue.remove(job_id)
        except ValueError:
            pass
        return True

    async def update_progress(self, job_id: str, progress: float, stage: Optional[str] = None) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.progress = max(0.0, min(1.0, float(progress)))
        if stage:
            job.stage = stage
        self._persist_job(job)

    async def update_state(self, job_id: str, state: Dict[str, Any]) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.progress = max(0.0, min(1.0, float(state.get("progress", job.progress))))
        job.stage = state.get("stage") or job.stage
        job.current_chapter = int(state.get("current_chapter") or job.current_chapter or 0)
        job.total_chapters = int(state.get("total_chapters") or job.total_chapters or 0)
        if state.get("error"):
            job.error = state["error"]
        self._persist_job(job)

    async def _process_queue(self) -> None:
        async with self._lock:
            while self._queue and self._running_count < self._max_concurrent:
                job_id = self._queue.popleft()
                job = self._jobs.get(job_id)
                if not job or job.status != JobStatus.PENDING:
                    continue
                self._running_count += 1
                asyncio.create_task(self._execute_job(job))

    async def _execute_job(self, job: Job) -> None:
        try:
            job.status = JobStatus.RUNNING
            job.stage = "running"
            job.started_at = datetime.utcnow()
            self._persist_job(job)

            handler = self._handlers.get(job.job_type)
            if not handler:
                raise ValueError(f"No handler for job type: {job.job_type}")

            result = await handler(
                job.payload,
                lambda progress, stage=None: self.update_progress(job.id, progress, stage),
                lambda state: self.update_state(job.id, state),
            )
            if not result or not result.get("success"):
                raise RuntimeError((result or {}).get("error") or "Job failed")

            job.status = JobStatus.COMPLETED
            job.stage = "completed"
            job.progress = 1.0
            job.result = result
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.stage = "failed"
            job.error = str(exc)
        finally:
            job.completed_at = datetime.utcnow()
            self._persist_job(job)
            async with self._lock:
                self._running_count -= 1
            asyncio.create_task(self._process_queue())

    def get_queue_stats(self) -> Dict[str, int]:
        stats = {status.value: 0 for status in JobStatus}
        for job in self._jobs.values():
            stats[job.status.value] += 1
        return stats
