# Category Service - Business logic for categories
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..models.category import Category

class CategoryService:
    """Service class handling all category-related business logic"""
    
    @staticmethod
    def get_all(db: Session, is_active: Optional[bool] = None) -> List[Category]:
        """Get all categories, optionally filtered by active status"""
        query = db.query(Category)
        
        if is_active is not None:
            query = query.filter(Category.is_active == is_active)
        
        return query.order_by(Category.order, Category.name).all()
    
    @staticmethod
    def get_by_id(db: Session, category_id: int) -> Optional[Category]:
        """Get category by ID"""
        return db.query(Category).filter(Category.id == category_id).first()
    
    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Optional[Category]:
        """Get category by slug"""
        return db.query(Category).filter(Category.slug == slug).first()
    
    @staticmethod
    def create(db: Session, data: dict) -> Category:
        """Create new category"""
        category = Category(**data)
        db.add(category)
        db.commit()
        db.refresh(category)
        return category
    
    @staticmethod
    def update(db: Session, category_id: int, data: dict) -> Optional[Category]:
        """Update existing category"""
        category = CategoryService.get_by_id(db, category_id)
        if not category:
            return None
        
        # Update fields
        for key, value in data.items():
            if hasattr(category, key) and value is not None:
                setattr(category, key, value)
        
        category.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(category)
        return category
    
    @staticmethod
    def delete(db: Session, category_id: int, soft_delete: bool = True) -> bool:
        """Delete category (soft delete by default)"""
        category = CategoryService.get_by_id(db, category_id)
        if not category:
            return False
        
        if soft_delete:
            # Soft delete - set is_active to False
            category.is_active = False
            category.updated_at = datetime.utcnow()
            db.commit()
        else:
            # Hard delete - remove from database
            db.delete(category)
            db.commit()
        
        return True
    
    @staticmethod
    def exists_by_slug(db: Session, slug: str, exclude_id: Optional[int] = None) -> bool:
        """Check if category with slug already exists"""
        query = db.query(Category).filter(Category.slug == slug)
        
        if exclude_id:
            query = query.filter(Category.id != exclude_id)
        
        return query.first() is not None
