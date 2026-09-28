from __future__ import annotations
import streamlit as st


THEME_STATE_KEY = "_ks_dark_mode"


_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600;700&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap');"
)


_LIGHT_TOKENS = """
:root {
  --ks-bg:            #f6f9fc;   /* soft tinted background (NOT pure white) */
  --ks-surface:       #ffffff;   /* cards float white on the tinted bg */
  --ks-surface-alt:   #f6f9fc;
  --ks-surface-muted: #eef2f8;
  --ks-border:        #e3e8ee;
  --ks-border-strong: #c8d1dc;
  --ks-text:          #0a2540;
  --ks-text-muted:    #425466;
  --ks-text-faint:    #8898aa;
  --ks-accent:        #3b5b7a;   /* muted slate-blue chrome accent (D-112) */
  --ks-accent-soft:   rgba(59,91,122,0.10);
  --ks-accent-hover:  #2f4a64;
  --ks-success:       #0a875a;
  --ks-danger:        #df1b41;
  --ks-warn:          #bb5504;
  --ks-inf:           #5048e5;
  --ks-cav:           #067f97;
  --ks-arc:           #0a875a;
  --ks-radius:        8px;
  --ks-radius-sm:     6px;
  --ks-shadow-card:   0 0 0 1px rgba(10,37,64,0.06), 0 1px 3px rgba(10,37,64,0.04);
  --ks-shadow:        0 1px 2px rgba(10,37,64,0.05);
}
"""

_DARK_TOKENS = """
:root {
  --ks-bg:            #0b1220;   /* deep navy app background (NOT pure black) */
  --ks-surface:       #131c2e;   /* cards float slightly lighter than the bg */
  --ks-surface-alt:   #0f1827;
  --ks-surface-muted: #1b2740;
  --ks-border:        #263449;
  --ks-border-strong: #3a4d68;
  --ks-text:          #e6ebf2;   /* near-white, cool tint */
  --ks-text-muted:    #9aabc0;
  --ks-text-faint:    #6b7c93;
  --ks-accent:        #7ea3c4;   /* brighter slate-blue for contrast on dark bg */
  --ks-accent-soft:   rgba(126,163,196,0.16);
  --ks-accent-hover:  #96b6d2;
  --ks-success:       #3ecf8e;
  --ks-danger:        #ff5c77;
  --ks-warn:          #e8a04a;
  --ks-inf:           #8a83ff;
  --ks-cav:           #2bb8d4;
  --ks-arc:           #3ecf8e;
  --ks-radius:        8px;
  --ks-radius-sm:     6px;
  --ks-shadow-card:   0 0 0 1px rgba(255,255,255,0.05), 0 1px 3px rgba(0,0,0,0.45);
  --ks-shadow:        0 1px 2px rgba(0,0,0,0.35);
}
"""


