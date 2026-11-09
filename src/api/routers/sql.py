"""SQL Editor execution, AST formatting, dialect conversion, and explanation FastAPI router."""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import (
    SqlConvertRequest,
    SqlExecuteRequest,
    SqlExplainTextRequest,
    SqlFormatRequest,
)
from src.api.state import get_container
from src.dialects.sqlglot_engine import (
    convert_sql_dialect,
    dialect_notes_for,
    format_sql_for_dialect,
    parse_sql_ast,
)
from src.nl2sql.explainer import explain_sql_query

router = APIRouter(prefix="/api/sql", tags=["SQL Editor & Dialects"])


@router.post("/execute")
def execute_query(payload: SqlExecuteRequest):
    c = get_container()
    res = c.context_manager.connector.execute_sql(
        payload.sql,
        dialect=payload.dialect,
        max_rows=payload.max_rows,
        timeout_ms=payload.timeout_ms,
        allow_write_opt_in=payload.allow_write_opt_in,
        confirmed_write=payload.confirmed_write,
        confirmation_token=payload.confirmation_token,
    )
    return res.to_dict()


@router.post("/format")
def format_query(payload: SqlFormatRequest):
    formatted, warn = format_sql_for_dialect(payload.sql, payload.dialect)
    return {"formatted_sql": formatted, "warning": warn}


@router.post("/convert")
def convert_dialect(payload: SqlConvertRequest):
    return convert_sql_dialect(
        payload.sql,
        payload.source_dialect,
        payload.target_dialect,
        pretty=payload.pretty,
    ).to_dict()


@router.post("/explain-text")
def explain_query(payload: SqlExplainTextRequest):
    c = get_container()
    ctx = c.context_manager.get_snapshot()
    return explain_sql_query(payload.sql, context=ctx, dialect=payload.dialect or ctx.dialect)


@router.post("/validate")
def validate_syntax(payload: SqlFormatRequest):
    res = parse_sql_ast(payload.sql, payload.dialect)
    return {
        "dialect": res.dialect,
        "is_valid": res.is_valid,
        "statement_types": res.statement_types,
        "error_message": res.error_message,
        "error_line": res.error_line,
        "error_column": res.error_column,
    }


@router.get("/dialect-notes/{dialect}")
def get_dialect_notes(dialect: str):
    return dialect_notes_for(dialect)
