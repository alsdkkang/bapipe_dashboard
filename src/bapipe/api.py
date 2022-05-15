"""Core classes for processing experiment videos"""
import csv
import json
import multiprocessing as mp
from functools import partial
from itertools import combinations
from pathlib import Path
from typing import Iterable, List, Tuple, Union

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm import tqdm

from .configs import AnalysisConfig

from dataclasses import dataclass, asdict
from pathlib import Path


class VideoSet:
    """High level interface for processing multiple videos at once"""

    def __init__(self):
        self.videos = []

    @staticmethod
    def load(
        df: pd.DataFrame,
        config: AnalysisConfig,
        root_dir: Union[Path, str] = "",
        use_multiprocessing: bool = True,
    ):
        """Load videos from a dataframe containing file locations

        Parameters
        ----------
        df : pandas.Dataframe
          Contains file locations with the following column names: id, video, 
          mouse_labels, landmark_labels, camera_calibrations
        config : AnalysisConfig
          Options to analyze the experiment with
        root_dir : Path
          Specify the directory which the `df` paths are relative to
        use_multiprocessing : bool, default=True
          Parallelize loading the files

        Returns
        -------
        """
        vs = VideoSet()
        p = partial(Video.from_record, kwargs={"root_dir": root_dir, "config": config})
        records = df.to_dict(orient="records")
        if use_multiprocessing:
            with mp.Pool(processes=mp.cpu_count()) as pool:
                vs.videos += list(tqdm(pool.imap(p, records), total=len(records)))
        else:
            vs.videos += [
                p(record)
                for record in tqdm(
                    records,
                )
            ]

        return vs

    def __iter__(self):
        return iter(self.videos)

    def __len__(self):
        return len(self.videos)

    def __getitem__(self, idx):
        return self.videos[idx]

    def __add__(self, other):
        assert isinstance(other, VideoSet)
        self.videos.update(other.videos)

    def apply(
        self,
        foo: callable,
        *args,
        use_multiprocessing: bool = True,
        as_df: bool = False,
        **kwargs,
    ):
        """Apply a callable to the entire VideoSet

        Parameters
        ----------
        foo : callable
          The function/class to apply
        *args 
          Arguments passed on to callable
        use_multiprocessing : bool, default = True
          Apply the function in parallel using multiprocessing
        as_df : bool, default = False
          Return results as dataframe

        Returns
        -------
        List or pandas.Dataframe containing outputs of the provided callable
        """
        p = partial(foo, *args, **kwargs)
        if use_multiprocessing:
            with mp.Pool(processes=mp.cpu_count()) as pool:
                results = list(tqdm(pool.imap(p, self.videos), total=len(self.videos)))
        else:
            results = [
                p(subject_analysis)
                for subject_analysis in tqdm(list(self.videos), total=len(self.videos))
            ]

        if as_df:
            results = pd.DataFrame(dict(zip(self.index, results))).T

        return results

    @property
    def index(self):
        return [v.id for v in self.videos]

    def get_description(self):
        """Summarize basic stats from the video set"""
        sizes = {(video.frame_width, video.frame_height) for video in self.videos}
        durations = np.array([video.duration for video in self.videos])

        return [
            ["Number of videos", len(self.videos)],
            ["Video sizes (W,H)", ", ".join([f"{w}x{h}" for w, h in sizes])],
            ["Total duration [s]", np.sum(durations)],
            ["Average duration [s]", round(np.mean(durations), 2)],
        ]

    def __repr__(self):
        return "\n".join([f"{d}: {v}" for d, v in self.get_description()])

    def _repr_html_(self):
        content = "".join(
            [f"<tr><td>{d}</td><td>{v}</td></tr>" for d, v in self.get_description()]
        )
        return f"<table>{content}</table>"


