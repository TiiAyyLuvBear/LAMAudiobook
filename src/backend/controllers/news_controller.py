import math
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.news import News
from ..schemas.news_schema import LikeRequest, NewsCreate, NewsUpdate
from ..services.news_service import NewsService


class NewsController:
    """Controller layer for news endpoints."""

    @staticmethod
    def get_news_list(
        db: Session,
        page: int,
        limit: int,
        status: Optional[str],
        category_id: Optional[int],
        is_featured: Optional[bool],
        is_trending: Optional[bool],
        search: Optional[str],
    ) -> dict:
        try:
            news_list, total = NewsService.get_all(
                db=db,
                page=page,
                limit=limit,
                status=status,
                category_id=category_id,
                is_featured=is_featured,
                is_trending=is_trending,
                search=search,
            )

            total_pages = math.ceil(total / limit) if total else 0

            return {
                "success": True,
                "data": [news.to_dict(include_content=False) for news in news_list],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "total_pages": total_pages,
                },
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def get_featured_news(db: Session, limit: int) -> dict:
        try:
            news_list = NewsService.get_featured(db, limit=limit)
            return {
                "success": True,
                "data": [news.to_dict(include_content=False) for news in news_list],
                "count": len(news_list),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def get_trending_news(db: Session, limit: int) -> dict:
        try:
            news_list = NewsService.get_trending(db, limit=limit)
            return {
                "success": True,
                "data": [news.to_dict(include_content=False) for news in news_list],
                "count": len(news_list),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def get_latest_news(db: Session, limit: int) -> dict:
        try:
            news_list = NewsService.get_latest(db, limit=limit)
            return {
                "success": True,
                "data": [news.to_dict(include_content=False) for news in news_list],
                "count": len(news_list),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def get_news_detail(db: Session, news: News) -> dict:
        NewsService.increment_view(db, news.id)
        return {
            "success": True,
            "data": news.to_dict(include_content=True),
        }

    @staticmethod
    def get_news_by_slug(db: Session, news: News) -> dict:
        NewsService.increment_view(db, news.id)
        return {
            "success": True,
            "data": news.to_dict(include_content=True),
        }

    @staticmethod
    def create_news(db: Session, news_data: NewsCreate) -> dict:
        try:
            news = NewsService.create(db, news_data.model_dump())
            return {
                "success": True,
                "message": "News created successfully",
                "data": news.to_dict(include_content=True),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def update_news(db: Session, news_id: int, news_data: NewsUpdate) -> dict:
        try:
            update_data = {
                key: value
                for key, value in news_data.model_dump().items()
                if value is not None
            }

            news = NewsService.update(db, news_id, update_data)
            if not news:
                raise HTTPException(status_code=404, detail="News not found")

            return {
                "success": True,
                "message": "News updated successfully",
                "data": news.to_dict(include_content=True),
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def delete_news(db: Session, news_id: int) -> dict:
        try:
            success = NewsService.delete(db, news_id)
            if not success:
                raise HTTPException(status_code=404, detail="News not found")

            return {
                "success": True,
                "message": "News deleted successfully",
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def toggle_like_news(db: Session, news_id: int, like_data: LikeRequest) -> dict:
        try:
            success = NewsService.toggle_like(db, news_id, like_data.action)
            if not success:
                raise HTTPException(status_code=404, detail="News not found")

            return {
                "success": True,
                "message": f"{like_data.action.capitalize()} successful",
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
