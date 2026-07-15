"""In-app how-to page (black & white)."""
import streamlit as st


def render_guide(on_back):
    if st.button("← Back", key="guide_back"):
        on_back()
    st.title("Guide")
    st.caption("How to prepare your data, load an experiment, and read each analysis.")
    st.markdown(
        """
#### 1. Prepare your data
Put your **manifest CSV** (`bapipe_datafiles.csv` or `datafiles.csv`) in one
folder together with the videos and DeepLabCut `.h5` tracking files it lists.
Optionally add a **metadata CSV** (`id` + group columns such as treatment / sex /
cohort) to compare groups.

#### 2. Start an analysis
Press **Start / New analysis** and follow the three steps: choose the data
folder, tick the animals to load, and confirm the analysis settings (the
defaults are auto-detected and fine for most experiments).

#### 3. Read the analyses
- **Overview** — experiment summary and an original-vs-aligned alignment check.
- **Distance** — total locomotion per group.
- **Heatmaps** — where each group spent its time.
- **Time in zone** — seconds spent in an adjustable centre zone.
- **Validation video** — the tracked keypoints drawn on a real clip.
- **Results** — per-animal metrics and a group summary (mean ± SEM).

#### 4. Your records
When a load finishes, its results are **saved automatically to your private
records** — visible only to you. Raw videos are never stored, only the computed
numbers. Open **My Records** any time to revisit or download past analyses.
        """
    )
