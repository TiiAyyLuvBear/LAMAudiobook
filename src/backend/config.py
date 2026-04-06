# Configuration settings for backend
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Config:
    """Base configuration"""
    # Application
    APP_NAME = "News Portal API"
    VERSION = "1.0.0"
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # Database
    _raw_database_url = os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR}/news_portal.db')
    if _raw_database_url.startswith('sqlite:///') and not _raw_database_url.startswith('sqlite:////'):
        # Resolve relative sqlite path from project root so behavior is stable across cwd.
        sqlite_path = Path(_raw_database_url.replace('sqlite:///', '', 1))
        if not sqlite_path.is_absolute():
            sqlite_path = BASE_DIR / sqlite_path
        DATABASE_URL = f"sqlite:///{sqlite_path.as_posix()}"
    else:
        DATABASE_URL = _raw_database_url
    
    # API
    API_V1_PREFIX = "/api/v1"
    
    # CORS
    CORS_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080"
    ]
    
    # Pagination
    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 100
    
    # News Settings
    FEATURED_NEWS_LIMIT = 5
    TRENDING_NEWS_LIMIT = 5
    
    # Upload
    UPLOAD_FOLDER = BASE_DIR / "uploads"
    MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    DATABASE_URL = f'sqlite:///{BASE_DIR}/test.db'

# Config mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config(env=None):
    """Get configuration based on environment"""
    if env is None:
        env = os.getenv('ENVIRONMENT', 'development')
    return config.get(env, config['default'])
