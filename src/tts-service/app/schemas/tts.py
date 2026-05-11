from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class TTSSegmentRequest(BaseModel):
    text: str
    voice_id: str
    speed: float = 1.0
    pitch: float = 1.0
    output_path: str
    segment_index: int
    chapter_index: int

class TTSBatchRequest(BaseModel):
    segments: List[TTSSegmentRequest]
    output_dir: str
    
class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str

class JobStatusResponse(BaseModel):
    job_id: str
    state: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
