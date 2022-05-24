#!/usr/bin/env python
# coding: utf-8

# # Demo of Behaviour Analysis for Keypoint Data
# This notebook demonstrates a pipeline for turning keypoint data gathered from deep learning models into scientifically useful data and visualizations. It includes an image registration step that removes scale and position variance between videos, allowing for perfectly aligned analysis not available in existing commercial or open source tools. 
# 
# Author: Andre Telfer (andretelfer@cmail.carleton.ca) - currently looking to collaborate on behavioral analysis pipelines.
# 
# ## Background
# Advances in Deep Learning have driven a wave of pose-estimation tools which extract information from animals and their surroundings ([DeepLabCut](http://www.mackenziemathislab.org/deeplabcut), [OpenPose](https://github.com/CMU-Perceptual-Computing-Lab/openpose), [SLEAP](https://sleap.ai/)). These models are trained to extract keypoint data (x, y coordinates) for specified bodyparts or objects in the environment.
# 

# ## Installation
# 

# In[1]:


pip install -U -q bapipe-keypoints-telfer


# To install the local code 
# ```python
# pip install --upgrade --no-deps --force-reinstall ..
# ```

# ## Structure of Data
# In order to use this pipeline, load a csv file with the following information
# - subject id
# - path to video
# - path to mouse bodypart position files (produced from DeepLabCut or similar pose estimation software) 
# - path to video landmarks (e.g. box corners) [optional]
# - path to camera calibrations [optional]

# In[2]:


get_ipython().run_cell_magic('time', '', 'import pandas as pd\nfrom pathlib import Path\n\nPROJECT = Path("/home/jovyan/shared/shared/curated/fran/v2")\n\ndatafiles = pd.read_csv(PROJECT / \'datafiles.csv\')\ndatafiles.head(3)')


# ## Load Experiment
# - Normalize videos
#   - Register arena corners
#   - Remove lens warping
#   - Clip start time for when mouse is first visible
# - Outlier correction 
#   - Remove based on pairwise distances
#   - Remove based on bodypart velocities
# - Provide an api for common operations
#   - Parallelized analysis to reduce run times by several times
#   - Provides visibility for common features

# In[3]:


get_ipython().run_cell_magic('time', '', 'import numpy as np\nimport bapipe\n\nconfig = bapipe.AnalysisConfig(\n    box_shape=(400, 300),            # size of the box in mm (or any other units)\n    remove_lens_distortion=True,     # remove distortion caused by camera lens (requires a calibration file)\n    use_box_reference=True,          # align all of the videos for the test arena\n)\n\nvideo_set = bapipe.VideoSet.load(datafiles, config, root_dir=PROJECT)\nvideo_set')


# ## Compare original videos to corrected videos

# In[4]:


get_ipython().run_cell_magic('time', '', 'import matplotlib.pyplot as plt\n\ngs = plt.GridSpec(1, 100)\nplt.figure(figsize=(16,10))\n\nplt.subplot(gs[:52])\nplt.title("Original")\noverride_config = {\'use_box_reference\': False, \'remove_lens_distortion\': False}\nplt.imshow(bapipe.create_video_grid(video_set, override_config=override_config))\nplt.axis(\'off\')\n\nplt.subplot(gs[60:])\nplt.title("Aligned")\nplt.imshow(bapipe.create_video_grid(video_set))\nplt.axis(\'off\')\nplt.show()')


# ## Analysis Examples

# In[5]:


get_ipython().run_cell_magic('time', '', "treatment_data = pd.read_csv(PROJECT / 'cohorts1&2.csv', index_col='animal')\ntreatment_data.head(3)")


# ### Example 1: Video Validation
#     Annotate what's being scored over the videos

# In[6]:


get_ipython().run_cell_magic('time', '', "from tqdm import tqdm\nfrom IPython.display import Video\n\nvideo = video_set[0]\nwith bapipe.VideoWriter(video, 'test.mp4') as writer:\n    for i in tqdm(range(1000,1100)):\n        frame = video.get_frame(i)\n        bapipe.draw_dataframe_points(frame, video.mouse_df, i)\n        writer.write(frame)\n\nVideo('test.mp4')")


# ### Example 2: Distance Travelled

# In[7]:


