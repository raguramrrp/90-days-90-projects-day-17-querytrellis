"""AST-based PostgreSQL SQL parser, single-statement validator, and structural extractor.

Security model:
- Never relies on naive string checks like ``sql.startswith("SELECT")``.
- Parses SQL using SQLGlot's PostgreSQL dialect and walks the full AST.
- Rejects multiple statements, write/DDL/DCL operations (even inside CTEs),
  locking clauses (FOR UPDATE/SHARE), SELECT INTO, and admin side-effect functions.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

logging.getLogger("sqlglot").setLevel(logging.ERROR)

DISALLOWED_AST_TYPES: tuple[type[exp.Expression], ...] = tuple(
    t
    for t in (
        getattr(exp, "Insert", None),
        getattr(exp, "Update", None),
        getattr(exp, "Delete", None),
        getattr(exp, "Merge", None),
        getattr(exp, "Create", None),
        getattr(exp, "Drop", None),
        getattr(exp, "Alter", None),
        getattr(exp, "TruncateTable", None),
        getattr(exp, "Command", None),
        getattr(exp, "Transaction", None),
        getattr(exp, "Commit", None),
        getattr(exp, "Rollback", None),
        getattr(exp, "Lock", None),
        getattr(exp, "Into", None),
        getattr(exp, "Grant", None),
        getattr(exp, "Revoke", None),
        getattr(exp, "Set", None),
        getattr(exp, "Copy", None),
        getattr(exp, "Analyze", None),
        getattr(exp, "Cache", None),
        getattr(exp, "Kill", None),
        getattr(exp, "Pragma", None),
    )
    if t is not None
)

ALLOWED_ROOT_TYPES: tuple[type[exp.Expression], ...] = tuple(
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

DANGEROUS_PG_FUNCTIONS: frozenset[str] = frozenset(
    {
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
    }
)


@dataclass(slots=True)
class TableRef:
    """Table reference found in FROM or JOIN clauses."""

    schema: str | None
    table: str
    alias: str | None


@dataclass(slots=True)
class PredicateInfo:
    """Extracted predicate from WHERE or JOIN ON."""

    location: str  # "WHERE" | "JOIN_ON"
    table_or_alias: str | None
    column: str | None
    operator: str
    is_function_wrapped: bool
    function_name: str | None
    literal_kind: str | None  # "str" | "num" | "bool" | "null" | None
    literal_value: str | None
    has_leading_wildcard: bool
    is_in_or_branch: bool
    raw_sql: str


@dataclass(slots=True)
class JoinInfo:
    """Extracted JOIN clause metadata."""

    join_type: str
    table_name: str
    table_alias: str | None
    has_on_condition: bool
    on_raw_sql: str
    column_pairs: list[tuple[str | None, str, str | None, str]] = field(default_factory=list)
    has_or_in_on: bool = False
    has_func_in_on: bool = False
    has_non_equi_on: bool = False
    is_comma_join: bool = False


@dataclass(slots=True)
class ParsedQueryInfo:
    """Structural summary of a validated PostgreSQL SELECT statement."""

    clean_sql: str
    normalized_hash: str
    statement_type: str
    tables: list[TableRef] = field(default_factory=list)
    alias_to_table: dict[str, str] = field(default_factory=dict)
    cte_names: list[str] = field(default_factory=list)
    predicates: list[PredicateInfo] = field(default_factory=list)
    joins: list[JoinInfo] = field(default_factory=list)
    order_by_cols: list[tuple[str | None, str, str, bool]] = field(default_factory=list)
    group_by_cols: list[tuple[str | None, str]] = field(default_factory=list)
    select_columns: list[tuple[str | None, str]] = field(default_factory=list)
    select_star_fragments: list[str] = field(default_factory=list)
    has_distinct: bool = False
    limit_value: int | None = None
    offset_value: int | None = None
    subquery_count: int = 0
    has_window_functions: bool = False


@dataclass(slots=True)
class ValidationResult:
    """Outcome of parsing and read-only safety validation."""

    is_valid: bool
    is_read_only: bool
    clean_sql: str = ""
    error_message: str = ""
    rejected_operation: str = ""
    ast: exp.Expression | None = None
    parsed_info: ParsedQueryInfo | None = None


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comments solely for checking if any non-comment text remains."""
    no_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", "", no_block)
    return no_line.strip()


