# bapipe-keypoints — Analysis Dashboard (GUI)

A user-friendly web dashboard for the `bapipe` behavioural-analysis pipeline. Load a
`datafiles.csv` manifest, tweak a few options, and explore the analyses in your browser —
no Python coding required.

## Views
- **Overview** — experiment summary + original-vs-aligned video montage
- **Distance** — total distance travelled, grouped by treatment
- **Heatmaps** — occupancy density per group
- **Time in zone** — time in an adjustable centered zone, per group
- **Validation video** — annotated clip with keypoints drawn on the mouse

Arena alignment is **automatic**: the box size is auto-detected from each animal's labelled arena
corners (likelihood-filtered, robust) when you open a folder, and the corners drive the perspective
alignment when *Align videos to box* is on. Adjust the box size manually if you have a real-mm
reference, or press *Re-detect box size from arena corners*.

Every view has an **Animals (select / deselect)** expander (options include the whole manifest —
picking one that wasn't loaded loads it on demand), and figures have **Export** (png/pdf/jpeg)
buttons. Config changes (box size, alignment, filters) apply after **↻ Reload with current
settings** in the sidebar.

## Setup

Requires **Python 3.11** (the `bapipe` library targets the pandas 1.x API; the
requirements pin a matching scientific stack). From the `bapipe-keypoints/` project directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r gui_app/requirements.txt
```

You do **not** need `pip install -e .` — the app adds `../src` to `sys.path` and imports
`bapipe` directly (this also avoids pulling in the heavy napari/PyQt dependency).

> **macOS note:** on some machines the `tables` (PyTables) wheel for older Pythons ships
> without its bundled HDF5 library. Python 3.11 wheels are self-contained and avoid this;
> if you hit a `libhdf5` load error, stick with 3.11.

## Run

```bash
streamlit run gui_app/app.py
# or:
bash gui_app/run_gui.sh
```

Then, on the **setup screen** (main area):
1. **Choose your data** — enter the folder that holds your manifest CSV
   (`bapipe_datafiles.csv` or `datafiles.csv`) plus the `videos/`, `mouse_labels/`,
   `landmark_labels/` it references, and optionally a metadata CSV (`id` + group columns). The app
   auto-detects the manifest and, if present, the `experiment-data.csv` metadata used for grouping.
2. **Select animals** — the manifest is listed as a checkbox table; tick the animals you want
   (or use *Select all* / *Clear*), then click **Load experiment**. (Use **← Change data / animals**
   in the sidebar to come back here.)
3. **Analysis config** (sidebar) — box size, alignment / lens-distortion toggles, and (under
   *Advanced*) the outlier-filter settings — these map directly to `bapipe.AnalysisConfig`.
   - **Auto-detect box size** — click *Auto-detect box size from arena corners* to fill the
     width/height from the labelled arena corners in the landmark file. These come out in **video
     pixels** (true aspect ratio); if you know the real size (e.g. 400 mm wide), type mm instead
     or scale by `known_mm / detected_px`. There is no way to recover real-world millimetres from
     the corners alone without such a reference.
4. Browse the tabs (Overview, Distance, Heatmaps, Time in zone, Validation video).

## Authentication (optional — email/password + Google, with admin approval)
By default the app runs with **no login**. To require sign-in:

1. Copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml`. Add your admin email under
   `[access]`. Keep the `[auth]` block (with Google OAuth `client_id` / `client_secret` /
   `cookie_secret`) to **also** offer Google login, or delete it for **email/password only**.
2. `pip install -r gui_app/requirements.txt` (includes `bcrypt` and `Authlib`) and restart.

Then:
- **Email/password** — users **Sign up** on the login page; the account is stored bcrypt-hashed in
  `gui_app/users.json` and lands on an **"Access pending"** screen.
- **Google** — a "Log in with Google" button appears when `[auth]` is configured (uses Streamlit's
  native OIDC; create a Web-application OAuth client and set the redirect URI to
  `http://<host>/oauth2callback`).
- **Admin approval** — new accounts (either method) stay pending until an **admin approves** them
  from the sidebar *Admin — approvals* panel (or by adding the email to the allow-list). Admins are
  seeded from `secrets["access"]["admins"]`; approvals live in `gui_app/access.json`.

Remove `secrets.toml` to turn auth back off. (Google login persists across refresh via Streamlit's
cookie; an email/password session ends on a hard refresh — just log in again.)

## Notes
- Loading runs **single-process** by design (multiprocessing is fragile under Streamlit); large
  experiments load fine, just start with a small N.
- Validation clips are written with `imageio`'s bundled ffmpeg, so no system `ffmpeg` is needed.
- The napari-based arena-registration and project-setup steps are **not** part of this GUI — it wraps
  the analysis API only. Build the manifest as before (or with `generate_bapipe_inputs.py`).
