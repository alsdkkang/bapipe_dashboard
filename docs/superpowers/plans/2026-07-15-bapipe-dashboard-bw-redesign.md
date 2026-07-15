# bapipe Dashboard B&W Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the bapipe Streamlit dashboard to black & white with the sidebar off, a first-time Welcome screen (Guide + Start), a private per-user "My Records" dashboard, and automatic result-only saving on load.

**Architecture:** Keep the existing Streamlit app (`gui_app/app.py`) and all bapipe analysis logic. Extract new **pure, unit-testable modules** — `records.py` (per-user JSON store), `routing.py` (phase resolution), `theme.py` (B&W CSS + greyscale chart palette) — and restructure `app.py` into a phase router (welcome → records → wizard → loading → app → guide) that renders a top bar instead of a sidebar. Results are auto-saved to the record store when a load completes.

**Tech Stack:** Python 3.11, Streamlit 1.58, pandas 1.5.3, numpy 1.26, matplotlib 3.8, pytest (added as a dev dependency), Streamlit `AppTest` for smoke tests.

## Global Constraints

- Python 3.11 only. pandas is pinned to 1.5.3 and numpy to 1.26.4 — do not use pandas 2.x APIs. (from `gui_app/requirements.txt`)
- Colours are **black & white only**: primary/active/buttons/focus = `#111111`; surfaces white `#ffffff`; canvas `#fafbfc`; neutrals are greys. **No blue accent** anywhere. (spec §6)
- Charts are greyscale: groups differentiated by **lightness steps and hatch patterns, never hue**. (spec §6, §10)
- Records store: `gui_app/records/<key>.json`, one file per user, key = filesystem-safe slug of the signed-in email or `"local"` when auth is disabled. Store dir overridable via env `BAPIPE_RECORDS_DIR` (for tests). (spec §7)
- **Never save** raw videos, pose `.h5`, frames, or montage/heatmap images — numbers + metadata only. (spec §7)
- Record saving is **automatic on load completion** — no explicit Save button. (spec §7, §10)
- Privacy is **UI-level**: no admin code path may list another user's records. (spec §7)
- Fonts: IBM Plex Sans (UI) + IBM Plex Mono (numerics/IDs) via Google Fonts. (spec §6)
- Run all tests with the venv: `./.venv/bin/python -m pytest`.

---

## File Structure

**New files:**
- `gui_app/records.py` — per-user JSON store: onboarded flag + record CRUD + dedupe + `assemble_record`.
- `gui_app/routing.py` — pure `resolve_phase(onboarded, session_phase)`.
- `gui_app/theme.py` — `inject_css()`, HTML helpers (`brand_header`, `top_bar`, `card`, `stat_tile`), greyscale `group_greys(n)`.
- `gui_app/guide.py` — `render_guide(on_back)` in-app how-to page.
- `gui_app/tests/test_records.py`, `gui_app/tests/test_routing.py`, `gui_app/tests/test_theme.py`, `gui_app/tests/test_app_smoke.py`.
- `gui_app/tests/__init__.py` (empty), `gui_app/pytest.ini`.
- `requirements-dev.txt` — pytest.

**Modified files:**
- `gui_app/app.py` — phase router; remove sidebar; top bar + tabs; welcome; wizard; loading + auto-save; records dashboard; guide wiring; re-skinned views.
- `gui_app/auth.py` — add `is_admin(email)` and `header_account()`; keep existing functions.
- `.gitignore` — add `gui_app/records/`.

---

## Task 1: Test harness + per-user record store

**Files:**
- Create: `requirements-dev.txt`, `gui_app/pytest.ini`, `gui_app/tests/__init__.py`, `gui_app/records.py`, `gui_app/tests/test_records.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces:
  - `records.store_dir() -> pathlib.Path` (honours `BAPIPE_RECORDS_DIR`, default `gui_app/records`)
  - `records.user_key(email: str | None) -> str` (slug; `None`/empty → `"local"`)
  - `records.is_onboarded(email) -> bool`
  - `records.mark_onboarded(email) -> None`
  - `records.list_records(email) -> list[dict]` (newest first)
  - `records.add_record(email, record: dict) -> dict` (dedupe on `animals`+`config`; returns stored record)
  - `records.get_record(email, rid: str) -> dict | None`
  - `records.delete_record(email, rid: str) -> None`

- [ ] **Step 1: Add pytest dev dependency and install it**

Create `requirements-dev.txt`:

```
pytest==8.3.2
```

Install into the existing venv:

Run: `cd "$(git rev-parse --show-toplevel)" && ./.venv/bin/python -m pip install -r requirements-dev.txt`
Expected: pytest installs successfully.

- [ ] **Step 2: Create pytest config and test package**

Create `gui_app/tests/__init__.py` (empty file).

Create `gui_app/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 3: Ignore the records directory**

Add to `.gitignore` (append a new line):

```
gui_app/records/
```

- [ ] **Step 4: Write failing tests for the record store**

Create `gui_app/tests/test_records.py`:

```python
import importlib
import sys
from pathlib import Path

import pytest

# Make `import records` resolve to gui_app/records.py
GUI_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI_APP))


@pytest.fixture()
def records(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    import records as mod
    importlib.reload(mod)
    return mod


def _rec(name="run", animals=("m1", "m2"), box=(400, 300)):
    return {
        "name": name,
        "animals": list(animals),
        "config": {"box_shape": list(box), "use_box_reference": True},
        "results": {"per_animal": [], "group_summary": []},
    }


def test_user_key_defaults_to_local(records):
    assert records.user_key(None) == "local"
    assert records.user_key("") == "local"
    assert records.user_key("A.B@Example.com") == records.user_key("a.b@example.com")


def test_onboarded_roundtrip(records):
    assert records.is_onboarded("u@x.com") is False
    records.mark_onboarded("u@x.com")
    assert records.is_onboarded("u@x.com") is True


def test_add_and_list_newest_first(records):
    a = records.add_record("u@x.com", _rec(name="first"))
    b = records.add_record("u@x.com", _rec(name="second", animals=("m3",)))
    assert "id" in a and "created" in a
    names = [r["name"] for r in records.list_records("u@x.com")]
    assert names == ["second", "first"]


def test_add_dedupe_same_animals_and_config_updates_timestamp(records):
    a = records.add_record("u@x.com", _rec())
    b = records.add_record("u@x.com", _rec())  # identical animals + config
    assert len(records.list_records("u@x.com")) == 1
    assert b["id"] == a["id"]


def test_get_and_delete(records):
    a = records.add_record("u@x.com", _rec())
    assert records.get_record("u@x.com", a["id"])["name"] == "run"
    records.delete_record("u@x.com", a["id"])
    assert records.get_record("u@x.com", a["id"]) is None


def test_users_are_isolated(records):
    records.add_record("u1@x.com", _rec())
    assert records.list_records("u2@x.com") == []
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_records.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'records'`.

