"""Visual research-console theme (CSS) for the EasyAgent visual lab.

Streamlit is passed in as a parameter rather than imported at module level so
that importing this module never hard-fails when the ``visual`` extra is
absent.
"""

from __future__ import annotations

from typing import Any

__all__ = ["inject_theme"]


def inject_theme(st: Any) -> None:
    """Emit both palettes so a theme switch repaints without a server rerun.

    Streamlit only reports the browser's color scheme when the frontend sends a
    rerun message, so flipping the theme in the settings menu never re-executes
    this script. Injecting one resolved palette would therefore leave the
    previous colors in the DOM until an unrelated rerun happened.

    Both palettes are emitted instead, selected by the CSS ``light-dark()``
    function against the ``color-scheme`` that Streamlit sets on the app
    container and updates client-side. ``st.context.theme.type`` is still used,
    but only for the static fallback that older engines without ``light-dark()``
    support fall back to.
    """
    context = getattr(st, "context", None)
    theme = getattr(context, "theme", None)
    theme_type = theme.get("type") if isinstance(theme, dict) else getattr(theme, "type", None)
    if theme_type not in {"light", "dark"}:
        theme_type = "dark"

    palettes = {
        "dark": {
            "bg": "#080c12",
            "surface": "#101823",
            "surface-2": "#141f2c",
            "surface-3": "#1a2a3c",
            "surface-raised": "#22384e",
            "input-bg": "#f7fbff",
            "input-text": "#172434",
            "line": "#253447",
            "line-strong": "#526d89",
            "text": "#e8f0f7",
            "text-soft": "#d6e2ee",
            "muted": "#8ea0b4",
            "muted-strong": "#a9bdd0",
            "cyan": "#5de4ff",
            "magenta": "#e68cff",
            "lime": "#b6f36b",
            "amber": "#ffc36b",
            "danger": "#ff8c8c",
            "danger-soft": "#ff9a9a",
            "line-live": "#3c8c7a",
            "line-complete": "#5c4b83",
            "line-error": "#9a4b54",
            "line-error-soft": "#6b353e",
            "chip-trace": "#76538f",
            "header-bg": "rgba(8, 12, 18, 0.92)",
        },
        "light": {
            "bg": "#f4f7fa",
            "surface": "#ffffff",
            "surface-2": "#eef3f8",
            "surface-3": "#e2e9f0",
            "surface-raised": "#d0dae8",
            "input-bg": "#ffffff",
            "input-text": "#1a2735",
            "line": "#c5d2de",
            "line-strong": "#8a9bad",
            "text": "#1a2735",
            "text-soft": "#2a3a4e",
            "muted": "#5a6e82",
            "muted-strong": "#4a5e72",
            "cyan": "#087ea4",
            "magenta": "#9b3caf",
            "lime": "#4d8d25",
            "amber": "#ad6d16",
            "danger": "#b3261e",
            "danger-soft": "#8c1d18",
            "line-live": "#2f7566",
            "line-complete": "#6b4f93",
            "line-error": "#c26b73",
            "line-error-soft": "#e0b4b8",
            "chip-trace": "#7c53a0",
            "header-bg": "rgba(244, 247, 250, 0.92)",
        },
    }
    if set(palettes["light"]) != set(palettes["dark"]):
        raise ValueError("light and dark palettes must define the same tokens")
    # Static fallback for engines without light-dark(): use the type Streamlit
    # reported, which is correct on first load and after any rerun.
    fallback = "\n".join(
        f"            --ea-{name}: {value};" for name, value in palettes[theme_type].items()
    )
    # Client-side selection: light-dark() reads the container's color-scheme,
    # which Streamlit updates in the browser without contacting the server, so
    # every element repaints the moment the user flips the theme. Look the dark
    # value up by name so reordering one palette cannot mispair colors.
    adaptive = "\n".join(
        f"            --ea-{name}: light-dark({light}, {palettes['dark'][name]});"
        for name, light in palettes["light"].items()
    )
    variables = "\n".join(
        [
            "        :root {",
            fallback,
            "        }",
            "        @supports (color: light-dark(white, black)) {",
            # light-dark() inside a custom property resolves against the
            # color-scheme of the element the property is DECLARED on, not the
            # one that consumes it. Declaring on :root would therefore follow the
            # OS preference, which the in-app theme menu does not change. These
            # Streamlit containers carry a concrete `color-scheme: light|dark`
            # that the frontend rewrites client-side, and color-scheme inherits,
            # so declaring here makes every descendant follow the active theme.
            "            .stApp,",
            '            [data-testid="stAppViewContainer"],',
            '            [data-testid="stHeader"],',
            '            [data-testid="stSidebar"] {',
            adaptive,
            "            }",
            "        }",
        ]
    )
    st.markdown(
        "<style>\n" + variables + "\n" + """
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] {
            background: var(--ea-bg);
            color: var(--ea-text);
        }
        .main .block-container,
        .main .block-container p,
        .main .block-container li,
        .main .block-container h1,
        .main .block-container h2,
        .main .block-container h3,
        .main .block-container h4,
        .main .block-container label,
        [data-testid="stWidgetLabel"] p {
            color: var(--ea-text-soft) !important;
        }
        .main .block-container a { color: var(--ea-cyan) !important; }
        [data-testid="stCaptionContainer"] p,
        [data-testid="stCaptionContainer"] small {
            color: var(--ea-muted-strong) !important;
        }
        [data-testid="stHeader"] button,
        [data-testid="stToolbar"] button {
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stHeader"] {
            background: var(--ea-header-bg);
        }
        [data-testid="stSidebar"] {
            background: var(--ea-surface);
            border-right: 1px solid var(--ea-line);
        }
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.2rem;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: var(--ea-muted) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            border-color: var(--ea-line-strong);
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            background: var(--ea-surface-2);
            border: 1px solid var(--ea-line-strong);
            border-radius: 8px;
            margin: 0.45rem 0 0.7rem;
            overflow: hidden;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] details[open] {
            background: var(--ea-surface-2);
            border-color: var(--ea-cyan);
            box-shadow: inset 0 2px 0 rgba(93, 228, 255, 0.65);
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            background: var(--ea-surface-3);
            color: var(--ea-text) !important;
            font-weight: 700;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
            background: var(--ea-surface-raised);
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            background: var(--ea-surface-2);
        }
        /* Keep the native Streamlit controls legible across light and dark browser themes. */
        /* These literals are intentionally shared: `input-bg` is a light surface in BOTH
           palettes, so the border/placeholder/stepper colors below are chosen to stay
           legible on a light field regardless of the surrounding theme. */
        [data-baseweb="input"] > div,
        [data-baseweb="textarea"] > div,
        [data-baseweb="select"] > div,
        [data-testid="stChatInput"] > div {
            background: var(--ea-input-bg) !important;
            border-color: #8ba3ba !important;
            color: var(--ea-input-text) !important;
        }
        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea,
        [data-baseweb="select"] input,
        [data-testid="stChatInput"] textarea {
            background: var(--ea-input-bg) !important;
            caret-color: var(--ea-input-text) !important;
            color: var(--ea-input-text) !important;
            -webkit-text-fill-color: var(--ea-input-text) !important;
        }
        [data-baseweb="input"] input::placeholder,
        [data-baseweb="textarea"] textarea::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {
            color: #647b91 !important;
            -webkit-text-fill-color: #647b91 !important;
        }
        [data-baseweb="select"] span,
        [data-baseweb="select"] svg {
            color: var(--ea-input-text) !important;
            fill: var(--ea-input-text) !important;
        }
        [data-testid="stNumberInput"] button {
            background: #e7f0f7 !important;
            border-color: #8ba3ba !important;
            color: var(--ea-input-text) !important;
        }
        [data-testid="stNumberInput"] button:hover {
            background: #d4e4ef !important;
            color: #0b1724 !important;
        }
        [data-baseweb="popover"],
        [data-baseweb="popover"] > div,
        [data-baseweb="menu"],
        [role="listbox"] {
            background: var(--ea-surface-3) !important;
            border: 1px solid var(--ea-line-strong) !important;
            color: var(--ea-text) !important;
            z-index: 1001 !important;
        }
        [data-baseweb="menu"] li,
        [role="option"] {
            color: var(--ea-text-soft) !important;
        }
        [data-baseweb="menu"] li:hover,
        [role="option"]:hover,
        [role="option"][aria-selected="true"] {
            background: var(--ea-surface-raised) !important;
            color: var(--ea-text) !important;
        }
        [data-testid*="VirtualDropdown"] {
            background: var(--ea-surface-3) !important;
            border: 1px solid var(--ea-line-strong) !important;
            box-sizing: border-box !important;
            color: var(--ea-text) !important;
            overflow: hidden !important;
            padding: 0.2rem 0 !important;
        }
        [data-testid*="VirtualDropdown"] li {
            box-sizing: border-box !important;
            padding: 0.45rem 0.75rem !important;
        }
        [data-testid*="VirtualDropdown"] li > div,
        [data-testid*="VirtualDropdown"] li > div > div {
            background: transparent !important;
            color: var(--ea-text-soft) !important;
            max-width: 100% !important;
            overflow: visible !important;
        }
        [data-testid*="VirtualDropdown"] li:hover,
        [data-testid*="VirtualDropdown"] li[aria-selected="true"] {
            background: var(--ea-surface-raised) !important;
            color: var(--ea-text) !important;
        }
        [data-baseweb="popover"] input {
            background: var(--ea-input-bg) !important;
            color: var(--ea-input-text) !important;
        }
        [data-baseweb="tag"] {
            background: var(--ea-surface-2) !important;
            border: 1px solid var(--ea-line-strong) !important;
            color: var(--ea-text) !important;
        }
        [data-baseweb="tag"] > span:first-child,
        [data-baseweb="tag"] svg {
            color: var(--ea-text) !important;
            fill: var(--ea-text) !important;
        }
        [data-baseweb="tag"]:hover {
            background: var(--ea-surface-raised) !important;
            border-color: var(--ea-muted) !important;
        }
        [data-testid="stAlert"],
        [data-testid="stToast"],
        [data-testid="stStatus"],
        [data-testid="stStatusWidget"] {
            background: var(--ea-surface-3) !important;
            border: 1px solid var(--ea-line-strong) !important;
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stAlert"] p,
        [data-testid="stAlert"] div,
        [data-testid="stToast"] p,
        [data-testid="stToast"] div,
        [data-testid="stStatus"] p,
        [data-testid="stStatus"] div,
        [data-testid="stStatusWidget"] p,
        [data-testid="stStatusWidget"] div {
            color: inherit !important;
        }
        [data-testid="stExpander"] {
            background: var(--ea-surface) !important;
            border: 1px solid var(--ea-line-strong) !important;
            border-radius: 8px;
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            background: var(--ea-surface) !important;
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stExpander"] summary:hover,
        [data-testid="stExpander"] details[open] summary {
            background: var(--ea-surface-raised) !important;
            color: var(--ea-text) !important;
        }
        [data-testid="stExpander"] summary p,
        [data-testid="stExpander"] summary span {
            color: inherit !important;
        }
        [data-testid="stFileUploader"] section {
            background: var(--ea-surface) !important;
            border: 1px dashed var(--ea-line-strong) !important;
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stFileUploader"] section p,
        [data-testid="stFileUploader"] section small {
            color: var(--ea-muted-strong) !important;
        }
        [data-testid="stChatMessage"] p,
        [data-testid="stChatMessage"] li,
        [data-testid="stChatMessage"] span {
            color: var(--ea-text-soft) !important;
        }
        .main .block-container {
            max-width: 1500px;
            padding: 2rem 2.6rem 4rem;
        }
        .ea-masthead {
            padding: 0.2rem 0 1.35rem;
            margin-bottom: 1.25rem;
            border-bottom: 1px solid var(--ea-line);
        }
        .ea-kicker {
            color: var(--ea-cyan);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }
        .ea-title {
            color: var(--ea-text);
            font-size: 2.55rem;
            font-weight: 760;
            letter-spacing: 0.01em;
            line-height: 1.1;
            margin-top: 0.35rem;
        }
        .ea-title span { color: var(--ea-magenta); }
        .ea-subtitle {
            color: var(--ea-muted);
            font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
            font-size: 0.92rem;
            font-weight: 400;
            letter-spacing: 0;
            line-height: 1.55;
            margin-top: 0.55rem;
            text-rendering: optimizeLegibility;
        }
        .ea-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 1rem;
        }
        .ea-chip {
            border: 1px solid var(--ea-line);
            border-radius: 999px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            letter-spacing: 0.08em;
            padding: 0.28rem 0.58rem;
        }
        .ea-chip.live { border-color: var(--ea-line-live); color: var(--ea-lime); }
        .ea-chip.trace { border-color: var(--ea-chip-trace); color: var(--ea-magenta); }
        .ea-section-label {
            color: var(--ea-cyan);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            margin: 0.15rem 0 0.7rem;
            text-transform: uppercase;
        }
        .ea-status-line {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            padding: 0.55rem 0.7rem;
        }
        .ea-status-line strong { color: var(--ea-lime); }
        .ea-run-metrics {
            align-items: stretch;
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            display: grid;
            gap: 0.5rem;
            grid-template-columns: minmax(8rem, 1.35fr) repeat(5, minmax(4.2rem, 0.7fr))
                minmax(5rem, 0.9fr);
            margin-bottom: 0.8rem;
            padding: 0.55rem;
        }
        .ea-run-state,
        .ea-run-metric,
        .ea-run-id {
            border-right: 1px solid var(--ea-line);
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-width: 0;
            padding: 0.2rem 0.6rem;
        }
        .ea-run-id { border-right: 0; }
        .ea-run-state span,
        .ea-run-metric span,
        .ea-run-id span {
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.1em;
        }
        .ea-run-state strong,
        .ea-run-metric strong,
        .ea-run-id strong {
            color: var(--ea-text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.82rem;
            margin-top: 0.2rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .ea-state-running { border-color: var(--ea-line-live); }
        .ea-state-running .ea-run-state strong { color: var(--ea-lime); }
        .ea-state-complete { border-color: var(--ea-line-complete); }
        .ea-state-complete .ea-run-state strong { color: var(--ea-magenta); }
        .ea-state-error { border-color: var(--ea-line-error); }
        .ea-state-error .ea-run-state strong { color: var(--ea-danger); }
        .ea-run-error {
            border-top: 1px solid var(--ea-line-error-soft);
            color: var(--ea-danger-soft);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            grid-column: 1 / -1;
            overflow-wrap: anywhere;
            padding: 0.5rem 0.6rem 0.1rem;
        }
        .ea-timeline {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            padding: 0.55rem 0.75rem;
        }
        .ea-timeline-row {
            display: grid;
            grid-template-columns: 2rem 1.6rem minmax(0, 1fr);
            gap: 0.65rem;
            padding: 0.65rem 0.1rem;
            border-bottom: 1px solid var(--ea-line);
        }
        .ea-timeline-row:last-child { border-bottom: 0; }
        .ea-timeline-index {
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            padding-top: 0.15rem;
        }
        .ea-timeline-icon {
            align-items: center;
            border: 1px solid currentColor;
            border-radius: 50%;
            display: flex;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            height: 1.35rem;
            justify-content: center;
            width: 1.35rem;
        }
        .ea-tool_call { color: var(--ea-amber); }
        .ea-tool_result { color: var(--ea-lime); }
        .ea-answer { color: var(--ea-magenta); }
        .ea-thought { color: var(--ea-cyan); }
        .ea-approval_request { color: var(--ea-amber); }
        .ea-loop_detected { color: var(--ea-danger); }
        .ea-timeline-label {
            color: var(--ea-text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.08em;
        }
        .ea-timeline-label span {
            color: var(--ea-muted);
            font-weight: 500;
            letter-spacing: 0;
            margin-left: 0.45rem;
        }
        .ea-timeline-detail {
            color: var(--ea-text-soft);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.75rem;
            line-height: 1.4;
            margin-top: 0.22rem;
            overflow-wrap: anywhere;
        }
        .ea-execution-map {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line-strong);
            border-radius: 8px;
            min-height: 12rem;
            overflow: hidden;
            padding: 0.75rem;
            position: relative;
        }
        .ea-execution-map::after {
            background: var(--ea-cyan);
            box-shadow: 0 0 18px 2px rgba(93, 228, 255, 0.4);
            content: "";
            height: 1px;
            left: 0;
            opacity: 0.2;
            position: absolute;
            right: 0;
            top: 0;
            transform: translateY(-2px);
            animation: ea-map-scan 2.8s ease-out 1;
        }
        .ea-map-heading {
            align-items: center;
            border-bottom: 1px solid var(--ea-line);
            color: var(--ea-muted);
            display: flex;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.64rem;
            justify-content: space-between;
            letter-spacing: 0.12em;
            padding: 0.05rem 0.15rem 0.65rem;
        }
        .ea-map-heading span { color: var(--ea-cyan); }
        .ea-map-heading b {
            background: var(--ea-lime);
            border-radius: 50%;
            box-shadow: 0 0 9px rgba(182, 243, 107, 0.8);
            display: inline-block;
            height: 0.4rem;
            margin-right: 0.3rem;
            width: 0.4rem;
        }
        .ea-map-heading small {
            color: var(--ea-muted);
            font-size: 0.58rem;
            letter-spacing: 0.08em;
        }
        .ea-flow-canvas { padding: 0.7rem 0.1rem 0.2rem; }
        .ea-flow-step {
            align-items: start;
            display: grid;
            grid-template-columns: 2.2rem 2.4rem minmax(0, 1fr);
            min-height: 3.3rem;
            position: relative;
            animation: ea-flow-arrive 0.45s cubic-bezier(0.2, 0.8, 0.2, 1)
                var(--ea-flow-delay) both;
        }
        .ea-flow-index {
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.65rem;
            padding-top: 0.55rem;
        }
        .ea-flow-node {
            align-items: center;
            background: var(--ea-surface-2);
            border: 1px solid var(--ea-line-strong);
            border-radius: 50%;
            color: var(--ea-text);
            display: flex;
            height: 1.85rem;
            justify-content: center;
            margin-top: 0.22rem;
            position: relative;
            width: 1.85rem;
            z-index: 1;
        }
        .ea-flow-node span {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.82rem;
        }
        .ea-flow-tool_call .ea-flow-node { border-radius: 7px; color: var(--ea-amber); }
        .ea-flow-tool_result .ea-flow-node { border-radius: 7px; color: var(--ea-lime); }
        .ea-flow-answer .ea-flow-node { color: var(--ea-magenta); transform: rotate(45deg); }
        .ea-flow-answer .ea-flow-node span { transform: rotate(-45deg); }
        .ea-flow-error .ea-flow-node { border-radius: 7px; color: var(--ea-danger); }
        .ea-flow-approval_request .ea-flow-node { border-radius: 7px; color: var(--ea-amber); }
        .ea-flow-loop_detected .ea-flow-node { border-radius: 7px; color: var(--ea-danger); }
        .ea-flow-user .ea-flow-node { color: var(--ea-cyan); }
        .ea-flow-copy { min-width: 0; padding: 0.22rem 0.2rem 0.8rem 0.55rem; }
        .ea-flow-code {
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.61rem;
            font-weight: 700;
            letter-spacing: 0.1em;
        }
        .ea-flow-code span { color: var(--ea-muted); float: right; font-size: 0.56rem; }
        .ea-flow-copy strong {
            color: var(--ea-text);
            display: block;
            font-size: 0.8rem;
            margin-top: 0.14rem;
        }
        .ea-flow-copy small {
            color: var(--ea-text-soft);
            display: block;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            line-height: 1.35;
            margin-top: 0.12rem;
            overflow-wrap: anywhere;
        }
        .ea-flow-connector {
            border-left: 1px solid var(--ea-line-strong);
            bottom: -0.1rem;
            left: 3.1rem;
            position: absolute;
            top: 2.1rem;
        }
        .ea-flow-connector i {
            background: var(--ea-cyan);
            border-radius: 50%;
            box-shadow: 0 0 8px rgba(93, 228, 255, 0.8);
            display: block;
            height: 0.28rem;
            left: -0.14rem;
            position: absolute;
            top: -0.15rem;
            width: 0.28rem;
            animation: ea-flow-travel 0.75s ease-in var(--ea-flow-delay) both;
        }
        .ea-flow-active .ea-flow-node {
            border-color: var(--ea-lime);
            box-shadow: 0 0 0 4px rgba(182, 243, 107, 0.1), 0 0 18px rgba(182, 243, 107, 0.35);
            animation: ea-node-pulse 1.7s ease-in-out infinite;
        }
        .ea-flow-latest .ea-flow-node {
            border-color: var(--ea-magenta);
            box-shadow: 0 0 0 3px rgba(230, 140, 255, 0.1);
        }
        .ea-execution-map-empty {
            align-items: center;
            display: flex;
            gap: 0.75rem;
            justify-content: center;
        }
        .ea-execution-map-empty strong {
            color: var(--ea-text);
            display: block;
            font-size: 0.82rem;
        }
        .ea-execution-map-empty small {
            color: var(--ea-muted);
            display: block;
            font-size: 0.7rem;
            margin-top: 0.15rem;
        }
        .ea-map-empty-orbit {
            border: 1px solid var(--ea-line-strong);
            border-radius: 50%;
            height: 2rem;
            position: relative;
            width: 2rem;
        }
        .ea-map-empty-orbit::after {
            border: 1px solid var(--ea-cyan);
            border-radius: 50%;
            content: "";
            inset: 0.45rem;
            position: absolute;
        }
        .ea-map-empty-orbit span {
            background: var(--ea-cyan);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--ea-cyan);
            height: 0.3rem;
            left: 0.85rem;
            position: absolute;
            top: -0.15rem;
            width: 0.3rem;
        }
        @keyframes ea-flow-arrive {
            from { opacity: 0; transform: translateY(0.45rem); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes ea-flow-travel {
            from { opacity: 0; transform: translateY(0); }
            20% { opacity: 1; }
            to { opacity: 0; transform: translateY(2.9rem); }
        }
        @keyframes ea-node-pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        @keyframes ea-map-scan {
            from { opacity: 0; transform: translateY(0); }
            18% { opacity: 0.35; }
            to { opacity: 0; transform: translateY(11rem); }
        }
        @media (prefers-reduced-motion: reduce) {
            .ea-execution-map::after,
            .ea-flow-step,
            .ea-flow-connector i,
            .ea-flow-active .ea-flow-node { animation: none; }
        }
        /* ---- Architecture demo flowchart ---- */
        .ea-arch-canvas {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 10px;
            overflow: hidden;
            margin: 0.5rem 0;
        }
        .ea-arch-heading {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 0.7rem;
            border-bottom: 1px solid var(--ea-line);
            background: var(--ea-surface-2);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            color: var(--ea-muted-strong);
        }
        .ea-arch-heading b {
            display: inline-block;
            width: 7px; height: 7px;
            border-radius: 50%;
            background: var(--ea-cyan);
            margin-right: 0.35rem;
            vertical-align: middle;
        }
        .ea-arch-heading small { color: var(--ea-muted); font-size: 0.6rem; }
        .ea-arch-flow { padding: 0.6rem 0.5rem 0.3rem; }
        .ea-arch-node-wrap {
            animation: ea-flow-arrive 0.45s cubic-bezier(0.2, 0.8, 0.2, 1)
                var(--ea-flow-delay) both;
        }
        .ea-arch-connector {
            display: flex;
            align-items: center;
            gap: 0.3rem;
            margin-left: 1.1rem;
            height: 1.1rem;
            position: relative;
        }
        .ea-arch-connector i {
            display: block;
            width: 2px;
            height: 100%;
            background: var(--ea-line-strong);
            border-radius: 1px;
        }
        .ea-arch-edge-loop i {
            background: repeating-linear-gradient(
                to bottom,
                var(--ea-magenta) 0 3px,
                transparent 3px 6px
            );
        }
        .ea-arch-edge-label {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.56rem;
            color: var(--ea-muted);
            background: var(--ea-surface-3);
            border: 1px solid var(--ea-line);
            border-radius: 4px;
            padding: 0.05rem 0.3rem;
            white-space: nowrap;
        }
        .ea-arch-node {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            padding: 0.45rem 0.6rem;
            border: 1px solid var(--ea-line);
            border-radius: 9px;
            background: var(--ea-surface-2);
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .ea-arch-node:hover {
            border-color: var(--ea-line-strong);
            box-shadow: 0 0 0 1px var(--ea-line-strong);
        }
        .ea-arch-node-icon {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 1.7rem; height: 1.7rem;
            border-radius: 50%;
            border: 1.5px solid currentColor;
            font-size: 0.8rem;
            flex-shrink: 0;
        }
        .ea-arch-node-body { min-width: 0; }
        .ea-arch-node-code {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.56rem;
            color: var(--ea-muted);
            letter-spacing: 0.04em;
        }
        .ea-arch-node-body strong {
            display: block;
            color: var(--ea-text);
            font-size: 0.82rem;
            font-weight: 600;
        }
        .ea-arch-node-body small {
            display: block;
            color: var(--ea-muted);
            font-size: 0.68rem;
            margin-top: 0.05rem;
        }
        .ea-arch-node-user .ea-arch-node-icon { color: var(--ea-cyan); }
        .ea-arch-node-llm .ea-arch-node-icon { color: var(--ea-magenta); }
        .ea-arch-node-tool .ea-arch-node-icon { color: var(--ea-amber); border-radius: 7px; }
        .ea-arch-node-memory .ea-arch-node-icon { color: var(--ea-lime); border-radius: 5px; }
        .ea-arch-node-agent .ea-arch-node-icon { color: var(--ea-cyan); border-style: dashed; }
        .ea-arch-node-decision .ea-arch-node-icon {
            color: var(--ea-amber);
            transform: rotate(45deg);
            border-radius: 3px;
        }
        .ea-arch-node-plan .ea-arch-node-icon { color: var(--ea-magenta); border-radius: 5px; }
        .ea-arch-node-reflect .ea-arch-node-icon { color: var(--ea-lime); }
        .ea-arch-node-answer .ea-arch-node-icon {
            color: var(--ea-magenta);
            transform: rotate(45deg);
        }
        .ea-arch-node-answer .ea-arch-node-icon span {
            display: inline-block;
            transform: rotate(-45deg);
        }
        .ea-arch-node-router .ea-arch-node-icon { color: var(--ea-amber); border-radius: 7px; }
        .ea-arch-empty {
            background: var(--ea-surface);
            border: 1px dashed var(--ea-line);
            border-radius: 8px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
            padding: 1rem;
            text-align: center;
        }
        .ea-teaching-head {
            align-items: center;
            border-bottom: 1px solid var(--ea-line);
            display: flex;
            justify-content: space-between;
            margin: 0.25rem 0 0.35rem;
            padding: 0.35rem 0 0.8rem;
        }
        .ea-teaching-head span,
        .ea-concept-watermark {
            color: var(--ea-cyan);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.65rem;
            font-weight: 700;
            letter-spacing: 0.12em;
        }
        .ea-teaching-head h2 {
            color: var(--ea-text);
            font-size: 1.55rem;
            letter-spacing: 0;
            margin: 0.15rem 0 0;
        }
        .ea-teaching-head > strong {
            border: 1px solid var(--ea-line-strong);
            border-radius: 6px;
            color: var(--ea-lime);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.7rem;
            padding: 0.35rem 0.55rem;
        }
        .ea-concept-band {
            background: var(--ea-surface-2);
            border-left: 3px solid var(--ea-cyan);
            padding: 0.75rem;
        }
        .ea-concept-watermark {
            border-bottom: 1px dashed var(--ea-line-strong);
            color: var(--ea-muted-strong);
            margin-bottom: 0.65rem;
            padding-bottom: 0.5rem;
        }
        .ea-concept-band .ea-arch-canvas {
            background: transparent;
            border: 0;
            margin: 0;
        }
        .ea-teaching-events {
            border-left: 2px solid var(--ea-line-strong);
            margin: 0.35rem 0 1rem 0.8rem;
        }
        .ea-teaching-event {
            display: grid;
            gap: 0.75rem;
            grid-template-columns: 2.2rem minmax(0, 1fr);
            padding: 0.55rem 0 0.65rem 0.7rem;
        }
        .ea-teaching-event > span {
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            padding-top: 0.12rem;
        }
        .ea-teaching-event strong {
            color: var(--ea-cyan);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            letter-spacing: 0.08em;
        }
        .ea-teaching-event b {
            color: var(--ea-text);
            font-size: 0.78rem;
            margin-left: 0.6rem;
        }
        .ea-teaching-event p {
            color: var(--ea-text-soft);
            font-size: 0.8rem;
            margin: 0.22rem 0 0;
            overflow-wrap: anywhere;
        }
        .ea-live-progress {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line-strong);
            border-left: 3px solid var(--ea-cyan);
            margin: 0.5rem 0 1rem;
            padding: 0.75rem;
        }
        .ea-live-progress-head {
            align-items: center;
            border-bottom: 1px solid var(--ea-line);
            display: flex;
            justify-content: space-between;
            padding-bottom: 0.55rem;
        }
        .ea-live-progress-head strong,
        .ea-live-progress-head span,
        .ea-live-progress-row > span {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        }
        .ea-live-progress-head strong { color: var(--ea-cyan); font-size: 0.78rem; }
        .ea-live-progress-head span { color: var(--ea-muted); font-size: 0.62rem; }
        .ea-live-progress-row {
            display: grid;
            gap: 0.7rem;
            grid-template-columns: 2rem minmax(0, 1fr);
            padding: 0.55rem 0 0.15rem;
        }
        .ea-live-progress-row > span { color: var(--ea-muted); font-size: 0.65rem; }
        .ea-live-progress-row strong { color: var(--ea-text); font-size: 0.78rem; }
        .ea-live-progress-row p {
            color: var(--ea-text-soft);
            font-size: 0.78rem;
            margin: 0.1rem 0 0;
            overflow-wrap: anywhere;
        }
        .ea-live-progress-completed strong { color: var(--ea-lime); }
        .ea-live-progress-warning strong { color: var(--ea-amber); }
        .ea-live-progress-failed {
            border-left: 2px solid var(--ea-danger);
            padding-left: 0.55rem;
        }
        .ea-live-progress-failed strong { color: var(--ea-danger); }
        @media (prefers-reduced-motion: reduce) {
            .ea-arch-node-wrap { animation: none; }
        }
        .ea-empty {
            background: var(--ea-surface);
            border: 1px dashed var(--ea-line);
            border-radius: 8px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
            padding: 1rem;
        }
        .ea-trace-metrics {
            align-items: stretch;
            background: var(--ea-surface);
            border: 1px solid var(--ea-muted);
            border-radius: 8px;
            display: grid;
            gap: 0.45rem;
            grid-template-columns: repeat(9, minmax(0, 1fr));
            margin: 0.75rem 0;
            padding: 0.55rem;
        }
        .ea-trace-metrics > div {
            border-right: 1px solid var(--ea-line);
            min-width: 0;
            padding: 0.2rem 0.55rem;
        }
        .ea-trace-metrics > div:last-child { border-right: 0; }
        .ea-trace-metrics span,
        .ea-compare-run-head span,
        .ea-compare-prompt span,
        .ea-compare-grid-metrics span {
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.1em;
        }
        .ea-trace-metrics strong,
        .ea-compare-grid-metrics strong {
            color: var(--ea-text);
            display: block;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
            margin-top: 0.2rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .ea-compare-grid {
            display: grid;
            gap: 0.8rem;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-top: 0.7rem;
        }
        .ea-compare-run {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            min-width: 0;
            padding: 0.8rem;
        }
        .ea-compare-run.run-a { border-top: 2px solid var(--ea-cyan); }
        .ea-compare-run.run-b { border-top: 2px solid var(--ea-magenta); }
        .ea-compare-run-head {
            align-items: center;
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.6rem;
        }
        .ea-compare-run-head strong {
            color: var(--ea-text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
        }
        .ea-compare-grid-metrics {
            display: grid;
            gap: 0.5rem;
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .ea-compare-grid-metrics > div { min-width: 0; }
        .ea-compare-prompt {
            border-top: 1px solid var(--ea-line);
            margin-top: 0.7rem;
            padding-top: 0.55rem;
        }
        .ea-compare-prompt p {
            color: var(--ea-text-soft);
            font-size: 0.78rem;
            line-height: 1.45;
            margin: 0.3rem 0 0;
            overflow-wrap: anywhere;
        }
        [data-testid="stCode"] {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
        }
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {
            background: var(--ea-surface) !important;
        }
        @media (max-width: 1200px) {
            .ea-trace-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
            .ea-trace-metrics > div:nth-child(4),
            .ea-trace-metrics > div:nth-child(8) { border-right: 0; }
        }
        @media (max-width: 720px) {
            .ea-trace-metrics,
            .ea-compare-grid { grid-template-columns: 1fr; }
            .ea-trace-metrics > div { border-right: 0; }
            .ea-compare-grid-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        .stButton > button {
            background: var(--ea-surface-2);
            border: 1px solid var(--ea-line);
            border-radius: 7px;
            color: var(--ea-text);
            font-weight: 650;
        }
        .stButton > button:hover {
            background: var(--ea-surface-raised);
            border-color: var(--ea-cyan);
            color: var(--ea-text);
        }
        .stButton > button:disabled,
        [data-testid="stButton"] button:disabled {
            background: var(--ea-surface-3) !important;
            border-color: var(--ea-surface-raised) !important;
            color: var(--ea-muted) !important;
            opacity: 1 !important;
        }
        [data-testid="stTabs"] [role="tablist"] {
            border-bottom: 1px solid var(--ea-line);
            gap: 0.35rem;
        }
        [data-testid="stTabs"] button[role="tab"] {
            background: transparent !important;
            color: var(--ea-muted-strong) !important;
            border-bottom-color: transparent !important;
        }
        [data-testid="stTabs"] button[role="tab"]:hover,
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: var(--ea-text) !important;
            border-bottom-color: var(--ea-cyan) !important;
        }
        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label,
        [data-testid="stToggle"] label {
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stRadio"] label:hover,
        [data-testid="stCheckbox"] label:hover,
        [data-testid="stToggle"] label:hover {
            color: var(--ea-text) !important;
        }
        [data-testid="stMetric"] label,
        [data-testid="stMetric"] [data-testid="stMetricLabel"] p {
            color: var(--ea-muted-strong) !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--ea-text) !important;
        }
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stCode"] [data-testid="stCodeCopyButton"] {
            background: var(--ea-surface-raised) !important;
            border-color: var(--ea-line-strong) !important;
            color: var(--ea-text-soft) !important;
        }
        hr {
            border-color: var(--ea-line) !important;
        }
        [data-testid="stChatMessage"] {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            margin-bottom: 0.55rem;
        }
        [data-testid="stChatInput"] {
            border-color: var(--ea-line);
        }
        [data-testid="stChatInput"] textarea:focus {
            border-color: var(--ea-cyan);
            box-shadow: 0 0 0 1px var(--ea-cyan);
        }
        [data-testid="stMetric"] {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            padding: 0.7rem;
        }
        .ea-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin-top: 0.55rem;
        }
        .ea-legend-item {
            align-items: center;
            border: 1px solid var(--ea-line);
            border-radius: 999px;
            color: var(--ea-muted);
            display: inline-flex;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.65rem;
            gap: 0.3rem;
            padding: 0.22rem 0.45rem;
            white-space: nowrap;
        }
        @media (max-width: 1200px) {
            .main .block-container { padding: 1.2rem 1rem 3rem; }
            .ea-title { font-size: 2rem; }
            .ea-run-metrics,
            .ea-trace-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .ea-run-state,
            .ea-run-metric,
            .ea-run-id,
            .ea-trace-metrics > div { border-right: 0; }
        }
        @media (max-width: 900px) {
            .ea-teaching-head {
                align-items: flex-start;
                flex-direction: column;
                gap: 0.55rem;
            }
            .ea-teaching-head h2 { font-size: 1.3rem; }
            .ea-concept-band { padding: 0.55rem; }
            [data-testid="stExpandSidebarButton"] {
                align-items: center !important;
                background: var(--ea-surface-3) !important;
                border: 1px solid var(--ea-line-strong) !important;
                border-radius: 7px !important;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.28) !important;
                color: var(--ea-text-soft) !important;
                display: inline-flex !important;
                gap: 0.35rem !important;
                height: 2rem !important;
                min-width: 7.25rem !important;
                padding: 0 0.65rem !important;
            }
            [data-testid="stExpandSidebarButton"]::after {
                color: var(--ea-text-soft);
                content: "Agent 配置";
                font-size: 0.74rem;
                font-weight: 700;
                letter-spacing: 0;
                line-height: 1;
                white-space: nowrap;
            }
            [data-testid="stExpandSidebarButton"] span {
                color: var(--ea-cyan) !important;
            }
            [data-testid="stExpandSidebarButton"]:hover {
                background: var(--ea-surface-raised) !important;
                border-color: var(--ea-cyan) !important;
                color: var(--ea-text) !important;
            }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )
