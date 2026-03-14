from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.news import News
from ..schemas.news_schema import NewsCreate, NewsUpdate
from ..services.category_service import CategoryService
from ..services.news_service import NewsService


def require_news_by_id(news_id: int, db: Session = Depends(get_db)) -> News:
    """Ensure news exists by id before controller is called."""
    news = NewsService.get_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    return news


def require_news_by_slug(slug: str, db: Session = Depends(get_db)) -> News:
    """Ensure news exists by slug before controller is called."""
    news = NewsService.get_by_slug(db, slug)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    return news


def _validate_category_id(category_id: int | None, db: Session) -> None:
    if category_id is None:
        return

    category = CategoryService.get_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=400, detail="Category does not exist")


def validate_create_news_payload(
    news_data: NewsCreate,
    db: Session = Depends(get_db),
) -> NewsCreate:
    """Validate create payload constraints before controller execution."""
    if NewsService.exists_by_slug(db, news_data.slug):
        raise HTTPException(status_code=400, detail="News with this slug already exists")

    _validate_category_id(news_data.category_id, db)
    return news_data


def validate_update_news_payload(
    news_id: int,
    news_data: NewsUpdate,
    db: Session = Depends(get_db),
) -> NewsUpdate:
    """Validate update payload constraints before controller execution."""
    if news_data.slug and NewsService.exists_by_slug(db, news_data.slug, exclude_id=news_id):
        raise HTTPException(status_code=400, detail="News with this slug already exists")

    _validate_category_id(news_data.category_id, db)
    return news_data