_BASE_CSS = """
/* ---------- HIDE Streamlit chrome (decorations) — but keep sidebar toggle accessible ----------
 *
 * Bug fix: the old rules hid `[data-testid="stHeader"]` and `stToolbar`
 * entirely (`display:none`). Streamlit renders the "open sidebar" arrow
 * inside that subtree when the sidebar is collapsed, so closing the
 * sidebar made it impossible to re-open without a hard refresh.
 *
 * Fix: keep stHeader in the layout (transparent, zero-height) so the
 * collapse/expand button stays clickable; only hide the *decorative*
 * children (menu, status widget, colored decoration bar).
 */
[data-testid="stHeader"], header[data-testid="stHeader"] {
  background: transparent !important;
  height: 0 !important;
  min-height: 0 !important;
  padding: 0 !important;
}
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
#MainMenu {
  display: none !important;
  visibility: hidden !important;
}
/* Keep the sidebar collapse / expand controls visible and on top. Streamlit
 * 1.58 renamed these: stExpandSidebarButton = the "open" button shown when the
 * sidebar is collapsed; stSidebarCollapseButton = the "close" button inside the
 * sidebar. (The old stSidebarCollapsedControl / collapsedControl ids no longer
 * exist — targeting them was a no-op, which is why the open button kept
 * clipping.) */
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"],
[data-testid="baseButton-headerNoPadding"] {
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  z-index: 1000000 !important;
}
/* The "open sidebar" button lives in our zero-height header, so it clipped ~2/3
 * off the top of the viewport on mobile (grey-on-navy). Pin it as a visible chip
 * INSIDE the viewport via fixed positioning (the header sets no overflow, so a
 * fixed child escapes it) and tint the glyph with the accent so it reads on both
 * palettes. Only shown when the sidebar is collapsed. */
[data-testid="stExpandSidebarButton"] {
  position: fixed !important;
  top: 0.5rem !important;
  left: 0.5rem !important;
  background: var(--ks-surface) !important;
  border: 1px solid var(--ks-border-strong) !important;
  border-radius: var(--ks-radius-sm) !important;
  box-shadow: var(--ks-shadow-card) !important;
  padding: 5px !important;
  height: auto !important;
  width: auto !important;
}
[data-testid="stExpandSidebarButton"]:hover {
  background: var(--ks-surface-alt) !important;
}
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stExpandSidebarButton"] svg *,
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
  color: var(--ks-accent) !important;
  fill: var(--ks-accent) !important;
}
/* Header must never clip the fixed button (defensive — it has no overflow today,
 * but pin it so a future Streamlit default can't reintroduce the clip). */
[data-testid="stHeader"], header[data-testid="stHeader"] { overflow: visible !important; }
footer { visibility: hidden; }
[data-testid="stAppViewContainer"] > .main, section.main { padding-top: 0 !important; }
[data-testid="stMain"] { padding-top: 1rem !important; }

/* ---------- Global background: SOFT TINTED, not pure white ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: var(--ks-bg) !important;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  color: var(--ks-text);
  -webkit-font-smoothing: antialiased;
}
.main .block-container, [data-testid="stMain"] .block-container {
  padding: 1.5rem 2.5rem 3rem !important;
  max-width: 1400px;
}

/* ---------- Typography ---------- */
h1, h2, h3, h4, h5, h6 {
  color: var(--ks-text) !important;
  font-family: 'Inter', system-ui, sans-serif !important;
  font-weight: 600 !important;
}
h1 { font-size: 28px !important; font-weight: 700 !important; letter-spacing: -0.02em !important; }
h2 { font-size: 22px !important; letter-spacing: -0.015em !important; }
h3 { font-size: 17px !important; letter-spacing: -0.01em !important; }
h4 { font-size: 14px !important; }
h5 { font-size: 13px !important; color: var(--ks-text-muted) !important; text-transform: uppercase; letter-spacing: 0.04em !important; font-weight: 600 !important; }

p, label, .stMarkdown, [data-testid="stMarkdownContainer"] p {
  color: var(--ks-text);
  line-height: 1.6;
}
[data-testid="stCaptionContainer"], .stCaption, small {
  color: var(--ks-text-muted) !important;
  font-size: 13px;
}

/* ---------- Code blocks — readable navy on soft surface ---------- */
code, pre, pre code {
  font-family: 'JetBrains Mono', ui-monospace, monospace !important;
  font-size: 13px;
}
pre {
  background: var(--ks-surface-muted) !important;
  border: 1px solid var(--ks-border) !important;
  border-radius: var(--ks-radius-sm) !important;
  padding: 14px 16px !important;
  margin: 8px 0 !important;
  overflow-x: auto !important;
}
/* KILL Prism's pale syntax tokens — force everything to navy text */
pre code, pre code *, pre *,
[data-testid="stMarkdownContainer"] pre,
[data-testid="stMarkdownContainer"] pre * {
  color: var(--ks-text) !important;
  background: transparent !important;
  text-shadow: none !important;
}
/* Inline code (single backticks) — subtle purple tint */
:not(pre) > code {
  color: var(--ks-accent) !important;
  background: var(--ks-accent-soft) !important;
  padding: 2px 6px !important;
  font-size: 0.92em !important;
  border-radius: 4px !important;
}

a { color: var(--ks-accent); text-decoration: none; font-weight: 500; }
a:hover { color: var(--ks-accent-hover); text-decoration: underline; }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
  background: var(--ks-surface) !important;
  border-right: 1px solid var(--ks-border);
}
section[data-testid="stSidebar"] > div:first-child {
  padding-top: 22px !important;
  padding-left: 18px !important;
  padding-right: 18px !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
  color: var(--ks-text) !important;
}
section[data-testid="stSidebar"] hr {
  border-color: var(--ks-border) !important;
  margin: 1rem 0 !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] > p:empty {
  display: none;
}

/* ---------- Sidebar navigation (grouped, flat nav list) ----------
 * Tool selection lives in the sidebar (app._render_sidebar_nav): a column of
 * st.button items under uppercase area headers. Flatten those buttons into a
 * left-aligned nav list and tint the ACTIVE (primary-styled) item softly,
 * instead of the heavy filled-purple default. The only buttons in the sidebar
 * are the nav, so scoping these rules to the sidebar is safe. */
.ks-nav-group {
  font-size: 10px; font-weight: 700; letter-spacing: 0.09em;
  text-transform: uppercase; color: var(--ks-text-faint);
  margin: 16px 0 3px 2px;
}
section[data-testid="stSidebar"] .stButton > button {
  justify-content: flex-start !important;
  text-align: left !important;
  background: transparent !important;
  color: var(--ks-text-muted) !important;
  border: 1px solid transparent !important;
  box-shadow: none !important;
  font-weight: 500 !important;
  padding: 8px 12px !important;
  margin: 1px 0 !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: var(--ks-surface-alt) !important;
  color: var(--ks-text) !important;
}
section[data-testid="stSidebar"] button[kind="primary"],
section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
  background: var(--ks-accent-soft) !important;
  color: var(--ks-accent) !important;
  border: 1px solid transparent !important;
  box-shadow: none !important;
  font-weight: 600 !important;
}
section[data-testid="stSidebar"] button[kind="primary"]:hover,
section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover {
  background: var(--ks-accent-soft) !important;
  color: var(--ks-accent) !important;
}

/* ---------- Tabs ---------- */
[data-baseweb="tab-list"] {
  gap: 0 !important;
  border-bottom: 1px solid var(--ks-border) !important;
  padding-left: 4px !important;
  margin-bottom: 8px !important;
  background: transparent !important;
}
[data-baseweb="tab"] {
  background: transparent !important;
  color: var(--ks-text-muted) !important;
  font-weight: 500 !important;
  font-size: 13.5px !important;
  padding: 12px 18px !important;
  border-radius: 0 !important;
  border-bottom: 2px solid transparent !important;
  margin-bottom: -1px !important;
}
[data-baseweb="tab"]:hover { color: var(--ks-text) !important; }
[data-baseweb="tab"][aria-selected="true"] {
  color: var(--ks-text) !important;
  border-bottom-color: var(--ks-accent) !important;
  font-weight: 600 !important;
}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none !important; }

/* ---------- Lazy-tab nav (radio rendered as tabs) ----------
 * V8.8 mem: app.py uses st.radio() for navigation so only the active
 * tab's render() runs (st.tabs would render all bodies on each rerun).
 * Style the radio to look exactly like the native tab bar above.
 */
[data-testid="stRadio"][aria-label="Navigation"],
div[role="radiogroup"]:has(input[type="radio"][name*="_ks_active_tab"]) {
  border-bottom: 1px solid var(--ks-border) !important;
  padding-left: 0 !important;
  margin: 0 0 12px 0 !important;
  background: transparent !important;
}
/* The horizontal radio group itself */
[data-testid="stRadio"] > div[role="radiogroup"] {
  gap: 0 !important;
  flex-wrap: wrap !important;
  border-bottom: 1px solid var(--ks-border) !important;
  margin-bottom: 12px !important;
}
/* Each radio "tab" — kill the dot and bullet styling */
[data-testid="stRadio"] > div[role="radiogroup"] > label {
  background: transparent !important;
  color: var(--ks-text-muted) !important;
  font-weight: 500 !important;
  font-size: 13.5px !important;
  padding: 12px 18px !important;
  margin: 0 !important;
  border-radius: 0 !important;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  margin-bottom: -1px !important;
  cursor: pointer !important;
  white-space: nowrap !important;
  transition: color 0.12s ease, border-color 0.12s ease;
}
[data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
  color: var(--ks-text) !important;
}
/* Hide the radio circle entirely — only the label is interactive */
[data-testid="stRadio"] > div[role="radiogroup"] > label > div:first-child,
[data-testid="stRadio"] > div[role="radiogroup"] input[type="radio"],
[data-testid="stRadio"] > div[role="radiogroup"] [data-baseweb="radio"] > div:first-child {
  display: none !important;
}
/* Selected state — purple underline + dark text */
[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked),
[data-testid="stRadio"] > div[role="radiogroup"] > label[data-selected="true"] {
  color: var(--ks-text) !important;
  border-bottom-color: var(--ks-accent) !important;
  font-weight: 600 !important;
}
/* Hide the label "Navigation" itself when label_visibility=collapsed
 * (Streamlit already does this but force it for safety) */
[data-testid="stRadio"] > label:first-child {
  display: none !important;
}

/* ---------- Buttons ----------
 * Target the <button> by data-testid / kind, NOT the `.stButton > button`
 * direct-child chain. When a button carries help= text, Streamlit wraps it
 * in stTooltipHoverTarget/stTooltipIcon spans, so it is no longer a direct
 * child of .stButton; the old `>` selector missed it and the button kept
 * its default white background under our near-white text — invisible in
 * dark mode (the "Reset quiz" report). The data-testid lives on the button
 * itself and is unaffected by the tooltip wrapper. */
button[kind="primary"],
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--ks-accent) !important; color: white !important;
  border: 1px solid var(--ks-accent) !important;
  border-radius: var(--ks-radius-sm) !important;
  padding: 8px 16px !important; font-weight: 600 !important; font-size: 14px !important;
  box-shadow: var(--ks-shadow) !important;
}
button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover { background: var(--ks-accent-hover) !important; }

button[data-testid="stBaseButton-secondary"],
button[data-testid="stBaseButton-secondaryFormSubmit"],
.stButton > button:not([kind="primary"]) {
  background: var(--ks-surface) !important;
  color: var(--ks-text) !important;
  border: 1px solid var(--ks-border) !important;
  border-radius: var(--ks-radius-sm) !important;
  padding: 7px 14px !important; font-weight: 500 !important; font-size: 14px !important;
  box-shadow: var(--ks-shadow) !important;
}
button[data-testid="stBaseButton-secondary"]:hover,
button[data-testid="stBaseButton-secondaryFormSubmit"]:hover,
.stButton > button:not([kind="primary"]):hover {
  border-color: var(--ks-border-strong) !important;
  background: var(--ks-surface-alt) !important;
}

/* ---------- Inputs ---------- */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
[data-baseweb="input"] input, [data-baseweb="select"] > div,
[data-baseweb="textarea"] textarea {
  background: var(--ks-surface) !important;
  border: 1px solid var(--ks-border) !important;
  border-radius: var(--ks-radius-sm) !important;
  color: var(--ks-text) !important;
  font-family: 'Inter', system-ui, sans-serif !important;
  font-size: 14px !important;
}
.stTextInput input:focus, .stNumberInput input:focus,
[data-baseweb="input"] input:focus, [data-baseweb="textarea"] textarea:focus {
  border-color: var(--ks-accent) !important;
  box-shadow: 0 0 0 3px var(--ks-accent-soft) !important;
  outline: none !important;
}
[data-baseweb="popover"] [role="listbox"] {
  background: var(--ks-surface) !important;
  border: 1px solid var(--ks-border) !important;
  border-radius: var(--ks-radius) !important;
  box-shadow: var(--ks-shadow-card) !important;
}
[data-baseweb="popover"] [role="option"]:hover { background: var(--ks-surface-alt) !important; }

/* ---------- File uploader (screenshot upload boxes) ----------
 * Streamlit's default dropzone is light-filled; under our near-white
 * --ks-text it became white-on-white in dark mode. Drive every part from
 * tokens so it reads in both palettes. */
[data-testid="stFileUploader"] { color: var(--ks-text) !important; }
[data-testid="stFileUploaderDropzone"], section[data-testid="stFileUploaderDropzone"] {
  background: var(--ks-surface-alt) !important;
  border: 1px dashed var(--ks-border-strong) !important;
  border-radius: var(--ks-radius) !important;
  color: var(--ks-text-muted) !important;
}
[data-testid="stFileUploaderDropzoneInstructions"],
[data-testid="stFileUploaderDropzoneInstructions"] * {
  color: var(--ks-text-muted) !important;
}
/* "Browse files" button inside the dropzone — comes AFTER the muted rule
 * above so it wins, restoring full-contrast button text. */
[data-testid="stFileUploaderDropzone"] button {
  background: var(--ks-surface) !important;
  color: var(--ks-text) !important;
  border: 1px solid var(--ks-border) !important;
}
/* Uploaded-file chip row. */
[data-testid="stFileUploaderFile"],
[data-testid="stFileUploaderFile"] * { color: var(--ks-text) !important; }

/* ---------- Tooltips (the help "?" icons + their popups) ----------
 * The default icon glyph is #31333F (dark grey) — fine on white, nearly
 * invisible on the dark bg. The hover popup also needs token colours so
 * its text doesn't inherit our near-white --ks-text onto a light fill. */
[data-testid="stTooltipIcon"],
[data-testid="stTooltipIcon"] svg { color: var(--ks-text-faint) !important; }
[data-testid="stTooltipContent"] {
  background: var(--ks-surface) !important;
  border: 1px solid var(--ks-border) !important;
  border-radius: var(--ks-radius-sm) !important;
  box-shadow: var(--ks-shadow-card) !important;
}
[data-testid="stTooltipContent"],
[data-testid="stTooltipContent"] * { color: var(--ks-text) !important; }

.stSlider [data-baseweb="slider"] [role="slider"] {
  background: var(--ks-accent) !important; border-color: var(--ks-accent) !important;
}
.stSlider [data-baseweb="slider"] > div > div { background: var(--ks-accent) !important; }

.stRadio [role="radiogroup"] label[aria-checked="true"] [data-baseweb="radio"] > div:first-child,
.stCheckbox [role="checkbox"][aria-checked="true"] {
  background: var(--ks-accent) !important; border-color: var(--ks-accent) !important;
}

/* ---------- Expanders — FORCE visible header text always ---------- */
[data-testid="stExpander"] {
  border: 1px solid var(--ks-border) !important;
  border-radius: var(--ks-radius) !important;
  background: var(--ks-surface) !important;
  box-shadow: var(--ks-shadow) !important;
  margin-bottom: 0.85rem !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary *,
[data-testid="stExpander"] [data-testid="stExpanderHeader"],
[data-testid="stExpander"] [data-testid="stExpanderHeader"] *,
[data-testid="stExpander"] details > summary,
[data-testid="stExpander"] details > summary * {
  color: var(--ks-text) !important;
  background: transparent !important;
  font-weight: 500 !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] [data-testid="stExpanderHeader"] {
  padding: 12px 16px !important;
}
[data-testid="stExpander"] summary:hover,
[data-testid="stExpander"] [data-testid="stExpanderHeader"]:hover {
  background: var(--ks-surface-alt) !important;
}

/* ---------- Metrics ---------- */
[data-testid="stMetric"], [data-testid="metric-container"] {
  background: var(--ks-surface) !important;
  border: 1px solid var(--ks-border) !important;
  border-radius: var(--ks-radius) !important;
  padding: 16px !important;
  box-shadow: var(--ks-shadow) !important;
}
[data-testid="stMetricLabel"], [data-testid="stMetric"] label {
  color: var(--ks-text-muted) !important; font-size: 12px !important;
  font-weight: 500 !important; text-transform: uppercase; letter-spacing: 0.04em;
}
[data-testid="stMetricValue"] {
  color: var(--ks-text) !important; font-weight: 700 !important;
  font-size: 28px !important; letter-spacing: -0.02em !important;
}

/* ---------- DataFrames ---------- */
.stDataFrame, [data-testid="stDataFrame"] {
  border: 1px solid var(--ks-border) !important;
  border-radius: var(--ks-radius) !important;
  overflow: hidden; box-shadow: var(--ks-shadow) !important;
}

/* ---------- Alerts ---------- */
[data-testid="stAlert"], .stAlert {
  border-radius: var(--ks-radius) !important;
  border: 1px solid var(--ks-border) !important;
  box-shadow: var(--ks-shadow) !important;
  padding: 14px 16px !important;
  background: var(--ks-surface) !important;
}
[data-baseweb="notification"][kind="info"] { background: rgba(59,91,122,0.06) !important; border-color: rgba(59,91,122,0.20) !important; }
[data-baseweb="notification"][kind="positive"], .stSuccess { background: rgba(10,135,90,0.06) !important; border-color: rgba(10,135,90,0.20) !important; }
[data-baseweb="notification"][kind="warning"], .stWarning  { background: rgba(187,85,4,0.06)  !important; border-color: rgba(187,85,4,0.20)  !important; }
[data-baseweb="notification"][kind="negative"], .stError   { background: rgba(223,27,65,0.06) !important; border-color: rgba(223,27,65,0.20) !important; }

hr {
  border: none !important;
  border-top: 1px solid var(--ks-border) !important;
  margin: 1.5rem 0 !important;
}

.js-plotly-plot, [data-testid="stPlotlyChart"] {
  border-radius: var(--ks-radius) !important;
  border: 1px solid var(--ks-border) !important;
  box-shadow: var(--ks-shadow) !important;
  overflow: hidden; background: var(--ks-surface) !important;
}

[data-testid="stVerticalBlock"] { gap: 1.1rem !important; }

.stProgress > div > div > div > div { background: var(--ks-accent) !important; }
.stProgress > div > div > div { background: var(--ks-surface-muted) !important; border-radius: 4px !important; }

[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: var(--ks-border) !important;
  border-radius: var(--ks-radius) !important;
  background: var(--ks-surface) !important;
  box-shadow: var(--ks-shadow) !important;
  padding: 18px !important;
}

/* ---------- UX revamp: responsive helpers (T2/T4/T7/T18/T19) ----------
 *
 * Class contract (consumed by the inline-HTML primitives + tabs):
 *   .ks-topk-table  — the wide results table; hidden on mobile (T2)
 *   .ks-topk-cards  — the stacked-card fallback; hidden on desktop (T2)
 *   .ks-hide-mobile — desktop-only flourishes (e.g. hero-body art, T18)
 *
 * Defaults (desktop): table shown, cards hidden. The @media block below
 * inverts that under 768px.
 */
.ks-topk-cards { display: none; }
.ks-topk-table { display: block; }

/* ---------- Font floor (T7/T8) ----------
 * Inline HTML used 10-11px for body copy in a few primitives. Eyebrow /
 * uppercase section tags legitimately stay small; general body copy gets a
 * 12px floor so it stays legible on mobile. We can't rewrite every inline
 * style literal, so this is a backstop on the markdown container. */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li { font-size: 14px; }

/* ---------- Mobile breakpoint (T7) ---------- */
@media (max-width: 768px) {
  /* tighter page gutters so cards aren't squeezed */
  .main .block-container, [data-testid="stMain"] .block-container {
    padding: 1rem 1rem 2.5rem !important;
  }
  /* swap the top-K table for stacked cards (T2) */
  .ks-topk-table { display: none !important; }
  .ks-topk-cards { display: block !important; }
  /* hide desktop-only flourishes (T18) */
  .ks-hide-mobile { display: none !important; }
  /* compact horizontal radios (mode toggles, etc.) so they don't overflow */
  [data-testid="stRadio"] > div[role="radiogroup"] > label {
    padding: 9px 11px !important;
    font-size: 12.5px !important;
  }
  /* full-width primary buttons read better as tap targets */
  h1 { font-size: 23px !important; }
}
@media (min-width: 769px) {
  .ks-nav-mobile-hint { display: none; }
}
"""


def build_css(dark: bool = False) -> str:
    tokens = _DARK_TOKENS if dark else _LIGHT_TOKENS
    return f"<style>\n{_FONT_IMPORT}\n{tokens}\n{_BASE_CSS}\n</style>"


def inject(dark: bool = False) -> None:
    st.markdown(build_css(dark), unsafe_allow_html=True)
