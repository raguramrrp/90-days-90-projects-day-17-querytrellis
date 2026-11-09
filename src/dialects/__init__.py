"""Multi-dialect SQLGlot parsing, conversion, and feature-limitation inspection."""

from src.dialects.sqlglot_engine import (
    SUPPORTED_DIALECTS,
    ConversionResult,
    DialectParseResult,
    convert_sql_dialect,
    dialect_notes_for,
    format_sql_for_dialect,
    normalize_dialect,
    parse_sql_ast,
    transpile_for_duckdb,
)

__all__ = [
    "SUPPORTED_DIALECTS",
    "ConversionResult",
    "DialectParseResult",
    "convert_sql_dialect",
    "dialect_notes_for",
    "format_sql_for_dialect",
    "normalize_dialect",
    "parse_sql_ast",
    "transpile_for_duckdb",
]
