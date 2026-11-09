"""Global workstation stylesheet driven by ThemeTokens for QueryTrellis."""
from __future__ import annotations

import streamlit as st

from app.theme import ThemeTokens, get_active_theme


def build_theme_css(t: ThemeTokens) -> str:
    """Compile CSS variables and unified component rules for the active theme."""
    scheme = "dark" if t.is_dark else "light"
    return f"""
<style>
:root {{
    color-scheme: {scheme};
    --qt-bg-app: {t.bg_app};
    --qt-bg-sidebar: {t.bg_sidebar};
    --qt-bg-surface: {t.bg_surface};
    --qt-bg-elevated: {t.bg_elevated};
    --qt-bg-code: {t.bg_code};
    --qt-border: {t.border};
    --qt-border-subtle: {t.border_subtle};
    --qt-text-primary: {t.text_primary};
    --qt-text-secondary: {t.text_secondary};
    --qt-text-muted: {t.text_muted};
    --qt-accent: {t.accent};
    --qt-accent-hover: {t.accent_hover};
    --qt-accent-soft: {t.accent_soft};
    --qt-accent-text: {t.accent_text};
    --qt-success: {t.success};
    --qt-success-bg: {t.success_bg};
    --qt-warning: {t.warning};
    --qt-warning-bg: {t.warning_bg};
    --qt-error: {t.error};
    --qt-error-bg: {t.error_bg};
    --qt-info: {t.info};
    --qt-info-bg: {t.info_bg};
    --qt-font-sans: 'Inter', 'Segoe UI Variable', 'Segoe UI', system-ui, -apple-system, sans-serif;
    --qt-font-mono: 'JetBrains Mono', 'Cascadia Mono', 'Cascadia Code', Consolas, monospace;
}}

/* Global workstation shell */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main,
[data-testid="stMain"] {{
    background-color: var(--qt-bg-app) !important;
    color: var(--qt-text-primary) !important;
    font-family: var(--qt-font-sans) !important;
}}

header[data-testid="stHeader"] {{
    background-color: transparent !important;
    height: 2.3rem !important;
}}

/* Hide Streamlit Deploy / MainMenu / rainbow bar while keeping sidebar toggle */
[data-testid="stAppDeployButton"],
[data-testid="stMainMenu"],
#MainMenu,
[data-testid="stDecoration"],
footer {{
    display: none !important;
}}

div[data-testid="stMainBlockContainer"],
.block-container {{
    padding-top: 1.45rem !important;
    padding-bottom: 2rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    max-width: 1540px !important;
}}

/* Compact vertical rhythm */
[data-testid="stVerticalBlock"] {{
    gap: 0.55rem !important;
}}

h1, h2, h3, h4 {{
    color: var(--qt-text-primary) !important;
    font-family: var(--qt-font-sans) !important;
    letter-spacing: -0.012em;
}}

p, li, span, label, [data-testid="stMarkdownContainer"] {{
    color: var(--qt-text-primary);
}}

code, pre {{
    font-family: var(--qt-font-mono) !important;
}}

/* Sidebar shell */
section[data-testid="stSidebar"] {{
    background-color: var(--qt-bg-sidebar) !important;
    border-right: 1px solid var(--qt-border-subtle) !important;
    min-width: 236px !important;
    max-width: 256px !important;
}}

section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    padding: 0.9rem 0.75rem 1rem 0.75rem !important;
}}

section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
    gap: 0.35rem !important;
}}

.qt-brand-wrap {{
    padding: 0.15rem 0.35rem 0.55rem 0.35rem;
    border-bottom: 1px solid var(--qt-border-subtle);
    margin-bottom: 0.35rem;
}}

.qt-brand-title {{
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--qt-text-primary);
    letter-spacing: -0.02em;
    line-height: 1.2;
}}

.qt-brand-sub {{
    font-size: 0.72rem;
    color: var(--qt-text-muted);
    margin-top: 2px;
    font-family: var(--qt-font-sans);
}}

.qt-nav-heading {{
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--qt-text-muted);
    padding: 0.45rem 0.5rem 0.15rem 0.5rem;
    margin: 0;
}}

/* Sidebar nav buttons */
.st-key-qt_nav_grp_workspace button,
.st-key-qt_nav_grp_optimization button,
.st-key-qt_nav_grp_management button {{
    width: 100% !important;
    justify-content: flex-start !important;
    text-align: left !important;
    border-radius: 4px !important;
    padding: 0.36rem 0.6rem !important;
    min-height: 2.0rem !important;
    font-size: 0.84rem !important;
    box-shadow: none !important;
    transition: background-color 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}}

.st-key-qt_nav_grp_workspace button[kind="secondary"],
.st-key-qt_nav_grp_optimization button[kind="secondary"],
.st-key-qt_nav_grp_management button[kind="secondary"] {{
    background-color: transparent !important;
    border: 1px solid transparent !important;
    border-left: 3px solid transparent !important;
    color: var(--qt-text-secondary) !important;
    font-weight: 500 !important;
}}

.st-key-qt_nav_grp_workspace button[kind="secondary"]:hover,
.st-key-qt_nav_grp_optimization button[kind="secondary"]:hover,
.st-key-qt_nav_grp_management button[kind="secondary"]:hover {{
    background-color: var(--qt-bg-elevated) !important;
    color: var(--qt-text-primary) !important;
}}

.st-key-qt_nav_grp_workspace button[kind="primary"],
.st-key-qt_nav_grp_optimization button[kind="primary"],
.st-key-qt_nav_grp_management button[kind="primary"] {{
    background-color: var(--qt-accent-soft) !important;
    border: 1px solid transparent !important;
    border-left: 3px solid var(--qt-accent) !important;
    color: var(--qt-text-primary) !important;
    font-weight: 600 !important;
}}

.st-key-qt_nav_grp_workspace button p,
.st-key-qt_nav_grp_optimization button p,
.st-key-qt_nav_grp_management button p {{
    color: inherit !important;
    font-size: 0.84rem !important;
}}

.qt-sb-footer-card {{
    background-color: var(--qt-bg-surface);
    border: 1px solid var(--qt-border-subtle);
    border-radius: 4px;
    padding: 0.55rem 0.65rem;
    margin-top: 0.4rem;
    font-size: 0.76rem;
}}

.qt-sb-kv {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
    margin-top: 3px;
    color: var(--qt-text-secondary);
}}

.qt-sb-mono {{
    font-family: var(--qt-font-mono);
    font-size: 0.73rem;
    color: var(--qt-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 145px;
}}

/* Status dot */
.qt-dot {{
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
}}
.qt-dot-ok {{ background-color: var(--qt-success); }}
.qt-dot-warn {{ background-color: var(--qt-warning); }}
.qt-dot-err {{ background-color: var(--qt-error); }}
.qt-dot-muted {{ background-color: var(--qt-text-muted); }}

/* Top application bar */
.qt-topbar-shell {{
    background-color: var(--qt-bg-surface);
    border: 1px solid var(--qt-border-subtle);
    border-radius: 5px;
    padding: 0.6rem 0.9rem;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
}}

.qt-breadcrumb {{
    font-size: 0.70rem;
    font-weight: 500;
    color: var(--qt-text-muted);
    letter-spacing: 0.03em;
    text-transform: uppercase;
}}

.qt-page-h1 {{
    font-size: 1.08rem;
    font-weight: 700;
    color: var(--qt-text-primary);
    margin: 1px 0 0 0;
    line-height: 1.25;
}}

.qt-page-sub {{
    font-size: 0.79rem;
    color: var(--qt-text-secondary);
    margin: 2px 0 0 0;
}}

.qt-pill-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
}}

.qt-pill {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid var(--qt-border-subtle);
    background-color: var(--qt-bg-elevated);
    color: var(--qt-text-secondary);
    font-family: var(--qt-font-mono);
    font-size: 0.72rem;
    white-space: nowrap;
}}

.qt-pill-ok {{
    border-color: rgba(56, 168, 121, 0.35);
    background-color: var(--qt-success-bg);
    color: var(--qt-success);
}}

.qt-pill-warn {{
    border-color: rgba(200, 141, 59, 0.35);
    background-color: var(--qt-warning-bg);
    color: var(--qt-warning);
}}

.qt-pill-err {{
    border-color: rgba(206, 92, 92, 0.35);
    background-color: var(--qt-error-bg);
    color: var(--qt-error);
}}

.qt-pill-accent {{
    border-color: rgba(53, 169, 155, 0.40);
    background-color: var(--qt-accent-soft);
    color: var(--qt-accent-text);
}}

/* Section headers */
.qt-sec-head {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    border-bottom: 1px solid var(--qt-border-subtle);
    padding-bottom: 0.32rem;
    margin: 0.45rem 0 0.4rem 0;
}}

.qt-sec-title {{
    font-size: 0.84rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--qt-text-secondary);
}}

.qt-sec-meta {{
    font-size: 0.74rem;
    color: var(--qt-text-muted);
    font-family: var(--qt-font-mono);
}}

/* Telemetry row cards */
.qt-telemetry-grid {{
    display: grid;
    grid-template-columns: 1.15fr 1fr 0.95fr 1.05fr 0.95fr;
    gap: 0.6rem;
    margin: 0.25rem 0 0.4rem 0;
}}

@media (max-width: 1120px) {{
    .qt-telemetry-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
}}

@media (max-width: 720px) {{
    .qt-telemetry-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
}}

.qt-tele-panel {{
    background-color: var(--qt-bg-surface);
    border: 1px solid var(--qt-border-subtle);
    border-radius: 5px;
    padding: 0.58rem 0.75rem;
}}

.qt-tele-panel-accent {{
    border-top: 2px solid var(--qt-accent);
}}

.qt-tele-label {{
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--qt-text-muted);
}}

.qt-tele-val {{
    font-family: var(--qt-font-mono);
    font-size: 1.14rem;
    font-weight: 700;
    color: var(--qt-text-primary);
    margin-top: 3px;
    line-height: 1.2;
}}

.qt-tele-sub {{
    font-size: 0.72rem;
    color: var(--qt-text-secondary);
    margin-top: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

/* Comparison & advisory panels */
.qt-surface-card {{
    background-color: var(--qt-bg-surface);
    border: 1px solid var(--qt-border-subtle);
    border-radius: 5px;
    padding: 0.7rem 0.85rem;
}}

.qt-banner {{
    background-color: var(--qt-bg-elevated);
    border: 1px solid var(--qt-border-subtle);
    border-left: 3px solid var(--qt-accent);
    border-radius: 4px;
    padding: 0.52rem 0.75rem;
    font-size: 0.80rem;
    color: var(--qt-text-secondary);
}}

.qt-banner strong {{
    color: var(--qt-text-primary);
}}

.qt-banner-warn {{
    border-left-color: var(--qt-warning);
    background-color: var(--qt-warning-bg);
    color: var(--qt-text-primary);
}}

.qt-banner-err {{
    border-left-color: var(--qt-error);
    background-color: var(--qt-error-bg);
    color: var(--qt-text-primary);
}}

.qt-empty-box {{
    background-color: var(--qt-bg-surface);
    border: 1px dashed var(--qt-border);
    border-radius: 5px;
    padding: 1.15rem 1rem;
    text-align: center;
}}

.qt-empty-title {{
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--qt-text-primary);
}}

.qt-empty-desc {{
    font-size: 0.78rem;
    color: var(--qt-text-secondary);
    margin-top: 4px;
}}

/* Standard buttons across main workspace */
[data-testid="stMain"] button[kind="primary"] {{
    background-color: var(--qt-accent) !important;
    border: 1px solid var(--qt-accent) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    border-radius: 4px !important;
    font-size: 0.82rem !important;
}}

[data-testid="stMain"] button[kind="primary"]:hover {{
    background-color: var(--qt-accent-hover) !important;
    border-color: var(--qt-accent-hover) !important;
}}

[data-testid="stMain"] button[kind="primary"] p {{
    color: #FFFFFF !important;
}}

[data-testid="stMain"] button[kind="secondary"],
[data-testid="stMain"] [data-testid="stDownloadButton"] button {{
    background-color: var(--qt-bg-surface) !important;
    border: 1px solid var(--qt-border) !important;
    color: var(--qt-text-primary) !important;
    border-radius: 4px !important;
    font-size: 0.81rem !important;
}}

[data-testid="stMain"] button[kind="secondary"]:hover,
[data-testid="stMain"] [data-testid="stDownloadButton"] button:hover {{
    background-color: var(--qt-bg-elevated) !important;
    border-color: var(--qt-accent) !important;
}}

[data-testid="stMain"] button:focus-visible,
section[data-testid="stSidebar"] button:focus-visible {{
    outline: 2px solid var(--qt-accent) !important;
    outline-offset: 1px !important;
}}

/* Inputs, Selectbox, Textarea across both Dark & Light */
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
[data-testid="stNumberInput"] > div {{
    background-color: var(--qt-bg-surface) !important;
    border: 1px solid var(--qt-border) !important;
    border-radius: 4px !important;
    color: var(--qt-text-primary) !important;
}}

[data-baseweb="input"] input,
[data-baseweb="select"] span,
[data-baseweb="select"] input,
[data-baseweb="textarea"] textarea {{
    color: var(--qt-text-primary) !important;
    font-size: 0.83rem !important;
}}

textarea {{
    font-family: var(--qt-font-mono) !important;
}}

/* Dropdown menu popover */
ul[data-baseweb="menu"],
div[data-baseweb="popover"] > div {{
    background-color: var(--qt-bg-elevated) !important;
    border: 1px solid var(--qt-border) !important;
    color: var(--qt-text-primary) !important;
}}

/* Tabs */
[data-baseweb="tab-list"] {{
    border-bottom: 1px solid var(--qt-border-subtle) !important;
    gap: 0.25rem !important;
}}

button[role="tab"] {{
    color: var(--qt-text-secondary) !important;
    font-size: 0.81rem !important;
    font-weight: 500 !important;
    padding: 0.42rem 0.72rem !important;
}}

button[role="tab"][aria-selected="true"] {{
    color: var(--qt-accent-text) !important;
    font-weight: 600 !important;
}}

[data-baseweb="tab-highlight"] {{
    background-color: var(--qt-accent) !important;
}}

/* Expanders */
[data-testid="stExpander"] {{
    background-color: var(--qt-bg-surface) !important;
    border: 1px solid var(--qt-border-subtle) !important;
    border-radius: 5px !important;
}}

[data-testid="stExpander"] summary {{
    color: var(--qt-text-primary) !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
}}

/* Code blocks */
[data-testid="stCode"] pre {{
    background-color: var(--qt-bg-code) !important;
    border: 1px solid var(--qt-border-subtle) !important;
    border-radius: 4px !important;
    color: var(--qt-text-primary) !important;
    font-size: 0.81rem !important;
}}

/* Native Metrics fallback */
div[data-testid="stMetric"] {{
    background-color: var(--qt-bg-surface) !important;
    border: 1px solid var(--qt-border-subtle) !important;
    border-radius: 5px !important;
    padding: 0.5rem 0.7rem !important;
}}
div[data-testid="stMetric"] label {{
    font-size: 0.70rem !important;
    color: var(--qt-text-muted) !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
    font-size: 1.08rem !important;
    font-family: var(--qt-font-mono) !important;
    color: var(--qt-text-primary) !important;
}}

/* Dataframes & Dialogs */
[data-testid="stDataFrame"] {{
    border: 1px solid var(--qt-border-subtle) !important;
    border-radius: 5px !important;
    overflow: hidden;
}}

div[role="dialog"] {{
    background-color: var(--qt-bg-surface) !important;
    border: 1px solid var(--qt-border) !important;
    color: var(--qt-text-primary) !important;
}}

/* Clean SQL comparison table HTML */
.qt-table-wrap {{
    width: 100%;
    overflow-x: auto;
    border: 1px solid var(--qt-border-subtle);
    border-radius: 5px;
    background-color: var(--qt-bg-surface);
}}

table.qt-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.80rem;
}}

table.qt-table th {{
    text-align: left;
    padding: 0.45rem 0.65rem;
    background-color: var(--qt-bg-elevated);
    color: var(--qt-text-secondary);
    font-size: 0.71rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid var(--qt-border-subtle);
    white-space: nowrap;
}}

table.qt-table td {{
    padding: 0.44rem 0.65rem;
    color: var(--qt-text-primary);
    border-bottom: 1px solid var(--qt-border-subtle);
    vertical-align: middle;
}}

table.qt-table tr:last-child td {{
    border-bottom: none;
}}

table.qt-table tr:hover td {{
    background-color: var(--qt-bg-elevated);
}}

.qt-num {{
    text-align: right !important;
    font-family: var(--qt-font-mono);
}}

.qt-mono {{
    font-family: var(--qt-font-mono);
}}
</style>
"""


def inject_workstation_css() -> None:
    """Inject active theme tokens and global workstation CSS."""
    t = get_active_theme()
    st.markdown(build_theme_css(t), unsafe_allow_html=True)
