# Paper
## A post-Deep Learning pipeline for improving analysis reproducibility in the Open Field Test
```{warning}
Draft for BioRxiv paper
```
```{attention}
Anonymize and publish data with paper necessary to get these results?
- can update to cite research data is from when published (Frances & Vern)
```
```{attention}
Reproduce all graphs using current pipeline version and publish
```
## Abstract
- Rising interest in deep learning methods
- Growing pains for labs: many struggle to turn this new wealth of data into publishable results
- Show how to turn the outputs of keypoint-based deep learning tools such as DeepLabCut into common behaviour measures for the Open Field Test
  - Many of these measurements are useful for other behavioural paradigms
- These results are comparable to manual analysis, including catching errors in manual analysis.
- Introduce two useful features that are uncommon in current behaviour analysis software
  1. Registration of arena in order to account for differences between videos: a common issue for many labs using shared experimental spaces.
  2. Real-time analysis dashboard for behaviour analysis parameters: something that is not possible for many of the slower existing systems.
- Use pipeline to demonstrate a reproducibility risk in traditional behavioral analysis. 
  - Example of zone-based behaviour measurements, e.g. the potential impact of arbitrary or standardized definitions for the zones. 

## Introduction
### Behaviour Analysis and the Open Field Test
- Open Field Test is a behavioral paradigm working for mouse models
- Involves placing mice in an uncovered box
- Traditionally has been used for testing anxiolytics drugs
  - Like other behavioural paradigms (e.g. elevated plus maze), mice tend to avoid open areas where predators are able to catch them
  - Time spent in corners vs open areas is used as a measure of anxiety-like behaviour
- The open field test has been a popular test to adapt to a wide number of other experiment designs
  - Locomotivity (e.g. depressive-like behaviours)
  - Food-related motivation by placing food in center area (e.g. Ghrelin)
  - Gait/stride (e.g. Parkinson's and Huntington's models)
  - ...

### Keypoint analysis and motivation for pipeline
```{attention}
Demonstrative figure with DLC-labelled points
```
- The field of Deep learning (a subfield of Machine Learning and Artificial Intelligence) has met rapid growth in recent years and success in dealing with many challenging problems. 
- This growth has diffused across industry and research, with the life sciences gaining several new open-source deep-learning tools for behaviour analysis currently capable of outperforming commercial systems {cite}`sturman_deep_2020`
- Some of these tools can be trained to track keypoints on the animal's body, such as nose, ears, hands, and feet {cite}`mathis_deeplabcut_2018,pereira_sleap_2020`
- The `{x, y}` coordinate data produced these models are quite flexible to later pipelines compared to other approaches directly performing classification on images or videos.
- `{x,y}` coordinates are useful for a range of behavioural measurements, including
  - time in zones/near objects
  - behaviour/action classification
  - identity tracking
- While performing operations on these coordinate outputs are trivial for some, many labs coming from more traditional methods are facing growing pains
- As such, we believe it would be valuable for presenting a post deep-learning pipeline for turning coordinate data into some common and meaningful measurements and publishable figures

### Deep Learning and Classic Analysis
- Full deep learning analysis are becoming more common
- These open many doors 
  - Behavioural classification (grooming behaviours)
  - Facial expressions
  - Unsupervised behavioural deviations
- Classic analysis gives us a more direct comparison to past research and known correlations to changes in the brain
  - For example, it is valuable to know when using mouse models of Parkinson's that stride can be a meaningful feature associated with degeneration in the basal ganglia.
- Ability to ask specific questions: does X affect time in center area?
  - Deep learning models are well suited to working out complicated rules such as where is X (which can have a variety of poses and appearances), or what action is X performing (where there may be many ways to perform the action)
    - More simply, deep learning is suited to discovering new features and working out complicated rules which we would struggle to define, in order to reach a desired outcome. 
    - Using deep learning where classical methods suffice only serves to reduce transparency of how the models work
    ```{note}
    Currently there is a lot of work to increase reproducibility, but I think it remains a fair comment
    ```
  - Complimentary to classic analysis, deep-learning can extract basic information for rule-based systems to use
- Deep Learning is an exciting tool for behaviour analysis that has the potential to identify behaviours at a level previously unavailable to us.
- Does not replace the value of classic analysis for targetted questions

### Noise
- The ability to reproduce results is core to the validation of theories
- Beneath reproducibility lies noise 
- The life sciences have an abundance of noise, especially behaivoural studies where variations in different areas such as environment, strain, and handling can all affect outcome
- Noise can also come up during analysis
- For example, one researcher may define a behavior slightly differently from another researcher (e.g. especially for challinging behaviours such as eating where a mouse may take a bite of food elsewhere to nibble on it which may look similar to sniffing or grooming)
- The impacts of noise are also often undervalued by experts (TODO: reference to Noise by Kahneman et al.)
- Computer analysis is well suited to removing much of this noise, however it does not eliminate it
- Machine Bias: 
  - Machines have their own bias
  - While using a single form of bias has less noise, it can also be incorrect.
  - For example, traditional machine learning models that many behavioural analysis programs still use are often poor at handling noisy environments
  - The machine-position of mice can jump as they interact with their environment which is different from what the model is trained on
  - A solution for this has been discussed in deep learning by readding back noise. For example, training many models to perform the same task, or randomly enabling/disabling neural circuits in deep learning models.
  - So eliminating noise at the cost of greater risk to bias is not desirable
- Human input/decisions also add noise to computer analysis.


```{figure} assets/compare-original-to-corrected.png
On the left, the original videos can be seen with clear differences between many of them. On the right we can see the corrected videos using our registration steps.
```
- In the Open Field Test, many popular automated tools for performing behaviour analysis require the redrawing of zones when the videos are not aligned
  - These variation between videos are common, as animal facilities 
  - Labs sharing these spaces are often required to set up their equipment each session, leading to some variation even when trying to mimic the setup as closely as possible.
  - This type of noise is not desirable, and we show it may in fact be affected by camera angle (e.g. we cannot fully account for changes in camera perspective, which therefore affect the shape of our zones)
  - We can remove this perspective-noise and therefore eliminate the need to redraw zones
  - This also allows to explore the impact of how slight differences in zone size can affect reproducibility


```{admonition} Recreate simulated manual analysis
Originally I performed an automated analysis using average size of manually drawn boxes for each user. 

I found that different users would have different results if they had analyzed the whole experiment
```

```{admonition} Intra-rater noise
Users draw zone and manually score area, how well do their reviews correlate to automatic analysis performed using the zone
- perhaps use a sample of videos and get them to exactly record when the mouse is in the zone or not to see where scores are unaligned? 
```

```{admonition} Defining Zones before/after

How well do researchers record what they scored?
- e.g. motorcycle countersteering example, experts often don't know the exact rules they use to perform a task

Get someone to define a zone before and score videos according to zone, vs defining the zone after.
- how well do the scores correlate with automatic analysis based on the zone size
```
## Methods
### Extracted features and speed
While other models focus on more complicated behaviour analysis, we focus more on core features that can be extracted from coordinate data without the need for traditional models. 

One thing that is special about our approach is that our image registration steps mean that we report our measurements in real units and not pixels. Our approach is more accurate than a simple pixel-unit conversion due to correcting for lens warping and perspective which can greatly skew measurements in some cases (moving on near side of box being given twice the weight as moving on the far side). 
- locomotivity
  - distance travelled
  - top 5%, bottom 5%, and median speeds
- time in zones (simulating noise in zones)
- latency to first approach (e.g. first time entering a zone)
- representative figures (provided by DLC, no need for our code)
- heatmaps

One note is that time in zones should not necessarily be used for a measurement of behaviour (e.g. time spent eating). We found a relatively low correlation between proximity-based automatic scoring and human based analysis for these features. This reflects the classic problem of measuring A and hoping for B, measuring complex behaviours should be done through further behaviour classification models.  

```{figure} assets/fran-heatmaps.png
---
name: fran-heatmaps-figure
---
Heatmap produced using our pipeline. By accounting for shifts in camera perspective between video, we could aggregate time in areas for each group.
```

### Datasets used
```{attention} 
Write up in more detail, include image examples for each video
```
- Two open field test experiments
  - n=80, and n>100

### Removing Outliers
```{attention}
Provide example images of removed outliers to show motivation better
... and to confirm motivation. I get a bit caught up in preemptive issues sometimes that turn out to be virtually irrelevant. This may be one of them
- Ahamd's SIT experiment will probably be the best demonstration
```
- may be negligible in good quality videos for certain measurments such as time in zone
- can create a jump in readings for measurements such as distance, especially in low quality videos or where the mouse can become occluded
  - particularly an issue in videos where humans struggle to provide labeled exampels for the model
- low confidence in DLC models is not a true probability
  - it reports the models internal confidence, different models will report different confidences for a bodypart being in a same location
  - occasionally very confident in a wrong point
  - many of these can be corrected by retraining a model, however even after several iterations errors can still remain. Furthermore, the randomness involved in training deep learning models means that new errors may occur as old ones are eliminated (e.g. focusing more of your dataset on one type of erroneous outlier may cause the model to undervalue its errors on other types of outliers you had already reduced)
  - removing outliers can therefore be a necessary sanity check for the model
