"""F. Query History page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.sidebar import render_page_header
from app.state import load_history_record_into_state
from src.db.metadata_store import MetadataStore


def render_query_history_page() -> None:
    render_page_header(
        "Query Analysis History",
        "Inspect previously executed and analyzed queries stored in the local QueryTrellis SQLite metadata store.",
    )

    store: MetadataStore = st.session_state["qt_store"]
    all_records = store.list_analyses(limit=250)

    if not all_records:
        st.info("No query history recorded yet. Validate, execute, or analyze a query in Query Editor.")
        return

    databases = ["All"] + sorted({r["database_name"] for r in all_records if r.get("database_name")})
    f1, f2, f3 = st.columns([1.0, 1.0, 2.0])
    db_filter = f1.selectbox("Database", options=databases)
    status_filter = f2.selectbox("Status", options=["All", "success", "rejected", "error"])
    search_txt = f3.text_input("Search SQL Text", placeholder="Filter by table, column, or keyword...")

    filtered = store.list_analyses(
        limit=200,
        database_filter=db_filter,
        status_filter=status_filter,
        search_text=search_txt,
    )

    if not filtered:
        st.warning("No history entries match your filters.")
        return

    df = pd.DataFrame(
        [
            {
                "ID": r["id"],
                "Timestamp": r["created_at"],
                "Database": r["database_name"],
                "Mode": r["execution_mode"],
                "Status": r["status"],
                "PG Exec (ms)": r["pg_execution_ms"] if r["pg_execution_ms"] is not None else "-",
                "Client (ms)": r["client_duration_ms"] if r["client_duration_ms"] is not None else "-",
                "Est Cost": r["total_cost"] if r["total_cost"] is not None else "-",
                "Issues": len(r.get("antipatterns_json") or []),
                "SQL Preview": (r["sql_text"] or "").replace("\n", " ")[:80],
            }
            for r in filtered
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Inspect or Reopen Historical Record")
    id_map = {f"#{r['id']} | {r['created_at']} | {r['status']} | {(r['sql_text'] or '').splitlines()[0][:55]}": r for r in filtered}
    chosen_key = st.selectbox("Select Analysis Record", options=list(id_map.keys()))
    rec = id_map[chosen_key]

    st.code(rec["sql_text"], language="sql")
    if rec.get("error_message"):
        st.error(f"Recorded Error: {rec['error_message']}")

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Open in Query Editor", type="primary", width="stretch"):
        load_history_record_into_state(rec)
        st.session_state["qt_pending_editor_sql"] = rec["sql_text"]
        st.session_state["qt_nav_page"] = "Query Editor"
        st.rerun()
    if b2.button("Open Explain Plan", width="stretch", disabled=not bool(rec.get("plan_json"))):
        load_history_record_into_state(rec)
        st.session_state["qt_nav_page"] = "Explain Plan"
        st.rerun()
    if b3.button("Open Recommendations", width="stretch"):
        load_history_record_into_state(rec)
        st.session_state["qt_nav_page"] = "Recommendations"
        st.rerun()
    if b4.button("Open in Reports", width="stretch"):
        load_history_record_into_state(rec)
        st.session_state["qt_nav_page"] = "Reports"
        st.rerun()
