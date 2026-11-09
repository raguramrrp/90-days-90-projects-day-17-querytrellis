"""Security guardrails, multi-dialect AST classification, and explicit write consent."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from sqlglot import exp

from src.dialects.sqlglot_engine import parse_sql_ast

_PROCESS_HMAC_SECRET = secrets.token_bytes(32)

_WRITE_DML_NODES: tuple[type[exp.Expression], ...] = tuple(
    t
    for t in (
        getattr(exp, "Insert", None),
        getattr(exp, "Update", None),
        getattr(exp, "Delete", None),
        getattr(exp, "Merge", None),
    )
    if t is not None
)

_WRITE_DDL_NODES: tuple[type[exp.Expression], ...] = tuple(
    t
    for t in (
        getattr(exp, "Create", None),
        getattr(exp, "Drop", None),
        getattr(exp, "Alter", None),
        getattr(exp, "TruncateTable", None),
    )
    if t is not None
)

_FORBIDDEN_ADMIN_NODES: tuple[type[exp.Expression], ...] = tuple(
    t
    for t in (
        getattr(exp, "Grant", None),
        getattr(exp, "Revoke", None),
        getattr(exp, "Copy", None),
        getattr(exp, "Attach", None),
        getattr(exp, "Detach", None),
        getattr(exp, "Pragma", None),
        getattr(exp, "Install", None),
        getattr(exp, "LoadData", None),
        getattr(exp, "Kill", None),
        getattr(exp, "Lock", None),
        getattr(exp, "Into", None),
        getattr(exp, "Set", None),
    )
    if t is not None
)

DANGEROUS_FUNCTIONS: frozenset[str] = frozenset(
    {
        # PostgreSQL admin/filesystem/sleep
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "lo_unlink",
        "dblink",
        "dblink_exec",
        "dblink_connect",
        "pg_sleep",
        # MySQL / SQL Server side effects
        "sleep",
        "load_file",
        "xp_cmdshell",
        "openrowset",
        "opendatasource",
        # DuckDB external filesystem / environment access inside sandbox SQL
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "read_text",
        "glob",
        "getenv",
    }
)


@dataclass(slots=True)
class WriteConfirmationChallenge:
    """Explicit confirmation details presented before opt-in write execution."""

    token: str
    operation_type: str
    target_database: str
    affected_tables: list[str]
    consequences: list[str]
    rollback_note: str
    expires_at_epoch: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "operation_type": self.operation_type,
            "target_database": self.target_database,
            "affected_tables": self.affected_tables,
            "consequences": self.consequences,
            "rollback_note": self.rollback_note,
            "expires_at_epoch": self.expires_at_epoch,
        }


@dataclass(slots=True)
class SafetyEvaluation:
    """Outcome of classifying SQL against read-only default and write safeguards."""

    is_valid: bool
    is_read_only: bool
    operation_category: str  # read_only | write_dml | write_ddl | blocked | syntax_error
    operation_name: str
    allowed: bool
    requires_write_confirmation: bool = False
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)
    affected_tables: list[str] = field(default_factory=list)
    confirmation_challenge: WriteConfirmationChallenge | None = None


def _compute_write_token(
    sql: str,
    target_db: str,
    operation_name: str,
    expires_at_epoch: int,
) -> str:
    payload = f"{target_db}|{operation_name}|{expires_at_epoch}|{sql.strip()}".encode("utf-8")
    sig = hmac.new(_PROCESS_HMAC_SECRET, payload, hashlib.sha256).hexdigest()
    return f"{expires_at_epoch}:{sig}"


def verify_write_confirmation_token(
    token: str | None,
    sql: str,
    target_db: str,
    operation_name: str,
) -> bool:
    """Verify explicit user confirmation token bound to exact SQL, target DB, and operation."""
    if not token or ":" not in token:
        return False
    exp_str, sig = token.split(":", 1)
    try:
        expires_at = int(exp_str)
    except ValueError:
        return False
    if int(time.time()) > expires_at:
        return False
    expected = _compute_write_token(sql, target_db, operation_name, expires_at)
    return hmac.compare_digest(token, expected)


def _describe_write_consequences(op_name: str, tables: list[str], is_ddl: bool) -> tuple[list[str], str]:
    tbl_label = ", ".join(tables) if tables else "target table(s)"
    consequences: list[str] = []
    if op_name in {"DROP", "TRUNCATE"}:
        consequences.append(f"Permanently removes structure or all rows from {tbl_label}.")
        consequences.append("Dependent views, indexes, or foreign key references may break or cascade.")
    elif op_name == "DELETE":
        consequences.append(f"Deletes matching rows from {tbl_label}.")
        if "WHERE" not in tbl_label:  # checked further by caller via SQL check
            consequences.append("Verify your WHERE predicate carefully to avoid deleting unintended rows.")
    elif op_name == "UPDATE":
        consequences.append(f"Modifies existing row values inside {tbl_label}.")
    elif op_name == "INSERT":
        consequences.append(f"Inserts new records into {tbl_label}.")
    elif op_name == "ALTER":
        consequences.append(f"Modifies table schema definition on {tbl_label}.")
    else:
        consequences.append(f"Executes state-changing operation ({op_name}) on {tbl_label}.")

    if is_ddl:
        rollback_note = (
            "DDL statements (DROP/TRUNCATE/ALTER/CREATE) auto-commit in MySQL and SQLite DDL/external tools; "
            "a transaction rollback does NOT undo auto-committed DDL."
        )
    else:
        rollback_note = (
            "Write execution runs only when your active database account permits writes and you have "
            "explicitly confirmed this exact statement and target database."
        )
    return consequences, rollback_note


def sanitize_error_message(raw_error: str) -> str:
    """Scrub passwords, bearer tokens, API keys, and DSN credentials from errors."""
    msg = (raw_error or "").strip()
    msg = re.sub(r"(?i)(password|pwd|secret|api[_-]?key|token)\s*=\s*([^\s;'\"&]+)", r"\1=[REDACTED]", msg)
    msg = re.sub(r"://([^:/@\s]+):([^/@\s]+)@", r"://\1:[REDACTED]@", msg)
    msg = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[REDACTED_API_KEY]", msg)
    return msg


def evaluate_sql_safety(
    sql: str,
    *,
    dialect: str = "postgresql",
    target_database: str = "sandbox",
    allow_write_opt_in: bool = False,
    confirmed_write: bool = False,
    confirmation_token: str | None = None,
) -> SafetyEvaluation:
    """Classify and authorize SQL according to read-only default & opt-in write rules."""
    parsed = parse_sql_ast(sql, dialect)
    if not parsed.is_valid:
        return SafetyEvaluation(
            is_valid=False,
            is_read_only=False,
            operation_category="syntax_error",
            operation_name="INVALID_SQL",
            allowed=False,
            error_message=parsed.error_message,
        )

    if len(parsed.statements) > 1:
        return SafetyEvaluation(
            is_valid=True,
            is_read_only=False,
            operation_category="blocked",
            operation_name="MULTIPLE_STATEMENTS",
            allowed=False,
            error_message=(
                f"Detected {len(parsed.statements)} statements in one batch. "
                "Execute one statement at a time for isolation and safety."
            ),
        )

    root = parsed.statements[0]
    affected_tables = sorted({t.name for t in root.find_all(exp.Table) if t.name})

    # Unparsed or administrative commands
    if isinstance(root, exp.Command):
        cmd_kw = (sql.strip().split()[0].upper() if sql.strip().split() else "COMMAND")
        return SafetyEvaluation(
            is_valid=True,
            is_read_only=False,
            operation_category="blocked",
            operation_name=cmd_kw,
            allowed=False,
            affected_tables=affected_tables,
            error_message=f"Administrative/command statement '{cmd_kw}' is blocked for safety.",
        )

    # Check dangerous functions across whole AST
    for node in root.walk():
        if isinstance(node, (exp.Anonymous, exp.Func)):
            fname = (
                str(node.this).lower()
                if isinstance(node, exp.Anonymous)
                else (node.sql_name() or "").lower()
            )
            if fname in DANGEROUS_FUNCTIONS:
                return SafetyEvaluation(
                    is_valid=True,
                    is_read_only=False,
                    operation_category="blocked",
                    operation_name=f"FUNCTION:{fname}",
                    allowed=False,
                    affected_tables=affected_tables,
                    error_message=f"Restricted system/file/delay function '{fname}()' is blocked.",
                )
        if isinstance(node, _FORBIDDEN_ADMIN_NODES):
            node_name = type(node).__name__.upper()
            if isinstance(node, exp.Into):
                node_name = "SELECT_INTO"
            elif isinstance(node, exp.Lock):
                node_name = "ROW_LOCK"
            return SafetyEvaluation(
                is_valid=True,
                is_read_only=False,
                operation_category="blocked",
                operation_name=node_name,
                allowed=False,
                affected_tables=affected_tables,
                error_message=f"Operation '{node_name}' is not permitted.",
            )

    # Check read-only locking clauses
    for sel in root.find_all(exp.Select):
        if sel.args.get("locks"):
            return SafetyEvaluation(
                is_valid=True,
                is_read_only=False,
                operation_category="blocked",
                operation_name="FOR_UPDATE_LOCK",
                allowed=False,
                affected_tables=affected_tables,
                error_message="Row locking clauses (FOR UPDATE / FOR SHARE) are blocked.",
            )

    # Detect DDL / DML anywhere in AST (including inside CTEs!)
    found_ddl = [n for n in root.walk() if isinstance(n, _WRITE_DDL_NODES)]
    found_dml = [n for n in root.walk() if isinstance(n, _WRITE_DML_NODES)]

    if found_ddl or found_dml:
        is_ddl = bool(found_ddl)
        first_node = found_ddl[0] if found_ddl else found_dml[0]
        op_name = type(first_node).__name__.upper()
        if op_name == "TRUNCATETABLE":
            op_name = "TRUNCATE"
        category = "write_ddl" if is_ddl else "write_dml"

        warnings: list[str] = []
        if op_name in {"UPDATE", "DELETE"} and not first_node.args.get("where"):
            warnings.append(
                f"CRITICAL WARNING: {op_name} has NO WHERE clause and will affect EVERY row in target table!"
            )

        if not allow_write_opt_in:
            return SafetyEvaluation(
                is_valid=True,
                is_read_only=False,
                operation_category=category,
                operation_name=op_name,
                allowed=False,
                affected_tables=affected_tables,
                warnings=warnings,
                error_message=(
                    f"Blocked '{op_name}' in Read-Only default mode. "
                    "Enable explicit Write Opt-In in SQL Editor / Database Manager and confirm the operation if intended."
                ),
            )

        if confirmed_write and verify_write_confirmation_token(
            confirmation_token, sql, target_database, op_name
        ):
            return SafetyEvaluation(
                is_valid=True,
                is_read_only=False,
                operation_category=category,
                operation_name=op_name,
                allowed=True,
                requires_write_confirmation=False,
                affected_tables=affected_tables,
                warnings=warnings,
            )

        expires_at = int(time.time()) + 300
        token = _compute_write_token(sql, target_database, op_name, expires_at)
        consequences, rollback_note = _describe_write_consequences(op_name, affected_tables, is_ddl)
        challenge = WriteConfirmationChallenge(
            token=token,
            operation_type=op_name,
            target_database=target_database,
            affected_tables=affected_tables,
            consequences=warnings + consequences,
            rollback_note=rollback_note,
            expires_at_epoch=expires_at,
        )
        return SafetyEvaluation(
            is_valid=True,
            is_read_only=False,
            operation_category=category,
            operation_name=op_name,
            allowed=False,
            requires_write_confirmation=True,
            affected_tables=affected_tables,
            warnings=warnings,
            confirmation_challenge=challenge,
            error_message=f"Explicit write confirmation required before executing '{op_name}'.",
        )

    # Check root is SELECT / UNION / INTERSECT / EXCEPT / Subquery
    allowed_roots = tuple(
        t
        for t in (
            exp.Select,
            getattr(exp, "Union", None),
            getattr(exp, "Intersect", None),
            getattr(exp, "Except", None),
            exp.Subquery,
        )
        if t is not None
    )
    if not isinstance(root, allowed_roots):
        op_name = type(root).__name__.upper()
        return SafetyEvaluation(
            is_valid=True,
            is_read_only=False,
            operation_category="blocked",
            operation_name=op_name,
            allowed=False,
            affected_tables=affected_tables,
            error_message=f"Statement type '{op_name}' is not permitted.",
        )

    return SafetyEvaluation(
        is_valid=True,
        is_read_only=True,
        operation_category="read_only",
        operation_name=_classify_read_op(root),
        allowed=True,
        affected_tables=affected_tables,
    )


def _classify_read_op(root: exp.Expression) -> str:
    if isinstance(root, exp.Select) and (root.args.get("with_") or root.args.get("with")):
        return "CTE SELECT"
    if isinstance(root, (exp.Union, exp.Intersect, exp.Except)):
        return type(root).__name__.upper()
    return "SELECT"
