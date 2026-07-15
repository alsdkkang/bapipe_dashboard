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


def group_like_columns(md):
    """Only categorical "group" columns (treatment/sex/cohort/…) are useful for
    grouping and for merging into results — drop the numeric hand-scored metrics
    and boolean flags."""
    return [c for c in md.columns
            if not (pd.api.types.is_float_dtype(md[c]) or pd.api.types.is_bool_dtype(md[c]))]


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


def autosave_current_load(sel_ids):
    """After a successful load, compute per-animal metrics + group summary and
    save a results-only snapshot to the current user's private records. Only
    numbers + metadata are saved — never video/frame data."""
    vs = st.session_state["video_set"]
    cfg = st.session_state["config"]
    md = st.session_state.get("metadata")
    present = set(vs.index)
    ids_present = [i for i in sel_ids if i in present]
    vids = [vs[vs.index.index(i)] for i in ids_present]
    ref = reference_frame(vs[0]); fh, fw = ref.shape[:2]
    half = max(10, min(int(min(fw, fh) // 2), 50))
    zone = analysis.square_zone(fw / 2, fh / 2, half)
    per = pd.DataFrame(
        {"distance": [analysis.distance_travelled(v) for v in vids],
         "time_in_zone": [analysis.time_in_zone(v, zone) for v in vids],
         "duration_s": [round(v.duration, 2) for v in vids]},
        index=pd.Index(ids_present, name="id"),
    )
    gcols = group_like_columns(md) if md is not None else []
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
            f"style='background:{'#111' if i <= step else '#cccccc'}'>{mark}</span>"
            f"<div style='font-size:13px;font-weight:600;color:"
            f"{'#111' if i == step else '#777777'}'>{lab}</div></div>",
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


# ---- Overview ------------------------------------------------------------- #
def render_overview():
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
def render_distance():
    st.subheader("Total distance travelled")
    sel = animal_selector("dist_animals")
    group_col = group_selector("dist_group")

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
            greys = theme.group_greys(data[group_col].nunique())
            palette = [g[0] for g in greys]
            bars = sns.barplot(data=data, x=group_col, y="distance", ax=ax, palette=palette)
            for patch, (_, hatch) in zip(bars.patches, greys):
                if hatch:
                    patch.set_hatch(hatch)
            ax.set_xlabel("Group")
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        else:
            sns.barplot(data=data.reset_index(), x="index", y="distance", ax=ax, color="#444444")
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
def render_heatmaps():
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
                        cs = ax.contourf(z, cmap="Greys", alpha=intensity, levels=levels)
                        cbar = fig.colorbar(cs, ax=ax, fraction=0.046, pad=0.04)
                        cbar.set_label("Occupancy density\n(darker = more time spent)")
                    ax.axis("off")
                    st.pyplot(fig)
                    fig_export(fig, f"heatmap_{name}".replace("/", "-"), f"heat_{i}")


# ---- Time in zone --------------------------------------------------------- #
def render_zone():
    st.subheader("Time spent in a centred zone")
    sel = animal_selector("zone_animals")
    group_col = group_selector("zone_group")

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
        disp.set(facecolor="none", edgecolor="#111111", linewidth=2, alpha=1.0)
        ax.add_patch(disp)
        ax.plot(cx, cy, "+", color="#111111", markersize=10,
                markeredgewidth=2)  # mark the zone centre
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
            greys = theme.group_greys(data[group_col].nunique())
            palette = [g[0] for g in greys]
            bars = sns.barplot(data=data, x=group_col, y="time_in_zone", ax=ax, palette=palette)
            for patch, (_, hatch) in zip(bars.patches, greys):
                if hatch:
                    patch.set_hatch(hatch)
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        else:
            sns.barplot(data=data.reset_index(), x="index", y="time_in_zone", ax=ax, color="#444444")
        ax.set_ylabel("Time in zone [s]")
        st.pyplot(fig)
        fig_export(fig, "time_in_zone", "zone_bar")
    st.dataframe(data)
    st.download_button("Download CSV", data.to_csv().encode(), "time_in_zone.csv",
                       "text/csv", key="zone_csv")


# ---- Validation video ------------------------------------------------------ #
def render_validation():
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


# ---- Results ---------------------------------------------------------------- #
def render_results():
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
    render_loading()
    st.stop()
elif phase == "records":
    render_records()
    st.stop()
elif phase == "app":
    if "video_set" not in st.session_state:
        go("wizard")
    render_top_bar("Analysis", "Explore your loaded experiment")
    video_set = st.session_state["video_set"]
    config = st.session_state["config"]
    metadata = st.session_state["metadata"]
    box_shape = config.box_shape
    group_cols = group_like_columns(metadata) if metadata is not None else []
    # All animals available in the manifest (not just the initially loaded ones).
    manifest_all = st.session_state.get("manifest_df")
    all_ids = list(manifest_all["id"].astype(str)) if manifest_all is not None else list(video_set.index)
    loaded_ids = list(video_set.index)

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
    st.stop()
