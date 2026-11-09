"""AST-based SQL parsing and dialect conversion using SQLGlot.

Supports PostgreSQL, MySQL, SQLite, and Microsoft SQL Server (T-SQL), plus
DuckDB local sandbox transpilation. Never uses naive keyword string-replacement
to convert between dialects and explicitly highlights unsupported syntax and
behavioral differences.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

logging.getLogger("sqlglot").setLevel(logging.ERROR)

SUPPORTED_DIALECTS: tuple[str, ...] = ("postgresql", "mysql", "sqlite", "sqlserver")

_DIALECT_TO_SQLGLOT: dict[str, str] = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "pg": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "sqlite3": "sqlite",
    "sqlserver": "tsql",
    "mssql": "tsql",
    "tsql": "tsql",
    "t-sql": "tsql",
    "microsoft sql server": "tsql",
    "duckdb": "duckdb",
}

_CANONICAL_DIALECT: dict[str, str] = {
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "pg": "postgresql",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "sqlite3": "sqlite",
    "sqlserver": "sqlserver",
    "mssql": "sqlserver",
    "tsql": "sqlserver",
    "t-sql": "sqlserver",
    "microsoft sql server": "sqlserver",
    "duckdb": "duckdb",
}


def normalize_dialect(dialect: str | None) -> str:
    """Normalize user dialect input into a canonical dialect name."""
    raw = (dialect or "postgresql").strip().lower()
    if raw not in _CANONICAL_DIALECT:
        raise ValueError(
            f"Unsupported SQL dialect '{dialect}'. Choose from: postgresql, mysql, sqlite, sqlserver."
        )
    return _CANONICAL_DIALECT[raw]


def to_sqlglot_read_write(dialect: str | None) -> str:
    """Map canonical dialect name to SQLGlot's dialect identifier."""
    norm = normalize_dialect(dialect)
    return _DIALECT_TO_SQLGLOT[norm]


@dataclass(slots=True)
class DialectParseResult:
    """Outcome of parsing one or more SQL statements in a dialect."""

    dialect: str
    is_valid: bool
    statements: list[exp.Expression] = field(default_factory=list)
    statement_types: list[str] = field(default_factory=list)
    error_message: str = ""
    error_line: int | None = None
    error_column: int | None = None

    @property
    def root(self) -> exp.Expression | None:
        return self.statements[0] if self.statements else None


@dataclass(slots=True)
class ConversionResult:
    """Result of AST-based SQL dialect transpilation with limitations."""

    source_dialect: str
    target_dialect: str
    source_sql: str
    converted_sql: str
    success: bool
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_dialect": self.source_dialect,
            "target_dialect": self.target_dialect,
            "source_sql": self.source_sql,
            "converted_sql": self.converted_sql,
            "success": self.success,
            "warnings": self.warnings,
            "limitations": self.limitations,
            "error_message": self.error_message,
        }


def _extract_error_coords(exc: Exception) -> tuple[int | None, int | None]:
    if isinstance(exc, ParseError) and getattr(exc, "errors", None):
        first = exc.errors[0]
        return first.get("line"), first.get("col")
    text = str(exc)
    line_m = re.search(r"Line\s+(\d+)", text, re.IGNORECASE)
    col_m = re.search(r"Col(?:umn)?\s+(\d+)", text, re.IGNORECASE)
    return (
        int(line_m.group(1)) if line_m else None,
        int(col_m.group(1)) if col_m else None,
    )


