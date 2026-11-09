"""Rule-based PostgreSQL index recommendation engine.

Combines SQLGlot AST structures (WHERE filters, JOIN keys, ORDER BY, GROUP BY,
projected columns), PostgreSQL pg_catalog metadata (existing indexes, table sizes),
and optional EXPLAIN plan evidence.

Safety guarantee:
- Recommendations are strictly advisory.
- QueryTrellis NEVER executes CREATE INDEX statements automatically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.db.connection_manager import DatabaseCatalog, IndexMetadata, TableMetadata
from src.explain.plan_parser import ParsedExplainPlan
from src.sql_analysis.parser_validator import ParsedQueryInfo, ValidationResult

MIN_INDEX_TABLE_ROWS = 1000
LOW_CARDINALITY_PARTIAL_VALUES = frozenset(
    {
        "pending",
        "failed",
        "cancelled",
        "returned",
        "delayed",
        "refunded",
        "false",
        "true",
    }
)


@dataclass(slots=True)
class IndexRecommendation:
    """Single advisory PostgreSQL index recommendation with full trade-off rationale."""

    rec_id: str
    table_name: str
    columns: list[str]
    include_columns: list[str]
    partial_predicate: str | None
    index_type: str  # "Single-Column B-tree" | "Composite B-tree" | "Covering (INCLUDE)" | "Partial B-tree"
    suggested_sql: str
    related_condition: str
    why_it_helps: str
    existing_index_status: str
    write_and_storage_overhead: str
    when_not_helpful: str
    confidence: str  # "High" | "Medium" | "Low"
    evidence_sources: list[str] = field(default_factory=list)


def _safe_ident(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip().lower())
    return cleaned.strip("_") or "col"


def _find_covering_existing_index(
    table_meta: TableMetadata | None, desired_prefix: list[str]
) -> IndexMetadata | None:
    """Return an existing index whose leading key columns cover ``desired_prefix``."""
    if table_meta is None or not desired_prefix:
        return None
    desired_low = [c.lower() for c in desired_prefix]
    for idx in table_meta.indexes:
        if idx.predicate is not None:
            continue  # Partial index does not generally cover unfiltered queries
        idx_keys = [k.lower() for k in idx.key_columns]
        if len(idx_keys) >= len(desired_low) and idx_keys[: len(desired_low)] == desired_low:
            return idx
    return None


def _resolve_table(alias_or_name: str | None, info: ParsedQueryInfo) -> str | None:
    if alias_or_name:
        return info.alias_to_table.get(alias_or_name.lower(), alias_or_name.lower())
    if len(info.tables) == 1:
        return info.tables[0].table.lower()
    return None


def recommend_indexes(
    validation: ValidationResult,
    catalog: DatabaseCatalog | None = None,
    plan: ParsedExplainPlan | None = None,
) -> list[IndexRecommendation]:
    """Generate non-redundant, evidence-backed PostgreSQL index recommendations."""
    if not validation.is_valid or not validation.is_read_only or validation.parsed_info is None:
        return []

    info = validation.parsed_info
    recommendations: list[IndexRecommendation] = []
    seen_signatures: set[tuple[str, tuple[str, ...], tuple[str, ...], str | None]] = set()

    # Track plan Seq Scans with Filters or Sorts for evidence enrichment
    seq_scan_tables: set[str] = set()
    has_sort_or_limit = bool(info.order_by_cols)
    if plan is not None:
        for n in plan.all_nodes:
            if n.node_type == "Seq Scan" and n.relation_name and n.filter_cond:
                seq_scan_tables.add(n.relation_name.lower())
            if n.node_type == "Sort":
                has_sort_or_limit = True

    # Group per-table filter predicates (sargable only!) and join keys
    eq_filters: dict[str, list[tuple[str, str, str | None]]] = {}  # tbl -> [(col, raw_sql, lit_val)]
    range_filters: dict[str, list[tuple[str, str]]] = {}  # tbl -> [(col, raw_sql)]
    join_keys: dict[str, list[tuple[str, str]]] = {}  # tbl -> [(col, raw_sql)]

    for pred in info.predicates:
        if pred.location != "WHERE" or not pred.column:
            continue
        # Skip non-sargable function-wrapped columns or leading wildcard LIKE
        if pred.is_function_wrapped or pred.has_leading_wildcard:
            continue
        tbl = _resolve_table(pred.table_or_alias, info)
        if not tbl:
            continue

        if pred.operator in ("=", "IN") and not pred.is_in_or_branch:
            eq_filters.setdefault(tbl, []).append((pred.column.lower(), pred.raw_sql, pred.literal_value))
        elif pred.operator in (">", ">=", "<", "<=", "BETWEEN", "LIKE", "ILIKE") and not pred.is_in_or_branch:
            range_filters.setdefault(tbl, []).append((pred.column.lower(), pred.raw_sql))

    for j in info.joins:
        for lt, lc, rt, rc in j.column_pairs:
            lt_resolved = _resolve_table(lt, info)
            rt_resolved = _resolve_table(rt, info)
            if lt_resolved and lc:
                join_keys.setdefault(lt_resolved, []).append((lc.lower(), j.on_raw_sql))
            if rt_resolved and rc:
                join_keys.setdefault(rt_resolved, []).append((rc.lower(), j.on_raw_sql))

    # Collect per-table ORDER BY / GROUP BY columns
    order_cols_by_tbl: dict[str, list[str]] = {}
    for tbl_alias, col, _dir, in_sub in info.order_by_cols:
        if in_sub:
            continue
        tbl = _resolve_table(tbl_alias, info)
        if tbl and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col):
            order_cols_by_tbl.setdefault(tbl, []).append(col.lower())

    group_cols_by_tbl: dict[str, list[str]] = {}
    for tbl_alias, col in info.group_by_cols:
        tbl = _resolve_table(tbl_alias, info)
        if tbl and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col):
            group_cols_by_tbl.setdefault(tbl, []).append(col.lower())

    # Collect per-table projected columns (for potential covering INCLUDE index)
    projected_by_tbl: dict[str, set[str]] = {}
    if not info.select_star_fragments:
        for tbl_alias, col in info.select_columns:
            tbl = _resolve_table(tbl_alias, info)
            if tbl and col:
                projected_by_tbl.setdefault(tbl, set()).add(col.lower())

    candidate_tables = sorted(
        set(eq_filters.keys()) | set(range_filters.keys()) | set(join_keys.keys())
    )

    rec_counter = 1
    for tbl in candidate_tables:
        tmeta = catalog.find_table(tbl) if catalog else None
        if tmeta and tmeta.table_type == "VIEW":
            continue
        if tmeta and tmeta.estimated_rows < MIN_INDEX_TABLE_ROWS:
            # Skip tiny lookup tables unless there's an explicit high-loop nested join
            continue

        eq_list = eq_filters.get(tbl, [])
        rng_list = range_filters.get(tbl, [])
        jn_list = join_keys.get(tbl, [])
        ord_list = order_cols_by_tbl.get(tbl, [])
        grp_list = group_cols_by_tbl.get(tbl, [])

        # Deduplicate preserving order
        eq_cols = list(dict.fromkeys([c for c, _, _ in eq_list]))
        rng_cols = list(dict.fromkeys([c for c, _ in rng_list if c not in eq_cols]))
        jn_cols = list(dict.fromkeys([c for c, _ in jn_list if c not in eq_cols and c not in rng_cols]))

        evidence: list[str] = ["AST Predicate/Join Analysis"]
        if tmeta:
            evidence.append(f"Catalog Stats (~{tmeta.estimated_rows:,} est. rows)")
        if tbl in seq_scan_tables:
            evidence.append("EXPLAIN Seq Scan + Filter")

        # ------------------------------------------------------------------
        # A. Composite / ESR Index (Equality cols -> Range / Order / Group)
        # ------------------------------------------------------------------
        composite_cols: list[str] = []
        if len(eq_cols) >= 2:
            composite_cols = eq_cols[:3]
        elif eq_cols and rng_cols:
            composite_cols = eq_cols[:2] + [rng_cols[0]]
        elif eq_cols and ord_list and ord_list[0] not in eq_cols:
            composite_cols = eq_cols[:2] + [ord_list[0]]
        elif eq_cols and grp_list and grp_list[0] not in eq_cols:
            composite_cols = eq_cols[:2] + [grp_list[0]]

        if len(composite_cols) >= 2:
            existing = _find_covering_existing_index(tmeta, composite_cols)
            if existing is None:
                sig = (tbl, tuple(composite_cols), (), None)
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    idx_name = f"idx_{_safe_ident(tbl)}_{'_'.join(_safe_ident(c) for c in composite_cols)}"
                    ddl = f"CREATE INDEX {idx_name} ON {tbl}({', '.join(composite_cols)});"
                    conds = [r for _, r, _ in eq_list[:2]] + [r for _, r in rng_list[:1]]
                    if ord_list:
                        conds.append(f"ORDER BY {ord_list[0]}")
                    partial_covered = _find_covering_existing_index(tmeta, composite_cols[:1])
                    existing_note = (
                        f"Leading column '{composite_cols[0]}' is indexed by '{partial_covered.index_name}', "
                        f"but no composite index covers ({', '.join(composite_cols)})."
                        if partial_covered
                        else f"No existing index on '{tbl}' starts with ({', '.join(composite_cols)})."
                    )
                    recommendations.append(
                        IndexRecommendation(
                            rec_id=f"IDX{rec_counter:03d}",
                            table_name=tbl,
                            columns=composite_cols,
                            include_columns=[],
                            partial_predicate=None,
                            index_type="Composite B-tree",
                            suggested_sql=ddl,
                            related_condition="; ".join(conds) or f"Filters/sorting on {tbl}",
                            why_it_helps=(
                                "Follows the Equality-Sort-Range (ESR) B-tree ordering rule: equality keys narrow "
                                "directly to a contiguous slice while trailing range/sort columns avoid extra filtering or Sort steps."
                            ),
                            existing_index_status=existing_note,
                            write_and_storage_overhead=(
                                "Adds B-tree maintenance cost on INSERT and on UPDATEs modifying any indexed column; "
                                "wider keys consume slightly more disk/buffer space than single-column indexes."
                            ),
                            when_not_helpful=(
                                "Ineffective if the leading equality column has very low selectivity (matching >25% of rows) "
                                "or if queries omit the leading column."
                            ),
                            confidence="High" if (tbl in seq_scan_tables or has_sort_or_limit) else "Medium",
                            evidence_sources=list(evidence),
                        )
                    )
                    rec_counter += 1

        # ------------------------------------------------------------------
        # B. Partial Index (when a low-cardinality constant flag/status pairs with another key)
        # ------------------------------------------------------------------
        low_card_eq = [
            (c, raw, lit)
            for c, raw, lit in eq_list
            if lit is not None and lit.lower() in LOW_CARDINALITY_PARTIAL_VALUES
        ]
        other_keys = [c for c in (eq_cols + rng_cols + ord_list) if all(c != lc[0] for lc in low_card_eq)]
        if low_card_eq and other_keys:
            flag_col, flag_raw, flag_lit = low_card_eq[0]
            target_col = other_keys[0]
            lit_sql = flag_lit if flag_lit.lower() in ("true", "false") else f"'{flag_lit}'"
            pred_sql = f"{flag_col} = {lit_sql}"
            sig = (tbl, (target_col,), (), pred_sql)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                idx_name = f"idx_{_safe_ident(tbl)}_{_safe_ident(target_col)}_{_safe_ident(flag_lit)}"
                ddl = f"CREATE INDEX {idx_name} ON {tbl}({target_col}) WHERE {pred_sql};"
                recommendations.append(
                    IndexRecommendation(
                        rec_id=f"IDX{rec_counter:03d}",
                        table_name=tbl,
                        columns=[target_col],
                        include_columns=[],
                        partial_predicate=pred_sql,
                        index_type="Partial B-tree",
                        suggested_sql=ddl,
                        related_condition=f"{flag_raw} combined with '{target_col}'",
                        why_it_helps=(
                            f"A partial index indexes only rows matching `WHERE {pred_sql}`, making the index dramatically "
                            "smaller, warmer in shared buffers, and faster to traverse for targeted operational queries."
                        ),
                        existing_index_status="Checked catalog; partial index avoids bloating full-table indexes.",
                        write_and_storage_overhead=(
                            "Lower write and storage overhead than a full-table index because rows outside the WHERE predicate are excluded."
                        ),
                        when_not_helpful=(
                            f"PostgreSQL can only use this index when queries explicitly include `{pred_sql}` (and if `{flag_lit}` actually represents a minor subset of rows)."
                        ),
                        confidence="Medium",
                        evidence_sources=list(evidence),
                    )
                )
                rec_counter += 1

        # ------------------------------------------------------------------
        # C. Single-Column & Covering (INCLUDE) Recommendations
        # ------------------------------------------------------------------
        single_candidates: list[tuple[str, str]] = []
        for col, raw, _ in eq_list:
            single_candidates.append((col, raw))
        for col, raw in jn_list:
            single_candidates.append((col, f"JOIN ON {raw}"))
        for col, raw in rng_list:
            single_candidates.append((col, raw))

        seen_single_cols: set[str] = set()
        for col, rel_cond in single_candidates:
            if col in seen_single_cols:
                continue
            seen_single_cols.add(col)

            existing = _find_covering_existing_index(tmeta, [col])
            if existing is not None:
                continue

            # Check if a covering index (INCLUDE) makes sense for narrow explicit projections
            proj = sorted(projected_by_tbl.get(tbl, set()) - {col})
            if proj and len(proj) <= 3 and len(info.tables) <= 2 and col in eq_cols:
                inc_cols = proj
                sig = (tbl, (col,), tuple(inc_cols), None)
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    idx_name = f"idx_{_safe_ident(tbl)}_{_safe_ident(col)}_cov"
                    ddl = f"CREATE INDEX {idx_name} ON {tbl}({col}) INCLUDE ({', '.join(inc_cols)});"
                    recommendations.append(
                        IndexRecommendation(
                            rec_id=f"IDX{rec_counter:03d}",
                            table_name=tbl,
                            columns=[col],
                            include_columns=inc_cols,
                            partial_predicate=None,
                            index_type="Covering (INCLUDE)",
                            suggested_sql=ddl,
                            related_condition=rel_cond,
                            why_it_helps=(
                                f"Includes projected columns ({', '.join(inc_cols)}) as non-key leaf payloads, enabling "
                                "an Index-Only Scan without visiting the main heap table (once visibility map pages are clean)."
                            ),
                            existing_index_status=f"No existing index on '{tbl}' has '{col}' as leading key.",
                            write_and_storage_overhead=(
                                "Larger index leaf pages than a plain single-column index; updates to INCLUDE columns also update the index."
                            ),
                            when_not_helpful=(
                                "If the table receives heavy UPDATE traffic on the INCLUDE columns, or if queries frequently change projected columns."
                            ),
                            confidence="Medium",
                            evidence_sources=list(evidence),
                        )
                    )
                    rec_counter += 1

            # Standard single-column B-tree recommendation
            sig = (tbl, (col,), (), None)
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)
            idx_name = f"idx_{_safe_ident(tbl)}_{_safe_ident(col)}"
            ddl = f"CREATE INDEX {idx_name} ON {tbl}({col});"
            recommendations.append(
                IndexRecommendation(
                    rec_id=f"IDX{rec_counter:03d}",
                    table_name=tbl,
                    columns=[col],
                    include_columns=[],
                    partial_predicate=None,
                    index_type="Single-Column B-tree",
                    suggested_sql=ddl,
                    related_condition=rel_cond,
                    why_it_helps=(
                        f"Allows PostgreSQL to jump directly to matching '{tbl}.{col}' entries via Index Scan / Bitmap Index Scan "
                        "instead of scanning the entire table sequentially."
                    ),
                    existing_index_status=f"No existing index on '{tbl}' leads with '{col}'.",
                    write_and_storage_overhead=(
                        f"Increases INSERT/DELETE time slightly and updates on '{col}'; adds B-tree disk footprint."
                    ),
                    when_not_helpful=(
                        "Not beneficial if the query returns a large fraction (>20–30%) of table rows, if the table is small, "
                        "or if predicates wrap the column in non-sargable functions."
                    ),
                    confidence="High" if (tbl in seq_scan_tables or col in [c for c, _ in jn_list]) else "Medium",
                    evidence_sources=list(evidence),
                )
            )
            rec_counter += 1

    return recommendations
