"""Vercel serverless entry: exposes the Flask WSGI app for all routes."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app import app

__all__ = ["app"]