def _classify_expr(node: exp.Expression, raw_sql: str = "") -> str:
    if isinstance(node, exp.Select):
        return "CTE_SELECT" if (node.args.get("with_") or node.args.get("with")) else "SELECT"
    if isinstance(node, (exp.Union, exp.Intersect, exp.Except)):
        return type(node).__name__.upper()
    if isinstance(node, exp.Insert):
        return "INSERT"
    if isinstance(node, exp.Update):
        return "UPDATE"
    if isinstance(node, exp.Delete):
        return "DELETE"
    if isinstance(node, exp.Merge):
        return "MERGE"
    if isinstance(node, exp.Create):
        return "CREATE"
    if isinstance(node, exp.Alter):
        return "ALTER"
    if isinstance(node, exp.Drop):
        return "DROP"
    if isinstance(node, getattr(exp, "TruncateTable", tuple())):
        return "TRUNCATE"
    if isinstance(node, exp.Command):
        toks = raw_sql.strip().split()
        return toks[0].upper() if toks else "COMMAND"
    return type(node).__name__.upper()


def parse_sql_ast(sql: str, dialect: str = "postgresql") -> DialectParseResult:
    """Parse SQL string into SQLGlot AST nodes for the specified dialect."""
    norm = normalize_dialect(dialect)
    sg_dialect = to_sqlglot_read_write(norm)
    raw = (sql or "").strip()
    if not raw:
        return DialectParseResult(
            dialect=norm,
            is_valid=False,
            error_message="SQL input is empty.",
        )

    try:
        parsed = [n for n in sqlglot.parse(raw, read=sg_dialect) if n is not None]
    except (ParseError, SqlglotError) as exc:
        line, col = _extract_error_coords(exc)
        return DialectParseResult(
            dialect=norm,
            is_valid=False,
            error_message=str(exc),
            error_line=line,
            error_column=col,
        )

    if not parsed:
        return DialectParseResult(
            dialect=norm,
            is_valid=False,
            error_message="No SQL statement found after stripping comments.",
        )

    stmt_types = [_classify_expr(stmt, raw) for stmt in parsed]
    return DialectParseResult(
        dialect=norm,
        is_valid=True,
        statements=parsed,
        statement_types=stmt_types,
    )


def format_sql_for_dialect(sql: str, dialect: str = "postgresql") -> tuple[str, str | None]:
    """Pretty-format SQL cleanly for the chosen dialect using SQLGlot."""
    norm = normalize_dialect(dialect)
    sg = to_sqlglot_read_write(norm)
    parsed = parse_sql_ast(sql, norm)
    if not parsed.is_valid:
        return sql.strip(), parsed.error_message
    formatted = ";\n\n".join(stmt.sql(dialect=sg, pretty=True) for stmt in parsed.statements)
    if sql.strip().endswith(";"):
        formatted += ";"
    return formatted, None


