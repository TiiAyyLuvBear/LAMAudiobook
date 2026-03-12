# Main FastAPI Application
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.config import get_config
from backend.database import init_db
from backend.routes import category_routes, news_routes, homepage_routes

# Get configuration
config = get_config()

# Lifespan event handler for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting News Portal API...")
    init_db()
    print("✅ Database initialized successfully")
    yield
    # Shutdown
    print("👋 Shutting down News Portal API...")

# Create FastAPI application
app = FastAPI(
    title=config.APP_NAME,
    description="Backend API for News Portal - Homepage, News, Categories",
    version=config.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(homepage_routes.router, prefix=config.API_V1_PREFIX)
app.include_router(news_routes.router, prefix=config.API_V1_PREFIX)
app.include_router(category_routes.router, prefix=config.API_V1_PREFIX)

# Root endpoint
@app.get("/")
def root():
    """Root endpoint - API information"""
    return {
        "app": config.APP_NAME,
        "version": config.VERSION,
        "status": "running",
        "docs": "/api/docs",
        "endpoints": {
            "homepage": f"{config.API_V1_PREFIX}/homepage",
            "news": f"{config.API_V1_PREFIX}/news",
            "categories": f"{config.API_V1_PREFIX}/categories"
        }
    }

# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "API is running smoothly"
    }

# Run the application
if __name__ == "__main__":
    import uvicorn
    
    print(f"""
    ╔══════════════════════════════════════════╗
    ║       News Portal API - Backend          ║
    ╠══════════════════════════════════════════╣
    ║  📰 Homepage API: ✅                     ║
    ║  📝 News API: ✅                         ║
    ║  📑 Categories API: ✅                   ║
    ║  🤖 Chatbot API: ❌ (Excluded)          ║
    ╠══════════════════════════════════════════╣
    ║  Server: http://localhost:8000           ║
    ║  Docs: http://localhost:8000/api/docs    ║
    ╚══════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
