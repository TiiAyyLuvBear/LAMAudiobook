from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..services.homepage_service import HomepageService


class HomepageController:
    """Controller layer for homepage endpoints."""

    @staticmethod
    def get_homepage(db: Session) -> dict:
        try:
            homepage_data = HomepageService.get_homepage_data(db)
            return {
                "success": True,
                "data": homepage_data,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def get_homepage_stats(db: Session) -> dict:
        try:
            stats = HomepageService.get_stats(db)
            return {
                "success": True,
                "data": stats,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
