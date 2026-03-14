# Homepage Routes/Controllers
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..controllers.homepage_controller import HomepageController
from ..database import get_db

router = APIRouter(prefix="/homepage", tags=["Homepage"])

@router.get("/", response_model=dict)
def get_homepage(db: Session = Depends(get_db)):
    """
    Get all homepage data in one request
    Includes: featured news, trending, latest, categories, news by category, stats
    """
    return HomepageController.get_homepage(db=db)

@router.get("/stats", response_model=dict)
def get_homepage_stats(db: Session = Depends(get_db)):
    """Get homepage statistics"""
    return HomepageController.get_homepage_stats(db=db)
