"""Query Analysis History page with Date, Database, Status, and Mode filters."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
from typing import Any

import pandas as pd
import streamlit as st

from app.components.topbar import render_topbar
from app.components.ui_primitives import (
    TelemetryCardData,
    render_empty_state,
    render_error_state,
    render_section_header,
    render_sql_panel,
    render_telemetry_row,
)
from app.state import load_history_record_into_state, navigate_to
from src.db.metadata_store import MetadataStore


def _parse_utc_date(ts_str: str) -> str:
    return str(ts_str or "")[:10]


def _matches_date_filter(created_at: str, date_choice: str) -> bool:
    if date_choice == "All Dates":
        return True
    rec_date_str = _parse_utc_date(created_at)
    if not rec_date_str:
        return False
    today_utc = datetime.now(timezone.utc).date()
    try:
        rec_date = datetime.strptime(rec_date_str, "%Y-%m-%d").date()
    except ValueError:
        return True

    if date_choice == "Today (UTC)":
        return rec_date == today_utc
    if date_choice == "Last 7 Days":
        return rec_date >= (today_utc - timedelta(days=7))
    if date_choice == "Last 30 Days":
        return rec_date >= (today_utc - timedelta(days=30))
    return rec_date_str == date_choice


def render_query_history_page() -> None:
    """Render searchable, filterable SQLite query execution & analysis history."""
    store: MetadataStore = st.session_state["qt_store"]
    disp_limit = int(st.session_state.get("qt_history_limit", 200))
    all_records = store.list_analyses(limit=max(disp_limit, 250))

    render_topbar(
        "Query History",
        right_meta=f"{len(all_records)} record(s) loaded",
        action_label="Open Query Editor",
        action_icon="code",
        on_action=lambda: (navigate_to("Query Editor"), st.rerun()),
    )

    if not all_records:
        render_empty_state(
            "No Query History Recorded",
            "Validate, execute, or run EXPLAIN ANALYZE in Query Editor to populate searchable analysis history.",
            action_label="Open Query Editor",
            action_key="qt_hist_empty_cta",
            on_action=lambda: (navigate_to("Query Editor"), st.rerun()),
        )
        return

    databases = ["All"] + sorted({str(r["database_name"]) for r in all_records if r.get("database_name")})
    modes = ["All"] + sorted({str(r["execution_mode"]) for r in all_records if r.get("execution_mode")})
    unique_dates = sorted({_parse_utc_date(r.get("created_at", "")) for r in all_records if _parse_utc_date(r.get("created_at", ""))}, reverse=True)
    date_options = ["All Dates", "Today (UTC)", "Last 7 Days", "Last 30 Days"] + unique_dates[:20]

    f1, f2, f3, f4, f5 = st.columns([1.45, 0.95, 0.95, 0.85, 1.0])
    search_txt = f1.text_input(
        "Search SQL",
        placeholder="Filter by table, column, or SQL keyword...",
        key="qt_hist_search",
    )
    date_filter = f2.selectbox("Date (UTC)", options=date_options, key="qt_hist_date")
    db_filter = f3.selectbox("Database", options=databases, key="qt_hist_db")
    status_filter = f4.selectbox("Status", options=["All", "success", "rejected", "error"], key="qt_hist_status")
    mode_filter = f5.selectbox("Execution Mode", options=modes, key="qt_hist_mode")

    pre_filtered = store.list_analyses(
        limit=disp_limit,
        database_filter=db_filter,
        status_filter=status_filter,
        search_text=search_txt,
    )
    filtered: list[dict[str, Any]] = [
        r
        for r in pre_filtered
        if (mode_filter == "All" or r.get("execution_mode") == mode_filter)
        and _matches_date_filter(str(r.get("created_at", "")), date_filter)
    ]

    if not filtered:
        render_empty_state(
            "No History Entries Match Current Filters",
            "Relax the Search, Date, Database, Status, or Execution Mode filter criteria above.",
        )
        return

    df = pd.DataFrame(
        [
            {
                "ID": r["id"],
                "Timestamp": r["created_at"],
                "Database": r["database_name"],
                "Mode": r["execution_mode"],
                "Status": r["status"],
                "PG Exec (ms)": f"{r['pg_execution_ms']:.3f}" if r["pg_execution_ms"] is not None else "Unavailable",
                "Client (ms)": f"{r['client_duration_ms']:.3f}" if r["client_duration_ms"] is not None else "Unavailable",
                "Est Cost": f"{r['total_cost']:,.2f}" if r["total_cost"] is not None else "Unavailable",
                "Issues": len(r.get("antipatterns_json") or []),
                "SQL Preview": (r["sql_text"] or "").replace("\n", " ")[:78],
            }
            for r in filtered
        ]
    )

    render_section_header("Recorded Executions & Plans", f"Showing {len(filtered)} record(s) — click any row to inspect")
    tbl_evt = st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="qt_hist_table",
    )

    selected_rows = list(getattr(getattr(tbl_evt, "selection", None), "rows", []) or [])
    id_map = {
        f"#{r['id']} | {r['created_at']} | {r['execution_mode']} | {r['status']} | {(r['sql_text'] or '').splitlines()[0][:48]}": r
        for r in filtered
    }
    keys_list = list(id_map.keys())

    if selected_rows and 0 <= selected_rows[0] < len(filtered):
        rec = filtered[selected_rows[0]]
    else:
        chosen_key = st.selectbox("Inspect Analysis Record", options=keys_list, key="qt_hist_sel_rec")
        rec = id_map[chosen_key]

    render_section_header(f"Record Inspector — Analysis #{rec['id']}", f"{rec['execution_mode']} · {rec['status']}")

    render_telemetry_row(
        [
            TelemetryCardData(
                label="Record Status",
                value=str(rec["status"]).title(),
                subtext=str(rec["created_at"]),
                accent=True,
                tone="ok" if rec["status"] == "success" else ("warn" if rec["status"] == "rejected" else "err"),
            ),
            TelemetryCardData(
                label="PG Execution",
                value=f"{rec['pg_execution_ms']:.3f} ms" if rec["pg_execution_ms"] is not None else "Unavailable",
                subtext=f"Mode: {rec['execution_mode']}",
            ),
            TelemetryCardData(
                label="Client Duration",
                value=f"{rec['client_duration_ms']:.3f} ms" if rec["client_duration_ms"] is not None else "Unavailable",
                subtext=f"Database: {rec['database_name']}",
            ),
            TelemetryCardData(
                label="Estimated Cost",
                value=f"{rec['total_cost']:,.2f}" if rec["total_cost"] is not None else "Unavailable",
                subtext=f"Rows: {rec['rows_returned']:,}" if rec.get("rows_returned") is not None else "Rows: Unavailable",
            ),
            TelemetryCardData(
                label="Findings",
                value=f"{len(rec.get('antipatterns_json') or [])} AP / {len(rec.get('recommendations_json') or [])} Idx",
                subtext="Anti-patterns / Index hints",
            ),
        ]
    )

    render_sql_panel(
        rec.get("formatted_sql") or rec.get("sql_text", ""),
        copy_key=f"qt_hist_copy_{rec['id']}",
        title=f"Captured SQL Statement (Hash: {str(rec.get('sql_hash', ''))[:12]})",
    )

    if rec.get("error_message"):
        render_error_state("Recorded Error", rec["error_message"])

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Open in Query Editor", key="qt_hist_open_qe", type="primary", width="stretch"):
        load_history_record_into_state(rec)
        navigate_to("Query Editor")
        st.rerun()
    if b2.button(
        "Open Explain Plan",
        key="qt_hist_open_ep",
        width="stretch",
        disabled=not bool(rec.get("plan_json")),
    ):
        load_history_record_into_state(rec)
        navigate_to("Explain Plan")
        st.rerun()
    if b3.button("Open Recommendations", key="qt_hist_open_rec", width="stretch"):
        load_history_record_into_state(rec)
        navigate_to("Recommendations")
        st.rerun()
    if b4.button("Open in Reports", key="qt_hist_open_rep", width="stretch"):
        load_history_record_into_state(rec)
        navigate_to("Reports")
        st.rerun()
