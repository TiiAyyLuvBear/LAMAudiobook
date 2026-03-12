# News Routes/Controllers
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
import math

from ..database import get_db
from ..services.news_service import NewsService
from ..schemas.news_schema import NewsCreate, NewsUpdate, NewsListResponse, LikeRequest

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
    try:
        news_list, total = NewsService.get_all(
            db=db,
            page=page,
            limit=limit,
            status=status,
            category_id=category_id,
            is_featured=is_featured,
            is_trending=is_trending,
            search=search
        )
        
        total_pages = math.ceil(total / limit)
        
        return {
            "success": True,
            "data": [news.to_dict(include_content=False) for news in news_list],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/featured", response_model=dict)
def get_featured_news(
    limit: int = Query(5, ge=1, le=20, description="Number of featured news"),
    db: Session = Depends(get_db)
):
    """Get featured news for homepage"""
    try:
        news_list = NewsService.get_featured(db, limit=limit)
        return {
            "success": True,
            "data": [news.to_dict(include_content=False) for news in news_list],
            "count": len(news_list)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trending", response_model=dict)
def get_trending_news(
    limit: int = Query(5, ge=1, le=20, description="Number of trending news"),
    db: Session = Depends(get_db)
):
    """Get trending news"""
    try:
        news_list = NewsService.get_trending(db, limit=limit)
        return {
            "success": True,
            "data": [news.to_dict(include_content=False) for news in news_list],
            "count": len(news_list)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/latest", response_model=dict)
def get_latest_news(
    limit: int = Query(10, ge=1, le=20, description="Number of latest news"),
    db: Session = Depends(get_db)
):
    """Get latest news"""
    try:
        news_list = NewsService.get_latest(db, limit=limit)
        return {
            "success": True,
            "data": [news.to_dict(include_content=False) for news in news_list],
            "count": len(news_list)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{news_id}", response_model=dict)
def get_news_detail(news_id: int, db: Session = Depends(get_db)):
    """Get news detail by ID (auto-increment view count)"""
    news = NewsService.get_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    
    # Increment view count
    NewsService.increment_view(db, news_id)
    
    return {
        "success": True,
        "data": news.to_dict(include_content=True)
    }

@router.get("/slug/{slug}", response_model=dict)
def get_news_by_slug(slug: str, db: Session = Depends(get_db)):
    """Get news detail by slug (auto-increment view count)"""
    news = NewsService.get_by_slug(db, slug)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    
    # Increment view count
    NewsService.increment_view(db, news.id)
    
    return {
        "success": True,
        "data": news.to_dict(include_content=True)
    }

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_news(news_data: NewsCreate, db: Session = Depends(get_db)):
    """Create a new news article"""
    # Check if slug already exists
    if NewsService.exists_by_slug(db, news_data.slug):
        raise HTTPException(status_code=400, detail="News with this slug already exists")
    
    try:
        news = NewsService.create(db, news_data.dict())
        return {
            "success": True,
            "message": "News created successfully",
            "data": news.to_dict(include_content=True)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{news_id}", response_model=dict)
def update_news(
    news_id: int,
    news_data: NewsUpdate,
    db: Session = Depends(get_db)
):
    """Update a news article"""
    # Check if slug exists (excluding current news)
    if news_data.slug and NewsService.exists_by_slug(db, news_data.slug, exclude_id=news_id):
        raise HTTPException(status_code=400, detail="News with this slug already exists")
    
    try:
        # Filter out None values
        update_data = {k: v for k, v in news_data.dict().items() if v is not None}
        
        news = NewsService.update(db, news_id, update_data)
        if not news:
            raise HTTPException(status_code=404, detail="News not found")
        
        return {
            "success": True,
            "message": "News updated successfully",
            "data": news.to_dict(include_content=True)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{news_id}", response_model=dict)
def delete_news(news_id: int, db: Session = Depends(get_db)):
    """Delete a news article"""
    try:
        success = NewsService.delete(db, news_id)
        if not success:
            raise HTTPException(status_code=404, detail="News not found")
        
        return {
            "success": True,
            "message": "News deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{news_id}/like", response_model=dict)
def toggle_like_news(
    news_id: int,
    like_data: LikeRequest,
    db: Session = Depends(get_db)
):
    """Like or unlike a news article"""
    try:
        success = NewsService.toggle_like(db, news_id, like_data.action)
        if not success:
            raise HTTPException(status_code=404, detail="News not found")
        
        return {
            "success": True,
            "message": f"{like_data.action.capitalize()} successful"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
