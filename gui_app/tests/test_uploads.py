import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uploads  # noqa: E402


def test_detect_dirs_on_sample_layout():
    sample = Path(__file__).resolve().parents[1] / "sample_data"
    if not sample.exists():
        import pytest
        pytest.skip("sample_data not bundled")
    found = uploads.detect_dirs(sample)
    assert found["video_dir"].name == "videos"
    assert found["dlc_dir"].name == "mouse_labels"
    assert found["landmark_dir"].name == "landmark_labels"
    assert found["calib"].name == "camera_calibrations.json"
    assert found["meta"].name == "metadata.csv"


def test_detect_dirs_missing_pieces(tmp_path):
    # only videos, no h5 / calib / metadata
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "f1.mp4").write_bytes(b"\x00")
    found = uploads.detect_dirs(tmp_path)
    assert found["video_dir"].name == "videos"
    assert found["dlc_dir"] is None
    assert found["landmark_dir"] is None
    assert found["calib"] is None and found["meta"] is None


def test_metadata_not_confused_with_manifest(tmp_path):
    (tmp_path / "meta.csv").write_text("id,treatment\nf1,saline\n")
    (tmp_path / "datafiles.csv").write_text("id,video,mouse_labels\nf1,videos/f1.mp4,x.h5\n")
    found = uploads.detect_dirs(tmp_path)
    assert found["meta"].name == "meta.csv"  # manifest (has 'video') is not picked


def test_classify_sorts_files_by_type():
    assert uploads._classify("f1.mp4") == "videos"
    assert uploads._classify("f1_labeledDLC.mp4") is None  # skip DLC-labeled videos
    assert uploads._classify("f1DLC_resnet50.h5") == "mouse_labels"
    assert uploads._classify("f1_landmarks.h5") == "landmarks"
    assert uploads._classify("camera_calibrations.json") is None  # sorted by content
    assert uploads._classify("metadata.csv") is None
