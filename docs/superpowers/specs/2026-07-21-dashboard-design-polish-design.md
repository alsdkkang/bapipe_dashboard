# Dashboard Design Polish — Design (UI system + chart palettes)

**Date:** 2026-07-21
**Repo:** `bapipe-keypoints/`, branch `feature/dashboard-bw-redesign`
**App:** `gui_app/` — deployed live on Streamlit Community Cloud.

## Goal

Raise the dashboard's polish/professionalism **and** researcher usability, applied
**uniformly across all screens**, by (1) evolving the pure-B&W system into a
disciplined **B&W + one accent** design system, and (2) adding **user-selectable
chart/heatmap palettes** (presets + per-group overrides).

## Confirmed decisions

- **Accent color:** Indigo **`#4F46E5`** (hover `#4338CA`). Used ONLY for UI
  signals — primary buttons, active states, links, focus rings. Neutrals stay
  greyscale. Easily swappable (one token) once live.
- **Charts get color, user-controlled:** replace the forced greyscale with a
  palette the analyst picks — a **curated preset selector** (greyscale kept as the
  default preset for publication neutrality) **plus optional per-group color
  overrides**. Applies to categorical group series (bar charts) and the heatmap's
  sequential colormap.
- **Uniform scope:** foundation tokens first, then every screen.
- **Light theme only** (no dark mode this pass).

## Scope

**In scope:** design tokens (accent + semantic + type/space), primary/secondary
button distinction, links/active-tab/focus states, state-feedback consistency,
empty-state cleanup, per-screen application, and the chart-palette feature.

**Out of scope:** dark mode, new analyses/features beyond the palette control,
auth/deploy changes, restructuring analysis logic.

## Current state (grounding)

- `gui_app/theme.py` holds a CSS token system in `:root`
  (`--ink #111`, `--body #333`, `--muted #777`, `--faint #a0a0a0`,
  `--canvas #fafafa`, `--card #fff`, `--sunken #f4f4f4`, `--border #e0e0e0`,
  `--border-strong #ccc`, `--radius 10px`), IBM Plex Sans/Mono, and
  `group_greys(n)` (grey ramp + hatches) used by charts.
- **All buttons are forced black** by `div.stButton > button{ background:var(--ink) }`
  — no primary/secondary distinction.
- `gui_app/.streamlit/config.toml` currently sets only `[browser]` + `[theme] base`
  (no `primaryColor`).
- Stray/ad-hoc colors in `app.py`: records empty-state text `#2f6df0` (a lone
  blue — remove); status tiles at ~L804-805 use green/red/amber hexes
  (`#e7f6ec/#1c6a2e`, `#fdecec/#a11b1b`, `#fff4e0/#8a5a00`) — legitimate semantics
  to formalize as tokens. Greyscale hexes in chart code stay as-is (data ink).

## Design foundation (tokens)

Add to `theme.py :root` (keep existing neutrals):

```
--accent:#4F46E5; --accent-hover:#4338CA; --accent-weak:#EEF0FD; --on-accent:#ffffff;
--focus:#4F46E5;
--success:#1c6a2e; --success-weak:#e7f6ec;
--warning:#8a5a00; --warning-weak:#fff4e0;
--danger:#a11b1b;  --danger-weak:#fdecec;
```

Also set `primaryColor = "#4F46E5"` in `.streamlit/config.toml [theme]` so
Streamlit's native primary widgets (type="primary" buttons, checkboxes, sliders,
active tab) adopt the accent automatically. Typography/spacing stay IBM Plex;
tighten heading scale and unify radius (buttons use `--radius`).

## Interaction signals (the accent's job)

- **Primary buttons** (`st.button(..., type="primary")`) → indigo bg / white text /
  `--accent-hover` on hover. **Secondary buttons** (default) → neutral outline
  (white bg, `--ink` text, `--border`), subtle hover. Requires replacing the
  blanket-black button CSS with `button[kind="primary"]` vs `button[kind="secondary"]`
  selectors (and letting `primaryColor` drive primary).