def _detect_command_keyword(raw_sql: str) -> str:
    tokens = _strip_sql_comments(raw_sql).split()
    return tokens[0].upper() if tokens else "COMMAND"


def _classify_literal(node: exp.Expression | None) -> tuple[str | None, str | None]:
    if node is None:
        return None, None
    if isinstance(node, exp.Literal):
        if node.is_string:
            return "str", str(node.this)
        return "num", str(node.this)
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal):
        return "num", f"-{node.this.this}"
    if isinstance(node, exp.Boolean):
        return "bool", str(node.this).lower()
    if isinstance(node, exp.Null):
        return "null", "NULL"
    return None, None


def _extract_column_or_wrapped(node: exp.Expression) -> tuple[str | None, str | None, bool, str | None]:
    """Return (table_or_alias, column_name, is_wrapped_in_func_or_math, wrapper_name)."""
    if isinstance(node, exp.Column):
        tbl = node.table or None
        col = node.name or None
        return tbl, col, False, None

    if isinstance(node, (exp.Func, exp.Anonymous, exp.Cast, exp.TryCast, exp.Extract, exp.Add, exp.Sub, exp.Mul, exp.Div)):
        cols = list(node.find_all(exp.Column))
        if len(cols) == 1:
            col_node = cols[0]
            wrapper = node.sql_name() if hasattr(node, "sql_name") else type(node).__name__.upper()
            if isinstance(node, exp.Anonymous):
                wrapper = str(node.this).upper()
            elif isinstance(node, (exp.Cast, exp.TryCast)):
                wrapper = "CAST"
            elif isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div)):
                wrapper = "ARITHMETIC"
            return (col_node.table or None), (col_node.name or None), True, wrapper
    return None, None, False, None


def _is_under_or(node: exp.Expression, stop_at: exp.Expression) -> bool:
    curr = node.parent
    while curr is not None and curr is not stop_at:
        if isinstance(curr, exp.Or):
            return True
        curr = curr.parent
    return False


def _extract_predicates_from_expr(
    root_expr: exp.Expression, location: str
) -> list[PredicateInfo]:
    preds: list[PredicateInfo] = []
    comp_types = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Like, exp.ILike, exp.In, exp.Between, exp.Is)
    for node in root_expr.walk():
        if not isinstance(node, comp_types):
            continue
        in_or = _is_under_or(node, root_expr)
        op_name = type(node).__name__.upper()
        if isinstance(node, exp.EQ):
            op_name = "="
        elif isinstance(node, exp.NEQ):
            op_name = "<>"
        elif isinstance(node, exp.GT):
            op_name = ">"
        elif isinstance(node, exp.GTE):
            op_name = ">="
        elif isinstance(node, exp.LT):
            op_name = "<"
        elif isinstance(node, exp.LTE):
            op_name = "<="
        elif isinstance(node, exp.ILike):
            op_name = "ILIKE"
        elif isinstance(node, exp.Like):
            op_name = "LIKE"

        left = getattr(node, "this", None)
        right = getattr(node, "expression", None)

        if left is None:
            continue

        # Check left side first, then swap if literal is on left (e.g. 'abc' = col)
        tbl, col, wrapped, wrapper = _extract_column_or_wrapped(left)
        lit_kind, lit_val = _classify_literal(right)
        if col is None and right is not None:
            tbl, col, wrapped, wrapper = _extract_column_or_wrapped(right)
            lit_kind, lit_val = _classify_literal(left)

        if col is None and not wrapped:
            continue

        leading_wildcard = False
        if isinstance(node, (exp.Like, exp.ILike)) and lit_kind == "str" and lit_val is not None:
            if lit_val.startswith("%") or lit_val.startswith("_"):
                leading_wildcard = True

        preds.append(
            PredicateInfo(
                location=location,
                table_or_alias=tbl,
                column=col,
                operator=op_name,
                is_function_wrapped=wrapped,
                function_name=wrapper,
                literal_kind=lit_kind,
                literal_value=lit_val,
                has_leading_wildcard=leading_wildcard,
                is_in_or_branch=in_or,
                raw_sql=node.sql(dialect="postgres"),
            )
        )
    return preds


