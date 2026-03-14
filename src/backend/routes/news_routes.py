# News Routes/Controllers
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from ..controllers.news_controller import NewsController
from ..database import get_db
from ..middleware.news_middleware import (
    require_news_by_id,
    require_news_by_slug,
    validate_create_news_payload,
    validate_update_news_payload,
)
from ..models.news import News
from ..schemas.news_schema import NewsCreate, NewsUpdate, LikeRequest

router = APIRouter(prefix="/news", tags=["News"])

@router.get("/", response_model=dict)
def get_news_list(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status: draft, published, archived"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    is_featured: Optional[bool] = Query(None, description="Filter featured news"),
    is_trending: Optional[bool] = Query(None, description="Filter trending news"),
    search: Optional[str] = Query(None, description="Search in title, content, tags"),
    db: Session = Depends(get_db)
):
    """Get all news with pagination and filter options"""
    return NewsController.get_news_list(
        db=db,
        page=page,
        limit=limit,
        status=status,
        category_id=category_id,
        is_featured=is_featured,
        is_trending=is_trending,
        search=search,
    )

@router.get("/featured", response_model=dict)
def get_featured_news(
    limit: int = Query(5, ge=1, le=20, description="Number of featured news"),
    db: Session = Depends(get_db)
):
    """Get featured news for homepage"""
    return NewsController.get_featured_news(db=db, limit=limit)

@router.get("/trending", response_model=dict)
def get_trending_news(
    limit: int = Query(5, ge=1, le=20, description="Number of trending news"),
    db: Session = Depends(get_db)
):
    """Get trending news"""
    return NewsController.get_trending_news(db=db, limit=limit)

@router.get("/latest", response_model=dict)
def get_latest_news(
    limit: int = Query(10, ge=1, le=20, description="Number of latest news"),
    db: Session = Depends(get_db)
):
    """Get latest news"""
    return NewsController.get_latest_news(db=db, limit=limit)

@router.get("/{news_id}", response_model=dict)
def get_news_detail(
    news: News = Depends(require_news_by_id),
    db: Session = Depends(get_db),
):
    """Get news detail by ID (auto-increment view count)"""
    return NewsController.get_news_detail(db=db, news=news)

@router.get("/slug/{slug}", response_model=dict)
def get_news_by_slug(
    news: News = Depends(require_news_by_slug),
    db: Session = Depends(get_db),
):
    """Get news detail by slug (auto-increment view count)"""
    return NewsController.get_news_by_slug(db=db, news=news)

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_news(
    news_data: NewsCreate = Depends(validate_create_news_payload),
    db: Session = Depends(get_db),
):
    """Create a new news article"""
    return NewsController.create_news(db=db, news_data=news_data)

@router.put("/{news_id}", response_model=dict)
def update_news(
    news_id: int,
    news_data: NewsUpdate = Depends(validate_update_news_payload),
    db: Session = Depends(get_db)
):
    """Update a news article"""
    return NewsController.update_news(db=db, news_id=news_id, news_data=news_data)

@router.delete("/{news_id}", response_model=dict)
def delete_news(
    news_id: int,
    _news: News = Depends(require_news_by_id),
    db: Session = Depends(get_db),
):
    """Delete a news article"""
    return NewsController.delete_news(db=db, news_id=news_id)

@router.post("/{news_id}/like", response_model=dict)
def toggle_like_news(
    news_id: int,
    like_data: LikeRequest,
    _news: News = Depends(require_news_by_id),
    db: Session = Depends(get_db)
):
    """Like or unlike a news article"""
    return NewsController.toggle_like_news(db=db, news_id=news_id, like_data=like_data)