get_ipython().run_cell_magic('time', '', 'import seaborn as sns\n\ndef get_distance_travelled(video):\n    # Average the bodypart positions of the mouse to get its centroid \n    centroid = video.mouse_df.groupby(level=\'coords\', axis=1).mean()\n    \n    # Get the between-frame movement of the bodyparts\n    deltas = centroid[[\'x\', \'y\']].diff().dropna()\n    \n    # Calculate the total distance travelled \n    return np.sum(np.linalg.norm(deltas.values, axis=1))\n\ndistances = pd.Series(\n    video_set.apply(get_distance_travelled),\n    index=video_set.index, \n    name=\'distance\')\n\nsns.barplot(data=treatment_data.join(distances), x=\'injected_with\', y=\'distance\')\nplt.xlabel("Treatment Group")\nplt.ylabel("Distance Travelled [mm]")\nplt.title("Locomotivity: Distance Travelled")\nplt.show()')


# ### Example 2: Heatmaps
# Show what zones the mice are spending their time

# #### Find position density

# In[8]:


get_ipython().run_cell_magic('time', '', "from tqdm import tqdm \nfrom scipy.stats.kde import gaussian_kde\n\ngroups = treatment_data.groupby(['treatment1', 'treatment2'])\nw,h = config.box_shape\n\nresult = {}\nfor idx, group in tqdm(groups):\n    group_videos = [video_set[video_set.index.index(idx)] for idx in group.index]\n    \n    # Stack the mouse-location dataframes for each mouse in this treatment group\n    group_df = pd.concat([video.mouse_df for video in group_videos], axis=0).dropna()\n    \n    # Get the centroid of the mouse by averaging the bodypart positions in each frame\n    centroid = group_df.groupby(level='coords', axis=1).mean()[['x', 'y']]\n    data = centroid[['y', 'x']].values.T\n    \n    # Get the density of time spent in location (down sampled for 1 frame every 100)\n    k = gaussian_kde(data[:,::100], )\n    mgrid = np.mgrid[:h, :w]\n    z = k(mgrid.reshape(2, -1))\n    result['/'.join(idx)] = z")


# #### Create contour plots

# In[9]:


get_ipython().run_cell_magic('time', '', 'import matplotlib.pyplot as plt\n\nCONTOUR_LEVELS = 20\n\nvideo = video_set[0]\nframe = video.get_frame(1000)\n\nplt.figure(figsize=(20, 5))\ngs = plt.GridSpec(1, 5)\n\nplt.title("Box Reference")\nplt.subplot(gs[0])\nplt.imshow(frame)\n\nfor idx, (gname, z) in enumerate(result.items()):\n    plt.subplot(gs[idx+1])\n    plt.title(gname)\n    plt.imshow(frame) # plotting a frame sets up the matplotlib axis correctly\n    plt.imshow(z.reshape(mgrid.shape[1:]))\n    plt.contourf(z.reshape(mgrid.shape[1:]), cmap=\'seismic\', alpha=1, levels=CONTOUR_LEVELS)')


# ### Example 3: Zone based analysis
# Zones on can be drawn once in tools like napari, or automatically plotted
# 
# If the videos have been normalized, zones can be drawn once and applied to all videos

# In[10]:


get_ipython().run_cell_magic('time', '', 'def get_center_zone(video):\n    w,h = video_set[0].config.box_shape\n    cx, cy = w//2, h//2\n    s = 50\n    return plt.Polygon([\n        [cx-s, cy-s],\n        [cx-s, cy+s],\n        [cx+s, cy+s],\n        [cx+s, cy-s]\n    ], alpha=0.5, label=\'Center zone\')\n    \ndef time_in_zone(video):\n    center_zone = get_center_zone(video)\n    centroid = video.mouse_df.groupby(level=\'coords\', axis=1).mean()[[\'x\', \'y\']].values\n    return np.sum(center_zone.contains_points(centroid)) / video.fps\n\n\ndata = pd.Series(\n    video_set.apply(time_in_zone),\n    index=video_set.index, \n    name=\'time_in_center_zone\')\n\nplt.figure(figsize=(15, 5))\ngs = plt.GridSpec(1, 2)\n\nplt.subplot(gs[0])\nv = video_set[0]\nplt.imshow(v.get_frame(900))\nplt.gca().add_patch(get_center_zone(v))\n\nplt.subplot(gs[1])\nsns.barplot(data=treatment_data.join(data), x=\'injected_with\', y=\'time_in_center_zone\')\nplt.xlabel("Treatment Group")\nplt.ylabel("Time in Zone [s]")\nplt.title("Time in Zone")')

