# Behaviour Analysis for Keypoint Data
A pipeline for turning keypoint data gathered from deep learning models into data and visualizations. 

## Background
Advances in Deep Learning have driven a wave of pose-estimation tools which extract information from animals and their surroundings ([DeepLabCut](http://www.mackenziemathislab.org/deeplabcut), [OpenPose](https://github.com/CMU-Perceptual-Computing-Lab/openpose), [SLEAP](https://sleap.ai/)). These models are trained to extract keypoint data (x, y coordinates) for specified bodyparts or objects in the environment.

This pipeline automates a number of steps involved in turning this keypoint data from behavioural experiments into meaningful data and visuallizations. Some of these steps include
- Aligning videos to account for changes in camera perspective
- Several outlier-filtering strategies
- Creating videos and other validation graphs
- Trimming video duration for when the mouse is first visible

We demonstrate a few examples of using DeepLabCut data in order to produce
1. Custom validation videos
2. Total distance travelled by treatment group
3. Heatmaps by treatment group treatment groups
4. Time spent in a zone

Entire experiments can often be processed quite quickly at this level, so this pipeline enables the ability to evaluate experiments for multiple parameters (e.g. different zone sizes) and develop real time dashboards for analysis. Furthermore, it includes an image registration step that removes scale and position variance between videos, allowing for perfectly aligned analysis not available in existing commercial or open source tools. 

Author: Andre Telfer (andretelfer@cmail.carleton.ca) 

## Installation
```python
pip install -U -q bapipe-keypoints-telfer
```

    Note: you may need to restart the kernel to use updated packages.


To install the local code 
```python
pip install --upgrade --no-deps --force-reinstall ..
```

## Dockerfiles
For convenience, we also provide dockerfiles to replicate our analysis environment

```bash
git clone git@github.com:A-Telfer/bapipe-keypoints.git
cd bapipe-keypoints
bash docker-run.sh
```

## Structure of Data
In order to use this pipeline, load a csv file with the following information
- subject id
- path to video
- path to mouse bodypart position files (produced from DeepLabCut or similar pose estimation software) 
- path to video landmarks (e.g. box corners) [optional]
- path to camera calibrations [optional]


```python
%%time
import pandas as pd
from pathlib import Path

PROJECT = Path("/home/jovyan/shared/shared/curated/fran/v2")

datafiles = pd.read_csv(PROJECT / 'datafiles.csv')
datafiles.head(3)
```

    CPU times: user 378 ms, sys: 1.03 s, total: 1.41 s
    Wall time: 210 ms

<div>

<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>id</th>
      <th>video</th>
      <th>mouse_labels</th>
      <th>landmark_labels</th>
      <th>camera_calibrations</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>m1</td>
      <td>videos/m1.mp4</td>
      <td>videos/mouse_labels/m1DLC_resnet50_agrpNov19sh...</td>
      <td>videos/landmark_labels/m1DLC_resnet50_agrp_lan...</td>
      <td>camera_calibrations.json</td>
    </tr>
    <tr>
      <th>1</th>
      <td>m2</td>
      <td>videos/m2.mp4</td>
      <td>videos/mouse_labels/m2DLC_resnet50_agrpNov19sh...</td>
      <td>videos/landmark_labels/m2DLC_resnet50_agrp_lan...</td>
      <td>camera_calibrations.json</td>
    </tr>
    <tr>
      <th>2</th>
      <td>m3</td>
      <td>videos/m3.mp4</td>
      <td>videos/mouse_labels/m3DLC_resnet50_agrpNov19sh...</td>
      <td>videos/landmark_labels/m3DLC_resnet50_agrp_lan...</td>
      <td>camera_calibrations.json</td>
    </tr>
  </tbody>
</table>
</div>



## Load Experiment
- Normalize videos
  - Register arena corners
  - Remove lens warping
  - Clip start time for when mouse is first visible
- Outlier correction 
  - Remove based on pairwise distances
  - Remove based on bodypart velocities
- Provide an api for common operations
  - Parallelized analysis to reduce run times by several times
  - Provides visibility for common features


```python
%%time 
import numpy as np
import bapipe

config = bapipe.AnalysisConfig(
    box_shape=(400, 300),            # size of the box in mm (or any other units)
    remove_lens_distortion=True,     # remove distortion caused by camera lens (requires a calibration file)
    use_box_reference=True,          # align all of the videos for the test arena
)

video_set = bapipe.VideoSet.load(datafiles, config, root_dir=PROJECT)
video_set
```

    100%|████████████████████████████████████████████████████████| 72/72 [00:09<00:00,  7.63it/s]


    CPU times: user 1.83 s, sys: 737 ms, total: 2.57 s
    Wall time: 10.1 s





<table><tr><td>Number of videos</td><td>72</td></tr><tr><td>Video sizes (W,H)</td><td>960x540</td></tr><tr><td>Total duration [s]</td><td>47837.6</td></tr><tr><td>Average duration [s]</td><td>664.41</td></tr></table>



## Compare original videos to corrected videos


```python
%%time 
import matplotlib.pyplot as plt

gs = plt.GridSpec(1, 100)
plt.figure(figsize=(16,10))

plt.subplot(gs[:52])
plt.title("Original")
override_config = {'use_box_reference': False, 'remove_lens_distortion': False}
plt.imshow(bapipe.create_video_grid(video_set, override_config=override_config))
plt.axis('off')

plt.subplot(gs[60:])
plt.title("Aligned")
plt.imshow(bapipe.create_video_grid(video_set))
plt.axis('off')
plt.show()
```


    
![png](docs/assets/output_9_0.png)
    


    CPU times: user 45.3 s, sys: 5.51 s, total: 50.9 s
    Wall time: 8.9 s


## Analysis Examples


```python
%%time
treatment_data = pd.read_csv(PROJECT / 'cohorts1&2.csv', index_col='animal')
treatment_data.head(3)
```

    CPU times: user 3.49 ms, sys: 0 ns, total: 3.49 ms
    Wall time: 2.65 ms





<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>injected_on</th>
      <th>injected_with</th>
      <th>amount_eaten</th>
      <th>treatment1</th>
      <th>treatment2</th>
      <th>cohort</th>
      <th>latency_to_approach</th>
      <th>time_in_corner</th>
      <th>time_eating</th>
      <th>sex</th>
    </tr>
    <tr>
      <th>animal</th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>m1</th>
      <td>2021-07-16</td>
      <td>saline/saline</td>
      <td>0.0</td>
      <td>saline</td>
      <td>saline</td>
      <td>1</td>
      <td>6.18</td>
      <td>245.17</td>
      <td>16.15</td>
      <td>male</td>
    </tr>
    <tr>
      <th>m2</th>
      <td>2021-07-15</td>
      <td>saline/ghrelin</td>
      <td>0.2</td>
      <td>saline</td>
      <td>ghrelin</td>
      <td>1</td>
      <td>22.97</td>
      <td>124.21</td>
      <td>35.81</td>
      <td>male</td>
    </tr>
    <tr>
      <th>m3</th>
      <td>2021-07-15</td>
      <td>mt2/ghrelin</td>
      <td>0.1</td>
      <td>mt2</td>
      <td>ghrelin</td>
      <td>1</td>
      <td>10.39</td>
      <td>130.09</td>
      <td>11.01</td>
      <td>male</td>
    </tr>
  </tbody>
</table>
</div>



### Example 1: Video Validation
    Annotate what's being scored over the videos


```python
%%time
from tqdm import tqdm
from IPython.display import Video

video = video_set[0]
with bapipe.VideoWriter(video, 'test.mp4') as writer:
    for i in tqdm(range(1000,1100)):
        frame = video.get_frame(i)
        bapipe.draw_dataframe_points(frame, video.mouse_df, i)
        writer.write(frame)

Video('test.mp4')
```

    100%|██████████████████████████████████████████████████████| 100/100 [00:04<00:00, 22.82it/s]

    CPU times: user 24.6 s, sys: 3.22 s, total: 27.8 s
    Wall time: 4.46 s


    





<video src="docs/assets/test.mp4" controls  >
      Your browser does not support the <code>video</code> element.
    </video>



### Example 2: Distance Travelled


```python
%%time
import seaborn as sns

def get_distance_travelled(video):
    # Average the bodypart positions of the mouse to get its centroid 
    centroid = video.mouse_df.groupby(level='coords', axis=1).mean()
    
    # Get the between-frame movement of the bodyparts
    deltas = centroid[['x', 'y']].diff().dropna()
    
    # Calculate the total distance travelled 
    return np.sum(np.linalg.norm(deltas.values, axis=1))

distances = pd.Series(
    video_set.apply(get_distance_travelled),
    index=video_set.index, 
    name='distance')

sns.barplot(data=treatment_data.join(distances), x='injected_with', y='distance')
plt.xlabel("Treatment Group")
plt.ylabel("Distance Travelled [mm]")
plt.title("Locomotivity: Distance Travelled")
plt.show()
```

    100%|███████████████████████████████████████████████████████| 72/72 [00:00<00:00, 216.58it/s]



    
![png](docs/assets/output_15_1.png)
    


    CPU times: user 439 ms, sys: 977 ms, total: 1.42 s
    Wall time: 660 ms


### Example 2: Heatmaps
Show what zones the mice are spending their time

#### Find position density


```python
%%time
from tqdm import tqdm 
from scipy.stats.kde import gaussian_kde

groups = treatment_data.groupby(['treatment1', 'treatment2'])
w,h = config.box_shape

result = {}
for idx, group in tqdm(groups):
    group_videos = [video_set[video_set.index.index(idx)] for idx in group.index]
    
    # Stack the mouse-location dataframes for each mouse in this treatment group
    group_df = pd.concat([video.mouse_df for video in group_videos], axis=0).dropna()
    
    # Get the centroid of the mouse by averaging the bodypart positions in each frame
    centroid = group_df.groupby(level='coords', axis=1).mean()[['x', 'y']]
    data = centroid[['y', 'x']].values.T
    
    # Get the density of time spent in location (down sampled for 1 frame every 100)
    k = gaussian_kde(data[:,::100], )
    mgrid = np.mgrid[:h, :w]
    z = k(mgrid.reshape(2, -1))
    result['/'.join(idx)] = z
```

    <timed exec>:2: DeprecationWarning: Please use `gaussian_kde` from the `scipy.stats` namespace, the `scipy.stats.kde` namespace is deprecated.
    100%|██████████████████████████████████████████████████████████| 4/4 [00:11<00:00,  2.86s/it]

    CPU times: user 12.3 s, sys: 4.22 s, total: 16.5 s
    Wall time: 11.4 s


    


#### Create contour plots


```python
%%time
import matplotlib.pyplot as plt

CONTOUR_LEVELS = 20

video = video_set[0]
frame = video.get_frame(1000)

plt.figure(figsize=(20, 5))
gs = plt.GridSpec(1, 5)

plt.title("Box Reference")
plt.subplot(gs[0])
plt.imshow(frame)

for idx, (gname, z) in enumerate(result.items()):
    plt.subplot(gs[idx+1])
    plt.title(gname)
    plt.imshow(frame) # plotting a frame sets up the matplotlib axis correctly
    plt.imshow(z.reshape(mgrid.shape[1:]))
    plt.contourf(z.reshape(mgrid.shape[1:]), cmap='seismic', alpha=1, levels=CONTOUR_LEVELS)
```

    CPU times: user 589 ms, sys: 50 ms, total: 639 ms
    Wall time: 178 ms



    
![png](docs/assets/output_20_1.png)
    


### Example 3: Zone based analysis
Zones on can be drawn once in tools like napari, or automatically plotted

If the videos have been normalized, zones can be drawn once and applied to all videos


```python
%%time
def get_center_zone(video):
    w,h = video_set[0].config.box_shape
    cx, cy = w//2, h//2
    s = 50
    return plt.Polygon([
        [cx-s, cy-s],
        [cx-s, cy+s],
        [cx+s, cy+s],
        [cx+s, cy-s]
    ], alpha=0.5, label='Center zone')
    
def time_in_zone(video):
    center_zone = get_center_zone(video)
    centroid = video.mouse_df.groupby(level='coords', axis=1).mean()[['x', 'y']].values
    return np.sum(center_zone.contains_points(centroid)) / video.fps


data = pd.Series(
    video_set.apply(time_in_zone),
    index=video_set.index, 
    name='time_in_center_zone')

plt.figure(figsize=(15, 5))
gs = plt.GridSpec(1, 2)

plt.subplot(gs[0])
v = video_set[0]
plt.imshow(v.get_frame(900))
plt.gca().add_patch(get_center_zone(v))

plt.subplot(gs[1])
sns.barplot(data=treatment_data.join(data), x='injected_with', y='time_in_center_zone')
plt.xlabel("Treatment Group")
plt.ylabel("Time in Zone [s]")
plt.title("Time in Zone")
```

    100%|███████████████████████████████████████████████████████| 72/72 [00:00<00:00, 185.93it/s]


    CPU times: user 583 ms, sys: 309 ms, total: 892 ms
    Wall time: 682 ms





    Text(0.5, 1.0, 'Time in Zone')




    
![png](docs/assets/output_22_3.png)
    

