# News Service - Business logic for news articles
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc, func
from typing import List, Optional, Tuple
from datetime import datetime

from ..models.news import News

class NewsService:
    """Service class handling all news-related business logic"""
    
    @staticmethod
    def get_all(
        db: Session,
        page: int = 1,
        limit: int = 10,
        status: Optional[str] = None,
        category_id: Optional[int] = None,
        is_featured: Optional[bool] = None,
        is_trending: Optional[bool] = None,
        search: Optional[str] = None
    ) -> Tuple[List[News], int]:
        """
        Get all news with pagination and filters
        Returns: (news_list, total_count)
        """
        query = db.query(News)
        
        # Apply filters
        if status:
            query = query.filter(News.status == status)
        
        if category_id:
            query = query.filter(News.category_id == category_id)
        
        if is_featured is not None:
            query = query.filter(News.is_featured ==is_featured)
        
        if is_trending is not None:
            query = query.filter(News.is_trending == is_trending)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    News.title.ilike(search_term),
                    News.summary.ilike(search_term),
                    News.content.ilike(search_term),
                    News.tags.ilike(search_term)
                )
            )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination and ordering
        offset = (page - 1) * limit
        news_list = query.order_by(desc(News.published_at), desc(News.created_at)).offset(offset).limit(limit).all()
        
        return news_list, total
    
    @staticmethod
    def get_by_id(db: Session, news_id: int) -> Optional[News]:
        """Get news by ID"""
        return db.query(News).filter(News.id == news_id).first()
    
    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Optional[News]:
        """Get news by slug"""
        return db.query(News).filter(News.slug == slug).first()
    
    @staticmethod
    def get_featured(db: Session, limit: int = 5) -> List[News]:
        """Get featured news for homepage"""
        return db.query(News).filter(
            News.is_featured == True,
            News.status == "published"
        ).order_by(desc(News.published_at)).limit(limit).all()
    
    @staticmethod
    def get_trending(db: Session, limit: int = 5) -> List[News]:
        """Get trending news ordered by view count"""
        return db.query(News).filter(
            News.is_trending == True,
            News.status == "published"
        ).order_by(desc(News.view_count), desc(News.published_at)).limit(limit).all()
    
    @staticmethod
    def get_latest(db: Session, limit: int = 10) -> List[News]:
        """Get latest published news"""
        return db.query(News).filter(
            News.status == "published"
        ).order_by(desc(News.published_at)).limit(limit).all()
    
    @staticmethod
    def get_breaking(db: Session, limit: int = 3) -> List[News]:
        """Get breaking news"""
        return db.query(News).filter(
            News.is_breaking == True,
            News.status == "published"
        ).order_by(desc(News.published_at)).limit(limit).all()
    
    @staticmethod
    def get_by_category(
        db: Session,
        category_id: int,
        page: int = 1,
        limit: int = 10,
        status: str = "published"
    ) -> Tuple[List[News], int]:
        """Get news by category with pagination"""
        return NewsService.get_all(
            db=db,
            page=page,
            limit=limit,
            status=status,
            category_id=category_id
        )
    
    @staticmethod
    def create(db: Session, data: dict) -> News:
        """Create new news article"""
        # Auto-set published_at if status is published and not set
        if data.get('status') == 'published' and not data.get('published_at'):
            data['published_at'] = datetime.utcnow()
        
        news = News(**data)
        db.add(news)
        db.commit()
        db.refresh(news)
        return news
    
    @staticmethod
    def update(db: Session, news_id: int, data: dict) -> Optional[News]:
        """Update existing news article"""
        news = NewsService.get_by_id(db, news_id)
        if not news:
            return None
        
        # Update fields
        for key, value in data.items():
            if hasattr(news, key) and value is not None:
                setattr(news, key, value)
        
        # Auto-set published_at if status changes to published
        if data.get('status') == 'published' and not news.published_at:
            news.published_at = datetime.utcnow()
        
        news.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(news)
        return news
    
    @staticmethod
    def delete(db: Session, news_id: int) -> bool:
        """Delete news article"""
        news = NewsService.get_by_id(db, news_id)
        if not news:
            return False
        
        db.delete(news)
        db.commit()
        return True
    
    @staticmethod
    def increment_view(db: Session, news_id: int) -> bool:
        """Increment view count"""
        news = NewsService.get_by_id(db, news_id)
        if not news:
            return False
        
        news.view_count += 1
        db.commit()
        return True
    
    @staticmethod
    def toggle_like(db: Session, news_id: int, action: str = "like") -> bool:
        """Toggle like (like/unlike)"""
        news = NewsService.get_by_id(db, news_id)
        if not news:
            return False
        
        if action == "like":
            news.like_count += 1
        elif action == "unlike" and news.like_count > 0:
            news.like_count -= 1
        
        db.commit()
        return True
    
    @staticmethod
    def exists_by_slug(db: Session, slug: str, exclude_id: Optional[int] = None) -> bool:
        """Check if news with slug already exists"""
        query = db.query(News).filter(News.slug == slug)
        
        if exclude_id:
            query = query.filter(News.id != exclude_id)
        
        return query.first() is not None
    
    @staticmethod
    def get_stats(db: Session) -> dict:
        """Get news statistics"""
        total_news = db.query(News).count()
        total_published = db.query(News).filter(News.status == "published").count()
        total_views = db.query(func.sum(News.view_count)).scalar() or 0
        total_likes = db.query(func.sum(News.like_count)).scalar() or 0
        
        return {
            "total_news": total_news,
            "total_published": total_published,
            "total_views": total_views,
            "total_likes": total_likes
        }
