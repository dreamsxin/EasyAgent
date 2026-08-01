"""Visual research-console theme (CSS) for the EasyAgent visual lab.

Streamlit is passed in as a parameter rather than imported at module level so
that importing this module never hard-fails when the ``visual`` extra is
absent.
"""

from __future__ import annotations

from typing import Any

__all__ = ["inject_theme"]


def inject_theme(st: Any) -> None:
    """Apply the visual research-console theme without changing Streamlit semantics.

    The theme defaults to dark.  A small JavaScript probe reads Streamlit's
    computed background and sets ``data-ea-theme="light"`` or ``"dark"`` on the
    ``<html>`` element so that light-mode overrides can fix color conflicts
    when the user selects Streamlit's Light theme.
    """
    st.markdown(
        """
        <style>
        :root {
            --ea-bg: #080c12;
            --ea-surface: #101823;
            --ea-surface-2: #141f2c;
            --ea-surface-3: #1a2a3c;
            --ea-surface-raised: #22384e;
            --ea-input-bg: #f7fbff;
            --ea-input-text: #172434;
            --ea-line: #253447;
            --ea-line-strong: #526d89;
            --ea-text: #e8f0f7;
            --ea-text-soft: #d6e2ee;
            --ea-muted: #8ea0b4;
            --ea-muted-strong: #a9bdd0;
            --ea-cyan: #5de4ff;
            --ea-magenta: #e68cff;
            --ea-lime: #b6f36b;
            --ea-amber: #ffc36b;
        }
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
            background: rgba(8, 12, 18, 0.92);
        }
        [data-testid="stSidebar"] {
            background: #0c121b;
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
            color: #c6d3e1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: #8295aa !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            border-color: #3a5068;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            background: #111d2a;
            border: 1px solid #3a5068;
            border-radius: 8px;
            margin: 0.45rem 0 0.7rem;
            overflow: hidden;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] details[open] {
            background: #142638;
            border-color: var(--ea-cyan);
            box-shadow: inset 0 2px 0 rgba(93, 228, 255, 0.65);
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            background: #182b3e;
            color: var(--ea-text) !important;
            font-weight: 700;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
            background: #203a52;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            background: #142638;
        }
        /* Keep the native Streamlit controls legible across light and dark browser themes. */
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
            color: #ffffff !important;
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
            color: #ffffff !important;
        }
        [data-baseweb="popover"] input {
            background: var(--ea-input-bg) !important;
            color: var(--ea-input-text) !important;
        }
        [data-baseweb="tag"] {
            background: #dceaf5 !important;
            border: 1px solid #8ba3ba !important;
            color: var(--ea-input-text) !important;
        }
        [data-baseweb="tag"] > span:first-child,
        [data-baseweb="tag"] svg {
            color: var(--ea-input-text) !important;
            fill: var(--ea-input-text) !important;
        }
        [data-baseweb="tag"]:hover {
            background: #c9deec !important;
            border-color: #5f7c98 !important;
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
            color: #ffffff !important;
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
            font-size: 0.92rem;
            margin-top: 0.55rem;
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
        .ea-chip.live { border-color: #3c8c7a; color: var(--ea-lime); }
        .ea-chip.trace { border-color: #76538f; color: var(--ea-magenta); }
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
            background: #0c131d;
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
            border-right: 1px solid #1d2a39;
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
            color: #62758b;
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
        .ea-state-running { border-color: #3c8c7a; }
        .ea-state-running .ea-run-state strong { color: var(--ea-lime); }
        .ea-state-complete { border-color: #5c4b83; }
        .ea-state-complete .ea-run-state strong { color: var(--ea-magenta); }
        .ea-state-error { border-color: #9a4b54; }
        .ea-state-error .ea-run-state strong { color: #ff8c8c; }
        .ea-run-error {
            border-top: 1px solid #6b353e;
            color: #ff9a9a;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            grid-column: 1 / -1;
            overflow-wrap: anywhere;
            padding: 0.5rem 0.6rem 0.1rem;
        }
        .ea-timeline {
            background: #0c131d;
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            padding: 0.55rem 0.75rem;
        }
        .ea-timeline-row {
            display: grid;
            grid-template-columns: 2rem 1.6rem minmax(0, 1fr);
            gap: 0.65rem;
            padding: 0.65rem 0.1rem;
            border-bottom: 1px solid #1d2a39;
        }
        .ea-timeline-row:last-child { border-bottom: 0; }
        .ea-timeline-index {
            color: #53677d;
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
        .ea-loop_detected { color: #ff8c8c; }
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
            color: #b8c7d6;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.75rem;
            line-height: 1.4;
            margin-top: 0.22rem;
            overflow-wrap: anywhere;
        }
        .ea-execution-map {
            background: #0b131d;
            border: 1px solid #30455b;
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
            border-bottom: 1px solid #1f3042;
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
        .ea-map-heading small { color: #62758b; font-size: 0.58rem; letter-spacing: 0.08em; }
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
            color: #516a82;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.65rem;
            padding-top: 0.55rem;
        }
        .ea-flow-node {
            align-items: center;
            background: #121e2b;
            border: 1px solid #486079;
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
        .ea-flow-error .ea-flow-node { border-radius: 7px; color: #ff8c8c; }
        .ea-flow-approval_request .ea-flow-node { border-radius: 7px; color: var(--ea-amber); }
        .ea-flow-loop_detected .ea-flow-node { border-radius: 7px; color: #ff8c8c; }
        .ea-flow-user .ea-flow-node { color: var(--ea-cyan); }
        .ea-flow-copy { min-width: 0; padding: 0.22rem 0.2rem 0.8rem 0.55rem; }
        .ea-flow-code {
            color: #6e849a;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.61rem;
            font-weight: 700;
            letter-spacing: 0.1em;
        }
        .ea-flow-code span { color: #4e6478; float: right; font-size: 0.56rem; }
        .ea-flow-copy strong {
            color: var(--ea-text);
            display: block;
            font-size: 0.8rem;
            margin-top: 0.14rem;
        }
        .ea-flow-copy small {
            color: #9ab0c4;
            display: block;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            line-height: 1.35;
            margin-top: 0.12rem;
            overflow-wrap: anywhere;
        }
        .ea-flow-connector {
            border-left: 1px solid #38516a;
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
            border: 1px solid #38516a;
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
        .ea-arch-node-answer .ea-arch-node-icon { color: var(--ea-magenta); transform: rotate(45deg); }
        .ea-arch-node-answer .ea-arch-node-icon span { display: inline-block; transform: rotate(-45deg); }
        .ea-arch-node-router .ea-arch-node-icon { color: var(--ea-amber); border-radius: 7px; }
        .ea-arch-empty {
            background: #0c131d;
            border: 1px dashed var(--ea-line);
            border-radius: 8px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
            padding: 1rem;
            text-align: center;
        }
        @media (prefers-reduced-motion: reduce) {
            .ea-arch-node-wrap { animation: none; }
        }
        .ea-empty {
            background: #0c131d;
            border: 1px dashed var(--ea-line);
            border-radius: 8px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
            padding: 1rem;
        }
        .ea-trace-metrics {
            align-items: stretch;
            background: #0c131d;
            border: 1px solid #3c5068;
            border-radius: 8px;
            display: grid;
            gap: 0.45rem;
            grid-template-columns: repeat(8, minmax(0, 1fr));
            margin: 0.75rem 0;
            padding: 0.55rem;
        }
        .ea-trace-metrics > div {
            border-right: 1px solid #1d2a39;
            min-width: 0;
            padding: 0.2rem 0.55rem;
        }
        .ea-trace-metrics > div:last-child { border-right: 0; }
        .ea-trace-metrics span,
        .ea-compare-run-head span,
        .ea-compare-prompt span,
        .ea-compare-grid-metrics span {
            color: #62758b;
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
            background: #0c131d;
            border: 1px solid #33485e;
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
            border-top: 1px solid #1d2a39;
            margin-top: 0.7rem;
            padding-top: 0.55rem;
        }
        .ea-compare-prompt p {
            color: #b8c7d6;
            font-size: 0.78rem;
            line-height: 1.45;
            margin: 0.3rem 0 0;
            overflow-wrap: anywhere;
        }
        [data-testid="stCode"] {
            background: #0c131d;
            border: 1px solid #33485e;
            border-radius: 8px;
        }
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {
            background: #0c131d !important;
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
            border: 1px solid #33485e;
            border-radius: 7px;
            color: var(--ea-text);
            font-weight: 650;
        }
        .stButton > button:hover {
            background: #1c2e40;
            border-color: var(--ea-cyan);
            color: #ffffff;
        }
        .stButton > button:disabled,
        [data-testid="stButton"] button:disabled {
            background: #162231 !important;
            border-color: #2a3b4d !important;
            color: #71869a !important;
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
            color: #ffffff !important;
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
            color: #ffffff !important;
        }
        [data-testid="stMetric"] label,
        [data-testid="stMetric"] [data-testid="stMetricLabel"] p {
            color: var(--ea-muted-strong) !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #ffffff !important;
        }
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {
            color: #dbe8f4 !important;
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
            background: #0f1722;
            border: 1px solid #213044;
            border-radius: 8px;
            margin-bottom: 0.55rem;
        }
        [data-testid="stChatInput"] {
            border-color: #33485e;
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
            .ea-run-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .ea-run-state,
            .ea-run-metric,
            .ea-run-id { border-right: 0; }
        }
        @media (max-width: 900px) {
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
                color: #ffffff !important;
            }
        }

        /* ===========================================================
           Light-mode overrides
           The dark theme above forces dark backgrounds and light text
           with !important.  When Streamlit is in Light mode these clash
           (light text on Streamlit's light native widgets).  The JS probe
           at the bottom sets data-ea-theme="light" on <html>; these rules
           override the dark forces with light-appropriate values.
           =========================================================== */
        [data-ea-theme="light"] .stApp,
        [data-ea-theme="light"] [data-testid="stAppViewContainer"],
        [data-ea-theme="light"] [data-testid="stMain"],
        [data-ea-theme="light"] [data-testid="stMainBlockContainer"] {
            background: #f4f7fa !important;
            color: #1a2735 !important;
        }
        [data-ea-theme="light"] .main .block-container,
        [data-ea-theme="light"] .main .block-container p,
        [data-ea-theme="light"] .main .block-container li,
        [data-ea-theme="light"] .main .block-container h1,
        [data-ea-theme="light"] .main .block-container h2,
        [data-ea-theme="light"] .main .block-container h3,
        [data-ea-theme="light"] .main .block-container h4,
        [data-ea-theme="light"] .main .block-container label,
        [data-ea-theme="light"] [data-testid="stWidgetLabel"] p {
            color: #2a3a4e !important;
        }
        [data-ea-theme="light"] .main .block-container a {
            color: #1a8cb8 !important;
        }
        [data-ea-theme="light"] [data-testid="stCaptionContainer"] p,
        [data-ea-theme="light"] [data-testid="stCaptionContainer"] small {
            color: #5a6e82 !important;
        }
        [data-ea-theme="light"] [data-testid="stHeader"] {
            background: rgba(244, 247, 250, 0.92) !important;
        }
        [data-ea-theme="light"] [data-testid="stHeader"] button,
        [data-ea-theme="light"] [data-testid="stToolbar"] button {
            color: #2a3a4e !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] {
            background: #e9eef4 !important;
            border-right: 1px solid #c5d2de !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] h1,
        [data-ea-theme="light"] [data-testid="stSidebar"] h2,
        [data-ea-theme="light"] [data-testid="stSidebar"] h3,
        [data-ea-theme="light"] [data-testid="stSidebar"] label,
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: #2a3a4e !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: #5a6e82 !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-ea-theme="light"] [data-testid="stSidebar"] input,
        [data-ea-theme="light"] [data-testid="stSidebar"] textarea {
            background: #ffffff !important;
            border-color: #b0c0d0 !important;
            color: #1a2735 !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-testid="stExpander"] {
            background: #dde5ee !important;
            border-color: #c5d2de !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-testid="stExpander"] details[open] {
            border-color: #1a8cb8 !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            color: #2a3a4e !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
            background: #d0dae8 !important;
        }
        [data-ea-theme="light"] [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            background: #e2e9f0 !important;
        }
        /* Keep input fields readable in light mode. */
        [data-ea-theme="light"] [data-baseweb="input"] > div,
        [data-ea-theme="light"] [data-baseweb="textarea"] > div,
        [data-ea-theme="light"] [data-baseweb="select"] > div,
        [data-ea-theme="light"] [data-testid="stChatInput"] > div {
            background: #ffffff !important;
            border-color: #b0c0d0 !important;
            color: #1a2735 !important;
        }
        [data-ea-theme="light"] [data-baseweb="input"] input,
        [data-ea-theme="light"] [data-baseweb="textarea"] textarea,
        [data-ea-theme="light"] [data-baseweb="select"] input,
        [data-ea-theme="light"] [data-testid="stChatInput"] textarea {
            background: #ffffff !important;
            caret-color: #1a2735 !important;
            color: #1a2735 !important;
            -webkit-text-fill-color: #1a2735 !important;
        }
        [data-ea-theme="light"] [data-baseweb="input"] input::placeholder,
        [data-ea-theme="light"] [data-baseweb="textarea"] textarea::placeholder,
        [data-ea-theme="light"] [data-testid="stChatInput"] textarea::placeholder {
            color: #8a9bad !important;
            -webkit-text-fill-color: #8a9bad !important;
        }
        [data-ea-theme="light"] [data-baseweb="select"] span,
        [data-ea-theme="light"] [data-baseweb="select"] svg {
            color: #1a2735 !important;
            fill: #1a2735 !important;
        }
        [data-ea-theme="light"] [data-testid="stNumberInput"] button {
            background: #eef3f8 !important;
            border-color: #b0c0d0 !important;
            color: #1a2735 !important;
        }
        [data-ea-theme="light"] [data-testid="stNumberInput"] button:hover {
            background: #dde7f0 !important;
            color: #0b1724 !important;
        }
        [data-ea-theme="light"] [data-baseweb="popover"],
        [data-ea-theme="light"] [data-baseweb="popover"] > div,
        [data-ea-theme="light"] [data-baseweb="menu"],
        [data-ea-theme="light"] [role="listbox"] {
            background: #ffffff !important;
            border: 1px solid #c5d2de !important;
            color: #1a2735 !important;
        }
        [data-ea-theme="light"] [data-baseweb="menu"] li,
        [data-ea-theme="light"] [role="option"] {
            color: #2a3a4e !important;
        }
        [data-ea-theme="light"] [data-baseweb="menu"] li:hover,
        [data-ea-theme="light"] [role="option"]:hover,
        [data-ea-theme="light"] [role="option"][aria-selected="true"] {
            background: #e2e9f0 !important;
            color: #0b1724 !important;
        }
        [data-ea-theme="light"] [data-testid*="VirtualDropdown"] {
            background: #ffffff !important;
            border: 1px solid #c5d2de !important;
            color: #1a2735 !important;
        }
        [data-ea-theme="light"] [data-testid*="VirtualDropdown"] li > div,
        [data-ea-theme="light"] [data-testid*="VirtualDropdown"] li > div > div {
            color: #2a3a4e !important;
        }
        [data-ea-theme="light"] [data-testid*="VirtualDropdown"] li:hover,
        [data-ea-theme="light"] [data-testid*="VirtualDropdown"] li[aria-selected="true"] {
            background: #e2e9f0 !important;
            color: #0b1724 !important;
        }
        [data-ea-theme="light"] [data-baseweb="tag"] {
            background: #e2e9f0 !important;
            border: 1px solid #b0c0d0 !important;
            color: #1a2735 !important;
        }
        [data-ea-theme="light"] [data-baseweb="tag"] > span:first-child,
        [data-ea-theme="light"] [data-baseweb="tag"] svg {
            color: #1a2735 !important;
        }
        /* Light-mode surfaces for custom EA components. */
        [data-ea-theme="light"] {
            --ea-bg: #f4f7fa;
            --ea-surface: #ffffff;
            --ea-surface-2: #eef3f8;
            --ea-surface-3: #e2e9f0;
            --ea-surface-raised: #d0dae8;
            --ea-line: #c5d2de;
            --ea-line-strong: #8a9bad;
            --ea-text: #1a2735;
            --ea-text-soft: #2a3a4e;
            --ea-muted: #5a6e82;
            --ea-muted-strong: #4a5e72;
            --ea-cyan: #1a8cb8;
            --ea-magenta: #a846bc;
            --ea-lime: #5a9e2e;
            --ea-amber: #c4842e;
        }
        </style>
        <script>
        // Probe Streamlit's rendered background to detect light vs dark mode.
        // Streamlit does not expose its runtime theme to the Python script, so
        // we read the computed background-color of the app container and set
        // data-ea-theme on <html>.  The probe runs on load and on DOM mutations
        // so theme switches are picked up without a full reload.
        (function () {
            function detectTheme() {
                var el = document.querySelector('[data-testid="stAppViewContainer"]')
                         || document.querySelector('.stApp');
                if (!el) return;
                var bg = window.getComputedStyle(el).backgroundColor;
                // Parse "rgb(r, g, b)" and compute luminance.
                var m = bg.match(/\\d+/g);
                if (!m || m.length < 3) return;
                var lum = (0.299 * +m[0] + 0.587 * +m[1] + 0.114 * +m[2]) / 255;
                var theme = lum > 0.5 ? 'light' : 'dark';
                document.documentElement.setAttribute('data-ea-theme', theme);
            }
            // Run once on load, then watch for Streamlit re-renders.
            if (document.readyState !== 'loading') {
                detectTheme();
            } else {
                document.addEventListener('DOMContentLoaded', detectTheme);
            }
            // Re-probe periodically for the first few seconds (Streamlit renders
            // asynchronously), then settle on a MutationObserver.
            var tries = 0;
            var interval = setInterval(function () {
                detectTheme();
                if (++tries >= 8) clearInterval(interval);
            }, 500);
            var observer = new MutationObserver(function () { detectTheme(); });
            observer.observe(document.body, { childList: true, subtree: true });
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )
