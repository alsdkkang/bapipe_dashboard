# bapipe Dashboard — Black & White Redesign

**Date:** 2026-07-15
**Status:** Approved design, ready for implementation planning
**Stack:** Streamlit (existing `gui_app/`), re-skinned. No React rewrite, no backend API.

---

## 1. Goal

Redesign the bapipe Streamlit dashboard so that:

1. The **sidebar is turned off**; all controls move into the main area.
2. **First-time users** land on a Welcome screen with exactly **two cards — Guide and Start**.
3. **Returning users** skip Welcome and land directly on their **My Records dashboard**.
4. **Analysis results are auto-saved** to a **per-user, private record store** on load. Raw
   video/pose data is never saved. Records are viewable/deletable **only by the owning user**;
   there is **no admin UI** to view them (UI-level privacy).
5. The visual language borrows the reference design system's **layout/structure** (3-step setup
   wizard, top bar, stat cards, eyebrow-labelled cards, SEM bar charts, data tables) but is
   rendered in **black & white** — not the reference's blue/slate palette.

The reference prototype (`Web dashboard for non-coders.zip`, a React `Dashboard.dc.html`) is a
**visual/layout reference only**. We reproduce its structure in Streamlit + injected CSS.

## 2. Non-goals (YAGNI)

- No React/Next rewrite; no separate backend API; no Cloud Run deployment changes.
- No encryption-at-rest for records (user chose UI-level privacy — see §7).
- No processing of raw 7 GB video in the cloud; the app remains "results only" when the raw
  data folder is absent (this is already how session state works — nothing new required here).
- No changes to the bapipe analysis math (`analysis.py`, `src/bapipe/`).

## 3. Users & auth (unchanged)

Auth stays as-is (`auth.py`): email/password + optional Google, admin-approved allow-list.
The signed-in **email is the record-store key**. When auth is disabled (no secrets), fall back
to a single local key `"local"` so local runs still work.

## 4. Routing / phases

Top-level state machine in `app.py`, replacing the current sidebar-config + expander flow:

```
require_login()                      # unchanged gate
user = current_user().email or "local"
onboarded = records.is_onboarded(user)

phase (st.session_state["phase"]):
  "welcome"  → first-time only (onboarded == False and no phase set)
  "records"  → My Records dashboard (default for returning users)
  "wizard"   → 3-step Start flow (Choose data → Select animals → Configure)
  "loading"  → dark loading screen while do_load runs
  "app"      → analysis views (topbar + tabs)
  "guide"    → in-app Guide page
```

Initial phase resolution on each run:
- If `phase` already in session → use it.
- Else if `onboarded` → `"records"`.
- Else → `"welcome"`.

Entering the wizard or guide from Welcome calls `records.mark_onboarded(user)` so the next
login goes straight to `"records"`.

## 5. Screens

