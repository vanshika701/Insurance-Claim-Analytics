"""MySQL connection helper. Reads credentials from .env (never hardcoded)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")


def _cfg(key: str, default: str | None = None) -> str:
    val = os.getenv(key, default)
    if val is None:
        raise RuntimeError(f"Missing required env var {key!r} (see .env.example)")
    return val


def get_engine() -> Engine:
    """Return a SQLAlchemy engine for the insurance_claims database."""
    url = (
        f"mysql+mysqlconnector://{_cfg('DB_USER')}:{_cfg('DB_PASSWORD')}"
        f"@{_cfg('DB_HOST', 'localhost')}:{_cfg('DB_PORT', '3306')}/{_cfg('DB_NAME')}"
    )
    return create_engine(url, pool_pre_ping=True)


if __name__ == "__main__":
    from sqlalchemy import text

    with get_engine().connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar()
        print(f"Connected to MySQL {version}")
