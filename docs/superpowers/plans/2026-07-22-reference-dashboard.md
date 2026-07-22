# Reference Analysis Dashboard Implementation Plan — Plan 2 of 2

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) — steps use checkbox syntax. UI-layout results are verified live (AppTest guards no-exception + element presence; the visual result is confirmed in the running app after each push).

**Goal:** Turn the analysis screen into a card-based KPI dashboard modeled on the user's reference: a left nav, a KPI-tile row, a main chart, and detail cards — with a consolidated chart-palette control (presets + per-group override) and grid-aligned form screens.

**Architecture:** All changes are in `gui_app/app.py` (layout of the `phase == "app"` router + `render_overview`, and the palette control) and `gui_app/theme.py` (nav/card/grid CSS + a `palette.py`-style resolver). The underlying `bapipe` analyses are reused, not rewritten. Nav is a **left column** (`st.columns`), not `st.sidebar`, to avoid the global sidebar-hide and to fully control the styling.

**Tech Stack:** Streamlit 1.60, matplotlib/seaborn, IBM Plex, Indigo accent from Plan 1. Python 3.11 via `.venv`. Verified against the bundled sample (`Load sample` → 4 animals / 4 groups).

## Global Constraints

- Build on Plan 1 tokens (`--accent`, semantic, neutrals). Charts stay greyscale by default (Greyscale preset); color is opt-in via the palette control.
- Reuse existing helpers: `animal_selector`, `group_selector`, `metric_by_group`, `theme.stat_tile`, `theme.card`, `analysis.distance_travelled`, `analysis.time_in_zone`, `_bar_palette`, `_BAR_PALETTES`, `_HEAT_CMAPS`.
- Do NOT rewrite bapipe analysis computations or the load pipeline.
- Nav = left column, not `st.sidebar` (keep the global sidebar-hide CSS as-is).
- Run tests with `cd gui_app && ../.venv/bin/python -m pytest`; use `_fresh_apptest` + the sample to drive the app phase.

## File Structure

- `gui_app/app.py` — `phase == "app"` router → left-nav column + content column; rebuild `render_overview` into KPI dashboard; consolidate palette into the nav; grid tidy for the wizard.
- `gui_app/theme.py` — nav CSS, KPI/card grid CSS, form-grid helpers.
- `gui_app/palette.py` — **new**: `resolve_group_colors(groups, preset, overrides)` + `active_palette()` reading session state; wraps `_bar_palette` so per-group overrides win.
- `gui_app/tests/` — AppTest smoke for the app-phase nav + KPI overview (driven by the sample); unit tests for `palette.py` override precedence.

---

### Task 1: Left-nav layout for the analysis phase

**Files:** Modify `gui_app/app.py` (`phase == "app"` block, lines ~1402-1438); `gui_app/theme.py` (nav CSS); Test: `gui_app/tests/test_app_smoke.py`.

**Interfaces:** Produces a `_nav` selection in `st.session_state["app_view"]`; renders exactly one view fn in the content column.

- [ ] **Step 1: Write the failing test** — after loading the sample and setting `phase="app"`, the app renders a nav with the six view labels and no exception.

```python
def test_app_phase_has_left_nav(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    import samples, importlib; importlib.reload(samples)
    if not samples.sample_available():
        import pytest; pytest.skip("no sample")
    at = _fresh_apptest()
    for k, v in {"data_video_dir": str(samples.SAMPLE_DIR / "videos"),
                 "data_dlc_dir": str(samples.SAMPLE_DIR / "mouse_labels"),
                 "data_landmark_dir": str(samples.SAMPLE_DIR / "landmark_labels"),
                 "data_calib_path": str(samples.SAMPLE_DIR / "camera_calibrations.json"),
                 "data_meta_path": str(samples.SAMPLE_DIR / "metadata.csv"),
                 "data_join_col": "id"}.items():
        at.session_state[k] = v
    at.session_state["pending_load_ids"] = list(samples.SAMPLE_IDS)
    at.session_state["phase"] = "loading"; at.run()          # loads
    at.session_state["phase"] = "app"; at.run()              # dashboard
    assert not at.exception
    labels = [r.label for r in at.radio] if at.radio else []
    assert any("Overview" in l for grp in labels for l in (grp if isinstance(grp, list) else [grp]))
```

- [ ] **Step 2: Run to confirm fail** — `../.venv/bin/python -m pytest tests/test_app_smoke.py::test_app_phase_has_left_nav -q` → FAIL (no radio nav yet).

- [ ] **Step 3: Implement** — replace the `st.tabs([...])` block in `phase == "app"` with a two-column layout:

```python
    VIEWS = ["Overview", "Distance", "Heatmaps", "Time in zone", "Validation video", "Results"]
    nav_col, content = st.columns([1.25, 6], gap="large")
    with nav_col:
        st.markdown("<div class='navwrap'>", unsafe_allow_html=True)
        view = st.radio("Views", VIEWS, key="app_view", label_visibility="collapsed")
        st.markdown("</div>", unsafe_allow_html=True)
    with content:
        {"Overview": render_overview, "Distance": render_distance,
         "Heatmaps": render_heatmaps, "Time in zone": render_zone,
         "Validation video": render_validation, "Results": render_results}[view]()
```

