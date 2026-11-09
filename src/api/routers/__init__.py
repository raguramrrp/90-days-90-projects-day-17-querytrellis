"""Modular FastAPI routers per workbench workspace."""

from src.api.routers import academy, ai, context, debug, nl2sql, optimize, sql

__all__ = ["academy", "ai", "context", "debug", "nl2sql", "optimize", "sql"]
