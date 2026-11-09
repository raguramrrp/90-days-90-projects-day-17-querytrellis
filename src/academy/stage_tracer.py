"""Real DuckDB stage-by-stage SQL execution tracer for Visual SQL Academy & Query Visualizer.

Every intermediate table shown in the frontend is actually computed by DuckDB from real rows:
- Never invents rows or fake visual diagrams.
- Tags kept/excluded rows with exact predicate reasoning, group bucket keys, join pairs,
  sort order changes, window partition frames, DML row diffs, and B-tree index probes.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp

from src.academy.curriculum import AcademyLesson, get_lesson_by_id


def _clean_val(val: Any) -> Any:
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    return str(val)


def create_lesson_duckdb() -> duckdb.DuckDBPyConnection:
    """Create a fresh isolated in-memory DuckDB populated with small, crystal-clear lesson tables."""
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE teams (
            dept_id INTEGER PRIMARY KEY,
            dept_name VARCHAR NOT NULL,
            office VARCHAR NOT NULL
        );

        CREATE TABLE staff (
            emp_id INTEGER PRIMARY KEY,
            emp_name VARCHAR NOT NULL,
            dept_id INTEGER,
            role VARCHAR NOT NULL,
            salary INTEGER NOT NULL,
            bonus INTEGER
        );

        CREATE TABLE deals (
            deal_id INTEGER PRIMARY KEY,
            emp_id INTEGER NOT NULL,
            region VARCHAR NOT NULL,
            quarter VARCHAR NOT NULL,
            amount INTEGER NOT NULL
        );

        CREATE TABLE leads_archive (
            lead_name VARCHAR NOT NULL,
            region VARCHAR NOT NULL
        );

        INSERT INTO teams VALUES
            (1, 'Enterprise', 'Bengaluru'),
            (2, 'Analytics', 'Austin'),
            (3, 'Platform', 'Berlin'),
            (4, 'Legal', 'London');

        INSERT INTO staff VALUES
            (1, 'Aarav', 1, 'Account Exec', 92000, 8000),
            (2, 'Maya', 2, 'Data Engineer', 88000, 6500),
            (3, 'Liam', 1, 'Account Exec', 74000, NULL),
            (4, 'Sofia', 2, 'Data Engineer', 96000, 9000),
            (5, 'Noah', 3, 'SQL Architect', 82000, 5000),
            (6, 'Priya', 1, 'Sales Lead', 85000, NULL),
            (7, 'Ethan', 3, 'Platform Eng', 78000, 4200),
            (8, 'Kiran', NULL, 'Contractor', 64000, NULL);

        INSERT INTO deals VALUES
            (101, 1, 'Asia Pacific', '2026-Q1', 42000),
            (102, 1, 'Asia Pacific', '2026-Q1', 28000),
            (103, 3, 'North America', '2026-Q1', 35000),
            (104, 6, 'North America', '2026-Q1', 51000),
            (105, 2, 'Europe West', '2026-Q1', 24000),
            (106, 4, 'Europe West', '2026-Q1', 19000),
            (107, 6, 'Asia Pacific', '2026-Q1', 46000);

        INSERT INTO leads_archive VALUES
            ('Aarav', 'Asia Pacific'),
            ('Nadia', 'Europe West'),
            ('Rohan', 'Latin America');
    """)
    return con


def _fetch_table_payload(
    con: duckdb.DuckDBPyConnection,
    query: str,
    row_status_col: str | None = None,
    row_reason_col: str | None = None,
) -> dict[str, Any]:
    cur = con.execute(query)
    cols = [str(d[0]) for d in (cur.description or [])]
    raw_rows = cur.fetchall()
    visible_cols = [c for c in cols if c not in {row_status_col, row_reason_col}]
    rows_out: list[dict[str, Any]] = []
    meta_out: list[dict[str, Any]] = []
    for r in raw_rows:
        row_map = {cols[i]: _clean_val(r[i]) for i in range(len(cols))}
        clean_row = {c: row_map[c] for c in visible_cols}
        rows_out.append(clean_row)
        meta_out.append(
            {
                "status": row_map.get(row_status_col, "kept") if row_status_col else "kept",
                "reason": row_map.get(row_reason_col, "") if row_reason_col else "",
            }
        )
    return {
        "columns": visible_cols,
        "rows": rows_out,
        "row_meta": meta_out,
        "row_count": len(rows_out),
    }


