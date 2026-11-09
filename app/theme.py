"""Unified design token system for QueryTrellis (Dark Graphite default & Crisp Light)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import plotly.graph_objects as go
import streamlit as st


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """Design system tokens shared across CSS, custom components, and Plotly figures."""

    name: str
    is_dark: bool
    bg_app: str
    bg_sidebar: str
    bg_surface: str
    bg_elevated: str
    bg_code: str
    border: str
    border_subtle: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    success: str
    success_bg: str
    warning: str
    warning_bg: str
    error: str
    error_bg: str
    info: str
    info_bg: str
    grid: str
    bar_secondary: str
    # SQL syntax tokens
    tok_keyword: str
    tok_function: str
    tok_string: str
    tok_number: str
    tok_comment: str
    tok_operator: str


DARK_THEME = ThemeTokens(
    name="dark",
    is_dark=True,
    bg_app="#151C24",
    bg_sidebar="#111820",
    bg_surface="#1B2530",
    bg_elevated="#202C38",
    bg_code="#0E141B",
    border="#34414D",
    border_subtle="#25313D",
    text_primary="#E8EDF2",
    text_secondary="#9BA9B7",
    text_muted="#738292",
    accent="#35A99B",
    accent_hover="#2C9185",
    accent_soft="rgba(53, 169, 155, 0.14)",
    accent_text="#58C4B6",
    success="#38A879",
    success_bg="rgba(56, 168, 121, 0.14)",
    warning="#C88D3B",
    warning_bg="rgba(200, 141, 59, 0.14)",
    error="#CE5C5C",
    error_bg="rgba(206, 92, 92, 0.15)",
    info="#5495C7",
    info_bg="rgba(84, 149, 199, 0.14)",
    grid="rgba(115, 130, 146, 0.16)",
    bar_secondary="#5B6E82",
    tok_keyword="#56B6C2",
    tok_function="#D4A656",
    tok_string="#78B87E",
    tok_number="#C98D68",
    tok_comment="#687889",
    tok_operator="#9BA9B7",
)

LIGHT_THEME = ThemeTokens(
    name="light",
    is_dark=False,
    bg_app="#F4F7FA",
    bg_sidebar="#EBF0F5",
    bg_surface="#FFFFFF",
    bg_elevated="#F8FAFC",
    bg_code="#F1F5F9",
    border="#D2DCE6",
    border_subtle="#E3EAF2",
    text_primary="#0F1D2E",
    text_secondary="#4A5C6E",
    text_muted="#6E8091",
    accent="#1E8A7E",
    accent_hover="#176F66",
    accent_soft="rgba(30, 138, 126, 0.10)",
    accent_text="#167066",
    success="#207B57",
    success_bg="rgba(32, 123, 87, 0.10)",
    warning="#A8691D",
    warning_bg="rgba(168, 105, 29, 0.10)",
    error="#B73C3C",
    error_bg="rgba(183, 60, 60, 0.10)",
    info="#2A6BAC",
    info_bg="rgba(42, 107, 172, 0.10)",
    grid="rgba(74, 92, 110, 0.13)",
    bar_secondary="#8FA0B2",
    tok_keyword="#0F6B76",
    tok_function="#9E6312",
    tok_string="#21723A",
    tok_number="#A84A24",
    tok_comment="#758696",
    tok_operator="#4A5C6E",
)

THEMES: dict[str, ThemeTokens] = {
    "dark": DARK_THEME,
    "light": LIGHT_THEME,
}


def get_active_theme() -> ThemeTokens:
    """Return active ThemeTokens from session state (defaults to Dark Graphite)."""
    key = st.session_state.get("qt_theme", "dark")
    return THEMES.get(key, DARK_THEME)


def set_active_theme(theme_name: str) -> ThemeTokens:
    """Switch active UI theme and persist preference in SQLite metadata store."""
    normalized = "light" if str(theme_name).lower() == "light" else "dark"
    st.session_state["qt_theme"] = normalized
    store = st.session_state.get("qt_store")
    if store is not None:
        try:
            store.set_preference("ui_theme", normalized)
        except Exception:
            pass
    return THEMES[normalized]


def apply_plotly_theme(
    fig: go.Figure,
    theme: ThemeTokens | None = None,
    *,
    height: int = 300,
    title: str | None = None,
    margin: dict[str, int] | None = None,
    show_legend: bool = True,
) -> go.Figure:
    """Apply consistent QueryTrellis typography, subtle gridlines, and hover tooltips to Plotly figures."""
    t = theme or get_active_theme()
    layout_kwargs: dict[str, Any] = {
        "height": height,
        "paper_bgcolor": t.bg_surface,
        "plot_bgcolor": t.bg_elevated,
        "font": {
            "family": "'Inter', 'Segoe UI', system-ui, sans-serif",
            "color": t.text_primary,
            "size": 12,
        },
        "margin": margin or {"l": 12, "r": 16, "t": 54 if title else 28, "b": 34},
        "hoverlabel": {
            "bgcolor": t.bg_elevated,
            "bordercolor": t.border,
            "font": {"color": t.text_primary, "size": 12},
        },
        "showlegend": show_legend,
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"color": t.text_secondary, "size": 11},
            "bgcolor": "rgba(0,0,0,0)",
        },
    }
    if title:
        layout_kwargs["title"] = {
            "text": title,
            "x": 0.01,
            "y": 0.96,
            "font": {"size": 13, "color": t.text_primary},
        }
    fig.update_layout(**layout_kwargs)
    fig.update_xaxes(
        gridcolor=t.grid,
        zerolinecolor=t.border_subtle,
        linecolor=t.border_subtle,
        tickfont={"color": t.text_secondary, "size": 11},
        title_font={"color": t.text_secondary, "size": 11},
    )
    fig.update_yaxes(
        gridcolor=t.grid,
        zerolinecolor=t.border_subtle,
        linecolor=t.border_subtle,
        tickfont={"color": t.text_secondary, "size": 11},
        title_font={"color": t.text_secondary, "size": 11},
    )
    return fig
