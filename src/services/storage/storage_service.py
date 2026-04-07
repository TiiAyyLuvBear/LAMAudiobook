"""
Storage Service - Handles file and data persistence.
"""

import os
import json
import shutil
from typing import Any, Dict, Optional
from pathlib import Path


class StorageService:
    """
    Service for file and data storage operations.
    
    Handles:
    - Temporary file management
    - Output file storage
    - Metadata persistence
    """
    
    def __init__(self, base_dir: str = "./storage"):
        self.base_dir = Path(base_dir)
        self.temp_dir = self.base_dir / "temp"
        self.output_dir = self.base_dir / "output"
        self.metadata_dir = self.base_dir / "metadata"
        
        # Ensure directories exist
        for dir_path in [self.temp_dir, self.output_dir, self.metadata_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def save_temp_file(self, filename: str, content: bytes) -> str:
        """Save a temporary file"""
        file_path = self.temp_dir / filename
        file_path.write_bytes(content)
        return str(file_path)
    
    def get_temp_path(self, filename: str) -> str:
        """Get path for a temporary file"""
        return str(self.temp_dir / filename)
    
    def save_output(self, filename: str, content: bytes) -> str:
        """Save output file"""
        file_path = self.output_dir / filename
        file_path.write_bytes(content)
        return str(file_path)
    
    def get_output_path(self, filename: str) -> str:
        """Get path for output file"""
        return str(self.output_dir / filename)
    
    def save_metadata(self, job_id: str, metadata: Dict[str, Any]) -> None:
        """Save job metadata"""
        file_path = self.metadata_dir / f"{job_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def load_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load job metadata"""
        file_path = self.metadata_dir / f"{job_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    
    def cleanup_temp(self, job_id: Optional[str] = None) -> None:
        """Clean up temporary files"""
        if job_id:
            # Clean specific job's temp files
            for file_path in self.temp_dir.glob(f"{job_id}*"):
                file_path.unlink()
        else:
            # Clean all temp files
            shutil.rmtree(self.temp_dir)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def file_exists(self, path: str) -> bool:
        """Check if file exists"""
        return Path(path).exists()
    
    def delete_file(self, path: str) -> bool:
        """Delete a file"""
        try:
            Path(path).unlink()
            return True
        except Exception:
            return False