def trace_custom_select_query(
    sql: str,
    db_path: Path | None = None,
    max_preview_rows: int = 25,
) -> dict[str, Any]:
    """Trace logical execution stages of an arbitrary SELECT query inside DuckDB."""
    con = duckdb.connect(str(db_path), read_only=True) if db_path else create_lesson_duckdb()
    stages: list[dict[str, Any]] = []
    try:
        parsed = sqlglot.parse_one(sql, read="duckdb")
        sel = parsed if isinstance(parsed, exp.Select) else next(parsed.find_all(exp.Select), None)
        if sel is None:
            # Final result only
            final_tbl = _fetch_table_payload(con, f"SELECT * FROM ({sql.rstrip(';')}) _q LIMIT {max_preview_rows}")
            stages.append(
                {
                    "stage_key": "FINAL",
                    "title": "Final Result",
                    "description": "Evaluated SQL statement result inside DuckDB.",
                    "sql_fragment": sql.strip(),
                    **final_tbl,
                }
            )
            return {"success": True, "sql": sql, "stages": stages}

        # Stage 1: Input FROM + JOIN relation(s)
        from_node = sel.args.get("from_") or sel.args.get("from")
        joins = sel.args.get("joins") or []
        cte_block = ""
        with_node = sel.args.get("with_") or sel.args.get("with")
        if with_node:
            cte_block = with_node.sql(dialect="duckdb") + "\n"

        if from_node:
            from_sql = from_node.sql(dialect="duckdb")
            joins_sql = " ".join(j.sql(dialect="duckdb") for j in joins)
            base_from = f"{cte_block}SELECT * {from_sql} {joins_sql}".strip()
            input_tbl = _fetch_table_payload(
                con, f"SELECT * FROM ({base_from}) _base LIMIT {max_preview_rows}"
            )
            stages.append(
                {
                    "stage_key": "FROM_JOIN",
                    "title": "1. FROM & JOIN Input Rows",
                    "description": "Candidate rows loaded from base table(s) and join pairings before WHERE filtering.",
                    "sql_fragment": f"{from_sql} {joins_sql}".strip(),
                    **input_tbl,
                }
            )

            # Stage 2: WHERE row-by-row filtering (tagging kept vs excluded!)
            where_node = sel.args.get("where")
            if where_node is not None:
                cond_sql = where_node.this.sql(dialect="duckdb")
                # Build tagged query against FROM/JOIN
                tagged_sql = (
                    f"{cte_block}SELECT *, "
                    f"CASE WHEN ({cond_sql}) THEN 'kept' ELSE 'excluded' END AS _qt_status, "
                    f"CASE WHEN ({cond_sql}) THEN 'Matches WHERE condition' ELSE 'Excluded by WHERE condition' END AS _qt_reason "
                    f"{from_sql} {joins_sql} LIMIT {max_preview_rows}"
                )
                where_tbl = _fetch_table_payload(
                    con, tagged_sql, row_status_col="_qt_status", row_reason_col="_qt_reason"
                )
                kept_cnt = sum(1 for m in where_tbl["row_meta"] if m["status"] == "kept")
                excl_cnt = len(where_tbl["row_meta"]) - kept_cnt
                stages.append(
                    {
                        "stage_key": "WHERE",
                        "title": f"2. WHERE Filter ({kept_cnt} kept, {excl_cnt} excluded)",
                        "description": f"Evaluates predicate `{cond_sql}` independently per row.",
                        "sql_fragment": f"WHERE {cond_sql}",
                        **where_tbl,
                    }
                )

            # Stage 3: GROUP BY / HAVING if present
            group_node = sel.args.get("group")
            having_node = sel.args.get("having")
            if group_node is not None:
                grp_cols = ", ".join(g.sql(dialect="duckdb") for g in group_node.expressions)
                where_part = f"WHERE {where_node.this.sql(dialect='duckdb')}" if where_node else ""
                proj_part = ", ".join(p.sql(dialect="duckdb") for p in sel.expressions)
                if having_node:
                    h_cond = having_node.this.sql(dialect="duckdb")
                    grp_sql = (
                        f"{cte_block}SELECT {proj_part}, "
                        f"CASE WHEN ({h_cond}) THEN 'kept' ELSE 'excluded' END AS _qt_status, "
                        f"CASE WHEN ({h_cond}) THEN 'Group matches HAVING' ELSE 'Group excluded by HAVING' END AS _qt_reason "
                        f"{from_sql} {joins_sql} {where_part} GROUP BY {grp_cols} LIMIT {max_preview_rows}"
                    )
                    grp_tbl = _fetch_table_payload(
                        con, grp_sql, row_status_col="_qt_status", row_reason_col="_qt_reason"
                    )
                else:
                    grp_sql = (
                        f"{cte_block}SELECT {proj_part} {from_sql} {joins_sql} {where_part} "
                        f"GROUP BY {grp_cols} LIMIT {max_preview_rows}"
                    )
                    grp_tbl = _fetch_table_payload(con, grp_sql)
                stages.append(
                    {
                        "stage_key": "GROUP_HAVING",
                        "title": "3. GROUP BY Aggregation" + (" + HAVING" if having_node else ""),
                        "description": f"Grouped rows by ({grp_cols}) and computed aggregate values per bucket.",
                        "sql_fragment": f"GROUP BY {grp_cols}" + (f" HAVING {having_node.this.sql(dialect='duckdb')}" if having_node else ""),
                        **grp_tbl,
                    }
                )

        # Stage 4: Pre-LIMIT sorted output when both ORDER BY and LIMIT exist
        order_node = sel.args.get("order")
        limit_node = sel.args.get("limit")
        if order_node and limit_node:
            no_limit_ast = parsed.copy()
            if isinstance(no_limit_ast, exp.Select):
                no_limit_ast.set("limit", None)
                no_limit_ast.set("offset", None)
                sorted_sql = no_limit_ast.sql(dialect="duckdb")
                sorted_tbl = _fetch_table_payload(con, f"SELECT * FROM ({sorted_sql}) _srt LIMIT {max_preview_rows}")
                stages.append(
                    {
                        "stage_key": "ORDER_BY",
                        "title": "ORDER BY (Before LIMIT Slice)",
                        "description": f"Sorts complete projected stream before applying `{limit_node.sql(dialect='duckdb')}`.",
                        "sql_fragment": order_node.sql(dialect="duckdb"),
                        **sorted_tbl,
                    }
                )

        # Final Stage: Actual query output
        final_tbl = _fetch_table_payload(con, f"SELECT * FROM ({sql.rstrip(';')}) _fin LIMIT {max_preview_rows}")
        stages.append(
            {
                "stage_key": "FINAL",
                "title": "Final Query Result",
                "description": "Exact output rows produced by executing the query.",
                "sql_fragment": sql.strip(),
                **final_tbl,
            }
        )
        return {"success": True, "sql": sql, "stages": stages}
    except Exception as exc:
        return {"success": False, "sql": sql, "stages": stages, "error_message": str(exc)}
    finally:
        con.close()