- [ ] **Step 6: Implement `records.py`**

Create `gui_app/records.py`:

```python
"""Per-user record store for the bapipe dashboard.

Stores small analysis-result snapshots (numbers + metadata only — never raw
video/pose data) as one JSON file per user under `gui_app/records/`. Keyed by
the signed-in email; falls back to "local" when auth is disabled. UI-level
privacy: only the owning user's file is ever read/written here, and no admin
path lists another user's records.

The store directory is overridable via the BAPIPE_RECORDS_DIR env var (tests).
"""
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def store_dir() -> Path:
    d = Path(os.environ.get("BAPIPE_RECORDS_DIR", str(HERE / "records")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_key(email) -> str:
    email = (email or "").strip().lower()
    if not email:
        return "local"
    return re.sub(r"[^a-z0-9]+", "_", email).strip("_") or "local"


def _path(email) -> Path:
    return store_dir() / f"{user_key(email)}.json"


def _load(email) -> dict:
    p = _path(email)
    if p.exists():
        try:
            data = json.loads(p.read_text())
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("onboarded", False)
    data.setdefault("records", [])
    return data


def _save(email, data) -> None:
    _path(email).write_text(json.dumps(data, indent=2))


def is_onboarded(email) -> bool:
    return bool(_load(email)["onboarded"])


def mark_onboarded(email) -> None:
    data = _load(email)
    if not data["onboarded"]:
        data["onboarded"] = True
        _save(email, data)


def _signature(record) -> tuple:
    return (tuple(record.get("animals", [])),
            json.dumps(record.get("config", {}), sort_keys=True))


def list_records(email) -> list:
    # newest first
    return list(reversed(_load(email)["records"]))


def add_record(email, record) -> dict:
    """Append a record; if the most recent record has the same animals+config,
    refresh its timestamp instead of adding a duplicate."""
    data = _load(email)
    now = datetime.now().isoformat(timespec="seconds")
    if data["records"] and _signature(data["records"][-1]) == _signature(record):
        data["records"][-1]["created"] = now
        _save(email, data)
        return data["records"][-1]
    stored = dict(record)
    stored["id"] = uuid.uuid4().hex
    stored["created"] = now
    data["records"].append(stored)
    _save(email, data)
    return stored


def get_record(email, rid):
    for r in _load(email)["records"]:
        if r.get("id") == rid:
            return r
    return None


def delete_record(email, rid) -> None:
    data = _load(email)
    data["records"] = [r for r in data["records"] if r.get("id") != rid]
    _save(email, data)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_records.py -q`
Expected: PASS (6 passed).

- [ ] **Step 8: Commit**

```bash
git add requirements-dev.txt gui_app/pytest.ini gui_app/tests/__init__.py \
        gui_app/records.py gui_app/tests/test_records.py .gitignore
git commit -m "feat: add per-user record store with onboarded flag + dedupe"
```

---

## Task 2: Assemble a record snapshot from load results

**Files:**
- Modify: `gui_app/records.py`
- Test: `gui_app/tests/test_records.py`

**Interfaces:**
- Consumes: pandas DataFrames produced by the analysis views.
- Produces:
  - `records.assemble_record(name: str, animals: list[str], config: dict, per_animal: pd.DataFrame, group_summary: pd.DataFrame | None) -> dict` — returns a JSON-serialisable record dict (no `id`/`created`; those are added by `add_record`).

- [ ] **Step 1: Write the failing test**

Append to `gui_app/tests/test_records.py`:

```python
def test_assemble_record_is_json_serialisable(records):
    import json as _json
    import pandas as pd
    per = pd.DataFrame(
        {"distance": [27000.0], "time_in_zone": [12.0], "duration_s": [650.0]},
        index=pd.Index(["m1"], name="id"),
    )
    summ = pd.DataFrame({"distance": [27000.0]}, index=pd.Index(["saline"], name="group"))
    rec = records.assemble_record(
        name="run", animals=["m1"],
        config={"box_shape": (400, 300)}, per_animal=per, group_summary=summ,
    )
    # must round-trip through JSON without error
    _json.dumps(rec)
    assert rec["name"] == "run"
    assert rec["animals"] == ["m1"]
    assert rec["config"]["box_shape"] == [400, 300]
    assert rec["results"]["per_animal"][0]["id"] == "m1"
    assert rec["results"]["group_summary"][0]["group"] == "saline"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_records.py::test_assemble_record_is_json_serialisable -q`
Expected: FAIL — `AttributeError: module 'records' has no attribute 'assemble_record'`.

- [ ] **Step 3: Implement `assemble_record`**

Add to `gui_app/records.py` (after the imports, before `store_dir` or at the end — keep imports at top):

```python
def _jsonable(value):
    """Coerce numpy/tuple values into plain JSON types."""
    import numpy as np
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def assemble_record(name, animals, config, per_animal, group_summary):
    """Build a JSON-serialisable snapshot from computed result frames.

    `per_animal` is indexed by animal id; `group_summary` (optional) is indexed
    by group. Only numbers + metadata are stored — no raw video/pose data.
    """
    pa = per_animal.reset_index()
    pa = pa.rename(columns={pa.columns[0]: "id"})
    per_rows = [{k: _jsonable(v) for k, v in row.items()}
                for row in pa.to_dict(orient="records")]
    summ_rows = []
    if group_summary is not None and len(group_summary):
        gs = group_summary.reset_index()
        gs = gs.rename(columns={gs.columns[0]: "group"})
        gs.columns = ["_".join(map(str, c)).strip("_") if isinstance(c, tuple) else str(c)
                      for c in gs.columns]
        summ_rows = [{k: _jsonable(v) for k, v in row.items()}
                     for row in gs.to_dict(orient="records")]
    return {
        "name": name,
        "animals": [str(a) for a in animals],
        "config": _jsonable(config),
        "results": {"per_animal": per_rows, "group_summary": summ_rows},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_records.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add gui_app/records.py gui_app/tests/test_records.py
git commit -m "feat: assemble JSON-serialisable record snapshot from result frames"
```

