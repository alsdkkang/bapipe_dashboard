"""Bundled sample experiment loader.

Primes the same canonical data-selection session keys the Start wizard writes, so
the existing folder-based load pipeline (`build_manifest_from_folders` + `do_load`)
handles the sample with no special-casing. Lets the deployed demo open a populated
dashboard without any upload.
"""
from pathlib import Path

import streamlit as st

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_data"
SAMPLE_IDS = ["f1", "f2", "f3", "f4"]


def sample_available() -> bool:
    return (SAMPLE_DIR / "videos").is_dir() and (SAMPLE_DIR / "mouse_labels").is_dir()


def prime_sample() -> None:
    """Point the canonical data-selection keys at the bundled sample and queue all
    of its animals for loading. Caller then routes to the "loading" phase."""
    st.session_state["data_video_dir"] = str(SAMPLE_DIR / "videos")
    st.session_state["data_dlc_dir"] = str(SAMPLE_DIR / "mouse_labels")
    st.session_state["data_landmark_dir"] = str(SAMPLE_DIR / "landmark_labels")
    st.session_state["data_calib_path"] = str(SAMPLE_DIR / "camera_calibrations.json")
    st.session_state["data_meta_path"] = str(SAMPLE_DIR / "metadata.csv")
    st.session_state["data_join_col"] = "id"
    st.session_state["pending_load_ids"] = list(SAMPLE_IDS)
    # Clear any stale wizard corner state so loading uses the bundled landmarks.
    st.session_state.pop("corners_by_id", None)
