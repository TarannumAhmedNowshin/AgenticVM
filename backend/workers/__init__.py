"""Async job runner powered by Procrastinate (Postgres-backed queue)."""

from backend.workers.app import app

__all__ = ["app"]