---

## Task 3: Phase routing

**Files:**
- Create: `gui_app/routing.py`, `gui_app/tests/test_routing.py`

**Interfaces:**
- Produces:
  - `routing.PHASES = ("welcome", "records", "wizard", "loading", "app", "guide")`
  - `routing.resolve_phase(onboarded: bool, session_phase: str | None) -> str`

- [ ] **Step 1: Write the failing test**

Create `gui_app/tests/test_routing.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import routing  # noqa: E402


def test_explicit_session_phase_wins():
    assert routing.resolve_phase(False, "wizard") == "wizard"
    assert routing.resolve_phase(True, "guide") == "guide"


def test_first_time_user_sees_welcome():
    assert routing.resolve_phase(False, None) == "welcome"


def test_returning_user_sees_records():
    assert routing.resolve_phase(True, None) == "records"


def test_unknown_session_phase_falls_back():
    assert routing.resolve_phase(True, "bogus") == "records"
    assert routing.resolve_phase(False, "bogus") == "welcome"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_routing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'routing'`.

- [ ] **Step 3: Implement `routing.py`**

Create `gui_app/routing.py`:

```python
"""Pure phase-resolution for the dashboard's top-level state machine."""

PHASES = ("welcome", "records", "wizard", "loading", "app", "guide")


def resolve_phase(onboarded, session_phase):
    """Which screen to show this run.

    An explicit, valid `session_phase` always wins. Otherwise a first-time user
    (not onboarded) sees "welcome"; a returning user sees "records".
    """
    if session_phase in PHASES:
        return session_phase
    return "records" if onboarded else "welcome"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_routing.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add gui_app/routing.py gui_app/tests/test_routing.py
git commit -m "feat: add pure phase-resolution for dashboard routing"
```

---

## Task 4: Black & white theme + greyscale chart palette

**Files:**
- Create: `gui_app/theme.py`, `gui_app/tests/test_theme.py`

**Interfaces:**
- Produces:
  - `theme.group_greys(n: int) -> list[tuple[str, str]]` — n `(hex_color, hatch)` pairs; colours are grey lightness steps, hatch cycles for differentiation.
  - `theme.CSS: str` — the full `<style>` block string (tokens + widget overrides + hide sidebar).
  - `theme.inject_css() -> None` — calls `st.markdown(CSS, unsafe_allow_html=True)`.
  - `theme.card(title, body_html, eyebrow=None, sub=None) -> str` — HTML string for a bordered card.
  - `theme.stat_tile(label, value, unit=None, note=None) -> str` — HTML string for a stat tile.

- [ ] **Step 1: Write the failing test**

Create `gui_app/tests/test_theme.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import theme  # noqa: E402


def test_group_greys_count_and_shape():
    greys = theme.group_greys(4)
    assert len(greys) == 4
    for color, hatch in greys:
        assert color.startswith("#")
        assert isinstance(hatch, str)


def test_group_greys_cycles_beyond_ramp():
    # more groups than base greys still returns n distinct (color, hatch) pairs
    greys = theme.group_greys(9)
    assert len(greys) == 9
    assert len(set(greys)) == 9


def test_css_is_black_and_white_only():
    css = theme.CSS.lower()
    # no blue accent from the reference palette
    assert "#2f6df0" not in css
    assert "111" in css  # primary black present


def test_card_and_stat_tile_render_content():
    assert "My Title" in theme.card("My Title", "<p>x</p>")
    assert "Animals" in theme.stat_tile("Animals", "12")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_theme.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'theme'`.

- [ ] **Step 3: Implement `theme.py`**

Create `gui_app/theme.py`:

```python
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
  --ink:#111111; --body:#37414e; --muted:#6c7889; --faint:#98a4b4;
  --canvas:#fafbfc; --card:#ffffff; --sunken:#f4f6f9;
  --border:#dce2ea; --border-strong:#c2ccd8;
  --radius:10px;
}
html, body, [class*="css"]{ font-family:var(--font-sans); color:var(--body); }
.stApp{ background:var(--canvas); }
/* hide the sidebar entirely (turned off for this redesign) */
section[data-testid="stSidebar"]{ display:none !important; }
div[data-testid="collapsedControl"]{ display:none !important; }
[data-testid="stStatusWidget"]{ display:none !important; }
/* black primary buttons */
div.stButton > button{
  background:var(--ink); color:#fff; border:1px solid var(--ink); border-radius:7px;
  font-family:var(--font-sans);
}
div.stButton > button:hover{ background:#fff; color:var(--ink); }
h1,h2,h3,h4{ color:var(--ink); letter-spacing:-0.02em; }
.mono{ font-family:var(--font-mono); }
.eyebrow{ font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.bw-card{ background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:0 1px 2px rgba(16,24,32,.06); padding:16px; margin-bottom:16px; }
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_theme.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add gui_app/theme.py gui_app/tests/test_theme.py
git commit -m "feat: add black & white theme + greyscale chart palette"
```

---

## Task 5: Auth helpers for the top bar

**Files:**
- Modify: `gui_app/auth.py`
- Test: `gui_app/tests/test_records.py` is unrelated; create `gui_app/tests/test_auth.py`

**Interfaces:**
- Consumes: existing `auth._load_access()`, `auth._current()`, `auth._logout()`.
- Produces:
  - `auth.is_admin(email: str | None) -> bool`
  - `auth.header_account() -> None` — renders the signed-in avatar + a logout button in the main area (used by the top bar). No-op when auth is disabled.

- [ ] **Step 1: Write the failing test**

Create `gui_app/tests/test_auth.py`:

```python
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_is_admin_reads_access(monkeypatch):
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_load_access",
                        lambda: {"admins": ["boss@x.com"], "approved": [], "pending": {}})
    assert auth.is_admin("boss@x.com") is True
    assert auth.is_admin("BOSS@x.com") is True   # case-insensitive
    assert auth.is_admin("nobody@x.com") is False
    assert auth.is_admin(None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_auth.py -q`
Expected: FAIL — `AttributeError: module 'auth' has no attribute 'is_admin'`.

- [ ] **Step 3: Implement the helpers**

