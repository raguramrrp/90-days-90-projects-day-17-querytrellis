"""Interactive exercise validator comparing real DuckDB output against expected results."""
from __future__ import annotations

from typing import Any

from src.academy.curriculum import get_lesson_by_id
from src.academy.stage_tracer import _clean_val, create_lesson_duckdb


def _normalize_row(row: tuple[Any, ...]) -> tuple[Any, ...]:
    vals: list[Any] = []
    for v in row:
        cv = _clean_val(v)
        if isinstance(cv, float):
            cv = round(cv, 2)
        vals.append(cv)
    return tuple(vals)


def evaluate_academy_exercise(lesson_id: str, user_sql: str) -> dict[str, Any]:
    """Run user SQL & verified expected solution on isolated DuckDB copies and compare cleanly."""
    lesson = get_lesson_by_id(lesson_id)
    if lesson is None:
        return {"success": False, "passed": False, "feedback": f"Unknown lesson '{lesson_id}'."}

    raw = (user_sql or "").strip()
    if not raw:
        return {"success": False, "passed": False, "feedback": "Write a SQL solution before checking."}

    ex = lesson.exercise

    # Compute ground truth cleanly inside isolated DuckDB copy
    ref_con = create_lesson_duckdb()
    try:
        if ex.is_dml and ex.target_verify_table:
            ref_con.execute(ex.solution_sql)
            exp_cur = ref_con.execute(f"SELECT * FROM {ex.target_verify_table}")
        else:
            exp_cur = ref_con.execute(ex.solution_sql)
        exp_cols = [str(d[0]).lower() for d in (exp_cur.description or [])]
        exp_rows = [_normalize_row(r) for r in exp_cur.fetchall()]
    finally:
        ref_con.close()

    # Execute student's SQL in its own fresh isolated DuckDB copy
    usr_con = create_lesson_duckdb()
    try:
        if ex.is_dml and ex.target_verify_table:
            usr_con.execute(raw)
            act_cur = usr_con.execute(f"SELECT * FROM {ex.target_verify_table}")
        else:
            act_cur = usr_con.execute(raw)
        act_cols = [str(d[0]).lower() for d in (act_cur.description or [])]
        act_rows = [_normalize_row(r) for r in act_cur.fetchall()]
    except Exception as exc:
        return {
            "success": True,
            "passed": False,
            "feedback": f"SQL execution error: {exc}",
            "expected_columns": exp_cols,
            "expected_rows": [dict(zip(exp_cols, r)) for r in exp_rows],
            "actual_columns": [],
            "actual_rows": [],
        }
    finally:
        usr_con.close()

    expected_dicts = [dict(zip(exp_cols, r)) for r in exp_rows]
    actual_dicts = [dict(zip(act_cols, r)) for r in act_rows]

    if len(act_cols) != len(exp_cols):
        return {
            "success": True,
            "passed": False,
            "feedback": f"Expected {len(exp_cols)} column(s) ({', '.join(exp_cols)}), got {len(act_cols)} ({', '.join(act_cols)}).",
            "expected_columns": exp_cols,
            "expected_rows": expected_dicts,
            "actual_columns": act_cols,
            "actual_rows": actual_dicts,
        }

    if ex.order_sensitive:
        passed = (act_rows == exp_rows)
        feedback = (
            "Verified correct: columns, values, and sort order match the expected output."
            if passed
            else "Rows or ordering do not yet match expected output. Check ORDER BY direction and LIMIT."
        )
    else:
        passed = (sorted(act_rows, key=lambda r: [str(x) for x in r]) == sorted(exp_rows, key=lambda r: [str(x) for x in r]))
        feedback = (
            "Verified correct: all expected rows and metrics match!"
            if passed
            else f"Row set mismatch: expected {len(exp_rows)} row(s), got {len(act_rows)} row(s). Review your filter or grouping."
        )

    return {
        "success": True,
        "passed": passed,
        "feedback": feedback,
        "expected_columns": exp_cols,
        "expected_rows": expected_dicts,
        "actual_columns": act_cols,
        "actual_rows": actual_dicts,
    }
