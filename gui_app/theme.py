"""Black & white visual system for the bapipe dashboard.

Ports the reference design system's spacing/typography/structure but substitutes
every colour for greyscale: primary/active = #111, white surfaces, grey
neutrals. No blue accent. Charts differentiate groups with grey lightness steps
and hatch patterns (never hue).
"""
import streamlit as st

# Grey ramp used for group series in charts (dark -> light).
_GREY_RAMP = ["#111111", "#444444", "#777777", "#a5a5a5", "#cccccc"]
_HATCHES = ["", "///", "...", "xxx", "\\\\\\", "+++", "ooo"]


def group_greys(n):
    """Return n (hex, hatch) pairs. Colours cycle the grey ramp; hatch advances
    once per full ramp cycle so groups beyond the ramp stay distinguishable."""
    out = []
    for i in range(n):
        color = _GREY_RAMP[i % len(_GREY_RAMP)]
        hatch = _HATCHES[(i // len(_GREY_RAMP)) % len(_HATCHES)]
        out.append((color, hatch))
    return out


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
:root{
  --font-sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --font-mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  --ink:#111111; --body:#333333; --muted:#777777; --faint:#a0a0a0;
  --canvas:#fafafa; --card:#ffffff; --sunken:#f4f4f4;
  --border:#e0e0e0; --border-strong:#cccccc;
  --radius:10px;
  /* Indigo accent — UI signals only (buttons/links/active/focus), never chart data. */
  --accent:#4F46E5; --accent-hover:#4338CA; --accent-weak:#EEF0FD; --on-accent:#ffffff;
  --focus:#4F46E5;
  --success:#1c6a2e; --success-weak:#e7f6ec;
  --warning:#8a5a00; --warning-weak:#fff4e0;
  --danger:#a11b1b;  --danger-weak:#fdecec;
}
html, body, [class*="css"]{ font-family:var(--font-sans); color:var(--body); }
.stApp{ background:var(--canvas); }
/* hide the sidebar entirely (turned off for this redesign) */
section[data-testid="stSidebar"]{ display:none !important; }
div[data-testid="collapsedControl"]{ display:none !important; }
[data-testid="stStatusWidget"]{ display:none !important; }
/* Buttons: default = neutral outline; primary (type="primary") = indigo accent. */
div.stButton > button{
  font-family:var(--font-sans); border-radius:var(--radius);
}
div.stButton > button[kind="secondary"]{
  background:var(--card); color:var(--ink); border:1px solid var(--border-strong);
}
div.stButton > button[kind="secondary"]:hover{
  background:var(--sunken); border-color:var(--ink);
}
div.stButton > button[kind="primary"]{
  background:var(--accent); color:var(--on-accent); border:1px solid var(--accent);
}
div.stButton > button[kind="primary"]:hover{
  background:var(--accent-hover); border-color:var(--accent-hover);
}
/* Links + interactive accents */
a, a:visited{ color:var(--accent); }
a:hover{ color:var(--accent-hover); }
/* Visible keyboard focus ring */
:focus-visible{ outline:2px solid var(--focus); outline-offset:2px; border-radius:6px; }
/* Active tab underline in accent */
button[data-baseweb="tab"][aria-selected="true"]{ color:var(--ink); box-shadow:inset 0 -2px 0 var(--accent); }
h1,h2,h3,h4{ color:var(--ink); letter-spacing:-0.02em; }
.mono{ font-family:var(--font-mono); }
.eyebrow{ font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.bw-card{ background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:0 1px 2px rgba(0,0,0,.06); padding:16px; margin-bottom:16px; }
.bw-card h4{ margin:0 0 8px 0; font-size:15px; }
.stat-tile{ background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; }
.stat-tile .label{ font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.stat-tile .value{ font-family:var(--font-mono); font-size:30px; font-weight:600; color:var(--ink); line-height:1.1; }
.stat-tile .unit{ font-family:var(--font-mono); font-size:14px; color:var(--muted); margin-left:4px; }
.stat-tile .note{ font-size:12px; color:var(--faint); margin-top:2px; }
.topbar{ display:flex; align-items:center; gap:14px; padding:10px 0 12px; border-bottom:1px solid var(--border); margin-bottom:18px; }
.topbar .title{ font-size:20px; font-weight:700; color:var(--ink); }
.topbar .sub{ font-size:12px; color:var(--muted); }
.avatar{ width:30px;height:30px;border-radius:50%;background:var(--ink);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600; }
/* Account chip: strip the markdown container's default spacing so the name row's
   centre line matches the logout button (both 40px, column-centred). */
[data-testid="stMarkdownContainer"]:has(.acct-chip){ margin:0; padding:0; }
/* KPI tile row (Overview): responsive grid of stat tiles. */
.kpi-grid{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr));
  gap:12px; margin:4px 0 18px; }
/* Left nav (analysis phase): vertical list, accent-tinted active item. */
.navwrap [role="radiogroup"]{ gap:2px; }
.navwrap [role="radiogroup"] > label{ padding:8px 12px; border-radius:8px; margin:0; width:100%; }
.navwrap [role="radiogroup"] > label:hover{ background:var(--sunken); }
.navwrap [role="radiogroup"] > label:has(input:checked){
  background:var(--accent-weak); color:var(--accent); font-weight:600; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def card(title, body_html, eyebrow=None, sub=None):
    eb = f'<div class="eyebrow">{eyebrow}</div>' if eyebrow else ""
    sb = f'<div class="sub">{sub}</div>' if sub else ""
    return (f'<div class="bw-card">{eb}<h4>{title}</h4>{sb}{body_html}</div>')


def stat_tile(label, value, unit=None, note=None):
    u = f'<span class="unit">{unit}</span>' if unit else ""
    n = f'<div class="note">{note}</div>' if note else ""
    return (f'<div class="stat-tile"><div class="label">{label}</div>'
            f'<div class="value">{value}{u}</div>{n}</div>')