Add to `gui_app/auth.py` (after `sidebar_account`):

```python
def is_admin(email) -> bool:
    email = (email or "").strip().lower()
    if not email:
        return False
    return email in set(a.lower() for a in _load_access()["admins"])


def header_account():
    """Signed-in avatar + logout, rendered in the main area (top bar). No-op
    unless auth is enabled and a user is signed in."""
    if not auth_enabled():
        return
    email, name = _current()
    if not email:
        return
    who = name or email
    initial = (who[:1] or "?").upper()
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    c1.markdown(
        f"<div style='text-align:right'>"
        f"<span class='avatar' style='display:inline-flex;vertical-align:middle;margin-right:6px'>{initial}</span>"
        f"<span style='color:#6c7889'>{who}</span></div>",
        unsafe_allow_html=True,
    )
    c2.button("Log out", on_click=_logout, use_container_width=True, key="hdr_logout")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_auth.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add gui_app/auth.py gui_app/tests/test_auth.py
git commit -m "feat: add is_admin + header_account helpers to auth"
```

---

## Task 6: Phase router shell + Welcome + Guide (remove sidebar)

This task rewires `app.py`'s top-level structure. The existing analysis view bodies (Overview/Distance/Heatmaps/Time in zone/Validation/Results) are **preserved as functions** but moved under the new shell in later tasks. In this task we introduce the router, the Welcome screen, the Guide page, remove all sidebar rendering, and inject the theme.

**Files:**
- Modify: `gui_app/app.py`
- Create: `gui_app/guide.py`
- Test: `gui_app/tests/test_app_smoke.py`

**Interfaces:**
- Consumes: `theme.inject_css`, `theme.card`, `routing.resolve_phase`, `records.is_onboarded/mark_onboarded`, `auth.current_user/header_account`, `guide.render_guide`.
- Produces (in `app.py`): a module-level phase router that reads
  `st.session_state["phase"]` and dispatches; helper `go(phase)` that sets
  `st.session_state["phase"]` and calls `st.rerun()`; `current_user_key()`.

- [ ] **Step 1: Write the Guide module**

Create `gui_app/guide.py`:

```python
"""In-app how-to page (black & white)."""
import streamlit as st


def render_guide(on_back):
    if st.button("← Back", key="guide_back"):
        on_back()
    st.title("Guide")
    st.caption("How to prepare your data, load an experiment, and read each analysis.")
    st.markdown(
        """
#### 1. Prepare your data
Put your **manifest CSV** (`bapipe_datafiles.csv` or `datafiles.csv`) in one
folder together with the videos and DeepLabCut `.h5` tracking files it lists.
Optionally add a **metadata CSV** (`id` + group columns such as treatment / sex /
cohort) to compare groups.

#### 2. Start an analysis
Press **Start / New analysis** and follow the three steps: choose the data
folder, tick the animals to load, and confirm the analysis settings (the
defaults are auto-detected and fine for most experiments).

#### 3. Read the analyses
- **Overview** — experiment summary and an original-vs-aligned alignment check.
- **Distance** — total locomotion per group.
- **Heatmaps** — where each group spent its time.
- **Time in zone** — seconds spent in an adjustable centre zone.
- **Validation video** — the tracked keypoints drawn on a real clip.
- **Results** — per-animal metrics and a group summary (mean ± SEM).

#### 4. Your records
When a load finishes, its results are **saved automatically to your private
records** — visible only to you. Raw videos are never stored, only the computed
numbers. Open **My Records** any time to revisit or download past analyses.
        """
    )
```

- [ ] **Step 2: Add the router scaffolding to `app.py`**

In `gui_app/app.py`, immediately after the existing imports block (after `import auth` and the `importlib.reload(...)` lines near the top, around line 35), add the new imports and reloads:

```python
import records
import routing
import theme
import guide
importlib.reload(records)
importlib.reload(routing)
importlib.reload(theme)
importlib.reload(guide)
```

Then replace the CSS `st.markdown(...)` block (the current `<style>` injection at lines ~39-57) with a call to the theme:

```python
theme.inject_css()
```

- [ ] **Step 3: Delete the sidebar rendering**

Remove the sidebar blocks in `app.py`:
- The logo/`st.sidebar.image` loop + `st.sidebar.caption("Developed by Andre Telfer")` + `auth.sidebar_account()` (around lines 144-152).
- The entire `st.sidebar.header("Analysis config")` section and every `st.sidebar.*` widget for box size / alignment / filters / reload / change-data (lines ~181-335). These controls move into the wizard in Task 7 — for now, keep the plain Python variables they produced (`box_w`, `box_h`, `use_box_reference`, `remove_lens`, `pcutoff`, `outlier_sigmas`, `mouse_in_box_tolerance`, `use_pairwise`, `use_bodypart`, `use_centroid`, `use_likelihood`, `use_min_bodyparts`, `min_bodyparts`) by assigning them from `st.session_state` defaults so `do_load` still resolves. Add this defaults block where the sidebar config used to be:

```python
# Analysis settings now live in the Start wizard (Task 7). Until then, resolve
# them from session defaults so do_load() keeps working.
_defaults = dict(box_w=400, box_h=300, use_box_reference=True, remove_lens=cal_present,
                 pcutoff=0.6, outlier_sigmas=3.0, mouse_in_box_tolerance=10,
                 use_pairwise=True, use_bodypart=True, use_centroid=True,
                 use_likelihood=True, use_min_bodyparts=True, min_bodyparts=3)
for _k, _v in _defaults.items():
    st.session_state.setdefault(_k, _v)
box_w = st.session_state["box_w"]; box_h = st.session_state["box_h"]
use_box_reference = st.session_state["use_box_reference"]
remove_lens = st.session_state["remove_lens"]
pcutoff = st.session_state["pcutoff"]; outlier_sigmas = st.session_state["outlier_sigmas"]
mouse_in_box_tolerance = st.session_state["mouse_in_box_tolerance"]
use_pairwise = st.session_state["use_pairwise"]; use_bodypart = st.session_state["use_bodypart"]
use_centroid = st.session_state["use_centroid"]; use_likelihood = st.session_state["use_likelihood"]
use_min_bodyparts = st.session_state["use_min_bodyparts"]; min_bodyparts = st.session_state["min_bodyparts"]
```

