"""User-friendly Streamlit dashboard for bapipe-keypoints.

Point it at a bapipe `datafiles.csv` manifest, set a few options, click
"Load experiment", then explore the analysis dashboards. No coding required.

Run with:
    streamlit run gui_app/app.py
"""
import io
import platform
import subprocess
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

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st

try:
    from streamlit_image_coordinates import streamlit_image_coordinates as _click_image
except Exception:  # component not installed → arena-corner picker disabled
    _click_image = None

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


def _metadata_columns(path):
    """Column names of a metadata CSV (header only), or [] if unreadable."""
    if not path or not Path(path).exists():
        return []
    try:
        return list(pd.read_csv(path, nrows=0).columns)
    except Exception:
        return []


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


def _native_pick(mode):
    """Open a native macOS folder/file chooser and return a POSIX path (or None).
    LOCAL runs only — on a deployed/headless server there is no desktop to show a
    dialog on, so this returns None and the user types the path instead.
    mode: 'folder' | 'csv'."""
    if platform.system() != "Darwin":
        return None
    if mode == "folder":
        script = 'POSIX path of (choose folder with prompt "Select data folder")'
    elif mode == "json":
        script = ('POSIX path of (choose file with prompt "Select calibration JSON" '
                  'of type {"json", "public.json"})')
    else:
        script = ('POSIX path of (choose file with prompt "Select CSV file" '
                  'of type {"csv", "public.comma-separated-values-text"})')
    try:
        out = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=180)
        return out.stdout.strip() or None
    except Exception:
        return None


def _pick_data_folder():
    p = _native_pick("folder")
    if p:
        st.session_state["data_folder_input"] = p.rstrip("/")


def _pick_meta_csv():
    p = _native_pick("csv")
    if p:
        st.session_state["w_meta"] = st.session_state["data_meta_path"] = p


def _pick_video_dir():
    p = _native_pick("folder")
    if p:
        st.session_state["w_video"] = st.session_state["data_video_dir"] = p.rstrip("/")


def _pick_dlc_dir():
    p = _native_pick("folder")
    if p:
        st.session_state["w_dlc"] = st.session_state["data_dlc_dir"] = p.rstrip("/")


def _pick_landmark_dir():
    p = _native_pick("folder")
    if p:
        st.session_state["w_land"] = st.session_state["data_landmark_dir"] = p.rstrip("/")


def _pick_calib_file():
    p = _native_pick("json")
    if p:
        st.session_state["w_calib"] = st.session_state["data_calib_path"] = p


_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}


def _dlc_animal_id(h5_name):
    """Animal id encoded in a DeepLabCut output filename (`<id>DLC_...h5`)."""
    return h5_name.split("DLC")[0] if "DLC" in h5_name else Path(h5_name).stem


def _find_landmark(land_dir, vid):
    """A landmark .h5 for this video id in land_dir (accepts a few name styles)."""
    if not land_dir:
        return None
    for cand in (land_dir / f"{vid}_landmarks.h5", land_dir / f"{vid}.h5"):
        if cand.exists():
            return cand
    return next((p for p in land_dir.glob(f"{vid}*.h5")), None)


