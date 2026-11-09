"""Compact workstation top application bar for QueryTrellis."""
from __future__ import annotations

import html
from typing import Callable

import streamlit as st

from app.state import NAV_ITEMS_BY_PAGE, navigate_to
from app.theme import get_active_theme, set_active_theme
from src.db.connection_manager import ConnectionManager


def render_topbar(
    page_name: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    right_meta: str | None = None,
    action_label: str | None = None,
    action_icon: str | None = None,
    on_action: Callable[[], None] | None = None,
    show_disconnected_banner: bool = True,
) -> None:
    """Render compact breadcrumb bar, live DB badge, connection button, and Dark/Light theme toggle."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    status = conn_mgr.status
    theme = get_active_theme()
    nav_item = NAV_ITEMS_BY_PAGE.get(page_name)

    resolved_title = title or (nav_item.page if nav_item else page_name)
    resolved_sub = subtitle or (nav_item.subtitle if nav_item else "")
    group_label = nav_item.group if nav_item else "Workspace"
    esc = html.escape

    if status.connected:
        ver_short = status.server_version.split(",")[0] if status.server_version else "PostgreSQL"
        conn_pill = (
            f"<span class='qt-pill qt-pill-ok'>"
            f"<span class='qt-dot qt-dot-ok' style='margin-right:3px;'></span>"
            f"{esc(status.current_database)} @ {esc(status.config.host)}:{status.config.port}"
            f"</span>"
            f"<span class='qt-pill'>{esc(ver_short)}</span>"
        )
    else:
        conn_pill = (
            "<span class='qt-pill qt-pill-warn'>"
            "<span class='qt-dot qt-dot-warn' style='margin-right:3px;'></span>"
            "PostgreSQL Disconnected"
            "</span>"
        )

    meta_pill = f"<span class='qt-pill'>{esc(right_meta)}</span>" if right_meta else ""

    col_info, col_controls = st.columns([2.2, 1.15], vertical_alignment="center")
    with col_info:
        st.markdown(
            f"""
            <div class="qt-topbar-shell">
                <div>
                    <div class="qt-breadcrumb">QueryTrellis / {esc(group_label)} / {esc(resolved_title)}</div>
                    <div class="qt-page-h1">{esc(resolved_title)}</div>
                    <div class="qt-page-sub">{esc(resolved_sub)}</div>
                </div>
                <div class="qt-pill-row">
                    {conn_pill}
                    {meta_pill}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_controls:
        has_extra = action_label is not None and on_action is not None
        if has_extra:
            b_act, b_conn, b_thm = st.columns([1.15, 1.0, 0.72])
        else:
            b_conn, b_thm = st.columns([1.05, 0.75])
            b_act = None

        if b_act is not None and action_label and on_action:
            if b_act.button(
                action_label,
                key=f"qt_top_act_{page_name}",
                icon=f":material/{action_icon}:" if action_icon else None,
                width="stretch",
                type="primary",
            ):
                on_action()

        if status.connected:
            if b_conn.button(
                "Disconnect",
                key=f"qt_top_disc_{page_name}",
                icon=":material/link_off:",
                width="stretch",
                help="Close active PostgreSQL session and return to static AST mode.",
            ):
                conn_mgr.disconnect()
                st.toast("Disconnected from PostgreSQL.")
                st.rerun()
        else:
            if b_conn.button(
                "Connect DB",
                key=f"qt_top_conn_{page_name}",
                icon=":material/database:",
                width="stretch",
                type="secondary" if has_extra else "primary",
                help="Configure host, port, database, and credentials.",
            ):
                navigate_to("Settings")
                st.rerun()

        next_theme = "light" if theme.is_dark else "dark"
        thm_label = "Light" if theme.is_dark else "Dark"
        thm_icon = ":material/light_mode:" if theme.is_dark else ":material/dark_mode:"
        if b_thm.button(
            thm_label,
            key=f"qt_top_thm_{page_name}",
            icon=thm_icon,
            width="stretch",
            help=f"Switch interface to {next_theme} theme.",
        ):
            set_active_theme(next_theme)
            st.toast(f"Switched to {next_theme.title()} theme.")
            st.rerun()

    if show_disconnected_banner and not status.connected and page_name not in ("Settings",):
        st.markdown(
            "<div class='qt-banner qt-banner-warn' style='margin-top:0.15rem;'>"
            "<strong>Offline Static AST Mode:</strong> PostgreSQL is not connected. "
            "SQL formatting, read-only validation, and static anti-pattern rules remain available. "
            "Use <strong>Connect DB</strong> above to enable live execution plans, schema inspection, and benchmarks."
            "</div>",
            unsafe_allow_html=True,
        )