Keep `do_load`, `find_manifest`, the data-folder resolution, and all analysis helper functions intact.

- [ ] **Step 4: Add the phase router and Welcome/Guide screens**

Replace everything from the old `render_header()` / setup-screen / `view` dispatch (the whole main-area section starting around line 338 `render_header()` through the end of the file) with a phase router. Add these helpers and the router:

```python
def current_user_key():
    email, _ = auth.current_user()
    return email or "local"


def go(phase):
    st.session_state["phase"] = phase
    st.rerun()


def render_welcome():
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
        st.markdown("### bapipe")
        st.caption("Behaviour Analysis for Keypoint Data")
        c1, c2 = st.columns(2)
        with c1.container(border=True):
            st.markdown("#### Guide")
            st.caption("Learn how to prepare data and read each analysis.")
            if st.button("Open guide →", key="welcome_guide", use_container_width=True):
                records.mark_onboarded(current_user_key()); go("guide")
        with c2.container(border=True):
            st.markdown("#### Start")
            st.caption("Load an experiment and run the analyses.")
            if st.button("Start →", key="welcome_start", use_container_width=True):
                records.mark_onboarded(current_user_key()); go("wizard")


# ---- phase router ----
user_key = current_user_key()
phase = routing.resolve_phase(records.is_onboarded(user_key),
                              st.session_state.get("phase"))

if phase == "welcome":
    render_welcome()
    st.stop()
elif phase == "guide":
    guide.render_guide(on_back=lambda: go("records"))
    st.stop()
elif phase == "wizard":
    st.info("Start wizard — implemented in Task 7.")
    st.stop()
elif phase == "loading":
    st.info("Loading — implemented in Task 8.")
    st.stop()
elif phase == "records":
    st.info("My Records dashboard — implemented in Task 9.")
    if st.button("Start →"):
        go("wizard")
    st.stop()
# phase == "app": analysis views (wired in Task 8)
```

(The stub `st.info(...)` lines are replaced by real screens in Tasks 7-9. Keeping them here makes this task independently runnable.)

- [ ] **Step 5: Write the smoke test**

Create `gui_app/tests/test_app_smoke.py`:

```python
import os
import sys
from pathlib import Path

import pytest

GUI_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI_APP))
APP = str(GUI_APP / "app.py")


@pytest.fixture(autouse=True)
def _tmp_records(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))


def _fresh_apptest():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=30)
    # Auth is enabled via .streamlit/secrets.toml; sign a test admin in so the
    # login gate passes and the phase router runs.
    at.secrets["access"] = {"admins": ["tester@example.com"]}
    at.session_state["auth_email"] = "tester@example.com"
    at.session_state["auth_name"] = "Tester"
    return at


def test_first_time_user_sees_welcome():
    at = _fresh_apptest().run()
    assert not at.exception
    texts = [m.value for m in at.markdown]
    assert any("bapipe" in t for t in texts)
    labels = [b.label for b in at.button]
    assert any("Start" in l for l in labels)
    assert any("guide" in l.lower() for l in labels)


def test_returning_user_sees_records_phase():
    at = _fresh_apptest()
    at.session_state["phase"] = "records"
    at.run()
    assert not at.exception
```

- [ ] **Step 6: Run the smoke test**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_app_smoke.py -q`
Expected: PASS (2 passed). If `AppTest` cannot resolve `import bapipe`, ensure the test is run from `gui_app/` (the app inserts `../src` onto `sys.path` itself).

- [ ] **Step 7: Commit**

```bash
git add gui_app/app.py gui_app/guide.py gui_app/tests/test_app_smoke.py
git commit -m "feat: phase router + Welcome + Guide; remove sidebar; inject B&W theme"
```

---

## Task 7: Start wizard (3 steps)

**Files:**
- Modify: `gui_app/app.py`
- Test: `gui_app/tests/test_app_smoke.py`

**Interfaces:**
- Consumes: existing `find_manifest`, `manifest_df`, `_autodetect_box`, `do_load`, `cal_present`, and the analysis-setting session keys from Task 6.
- Produces: `render_wizard()` driven by `st.session_state["wizard_step"] in (0,1,2)`; step 3's primary button sets `phase="loading"` and stores `pending_load_ids`.

- [ ] **Step 1: Implement `render_wizard()`**

Add to `app.py` (above the phase router) a function that renders the three steps. Port the existing setup widgets (data folder + metadata from the old `① Data folder & metadata` expander; animal picker from the old `② Select animals` form; box/align/lens + advanced filters from the old sidebar) into three stacked steps inside a centred card. Wire the config widgets to the same `st.session_state` keys used by `do_load` (`box_w`, `box_h`, `use_box_reference`, `remove_lens`, `pcutoff`, `outlier_sigmas`, `min_bodyparts`, `mouse_in_box_tolerance`, and the four `use_*` filter toggles):

```python
def _stepper(step):
    labels = ["Choose data", "Select animals", "Configure"]
    cols = st.columns(len(labels))
    for i, lab in enumerate(labels):
        mark = "✓" if i < step else str(i + 1)
        cols[i].markdown(
            f"<div style='text-align:center'><span class='avatar' "
            f"style='background:{'#111' if i <= step else '#c2ccd8'}'>{mark}</span>"
            f"<div style='font-size:13px;font-weight:600;color:"
            f"{'#111' if i == step else '#6c7889'}'>{lab}</div></div>",
            unsafe_allow_html=True)


