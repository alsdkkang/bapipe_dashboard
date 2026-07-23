"""Pure analysis helpers for the bapipe GUI.

These functions are lifted from the worked examples in the project README so they
can be reused and tested without Streamlit. Each takes a ``bapipe.Video`` (or a
list of them) and returns plain numbers / arrays / file paths.
"""
from pathlib import Path

import numpy as np
import pandas as pd


CORNERS = ["top_left", "top_right", "bottom_right", "bottom_left"]


def robust_corner_points(landmark_h5_path, pcutoff=0.6):
    """Robust (x, y) estimate of the 4 arena corners from a landmark .h5.

    For each corner, discards frames where the detection likelihood is below
    ``pcutoff`` (so noisy / occluded frames don't drag the estimate around) and
    takes the median of the survivors — much cleaner than a plain mean/median
    over every frame when the corners are DeepLabCut-detected. Falls back to all
    frames for a corner if too few pass the threshold. Returns 4 (x, y) pairs
    ordered [top_left, top_right, bottom_right, bottom_left].
    """
    df = pd.read_hdf(landmark_h5_path)
    if "scorer" in (df.columns.names or []):
        df = df.droplevel("scorer", axis=1)

    points = []
    for c in CORNERS:
        x, y = df[(c, "x")], df[(c, "y")]
        if (c, "likelihood") in df.columns:
            good = df[(c, "likelihood")] >= pcutoff
            if int(good.sum()) >= 5:
                x, y = x[good], y[good]
        points.append((float(np.nanmedian(x)), float(np.nanmedian(y))))
    return points


def detect_box_shape_from_landmarks(landmark_h5_path, pcutoff=0.6):
    """Estimate the arena's (width, height) from its labelled corners.

    Uses the likelihood-filtered robust corner estimate, then measures both
    horizontal sides (and both vertical sides) and averages each. Returns
    integers in the *pixel* units of the source video — the true aspect ratio
    and relative size of the open-field box. For real millimetres, scale by
    (known_mm / measured_px) using a known physical dimension.
    """
    tl, tr, br, bl = (np.array(p, dtype=float) for p in robust_corner_points(landmark_h5_path, pcutoff))
    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    return int(round(width)), int(round(height))


def get_centroid(video):
    """Average the mouse bodypart positions to a single (x, y) trajectory."""
    centroid = video.mouse_df.groupby(level="coords", axis=1).mean()
    return centroid[["x", "y"]]


def distance_travelled(video):
    """Total distance travelled by the mouse centroid (in box units, e.g. mm)."""
    centroid = get_centroid(video)
    deltas = centroid.diff().dropna()
    return float(np.sum(np.linalg.norm(deltas.values, axis=1)))


def occupancy_kde(videos, box_shape, downsample=100):
    """Gaussian-KDE occupancy density over a group of videos.

    Parameters
    ----------
    videos : list of bapipe.Video
    box_shape : (width, height)
    downsample : keep 1 frame every ``downsample`` frames (speed).

    Returns
    -------
    z : 2D ndarray of shape (height, width) with the density, or None if there
        were not enough points to fit a KDE.
    """
    from scipy.stats import gaussian_kde

    w, h = box_shape
    if not videos:
        return None
    group_df = pd.concat([v.mouse_df for v in videos], axis=0).dropna()
    if group_df.empty:
        return None

    centroid = group_df.groupby(level="coords", axis=1).mean()[["x", "y"]]
    # data as (y, x) rows -> shape (2, N)
    data = centroid[["y", "x"]].values.T
    data = data[:, ::downsample]
    if data.shape[1] < 3:
        return None

    try:
        k = gaussian_kde(data)
    except np.linalg.LinAlgError:
        return None

    mgrid = np.mgrid[:h, :w]
    z = k(mgrid.reshape(2, -1))
    return z.reshape(h, w)


def square_zone(cx, cy, half_size):
    """A square zone of side 2*half_size centred at (cx, cy), as a matplotlib Polygon."""
    import matplotlib.pyplot as plt

    s = half_size
    return plt.Polygon(
        [[cx - s, cy - s], [cx - s, cy + s], [cx + s, cy + s], [cx + s, cy - s]],
        alpha=0.5,
        label="zone",
    )


def centered_zone(box_shape, half_size):
    """A square zone centred in the box, as a matplotlib Polygon."""
    w, h = box_shape
    return square_zone(w // 2, h // 2, half_size)


def time_in_zone(video, zone):
    """Seconds the mouse centroid spends inside ``zone`` (a matplotlib Polygon)."""
    centroid = get_centroid(video).values
    inside = zone.contains_points(centroid)
    return float(np.sum(inside) / video.fps)


def annotate_clip(video, start, length, out_path, bodyparts=None):
    """Write a browser-playable mp4 of ``length`` frames from ``start`` with the
    mouse keypoints drawn on top. Uses imageio (bundled ffmpeg) so no system
    ffmpeg binary is required.

    Returns the output path.
    """
    import imageio.v2 as imageio

    from bapipe import draw_dataframe_points

    out_path = str(out_path)
    fps = video.fps if video.fps and video.fps > 0 else 30.0
    # Clamp to the video's real length — reading past the last frame returns an
    # empty array and crashes OpenCV's cvtColor (e.g. trimmed clips / overshooting
    # start+length). The clip is simply shorter when the range exceeds the video.
    start = max(0, min(int(start), max(0, video.frame_count - 1)))
    end = min(start + int(length), video.frame_count)

    writer = imageio.get_writer(out_path, fps=fps, codec="libx264", format="FFMPEG")
    try:
        for i in range(start, end):
            frame = video.get_frame(i)  # RGB uint8
            if frame is None or getattr(frame, "size", 0) == 0:
                break
            draw_dataframe_points(
                frame, video.mouse_df, i, bodyparts=bodyparts or []
            )
            writer.append_data(frame.astype(np.uint8))
    finally:
        writer.close()
    return Path(out_path)