def _detect_conversion_limitations(
    asts: list[exp.Expression],
    source_dialect: str,
    target_dialect: str,
) -> tuple[list[str], list[str]]:
    """Inspect source ASTs for dialect constructs with limited or lossy translation."""
    warnings: list[str] = []
    limitations: list[str] = []

    for root in asts:
        sql_upper = root.sql(dialect=to_sqlglot_read_write(source_dialect)).upper()

        if source_dialect == "postgresql" and target_dialect != "postgresql":
            if "DISTINCT ON" in sql_upper:
                limitations.append(
                    "PostgreSQL DISTINCT ON has no native equivalent in MySQL, SQLite, or SQL Server; "
                    "rewrite using ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) = 1."
                )
            if any(isinstance(n, exp.ILike) for n in root.walk()):
                warnings.append(
                    f"{target_dialect} treats LIKE/LOWER differently than PostgreSQL ILIKE; verify collation case-sensitivity."
                )
            if any(isinstance(n, exp.Returning) for n in root.walk()) and target_dialect == "mysql":
                limitations.append("MySQL does not support PostgreSQL DML RETURNING clauses.")
            if "GENERATE_SERIES" in sql_upper and target_dialect in {"mysql", "sqlite", "sqlserver"}:
                limitations.append(
                    f"PostgreSQL GENERATE_SERIES() is not natively available in {target_dialect}; "
                    "consider a recursive CTE (WITH RECURSIVE)."
                )

        if target_dialect == "sqlserver":
            if any(isinstance(n, exp.Order) for n in root.walk()) is False and any(
                isinstance(n, exp.Offset) for n in root.walk()
            ):
                limitations.append(
                    "SQL Server OFFSET ... FETCH requires an explicit ORDER BY clause."
                )
            if "GROUP_CONCAT" in sql_upper or "STRING_AGG" in sql_upper:
                warnings.append(
                    "Verify STRING_AGG availability on SQL Server (requires SQL Server 2017+)."
                )

        if target_dialect == "sqlite":
            if "RIGHT JOIN" in sql_upper or "FULL OUTER JOIN" in sql_upper:
                warnings.append(
                    "SQLite supports RIGHT and FULL OUTER JOIN starting in version 3.39.0 (older runtimes reject them)."
                )
            if any(isinstance(n, exp.Window) for n in root.walk()):
                warnings.append("Window functions require SQLite 3.25.0 or newer.")

        if target_dialect == "mysql":
            if "FULL OUTER JOIN" in sql_upper:
                limitations.append(
                    "MySQL does not natively support FULL OUTER JOIN; emulate via LEFT JOIN UNION RIGHT JOIN."
                )
            if any(isinstance(n, exp.CTE) for n in root.walk()):
                warnings.append("CTEs and window functions require MySQL 8.0 or newer.")

        if any(isinstance(n, exp.Create) for n in root.walk()):
            if "SERIAL" in sql_upper or "AUTO_INCREMENT" in sql_upper or "IDENTITY" in sql_upper:
                warnings.append(
                    "Auto-increment key definitions differ by engine (SERIAL vs AUTO_INCREMENT vs AUTOINCREMENT vs IDENTITY)."
                )

    return warnings, limitations


def convert_sql_dialect(
    sql: str,
    source_dialect: str,
    target_dialect: str,
    pretty: bool = True,
) -> ConversionResult:
    """Convert SQL between PostgreSQL, MySQL, SQLite, and SQL Server using SQLGlot ASTs."""
    src = normalize_dialect(source_dialect)
    tgt = normalize_dialect(target_dialect)
    parsed = parse_sql_ast(sql, src)
    if not parsed.is_valid:
        return ConversionResult(
            source_dialect=src,
            target_dialect=tgt,
            source_sql=sql,
            converted_sql=sql,
            success=False,
            error_message=parsed.error_message,
        )

    warnings, limitations = _detect_conversion_limitations(parsed.statements, src, tgt)
    src_sg = to_sqlglot_read_write(src)
    tgt_sg = to_sqlglot_read_write(tgt)

    try:
        transpiled = sqlglot.transpile(
            sql,
            read=src_sg,
            write=tgt_sg,
            pretty=pretty,
            unsupported_level=sqlglot.ErrorLevel.WARN,
        )
        converted_sql = ";\n\n".join(stmt for stmt in transpiled if stmt)
        if sql.strip().endswith(";") and converted_sql and not converted_sql.endswith(";"):
            converted_sql += ";"
    except SqlglotError as exc:
        return ConversionResult(
            source_dialect=src,
            target_dialect=tgt,
            source_sql=sql,
            converted_sql=sql,
            success=False,
            warnings=warnings,
            limitations=limitations,
            error_message=f"AST conversion from {src} to {tgt} failed: {exc}",
        )

    return ConversionResult(
        source_dialect=src,
        target_dialect=tgt,
        source_sql=sql,
        converted_sql=converted_sql,
        success=True,
        warnings=warnings,
        limitations=limitations,
    )


def _is_string_concat_operand(node: exp.Expression | None) -> bool:
    if node is None:
        return False
    if isinstance(node, exp.Literal) and node.is_string:
        return True
    if isinstance(node, (exp.DPipe, exp.Concat)):
        return True
    if isinstance(node, exp.Add):
        return _is_string_concat_operand(node.this) or _is_string_concat_operand(node.expression)
    return False


