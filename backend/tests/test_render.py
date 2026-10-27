"""Rendered clips must be TikTok-ready: 9:16, exact cut length, title that fits the frame."""

import shutil
import subprocess

import pytest

from smartpost.services import render
from smartpost.services.fetch import probe_file

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")


@pytest.fixture
def landscape_video(tmp_path):
    path = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest",
         "-c:v", "libx264", "-c:a", "aac", str(path)],
        check=True,
    )
    return path


def test_render_makes_vertical_clip_of_the_cut_length(landscape_video, tmp_path):
    out = render.render_clip(
        landscape_video, tmp_path / "out" / "clip.mp4", 1.0, 4.0,
        "Hello world", "Second line", (640, 360),
        render.ColorNudge(0.02, 1.03, 0.95), render.DEFAULT_STYLE,
    )
    w, h, duration = probe_file(out)
    assert (w, h) == (1080, 1920)
    assert abs(duration - 3.0) < 0.15
    assert not (tmp_path / "out" / "clip.part.mp4").exists()


def test_long_title_shrinks_to_fit_width():
    long_line = "X" * 40
    size = render.fit_font_size([long_line, "short"], 84)
    assert size < 84
    assert size * render.GLYPH_WIDTH * len(long_line) <= render.W - 2 * render.SIDE_MARGIN


def test_title_sits_above_landscape_video_and_near_top_for_vertical():
    # 16:9 source: the video band starts at y=656, title must end above it
    assert render.title_bottom_y(render.foreground_height(1920, 1080)) < 656
    # 9:16 source fills the frame: title goes near the top instead of off-screen
    assert render.title_bottom_y(render.foreground_height(1080, 1920)) == 420


def test_random_nudge_stays_within_jitter():
    import random

    style = render.DEFAULT_STYLE
    for seed in range(50):
        n = render.random_nudge(style, random.Random(seed))
        assert abs(n.brightness) <= style["brightness_jitter"]
        assert abs(n.contrast - 1) <= style["contrast_jitter"] + 1e-9
        assert abs(n.saturation - 1) <= style["saturation_jitter"] + 1e-9
