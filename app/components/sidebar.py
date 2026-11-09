"""Fixed, collapsible left navigation sidebar for QueryTrellis."""
from __future__ import annotations

import html

import streamlit as st

from app.state import NAV_GROUPS, navigate_to
from src.db.connection_manager import ConnectionManager


def render_sidebar() -> str:
    """Render grouped workstation navigation, connection badge, and policy footer."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    status = conn_mgr.status
    current_page = st.session_state.get("qt_nav_page", "Overview")

    with st.sidebar:
        st.markdown(
            """
            <div class="qt-brand-wrap">
                <div class="qt-brand-title">QueryTrellis</div>
                <div class="qt-brand-sub">PostgreSQL Performance Workbench</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for group_title, group_key, items in NAV_GROUPS:
            st.markdown(
                f"<div class='qt-nav-heading'>{html.escape(group_title)}</div>",
                unsafe_allow_html=True,
            )
            with st.container(key=group_key):
                for item in items:
                    is_active = current_page == item.page
                    if st.button(
                        item.page,
                        key=f"qt_nav_btn_{item.page.lower().replace(' ', '_')}",
                        icon=f":material/{item.icon}:",
                        type="primary" if is_active else "secondary",
                        width="stretch",
                        help=item.subtitle,
                    ):
                        if not is_active:
                            navigate_to(item.page)
                            st.rerun()

        st.markdown("<div style='height: 0.4rem;'></div>", unsafe_allow_html=True)

        # Compact bottom connection summary card
        if status.connected:
            db_disp = html.escape(status.current_database)
            host_disp = html.escape(f"{status.config.host}:{status.config.port}")
            user_disp = html.escape(status.current_user or status.config.username)
            ver_short = html.escape(status.server_version.split(",")[0] if status.server_version else "PostgreSQL")
            st.markdown(
                f"""
                <div class="qt-sb-footer-card">
                    <div style="display:flex;align-items:center;justify-content:space-between;">
                        <span style="font-weight:600;color:var(--qt-text-primary);font-size:0.75rem;">
                            <span class="qt-dot qt-dot-ok"></span>Connected
                        </span>
                        <span style="font-size:0.68rem;color:var(--qt-text-muted);font-family:var(--qt-font-mono);">{ver_short}</span>
                    </div>
                    <div class="qt-sb-kv"><span>Database</span><span class="qt-sb-mono" title="{db_disp}">{db_disp}</span></div>
                    <div class="qt-sb-kv"><span>Endpoint</span><span class="qt-sb-mono" title="{host_disp}">{host_disp}</span></div>
                    <div class="qt-sb-kv"><span>Role</span><span class="qt-sb-mono" title="{user_disp}">{user_disp}</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if len(status.available_databases) > 1:
                curr_idx = (
                    status.available_databases.index(status.current_database)
                    if status.current_database in status.available_databases
                    else 0
                )
                chosen_db = st.selectbox(
                    "Active Database",
                    options=status.available_databases,
                    index=curr_idx,
                    key="qt_sidebar_db_switch",
                    label_visibility="collapsed",
                )
                if chosen_db != status.current_database:
                    new_status = conn_mgr.switch_database(chosen_db)
                    if new_status.connected:
                        conn_mgr.fetch_catalog(force_refresh=True)
                        st.toast(f"Switched database to {chosen_db}")
                        st.rerun()
                    else:
                        st.error(new_status.error_message)
        else:
            st.markdown(
                """
                <div class="qt-sb-footer-card">
                    <div style="font-weight:600;color:var(--qt-text-primary);font-size:0.75rem;">
                        <span class="qt-dot qt-dot-warn"></span>Disconnected
                    </div>
                    <div style="font-size:0.71rem;color:var(--qt-text-muted);margin-top:3px;">
                        Static AST parsing &amp; rules active. Connect PostgreSQL in Settings.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        timeout_ms = st.session_state.get("qt_timeout_ms", 5000)
        max_rows = st.session_state.get("qt_max_rows", 500)
        st.markdown(
            f"""
            <div class="qt-sb-footer-card" style="padding:0.45rem 0.65rem;">
                <div style="font-size:0.67rem;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:var(--qt-text-muted);">
                    Execution Policy
                </div>
                <div style="font-family:var(--qt-font-mono);font-size:0.71rem;color:var(--qt-text-secondary);margin-top:2px;">
                    READ-ONLY &middot; {timeout_ms} ms &middot; {max_rows} rows
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return st.session_state.get("qt_nav_page", "Overview")