def _extract_query_info(ast: exp.Expression, clean_sql: str) -> ParsedQueryInfo:
    normalized = re.sub(r"\s+", " ", ast.sql(dialect="postgres")).strip()
    sql_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    stmt_type = "SELECT"
    if ast.args.get("with_") or ast.args.get("with"):
        stmt_type = "WITH (CTE) SELECT"
    elif isinstance(ast, (exp.Union, exp.Intersect, exp.Except)):
        stmt_type = type(ast).__name__.upper()

    cte_names: list[str] = []
    for cte in ast.find_all(exp.CTE):
        alias = cte.alias_or_name
        if alias:
            cte_names.append(alias)
    cte_lower = {c.lower() for c in cte_names}

    tables: list[TableRef] = []
    alias_to_table: dict[str, str] = {}
    seen_tables: set[tuple[str | None, str, str | None]] = set()
    for tbl_node in ast.find_all(exp.Table):
        tname = tbl_node.name
        if not tname or tname.lower() in cte_lower:
            continue
        schema = tbl_node.db or None
        alias = tbl_node.alias or None
        key = (schema, tname, alias)
        if key not in seen_tables:
            seen_tables.add(key)
            tables.append(TableRef(schema=schema, table=tname, alias=alias))
        alias_to_table[tname.lower()] = tname.lower()
        if alias:
            alias_to_table[alias.lower()] = tname.lower()

    predicates: list[PredicateInfo] = []
    for where_node in ast.find_all(exp.Where):
        predicates.extend(_extract_predicates_from_expr(where_node.this, "WHERE"))

    joins: list[JoinInfo] = []
    for select_node in ast.find_all(exp.Select):
        # Comma-joins in FROM (older sqlglot versions put them in from_.expressions)
        from_node = select_node.args.get("from_") or select_node.args.get("from")
        if from_node and len(from_node.expressions) > 1:
            for extra_tbl in from_node.expressions[1:]:
                tname = extra_tbl.name if isinstance(extra_tbl, exp.Table) else extra_tbl.sql(dialect="postgres")
                joins.append(
                    JoinInfo(
                        join_type="COMMA JOIN",
                        table_name=tname,
                        table_alias=extra_tbl.alias or None if isinstance(extra_tbl, exp.Table) else None,
                        has_on_condition=False,
                        on_raw_sql="",
                        is_comma_join=True,
                    )
                )

        for join_node in select_node.args.get("joins") or []:
            jkind = " ".join(
                part
                for part in [join_node.side or "", join_node.kind or "", "JOIN"]
                if part
            ).strip()
            target = join_node.this
            tname = target.name if isinstance(target, exp.Table) else target.sql(dialect="postgres")
            talias = target.alias or None if isinstance(target, exp.Table) else None
            on_expr = join_node.args.get("on")
            using_expr = join_node.args.get("using")
            is_comma = (
                not (join_node.side or "")
                and not (join_node.kind or "")
                and on_expr is None
                and using_expr is None
            )
            if is_comma:
                jkind = "COMMA JOIN"

            col_pairs: list[tuple[str | None, str, str | None, str]] = []
            has_or = False
            has_func = False
            has_non_equi = False
            on_sql = ""
            if on_expr is not None:
                on_sql = on_expr.sql(dialect="postgres")
                predicates.extend(_extract_predicates_from_expr(on_expr, "JOIN_ON"))
                has_or = any(True for _ in on_expr.find_all(exp.Or))
                has_non_equi = any(
                    True
                    for _ in on_expr.find_all((exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Like, exp.ILike))
                )
                for eq in on_expr.find_all(exp.EQ):
                    lt, lc, lw, _ = _extract_column_or_wrapped(eq.left)
                    rt, rc, rw, _ = _extract_column_or_wrapped(eq.right)
                    if lw or rw:
                        has_func = True
                    if lc and rc:
                        col_pairs.append((lt, lc, rt, rc))
            elif using_expr is not None:
                on_sql = f"USING ({', '.join(c.name for c in using_expr)})"
                for c in using_expr:
                    col_pairs.append((None, c.name, talias or tname, c.name))

            joins.append(
                JoinInfo(
                    join_type=jkind,
                    table_name=tname,
                    table_alias=talias,
                    has_on_condition=(on_expr is not None or using_expr is not None),
                    on_raw_sql=on_sql,
                    column_pairs=col_pairs,
                    has_or_in_on=has_or,
                    has_func_in_on=has_func,
                    has_non_equi_on=has_non_equi,
                    is_comma_join=is_comma,
                )
            )

    order_by_cols: list[tuple[str | None, str, str, bool]] = []
    for ob in ast.find_all(exp.Order):
        in_sub = ob.parent is not ast
        for ordered in ob.expressions:
            direction = "DESC" if ordered.args.get("desc") else "ASC"
            inner = ordered.this
            if isinstance(inner, exp.Column):
                order_by_cols.append((inner.table or None, inner.name, direction, in_sub))
            else:
                order_by_cols.append((None, inner.sql(dialect="postgres"), direction, in_sub))

    group_by_cols: list[tuple[str | None, str]] = []
    for gb in ast.find_all(exp.Group):
        for gexpr in gb.expressions:
            if isinstance(gexpr, exp.Column):
                group_by_cols.append((gexpr.table or None, gexpr.name))

    select_columns: list[tuple[str | None, str]] = []
    select_star_fragments: list[str] = []
    has_distinct = False
    for sel in ast.find_all(exp.Select):
        if sel.args.get("distinct"):
            has_distinct = True
        for proj in sel.expressions:
            actual = proj.this if isinstance(proj, exp.Alias) else proj
            if isinstance(actual, exp.Star):
                # Ignore COUNT(*)
                if not isinstance(proj.parent, exp.Count):
                    select_star_fragments.append(sel.sql(dialect="postgres")[:140])
            elif isinstance(actual, exp.Column):
                select_columns.append((actual.table or None, actual.name))
            else:
                for c in actual.find_all(exp.Column):
                    select_columns.append((c.table or None, c.name))

    limit_value: int | None = None
    limit_node = ast.args.get("limit")
    if isinstance(limit_node, exp.Limit) and isinstance(limit_node.expression, exp.Literal):
        try:
            limit_value = int(limit_node.expression.this)
        except (TypeError, ValueError):
            limit_value = None

    offset_value: int | None = None
    offset_node = ast.args.get("offset")
    if isinstance(offset_node, exp.Offset) and isinstance(offset_node.expression, exp.Literal):
        try:
            offset_value = int(offset_node.expression.this)
        except (TypeError, ValueError):
            offset_value = None

    subqueries = [s for s in ast.find_all(exp.Subquery)]
    has_window = any(True for _ in ast.find_all(exp.Window))

    return ParsedQueryInfo(
        clean_sql=clean_sql,
        normalized_hash=sql_hash,
        statement_type=stmt_type,
        tables=tables,
        alias_to_table=alias_to_table,
        cte_names=cte_names,
        predicates=predicates,
        joins=joins,
        order_by_cols=order_by_cols,
        group_by_cols=group_by_cols,
        select_columns=select_columns,
        select_star_fragments=select_star_fragments,
        has_distinct=has_distinct,
        limit_value=limit_value,
        offset_value=offset_value,
        subquery_count=len(subqueries),
        has_window_functions=has_window,
    )


