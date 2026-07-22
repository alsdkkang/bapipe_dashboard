import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import palette  # noqa: E402
import theme  # noqa: E402


def test_grayscale_parity_with_group_greys():
    colors, hatches = palette.colors_for(["a", "b", "c"], preset="Grayscale", overrides={})
    greys = theme.group_greys(3)
    assert colors == [g[0] for g in greys]
    assert hatches == [g[1] for g in greys]


def test_colored_preset_returns_n_hex():
    colors, hatches = palette.colors_for(["a", "b"], preset="Set2", overrides={})
    assert len(colors) == 2
    assert all(c.startswith("#") for c in colors)
    assert hatches == ["", ""]


def test_override_replaces_that_group_only():
    colors, hatches = palette.colors_for(
        ["a", "b"], preset="Set2", overrides={"a": "#ff0000"})
    assert colors[0] == "#ff0000"
    assert colors[1] != "#ff0000"
    assert hatches[0] == ""
