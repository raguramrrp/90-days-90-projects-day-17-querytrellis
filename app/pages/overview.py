"""A. Overview Dashboard page."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components.sidebar import render_page_header
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore


def render_overview_page() -> None:
    render_page_header(
        "Overview Dashboard",
        "Database telemetry, local analysis history, detected patterns, and recent benchmark comparisons.",
    )

    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    status = conn_mgr.status
    stats = store.get_overview_stats()

    catalog = None
    if status.connected:
        try:
            catalog = conn_mgr.fetch_catalog()
        except Exception as exc:
            st.warning(f"Connected, but unable to inspect catalog metadata: {exc}")

    # KPI Row — strictly real metrics only
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Connection", "Connected" if status.connected else "Offline")
    k2.metric("Total Tables", f"{len(catalog.tables)}" if catalog else "Unavailable")
    k3.metric("Total Indexes", f"{catalog.total_indexes()}" if catalog else "Unavailable")
    k4.metric("Queries Analyzed", f"{stats['total_analyses']}")
    k5.metric(
        "Avg Observed Exec Time",
        f"{stats['avg_execution_ms']:.2f} ms" if stats["avg_execution_ms"] is not None else "No runs yet",
    )

    if status.connected:
        st.caption(
            f"Server: {status.server_version} | Active Database: `{status.current_database}` | "
            f"Schemas: {', '.join(status.available_schemas) or 'public'}"
        )
    else:
        st.info(
            "PostgreSQL is not currently connected. Open Settings to configure and connect to your "
            "PostgreSQL instance (or run `python scripts/setup_sample_db.py` to seed the e-commerce sample database)."
        )

    # Catalog Footprint Table
    if catalog and catalog.tables:
        st.subheader("Database Table & Index Footprint")
        tbl_rows = []
        for t in catalog.tables:
            tbl_rows.append(
                {
                    "Schema": t.schema_name,
                    "Table": t.table_name,
                    "Type": t.table_type,
                    "Est. Rows": t.estimated_rows,
                    "Indexes": len(t.indexes),
                    "Total Size (MB)": round(t.total_size_bytes / (1024 * 1024), 2),
                    "Seq Scans": t.seq_scan,
                    "Index Scans": t.idx_scan,
                }
            )
        st.dataframe(pd.DataFrame(tbl_rows), width="stretch", hide_index=True)

    col_left, col_right = st.columns([1.2, 1.0])

    with col_left:
        st.subheader("Recent Query Analyses")
        recent = stats["recent_analyses"]
        if not recent:
            st.info("No queries have been executed or analyzed yet. Open Query Editor to analyze your first query.")
        else:
            rec_df = pd.DataFrame(
                [
                    {
                        "ID": r["id"],
                        "Timestamp": r["created_at"],
                        "Database": r["database_name"],
                        "Mode": r["execution_mode"],
                        "Status": r["status"],
                        "PG Exec (ms)": r["pg_execution_ms"] if r["pg_execution_ms"] is not None else "-",
                        "Client (ms)": r["client_duration_ms"] if r["client_duration_ms"] is not None else "-",
                        "SQL Preview": (r["sql_text"] or "").replace("\n", " ")[:68],
                    }
                    for r in recent
                ]
            )
            st.dataframe(rec_df, width="stretch", hide_index=True)

    with col_right:
        st.subheader("Most Common Detected Anti-Patterns")
        common_issues = stats["common_issues"]
        if not common_issues:
            st.info("No anti-pattern findings recorded across analyzed queries yet.")
        else:
            issue_df = pd.DataFrame(common_issues[:8])
            fig = px.bar(
                issue_df,
                x="count",
                y="issue_name",
                orientation="h",
                color_discrete_sequence=["#0F766E"],
            )
            fig.update_layout(
                height=290,
                margin=dict(l=10, r=15, t=10, b=25),
                xaxis_title="Occurrences",
                yaxis_title="",
                yaxis=dict(autorange="reversed"),
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#F8FAFC",
                font=dict(color="#0F172A", size=11),
            )
            st.plotly_chart(fig, width="stretch")

    st.subheader("Recent Before & After Comparisons")
    comps = store.list_comparisons(limit=10)
    if not comps:
        st.info("No query comparisons saved yet. Compare two SQL versions in Benchmark Lab.")
    else:
        comp_rows = []
        for c in comps:
            cdata = c.get("comparison", {})
            comp_rows.append(
                {
                    "ID": c["id"],
                    "Timestamp": c["created_at"],
                    "Title": c["title"],
                    "Database": c["database_name"],
                    "Verdict": cdata.get("verdict", "-"),
                    "Baseline (ms)": cdata.get("baseline_time_ms", "-"),
                    "Optimized (ms)": cdata.get("optimized_time_ms", "-"),
                    "Change (%)": f"{cdata['pct_change']}%" if cdata.get("pct_change") is not None else "-",
                }
            )
        st.dataframe(pd.DataFrame(comp_rows), width="stretch", hide_index=True)
