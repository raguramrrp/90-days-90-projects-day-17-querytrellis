"""PostgreSQL SQL formatting helpers built on SQLGlot."""
from __future__ import annotations

import sqlglot
from sqlglot.errors import SqlglotError


def format_sql(sql: str) -> tuple[str, str | None]:
    """Format PostgreSQL SQL cleanly using SQLGlot.

    Returns ``(formatted_sql, warning_or_error)``. If parsing fails, returns the
    original SQL along with a descriptive error message instead of crashing.
    """
    stripped = (sql or "").strip()
    if not stripped:
        return "", "SQL input is empty."

    try:
        expressions = [e for e in sqlglot.parse(stripped, read="postgres") if e is not None]
        if not expressions:
            return stripped, "No executable SQL statement found to format."
        formatted_parts = [
            expr.sql(dialect="postgres", pretty=True) for expr in expressions
        ]
        return ";\n\n".join(formatted_parts) + (";" if stripped.endswith(";") else ""), None
    except SqlglotError as exc:
        return stripped, f"Unable to format SQL due to syntax error: {exc}"
    except Exception as exc:
        return stripped, f"Formatting failed: {exc}"
