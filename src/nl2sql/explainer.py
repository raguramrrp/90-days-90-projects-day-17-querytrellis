"""AST-driven SQL schema verifier, clause-by-clause explainer, and sample output structure helper."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlglot import exp

from src.context.models import DatabaseContextSnapshot
from src.dialects.sqlglot_engine import parse_sql_ast, to_sqlglot_read_write


@dataclass(slots=True)
class SchemaVerificationResult:
    """Checks parsed SQL identifiers strictly against active DatabaseContextSnapshot."""

    is_valid_syntax: bool
    schema_verified: bool
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    unknown_tables: list[str] = field(default_factory=list)
    unknown_columns: list[str] = field(default_factory=list)
    error_message: str = ""


def verify_sql_against_schema(
    sql: str,
    context: DatabaseContextSnapshot,
    dialect: str | None = None,
) -> SchemaVerificationResult:
    """Confirm SQL parses cleanly and every referenced table/column exists in active schema."""
    d = dialect or context.dialect
    parsed = parse_sql_ast(sql, d)
    if not parsed.is_valid or parsed.root is None:
        return SchemaVerificationResult(
            is_valid_syntax=False,
            schema_verified=False,
            error_message=parsed.error_message,
        )

    root = parsed.root
    cte_names = {c.alias_or_name.lower() for c in root.find_all(exp.CTE) if c.alias_or_name}
    sub_aliases: set[str] = set()
    for sub in root.find_all(exp.Subquery):
        if sub.alias:
            sub_aliases.add(sub.alias.lower())

    alias_to_table: dict[str, str] = {}
    tables_used: list[str] = []
    unknown_tables: list[str] = []

    for tbl_node in root.find_all(exp.Table):
        tname = tbl_node.name
        if not tname or tname.lower() in cte_names or tname.lower() in sub_aliases:
            continue
        tschema = context.find_table(tname)
        if tschema is None:
            if tname not in unknown_tables:
                unknown_tables.append(tname)
        else:
            if tschema.name not in tables_used:
                tables_used.append(tschema.name)
            alias_to_table[tname.lower()] = tschema.name
            if tbl_node.alias:
                alias_to_table[tbl_node.alias.lower()] = tschema.name

    columns_used: list[str] = []
    unknown_columns: list[str] = []
    select_aliases: set[str] = set()
    for al in root.find_all(exp.Alias):
        if al.alias:
            select_aliases.add(al.alias.lower())

    for col_node in root.find_all(exp.Column):
        cname = col_node.name
        if not cname or cname == "*":
            continue
        qualifier = (col_node.table or "").lower()
        if qualifier in cte_names or qualifier in sub_aliases:
            columns_used.append(f"{col_node.table}.{cname}")
            continue
        if qualifier and qualifier in alias_to_table:
            real_tbl = context.find_table(alias_to_table[qualifier])
            if real_tbl and real_tbl.get_column(cname) is None:
                unknown_columns.append(f"{col_node.table}.{cname}")
            else:
                columns_used.append(f"{alias_to_table[qualifier]}.{cname}")
        elif qualifier and qualifier not in alias_to_table:
            unknown_columns.append(f"{col_node.table}.{cname}")
        else:
            if cname.lower() in select_aliases:
                continue
            # Unqualified column: check referenced tables in query
            matched = False
            for tname in tables_used:
                ts = context.find_table(tname)
                if ts and ts.get_column(cname) is not None:
                    matched = True
                    columns_used.append(f"{tname}.{cname}")
                    break
            if not matched and tables_used and not cte_names:
                unknown_columns.append(cname)

    columns_used = list(dict.fromkeys(columns_used))
    schema_verified = (len(unknown_tables) == 0 and len(unknown_columns) == 0)
    return SchemaVerificationResult(
        is_valid_syntax=True,
        schema_verified=schema_verified,
        tables_used=tables_used,
        columns_used=columns_used,
        unknown_tables=unknown_tables,
        unknown_columns=unknown_columns,
    )


def explain_sql_query(
    sql: str,
    context: DatabaseContextSnapshot | None = None,
    dialect: str = "postgresql",
) -> dict[str, Any]:
    """Generate an AST-accurate plain-English explanation + illustrative projection columns."""
    parsed = parse_sql_ast(sql, dialect)
    if not parsed.is_valid or parsed.root is None:
        return {
            "valid": False,
            "summary": f"Cannot explain query due to syntax error: {parsed.error_message}",
            "steps": [],
            "clauses": [],
            "illustrative_columns": [],
        }

    root = parsed.root
    sg = to_sqlglot_read_write(dialect)
    steps: list[dict[str, str]] = []

    ctes = list(root.find_all(exp.CTE))
    if ctes:
        names = ", ".join(c.alias_or_name for c in ctes if c.alias_or_name)
        steps.append(
            {
                "clause": "WITH (CTEs)",
                "detail": f"Computes reusable intermediate result set(s): {names}.",
            }
        )

    outer_sel = root if isinstance(root, exp.Select) else next(root.find_all(exp.Select), None)
    if outer_sel is not None:
        from_node = outer_sel.args.get("from_") or outer_sel.args.get("from")
        if from_node:
            steps.append(
                {
                    "clause": "FROM",
                    "detail": f"Reads base rows from {from_node.sql(dialect=sg).replace('FROM ', '')}.",
                }
            )
        joins = outer_sel.args.get("joins") or []
        for j in joins:
            steps.append(
                {
                    "clause": f"{(j.side + ' ') if j.side else ''}JOIN",
                    "detail": f"Combines rows via: {j.sql(dialect=sg)}.",
                }
            )
        where_node = outer_sel.args.get("where")
        if where_node:
            steps.append(
                {
                    "clause": "WHERE",
                    "detail": f"Filters row candidates keeping records matching: {where_node.this.sql(dialect=sg)}.",
                }
            )
        group_node = outer_sel.args.get("group")
        if group_node:
            grp_keys = ", ".join(g.sql(dialect=sg) for g in group_node.expressions)
            steps.append(
                {
                    "clause": "GROUP BY",
                    "detail": f"Buckets filtered rows by ({grp_keys}) and evaluates aggregate functions per group.",
                }
            )
        having_node = outer_sel.args.get("having")
        if having_node:
            steps.append(
                {
                    "clause": "HAVING",
                    "detail": f"Filters aggregated groups matching: {having_node.this.sql(dialect=sg)}.",
                }
            )
        if any(True for _ in outer_sel.find_all(exp.Window)):
            steps.append(
                {
                    "clause": "WINDOW (OVER)",
                    "detail": "Evaluates analytical ranking, lag, or running total calculations across ordered partitions without collapsing rows.",
                }
            )
        distinct_flag = outer_sel.args.get("distinct") is not None
        steps.append(
            {
                "clause": "SELECT" + (" DISTINCT" if distinct_flag else ""),
                "detail": (
                    f"Projects {len(outer_sel.expressions)} output expression(s)"
                    + (" and removes duplicate rows." if distinct_flag else ".")
                ),
            }
        )
        order_node = outer_sel.args.get("order")
        if order_node:
            steps.append(
                {
                    "clause": "ORDER BY",
                    "detail": f"Sorts output by {order_node.sql(dialect=sg).replace('ORDER BY ', '')}.",
                }
            )
        limit_node = outer_sel.args.get("limit")
        if limit_node:
            steps.append(
                {
                    "clause": "LIMIT / TOP",
                    "detail": f"Caps final returned rows: {limit_node.sql(dialect=sg)}.",
                }
            )

        # Build honest illustrative schema projection (columns & inferred types ONLY, never fake rows!)
        illus_cols: list[dict[str, str]] = []
        for proj in outer_sel.expressions:
            col_name = proj.alias_or_name or proj.sql(dialect=sg)
            col_type = "expression"
            if context is not None and isinstance(proj, exp.Column) and proj.name != "*":
                for t in context.tables:
                    cdef = t.get_column(proj.name)
                    if cdef:
                        col_type = cdef.data_type
                        break
            illus_cols.append({"name": col_name, "type": col_type})
    else:
        illus_cols = []
        steps.append(
            {
                "clause": type(root).__name__.upper(),
                "detail": f"Executes {type(root).__name__.upper()} set/statement structure.",
            }
        )

    verification = (
        verify_sql_against_schema(sql, context, dialect)
        if context is not None
        else None
    )

    summary = (
        f"This {dialect.upper()} query evaluates {len(steps)} logical stage(s): "
        + " -> ".join(s["clause"] for s in steps)
        + "."
    )

    return {
        "valid": True,
        "summary": summary,
        "steps": steps,
        "tables_used": verification.tables_used if verification else [],
        "columns_used": verification.columns_used if verification else [],
        "schema_verified": verification.schema_verified if verification else True,
        "unknown_tables": verification.unknown_tables if verification else [],
        "unknown_columns": verification.unknown_columns if verification else [],
        "illustrative_structure": {
            "is_illustrative_only": True,
            "notice": "Illustrative projection structure only — click 'Show Sample Output' to query real data from the active database.",
            "columns": illus_cols,
        },
    }
