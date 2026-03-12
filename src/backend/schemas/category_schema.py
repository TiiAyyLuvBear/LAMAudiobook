# Category Schemas - Request/Response models
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CategoryBase(BaseModel):
    """Base category schema"""
    name: str = Field(..., min_length=1, max_length=100, example="Công nghệ")
    slug: str = Field(..., min_length=1, max_length=100, example="cong-nghe")
    description: Optional[str] = Field(None, example="Tin tức công nghệ, AI, khoa học")
    icon: Optional[str] = Field(None, example="💻")
    color: Optional[str] = Field(None, example="#3B82F6")
    order: Optional[int] = Field(0, ge=0, example=1)
    is_active: Optional[bool] = Field(True, example=True)

class CategoryCreate(CategoryBase):
    """Schema for creating a category"""
    pass

class CategoryUpdate(BaseModel):
    """Schema for updating a category (all fields optional)"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

class CategoryResponse(CategoryBase):
    """Schema for category response"""
    id: int
    news_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class CategoryListResponse(BaseModel):
    """Schema for list of categories response"""
    success: bool = True
    data: list[CategoryResponse]
    count: int