- Detecting outliers
  - bodypart distances, movement distances, etc
  - normalization 
    - SVD
    - relative coordinates vs global coordinates, e.g. do we care if the mouse is in an outlier area (perhaps climbing something, or in an outlier position
  - Deciding outlier thresholds: standard deviation vs other methods, e.g. 
    - isolation forests
      ```{admonition} Untried 
      naive bayes?
      ```
- Correcting points: 
  - Leaving empty points can make later analysis difficult
  - Filling a point with previous values can be very wrong 
  - Interpolations are perhaps the best solution, but also can be noticably very wrong in videos

```{admonition} In Progress (include?)
- Autoencoders [in progress]: detecting and correcting outliers
  - bottlenecking forces the model to decide what information is important and what isnt
  - bodyparts can only be so far away, and in certain configurations. The model can discard some information about the location of bodyparts if it learns the skeletal structure of the animal.
  - very rare situations can still be undervalued
    - perhaps fixed by increasing training weight of these examples (boosting?)
    - however greater risk of learning errors
```

### Correcting for Perspectives
```{attention} 
Insert useful illustration that shows process (existing one is screen-shotted from google-slide presentations)
```
```{attention}
Obligatory math section to pretend I wasn't just calling functions I didn't understand (which is exactly what I did since I could easily just see if it worked or not, but it would be good to understand it now)
```

- Photogrammetry techniques can be used 
  - Intrinsic calibration: requires only a video of a checkerboard
  - Extrinsic calibration: manually register points on the box in each frame
- Correcting for perspective reduces noise in zone drawing

### Validation
```{attention}
Recreate manual-automatic correlations for full datasets with manual scores (re:Frances)
```
- High correlation with manual analysis 
- Stochastic gradient descent to match parameters to humans
  - Ahmad's SIT experiment: zone size produced values too small for some videos and too large for others. Highlighting intra-rater variability in manual scores.
- Catching outliers in the manual approach (reviewed only easy to check features like latency to first approach)
Unfortunately some of these notes are difficult to recover with laptop lost

### Exploring impact of zone definitions
```{attention}
Illustration of different zones
```
- using the pipeiline videos, it's trivial to programmatically vary zone size and automatically apply across the normalized videos

## Conclusion
### Value of Pipeline
- Most simply: we have a simple pipeline for extracting core features for behaviour analysis
- Add features that are useful to experienced developers, such as a multi-processing based api.
- Removal of outliers
- Optional ability to perform image registration and remove lens warping
- Validation
  - Comparison to manual methods (caught outliers in manual methods)
  - Correcting for perspective changes/translation to real units

### Impact of Zone Shape on Results
```{figure} assets/significance-events.png
p-values between groups change on orders of magnitude as center area size changes
```

```{admonition} Rerun for both datasets
Data may have only been from cohort1 of Fran's data - likely less noisy with all cohorts
- Verns data on the other hand appears quite noisy with all cohorts
```

```{figure} assets/vern-heatmap-obfuscated-groups.png
---
name: vern-heatmap
---
Ideal data would have a more diffuse heatmap, however here we see some behavioural variation in where the mice spend their time.
```

- Including/excluding zones here 

## Discussion
### Error from Operational Definitions 
- Current behaviour analysis tools reflect popular opinions that analysis is robust to noise
  - Intuitively, growing the center area 1cm shouldn't reflect a great change in neural state
  - Practically, not the case. We do see big changes in our statistical results.
  - Though it would have been virtually impossible to explore the impact of zone size on measurements in the past, it is trivial using automatated analysis from a standardized perspective
  - Our approach simplifies this even further by removing the time constraint which commercial 

### Standardization may help, but is not a solution
- Argument against standardization
  - Being over specific also may also affect translatability. e.g. if we achieve reproducibility for a treatment in one mouse model of Parkinson's but another.
    - TODO: insert the paper mentioning increasing variability in behavioural experiments
  - There is noise in the data, and current experiment sizes often cannot smooth this out (Evidence in heatmaps hotspots) {numref}`Fig {number} <vern-heatmap>`

## Bibliography
```{bibliography}
:filter: docname in docnames
```

### Questions
- Does adding noise to zones corners improve reproducibility (which can be defined as a smoothing of the man-whitney U curves)
  - Smoothing of the distribution can be measure by smaller gradients (e.g. sum gradients)
- Which corners have greater variation from perfect squares in the manual zone drawing