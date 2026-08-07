"""Upload an experiment as a .zip and analyse it on the hosted app.

The browser can't reach the user's local files (and native Browse dialogs don't
exist on the server), so the user zips their experiment folder and uploads it. We
extract it to a temporary directory, auto-detect the video / DLC / landmark folders
+ calibration + metadata, and point the existing folder-based load pipeline at
them. Nothing is persisted — the temp dir is ephemeral and replaced on each upload.
"""
import io
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import streamlit as st

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv"}


def _dir_with(pred, root):
    """Directory holding the most files matching ``pred`` (or None)."""
    counts = Counter()
    for p in root.rglob("*"):
        if p.is_file() and pred(p):
            counts[p.parent] += 1
    return counts.most_common(1)[0][0] if counts else None


def _is_calib(path):
    try:
        return "camera_matrix" in path.read_text()
    except Exception:
        return False


def _is_metadata(path):
    try:
        header = path.read_text().splitlines()[0].lower()
    except Exception:
        return False
    cols = [c.strip() for c in header.split(",")]
    return "id" in cols and "video" not in cols  # a metadata table, not a manifest


def detect_dirs(root):
    """Auto-detect the experiment pieces inside an extracted folder tree.
    Pure function (no Streamlit) so it can be unit-tested."""
    root = Path(root)
    return {
        "video_dir": _dir_with(lambda p: p.suffix.lower() in VIDEO_EXT, root),
        "landmark_dir": _dir_with(lambda p: p.name.endswith("_landmarks.h5"), root),
        "dlc_dir": _dir_with(
            lambda p: p.suffix.lower() == ".h5" and not p.name.endswith("_landmarks.h5"),
            root),
        "calib": next((p for p in root.rglob("*.json") if _is_calib(p)), None),
        "meta": next((p for p in root.rglob("*.csv") if _is_metadata(p)), None),
    }


def save_and_detect(uploaded):
    """Extract an uploaded zip to a fresh temp dir, detect the pieces, and prime
    the canonical + wizard data keys. Returns ``(ok, message)``."""
    prev = st.session_state.get("_upload_dir")
    if prev and Path(prev).exists():
        shutil.rmtree(prev, ignore_errors=True)
    root = Path(tempfile.mkdtemp(prefix="bapipe_upload_"))
    try:
        with zipfile.ZipFile(io.BytesIO(uploaded.getvalue())) as z:
            z.extractall(root)
    except zipfile.BadZipFile:
        return False, "That doesn't look like a valid .zip file."
    st.session_state["_upload_dir"] = str(root)

    found = detect_dirs(root)
    if not found["video_dir"]:
        return False, "No videos (.mp4) found in the zip."
    if not found["dlc_dir"]:
        return False, "No DLC keypoints (.h5) found in the zip."

    st.session_state["data_video_dir"] = st.session_state["w_video"] = str(found["video_dir"])
    st.session_state["data_dlc_dir"] = st.session_state["w_dlc"] = str(found["dlc_dir"])
    st.session_state["data_landmark_dir"] = st.session_state["w_land"] = (
        str(found["landmark_dir"]) if found["landmark_dir"] else "")
    st.session_state["data_calib_path"] = st.session_state["w_calib"] = (
        str(found["calib"]) if found["calib"] else "")
    st.session_state["data_meta_path"] = st.session_state["w_meta"] = (
        str(found["meta"]) if found["meta"] else "")

    n_vid = sum(1 for p in found["video_dir"].iterdir() if p.suffix.lower() in VIDEO_EXT)
    bits = [f"{n_vid} video(s)", f"DLC “{found['dlc_dir'].name}”"]
    if found["landmark_dir"]:
        bits.append("landmarks")
    if found["calib"]:
        bits.append("calibration")
    if found["meta"]:
        bits.append(f"metadata “{found['meta'].name}”")
    return True, "Extracted — " + ", ".join(bits) + "."
