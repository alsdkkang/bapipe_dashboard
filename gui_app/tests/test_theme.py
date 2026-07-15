import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import theme  # noqa: E402


def test_group_greys_count_and_shape():
    greys = theme.group_greys(4)
    assert len(greys) == 4
    for color, hatch in greys:
        assert color.startswith("#")
        assert isinstance(hatch, str)


def test_group_greys_cycles_beyond_ramp():
    # more groups than base greys still returns n distinct (color, hatch) pairs
    greys = theme.group_greys(9)
    assert len(greys) == 9
    assert len(set(greys)) == 9


def test_css_is_black_and_white_only():
    css = theme.CSS.lower()
    # no blue accent from the reference palette
    assert "#2f6df0" not in css
    assert "111" in css  # primary black present


def test_card_and_stat_tile_render_content():
    assert "My Title" in theme.card("My Title", "<p>x</p>")
    assert "Animals" in theme.stat_tile("Animals", "12")
