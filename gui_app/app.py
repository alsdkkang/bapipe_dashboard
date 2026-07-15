"""User-friendly Streamlit dashboard for bapipe-keypoints.

Point it at a bapipe `datafiles.csv` manifest, set a few options, click
"Load experiment", then explore the analysis dashboards. No coding required.

Run with:
    streamlit run gui_app/app.py
"""
import io
import sys
import tempfile
from pathlib import Path

# Make `import bapipe` (from ../src) and `import analysis` (this folder) work
# whether the app is launched via `streamlit run` or the AppTest harness.
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
for p in (str(HERE), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st

import bapipe
import analysis
import auth
# Streamlit reruns app.py but keeps imported local modules cached; reload so edits
# to these take effect without restarting the server.
import importlib
importlib.reload(analysis)
importlib.reload(auth)
import records
import routing
import theme
import guide
importlib.reload(records)
importlib.reload(routing)
importlib.reload(theme)
importlib.reload(guide)

st.set_page_config(page_title="bapipe-keypoints dashboard", layout="wide")

theme.inject_css()

# Gate the whole app behind login (email/password + optional Google) + admin approval.
# No-op unless secrets are configured, so local use keeps working without credentials.
LOGO_PATH = next((p for p in (HERE / "logo.svg", HERE.parent / "logo.svg",
                              HERE / "logo.png", HERE.parent / "logo.png") if p.exists()), None)
auth.require_login(LOGO_PATH)


class loading:
    """Context manager showing a blinking 'loading' text (no spinner icon)."""

    def __init__(self, text="loading"):
        self.text = text

    def __enter__(self):
        self._ph = st.empty()
        self._ph.markdown(f'<div class="blink-loading">{self.text}</div>',
                          unsafe_allow_html=True)
        return self

    def __exit__(self, *exc):
        self._ph.empty()
        return False

# The folder that ships with the known dataset, used as a default if present.
DEFAULT_FOLDER = Path(__file__).resolve().parent.parent.parent / "v4"
MANIFEST_NAMES = ["bapipe_datafiles.csv", "datafiles.csv"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def find_manifest(folder):
    """Return the first known manifest CSV inside ``folder`` (or None)."""
    for name in MANIFEST_NAMES:
        if (folder / name).exists():
            return folder / name
    return None


def _cfg_sig():
    c = st.session_state.get("config")
    return None if c is None else (c.box_shape, c.use_box_reference, c.remove_lens_distortion)


def frame_cached(video, idx, raw=False):
    """Read a video frame once and memoise it for the session, so the many reruns
    triggered by clicks/sliders don't re-open the video file every time (the main
    source of UI lag). Keyed by (id, idx, raw, config)."""
    cache = st.session_state.setdefault("_frame_cache", {})
    key = (video.id, int(idx), raw, _cfg_sig())
    if key not in cache:
        if raw:
            cache[key] = video.get_frame(
                idx, override_config={"use_box_reference": False, "remove_lens_distortion": False}
            ).astype(np.uint8)
        else:
            cache[key] = video.get_frame(idx)
    return cache[key]


def reference_frame(video):
    """A representative frame for overlays, safe for short videos."""
    idx = min(900, max(0, video.frame_count - 1))
    return frame_cached(video, idx, raw=False)


def load_metadata(path, join_col):
    df = pd.read_csv(path)
    if join_col in df.columns:
        df = df.set_index(join_col)
    return df


def metric_by_group(video_set, metric_series, metadata, group_col):
    """Join a per-animal metric with metadata for grouped plotting."""
    df = metric_series.to_frame()
    if metadata is not None and group_col and group_col in metadata.columns:
        df = df.join(metadata[[group_col]])
    return df


# --------------------------------------------------------------------------- #
# Data folder resolution
# --------------------------------------------------------------------------- #
# Data settings live on the main setup screen (widgets rendered there). Resolve their
# values here every run; setdefault keeps the widget keys alive so they persist even on
# dashboard runs where the widgets aren't rendered.
st.session_state.setdefault("data_folder_input", str(DEFAULT_FOLDER) if DEFAULT_FOLDER.is_dir() else "")
data_folder = st.session_state["data_folder_input"]

manifest_path, root_dir, manifest_df, data_status = None, "", None, None
folder = Path(data_folder) if data_folder else None
if folder and folder.is_dir():
    root_dir = str(folder)
    manifest_path = find_manifest(folder)
    if manifest_path is not None:
        manifest_df = pd.read_csv(manifest_path)
        if "id" not in manifest_df.columns:
            manifest_df = manifest_df.rename(columns={manifest_df.columns[0]: "id"})
        data_status = ("success", f"{manifest_path.name} · {len(manifest_df)} animals")
    else:
        data_status = ("error", "No bapipe_datafiles.csv / datafiles.csv in this folder.")
elif data_folder:
    data_status = ("error", "Folder not found.")

_meta_default = (str(folder / "experiment-data.csv")
                 if folder and folder.is_dir() and (folder / "experiment-data.csv").exists() else "")
st.session_state.setdefault("meta_input", _meta_default)
meta_path = st.session_state["meta_input"]
st.session_state.setdefault("join_input", "id")
join_col = st.session_state["join_input"] or "id"

# Is a camera-calibration file actually available for these videos?
cal_present = False
if manifest_df is not None:
    try:
        cal_rel = str(manifest_df.iloc[0].get("camera_calibrations", "camera_calibrations.json"))
        cal_present = (Path(root_dir) / cal_rel).exists()
    except Exception:
        cal_present = False

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


def do_load(selected_ids):
    """Load only the selected animals into session_state."""
    df = manifest_df[manifest_df["id"].astype(str).isin(selected_ids)].reset_index(drop=True)
    config = bapipe.AnalysisConfig(
        pcutoff=pcutoff,
        outlier_sigmas=outlier_sigmas,
        outlier_minimum_bodyparts=int(min_bodyparts),
        outlier_use_pairwise_distance=use_pairwise,
        outlier_use_bodypart_distance=use_bodypart,
        outlier_use_centroid_distance=use_centroid,
        outlier_use_likelhiood=use_likelihood,  # (sic) matches source field
        outlier_use_minimum_bodyparts=use_min_bodyparts,
        mouse_in_box_tolerance=int(mouse_in_box_tolerance),
        remove_lens_distortion=remove_lens,
        use_box_reference=use_box_reference,
        box_shape=(int(box_w), int(box_h)),
    )
    with st.spinner(f"Loading {len(df)} videos…"):
        # Single-process on purpose: mp.Pool is fragile under Streamlit reruns.
        video_set = bapipe.VideoSet.load(
            df, config, root_dir=root_dir, use_multiprocessing=False
        )
    st.session_state["video_set"] = video_set
    st.session_state["config"] = config
    st.session_state["manifest_df"] = manifest_df.reset_index(drop=True)
    st.session_state["root_dir"] = root_dir
    st.session_state["meta_path"] = meta_path
    st.session_state["join_col"] = join_col
    st.session_state.pop("_frame_cache", None)  # frames may differ under the new config
    st.session_state["metadata"] = (
        load_metadata(meta_path, join_col)
        if meta_path and Path(meta_path).exists() else None
    )


# --------------------------------------------------------------------------- #
# Main area — top header bar + card home (MGS-style)
# --------------------------------------------------------------------------- #
SECTIONS = [
    ("Overview", "Experiment summary and the original-vs-aligned video montage."),
    ("Distance", "Total distance travelled, grouped by treatment."),
    ("Heatmaps", "Occupancy density heatmaps, per group."),
    ("Time in zone", "Time spent in an adjustable centred zone, per group."),
    ("Validation video", "Annotated clip with the tracked keypoints drawn on the mouse."),
    ("Results", "Per-animal metrics + group summary; export tidy CSVs."),
]


def render_header():
    email, name = auth.current_user()
    who = name or email
    h1, h2, h3 = st.columns([1, 6, 3], vertical_alignment="center")
    with h1:
        if LOGO_PATH and LOGO_PATH.suffix == ".svg":
            st.image(LOGO_PATH.read_text(), width=46)
        elif LOGO_PATH:
            st.image(str(LOGO_PATH), width=46)
    h2.markdown("**Dashboard**")
    if who:
        initial = (who[:1] or "?").upper()
        h3.markdown(
            "<div style='text-align:right'>"
            "<span style='display:inline-block;width:26px;height:26px;line-height:26px;"
            f"border-radius:50%;background:#111;color:#fff;text-align:center;margin-right:6px'>{initial}</span>"
            f"{who}</div>", unsafe_allow_html=True)
    st.divider()


def render_home():
    st.title("Behavioural Analysis Dashboard")
    st.write("Pick a section to explore your loaded experiment, or use the analysis "
             "settings above to change what's loaded.")
    cols = st.columns(3)
    for i, (name, desc) in enumerate(SECTIONS):
        with cols[i % 3].container(border=True):
            st.markdown(f"#### {name}")
            st.caption(desc)
            if st.button("Open →", key=f"home_{name}", use_container_width=True):
                st.session_state["view"] = name
                st.rerun()


# --------------------------------------------------------------------------- #
# Phase router — Welcome / Guide / Wizard / Loading / My Records / App
# --------------------------------------------------------------------------- #
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


def _autodetect_box(silent=False):
    """Estimate arena (width, height) from the first manifest row's labelled
    landmark corners, writing box_w/box_h into session_state. Best-effort:
    on any failure, keeps whatever box_w/box_h are already set (the 400x300
    default from the defaults block) and — unless ``silent`` — surfaces the
    error so a user pressing "Re-detect" gets feedback."""
    try:
        row = manifest_df.iloc[0]
        landmark_path = Path(root_dir) / row["landmark_labels"]
        w, h = analysis.detect_box_shape_from_landmarks(landmark_path, pcutoff=st.session_state["pcutoff"])
        st.session_state["box_w"] = int(w)
        st.session_state["box_h"] = int(h)
        if not silent:
            st.success(f"Detected arena size: {w} × {h}.")
        return True
    except Exception as e:
        if not silent:
            st.error(f"Could not auto-detect arena size: {e}")
        return False


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
        if manifest_df is not None:
            _autobox_key = str(manifest_path)
            if st.session_state.get("_wizard_autobox_for") != _autobox_key:
                st.session_state["_wizard_autobox_for"] = _autobox_key
                _autodetect_box(silent=True)
        # The re-detect button must run (and update box_w/box_h in session_state)
        # BEFORE the number_input widgets below are instantiated — Streamlit
        # forbids mutating a widget-bound session_state key after that widget
        # has been created in the same run.
        if st.button("Re-detect from arena corners", disabled=manifest_df is None):
            _autodetect_box(silent=False)
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
    render_wizard()
    st.stop()
elif phase == "loading":
    st.info("Loading — implemented in Task 8.")
    st.stop()
elif phase == "records":
    st.info("My Records dashboard — implemented in Task 9.")
    if st.button("Start →"):
        go("wizard")
    st.stop()
# phase == "app": analysis views (wired in Task 8) — fall through to the
# existing setup screen + view dispatch below.


render_header()

# ---- Setup screen: choose data, then pick animals ------------------------- #
_loaded = "video_set" in st.session_state

# Data inputs live in an expander that is ALWAYS rendered (so its widget state is never
# garbage-collected on dashboard runs). Expanded on the setup screen, collapsed once loaded.
with st.expander("① Data folder & metadata", expanded=not _loaded):
    st.caption(
        "Point the app at the folder with your **manifest CSV** (`bapipe_datafiles.csv` / "
        "`datafiles.csv`), videos and DeepLabCut `.h5` files. Optionally add a **metadata CSV** "
        "(`id` + group columns like treatment / sex / cohort) to compare groups."
    )
    st.text_input(
        "Data folder", key="data_folder_input",
        help="Folder containing the manifest CSV plus the videos/, mouse_labels/, "
             "landmark_labels/ it references.")
    if data_status:
        (st.success if data_status[0] == "success" else st.error)(data_status[1])
    dc1, dc2 = st.columns(2)
    dc1.text_input(
        "Metadata CSV (optional, for grouping)", key="meta_input",
        help="Per-animal metadata joined by id, e.g. treatment / sex / cohort.")
    dc2.text_input(
        "Metadata join column", key="join_input",
        help="Column in the metadata CSV that matches the manifest id (usually 'id').")

# ---- Setup screen: pick which animals to load ----------------------------- #
if not _loaded:
    if manifest_df is None:
        st.stop()  # wait for a valid data folder before showing the animal picker

    st.markdown("### ② Select animals to load")
    ids = manifest_df["id"].astype(str).tolist()

    picker_key = f"picker::{manifest_path}"
    if st.session_state.get("picker_key") != picker_key:
        st.session_state["picker_key"] = picker_key
        st.session_state["picker_df"] = pd.DataFrame(
            {"id": ids, "load": [i < 8 for i in range(len(ids))]}
        )

    # Select all / Clear rewrite the source frame (these buttons rerun, but the
    # rerun happens before the editor renders, so the page stays put).
    c1, c2, _ = st.columns([1, 1, 6])
    if c1.button("Select all"):
        st.session_state["picker_df"]["load"] = True
    if c2.button("Clear"):
        st.session_state["picker_df"]["load"] = False

    # The editor lives inside a form: ticking checkboxes no longer triggers a
    # rerun (which would scroll the page back to the top). Nothing is submitted
    # until you press "Load experiment".
    with st.form("animal_picker", border=False):
        edited = st.data_editor(
            st.session_state["picker_df"],
            hide_index=True,
            disabled=["id"],
            width="stretch",
            height=360,
            column_config={
                "id": st.column_config.TextColumn("Animal"),
                "load": st.column_config.CheckboxColumn("Load", default=False),
            },
        )
        submitted = st.form_submit_button("Load experiment", type="primary")

    st.caption(f"{len(ids)} animals available. Tick the ones to load, then press Load experiment.")

    if submitted:
        st.session_state["picker_df"] = edited
        selected_ids = edited.loc[edited["load"], "id"].tolist()
        if not selected_ids:
            st.warning("Select at least one animal to load.")
        else:
            try:
                do_load(selected_ids)
                st.rerun()
            except Exception as e:
                st.session_state.pop("video_set", None)
                st.error(f"Failed to load: {e}")
                st.exception(e)
    st.stop()

video_set = st.session_state["video_set"]
config = st.session_state["config"]
metadata = st.session_state["metadata"]
box_shape = config.box_shape

# Only categorical "group" columns (treatment/sex/cohort/…) are useful for grouping and
# for merging into results — drop the numeric hand-scored metrics and boolean flags.
def group_like_columns(md):
    return [c for c in md.columns
            if not (pd.api.types.is_float_dtype(md[c]) or pd.api.types.is_bool_dtype(md[c]))]


group_cols = group_like_columns(metadata) if metadata is not None else []

# All animals available in the manifest (not just the initially loaded ones).
manifest_all = st.session_state.get("manifest_df")
all_ids = list(manifest_all["id"].astype(str)) if manifest_all is not None else list(video_set.index)
loaded_ids = list(video_set.index)


def group_selector(key):
    if not group_cols:
        st.caption("No metadata loaded — showing all animals together.")
        return None
    default = "injected_with" if "injected_with" in group_cols else group_cols[0]
    return st.selectbox("Group by", group_cols, index=group_cols.index(default), key=key,
                        help="Metadata column used to split animals into groups for comparison "
                             "(e.g. treatment, sex, cohort).")


def ensure_loaded(ids):
    """Lazily load any selected animals that weren't loaded yet."""
    vs = st.session_state["video_set"]
    missing = [i for i in ids if i not in set(vs.index)]
    if not missing:
        return
    mdf = st.session_state["manifest_df"]
    rows = mdf[mdf["id"].astype(str).isin(missing)].reset_index(drop=True)
    if len(rows):
        with st.spinner(f"Loading {len(rows)} more video(s)…"):
            extra = bapipe.VideoSet.load(
                rows, st.session_state["config"],
                root_dir=st.session_state["root_dir"], use_multiprocessing=False,
            )
        vs.videos.extend(extra.videos)


def animal_selector(key):
    """Per-tab select / deselect of animals. Options include the WHOLE manifest;
    picking an animal that wasn't loaded yet loads it on demand."""
    with st.expander("Animals (select / deselect)", expanded=False):
        c1, c2 = st.columns(2)
        if c1.button("All", key=f"{key}_all"):
            st.session_state[key] = list(all_ids)
        if c2.button("None", key=f"{key}_none"):
            st.session_state[key] = []
        st.session_state.setdefault(key, list(loaded_ids))
        sel = st.multiselect("Included animals", all_ids, key=key)
    if not sel:
        st.warning("No animals selected — using the initially loaded set.")
        sel = list(loaded_ids)
    ensure_loaded(sel)
    return sel


def videos_for(ids):
    vs = st.session_state["video_set"]
    return [vs[vs.index.index(i)] for i in ids]


def fig_export(fig, basename, key):
    """Format picker + download button for a matplotlib figure (png/pdf/jpeg)."""
    mimes = {"png": "image/png", "pdf": "application/pdf", "jpeg": "image/jpeg"}
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    fmt = c1.selectbox("Export format", list(mimes), key=f"{key}_fmt",
                       help="File type for the downloaded figure. PNG/JPEG = image, PDF = vector.")
    buf = io.BytesIO()
    fig.savefig(buf, format="jpg" if fmt == "jpeg" else fmt,
                bbox_inches="tight", dpi=200, facecolor="white")
    c2.download_button(f"Download figure (.{fmt})", buf.getvalue(),
                       file_name=f"{basename}.{fmt}", mime=mimes[fmt], key=f"{key}_dl")


# Navigation is card-based (Home) instead of tabs: only the selected section's code runs,
# which also keeps interactions snappy.
view = st.session_state.setdefault("view", "Home")
if view != "Home":
    if st.button("← Home"):
        st.session_state["view"] = "Home"
        st.rerun()

# ---- Home (section cards) ------------------------------------------------- #
if view == "Home":
    render_home()

# ---- Overview ------------------------------------------------------------- #
elif view == "Overview":
    st.subheader("Experiment summary")
    sel = animal_selector("ov_animals")
    vids = videos_for(sel)

    sizes = {(v.frame_width, v.frame_height) for v in vids}
    durations = [v.duration for v in vids]
    desc = pd.DataFrame(
        [
            ["Number of videos", len(vids)],
            ["Video sizes (W,H)", ", ".join(f"{w}x{h}" for w, h in sizes)],
            ["Total duration [s]", round(float(np.sum(durations)), 1)],
            ["Average duration [s]", round(float(np.mean(durations)), 2) if durations else 0],
        ],
        columns=["Metric", "Value"],
    )
    desc["Value"] = desc["Value"].astype(str)  # mixed types -> str for Arrow
    st.table(desc)

    st.subheader("Original vs. aligned montage")
    st.caption("Reads one frame per selected video — may take a moment.")
    if st.button("Build montage",
                 help="Render a grid of one frame per selected video, before vs. after alignment."):
        with loading("loading"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Original**")
                orig = bapipe.create_video_grid(
                    vids,
                    override_config={"use_box_reference": False, "remove_lens_distortion": False},
                )
                st.image(np.clip(orig, 0, 1))
            with col2:
                st.markdown("**Aligned**")
                aligned = bapipe.create_video_grid(vids)
                st.image(np.clip(aligned, 0, 1))

# ---- Distance ------------------------------------------------------------- #
elif view == "Distance":
    st.subheader("Total distance travelled")
    sel = animal_selector("dist_animals")
    group_col = group_selector("dist_group")
    bar_color = st.color_picker("Bar colour", "#4C72B0", key="dist_color",
                                help="Colour of the bars in the chart.")

    with loading("loading"):
        distances = pd.Series(
            [analysis.distance_travelled(v) for v in videos_for(sel)],
            index=sel, name="distance",
        )
    data = metric_by_group(video_set, distances, metadata, group_col)

    # Graph on the left, the actual distance table on the right.
    col_fig, col_tbl = st.columns([2, 1])
    with col_fig:
        fig, ax = plt.subplots(figsize=(8, 5))
        if group_col:
            sns.barplot(data=data, x=group_col, y="distance", ax=ax, color=bar_color)
            ax.set_xlabel("Group")
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        else:
            sns.barplot(data=data.reset_index(), x="index", y="distance", ax=ax, color=bar_color)
            ax.set_xlabel("Animal")
        ax.set_ylabel("Distance travelled")
        ax.set_title("Locomotion")
        st.pyplot(fig)
        fig_export(fig, "distance", "dist")
    with col_tbl:
        st.markdown("**Distances**")
        st.dataframe(data, height=380)
        st.download_button("Download CSV", data.to_csv().encode(), "distances.csv",
                           "text/csv", key="dist_csv")

# ---- Heatmaps ------------------------------------------------------------- #
elif view == "Heatmaps":
    st.subheader("Occupancy heatmaps")
    sel = animal_selector("heat_animals")
    group_col = group_selector("heat_group")
    levels = st.slider("Contour levels", 5, 40, 20,
                       help="Number of shading bands in the density contour. More = smoother gradient.")
    downsample = st.slider(
        "Downsample (1 frame every N)", 10, 500, 100, step=10,
        help="Use every Nth frame's position when estimating the density. Higher = faster / coarser "
             "sampling; lower = denser / slower. Consecutive frames are nearly identical, so the "
             "shape barely changes.")
    intensity = st.slider("Colour intensity", 0.1, 1.0, 0.45, 0.05,
                          help="Lower = lighter overlay so the arena stays visible.")

    # Background is automatic: for "Arena frame" each group panel uses a representative
    # frame from that group's own first animal; "White" uses a plain canvas.
    bg_mode = st.radio("Background", ["Arena frame", "White"], horizontal=True, key="heat_bg",
                       help="Image behind the density. 'Arena frame' auto-picks a representative "
                            "frame from each group; 'White' shows the distribution alone.")

    def group_background(ids):
        if bg_mode == "White":
            bw, bh = int(box_shape[0]), int(box_shape[1])
            return np.ones((bh, bw, 3))
        return reference_frame(videos_for(ids)[0])  # representative frame of the group's 1st animal

    sel_set = set(sel)
    if group_col:
        items = []
        for name, grp in metadata.groupby(group_col):
            ids = [x for x in grp.index if x in sel_set]
            if ids:
                items.append((name, ids))
    else:
        items = [("all animals", list(sel))]

    if not items:
        st.info("No selected animals match the metadata groups.")
    elif st.button("Compute heatmaps",
                   help="Estimate and draw the occupancy density for each group (can take a moment)."):
        cols = st.columns(min(len(items), 3) or 1)
        with loading("loading"):
            for i, (name, ids) in enumerate(items):
                z = analysis.occupancy_kde(videos_for(ids), box_shape, downsample=downsample)
                with cols[i % len(cols)]:
                    st.markdown(f"**{name}**")
                    fig, ax = plt.subplots()
                    ax.imshow(group_background(ids))
                    if z is not None:
                        cs = ax.contourf(z, cmap="Reds", alpha=intensity, levels=levels)
                        cbar = fig.colorbar(cs, ax=ax, fraction=0.046, pad=0.04)
                        cbar.set_label("Occupancy density\n(darker red = more time spent)")
                    ax.axis("off")
                    st.pyplot(fig)
                    fig_export(fig, f"heatmap_{name}".replace("/", "-"), f"heat_{i}")

# ---- Time in zone --------------------------------------------------------- #
elif view == "Time in zone":
    st.subheader("Time spent in a centred zone")
    sel = animal_selector("zone_animals")
    group_col = group_selector("zone_group")
    bar_color = st.color_picker("Bar colour", "#4C72B0", key="zone_color",
                                help="Colour of the bars in the chart.")

    # The displayed reference frame and each video's mouse_df live in the SAME
    # coordinate space (both had the same config transform applied). So centre the
    # zone on the frame's own dimensions — this is correct whether or not videos
    # are box-aligned, and guarantees the drawn box matches what's measured.
    ref = reference_frame(video_set[0])
    fh, fw = ref.shape[:2]
    half = st.slider("Zone half-size", 10, int(min(fw, fh) // 2),
                     min(50, int(min(fw, fh) // 2)), key="zone_half",
                     help="Half the side length of the square zone (in frame pixels). "
                          "Larger = bigger zone.")
    # The square is centred on the frame by default; nudge it to the arena's real
    # centre (e.g. the food port) if the camera isn't perfectly centred.
    dx = st.slider("Centre X offset", -fw // 2, fw // 2, 0, key="zone_dx",
                   help="Shift the zone left/right from the frame centre (pixels).")
    dy = st.slider("Centre Y offset", -fh // 2, fh // 2, 0, key="zone_dy",
                   help="Shift the zone up/down from the frame centre (pixels).")
    cx, cy = fw / 2 + dx, fh / 2 + dy
    zone = analysis.square_zone(cx, cy, half)

    col_a, col_b = st.columns([1, 1.4])
    with col_a:
        st.markdown("**Zone**")
        fig_zone, ax = plt.subplots()
        ax.imshow(ref)
        disp = analysis.square_zone(cx, cy, half)  # separate patch for drawing
        disp.set(facecolor="none", edgecolor="red", linewidth=2, alpha=1.0)
        ax.add_patch(disp)
        ax.plot(cx, cy, "r+", markersize=10)  # mark the zone centre
        ax.set_xlim(0, fw)
        ax.set_ylim(fh, 0)
        ax.axis("off")
        st.pyplot(fig_zone)
        fig_export(fig_zone, "zone", "zone_img")

    with loading("loading"):
        times = pd.Series(
            [analysis.time_in_zone(v, zone) for v in videos_for(sel)],
            index=sel, name="time_in_zone",
        )
    data = metric_by_group(video_set, times, metadata, group_col)
    with col_b:
        st.markdown("**Time in zone [s]**")
        fig, ax = plt.subplots(figsize=(7, 5))
        if group_col:
            sns.barplot(data=data, x=group_col, y="time_in_zone", ax=ax, color=bar_color)
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        else:
            sns.barplot(data=data.reset_index(), x="index", y="time_in_zone", ax=ax, color=bar_color)
        ax.set_ylabel("Time in zone [s]")
        st.pyplot(fig)
        fig_export(fig, "time_in_zone", "zone_bar")
    st.dataframe(data)
    st.download_button("Download CSV", data.to_csv().encode(), "time_in_zone.csv",
                       "text/csv", key="zone_csv")

# ---- Validation video ----------------------------------------------------- #
elif view == "Validation video":
    st.subheader("Annotated validation clip")
    sel = animal_selector("vid_animals")
    animal = st.selectbox("Animal", sel, help="Which animal's video to annotate.")
    video = video_set[video_set.index.index(animal)]
    max_start = max(0, video.frame_count - 2)
    start = st.number_input("Start frame", value=min(1000, max_start), min_value=0, max_value=max_start,
                            help="Frame the clip starts from.")
    length = st.slider("Number of frames", 20, 300, 100,
                       help="How many frames to render (at video fps).")

    if st.button("Generate clip", help="Render a short clip with the tracked keypoints drawn on the mouse."):
        out = Path(tempfile.mkdtemp()) / f"{animal}_annotated.mp4"
        with loading("loading"):
            try:
                analysis.annotate_clip(video, int(start), int(length), out)
                st.video(str(out))
            except Exception as e:
                st.error(f"Failed to render clip: {e}")
                st.exception(e)

# ---- Results -------------------------------------------------------------- #
elif view == "Results":
    st.subheader("Results — computed metrics by group")
    st.caption(
        "Per-animal metrics computed live from the pose data, merged with your metadata "
        "groups. Metadata only needs id + group columns (treatment/sex/cohort); the numbers "
        "here are produced by the app, not read from the metadata."
    )
    sel = animal_selector("results_animals")
    vids = videos_for(sel)

    # Reuse the zone configured in the Time-in-zone view (or a centred default).
    ref = reference_frame(video_set[0])
    fh, fw = ref.shape[:2]
    half = int(st.session_state.get("zone_half", min(50, int(min(fw, fh) // 2))))
    half = max(10, min(half, int(min(fw, fh) // 2)))
    cx = fw / 2 + int(st.session_state.get("zone_dx", 0))
    cy = fh / 2 + int(st.session_state.get("zone_dy", 0))
    zone = analysis.square_zone(cx, cy, half)

    with loading("loading"):
        results = pd.DataFrame(
            {
                "distance": [analysis.distance_travelled(v) for v in vids],
                "time_in_zone": [analysis.time_in_zone(v, zone) for v in vids],
                "duration_s": [round(v.duration, 2) for v in vids],
            },
            index=pd.Index(sel, name="id"),
        )
    metric_cols = list(results.columns)
    if metadata is not None and group_cols:
        results = results.join(metadata[group_cols])  # only categorical group columns

    st.markdown("**Per-animal results**")
    st.dataframe(results)
    st.download_button("Download per-animal CSV", results.to_csv().encode(),
                       "results_per_animal.csv", "text/csv", key="results_csv")

    st.markdown("**Group summary (mean ± SEM)**")
    if group_cols:
        default_g = "injected_with" if "injected_with" in group_cols else group_cols[0]
        gcol = st.selectbox("Summarise by", group_cols, index=group_cols.index(default_g),
                            key="results_group",
                            help="Group column to aggregate the metrics by (mean ± SEM per group).")
        summary = results.groupby(gcol)[metric_cols].agg(["mean", "sem", "count"]).round(3)
        st.dataframe(summary)
        st.download_button("Download group-summary CSV", summary.to_csv().encode(),
                           "results_group_summary.csv", "text/csv", key="results_summary_csv")
    else:
        st.info(
            "No metadata groups loaded — showing the per-animal table only. Add a metadata "
            "CSV with id + a group column (treatment / sex / cohort) to summarise by group."
        )
