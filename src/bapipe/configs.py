"""Configuration file for processing videos"""
import multiprocessing as mp
import pandas as pd

from dataclasses import dataclass, asdict
from typing import Iterable, Union, Tuple, List
from pathlib import Path

@dataclass
class AnalysisConfig:
    # Outlier parameters for filtering pose data
    pcutoff: float = 0.6 # DLC

    outlier_sigmas: float = 3.0
    outlier_minimum_bodyparts: int = 3
    outlier_use_pairwise_distance: bool = True
    outlier_use_bodypart_distance: bool = True
    outlier_use_centroid_distance: bool = True
    outlier_use_likelhiood: bool = True
    outlier_use_minimum_bodyparts: bool = True

    # Tolerance for when mouse is first placed in box
    mouse_in_box_tolerance: int = 10

    # Remove distortion
    remove_lens_distortion: bool = False
    use_box_reference: bool = True
    box_shape: Tuple[int, int] = (540, 540)