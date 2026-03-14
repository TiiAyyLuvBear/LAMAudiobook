from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.category import Category
from ..schemas.category_schema import CategoryCreate, CategoryUpdate
from ..services.category_service import CategoryService


def require_category_by_id(category_id: int, db: Session = Depends(get_db)) -> Category:
    """Ensure category exists by id before controller is called."""
    category = CategoryService.get_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def require_category_by_slug(slug: str, db: Session = Depends(get_db)) -> Category:
    """Ensure category exists by slug before controller is called."""
    category = CategoryService.get_by_slug(db, slug)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def validate_create_category_slug(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
) -> CategoryCreate:
    """Reject create payload when category slug already exists."""
    if CategoryService.exists_by_slug(db, category_data.slug):
        raise HTTPException(status_code=400, detail="Category with this slug already exists")
    return category_data


def validate_update_category_slug(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db),
) -> CategoryUpdate:
    """Reject update payload when category slug already exists on another category."""
    if category_data.slug and CategoryService.exists_by_slug(
        db,
        category_data.slug,
        exclude_id=category_id,
    ):
        raise HTTPException(status_code=400, detail="Category with this slug already exists")
    return category_data
