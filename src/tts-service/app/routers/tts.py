from fastapi import APIRouter, HTTPException
from ..schemas.tts import TTSBatchRequest, JobResponse, JobStatusResponse
import redis
from rq import Queue
from rq.job import Job
from ..worker.tts_worker import synthesize_batch
import os

router = APIRouter()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = redis.from_url(redis_url)
q = Queue("tts_queue", connection=redis_conn)

@router.post("/batch", response_model=JobResponse)
def enqueue_tts_batch(request: TTSBatchRequest):
    try:
        job = q.enqueue(synthesize_batch, request.dict(), job_timeout=3600)
        return JobResponse(job_id=job.id, status="queued", message="Job enqueued successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/job/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        
        response = JobStatusResponse(job_id=job_id, state=status)
        if status == "finished":
            response.result = job.result
        elif status == "failed":
            response.error = str(job.exc_info)
            
        return response
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job not found: {str(e)}")
