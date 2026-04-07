"""
API Routes - HTTP endpoints for audiobook generation.

NOTE: This layer only accepts requests and delegates to workflows.
NO business logic or TTS calls here.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from ..workflows import AudiobookPipeline
from ..workflows.audiobook_pipeline import PipelineConfig
from ..services.queue import QueueService
from ..services.storage import StorageService


router = APIRouter(prefix="/api/v1/audiobook", tags=["audiobook"])

# Service instances
queue_service = QueueService()
storage_service = StorageService()


class GenerateRequest(BaseModel):
    """Request to generate audiobook"""
    output_format: str = "mp3"
    normalize_audio: bool = True
    add_chapters: bool = True


class JobStatusResponse(BaseModel):
    """Job status response"""
    job_id: str
    status: str
    progress: float
    error: Optional[str] = None


@router.post("/generate")
async def generate_audiobook(
    file: UploadFile = File(...),
    config: GenerateRequest = GenerateRequest()
):
    """
    Start audiobook generation job.
    
    Accepts file upload, enqueues job, returns job ID.
    NO processing happens here - delegates to workflow via queue.
    """
    # Save uploaded file
    file_content = await file.read()
    file_path = storage_service.save_temp_file(file.filename, file_content)
    
    # Enqueue job
    job_id = await queue_service.enqueue(
        job_type="audiobook_generation",
        payload={
            "input_file": file_path,
            "output_format": config.output_format,
            "normalize_audio": config.normalize_audio,
            "add_chapters": config.add_chapters
        }
    )
    
    return {"job_id": job_id, "status": "queued"}


@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Get job status.
    
    Returns current status and progress of a generation job.
    """
    status = await queue_service.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return status


@router.delete("/job/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancel a pending job.
    """
    success = await queue_service.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel job")
    
    return {"status": "cancelled"}


@router.get("/job/{job_id}/download")
async def download_audiobook(job_id: str):
    """
    Download completed audiobook.
    """
    job = await queue_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status.value != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    
    # Return file path for download
    return {"download_url": job.result.get("output_path") if job.result else None}
