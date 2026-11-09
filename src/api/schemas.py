"""Pydantic v2 request and response schemas for QueryTrellis Studio FastAPI backend."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DialectUpdateRequest(BaseModel):
    dialect: str = Field(..., pattern="^(postgresql|mysql|sqlite|sqlserver|mssql|tsql)$")


class WriteModeRequest(BaseModel):
    allow_write_opt_in: bool


class LiveConnectRequest(BaseModel):
    engine: str = Field(..., pattern="^(postgresql|mysql|sqlite|sqlserver)$")
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    username: str = ""
    password: str = ""
    sqlite_path: str = ""
    ssl_mode: str = "prefer"
    connect_timeout: int = 5
    allow_write_opt_in: bool = False


class AcceptImportRequest(BaseModel):
    preview_id: str


class NLGenerateRequest(BaseModel):
    request: str = Field(..., min_length=1, max_length=4000)
    dialect: str | None = None
    clarification_answer: str | None = None
    force_provider: str | None = None


class SqlExecuteRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    dialect: str | None = None
    max_rows: int = Field(default=500, ge=1, le=5000)
    timeout_ms: int = Field(default=5000, ge=200, le=60000)
    allow_write_opt_in: bool | None = None
    confirmed_write: bool = False
    confirmation_token: str | None = None


class SqlFormatRequest(BaseModel):
    sql: str
    dialect: str = "postgresql"


class SqlConvertRequest(BaseModel):
    sql: str
    source_dialect: str
    target_dialect: str
    pretty: bool = True


class SqlExplainTextRequest(BaseModel):
    sql: str
    dialect: str | None = None


class DebugAnalyzeRequest(BaseModel):
    sql: str
    dialect: str | None = None
    captured_error: str | None = None
    test_fixes: bool = True


class OptimizeAnalyzeRequest(BaseModel):
    sql: str
    dialect: str | None = None
    include_estimated_plan: bool = True
    allow_explain_analyze: bool = False
    benchmark_candidate_sql: str | None = None


class CustomVisualizeRequest(BaseModel):
    sql: str


class ExerciseCheckRequest(BaseModel):
    lesson_id: str
    user_sql: str


class AISettingsUpdateRequest(BaseModel):
    active_provider: str | None = None
    external_provider: str | None = None
    external_base_url: str | None = None
    external_model: str | None = None
    external_api_key: str | None = None
    clear_external_api_key: bool = False
    external_data_consent: bool | None = None
    include_sample_rows_in_external: bool | None = None
    deterministic_fallback_enabled: bool | None = None
    cpu_fallback_enabled: bool | None = None
