# Homepage Routes/Controllers
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.homepage_service import HomepageService

router = APIRouter(prefix="/homepage", tags=["Homepage"])

@router.get("/", response_model=dict)
def get_homepage(db: Session = Depends(get_db)):
    """
    Get all homepage data in one request
    Includes: featured news, trending, latest, categories, news by category, stats
    """
    try:
        homepage_data = HomepageService.get_homepage_data(db)
        return {
            "success": True,
            "data": homepage_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats", response_model=dict)
def get_homepage_stats(db: Session = Depends(get_db)):
    """Get homepage statistics"""
    try:
        stats = HomepageService.get_stats(db)
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