def validate_read_only_sql(sql: str) -> ValidationResult:
    """Parse and validate that SQL is a single, pure read-only SELECT statement."""
    raw = (sql or "").strip()
    if not raw or not _strip_sql_comments(raw):
        return ValidationResult(
            is_valid=False,
            is_read_only=False,
            error_message="SQL input is empty or contains only comments.",
        )

    try:
        parsed_list = [node for node in sqlglot.parse(raw, read="postgres") if node is not None]
    except ParseError as exc:
        return ValidationResult(
            is_valid=False,
            is_read_only=False,
            error_message=f"SQL syntax error: {exc}",
        )
    except SqlglotError as exc:
        return ValidationResult(
            is_valid=False,
            is_read_only=False,
            error_message=f"Unable to parse PostgreSQL query: {exc}",
        )

    if not parsed_list:
        return ValidationResult(
            is_valid=False,
            is_read_only=False,
            error_message="No valid SQL statement found.",
        )

    if len(parsed_list) > 1:
        return ValidationResult(
            is_valid=False,
            is_read_only=False,
            rejected_operation="MULTIPLE_STATEMENTS",
            error_message=(
                f"Multiple SQL statements detected ({len(parsed_list)} statements). "
                "QueryTrellis allows only a single read-only SELECT statement per execution."
            ),
        )

    root = parsed_list[0]

    # Reject unparsed commands like GRANT, TRUNCATE, COPY, EXPLAIN, VACUUM, DO, CALL
    if isinstance(root, exp.Command):
        cmd_kw = _detect_command_keyword(raw)
        extra = ""
        if cmd_kw == "EXPLAIN":
            extra = " Use the 'Analyze Query' action instead of writing EXPLAIN directly."
        return ValidationResult(
            is_valid=True,
            is_read_only=False,
            rejected_operation=cmd_kw,
            error_message=(
                f"Statement '{cmd_kw}' is not permitted in read-only execution mode.{extra}"
            ),
        )

    # Walk entire AST for any write, DDL, locking, or SELECT INTO constructs (including inside CTEs!)
    for node in root.walk():
        if isinstance(node, DISALLOWED_AST_TYPES):
            op_name = type(node).__name__.upper()
            if isinstance(node, exp.Command):
                op_name = str(node.this).upper() if node.this else "COMMAND"
            elif isinstance(node, exp.Into):
                op_name = "SELECT INTO"
            elif isinstance(node, exp.Lock):
                op_name = "ROW LOCK (FOR UPDATE/SHARE)"
            return ValidationResult(
                is_valid=True,
                is_read_only=False,
                rejected_operation=op_name,
                error_message=(
                    f"Blocked non-read-only or restricted operation '{op_name}'. "
                    "QueryTrellis permits only read-only SELECT queries in safe mode."
                ),
            )

        if isinstance(node, (exp.Anonymous, exp.Func)):
            fname = (
                str(node.this).lower()
                if isinstance(node, exp.Anonymous)
                else (node.sql_name() or "").lower()
            )
            if fname in DANGEROUS_PG_FUNCTIONS:
                return ValidationResult(
                    is_valid=True,
                    is_read_only=False,
                    rejected_operation=f"FUNCTION:{fname}",
                    error_message=(
                        f"Blocked restricted PostgreSQL administrative/side-effect function '{fname}()'."
                    ),
                )

    if not isinstance(root, ALLOWED_ROOT_TYPES):
        op_name = type(root).__name__.upper()
        return ValidationResult(
            is_valid=True,
            is_read_only=False,
            rejected_operation=op_name,
            error_message=f"Statement type '{op_name}' is not allowed in read-only mode.",
        )

    # Also check SELECT ... FOR UPDATE/SHARE stored in Select.args["locks"]
    for sel in root.find_all(exp.Select):
        if sel.args.get("locks"):
            return ValidationResult(
                is_valid=True,
                is_read_only=False,
                rejected_operation="SELECT FOR UPDATE/SHARE",
                error_message="Locking clauses (FOR UPDATE / FOR SHARE) are not allowed in read-only analysis mode.",
            )

    clean_sql = root.sql(dialect="postgres")
    info = _extract_query_info(root, clean_sql)

    return ValidationResult(
        is_valid=True,
        is_read_only=True,
        clean_sql=clean_sql,
        ast=root,
        parsed_info=info,
    )
