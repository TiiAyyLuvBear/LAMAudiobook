# Category Routes/Controllers
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..services.category_service import CategoryService
from ..services.news_service import NewsService
from ..schemas.category_schema import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryListResponse
from ..schemas.news_schema import NewsListResponse
import math

router = APIRouter(prefix="/categories", tags=["Categories"])

@router.get("/", response_model=CategoryListResponse)
def get_categories(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db)
):
    """Get all categories"""
    try:
        categories = CategoryService.get_all(db, is_active=is_active)
        return {
            "success": True,
            "data": [cat.to_dict() for cat in categories],
            "count": len(categories)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{category_id}", response_model=dict)
def get_category(category_id: int, db: Session = Depends(get_db)):
    """Get category by ID"""
    category = CategoryService.get_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return {
        "success": True,
        "data": category.to_dict()
    }

@router.get("/slug/{slug}", response_model=dict)
def get_category_by_slug(slug: str, db: Session = Depends(get_db)):
    """Get category by slug"""
    category = CategoryService.get_by_slug(db, slug)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return {
        "success": True,
        "data": category.to_dict()
    }

@router.get("/{category_id}/news", response_model=dict)
def get_category_news(
    category_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    status: str = Query("published", description="Filter by status"),
    db: Session = Depends(get_db)
):
    """Get news articles in a category"""
    # Check if category exists
    category = CategoryService.get_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    try:
        news_list, total = NewsService.get_by_category(db, category_id, page, limit, status)
        
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

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_category(category_data: CategoryCreate, db: Session = Depends(get_db)):
    """Create a new category"""
    # Check if slug already exists
    if CategoryService.exists_by_slug(db, category_data.slug):
        raise HTTPException(status_code=400, detail="Category with this slug already exists")
    
    try:
        category = CategoryService.create(db, category_data.dict())
        return {
            "success": True,
            "message": "Category created successfully",
            "data": category.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{category_id}", response_model=dict)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db)
):
    """Update a category"""
    # Check if slug exists (excluding current category)
    if category_data.slug and CategoryService.exists_by_slug(db, category_data.slug, exclude_id=category_id):
        raise HTTPException(status_code=400, detail="Category with this slug already exists")
    
    try:
        # Filter out None values
        update_data = {k: v for k, v in category_data.dict().items() if v is not None}
        
        category = CategoryService.update(db, category_id, update_data)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        
        return {
            "success": True,
            "message": "Category updated successfully",
            "data": category.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{category_id}", response_model=dict)
def delete_category(
    category_id: int,
    hard_delete: bool = Query(False, description="Permanently delete (true) or soft delete (false)"),
    db: Session = Depends(get_db)
):
    """Delete a category"""
    try:
        success = CategoryService.delete(db, category_id, soft_delete=not hard_delete)
        if not success:
            raise HTTPException(status_code=404, detail="Category not found")
        
        return {
            "success": True,
            "message": "Category deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