def render_wizard():
    step = st.session_state.setdefault("wizard_step", 0)
    if st.button("← Back to records", key="wiz_home"):
        go("records")
    _stepper(step)
    st.divider()

    if step == 0:  # choose data
        st.subheader("Where is your experiment?")
        st.text_input("Data folder", key="data_folder_input",
                      help="Folder with the manifest CSV plus its videos and tracking files.")
        if data_status:
            (st.success if data_status[0] == "success" else st.error)(data_status[1])
        st.text_input("Metadata CSV (optional)", key="meta_input")
        st.text_input("Metadata join column", key="join_input")
        if st.button("Next: select animals →", type="primary", disabled=manifest_df is None):
            st.session_state["wizard_step"] = 1; st.rerun()

    elif step == 1:  # select animals
        st.subheader("Which animals to load?")
        ids = manifest_df["id"].astype(str).tolist()
        st.session_state.setdefault("wizard_sel",
                                    {i: (k < 8) for k, i in enumerate(ids)})
        cA, cB = st.columns(2)
        if cA.button("Select all"):
            st.session_state["wizard_sel"] = {i: True for i in ids}
        if cB.button("Clear"):
            st.session_state["wizard_sel"] = {i: False for i in ids}
        with st.container(height=340):
            for i in ids:
                st.session_state["wizard_sel"][i] = st.checkbox(
                    i, value=st.session_state["wizard_sel"].get(i, False), key=f"wsel_{i}")
        n = sum(1 for v in st.session_state["wizard_sel"].values() if v)
        st.caption(f"{n} of {len(ids)} selected")
        b1, b2 = st.columns(2)
        if b1.button("← Back"):
            st.session_state["wizard_step"] = 0; st.rerun()
        if b2.button("Next: configure →", type="primary", disabled=n == 0):
            st.session_state["wizard_step"] = 2; st.rerun()

    else:  # configure
        st.subheader("Analysis settings")
        c1, c2 = st.columns(2)
        c1.number_input("Arena width", min_value=1, key="box_w")
        c2.number_input("Arena height", min_value=1, key="box_h")
        st.checkbox("Align videos to box", key="use_box_reference")
        st.checkbox("Remove lens distortion", key="remove_lens")
        if st.session_state["remove_lens"] and not cal_present:
            st.warning("No camera_calibrations.json found — loading will fail with this on.")
        with st.expander("Advanced: outlier filtering"):
            st.slider("Tracking confidence cutoff (pcutoff)", 0.0, 1.0, key="pcutoff", step=0.05)
            st.slider("Outlier sensitivity (σ)", 1.0, 6.0, key="outlier_sigmas", step=0.5)
            st.number_input("Minimum bodyparts", min_value=1, key="min_bodyparts")
            st.number_input("Mouse-in-box tolerance (frames)", min_value=1, key="mouse_in_box_tolerance")
            st.checkbox("Filter by pairwise distance", key="use_pairwise")
            st.checkbox("Filter by bodypart velocity", key="use_bodypart")
            st.checkbox("Filter by centroid velocity", key="use_centroid")
            st.checkbox("Filter by likelihood", key="use_likelihood")
            st.checkbox("Filter by minimum bodyparts", key="use_min_bodyparts")
        d1, d2 = st.columns(2)
        if d1.button("← Back"):
            st.session_state["wizard_step"] = 1; st.rerun()
        sel_ids = [i for i, v in st.session_state.get("wizard_sel", {}).items() if v]
        if d2.button(f"Load experiment ({len(sel_ids)})", type="primary", disabled=not sel_ids):
            st.session_state["pending_load_ids"] = sel_ids
            go("loading")
```

Note: the config widgets bind directly to the same session keys `do_load` reads, so the Task 6 defaults block still initialises them and the widgets just override. Remove the now-redundant scalar re-assignment lines from Task 6 that read those keys into locals **only if** `do_load` is refactored to read from session; otherwise keep them — `do_load` closes over the module-level locals, so keep the re-assignment block and ensure it runs before `do_load` is called (it does, at module top on every rerun).

- [ ] **Step 2: Wire the router to the wizard**

In the phase router, replace the wizard stub:

```python
elif phase == "wizard":
    render_wizard()
    st.stop()
```

- [ ] **Step 3: Smoke-test the wizard renders**

Append to `gui_app/tests/test_app_smoke.py`:

```python
def test_wizard_renders_step_zero():
    at = _fresh_apptest()
    at.session_state["phase"] = "wizard"
    at.run()
    assert not at.exception
    assert any("experiment" in (m.value or "").lower() for m in at.markdown + at.subheader)
```

- [ ] **Step 4: Run the smoke test**

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_app_smoke.py -q`
Expected: PASS. (If `at.subheader` is unavailable in this Streamlit version, assert on `at.markdown` only.)

- [ ] **Step 5: Commit**

```bash
git add gui_app/app.py gui_app/tests/test_app_smoke.py
git commit -m "feat: 3-step Start wizard (choose data / select animals / configure)"
```

---

## Task 8: Loading screen, auto-save, and top-bar analysis shell

**Files:**
- Modify: `gui_app/app.py`
- Test: `gui_app/tests/test_records.py` (auto-save unit), `gui_app/tests/test_app_smoke.py`

**Interfaces:**
- Consumes: `do_load`, `records.assemble_record`, `records.add_record`, `theme.top_bar`-style HTML, existing view functions.
- Produces: `render_loading()`, `autosave_current_load(sel_ids)`, `render_app_shell()` with `st.tabs` for the six views.

- [ ] **Step 1: Unit-test the auto-save assembly path**

Append to `gui_app/tests/test_records.py`:

