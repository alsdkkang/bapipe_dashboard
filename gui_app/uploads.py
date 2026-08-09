"""Per-field experiment upload for the hosted app.

The browser can't reach the user's local files (and can't upload a folder), so
each wizard field gets its own uploader: pick the files for that folder — or a
.zip of it. We write them into a per-field subfolder of a temporary directory and
point the existing folder-based load pipeline at it. Nothing is persisted; the
temp folder is ephemeral.
"""
import shutil
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

# folder subdir -> (canonical data key, wizard widget key)
FIELD_KEYS = {
    "videos": ("data_video_dir", "w_video"),
    "mouse_labels": ("data_dlc_dir", "w_dlc"),
    "landmarks": ("data_landmark_dir", "w_land"),
}


def _root():
    """A persistent (per-session) temp directory holding the uploaded pieces."""
    r = st.session_state.get("_upload_dir")
    if not r or not Path(r).exists():
        r = tempfile.mkdtemp(prefix="bapipe_upload_")
        st.session_state["_upload_dir"] = r
    return Path(r)


def write_folder(dest, files):
    """Write uploaded files into ``dest`` (a single .zip is extracted in place).
    Returns the file count. Pure helper (no Streamlit) — each file needs ``.name``
    and ``.getvalue()``."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in files:
        f.seek(0)
        if f.name.lower().endswith(".zip"):
            # ZipFile reads the (seekable) upload directly and streams each member
            # out to disk — no second full-size copy of the archive in memory.
            with zipfile.ZipFile(f) as z:
                for member in z.namelist():
                    if member.endswith("/"):
                        continue
                    with z.open(member) as src, open(dest / Path(member).name, "wb") as out:
                        shutil.copyfileobj(src, out)
                    n += 1
        else:
            with open(dest / Path(f.name).name, "wb") as out:
                shutil.copyfileobj(f, out)  # chunked copy, avoids getvalue()'s full copy
            n += 1
    return n


def save_field_folder(subdir, files):
    """Save one folder field's files (or zip) into its subdir and set its data
    keys. Returns ``(ok, message)``."""
    dest = _root() / subdir
    n = write_folder(dest, files)
    dkey, wkey = FIELD_KEYS[subdir]
    st.session_state[dkey] = st.session_state[wkey] = str(dest)
    return (n > 0), (f"{n} file(s) uploaded." if n else "No files were uploaded.")


def save_field_single(dkey, wkey, uploaded, is_calib=False):
    """Save a single-file field (calibration / metadata) and set its keys."""
    data = uploaded.getvalue()
    if is_calib and b"camera_matrix" not in data:
        return False, "That JSON has no camera_matrix — it isn't a calibration file."
    path = _root() / Path(uploaded.name).name
    path.write_bytes(data)
    st.session_state[dkey] = st.session_state[wkey] = str(path)
    return True, f"“{uploaded.name}” uploaded."
