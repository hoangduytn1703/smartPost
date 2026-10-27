"""Replace the CapCut step: cut, 9:16 with blurred background, colour nudge, 2-line title."""

import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

W, H = 1080, 1920
SIDE_MARGIN = 60
# Rough width of an uppercase bold Arial glyph relative to the font size.
GLYPH_WIDTH = 0.55

DEFAULT_STYLE = {
    "font": "Arial",
    "font_size": 84,
    "line1_color": "#FFFFFF",
    "line2_color": "#FFD400",
    "outline": 6,
    "uppercase": True,
    # Each render picks a random value within +/- these amounts ("a bit brighter, a bit darker")
    "brightness_jitter": 0.04,
    "contrast_jitter": 0.06,
    "saturation_jitter": 0.10,
}


class RenderError(Exception):
    pass


@dataclass
class ColorNudge:
    brightness: float
    contrast: float
    saturation: float


def random_nudge(style: dict, rng: random.Random | None = None) -> ColorNudge:
    rng = rng or random.Random()
    return ColorNudge(
        brightness=round(rng.uniform(-1, 1) * style["brightness_jitter"], 3),
        contrast=round(1 + rng.uniform(-1, 1) * style["contrast_jitter"], 3),
        saturation=round(1 + rng.uniform(-1, 1) * style["saturation_jitter"], 3),
    )


def foreground_height(src_w: int, src_h: int) -> int:
    if not src_w or not src_h:
        return H
    return min(H, round(W * src_h / src_w / 2) * 2)


def title_bottom_y(fg_h: int) -> int:
    """Baseline for the title: just above the video, or near the top when the video fills the frame."""
    top = (H - fg_h) // 2
    return top - 40 if top > 360 else 420


def fit_font_size(lines: list[str], base: int) -> int:
    longest = max((len(l) for l in lines if l), default=1)
    fit = int((W - 2 * SIDE_MARGIN) / (GLYPH_WIDTH * longest))
    return max(40, min(base, fit))


def _ass_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(line1: str, line2: str, duration: float, fg_h: int, style: dict) -> str:
    if style.get("uppercase"):
        line1, line2 = line1.upper(), line2.upper()
    size = fit_font_size([line1, line2], int(style["font_size"]))
    y = title_bottom_y(fg_h)
    end = f"{int(duration // 3600)}:{int(duration % 3600 // 60):02d}:{duration % 60:05.2f}"
    text = "\\N".join(
        f"{{\\c{_ass_color(color)}}}{_ass_escape(line)}"
        for line, color in ((line1, style["line1_color"]), (line2, style["line2_color"]))
        if line.strip()
    )
    return (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Title,{style['font']},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,{style['outline']},2,2,{SIDE_MARGIN},{SIDE_MARGIN},0,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,{end},Title,,0,0,0,,{{\\an2\\pos({W // 2},{y})}}{text}\n"
    )


def filter_graph(nudge: ColorNudge, ass_name: str) -> str:
    return (
        "[0:v]split=2[bgsrc][fgsrc];"
        # Blur a small copy (cheap), then scale it back up to fill 9:16
        f"[bgsrc]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,"
        f"crop={W // 4}:{H // 4},boxblur=12:2,scale={W}:{H},setsar=1[bg];"
        f"[fgsrc]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"eq=brightness={nudge.brightness}:contrast={nudge.contrast}:saturation={nudge.saturation},"
        f"ass={ass_name},format=yuv420p[v]"
    )


def render_clip(
    source: Path,
    out_path: Path,
    start: float,
    end: float,
    line1: str,
    line2: str,
    src_size: tuple[int, int],
    nudge: ColorNudge,
    style: dict,
) -> Path:
    duration = end - start
    if duration <= 0.5:
        raise RenderError("Đoạn cắt quá ngắn")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ass_name = out_path.stem + ".ass"
    (out_path.parent / ass_name).write_text(
        build_ass(line1, line2, duration, foreground_height(*src_size), style), encoding="utf-8"
    )
    tmp = out_path.with_suffix(".part.mp4")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
        "-filter_complex", filter_graph(nudge, ass_name),
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-movflags", "+faststart", tmp.name,
    ]
    # cwd = output folder so the ass= filter gets a plain file name (no path escaping)
    proc = subprocess.run(cmd, cwd=out_path.parent, capture_output=True, text=True)
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RenderError("ffmpeg lỗi: " + proc.stderr.strip()[-500:])
    tmp.replace(out_path)
    return out_path
