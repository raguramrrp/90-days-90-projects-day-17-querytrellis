"""Environment and application configuration for QueryTrellis.

Reads PostgreSQL connection defaults and safety limits from `.env` or environment
variables. Never exposes secrets in serialized dictionaries or logs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _parse_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    """Safely parse and clamp an integer configuration value."""
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


@dataclass(slots=True)
class ConnectionConfig:
    """PostgreSQL connection parameters without leaking credentials."""

    host: str = "localhost"
    port: int = 5432
    database: str = "querytrellis_sample"
    username: str = "postgres"
    password: str = field(default="", repr=False)
    sslmode: str = "prefer"
    connect_timeout: int = 5

    def to_safe_dict(self) -> dict[str, str | int | bool]:
        """Return sanitized connection parameters suitable for logs, UI, and reports."""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout,
            "password_configured": bool(self.password),
        }

    def display_label(self) -> str:
        """Return a safe display label without credentials."""
        return f"{self.database} @ {self.host}:{self.port} ({self.username})"


@dataclass(slots=True)
class AppSettings:
    """Application-wide runtime settings and safety guardrails."""

    connection: ConnectionConfig
    default_statement_timeout_ms: int = 5000
    default_max_rows: int = 500
    benchmark_max_repeats: int = 20
    metadata_db_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "querytrellis_meta.db"
    )
    large_table_row_threshold: int = 5000


def load_settings(env_path: Path | None = None) -> AppSettings:
    """Load settings from `.env` (if present) and process environment variables."""
    target_env = env_path or (PROJECT_ROOT / ".env")
    if target_env.exists():
        load_dotenv(dotenv_path=target_env, override=False)

    raw_password = (
        os.getenv("PGPASSWORD")
        or os.getenv("POSTGRES_PASSWORD")
        or os.getenv("QUERYTRELLIS_PG_PASSWORD")
        or ""
    )

    conn = ConnectionConfig(
        host=os.getenv("PGHOST", "localhost").strip() or "localhost",
        port=_parse_int(os.getenv("PGPORT"), default=5432, minimum=1, maximum=65535),
        database=os.getenv("PGDATABASE", "querytrellis_sample").strip() or "querytrellis_sample",
        username=os.getenv("PGUSER", "postgres").strip() or "postgres",
        password=raw_password,
        sslmode=os.getenv("PGSSLMODE", "prefer").strip() or "prefer",
        connect_timeout=_parse_int(os.getenv("PGCONNECT_TIMEOUT"), default=5, minimum=1, maximum=60),
    )

    meta_raw = os.getenv("QT_METADATA_DB_PATH", "data/querytrellis_meta.db").strip()
    meta_path = Path(meta_raw)
    if not meta_path.is_absolute():
        meta_path = PROJECT_ROOT / meta_path

    return AppSettings(
        connection=conn,
        default_statement_timeout_ms=_parse_int(
            os.getenv("QT_DEFAULT_STATEMENT_TIMEOUT_MS"), default=5000, minimum=100, maximum=120000
        ),
        default_max_rows=_parse_int(
            os.getenv("QT_DEFAULT_MAX_ROWS"), default=500, minimum=10, maximum=10000
        ),
        benchmark_max_repeats=_parse_int(
            os.getenv("QT_BENCHMARK_MAX_REPEATS"), default=20, minimum=2, maximum=50
        ),
        metadata_db_path=meta_path,
    )
