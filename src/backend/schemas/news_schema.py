# News Schemas - Request/Response models
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class NewsBase(BaseModel):
    """Base news schema"""
    title: str = Field(..., min_length=1, max_length=500, example="Tiêu đề tin tức")
    slug: str = Field(..., min_length=1, max_length=500, example="tieu-de-tin-tuc")
    summary: Optional[str] = Field(None, example="Tóm tắt ngắn về tin tức")
    content: str = Field(..., min_length=1, example="Nội dung đầy đủ của tin tức...")
    thumbnail: Optional[str] = Field(None, example="https://example.com/image.jpg")
    author: Optional[str] = Field(None, max_length=200, example="Nguyễn Văn A")
    source: Optional[str] = Field(None, max_length=200, example="VnExpress")
    source_url: Optional[str] = Field(None, example="https://vnexpress.net/...")
    tags: Optional[str] = Field(None, example="AI,Machine Learning,Technology")
    category_id: Optional[int] = Field(None, example=1)
    status: Optional[str] = Field("draft", example="published")
    is_featured: Optional[bool] = Field(False, example=True)
    is_trending: Optional[bool] = Field(False, example=False)
    is_breaking: Optional[bool] = Field(False, example=False)

class NewsCreate(NewsBase):
    """Schema for creating news"""
    pass

class NewsUpdate(BaseModel):
    """Schema for updating news (all fields optional)"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    slug: Optional[str] = Field(None, min_length=1, max_length=500)
    summary: Optional[str] = None
    content: Optional[str] = Field(None, min_length=1)
    thumbnail: Optional[str] = None
    author: Optional[str] = Field(None, max_length=200)
    source: Optional[str] = Field(None, max_length=200)
    source_url: Optional[str] = None
    tags: Optional[str] = None
    category_id: Optional[int] = None
    status: Optional[str] = None
    is_featured: Optional[bool] = None
    is_trending: Optional[bool] = None
    is_breaking: Optional[bool] = None

class NewsResponse(BaseModel):
    """Schema for news response (without full content)"""
    id: int
    title: str
    slug: str
    summary: Optional[str]
    thumbnail: Optional[str]
    author: Optional[str]
    source: Optional[str]
    tags: List[str]
    status: str
    is_featured: bool
    is_trending: bool
    is_breaking: bool
    view_count: int
    like_count: int
    category: Optional[dict]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class NewsDetailResponse(NewsResponse):
    """Schema for detailed news response (with full content)"""
    content: str
    images: Optional[str]
    source_url: Optional[str]
    share_count: int
    comment_count: int

class NewsListResponse(BaseModel):
    """Schema for list of news response with pagination"""
    success: bool = True
    data: List[NewsResponse]
    pagination: dict

class LikeRequest(BaseModel):
    """Schema for like/unlike request"""
    action: str = Field(..., pattern="^(like|unlike)$", example="like")