def _rewrite_tsql_string_add(root: exp.Expression) -> exp.Expression:
    """Rewrite T-SQL string `+` chains into ANSI `||` (exp.DPipe) for DuckDB execution."""

    def _transform(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Add) and _is_string_concat_operand(node):
            return exp.DPipe(this=node.this, expression=node.expression)
        return node

    return root.transform(_transform)


def transpile_for_duckdb(sql: str, user_dialect: str) -> tuple[str, list[str], str | None]:
    """Transpile dialect SQL safely to DuckDB for local sandbox execution."""
    src = normalize_dialect(user_dialect)
    if src == "duckdb":
        return sql, [], None
    res = convert_sql_dialect(sql, src, "duckdb", pretty=False)
    if not res.success:
        return sql, res.warnings + res.limitations, res.error_message
    converted_sql = res.converted_sql
    if src == "sqlserver":
        try:
            trees = [n for n in sqlglot.parse(sql, read="tsql") if n is not None]
            if trees:
                rewritten = [_rewrite_tsql_string_add(t).sql(dialect="duckdb", pretty=False) for t in trees]
                converted_sql = ";\n\n".join(s for s in rewritten if s)
                if sql.strip().endswith(";") and converted_sql and not converted_sql.endswith(";"):
                    converted_sql += ";"
        except SqlglotError:
            pass
    notes = list(res.warnings)
    if src != "postgresql":
        notes.append(
            f"Executed inside isolated DuckDB local sandbox (transpiled from {src} AST via SQLGlot)."
        )
    return converted_sql, notes, None


def dialect_notes_for(dialect: str) -> dict[str, Any]:
    """Return accurate dialect syntax and capability reference details."""
    d = normalize_dialect(dialect)
    table = {
        "postgresql": {
            "label": "PostgreSQL",
            "identifier_quote": '"identifier"',
            "pagination": "LIMIT n OFFSET m  or  FETCH FIRST n ROWS ONLY",
            "date_truncation": "DATE_TRUNC('month', col)",
            "string_agg": "STRING_AGG(col, ',')",
            "case_insensitive_like": "ILIKE",
            "auto_increment": "SERIAL / GENERATED ALWAYS AS IDENTITY",
        },
        "mysql": {
            "label": "MySQL",
            "identifier_quote": "`identifier`",
            "pagination": "LIMIT n OFFSET m",
            "date_truncation": "DATE_FORMAT(col, '%Y-%m-01')",
            "string_agg": "GROUP_CONCAT(col SEPARATOR ',')",
            "case_insensitive_like": "LIKE (collation-dependent)",
            "auto_increment": "INT AUTO_INCREMENT PRIMARY KEY",
        },
        "sqlite": {
            "label": "SQLite",
            "identifier_quote": '"identifier"',
            "pagination": "LIMIT n OFFSET m",
            "date_truncation": "strftime('%Y-%m-01', col)",
            "string_agg": "GROUP_CONCAT(col, ',')",
            "case_insensitive_like": "LIKE (ASCII case-insensitive by default)",
            "auto_increment": "INTEGER PRIMARY KEY AUTOINCREMENT",
        },
        "sqlserver": {
            "label": "Microsoft SQL Server (T-SQL)",
            "identifier_quote": "[identifier]",
            "pagination": "SELECT TOP n ...  or  ORDER BY ... OFFSET m ROWS FETCH NEXT n ROWS ONLY",
            "date_truncation": "DATEFROMPARTS(YEAR(col), MONTH(col), 1) or DATETRUNC(month, col)",
            "string_agg": "STRING_AGG(col, ',') (SQL Server 2017+)",
            "case_insensitive_like": "LIKE (server/column collation dependent)",
            "auto_increment": "INT IDENTITY(1,1) PRIMARY KEY",
        },
    }
    return table[d]
