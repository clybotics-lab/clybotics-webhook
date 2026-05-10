"""Vercel serverless entry: exposes the Flask WSGI app for all routes."""

from __future__ import annotations

from app import app

__all__ = ["app"]
