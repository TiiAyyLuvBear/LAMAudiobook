# Category Routes/Controllers
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from ..controllers.category_controller import CategoryController
from ..database import get_db
from ..middleware.category_middleware import (
    require_category_by_id,
    require_category_by_slug,
    validate_create_category_slug,
    validate_update_category_slug,
)
from ..models.category import Category
from ..schemas.category_schema import CategoryCreate, CategoryUpdate, CategoryListResponse

router = APIRouter(prefix="/categories", tags=["Categories"])

@router.get("/", response_model=CategoryListResponse)
def get_categories(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db)
):
    """Get all categories"""
    return CategoryController.get_categories(db=db, is_active=is_active)

@router.get("/{category_id}", response_model=dict)
def get_category(category: Category = Depends(require_category_by_id)):
    """Get category by ID"""
    return CategoryController.get_category(category)

@router.get("/slug/{slug}", response_model=dict)
def get_category_by_slug(category: Category = Depends(require_category_by_slug)):
    """Get category by slug"""
    return CategoryController.get_category_by_slug(category)

@router.get("/{category_id}/news", response_model=dict)
def get_category_news(
    category_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    status: str = Query("published", description="Filter by status"),
    _category: Category = Depends(require_category_by_id),
    db: Session = Depends(get_db)
):
    """Get news articles in a category"""
    return CategoryController.get_category_news(
        db=db,
        category_id=category_id,
        page=page,
        limit=limit,
        status=status,
    )

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_category(
    category_data: CategoryCreate = Depends(validate_create_category_slug),
    db: Session = Depends(get_db),
):
    """Create a new category"""
    return CategoryController.create_category(db=db, category_data=category_data)

@router.put("/{category_id}", response_model=dict)
def update_category(
    category_id: int,
    category_data: CategoryUpdate = Depends(validate_update_category_slug),
    db: Session = Depends(get_db)
):
    """Update a category"""
    return CategoryController.update_category(
        db=db,
        category_id=category_id,
        category_data=category_data,
    )

@router.delete("/{category_id}", response_model=dict)
def delete_category(
    category_id: int,
    hard_delete: bool = Query(False, description="Permanently delete (true) or soft delete (false)"),
    _category: Category = Depends(require_category_by_id),
    db: Session = Depends(get_db)
):
    """Delete a category"""
    return CategoryController.delete_category(
        db=db,
        category_id=category_id,
        hard_delete=hard_delete,
    )
