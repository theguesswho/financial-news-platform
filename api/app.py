"""
FastAPI application for Financial News Platform backend.

Provides REST API endpoints for:
- User authentication (register, login)
- Watchlist management
- Portfolio tracking
- Stock data and V2 scores
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Import route handlers
from api.routes import auth, watchlist, portfolio, stocks


# ──────────────────────────────────────────────────────────────────────────
# Lifespan management
# ──────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("✓ Financial News Platform API starting...")
    yield
    # Shutdown
    print("✓ API shutdown complete")


# ──────────────────────────────────────────────────────────────────────────
# Create FastAPI application
# ──────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Financial News Platform API",
    description="REST API for stock screening, watchlists, and portfolio tracking",
    version="1.0.0",
    lifespan=lifespan,
)

# ──────────────────────────────────────────────────────────────────────────
# CORS Middleware
# ──────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",  # Next.js frontend
        "http://localhost:8000",
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:3001",  # Alternative localhost
        "*",  # Allow all origins in development; restrict in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────
# Include route modules
# ──────────────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["watchlist"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"])

# ──────────────────────────────────────────────────────────────────────────
# Health check endpoint
# ──────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "financial-news-platform-api",
        "version": "1.0.0"
    }


# ──────────────────────────────────────────────────────────────────────────
# Root endpoint
# ──────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """API root endpoint with documentation links."""
    return {
        "message": "Financial News Platform API",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
