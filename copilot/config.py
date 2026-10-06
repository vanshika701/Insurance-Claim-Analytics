"""Shared configuration for the Copilot extension.

Backend selection: set DB_BACKEND=sqlite in the environment (or .env) to run everything
against the local SQLite fallback instead of MySQL. Default is "mysql" since that's what
the original project uses and it's already populated.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DB_BACKEND: str = os.getenv("DB_BACKEND", "mysql").strip().lower()
if DB_BACKEND not in {"mysql", "sqlite"}:
    raise ValueError(f"DB_BACKEND must be 'mysql' or 'sqlite', got {DB_BACKEND!r}")

SQLITE_PATH: Path = PROJECT_ROOT / "data" / "claims.db"
CHROMA_DIR: Path = PROJECT_ROOT / "docs" / "guidelines" / "chroma"
MODELS_DIR: Path = PROJECT_ROOT / "models"
RESULTS_DIR: Path = PROJECT_ROOT / "results"
GUIDELINES_DIR: Path = PROJECT_ROOT / "docs" / "guidelines"

for _d in (MODELS_DIR, RESULTS_DIR, GUIDELINES_DIR):
    _d.mkdir(parents=True, exist_ok=True)