- **Links & interactive text** → `--accent`. **Active tab** → accent underline/weight.
- **Focus rings** → visible `--focus` outline on keyboard focus (a11y).

## States & feedback

- Success/warning/danger surfaces use the semantic tokens (soft bg + strong text),
  replacing the ad-hoc hexes in `app.py`.
- Records **empty state**: remove `#2f6df0`; neutral/muted copy with the primary
  CTA ("New analysis") in accent to draw the eye.

## Chart palette feature

A small **"Chart colors"** control on the analysis dashboard lets the analyst
choose how group series and heatmaps are colored. Renders live (charts redraw).

- **Preset selector** (curated, dataviz-driven): at minimum **Greyscale (default,
  publication-neutral)**, a **colorblind-safe categorical** set, **Viridis**
  (perceptually-uniform) and one more categorical (e.g. Set2-like). Categorical
  presets supply the group series; sequential presets/colormaps supply the heatmap.
  Exact palette values chosen at implementation time following the `dataviz` skill
  (colorblind-safe, sufficient contrast, consistent in light mode).
- **Per-group override:** an optional color picker per group id (treatment/sex/
  cohort). An override wins over the preset for that group; unset groups fall back
  to the preset.
- **Applies to:** categorical group series in bar charts (Distance, Time-in-zone)
  and the heatmap colormap. When "Greyscale" is active, behavior matches today
  (grey ramp + hatches for print safety).
- **State:** kept in `st.session_state` (ephemeral, re-renders charts). Not
  persisted to records this pass.

### New module

`gui_app/palette.py` — preset definitions + a resolver:
- `PRESETS`: categorical palettes (name → list of hex) and sequential colormaps
  (name → matplotlib colormap name).
- `resolve_group_colors(groups, preset, overrides) -> list[(color, hatch)]` —
  returns per-group `(color, hatch)` (hatch only meaningful for Greyscale), so
  chart code keeps one call shape. The current `theme.group_greys` becomes the
  Greyscale preset behind this resolver.
- `heatmap_cmap(preset) -> str` — colormap name for the heatmap.
- `palette_controls()` — renders the selector + per-group pickers, reads/writes
  session state, returns the active `(preset, overrides)`.

## Files affected

- `gui_app/theme.py` — accent + semantic tokens, button/link/focus/tab CSS,
  keep `group_greys` (now the Greyscale preset source).
- `gui_app/.streamlit/config.toml` — add `[theme] primaryColor = "#4F46E5"`.
- `gui_app/palette.py` — **new**: presets + resolver + controls.
- `gui_app/app.py` — render `palette.palette_controls()` on the dashboard; feed
  the resolved colors into the bar-chart and heatmap rendering; replace hardcoded
  `group_greys(...)` / `"Greys"` calls; remove the `#2f6df0` empty-state color;
  route status tiles through semantic tokens; apply primary/secondary button types.
- `gui_app/tests/` — unit tests for `palette.py` (preset resolve + override
  precedence + Greyscale parity with `group_greys`).

## Per-screen application (uniform)

Login, records home (empty state + admin panel + record cards + "New analysis"
primary), wizard (active step = accent, primary "Next" / secondary "Back"),
analysis dashboard (active tab = accent, stat tiles, palette control), guide.

## Risks / notes

- **Contrast/a11y:** verify `#4F46E5` on white and white-on-`#4F46E5` meet WCAG AA
  for buttons/links; adjust hover/weak variants if needed.
- **Publication neutrality preserved:** Greyscale stays the default chart preset,
  so nothing regresses for print/figures; color is opt-in.
- **Palette presets** must follow the `dataviz` skill at implementation time
  (colorblind-safe categorical, perceptually-uniform sequential).
- `primaryColor` in `config.toml` is theme-only and safe on Streamlit Community
  Cloud (does not touch server host/port).
