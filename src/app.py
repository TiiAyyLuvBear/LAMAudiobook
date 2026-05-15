"""Compatibility wrapper for the FastAPI audiobook app.

Prefer running `uvicorn src.backend.app:app`.
"""

from src.backend.app import app

__all__ = ["app"]
