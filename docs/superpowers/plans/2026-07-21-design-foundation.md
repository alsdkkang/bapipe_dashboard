# Design Foundation (B&W + Indigo) Implementation Plan — Plan 1 of 2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the pure-B&W UI into a disciplined B&W + one-accent design system (Indigo), applied globally — tokens, primary/secondary buttons, links, focus, and consistent state colors.

**Architecture:** All visual changes flow through `gui_app/theme.py` (CSS tokens + rules injected once) and `gui_app/.streamlit/config.toml` (`primaryColor`), plus routing the few hardcoded colors in `app.py` through the new tokens. No analysis/logic changes. Charts are untouched here (their colors are Plan 2).

**Tech Stack:** Streamlit 1.60, CSS custom properties, IBM Plex. Python 3.11 via the repo `.venv`.

## Global Constraints

- **Accent:** `--accent:#4F46E5`, `--accent-hover:#4338CA`, `--accent-weak:#EEF0FD`, `--on-accent:#ffffff`, `--focus:#4F46E5`. Used ONLY for UI signals (buttons/links/active/focus), never chart data.
- **Semantic tokens (exact):** `--success:#1c6a2e` / `--success-weak:#e7f6ec`; `--warning:#8a5a00` / `--warning-weak:#fff4e0`; `--danger:#a11b1b` / `--danger-weak:#fdecec`.
- Keep existing neutral tokens and IBM Plex fonts unchanged.
- **Do NOT touch chart colors** (`_bar_palette`, `_BAR_PALETTES`, `_HEAT_CMAPS`, `group_greys`, heatmap cmaps) — Plan 2.
- **Do NOT re-enable the sidebar** here — that's Plan 2 (with nav content).
- `primaryColor` goes in `config.toml [theme]` — theme-only, safe on Streamlit Community Cloud (never touch `[server]`).
- Run tests with `cd gui_app && ../.venv/bin/python -m pytest`.

## File Structure

- `gui_app/theme.py` — add accent + semantic tokens to `:root`; button (primary/secondary), link, focus, active-tab CSS.
- `gui_app/.streamlit/config.toml` — add `[theme] primaryColor`.
- `gui_app/app.py` — route hardcoded status colors through semantic token classes; remove the stray `#2f6df0` empty-state color.
- `gui_app/tests/test_theme.py` — guard tests for the new tokens/CSS.

---

### Task 1: Design tokens + Streamlit primaryColor

**Files:**
- Modify: `gui_app/theme.py` (`:root` block in `CSS`)
- Modify: `gui_app/.streamlit/config.toml`
- Test: `gui_app/tests/test_theme.py`

**Interfaces:**
- Produces: CSS custom properties `--accent`, `--accent-hover`, `--accent-weak`, `--on-accent`, `--focus`, `--success(-weak)`, `--warning(-weak)`, `--danger(-weak)` available to all later CSS and to `app.py` inline styles.

- [ ] **Step 1: Write the failing test**

Add to `gui_app/tests/test_theme.py`:

```python
def test_accent_and_semantic_tokens_present():
    import theme
    css = theme.CSS
    for token in ("--accent:#4F46E5", "--accent-hover:#4338CA", "--accent-weak:#EEF0FD",
                  "--focus:", "--success:#1c6a2e", "--success-weak:#e7f6ec",
                  "--warning:#8a5a00", "--danger:#a11b1b"):
        assert token in css, f"missing token {token}"


def test_config_sets_indigo_primary():
    import tomllib
    from pathlib import Path
    cfg = tomllib.load(open(Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml", "rb"))
    assert cfg["theme"]["primaryColor"].lower() == "#4f46e5"
    assert "server" not in cfg  # must not manage the server on Streamlit Cloud
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_theme.py::test_accent_and_semantic_tokens_present tests/test_theme.py::test_config_sets_indigo_primary -q`
Expected: FAIL (tokens/primaryColor absent).

- [ ] **Step 3: Implement**

In `gui_app/theme.py`, extend the `:root{…}` block (keep every existing line) by appending these declarations before the closing `}`:

```css
  --accent:#4F46E5; --accent-hover:#4338CA; --accent-weak:#EEF0FD; --on-accent:#ffffff;
  --focus:#4F46E5;
  --success:#1c6a2e; --success-weak:#e7f6ec;
  --warning:#8a5a00; --warning-weak:#fff4e0;
  --danger:#a11b1b;  --danger-weak:#fdecec;
```

In `gui_app/.streamlit/config.toml`, add to the existing `[theme]` section:

```toml
[theme]
base = "light"
primaryColor = "#4F46E5"
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_theme.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_app/theme.py gui_app/.streamlit/config.toml gui_app/tests/test_theme.py
git commit -m "feat(theme): indigo accent + semantic tokens, streamlit primaryColor"
```

### Task 2: Primary/secondary buttons + links + focus + active tab

**Files:**
- Modify: `gui_app/theme.py` (button CSS at `div.stButton > button`, add link/focus/tab rules)
- Test: `gui_app/tests/test_theme.py`, plus the existing AppTest smoke suite

**Interfaces:**
- Consumes: tokens from Task 1.
- Produces: `type="primary"` buttons render indigo (via `primaryColor` + accent CSS); default buttons render as neutral outline; links/focus/active-tab use the accent.