Move the existing "← Change data" / "Guide" buttons into `nav_col` (below the radio). In `theme.py` add nav styling: the radio as a vertical list, active item in `--accent-weak` bg / `--accent` text, hover states.

- [ ] **Step 4: Verify** — `../.venv/bin/python -m pytest tests/test_app_smoke.py -q` → PASS (nav present, sample view renders).

- [ ] **Step 5: Commit** — `feat(dashboard): left nav for the analysis phase (replaces top tabs)`.

### Task 2: KPI-tile Overview

**Files:** Modify `gui_app/app.py` (`render_overview`, ~1022-1067); `gui_app/theme.py` (KPI grid CSS); Test: `gui_app/tests/test_app_smoke.py`.

**Interfaces:** Consumes globals `video_set`, `metadata`, `group_cols`, `loaded_ids`. Produces the KPI/main-chart/cards layout.

- [ ] **Step 1: Write the failing test** — Overview (with the sample loaded) renders stat-tile labels "Animals" and "Groups".

```python
def test_overview_shows_kpi_tiles(tmp_path, monkeypatch):
    # (same sample-load preamble as test_app_phase_has_left_nav)
    ...
    at.session_state["phase"] = "app"; at.session_state["app_view"] = "Overview"; at.run()
    assert not at.exception
    md = [m.value for m in at.markdown]
    assert any("Animals" in (t or "") for t in md)
    assert any("Groups" in (t or "") for t in md)
```

- [ ] **Step 2: Run to confirm fail.**

- [ ] **Step 3: Implement** `render_overview` as:
  - a **filters row** (experiment name + `animal_selector` + `group_selector`),
  - a **KPI tile row** via `theme.stat_tile` inside a CSS grid: `Animals` = len(sel); `Groups` = n unique groups (or "—"); `Total distance` = mean of `analysis.distance_travelled` over selected (rounded); `Avg recording` = mean `v.duration`,
  - a **main chart**: distance-by-group bar (reuse `metric_by_group` + `_bar_palette`),
  - **detail cards**: *By group* (group means table/bars) and *Animal ranking* (per-animal distance sorted). Keep the montage builder below, in a `theme.card`/expander.
  Compute per-animal distance once into a DataFrame (like `autosave_current_load`) and reuse for KPIs + ranking to avoid recomput​ing.

- [ ] **Step 4: Verify** tests + no exception. **Step 5: Commit** `feat(dashboard): KPI-tile Overview (stat tiles + main chart + detail cards)`.

### Task 3: Grid alignment for form screens

**Files:** `gui_app/app.py` (`render_wizard` step 0 folder inputs), `gui_app/theme.py` (form-grid CSS). Test: existing smoke stays green.

- [ ] Align the wizard's input+Browse rows on a consistent two-column grid (label column + control), tighten vertical rhythm, group into a `theme.card`. Verify `tests/test_app_smoke.py::test_wizard_renders_step_zero` still passes. Commit `feat(dashboard): grid-align the Start wizard form`.

### Task 4: Consolidated palette control + per-group override

**Files:** `gui_app/palette.py` (new), `gui_app/app.py` (nav palette control; charts use resolver), `gui_app/tests/test_palette.py` (new).

**Interfaces:** `palette.active_palette()` → `(preset:str, overrides:dict)` from session; `palette.resolve_group_colors(groups, preset, overrides)` → `[(hex, hatch)]` (Greyscale via `theme.group_greys`; else `sns.color_palette`, with any per-group override replacing that group's hex).

- [ ] **Step 1: failing unit test** for `resolve_group_colors`: Greyscale parity with `theme.group_greys`; a non-grey preset returns n hexes; an override for one group replaces exactly that group's color.
- [ ] **Step 2/3:** implement `palette.py`; add a "Chart colors" control in `nav_col` (preset select + per-group color pickers) writing session state; route `render_distance`/`render_zone`/`render_heatmaps` through the resolver instead of per-view `_bar_palette` dropdowns.
- [ ] **Step 4/5:** tests pass; commit `feat(dashboard): consolidated chart palette + per-group overrides`.

---

## Final check

```bash
cd gui_app && ../.venv/bin/python -m pytest tests/ -q     # all green
```
Push; live-verify the dashboard (left nav, KPI tiles populated by Load sample, main chart, cards, palette control) on Streamlit Cloud.

## Self-Review

- **Spec coverage:** left nav (T1) ✓, KPI dashboard layout (T2) ✓, form grid (T3) ✓, palette consolidation + override (T4) ✓; sample data + Load sample already shipped (Plan 2a).
- **Placeholders:** T2/T3 describe layout with the exact helpers/globals to use; the per-tile values and card contents are specified. UI-visual polish is iterated live by design (noted in the header).
- **Consistency:** nav writes `app_view`; content dispatch and the T1 test both key off the same `VIEWS` labels; palette resolver signature matches its test and its call sites.
- **Risk:** rebuilding `render_overview` is the largest change — guarded by the sample-driven AppTest (no exception + KPI tiles present) and live verification.
