"""
Storage service for audiobook jobs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class StorageService:
    """Filesystem layout for queued audiobook jobs."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.getenv("STORAGE_DIR", "./storage"))
        self.jobs_dir = self.base_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def create_job_dirs(self, job_id: str) -> Dict[str, Path]:
        root = self.job_dir(job_id)
        paths = {
            "root": root,
            "input": root / "input",
            "segments": root / "segments",
            "output": root / "output",
            "logs": root / "logs",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    def input_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "input" / "book.epub"

    def output_path(self, job_id: str, output_format: str = "mp3") -> Path:
        return self.job_dir(job_id) / "output" / f"audiobook.{output_format}"

    def metadata_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "metadata.json"

    def log_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "logs" / "logs.txt"

    def save_input_file(self, job_id: str, content: bytes) -> str:
        self.create_job_dirs(job_id)
        path = self.input_path(job_id)
        path.write_bytes(content)
        return str(path)

    def save_metadata(self, job_id: str, metadata: Dict[str, Any]) -> None:
        self.create_job_dirs(job_id)
        self.metadata_path(job_id).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self.metadata_path(job_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def append_log(self, job_id: str, message: str) -> None:
        self.create_job_dirs(job_id)
        with self.log_path(job_id).open("a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")

    def read_logs(self, job_id: str, max_lines: int = 200) -> str:
        path = self.log_path(job_id)
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])

    def file_exists(self, path: str) -> bool:
        return Path(path).exists()
