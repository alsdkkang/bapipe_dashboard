"""Consolidated chart palette: one control for every chart + per-group overrides.

Presets come from seaborn/matplotlib (Greyscale is the publication-neutral default
via `theme.group_greys`). A per-group override maps a group label to a hex colour
that wins over the preset for that group. State lives in session_state so charts
re-render live.
"""
import seaborn as sns
import streamlit as st

import theme

BAR_PRESETS = ["Grayscale", "colorblind", "Set2", "tab10", "Dark2", "Paired"]
HEAT_PRESETS = ["Greys", "viridis", "magma", "Blues", "Reds", "coolwarm"]


def bar_preset() -> str:
    return st.session_state.get("palette_bar", "Grayscale")


def heat_preset() -> str:
    return st.session_state.get("palette_heat", "Greys")


def _overrides() -> dict:
    return st.session_state.get("palette_overrides", {})


def colors_for(labels, preset=None, overrides=None):
    """Return ``(colors, hatches)`` aligned to ``labels`` (group order).

    Greyscale yields the grey ramp + hatches (print-safe); any other preset yields
    that seaborn palette with empty hatches. A per-group override replaces exactly
    that label's colour (and clears its hatch).
    """
    labels = [str(x) for x in labels]
    n = len(labels)
    preset = preset or bar_preset()
    overrides = _overrides() if overrides is None else overrides
    if preset == "Grayscale":
        base = theme.group_greys(n)
    else:
        base = [(c, "") for c in sns.color_palette(preset, n).as_hex()]
    colors, hatches = [], []
    for lbl, (color, hatch) in zip(labels, base):
        if overrides.get(lbl):
            colors.append(overrides[lbl])
            hatches.append("")
        else:
            colors.append(color)
            hatches.append(hatch)
    return colors, hatches


def controls(group_labels):
    """Render the single "Chart colors" control (call from the analysis nav)."""
    with st.expander("Chart colors"):
        st.selectbox("Bar palette", BAR_PRESETS, key="palette_bar")
        st.selectbox("Heatmap colors", HEAT_PRESETS, key="palette_heat")
        labels = [str(x) for x in (group_labels or [])]
        if labels:
            custom = st.checkbox("Custom colour per group", key="palette_custom")
            if custom:
                ov = dict(_overrides())
                for lbl in labels:
                    ov[lbl] = st.color_picker(lbl, value=ov.get(lbl) or "#4F46E5",
                                              key=f"palette_ov_{lbl}")
                st.session_state["palette_overrides"] = ov
            else:
                st.session_state["palette_overrides"] = {}
