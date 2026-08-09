import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uploads  # noqa: E402


class _Fake(io.BytesIO):
    """Stand-in for a Streamlit UploadedFile: a seekable byte stream + name."""
    def __init__(self, name, data=b"\x00"):
        super().__init__(data)
        self.name = name


def test_write_folder_writes_files(tmp_path):
    dest = tmp_path / "videos"
    n = uploads.write_folder(dest, [_Fake("f1.mp4"), _Fake("f2.mp4")])
    assert n == 2
    assert {p.name for p in dest.iterdir()} == {"f1.mp4", "f2.mp4"}


def test_write_folder_extracts_zip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("run/f1DLC.h5", b"\x00")
        z.writestr("run/f2DLC.h5", b"\x00")
        z.writestr("run/", b"")  # a bare directory entry is skipped
    dest = tmp_path / "mouse_labels"
    n = uploads.write_folder(dest, [_Fake("labels.zip", buf.getvalue())])
    assert n == 2
    # nested paths are flattened to basenames
    assert {p.name for p in dest.iterdir()} == {"f1DLC.h5", "f2DLC.h5"}


def test_write_folder_replaces_previous_contents(tmp_path):
    dest = tmp_path / "videos"
    uploads.write_folder(dest, [_Fake("old.mp4")])
    uploads.write_folder(dest, [_Fake("new.mp4")])
    assert {p.name for p in dest.iterdir()} == {"new.mp4"}  # old cleared


def test_field_keys_cover_the_three_folders():
    assert set(uploads.FIELD_KEYS) == {"videos", "mouse_labels", "landmarks"}
    # each maps to (canonical data key, wizard widget key)
    assert uploads.FIELD_KEYS["videos"] == ("data_video_dir", "w_video")