def build_manifest_from_folders(video_dir, dlc_dir, landmark_dir=""):
    """Pair each video with its DeepLabCut .h5 by name and build an in-memory
    manifest with ABSOLUTE paths (so bapipe's root_dir join is a no-op). If a
    landmark folder is given (or <video_dir>/landmark_labels exists), each video's
    arena-corner .h5 is wired in so alignment uses those instead of drawn corners."""
    vdir, ddir = Path(video_dir), Path(dlc_dir)
    videos = sorted(p for p in vdir.iterdir()
                    if p.is_file() and p.suffix.lower() in _VIDEO_EXTS)
    h5s = [p for p in ddir.iterdir() if p.is_file() and p.suffix.lower() == ".h5"]
    dlc_by_id = {}
    for h in h5s:
        dlc_by_id.setdefault(_dlc_animal_id(h.name), h)
    land_dir = (Path(landmark_dir) if landmark_dir and Path(landmark_dir).is_dir()
                else vdir / "landmark_labels")
    if not land_dir.is_dir():
        land_dir = None
    rows, unmatched = [], []
    for v in videos:
        vid = v.stem
        h = dlc_by_id.get(vid) or next(
            (hh for hh in h5s if hh.name.startswith(vid)), None)
        if h is None:
            unmatched.append(vid)
            continue
        row = {"id": vid, "video": str(v), "mouse_labels": str(h)}
        lm = _find_landmark(land_dir, vid)
        if lm:
            row["landmark_labels"] = str(lm)
        rows.append(row)
    if not rows:
        return None, ("error", "No videos in that folder matched a DLC .h5 file.")
    df = pd.DataFrame(rows)
    msg = f"{len(df)} video(s) matched to DLC files"
    if unmatched:
        msg += f" · {len(unmatched)} without a match (skipped)"
    # Guard against picking the landmark_labels folder (or any non-pose h5) by
    # mistake — otherwise the "pose" is just arena corners and every analysis
    # comes out empty. Definitive check: peek at the matched file's bodyparts.
    matched = [Path(r["mouse_labels"]) for r in rows]
    try:
        bps = {c[1] for c in pd.read_hdf(matched[0], stop=1).columns}
    except Exception:
        bps = set()
    if bps and bps <= {"top_left", "top_right", "bottom_right", "bottom_left"}:
        return None, ("error", "That folder holds arena LANDMARK files (corners), not "
                      "mouse pose. Choose the DeepLabCut keypoints folder instead — the "
                      "one with the pose .h5 files (e.g. 'mouse_labels', names like "
                      "f1DLC_resnet50_…). 'landmark_labels' is the arena corners.")
    if not any("DLC" in m.name for m in matched):
        return df, ("warn", f"{len(df)} matched, but these .h5 files don't look like "
                    "DeepLabCut pose output (no 'DLC' in their names). Make sure this is "
                    "the mouse keypoints folder, not the arena landmarks.")
    return df, ("success", msg)


# --------------------------------------------------------------------------- #
# Arena corners → landmark generation (for users without landmark .h5 files)
# --------------------------------------------------------------------------- #
_ARENA_CORNERS = ["top_left", "top_right", "bottom_right", "bottom_left"]
_ARENA_LABELS = ["top-left", "top-right", "bottom-right", "bottom-left"]


def _video_path_for(root_dir, mdf, animal_id):
    row = mdf[mdf["id"].astype(str) == str(animal_id)].iloc[0]
    return Path(root_dir) / str(row["video"])


def _read_raw_frame(video_path, idx=900):
    """Return a representative RGB frame (uint8) from a video, or None."""
    try:
        cap = cv2.VideoCapture(str(video_path))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(idx, max(0, n - 1)))
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        cap.release()
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if ok else None
    except Exception:
        return None


