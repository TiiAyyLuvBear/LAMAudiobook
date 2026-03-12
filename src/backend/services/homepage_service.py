# Homepage Service - Business logic for homepage data aggregation
from sqlalchemy.orm import Session
from typing import Dict, Any
from sqlalchemy import func

from .news_service import NewsService
from .category_service import CategoryService
from ..models.news import News
from ..models.category import Category

class HomepageService:
    """Service class for aggregating homepage data"""
    
    @staticmethod
    def get_homepage_data(db: Session) -> Dict[str, Any]:
        """
        Get all data needed for homepage
        This aggregates data from multiple sources
        """
        
        # Get featured news (top 5)
        featured_news = NewsService.get_featured(db, limit=5)
        
        # Get trending news (top 5)
        trending_news = NewsService.get_trending(db, limit=5)
        
        # Get latest news (top 10)
        latest_news = NewsService.get_latest(db, limit=10)
        
        # Get breaking news if any
        breaking_news = NewsService.get_breaking(db, limit=3)
        
        # Get all active categories
        categories = CategoryService.get_all(db, is_active=True)
        
        # Get news by category (top 3-5 from each major category)
        news_by_category = {}
        for category in categories[:5]:  # Limit to top 5 categories
            category_news, _ = NewsService.get_by_category(
                db=db,
                category_id=category.id,
                page=1,
                limit=5,
                status="published"
            )
            
            if category_news:
                news_by_category[category.slug] = {
                    "category": category.to_dict(include_news_count=False),
                    "news": [news.to_dict(include_content=False) for news in category_news]
                }
        
        # Get statistics
        stats = HomepageService.get_stats(db)
        
        return {
            "featured_news": [news.to_dict(include_content=False) for news in featured_news],
            "trending_news": [news.to_dict(include_content=False) for news in trending_news],
            "latest_news": [news.to_dict(include_content=False) for news in latest_news],
            "breaking_news": [news.to_dict(include_content=False) for news in breaking_news],
            "categories": [cat.to_dict(include_news_count=True) for cat in categories],
            "news_by_category": news_by_category,
            "stats": stats
        }
    
    @staticmethod
    def get_stats(db: Session) -> Dict[str, int]:
        """Get homepage statistics"""
        total_news = db.query(News).count()
        total_published = db.query(News).filter(News.status == "published").count()
        total_categories = db.query(Category).filter(Category.is_active == True).count()
        total_views = db.query(func.sum(News.view_count)).scalar() or 0
        
        return {
            "total_news": total_news,
            "total_published": total_published,
            "total_categories": total_categories,
            "total_views": int(total_views)
        }