```python
def test_autosave_snapshot_has_expected_fields(records):
    import pandas as pd
    per = pd.DataFrame(
        {"distance": [1.0, 2.0], "time_in_zone": [3.0, 4.0], "duration_s": [5.0, 6.0]},
        index=pd.Index(["m1", "m2"], name="id"),
    )
    rec = records.assemble_record("run", ["m1", "m2"],
                                  {"box_shape": [400, 300]}, per, None)
    stored = records.add_record("u@x.com", rec)
    got = records.get_record("u@x.com", stored["id"])
    assert len(got["results"]["per_animal"]) == 2
    assert {"id", "distance", "time_in_zone", "duration_s"} <= set(got["results"]["per_animal"][0])
```

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_records.py -q`
Expected: PASS.

- [ ] **Step 2: Implement loading + auto-save + app shell**

Add to `app.py`:

```python
def autosave_current_load(sel_ids):
    """After a successful load, compute per-animal metrics + group summary and
    save a results-only snapshot to the current user's private records."""
    vs = st.session_state["video_set"]
    cfg = st.session_state["config"]
    md = st.session_state.get("metadata")
    vids = [vs[vs.index.index(i)] for i in sel_ids if i in set(vs.index)]
    ref = reference_frame(vs[0]); fh, fw = ref.shape[:2]
    half = max(10, min(int(min(fw, fh) // 2), 50))
    zone = analysis.square_zone(fw / 2, fh / 2, half)
    per = pd.DataFrame(
        {"distance": [analysis.distance_travelled(v) for v in vids],
         "time_in_zone": [analysis.time_in_zone(v, zone) for v in vids],
         "duration_s": [round(v.duration, 2) for v in vids]},
        index=pd.Index([i for i in sel_ids if i in set(vs.index)], name="id"),
    )
    gcols = ([c for c in md.columns
              if not (pd.api.types.is_float_dtype(md[c]) or pd.api.types.is_bool_dtype(md[c]))]
             if md is not None else [])
    summary = None
    if gcols:
        joined = per.join(md[gcols])
        summary = joined.groupby(gcols[0])[["distance", "time_in_zone", "duration_s"]].mean()
    cfg_summary = {"box_shape": list(cfg.box_shape),
                   "use_box_reference": cfg.use_box_reference,
                   "remove_lens_distortion": cfg.remove_lens_distortion}
    name = f"{len(sel_ids)} animals · {pd.Timestamp.now():%Y-%m-%d %H:%M}"
    rec = records.assemble_record(name, sel_ids, cfg_summary, per, summary)
    records.add_record(current_user_key(), rec)


def render_loading():
    sel_ids = st.session_state.get("pending_load_ids", [])
    st.markdown("<div style='height:12vh'></div>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.spinner(f"Loading {len(sel_ids)} videos…"):
            try:
                do_load(sel_ids)
                autosave_current_load(sel_ids)
            except Exception as e:
                st.error(f"Failed to load: {e}")
                if st.button("← Back to setup"):
                    go("wizard")
                st.stop()
    st.session_state["view"] = "Overview"
    go("app")


def render_top_bar(title, sub):
    c1, c2 = st.columns([2, 1], vertical_alignment="center")
    c1.markdown(f"<div class='topbar'><div><div class='title'>{title}</div>"
                f"<div class='sub'>{sub}</div></div></div>", unsafe_allow_html=True)
    with c2:
        b1, b2 = st.columns(2)
        if b1.button("Guide", key="app_guide", use_container_width=True):
            go("guide")
        if b2.button("Change data", key="app_change", use_container_width=True):
            for k in ("video_set", "config", "metadata"):
                st.session_state.pop(k, None)
            st.session_state["wizard_step"] = 0
            go("wizard")
    auth.header_account()
```

- [ ] **Step 3: Replace the app-shell dispatch to use tabs**

Replace the old `view = st.session_state.setdefault("view", "Home")` card-home dispatch with a top-bar + `st.tabs` shell that calls the existing view render functions. In the phase router, replace the trailing "app" section:

```python
elif phase == "app":
    if "video_set" not in st.session_state:
        go("wizard")
    render_top_bar("Analysis", "Explore your loaded experiment")
    video_set = st.session_state["video_set"]
    config = st.session_state["config"]
    metadata = st.session_state["metadata"]
    box_shape = config.box_shape
    # ... (existing per-view setup: group_cols, all_ids, loaded_ids, helper defs) ...
    tabs = st.tabs(["Overview", "Distance", "Heatmaps", "Time in zone",
                    "Validation video", "Results"])
    with tabs[0]:
        render_overview()
    with tabs[1]:
        render_distance()
    with tabs[2]:
        render_heatmaps()
    with tabs[3]:
        render_zone()
    with tabs[4]:
        render_validation()
    with tabs[5]:
        render_results()
```

Refactor the existing `elif view == "…":` blocks (Overview/Distance/Heatmaps/Time in zone/Validation video/Results) into functions `render_overview()` … `render_results()` containing the **same body as today** (move the code verbatim into the function; keep every `analysis.*` call, widget, and export unchanged). They read `video_set`, `config`, `metadata`, `box_shape`, and the helper functions from module scope, so define them after those are set — or pass them as needed. Keep `animal_selector`, `group_selector`, `videos_for`, `fig_export`, `metric_by_group`, `ensure_loaded`, `reference_frame` unchanged.

- [ ] **Step 4: Add the loading route**

In the router, replace the loading stub:

```python
elif phase == "loading":
    render_loading()
    st.stop()
```

- [ ] **Step 5: Smoke-test loading is reachable without exception (no real videos)**

Because loading needs real video files, verify only that entering the `app` phase without a loaded `video_set` safely redirects to the wizard (no crash):

Append to `gui_app/tests/test_app_smoke.py`:

```python
def test_app_phase_without_data_redirects():
    at = _fresh_apptest()
    at.session_state["phase"] = "app"
    at.run()
    assert not at.exception
```

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_app_smoke.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui_app/app.py gui_app/tests/test_records.py gui_app/tests/test_app_smoke.py
git commit -m "feat: loading screen, auto-save on load, top-bar tabbed analysis shell"
```

---

## Task 9: My Records dashboard

**Files:**
- Modify: `gui_app/app.py`
- Test: `gui_app/tests/test_app_smoke.py`

**Interfaces:**
- Consumes: `records.list_records`, `records.get_record`, `records.delete_record`.
- Produces: `render_records()`.

- [ ] **Step 1: Implement `render_records()`**

Add to `app.py`:

```python
def render_records():
    render_top_bar("Dashboard", "Your saved analyses")
    a1, a2, _ = st.columns([1, 1, 4])
    if a1.button("＋ New analysis", type="primary"):
        st.session_state["wizard_step"] = 0
        for k in ("video_set", "config", "metadata"):
            st.session_state.pop(k, None)
        go("wizard")
    if a2.button("Guide"):
        go("guide")

    recs = records.list_records(current_user_key())
    if not recs:
        st.info("No saved records yet — press New analysis to begin.")
        return

    opened = st.session_state.get("open_record")
    if opened:
        rec = records.get_record(current_user_key(), opened)
        if rec:
            if st.button("← Back to records"):
                st.session_state.pop("open_record"); st.rerun()
            st.subheader(rec["name"])
            st.caption(f"Saved {rec['created']} · {len(rec['animals'])} animals")
            per = pd.DataFrame(rec["results"]["per_animal"])
            st.markdown("**Per-animal results**")
            st.dataframe(per, use_container_width=True)
            st.download_button("Download CSV", per.to_csv(index=False).encode(),
                               f"{rec['id']}_per_animal.csv", "text/csv")
            import json as _json
            st.download_button("Download JSON", _json.dumps(rec, indent=2).encode(),
                               f"{rec['id']}.json", "application/json")
            if rec["results"]["group_summary"]:
                st.markdown("**Group summary**")
                st.dataframe(pd.DataFrame(rec["results"]["group_summary"]),
                             use_container_width=True)
        return

    for rec in recs:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
            c1.markdown(f"**{rec['name']}**")
            c1.caption(f"Saved {rec['created']}")
            c2.caption(f"{len(rec['animals'])} animals · "
                       f"box {rec['config'].get('box_shape')}")
            if c3.button("Open", key=f"open_{rec['id']}"):
                st.session_state["open_record"] = rec["id"]; st.rerun()
            if c4.button("Delete", key=f"del_{rec['id']}"):
                records.delete_record(current_user_key(), rec["id"]); st.rerun()
```

- [ ] **Step 2: Wire the router**

Replace the records stub in the router:

```python
elif phase == "records":
    render_records()
    st.stop()
```

- [ ] **Step 3: Smoke-test the dashboard lists a seeded record**

Append to `gui_app/tests/test_app_smoke.py`:

```python
def test_records_dashboard_lists_seeded_record(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    import records as recmod
    import importlib
    importlib.reload(recmod)
    recmod.add_record("tester@example.com", {
        "name": "seeded run", "animals": ["m1"],
        "config": {"box_shape": [400, 300]},
        "results": {"per_animal": [{"id": "m1", "distance": 1.0}], "group_summary": []},
    })
    at = _fresh_apptest()
    at.session_state["phase"] = "records"
    at.run()
    assert not at.exception
    assert any("seeded run" in (m.value or "") for m in at.markdown)
```

Run: `cd gui_app && ../.venv/bin/python -m pytest tests/test_app_smoke.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add gui_app/app.py gui_app/tests/test_app_smoke.py
git commit -m "feat: private My Records dashboard (open / download / delete)"
```

---

## Task 10: Greyscale charts

**Files:**
- Modify: `gui_app/app.py`

**Interfaces:**
- Consumes: `theme.group_greys`.

- [ ] **Step 1: Recolour the bar charts to greyscale**

In the Distance, Time-in-zone, and any grouped `sns.barplot`/`ax.bar` calls inside the view functions, replace the `color=bar_color` colour-picker inputs and default seaborn palette with greyscale from `theme.group_greys`. Concretely, remove the `st.color_picker(...)` widgets (Distance `dist_color`, Time-in-zone `zone_color`) and instead:

```python
# grouped bars: one grey (+ hatch) per group, in group order
greys = theme.group_greys(len(data[group_col].unique()) if group_col else 1)
palette = [g[0] for g in greys]
bars = sns.barplot(data=data, x=group_col, y="distance", ax=ax, palette=palette)
for patch, (_, hatch) in zip(bars.patches, greys):
    if hatch:
        patch.set_hatch(hatch)
```

For single-series (per-animal) bars use a solid `color="#444444"`.

- [ ] **Step 2: Recolour heatmaps to greyscale**

In `render_heatmaps()`, change the contour colormap from `cmap="Reds"` to `cmap="Greys"` and the legend/description text accordingly ("darker = more time"). Leave the KDE math unchanged.

- [ ] **Step 3: Verify charts still render (manual)**

Run the app (Task 11 covers the full launch) and open Distance, Time in zone, Heatmaps; confirm the charts render in greyscale without a colour picker and without exceptions. There is no unit test for matplotlib colour; this is verified in Task 11.

- [ ] **Step 4: Commit**

```bash
git add gui_app/app.py
git commit -m "feat: greyscale bar charts (lightness + hatch) and Greys heatmaps"
```

---

## Task 11: Full test suite + manual verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `cd gui_app && ../.venv/bin/python -m pytest -q`
Expected: all tests PASS (records, routing, theme, auth, app smoke).

- [ ] **Step 2: Launch the app and verify the flows**

Run: `cd "$(git rev-parse --show-toplevel)" && ./.venv/bin/python -m streamlit run gui_app/app.py`

Verify manually (use the `verify` skill to drive it):
1. **First-time user:** with a brand-new record store (delete `gui_app/records/<you>.json` or set `BAPIPE_RECORDS_DIR` to an empty temp dir), logging in shows the **Welcome** screen with exactly **Guide** and **Start** cards, and **no sidebar**.
2. **Guide:** the Guide button opens the in-app how-to and Back returns.
3. **Start wizard:** three steps (Choose data → Select animals → Configure); loading runs; the app opens on Overview with a **top bar + tabs** (no sidebar).
4. **Auto-save:** after loading, a new record appears in **My Records** without pressing any Save button; it contains numbers only (open the JSON — no video paths/frames).
5. **Returning user:** reload the page / log in again → lands directly on **My Records** (not Welcome).
6. **Records privacy:** open/download/delete work; confirm no admin UI anywhere lists another user's records.
7. **B&W:** all chrome and charts are black/white/grey — no blue.

- [ ] **Step 3: Finish the branch**

Use the `superpowers:finishing-a-development-branch` skill to decide how to integrate the work.

---

## Self-Review

**Spec coverage:**
- §4 routing → Tasks 3, 6. ✅
- §5.1 Welcome → Task 6. ✅
- §5.2 My Records → Task 9. ✅
- §5.3 wizard → Task 7. ✅
- §5.4 loading → Task 8. ✅
- §5.5 top-bar analysis views → Task 8. ✅
- §5.6 Guide → Task 6. ✅
- §6 B&W theme + greyscale charts → Tasks 4, 10. ✅
- §7 records store + auto-save + privacy → Tasks 1, 2, 8, 9. ✅
- §8 files → all created/modified across tasks. ✅
- §9 testing → Tasks 1-9 unit/smoke + Task 11 manual. ✅
- §10 resolved details (greyscale groups, auto-save, My Records, in-app guide) → Tasks 10, 8, 9, 6. ✅

**Placeholder scan:** The Task 6/7/8 stub `st.info("… implemented in Task N")` lines are intentional, each replaced by a later task's real screen; no `TODO`/`TBD` left in shipped code paths. Task 8 Step 3 asks to move existing view bodies verbatim rather than reproducing ~250 lines — acceptable because the code already exists in `app.py` and is being relocated, not written.

**Type consistency:** `current_user_key()` used consistently; `records.add_record`/`get_record`/`delete_record`/`list_records`/`assemble_record` signatures match between definition (Tasks 1-2) and callers (Tasks 8-9); `theme.group_greys` returns `(color, hatch)` pairs consumed correctly in Task 10; `routing.resolve_phase(onboarded, session_phase)` matches its caller in Task 6.
