"""Frontend v2 read layer — thin FastAPI over the platform's Postgres.

SQL in, JSON out. Reuses pipeline/db modules; no logic duplicated here.
Endpoints land per FRONTEND_SPEC.md Phase 1+ (board, stocks, narratives,
reports, then the rest). Run locally: uvicorn api.main:app --reload
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=True)

app = FastAPI(title="Financial News Platform API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("API_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "api", "version": "2.0.0"}


from api.routers import board, narratives, reports, stocks  # noqa: E402

app.include_router(board.router)
app.include_router(stocks.router)
app.include_router(narratives.router)
app.include_router(reports.router)