def _draw_corners(frame, corners):
    img = frame.copy()
    for i, (x, y) in enumerate(corners):
        cv2.circle(img, (int(x), int(y)), 8, (17, 17, 17), -1)
        cv2.circle(img, (int(x), int(y)), 8, (255, 255, 255), 2)
        cv2.putText(img, str(i + 1), (int(x) + 11, int(y) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (17, 17, 17), 2, cv2.LINE_AA)
    return img


def _landmarks_present(root_dir, mdf, sel_ids):
    """True only if every selected animal has an existing landmark_labels .h5."""
    if mdf is None or "landmark_labels" not in mdf.columns:
        return False
    rows = mdf[mdf["id"].astype(str).isin([str(i) for i in sel_ids])]
    if rows.empty:
        return False
    for _, r in rows.iterrows():
        lm = r.get("landmark_labels")
        if not isinstance(lm, str) or not lm or not (Path(root_dir) / lm).exists():
            return False
    return True


def _box_from_corners(corners):
    tl, tr, br, bl = [np.array(c, float) for c in corners]
    w = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    h = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    return max(1, int(round(w))), max(1, int(round(h)))


def _corners_key(corners):
    return tuple(tuple(int(v) for v in c) for c in corners)


def _detect_corners_by_color(frame, min_area=120):
    """Auto-detect the 4 arena corners from the coloured (teal/yellow) corner
    tape. Returns [TL, TR, BR, BL] in pixel coords, or None if it can't find a
    marker near every corner (e.g. a video whose corners aren't taped)."""
    if frame is None:
        return None
    h, w = frame.shape[:2]
    # frames from _read_raw_frame are RGB (for display), so convert from RGB.
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    teal = (H >= 76) & (H <= 100) & (S > 85) & (V > 55)
    yellow = (H >= 14) & (H <= 33) & (S > 85) & (V > 55)
    mask = (teal | yellow).astype(np.uint8) * 255
    # The food port sits near the centre — ignore the middle so it isn't picked.
    mask[int(h * 0.28):int(h * 0.72), int(w * 0.28):int(w * 0.72)] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a < min_area:
            continue
        m = cv2.moments(c)
        blobs.append((a, m["m10"] / m["m00"], m["m01"] / m["m00"]))
    if len(blobs) < 4:
        return None
    img_corners = [(0, 0), (w, 0), (w, h), (0, h)]  # TL, TR, BR, BL
    groups = {0: [], 1: [], 2: [], 3: []}
    for a, cx, cy in blobs:
        i = int(np.argmin([(cx - ix) ** 2 + (cy - iy) ** 2 for ix, iy in img_corners]))
        groups[i].append((a, cx, cy))
    out = []
    for i in range(4):
        if not groups[i]:
            return None
        tot = sum(a for a, _, _ in groups[i])
        out.append((sum(a * x for a, x, _ in groups[i]) / tot,
                    sum(a * y for a, _, y in groups[i]) / tot))
    tl, tr, br, bl = out
    if not (tl[0] < tr[0] and bl[0] < br[0] and tl[1] < bl[1] and tr[1] < br[1]):
        return None
    return out


def _frame_for_id(root_dir, mdf, aid):
    """Cached representative RGB frame for one animal's video."""
    fp = _video_path_for(root_dir, mdf, aid)
    key = f"_frame::{fp}"
    if key not in st.session_state:
        st.session_state[key] = _read_raw_frame(fp)
    return st.session_state[key]


def _make_landmark_h5(corners, n_frames, out_path):
    """Write a DeepLabCut-format landmark .h5 with constant arena corners."""
    cols = pd.MultiIndex.from_product(
        [["manual"], _ARENA_CORNERS, ["x", "y", "likelihood"]],
        names=["scorer", "bodyparts", "coords"])
    data = np.zeros((n_frames, len(_ARENA_CORNERS) * 3), dtype=float)
    for i, (cx, cy) in enumerate(corners):
        data[:, i * 3 + 0] = cx
        data[:, i * 3 + 1] = cy
        data[:, i * 3 + 2] = 1.0
    pd.DataFrame(data, columns=cols).to_hdf(out_path, key="df_with_missing", mode="w")


def _generate_landmarks(root_dir, mdf, sel_ids, corners_by_id):
    """Create per-animal landmark .h5 files (under <video_dir>/landmark_labels)
    from EACH video's own arena corners, and wire their absolute paths into the
    manifest. Video / mouse_labels paths are already absolute."""
    land_dir = Path(root_dir) / "landmark_labels"
    land_dir.mkdir(parents=True, exist_ok=True)
    sel = {str(i) for i in sel_ids}
    if "landmark_labels" not in mdf.columns:
        mdf["landmark_labels"] = ""
    for _, r in mdf.iterrows():
        rid = str(r["id"])
        if rid not in sel or rid not in corners_by_id:
            continue
        n = None
        ml = r.get("mouse_labels")
        try:
            if isinstance(ml, str) and Path(ml).exists():
                n = len(pd.read_hdf(ml))
        except Exception:
            n = None
        if not n:
            try:
                cap = cv2.VideoCapture(str(r["video"]))
                n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
            except Exception:
                n = 1000
        out = land_dir / f"{rid}_landmarks.h5"
        _make_landmark_h5(corners_by_id[rid], max(1, int(n)), out)
        mdf.loc[mdf["id"].astype(str) == rid, "landmark_labels"] = str(out)


def _autodetect_all_corners(root_dir, mdf, sel_ids):
    """Run colour-based corner detection on every selected video, storing results
    in session_state['corners_by_id']. Returns (n_detected, [failed ids])."""
    cbid = st.session_state.setdefault("corners_by_id", {})
    failed = []
    for aid in sel_ids:
        c = _detect_corners_by_color(_frame_for_id(root_dir, mdf, aid))
        if c:
            cbid[aid] = c
        elif aid not in cbid:
            failed.append(aid)
    return len(cbid), failed


def _fix_corner_ui(root_dir, mdf, aid):
    """Click the 4 corners for ONE video; store into corners_by_id[aid]."""
    if _click_image is None:
        st.error("Corner picker needs the `streamlit-image-coordinates` package.")
        return
    frame = _frame_for_id(root_dir, mdf, aid)
    if frame is None:
        st.error(f"Could not read a frame for {aid}.")
        return
    cbid = st.session_state.setdefault("corners_by_id", {})
    pending = st.session_state.setdefault("_fix_pending", {})
    corners = pending.get(aid, [])
    fh, fw = frame.shape[:2]
    disp_w = min(int(fw), 720)
    c1, c2 = st.columns([4, 1], vertical_alignment="top")
    with c1:
        val = _click_image(_draw_corners(frame, corners), width=disp_w, key=f"fix_click_{aid}")
    with c2:
        st.caption(f"Video **{aid}**")
        if st.button("Reset", key=f"fix_reset_{aid}"):
            pending[aid] = []
            st.session_state.pop(f"_fix_last_{aid}", None)
            st.rerun()
    if len(corners) < 4:
        st.info(f"Click the **{_ARENA_LABELS[len(corners)]}** corner ({len(corners) + 1} of 4).")
        if val and val.get("width") and val.get("height"):
            cur = (val["x"], val["y"])
            if st.session_state.get(f"_fix_last_{aid}") != cur:
                st.session_state[f"_fix_last_{aid}"] = cur
                corners.append((val["x"] * fw / val["width"], val["y"] * fh / val["height"]))
                pending[aid] = corners
                if len(corners) == 4:
                    cbid[aid] = corners
                st.rerun()


# --------------------------------------------------------------------------- #
# Data folder resolution
# --------------------------------------------------------------------------- #
# The data selection lives in CANONICAL (non-widget) session keys so it survives
# step changes and reruns. Streamlit can drop a widget-keyed value on a run where
# that widget isn't rendered (e.g. the folder inputs on step 0 are gone once you're
# on step 1/2), which previously blanked the manifest and stranded the wizard.
video_dir = st.session_state.get("data_video_dir", "")
dlc_dir = st.session_state.get("data_dlc_dir", "")
landmark_dir = st.session_state.get("data_landmark_dir", "")
calib_path = st.session_state.get("data_calib_path", "")
meta_path = st.session_state.get("data_meta_path", "")
join_col = st.session_state.get("data_join_col") or "id"

manifest_path, root_dir, manifest_df, data_status = None, "", None, None
if video_dir and Path(video_dir).is_dir():
    root_dir = video_dir
    if dlc_dir and Path(dlc_dir).is_dir():
        manifest_df, data_status = build_manifest_from_folders(video_dir, dlc_dir, landmark_dir)
    else:
        data_status = ("error", "Now choose the DLC keypoints (.h5) folder.")
elif video_dir:
    data_status = ("error", "Video folder not found.")

# Analysis settings live in the Start wizard. Resolve
# them from session defaults so do_load() keeps working.
_defaults = dict(box_w=400, box_h=300, use_box_reference=True, remove_lens=False,
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
    # Lens-distortion correction is applied automatically when a camera calibration
    # JSON is provided; every video points at that one calibration file. Without it,
    # correction is off and a placeholder keeps bapipe happy (it's never opened).
    _use_lens = bool(calib_path and Path(calib_path).exists())
    df["camera_calibrations"] = calib_path if _use_lens else "camera_calibrations.json"
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
        remove_lens_distortion=_use_lens,
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
    name = f"{len(ids_present)} animals · {pd.Timestamp.now():%Y-%m-%d %H:%M}"
    rec = records.assemble_record(name, ids_present, cfg_summary, per, summary)
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
    # If we somehow reached a later step without a valid data selection (e.g. the
    # app restarted and cleared the session), fall back to the data-picker step so
    # the user is never stranded with no way to proceed.
    if step > 0 and manifest_df is None:
        step = st.session_state["wizard_step"] = 0
        st.session_state["_wizard_bounced"] = True
    if st.button("← Back to records", key="wiz_home"):
        go("records")
    _stepper(step)
    st.divider()

    if step == 0:  # choose data
        if st.session_state.pop("_wizard_bounced", False):
            st.info("Please choose your Video and DLC folders to continue.")
        st.subheader("Where is your experiment?")
        # Widget keys are seeded from the canonical values and mirrored back after,
        # so the selection survives when these widgets aren't rendered on later steps.
        st.session_state.setdefault("w_video", video_dir)
        st.session_state.setdefault("w_dlc", dlc_dir)
        st.session_state.setdefault("w_land", landmark_dir)
        st.session_state.setdefault("w_calib", calib_path)
        st.session_state.setdefault("w_meta", meta_path)
        v1, v2 = st.columns([4, 1], vertical_alignment="bottom")
        v1.text_input("Video folder", key="w_video",
                      help="Folder containing your .mp4 videos (one per animal).")
        v2.button("Browse…", key="browse_video", on_click=_pick_video_dir,
                  use_container_width=True, help="Open a folder chooser (local use only).")
        h1, h2 = st.columns([4, 1], vertical_alignment="bottom")
        h1.text_input("DLC keypoints folder (.h5)", key="w_dlc",
                      help="Folder with the DeepLabCut .h5 output for each video "
                           "(matched to videos by filename).")
        h2.button("Browse…", key="browse_dlc", on_click=_pick_dlc_dir,
                  use_container_width=True, help="Open a folder chooser (local use only).")
        l1, l2 = st.columns([4, 1], vertical_alignment="bottom")
        l1.text_input("Landmark folder (.h5, optional)", key="w_land",
                      help="Folder with per-video arena-corner .h5 files "
                           "(<id>_landmarks.h5). If given, alignment uses these — more "
                           "accurate than auto-detecting corners. Leave blank to set "
                           "corners in the next steps.")
        l2.button("Browse…", key="browse_land", on_click=_pick_landmark_dir,
                  use_container_width=True, help="Open a folder chooser (local use only).")
        cb1, cb2 = st.columns([4, 1], vertical_alignment="bottom")
        cb1.text_input("Camera calibration (.json)", key="w_calib",
                       help="Camera calibration JSON (camera_matrix + distortion_"
                            "coefficients). When given, lens-distortion correction is "
                            "applied automatically to every video. Leave blank to skip.")
        cb2.button("Browse…", key="browse_calib", on_click=_pick_calib_file,
                   use_container_width=True, help="Open a file chooser (local use only).")
        st.session_state["data_video_dir"] = st.session_state["w_video"]
        st.session_state["data_dlc_dir"] = st.session_state["w_dlc"]
        st.session_state["data_landmark_dir"] = st.session_state["w_land"]
        st.session_state["data_calib_path"] = st.session_state["w_calib"]
        _cp = st.session_state["w_calib"]
        if _cp:
            _cok = Path(_cp).exists()
            st.caption(("✓ Lens-distortion correction will be applied." if _cok
                        else "⚠ Calibration file not found — lens correction will be skipped."))
        if data_status:
            _bg = {"success": "#e7f6ec", "warn": "#fff4e0"}.get(data_status[0], "#fdecec")
            _fg = {"success": "#1c6a2e", "warn": "#8a5a00"}.get(data_status[0], "#a11b1b")
            st.markdown(
                f"<span style='display:inline-block;background:{_bg};color:{_fg};"
                f"padding:6px 12px;border-radius:6px;font-size:13px'>{data_status[1]}</span>",
                unsafe_allow_html=True)
        m1, m2 = st.columns([4, 1], vertical_alignment="bottom")
        m1.text_input("Metadata CSV (optional)", key="w_meta",
                      help="One row per animal with group columns (treatment, sex, "
                           "cohort, …) so results can be compared across groups.")
        m2.button("Browse…", key="browse_meta", on_click=_pick_meta_csv,
                  use_container_width=True, help="Open a file chooser (local use only).")
        st.session_state["data_meta_path"] = st.session_state["w_meta"]
        # Join column: once a metadata CSV is chosen, offer its columns as a dropdown.
        _meta_cols = _metadata_columns(st.session_state["w_meta"])
        if _meta_cols:
            if st.session_state.get("w_join") not in _meta_cols:
                st.session_state["w_join"] = ("id" if "id" in _meta_cols else _meta_cols[0])
            st.selectbox(
                "Metadata join column", _meta_cols, key="w_join",
                help="Column in your metadata CSV that holds the animal id — its "
                     "values must match the video filenames (e.g. f1, f2).")
            st.session_state["data_join_col"] = st.session_state["w_join"]
        elif st.session_state["w_meta"]:
            st.caption("Couldn't read columns from that metadata file.")
        _, _nr = st.columns([5, 2])
        if _nr.button("Next: select animals →", type="primary", disabled=manifest_df is None,
                      use_container_width=True):
            st.session_state["wizard_step"] = 1; st.rerun()

    elif step == 1:  # select animals
        st.subheader("Which animals to load?")
        ids = manifest_df["id"].astype(str).tolist()

        # Optional metadata → show each animal's group columns next to its id.
        _md = None
        if meta_path and Path(meta_path).exists():
            try:
                _md = load_metadata(meta_path, join_col)
            except Exception:
                _md = None
        _gcols = group_like_columns(_md) if _md is not None else []

        def _meta_label(aid):
            if _md is not None and _gcols and aid in _md.index:
                parts = [f"{c}={_md.loc[aid, c]}" for c in _gcols
                         if pd.notna(_md.loc[aid, c])]
                if parts:
                    return f"{aid} — " + " · ".join(parts)
            return aid

        st.session_state.setdefault("wizard_sel",
                                    {i: (k < 8) for k, i in enumerate(ids)})
        cA, cB, _ = st.columns([1, 1, 6], gap="small")
        if cA.button("Select all", use_container_width=True):
            st.session_state["wizard_sel"] = {i: True for i in ids}
        if cB.button("Clear", use_container_width=True):
            st.session_state["wizard_sel"] = {i: False for i in ids}
        if meta_path and _md is None:
            st.caption("Metadata CSV couldn't be read — showing animal ids only.")
        elif _md is not None and not any(i in _md.index for i in ids):
            st.caption("No metadata rows matched these animals — check the join column.")
        with st.container(height=340):
            for i in ids:
                st.session_state["wizard_sel"][i] = st.checkbox(
                    _meta_label(i), value=st.session_state["wizard_sel"].get(i, False),
                    key=f"wsel_{i}")
        n = sum(1 for v in st.session_state["wizard_sel"].values() if v)
        st.caption(f"{n} of {len(ids)} selected")
        b1, _, b2 = st.columns([2, 6, 2])
        if b1.button("← Back", use_container_width=True):
            st.session_state["wizard_step"] = 0; st.rerun()
        if b2.button("Next: configure →", type="primary", disabled=n == 0,
                     use_container_width=True):
            st.session_state["wizard_step"] = 2; st.rerun()

    else:  # configure
        st.subheader("Analysis settings")
        sel_ids = [i for i, v in st.session_state.get("wizard_sel", {}).items() if v]

        # Reset per-video corners + box size if the data folder changed under us.
        if st.session_state.get("_arena_folder") != root_dir:
            st.session_state["_arena_folder"] = root_dir
            for _k in ("corners_by_id", "_fix_pending", "_corner_box_set",
                       "_wizard_autobox_for"):
                st.session_state.pop(_k, None)
            st.session_state["box_w"], st.session_state["box_h"] = 400, 300

        have_landmarks = _landmarks_present(root_dir, manifest_df, sel_ids)
        cbid = st.session_state.setdefault("corners_by_id", {})
        done_ids = [i for i in sel_ids if i in cbid]
        missing = [i for i in sel_ids if i not in cbid]

        # --- Resolve box size BEFORE the number_input widgets render (Streamlit
        # forbids mutating a widget-bound key after its widget exists this run).
        # The box is the output canvas all videos warp to: use the median of the
        # detected per-video corner boxes. ---
        if have_landmarks:
            if manifest_df is not None and st.session_state.get("_wizard_autobox_for") != str(manifest_path):
                st.session_state["_wizard_autobox_for"] = str(manifest_path)
                _autodetect_box(silent=True)
        elif done_ids:
            _bkey = tuple(sorted(done_ids))
            if st.session_state.get("_corner_box_set") != _bkey:
                st.session_state["_corner_box_set"] = _bkey
                _ws = [_box_from_corners(cbid[i]) for i in done_ids]
                st.session_state["box_w"] = int(np.median([w for w, _ in _ws]))
                st.session_state["box_h"] = int(np.median([h for _, h in _ws]))

        # --- Per-video arena corners (only when no landmark files exist) ---
        if not have_landmarks and manifest_df is not None and sel_ids:
            st.markdown("**Arena corners**")
            st.caption("Corners are found automatically from the coloured corner tape "
                       "in each video. Videos whose corners aren't taped are set by clicking.")
            ac1, ac2 = st.columns([1, 3], vertical_alignment="center")
            if ac1.button("Auto-detect corners", use_container_width=True):
                with st.spinner("Detecting corners in each video…"):
                    _autodetect_all_corners(root_dir, manifest_df, sel_ids)
                st.rerun()
            ac2.markdown(
                f"<div style='padding-top:6px'>Corners set for <b>{len(done_ids)}</b> / "
                f"{len(sel_ids)} videos"
                + (f" · <b>{len(missing)}</b> still need manual corners" if missing else "")
                + "</div>", unsafe_allow_html=True)
            if missing:
                st.markdown("**Set corners for a video without tape:**")
                fix_id = st.selectbox("Video", missing, key="_fix_which")
                _fix_corner_ui(root_dir, manifest_df, fix_id)
            elif done_ids:
                st.success(f"All {len(done_ids)} selected videos have corners.")

        if have_landmarks and st.button("Re-detect from arena corners"):
            _autodetect_box(silent=False)
        c1, c2 = st.columns(2)
        c1.number_input("Arena width", min_value=1, key="box_w")
        c2.number_input("Arena height", min_value=1, key="box_h")
        st.checkbox("Align videos to box", key="use_box_reference")
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
        load_ready = bool(sel_ids) and (have_landmarks or (bool(done_ids) and not missing))
        if not load_ready and sel_ids and not have_landmarks:
            st.caption("Set arena corners for every selected video to enable loading "
                       "(press Auto-detect, then fix any that remain).")
        d1, _, d2 = st.columns([2, 6, 2])
        if d1.button("← Back", use_container_width=True):
            st.session_state["wizard_step"] = 1; st.rerun()
        if d2.button(f"Load experiment ({len(sel_ids)})", type="primary",
                     disabled=not load_ready, use_container_width=True):
            st.session_state["pending_load_ids"] = sel_ids
            go("loading")


def render_loading():
    sel_ids = st.session_state.get("pending_load_ids", [])
    st.markdown("<div style='height:12vh'></div>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.spinner(f"Loading {len(sel_ids)} videos…"):
            try:
                _cbid = st.session_state.get("corners_by_id", {})
                if _cbid and not _landmarks_present(root_dir, manifest_df, sel_ids):
                    _generate_landmarks(root_dir, manifest_df, sel_ids, _cbid)
                do_load(sel_ids)
            except Exception as e:
                st.error(f"Failed to load: {e}")
                if st.button("← Back to setup"):
                    go("wizard")
                st.stop()
            try:
                autosave_current_load(sel_ids)
            except Exception:
                st.warning("Couldn't save this analysis to your records.")
    st.session_state["view"] = "Overview"
    go("app")


def render_top_bar(title, sub, logo=None):
    c1, c2 = st.columns([2, 1], vertical_alignment="center")
    with c1:
        if logo and Path(logo).exists():
            lg1, lg2 = st.columns([1, 5], vertical_alignment="center")
            with lg1:
                if str(logo).endswith(".svg"):
                    st.image(Path(logo).read_text(), width=72)
                else:
                    st.image(str(logo), width=72)
            lg2.markdown(f"<div class='topbar'><div><div class='sub'>{sub}</div>"
                         f"</div></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='topbar'><div><div class='title'>{title}</div>"
                        f"<div class='sub'>{sub}</div></div></div>", unsafe_allow_html=True)
    with c2:
        auth.header_account()


# ---- Overview ------------------------------------------------------------- #
_BAR_PALETTES = ["Grayscale", "tab10", "Set2", "Set1", "Dark2", "Paired", "colorblind"]
_HEAT_CMAPS = ["Greys", "Blues", "Reds", "Greens", "Oranges", "Purples",
               "viridis", "magma", "plasma", "inferno", "coolwarm", "hot"]


def _bar_palette(name, n):
    """Return (colors, hatches) for n groups. 'Grayscale' keeps the B&W look
    (grey ramp + hatch); any other name uses that seaborn/matplotlib palette."""
    if name == "Grayscale":
        greys = theme.group_greys(n)
        return [g[0] for g in greys], [g[1] for g in greys]
    return sns.color_palette(name, n).as_hex(), [""] * n


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
    _sig = (tuple(sel), _cfg_sig())
    if st.button("Build montage",
                 help="Render a grid of one frame per selected video, before vs. after alignment."):
        with loading("loading"):
            try:
                orig = bapipe.create_video_grid(
                    vids,
                    override_config={"use_box_reference": False, "remove_lens_distortion": False})
                aligned = bapipe.create_video_grid(vids)
                st.session_state["_montage"] = {
                    "sig": _sig, "orig": np.clip(orig, 0, 1), "aligned": np.clip(aligned, 0, 1)}
            except Exception as e:
                st.session_state["_montage"] = {"sig": _sig, "error": str(e)}
    # Persisted so it stays visible after other interactions rerun the app.
    _m = st.session_state.get("_montage")
    if _m and _m.get("sig") == _sig:
        if _m.get("error"):
            st.error(f"Couldn't build the montage: {_m['error']}")
        else:
            col1, col2 = st.columns(2)
            col1.markdown("**Original**")
            col1.image(_m["orig"], use_container_width=True)
            col2.markdown("**Aligned**")
            col2.image(_m["aligned"], use_container_width=True)


# ---- Distance ------------------------------------------------------------- #
def render_distance():
    st.subheader("Total distance travelled")
    sel = animal_selector("dist_animals")
    group_col = group_selector("dist_group")
    pal_name = st.selectbox("Colour palette", _BAR_PALETTES, key="dist_palette",
                            help="Bar colours by group. 'Grayscale' keeps the black & white look.")

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
            colors, hatches = _bar_palette(pal_name, data[group_col].nunique())
            bars = sns.barplot(data=data, x=group_col, y="distance", ax=ax, palette=colors)
            for patch, hatch in zip(bars.patches, hatches):
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
    cmap = st.selectbox("Colour map", _HEAT_CMAPS, key="heat_cmap",
                        help="Density colour scheme. 'Greys' keeps the black & white look.")

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
                        cs = ax.contourf(z, cmap=cmap, alpha=intensity, levels=levels)
                        cbar = fig.colorbar(cs, ax=ax, fraction=0.046, pad=0.04)
                        cbar.set_label("Occupancy density\n(more intense = more time spent)")
                    ax.axis("off")
                    st.pyplot(fig)
                    fig_export(fig, f"heatmap_{name}".replace("/", "-"), f"heat_{i}")


# ---- Time in zone --------------------------------------------------------- #
def render_zone():
    st.subheader("Time spent in a centred zone")
    sel = animal_selector("zone_animals")
    group_col = group_selector("zone_group")
    pal_name = st.selectbox("Colour palette", _BAR_PALETTES, key="zone_palette",
                            help="Bar colours by group. 'Grayscale' keeps the black & white look.")

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
            colors, hatches = _bar_palette(pal_name, data[group_col].nunique())
            bars = sns.barplot(data=data, x=group_col, y="time_in_zone", ax=ax, palette=colors)
            for patch, hatch in zip(bars.patches, hatches):
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
    render_top_bar("Dashboard", "Your saved analyses", logo=LOGO_PATH)
    a1, a2, _ = st.columns([1, 1.3, 8], gap="small")
    if a1.button("Guide", use_container_width=True):
        go("guide")
    if a2.button("＋ New analysis", type="primary", use_container_width=True):
        st.session_state["wizard_step"] = 0
        for k in ("video_set", "config", "metadata"):
            st.session_state.pop(k, None)
        go("wizard")

    recs = records.list_records(current_user_key())
    if not recs:
        st.markdown(
            "<div style='text-align:center;color:#2f6df0;padding:2.5rem 0;"
            "font-size:1rem'>No saved records yet — press New analysis to begin.</div>",
            unsafe_allow_html=True)
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
    nav1, nav2, _ = st.columns([1, 1, 6])
    if nav1.button("← Change data", key="app_change"):
        for k in ("video_set", "config", "metadata"):
            st.session_state.pop(k, None)
        st.session_state["wizard_step"] = 0
        go("wizard")
    if nav2.button("Guide", key="app_guide"):
        go("guide")
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