### 5.1 Welcome (first-time)
Centred layout, dotted background, brand header (`bapipe` / "Behaviour Analysis for Keypoint
Data"). Exactly **two cards**:
- **Guide** — "Learn how to prepare data and read each analysis." → `phase="guide"`.
- **Start** — "Load an experiment and run the analyses." → `phase="wizard"`.

Black & white: white card surfaces, `#111` titles, grey body text, `Open guide →` / `Start →`
link-style CTAs.

### 5.2 My Records dashboard (returning / after onboarding)
- Top bar: logo + "Dashboard" + right-aligned avatar → logout.
- Actions row: **＋ New analysis** (→ `phase="wizard"`) and **Guide** link (→ `phase="guide"`).
- **Saved records list** (cards or table). Each row shows: name, saved date, #animals, metrics
  captured, config summary (box size / alignment / filters). Row actions:
  - **Open** → read-only view of the saved result tables + downloads (no video reload).
  - **Download** → CSV and/or JSON of the saved snapshot.
  - **Delete** → remove the record from the user's store.
- Empty state: "No saved records yet — press New analysis to begin."

### 5.3 Start wizard (3 steps, B&W)
Reproduces the reference wizard structure; stepper shows **① Choose data → ② Select animals →
③ Configure**.
- **① Choose data:** data-folder input + optional metadata CSV + join column; live validation
  ("manifest found · N animals" / error states). Same manifest logic as today (`find_manifest`).
- **② Select animals:** roster with checkboxes, Select all / Clear, count.
- **③ Configure:** box width/height (auto-detected), align-to-box, remove-lens toggles, and an
  **Advanced: outlier filtering** expander (pcutoff, sigmas, min bodyparts, the four filter
  toggles). These are exactly today's sidebar controls, relocated.
- Primary button "Load experiment (N)" → `phase="loading"`, runs `do_load(selected_ids)`.

### 5.4 Loading screen
Dark panel, centred spinner + progress bar with step messages (Reading manifest → Opening
videos → …). On completion: auto-save the record (§7), then `phase="app"`, `view="Overview"`.

### 5.5 Analysis views (top bar, no sidebar)
- **Top bar:** title + subtitle for the current view, animals count, Guide button, avatar.
- **Underline tabs:** Overview / Distance / Heatmaps / Time in zone / Validation video / Results.
- Content keeps today's analysis behaviour (`analysis.py` calls) but re-skinned: stat cards,
  eyebrow-labelled cards, SEM bar charts with individual points, data tables.
- A "Change data / animals" affordance (returns to the wizard) lives in the top bar or an
  overflow menu, replacing the old sidebar buttons. A "Reload with current settings" action is
  also relocated here.

### 5.6 Guide page
New in-app how-to (Streamlit page/view): data preparation → loading → what each analysis means.
Black & white, reachable from Welcome, the records dashboard, and the analysis top bar. A
"← Back" returns to the previous phase.

## 6. Visual system (black & white)

Port the reference design tokens but substitute colour:

- **Typography:** IBM Plex Sans (UI) + IBM Plex Mono (numerics/IDs), loaded via Google Fonts.
- **Spacing / radius / shadow / motion:** adopt the reference `layout.css` tokens as-is.
- **Colour → greyscale:**
  - Primary / active / buttons / focus = `#111`.
  - Surfaces = white (`#fff`) on a near-white canvas (`#fafbfc`), sunken = light grey.
  - Text: strong `#111`, body `#37414e`→grey, muted/faint greys. Borders = light greys.
  - **No blue accent.** Where the reference uses `--accent` (blue), use `#111`.
- **Charts (matplotlib):** greyscale. Group differentiation uses **lightness steps and/or hatch
  patterns**, not hue. A small ordered grey ramp (e.g. `#111 / #555 / #888 / #bbb`) plus hatch
  fallback when groups exceed the ramp. Grid lines light grey; SEM whiskers + individual points
  black at low opacity.
- **Implementation:** a `theme.py` that injects a `<style>` block (token `:root` variables +
  Streamlit widget overrides + hide-sidebar CSS). HTML cards / stat tiles / top bar rendered via
  `st.markdown(..., unsafe_allow_html=True)`. Accept that Streamlit widget styling is not
  pixel-perfect; aim for ~90% fidelity to the reference in B&W.

## 7. Records model, auto-save, privacy

### Store
- Location: `gui_app/records/<key>.json`, where `<key>` is a filesystem-safe hash/slug of the
  user email (or `"local"`). One file per user.
- Shape:
  ```json
  {
    "onboarded": true,
    "records": [
      {
        "id": "<uuid>",
        "name": "AgRP open-field · 12 animals",
        "created": "2026-07-15T13:43:00",
        "animals": ["m1", "m2", "..."],
        "config": {"box_shape": [400, 300], "use_box_reference": true,
                    "remove_lens_distortion": true, "pcutoff": 0.6, "...": "..."},
        "results": {
          "per_animal": [{"id": "m1", "distance": 27000, "time_in_zone": 12.0,
                           "duration_s": 650}, "..."],
          "group_summary": [{"group": "saline", "distance_mean": 26580,
                              "distance_sem": 915, "n": 6}, "..."]
        }
      }
    ]
  }
  ```

### Auto-save
- On successful `do_load` completion (end of the loading phase), compute the per-animal metrics
  and group summary that the Results view already computes, and append a record automatically.
  No explicit "Save" button.
- Debounce/dedupe: if a load produces a snapshot identical (same animals + config) to the most
  recent record, update its timestamp instead of appending a duplicate.
- **Saved:** numbers + small metadata only. **Never saved:** raw videos, pose `.h5`, frames,
  montage/heatmap images.

### Privacy (UI-level, per user's choice)
- Only the owning user's file is read/written, keyed by their signed-in email.
- The admin panel (`auth.sidebar_account` admin section) is **not** given any UI to browse other
  users' records. Records never appear in any admin view.
- Explicitly documented limitation: a person with server filesystem access can read the JSON
  files. This is acceptable per the chosen "UI 차단만" option; encryption-at-rest is out of scope.
- Add `gui_app/records/` to `.gitignore`.

## 8. Files

- `gui_app/app.py` — restructured: phase router, welcome, records dashboard, wizard, loading,
  top-bar analysis shell, guide. Remove all sidebar rendering.
- `gui_app/records.py` — **new**: `is_onboarded`, `mark_onboarded`, `list_records`,
  `add_record`, `get_record`, `delete_record`, keyed by user. Single responsibility, JSON-backed.
- `gui_app/theme.py` — **new**: inject B&W token CSS + Streamlit overrides + hide sidebar; small
  HTML component helpers (card, stat tile, top bar, brand header).
- `gui_app/guide.py` (or a `render_guide()` in `app.py`) — **new**: in-app how-to content.
- `gui_app/auth.py` — minor: expose `is_admin(email)`; move account/logout affordance out of the
  sidebar into the top bar (a `header_account()` helper) while keeping `sidebar_account()` usable
  or deprecated.
- `.gitignore` — add `gui_app/records/`.
- Matplotlib helpers — a small greyscale palette/hatch helper used by the charts.

## 9. Testing

Streamlit `AppTest` (already used per `app.py` comments):

1. **Routing:** a fresh user (onboarded=false) sees Welcome; a user with `onboarded=true` sees
   the records dashboard; entering wizard/guide sets onboarded.
2. **Auto-save:** completing a load appends exactly one record with the expected per-animal +
   group-summary fields; a second identical load does not duplicate.
3. **Records CRUD:** open shows saved tables read-only; delete removes it; download produces
   CSV/JSON.
4. **Privacy:** no admin code path lists another user's records; records store path is per-user.
5. **Sidebar off:** the app renders without the sidebar; relocated controls (data folder,
   filters, logout, change-data) are reachable in the main area / top bar.

Run the existing test suite plus the new tests before completion.

## 10. Open detail resolved during design

- **Group colours in B&W:** groups are distinguished by **greyscale lightness steps and hatch
  patterns**, never hue (§6).
- **Save trigger:** **automatic on load completion**, not a button (§7).
- **"Their dashboard" for returning users:** the **My Records dashboard** (§5.2).
- **Guide content:** a **new in-app how-to page** (§5.6).
