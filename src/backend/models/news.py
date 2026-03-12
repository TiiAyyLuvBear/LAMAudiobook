# News Model - Tin tức
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base

class News(Base):
    """News article model"""
    __tablename__ = "news"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Basic Information
    title = Column(String(500), nullable=False, index=True)
    slug = Column(String(500), unique=True, nullable=False, index=True)
    summary = Column(Text, nullable=True)  # Short summary/excerpt
    content = Column(Text, nullable=False)  # Full content
    
    # Media
    thumbnail = Column(String(500), nullable=True)  # Main image URL
    images = Column(Text, nullable=True)  # JSON array of additional images
    
    # Metadata
    author = Column(String(200), nullable=True)
    source = Column(String(200), nullable=True)  # News source
    source_url = Column(String(500), nullable=True)  # Original news URL
    tags = Column(String(500), nullable=True)  # Comma-separated tags
    
    # Status & Publishing
    status = Column(String(20), default="draft", index=True)  # draft, published, archived
    published_at = Column(DateTime, nullable=True, index=True)
    
    # Features
    is_featured = Column(Boolean, default=False)  # Show on homepage slider
    is_trending = Column(Boolean, default=False)  # Trending/hot news
    is_breaking = Column(Boolean, default=False)  # Breaking news
    
    # Statistics
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    # Category Relationship
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    category = relationship("Category", back_populates="news")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<News(id={self.id}, title='{self.title[:50]}...')>"
    
    def to_dict(self, include_content=False):
        """Convert model to dictionary for API response"""
        data = {
            "id": self.id,
            "title": self.title,
            "slug": self.slug,
            "summary": self.summary,
            "thumbnail": self.thumbnail,
            "author": self.author,
            "source": self.source,
            "source_url": self.source_url,
            "tags": self.tags.split(',') if self.tags else [],
            "status": self.status,
            "is_featured": self.is_featured,
            "is_trending": self.is_trending,
            "is_breaking": self.is_breaking,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "share_count": self.share_count,
            "comment_count": self.comment_count,
            "category": self.category.to_dict(include_news_count=False) if self.category else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        # Include full content only when requested (detail view)
        if include_content:
            data["content"] = self.content
            data["images"] = self.images
        
        return data
