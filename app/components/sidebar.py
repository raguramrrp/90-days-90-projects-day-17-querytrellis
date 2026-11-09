"""Fixed left sidebar navigation and workspace top context header."""
from __future__ import annotations

import html

import streamlit as st

from app.state import NAV_PAGES
from src.db.connection_manager import ConnectionManager


def render_sidebar() -> str:
    """Render fixed sidebar navigation and compact connection summary."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    status = conn_mgr.status

    with st.sidebar:
        st.markdown("### QueryTrellis")
        st.caption("PostgreSQL Query Performance Workbench")
        st.divider()

        current = st.session_state.get("qt_nav_page", "Overview")
        idx = NAV_PAGES.index(current) if current in NAV_PAGES else 0
        selected = st.radio(
            "Navigation",
            options=NAV_PAGES,
            index=idx,
            label_visibility="collapsed",
        )
        st.session_state["qt_nav_page"] = selected

        st.divider()
        st.caption("TARGET DATABASE")
        if status.connected:
            st.markdown(f"**Status:** Connected")
            st.markdown(f"**DB:** `{status.current_database}`")
            st.markdown(f"**Host:** `{status.config.host}:{status.config.port}`")
            st.markdown(f"**User:** `{status.current_user}`")
            # Quick DB switcher directly in sidebar when multiple DBs exist
            if len(status.available_databases) > 1:
                curr_idx = (
                    status.available_databases.index(status.current_database)
                    if status.current_database in status.available_databases
                    else 0
                )
                chosen_db = st.selectbox(
                    "Switch Database",
                    options=status.available_databases,
                    index=curr_idx,
                    key="qt_sidebar_db_switch",
                )
                if chosen_db != status.current_database:
                    new_status = conn_mgr.switch_database(chosen_db)
                    if new_status.connected:
                        conn_mgr.fetch_catalog(force_refresh=True)
                        st.rerun()
                    else:
                        st.error(new_status.error_message)
        else:
            st.markdown("**Status:** Disconnected")
            st.caption("Static SQL parsing & anti-pattern rules remain available. Connect PostgreSQL in Settings.")

        st.divider()
        st.caption("SAFE EXECUTION GUARDRAILS")
        st.text(
            f"Mode: READ ONLY\n"
            f"Timeout: {st.session_state['qt_timeout_ms']} ms\n"
            f"Max Rows: {st.session_state['qt_max_rows']}"
        )

    return selected


def render_page_header(title: str, subtitle: str) -> None:
    """Render a compact workstation header with sanitized live connection status."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    status = conn_mgr.status
    esc = html.escape

    if status.connected:
        ver_short = status.server_version.split(",")[0] if status.server_version else "PostgreSQL"
        conn_pill = (
            f"<span class='qt-pill qt-pill-connected'>CONNECTED: "
            f"{esc(status.current_database)} @ {esc(status.config.host)}:{status.config.port}</span>"
            f"<span class='qt-pill'>{esc(ver_short)}</span>"
        )
    else:
        conn_pill = (
            "<span class='qt-pill qt-pill-offline'>DISCONNECTED &mdash; Static AST Mode</span>"
        )

    guard_pill = (
        f"<span class='qt-pill'>READ-ONLY TX | "
        f"{st.session_state['qt_timeout_ms']} ms | "
        f"LIMIT {st.session_state['qt_max_rows']}</span>"
    )

    st.markdown(
        f"""
        <div class="qt-topbar">
          <div>
            <div class="qt-topbar-title">{esc(title)}</div>
            <div class="qt-topbar-sub">{esc(subtitle)}</div>
          </div>
          <div class="qt-status-bar">
            {conn_pill}
            {guard_pill}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