- [ ] **Step 1: Write the failing test**

Add to `gui_app/tests/test_theme.py`:

```python
def test_button_and_focus_css_present():
    import theme
    css = theme.CSS
    # secondary buttons are neutral outline (not the old blanket black)
    assert 'button[kind="secondary"]' in css
    # primary buttons use the accent
    assert 'button[kind="primary"]' in css and "var(--accent)" in css
    # visible keyboard focus ring using the accent
    assert "var(--focus)" in css and ":focus-visible" in css
    # the old blanket-black rule that made ALL buttons black is gone
    assert "div.stButton > button{ background:var(--ink)" not in css.replace("\n", " ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_theme.py::test_button_and_focus_css_present -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `gui_app/theme.py`, replace the current button block:

```css
/* black primary buttons */
div.stButton > button{
  background:var(--ink); color:#fff; border:1px solid var(--ink); border-radius:7px;
  font-family:var(--font-sans);
}
div.stButton > button:hover{ background:#fff; color:var(--ink); }
```

with:

```css
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
```

- [ ] **Step 4: Verify tests + smoke pass**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_theme.py tests/test_app_smoke.py -q`
Expected: PASS (new CSS guard + app still renders without exception).

- [ ] **Step 5: Commit**

```bash
git add gui_app/theme.py gui_app/tests/test_theme.py
git commit -m "feat(theme): primary/secondary buttons, accent links, focus ring, active tab"
```

> **Live-verify note (execution):** button/tab styling is CSS-behavioural — after Plan 1 lands, confirm in the running app (primary buttons indigo, secondary outlined, visible focus ring) since unit tests only guard the CSS strings.

### Task 3: Consistent state colors + remove stray blue

**Files:**
- Modify: `gui_app/theme.py` (add `.state-*` helper classes)
- Modify: `gui_app/app.py` (status tiles ~L804-805 → token classes; empty-state `#2f6df0` at ~L1332 → neutral token)
- Test: `gui_app/tests/test_app_smoke.py`

**Interfaces:**
- Consumes: semantic tokens (Task 1).
- Produces: status surfaces + empty state use tokens; no hardcoded `#2f6df0`.

- [ ] **Step 1: Write the failing test**

Add to `gui_app/tests/test_app_smoke.py`:

```python
def test_no_stray_blue_in_app_source():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert "#2f6df0" not in src, "stray blue should be replaced by a token"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_app_smoke.py::test_no_stray_blue_in_app_source -q`
Expected: FAIL (the `#2f6df0` empty-state color is still there).

- [ ] **Step 3: Implement**

In `gui_app/theme.py`, add semantic helper classes to the CSS (before `</style>`):

```css
.state-success{ background:var(--success-weak); color:var(--success); border:1px solid var(--success); border-radius:8px; padding:8px 12px; }
.state-warning{ background:var(--warning-weak); color:var(--warning); border:1px solid var(--warning); border-radius:8px; padding:8px 12px; }
.state-danger{ background:var(--danger-weak); color:var(--danger); border:1px solid var(--danger); border-radius:8px; padding:8px 12px; }
```

In `gui_app/app.py`:
- At the records empty-state (~L1332), replace the inline `color:#2f6df0` with `color:var(--muted)` so it reads as neutral guidance (the primary "New analysis" CTA already draws the eye).
- At the status tiles (~L804-805), replace the hardcoded background/text hexes (`#e7f6ec/#1c6a2e`, `#fdecec/#a11b1b`, `#fff4e0/#8a5a00`) with the matching `state-success` / `state-danger` / `state-warning` classes (or the `var(--success)` etc. tokens if the markup is inline), so the semantics come from tokens. Keep the same text/logic.

- [ ] **Step 4: Verify tests + smoke pass**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_app_smoke.py -q`
Expected: PASS (no stray blue; app renders without exception).

- [ ] **Step 5: Commit**

```bash
git add gui_app/theme.py gui_app/app.py gui_app/tests/test_app_smoke.py
git commit -m "feat(theme): route state colors through semantic tokens; drop stray blue"
```

---

## Final check (after all tasks)

```bash
cd gui_app && ../.venv/bin/python -m pytest tests/ -q      # all green
```

Then push and let Streamlit Cloud redeploy; live-verify the accent system
(primary buttons indigo, secondary outlined, focus ring, active tab, status
colors) before starting Plan 2.

## Self-Review

- **Spec coverage (foundation slice):** accent + semantic tokens (Task 1) ✓,
  primaryColor (Task 1) ✓, primary/secondary buttons (Task 2) ✓, links/focus/
  active-tab (Task 2) ✓, state consistency + remove `#2f6df0` (Task 3) ✓.
- **Deferred to Plan 2 (per spec):** sidebar re-enable + nav, chart palette
  consolidation + per-group override, analysis dashboard KPI layout, sample data.
- **Placeholders:** none — exact tokens/CSS/selectors given.
- **Type/consistency:** token names identical across theme.py, config.toml, and
  app.py usages; `button[kind="primary"|"secondary"]` and `--focus`/`--accent`
  referenced consistently between Task 2 CSS and its guard test.
- **Note:** CSS-behavioural results (button/tab look) are guarded only at the
  string level by tests; the plan calls for live verification at execution.
