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
- **Analysis dashboard gets a reference-driven layout** (card-based KPI dashboard,
  modeled on the user's Figma "Analytics Dashboard" reference): a **left sidebar
  nav** (re-enabled for the analysis screens) + a KPI-tile row + a main chart +
  detail cards. This intentionally revisits the earlier sidebar-less choice, for
  the analysis screens only.
- **Bundle a small sample experiment** + a "Load sample" entry so the deployed
  demo opens straight into a populated dashboard (raw data still never persisted;
  the sample is read-only fixtures shipped in the repo).
- **Demo defaults to an Indigo chart preset** (matches the reference's colored
  look); Greyscale remains a selectable preset.

## Scope

**In scope:** design tokens (accent + semantic + type/space), primary/secondary
button distinction, links/active-tab/focus states, state-feedback consistency,
empty-state cleanup, per-screen application, the chart-palette feature, the
reference-driven analysis-dashboard layout (sidebar nav + KPI tiles + main chart +
detail cards), and a bundled sample experiment with a "Load sample" entry.

**Out of scope:** dark mode, auth/deploy changes, and rewriting the underlying
`bapipe` analysis computations (the redesign reuses them). New analytical metrics
beyond surfacing existing computed values as KPI tiles/cards are out of scope.

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

- **Preset selector** — **already implemented per-view** today via `_BAR_PALETTES`
  (`Grayscale`, `tab10`, `Set2`, `Set1`, `Dark2`, `Paired`, `colorblind`) +
  `_HEAT_CMAPS` (`Greys`, `viridis`, `Blues`, …) and `_bar_palette()`. This pass
  **consolidates** those per-view dropdowns into a single "Chart colors" control
  (lives in the sidebar — Plan 2) and curates the preset list per the `dataviz`
  skill (colorblind-safe categorical, perceptually-uniform sequential). Greyscale
  stays the publication-neutral default.
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

## Analysis dashboard redesign (reference-driven)

Rework the analysis screen (currently top `st.tabs` with a plain Overview table)
into a card-based KPI dashboard, mapping the Figma reference onto the app's mouse-
behaviour data:

- **Left sidebar** (`st.sidebar`, re-enabled + styled): logo, nav items (Overview,
  Distance, Heatmaps, Time in zone) replacing the top tabs, the **"Chart colors"**
  palette control, and the account/logout at the bottom. The global CSS that hides
  the sidebar (`section[data-testid="stSidebar"]{display:none}`) is scoped so it no
  longer hides it on the analysis screens.
- **Overview = the main screen**, laid out as:
  - **Filters row:** experiment name + group/animal filter (reuses `animal_selector`
    + group columns) + a Download action.
  - **KPI tile row** (uses the existing, currently-unused `theme.stat_tile`):
    Animals (count), Groups (count), Total distance (mean per animal), Avg recording
    length — computed from the loaded videos + `analysis` helpers.
  - **Main chart:** distance-by-group bar chart (palette applied) — the reference's
    large activity chart slot.
  - **Detail cards:** *By group* (per-group summary / horizontal bars) and *Animal
    ranking* (most→least active animals, leaderboard style) from the per-animal
    results.
- **Distance / Heatmaps / Time-in-zone** views adopt the same card styling and the
  chart palette; charts otherwise keep their existing computations.

This is a layout/presentation change — the underlying `bapipe` analysis
computations (`render_distance`, `render_heatmaps`, `render_zone`, montage) are
reused, not rewritten.

## Sample data

- Curate a **small sample experiment** from the local `v4` dataset (one manifest +
  a few animals' videos/`.h5`, trimmed to megabytes) committed under
  `gui_app/sample_data/` so it ships with the app (and the deployed Streamlit
  Cloud demo).
- Add a **"Load sample experiment"** action (on welcome / records home) that loads
  this bundle straight into the analysis dashboard, so the demo opens populated —
  no upload, nothing persisted.
- The sample must be small enough for Streamlit Community Cloud (repo stays light;
  keep well under the free-tier limits). If no adequately small valid subset can be
  produced, surface that rather than committing a large asset.

## Files affected

- `gui_app/theme.py` — accent + semantic tokens, button/link/focus/tab CSS, sidebar
  re-enabled + styled (scope the display:none rule), keep `group_greys` (now the
  Greyscale preset source).
- `gui_app/.streamlit/config.toml` — add `[theme] primaryColor = "#4F46E5"`.
- `gui_app/palette.py` — **new**: presets + resolver + controls.
- `gui_app/app.py` — sidebar nav (replacing top tabs) + palette control + account
  in the sidebar; rebuild `render_overview` as the KPI-tile/main-chart/detail-card
  layout using `theme.stat_tile`; feed resolved palette into bar-chart/heatmap
  rendering; replace hardcoded `group_greys(...)`/`"Greys"`; remove the `#2f6df0`
  empty-state color; route status tiles through semantic tokens; apply
  primary/secondary button types; add the "Load sample experiment" entry.
- `gui_app/sample_data/` — **new**: the trimmed sample experiment (manifest +
  small videos/`.h5`) committed for the demo.
- `gui_app/samples.py` — **new** (small): resolve the bundled sample path and load
  it into the same session state the wizard produces.
- `gui_app/tests/` — unit tests for `palette.py` (preset resolve + override
  precedence + Greyscale parity with `group_greys`); AppTest smoke for the redesigned
  Overview (KPI tiles render) and the sidebar nav.

## Per-screen application (uniform)

Login, records home (empty state + admin panel + record cards + "New analysis"
primary + "Load sample" entry), wizard (active step = accent, primary "Next" /
secondary "Back"), analysis dashboard (sidebar nav + KPI tiles + main chart +
detail cards + palette control), guide.

## Risks / notes

- **Contrast/a11y:** verify `#4F46E5` on white and white-on-`#4F46E5` meet WCAG AA
  for buttons/links; adjust hover/weak variants if needed.
- **Publication neutrality preserved:** Greyscale stays the default chart preset,
  so nothing regresses for print/figures; color is opt-in.
- **Palette presets** must follow the `dataviz` skill at implementation time
  (colorblind-safe categorical, perceptually-uniform sequential).
- `primaryColor` in `config.toml` is theme-only and safe on Streamlit Community
  Cloud (does not touch server host/port).