class Video:
    """Class for processing data relating to a single video"""

    def __init__(
        self,
        config: AnalysisConfig,
        id: str,
        video: str,
        mouse_labels: str,
        landmark_labels: str,
        camera_calibrations: str,
        root_dir: Union[str, Path] = "",
        **kwargs,
    ):
        """Load and preprocess the video datafiles 
        
        Parameters
        ----------

        """
        if isinstance(root_dir, str):
            root_dir = Path(root_dir)

        self.config = config
        self.id = id
        self.video = root_dir / video
        self.mouse_labels = root_dir / mouse_labels
        self.landmark_labels = root_dir / landmark_labels
        self.camera_calibrations = root_dir / camera_calibrations

        # Load data
        self.mouse_df = pd.read_hdf(self.mouse_labels)
        self.landmarks_df = pd.read_hdf(self.landmark_labels)

        # Remove lens distortions
        if self.config.remove_lens_distortion:
            self.calib = CameraCalibration(self.camera_calibrations)
            self.calib.get_new_cameramatrix(self.frame_width, self.frame_height)
            self.mouse_df = self.undistort(self.mouse_df)
            self.landmarks_df = self.undistort(self.landmarks_df)

        # Change to the box frame of reference
        if self.config.use_box_reference:
            self.get_perspective_transform()
            self.mouse_df = self.transform_dataframe_to_perspective(self.mouse_df)
            self.landmarks_df = self.transform_dataframe_to_perspective(
                self.landmarks_df
            )

        # Filter outliers
        self.mouse_df = self.remove_outliers(self.mouse_df, self.config.outlier_sigmas)
        self.landmarks_df = self.remove_outliers(
            self.landmarks_df, self.config.outlier_sigmas
        )

        # Forward fill missing points (e.g. ones removed for low confidence)
        self.mouse_df = self.mouse_df.interpolate(imitection="forward")
        self.landmarks_df = self.landmarks_df.interpolate(limitection="forward")

        # Get first frame in box
        self.get_first_frame_mouse_in_box()

    @staticmethod
    def from_record(record, kwargs):
        return Video(**record, **kwargs)

    @property
    def frame_count(self):
        return int(self.get_cap().get(cv2.CAP_PROP_FRAME_COUNT))

    @property
    def frame_width(self):
        return int(self.get_cap().get(cv2.CAP_PROP_FRAME_WIDTH))

    @property
    def frame_height(self):
        return int(self.get_cap().get(cv2.CAP_PROP_FRAME_HEIGHT))

    @property
    def fps(self):
        return float(self.get_cap().get(cv2.CAP_PROP_FPS))

    @property
    def duration(self):
        """Duration in seconds"""
        return self.frame_count / self.fps

    def get_cap(self):
        return cv2.VideoCapture(str(self.video))

    def undistort(self, df):
        """Remove lens warping from dataframe containing x,y coordinates"""
        df = df.copy()
        idx = pd.IndexSlice

        x = df.loc[:, idx[:, :, "x"]]
        y = df.loc[:, idx[:, :, "y"]]

        # Stack x, y coordinates into 1 dimension
        x = x.stack(dropna=False).stack(dropna=False)
        y = y.stack(dropna=False).stack(dropna=False)

        # Create a merged [x,y] array and remove lens warping
        points = np.c_[x, y][:, np.newaxis, :]
        points = cv2.undistortPoints(
            points, self.calib.m, self.calib.d, None, None, self.calib.m
        )

        # Shape points back into a multi-indexed dataframe
        nx, ny = points[:, 0].T
        nx = pd.DataFrame(nx, index=x.index, columns=x.columns).unstack().unstack()
        ny = pd.DataFrame(ny, index=y.index, columns=y.columns).unstack().unstack()

        # Recover original structure
        df.loc[:, idx[:, :, "x"]] = nx
        df.loc[:, idx[:, :, "y"]] = ny
        return df

    def get_perspective_transform(self):
        """Get the perspective transformation to be in the box's frame of reference"""
        corners = ["top_left", "top_right", "bottom_right", "bottom_left"]

        # Use median values because:
        # 1. Computing frame-by-frame perspective transform is too expensive and indicates greater problems in the experiment
        # 2. A mean should not be used as there is sometimes initial movement
        # Movement should be tested either visually (by plotting out corner movement) or develop a test (TODO)
        df = self.landmarks_df.droplevel("scorer", axis=1)
        landmarks_median = df.median()[corners]

        x = landmarks_median.xs("x", level="coords").values
        y = landmarks_median.xs("y", level="coords").values

        width, height = self.config.box_shape
        src = np.array(list(zip(x, y))).astype(np.float32)
        dst = np.array([[0, 0], [width, 0], [width, height], [0, height]]).astype(
            np.float32
        )
        self.perspective_transform = cv2.getPerspectiveTransform(src=src, dst=dst)

    def transform_dataframe_to_perspective(self, df):
        """Transform the coordinate dataframes to be in the box's frame of reference"""
        df = df.copy().dropna()
        idx = pd.IndexSlice
        x = df.loc[:, idx[:, :, "x"]]
        y = df.loc[:, idx[:, :, "y"]]
        x = x.stack(dropna=False).stack(dropna=False)
        y = y.stack(dropna=False).stack(dropna=False)

        tx, ty, v = self.perspective_transform @ np.c_[x, y, np.ones_like(x)].T
        tx = tx / v
        ty = ty / v

        tx = pd.DataFrame(tx, index=x.index, columns=x.columns).unstack().unstack()
        ty = pd.DataFrame(ty, index=y.index, columns=y.columns).unstack().unstack()

        # Update multi index columns to match
        df.loc[:, pd.IndexSlice[:, :, "x"]] = tx
        df.loc[:, pd.IndexSlice[:, :, "y"]] = ty
        return df

    def transform_array_to_perspective(self, arr):
        """Move into the box's frame of reference"""
        x, y = arr.T
        tx, ty, v = self.perspective_transform @ np.c_[x, y, np.ones_like(x)].T
        return np.c_[tx / v, ty / v]

    def undistort_frame(self, frame, override_config={}):
        config = {**asdict(self.config), **override_config}

        if config["remove_lens_distortion"]:
            frame = cv2.undistort(frame, self.calib.m, self.calib.d)

        if config["use_box_reference"]:
            frame = cv2.warpPerspective(
                frame, self.perspective_transform, config["box_shape"]
            )

        return frame

    def get_frame(self, frame_idx, override_config={}):
        cap = self.get_cap()
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = self.undistort_frame(frame, override_config)
        return frame

    def get_first_frame_mouse_in_box(self):
        """Return the frame the mouse is first visible, with a tolerance to
        remove noise"""
        
        w, h = self.config.box_shape
        padding = 50
        points = [
            (-padding, -padding),
            (w + padding, -padding),
            (w + padding, h + padding),
            (-padding, h + padding),
        ]
        box = plt.Polygon(points)
        centroid_df = self.mouse_df.groupby(level="coords", axis=1).mean()
        centroid = centroid_df.values.reshape(-1, 3)[:, :2]

        s = pd.DataFrame(box.contains_points(centroid), index=centroid_df.index)
        self.first_frame_mouse_in_box = (
            s.rolling(self.config.mouse_in_box_tolerance).mean().idxmax()[0]
        )

    def remove_outliers(self, df, sigmas=3):
        df = df.droplevel("scorer", axis=1)

        # Remove keypoints based on confidence
        if self.config.outlier_use_likelhiood:
            low_confidence = (
                df.xs("likelihood", level="coords", axis=1) < self.config.pcutoff
            )
            df = df.where(~low_confidence)

        # Remove keypoints based on position relative to other keypoints
        if self.config.outlier_use_pairwise_distance:
            columns = df.columns.get_level_values("bodyparts").unique()
            relative_distances = pd.DataFrame(
                index=df.index, columns=pd.MultiIndex.from_product([columns, columns])
            )
            relative_distances.columns = (
                relative_distances.columns.sort_values()
            )  # get rid of sorted errors
            relative_distances = relative_distances.sort_index()

            for c1, c2 in combinations(columns, 2):
                delta = abs(df.loc[:, c1] - df.loc[:, c2])
                distance = np.sqrt(delta.x**2 + delta.y**2)
                relative_distances.loc[:, (c1, c2)] = distance.values
                relative_distances.loc[:, (c2, c1)] = distance.values

            outliers = pd.DataFrame(index=df.index, columns=columns)
            for c in columns:
                cdata = relative_distances.loc[:, c]
                standardized_distance = cdata - cdata.mean() > cdata.std() * sigmas
                count = standardized_distance.sum(axis=1)
                outliers.loc[:, c] = count >= len(columns) - 1

            df = df.where(~outliers)

        # Remove keypoints based on individual position changes
        if self.config.outlier_use_bodypart_distance:
            deltas = df.diff()
            x = deltas.xs("x", level="coords", axis=1)
            y = deltas.xs("y", level="coords", axis=1)
            distance = np.sqrt(x**2 + y**2)
            df = df.where(distance - distance.mean() < distance.std() * sigmas)

        # Remove rows based on centroid changes
        if self.config.outlier_use_centroid_distance:
            deltas = df.groupby(level="coords", axis=1).mean().diff()
            distance = np.sqrt(deltas.x**2 + deltas.y**2)
            df = df.where(distance - distance.mean() < distance.std() * sigmas)

        # Remove rows based on number of bodyparts
        if self.config.outlier_use_minimum_bodyparts:
            missing_parts = (
                df.isna().groupby(level="bodyparts", axis=1).all().sum(axis=1)
            )
            df = df.where(missing_parts < self.config.outlier_minimum_bodyparts)

        return df


class CameraCalibration:
    def __init__(self, calibration_file: Union[Path, str]):
        """Load camera calibration data from a file"""
        with open(calibration_file, "r") as fp:
            calib = json.load(fp)
            self.d = np.array(calib["distortion_coefficients"])
            self.m = np.array(calib["camera_matrix"])

    @property
    def distortion_coefficients(self):
        """Camera distortion coefficients, equivalent to self.d"""
        return self.d

    @property
    def camera_matrix(self):
        """Camera matrix, equivalent to self.m"""
        return self.m

    @property
    def new_cameramatrix(self):
        """New camera matrix, equivalent to self.nm"""
        return self.nm

    def get_new_cameramatrix(self, frame_width: int, frame_height: int):
        """Create a new camera matrix for the given resolution"""
        self.nm = cv2.getOptimalNewCameraMatrix(
            self.m, self.d, (frame_width, frame_height), 1, (frame_width, frame_height)
        )
