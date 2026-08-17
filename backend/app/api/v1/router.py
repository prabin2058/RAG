"""Aggregate v1 router — all API endpoints under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import auth, documents, query

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(query.router)