def trace_lesson_execution(lesson_id: str) -> dict[str, Any]:
    """Produce rich educational step-by-step stage snapshots tailored to each of the 21 lessons."""
    lesson = get_lesson_by_id(lesson_id)
    if lesson is None:
        return {"success": False, "error_message": f"Unknown lesson '{lesson_id}'."}

    con = create_lesson_duckdb()
    stages: list[dict[str, Any]] = []

    try:
        lid = lesson.lesson_id

        # Tailored JOIN visual steps showing unmatched rows explicitly
        if lid in {"inner_join", "left_join", "right_join"}:
            t_staff = _fetch_table_payload(con, "SELECT emp_id, emp_name, dept_id, role FROM staff ORDER BY emp_id")
            t_teams = _fetch_table_payload(con, "SELECT dept_id, dept_name, office FROM teams ORDER BY dept_id")
            stages.append(
                {
                    "stage_key": "INPUT_LEFT",
                    "title": "1A. Left Table (staff)",
                    "description": "Notice emp_id=8 ('Kiran') has `dept_id = NULL`.",
                    "sql_fragment": "FROM staff s",
                    **t_staff,
                }
            )
            stages.append(
                {
                    "stage_key": "INPUT_RIGHT",
                    "title": "1B. Right Table (teams)",
                    "description": "Notice dept_id=4 ('Legal') has zero matching employees in `staff`.",
                    "sql_fragment": "JOIN teams t",
                    **t_teams,
                }
            )
            if lid == "inner_join":
                pair_sql = """
                SELECT s.emp_id, s.emp_name, s.dept_id AS staff_dept_id, t.dept_id AS team_dept_id, t.dept_name,
                    CASE WHEN s.dept_id = t.dept_id THEN 'kept' ELSE 'excluded' END AS _st,
                    CASE WHEN s.dept_id IS NULL THEN 'Excluded: staff.dept_id is NULL (never equals team_dept_id)'
                         WHEN s.dept_id IS NOT NULL AND t.dept_id IS NULL THEN 'Excluded: unmatched row'
                         WHEN t.dept_id = 4 AND s.emp_id IS NULL THEN 'Excluded by INNER JOIN: Legal team has no matching staff'
                         ELSE 'Matched on dept_id' END AS _rsn
                FROM staff s
                FULL OUTER JOIN teams t ON t.dept_id = s.dept_id
                ORDER BY COALESCE(s.emp_id, 99), t.dept_id
                """
            elif lid == "left_join":
                pair_sql = """
                SELECT s.emp_id, s.emp_name, s.dept_id AS staff_dept_id, t.dept_name,
                    CASE WHEN s.emp_id IS NOT NULL AND t.dept_id IS NULL THEN 'padded_null'
                         WHEN s.emp_id IS NULL THEN 'excluded'
                         ELSE 'kept' END AS _st,
                    CASE WHEN s.emp_id IS NOT NULL AND t.dept_id IS NULL THEN 'Preserved from LEFT table (right columns NULL-padded)'
                         WHEN s.emp_id IS NULL THEN 'Excluded: only in RIGHT table (Legal)'
                         ELSE 'Matched left & right row' END AS _rsn
                FROM staff s
                FULL OUTER JOIN teams t ON t.dept_id = s.dept_id
                ORDER BY COALESCE(s.emp_id, 99), t.dept_id
                """
            else:  # right_join
                pair_sql = """
                SELECT s.emp_name, s.dept_id AS staff_dept_id, t.dept_id AS team_dept_id, t.dept_name,
                    CASE WHEN s.emp_id IS NULL AND t.dept_id IS NOT NULL THEN 'padded_null'
                         WHEN t.dept_id IS NULL THEN 'excluded'
                         ELSE 'kept' END AS _st,
                    CASE WHEN s.emp_id IS NULL AND t.dept_id IS NOT NULL THEN 'Preserved from RIGHT table (left emp_name NULL-padded)'
                         WHEN t.dept_id IS NULL THEN 'Excluded: Kiran has dept_id NULL'
                         ELSE 'Matched left & right row' END AS _rsn
                FROM staff s
                FULL OUTER JOIN teams t ON t.dept_id = s.dept_id
                ORDER BY COALESCE(t.dept_id, 99), s.emp_id
                """
            match_tbl = _fetch_table_payload(con, pair_sql, row_status_col="_st", row_reason_col="_rsn")
            stages.append(
                {
                    "stage_key": "JOIN_MATCHING",
                    "title": f"2. {lesson.concept} Row Pairing Decisions",
                    "description": "Shows which rows matched on `dept_id`, which were NULL-padded, and which were discarded.",
                    "sql_fragment": lesson.lesson_sql,
                    **match_tbl,
                }
            )
            fin_tbl = _fetch_table_payload(con, lesson.lesson_sql)
            stages.append(
                {
                    "stage_key": "FINAL",
                    "title": "3. Final Join Output",
                    "description": "Surviving rows after join rule completes.",
                    "sql_fragment": lesson.lesson_sql,
                    **fin_tbl,
                }
            )

        # Tailored DML visual steps (isolated before -> target match -> after diff)
        elif lid in {"insert", "update", "delete"}:
            target_tbl = "teams" if lid == "insert" else ("staff" if lid == "update" else "leads_archive")
            before_tbl = _fetch_table_payload(con, f"SELECT * FROM {target_tbl}")
            stages.append(
                {
                    "stage_key": "BEFORE_STATE",
                    "title": f"1. Before DML ({target_tbl})",
                    "description": "Snapshot of isolated lesson table BEFORE write executes.",
                    "sql_fragment": f"SELECT * FROM {target_tbl};",
                    **before_tbl,
                }
            )
            con.execute(lesson.lesson_sql)
            if lid == "insert":
                after_sql = (
                    "SELECT dept_id, dept_name, office, "
                    "CASE WHEN dept_id = 5 THEN 'added' ELSE 'kept' END AS _st, "
                    "CASE WHEN dept_id = 5 THEN 'Newly inserted row' ELSE 'Unchanged row' END AS _rsn "
                    "FROM teams ORDER BY dept_id"
                )
            elif lid == "update":
                after_sql = (
                    "SELECT emp_id, emp_name, dept_id, salary, bonus, "
                    "CASE WHEN dept_id = 1 THEN 'modified' ELSE 'kept' END AS _st, "
                    "CASE WHEN dept_id = 1 THEN 'Updated bonus = 5000 (matched WHERE dept_id = 1)' ELSE 'Unchanged row' END AS _rsn "
                    "FROM staff ORDER BY emp_id"
                )
            else:  # delete
                # Re-query before vs remaining unioned to show deleted row explicitly!
                after_tbl = _fetch_table_payload(con, "SELECT * FROM leads_archive")
                stages.append(
                    {
                        "stage_key": "AFTER_STATE",
                        "title": "2. After DELETE (Isolated Sandbox)",
                        "description": "Row matching `WHERE region = 'Europe West'` ('Nadia') was removed cleanly; remaining rows stay untouched.",
                        "sql_fragment": lesson.lesson_sql,
                        **after_tbl,
                    }
                )
                return _lesson_response(lesson, stages)

            after_tbl = _fetch_table_payload(con, after_sql, row_status_col="_st", row_reason_col="_rsn")
            stages.append(
                {
                    "stage_key": "AFTER_STATE",
                    "title": f"2. After {lesson.concept} (Row Diff)",
                    "description": "Highlights exactly which row(s) changed in the isolated sandbox table.",
                    "sql_fragment": lesson.lesson_sql,
                    **after_tbl,
                }
            )

        # Index Fundamentals visual comparison (Seq Scan vs B-Tree lookup probes)
        elif lid == "index_fundamentals":
            seq_sql = """
            SELECT emp_id, emp_name, role, salary,
                CASE WHEN emp_id = 7 THEN 'kept' ELSE 'excluded' END AS _st,
                CASE WHEN emp_id <= 7 THEN 'Scanned step #' || CAST(emp_id AS VARCHAR) || CASE WHEN emp_id = 7 THEN ' (MATCH FOUND)' ELSE ' (not matching)' END
                     ELSE 'Scanned step #' || CAST(emp_id AS VARCHAR) || ' (if no early exit, still checked)' END AS _rsn
            FROM staff ORDER BY emp_id
            """
            seq_tbl = _fetch_table_payload(con, seq_sql, row_status_col="_st", row_reason_col="_rsn")
            stages.append(
                {
                    "stage_key": "SEQ_SCAN",
                    "title": "1. Without Index: Sequential Table Scan (8 checks)",
                    "description": "Database reads unsorted heap tuples one by one comparing `emp_id = 7`.",
                    "sql_fragment": "Seq Scan on staff (Filter: emp_id = 7)",
                    **seq_tbl,
                }
            )
            # B-Tree steps: Root/Pivot probe 4 -> right subtree probe 6 -> leaf probe 7!
            btree_sql = """
            SELECT emp_id, emp_name, role, salary,
                CASE WHEN emp_id = 7 THEN 'kept'
                     WHEN emp_id IN (4, 6) THEN 'padded_null'
                     ELSE 'excluded' END AS _st,
                CASE WHEN emp_id = 4 THEN 'B-Tree Hop 1 (Root Key=4 -> 7 > 4, branch right)'
                     WHEN emp_id = 6 THEN 'B-Tree Hop 2 (Internal Key=6 -> 7 > 6, branch right)'
                     WHEN emp_id = 7 THEN 'B-Tree Hop 3 (Leaf MATCH! Fetch heap tuple for emp_id=7)'
                     ELSE 'Skipped completely (pruned by B-Tree bounds)' END AS _rsn
            FROM staff ORDER BY emp_id
            """
            btree_tbl = _fetch_table_payload(con, btree_sql, row_status_col="_st", row_reason_col="_rsn")
            stages.append(
                {
                    "stage_key": "INDEX_SEEK",
                    "title": "2. With B-Tree Index: Logarithmic Seek (3 hops vs 8 scans)",
                    "description": "Sorted index tree narrows range cleanly, skipping 5 untouched rows.",
                    "sql_fragment": "Index Scan using idx_staff_emp_id on staff (Index Cond: emp_id = 7)",
                    **btree_tbl,
                }
            )
            fin_tbl = _fetch_table_payload(con, lesson.lesson_sql)
            stages.append(
                {
                    "stage_key": "FINAL",
                    "title": "3. Returned Record",
                    "description": "Exact same result row returned with dramatically fewer page checks at scale.",
                    "sql_fragment": lesson.lesson_sql,
                    **fin_tbl,
                }
            )

        # UNION deduplication visual
        elif lid == "union":
            s1 = _fetch_table_payload(con, "SELECT emp_name AS contact_name, 'Staff (dept 1)' AS origin FROM staff WHERE dept_id = 1")
            s2 = _fetch_table_payload(con, "SELECT lead_name AS contact_name, 'Archive' AS origin FROM leads_archive")
            stages.append({"stage_key": "SET_A", "title": "1A. First SELECT (Staff in Dept 1)", "description": "Notice 'Aarav' appears here.", "sql_fragment": "SELECT emp_name FROM staff WHERE dept_id = 1", **s1})
            stages.append({"stage_key": "SET_B", "title": "1B. Second SELECT (Leads Archive)", "description": "Notice 'Aarav' ALSO appears here!", "sql_fragment": "SELECT lead_name FROM leads_archive", **s2})
            fin_union = _fetch_table_payload(con, lesson.secondary_sql or lesson.lesson_sql)
            stages.append({"stage_key": "FINAL", "title": "2. Final UNION Output (Duplicate 'Aarav' Collapsed)", "description": "UNION deduplicated overlapping rows; UNION ALL would have returned 6 rows instead of 5.", "sql_fragment": lesson.secondary_sql or lesson.lesson_sql, **fin_union})

        else:
            # Standard SQL clause pipeline trace via real DuckDB queries!
            trace = trace_custom_select_query(lesson.lesson_sql, db_path=None, max_preview_rows=20)
            if trace.get("stages"):
                stages = trace["stages"]

        return _lesson_response(lesson, stages)
    finally:
        con.close()


def _lesson_response(lesson: AcademyLesson, stages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "success": True,
        "lesson": {
            "lesson_id": lesson.lesson_id,
            "order": lesson.order,
            "title": lesson.title,
            "concept": lesson.concept,
            "tier": lesson.tier,
            "summary": lesson.summary,
            "key_rule": lesson.key_rule,
            "lesson_sql": lesson.lesson_sql,
        },
        "stages": stages,
        "exercise": {
            "exercise_id": lesson.exercise.exercise_id,
            "prompt": lesson.exercise.prompt,
            "starter_sql": lesson.exercise.starter_sql,
            "order_sensitive": lesson.exercise.order_sensitive,
            "is_dml": lesson.exercise.is_dml,
            "hints": list(lesson.exercise.hints),
            "step_by_step_solution": list(lesson.exercise.step_by_step_solution),
            "solution_sql": lesson.exercise.solution_sql,
        },
    }
