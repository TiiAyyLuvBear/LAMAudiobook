import math

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.category import Category
from ..schemas.category_schema import CategoryCreate, CategoryUpdate
from ..services.category_service import CategoryService
from ..services.news_service import NewsService


class CategoryController:
    """Controller layer for category endpoints."""

    @staticmethod
    def get_categories(db: Session, is_active: bool | None = None) -> dict:
        try:
            categories = CategoryService.get_all(db, is_active=is_active)
            return {
                "success": True,
                "data": [cat.to_dict() for cat in categories],
                "count": len(categories),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def get_category(category: Category) -> dict:
        return {
            "success": True,
            "data": category.to_dict(),
        }

    @staticmethod
    def get_category_by_slug(category: Category) -> dict:
        return {
            "success": True,
            "data": category.to_dict(),
        }

    @staticmethod
    def get_category_news(
        db: Session,
        category_id: int,
        page: int,
        limit: int,
        status: str,
    ) -> dict:
        try:
            news_list, total = NewsService.get_by_category(db, category_id, page, limit, status)
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
    def create_category(db: Session, category_data: CategoryCreate) -> dict:
        try:
            category = CategoryService.create(db, category_data.model_dump())
            return {
                "success": True,
                "message": "Category created successfully",
                "data": category.to_dict(),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def update_category(db: Session, category_id: int, category_data: CategoryUpdate) -> dict:
        try:
            update_data = {
                key: value
                for key, value in category_data.model_dump().items()
                if value is not None
            }

            category = CategoryService.update(db, category_id, update_data)
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")

            return {
                "success": True,
                "message": "Category updated successfully",
                "data": category.to_dict(),
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @staticmethod
    def delete_category(db: Session, category_id: int, hard_delete: bool) -> dict:
        try:
            success = CategoryService.delete(db, category_id, soft_delete=not hard_delete)
            if not success:
                raise HTTPException(status_code=404, detail="Category not found")

            return {
                "success": True,
                "message": "Category deleted successfully",
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
