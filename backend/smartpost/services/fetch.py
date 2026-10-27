"""yt-dlp wrappers: metadata, English subtitles, source video."""

import json
import re
import subprocess
from pathlib import Path

from .. import config

BASE = ["yt-dlp", "--js-runtimes", "node", "--no-playlist", "--no-warnings"]
VIDEO_FORMAT = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b"


YOUTUBE_URL = re.compile(
    r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


class FetchError(Exception):
    pass


def extract_youtube_url(text: str) -> str | None:
    """Accept a pasted line that contains a YouTube link; return a clean watch URL."""
    m = YOUTUBE_URL.search(text or "")
    return f"https://www.youtube.com/watch?v={m.group(1)}" if m else None


def _run(args: list[str], cwd: Path | None = None, timeout: int = 120) -> str:
    cmd = BASE + config.YTDLP_ARGS + args
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise FetchError("yt-dlp hết thời gian chờ")
    if proc.returncode != 0:
        lines = [l for l in proc.stderr.splitlines() if "ERROR" in l] or proc.stderr.splitlines()[-3:]
        raise FetchError("yt-dlp lỗi: " + " | ".join(lines)[:500])
    return proc.stdout


def probe(url: str) -> dict:
    return json.loads(_run(["-J", url]))


def subtitle_candidates(info: dict) -> list[tuple[str, bool]]:
    """Tracks to try, best first. Each item is (language code, is_auto).

    YouTube answers HTTP 429 for *translated* automatic captions (the `en` track of a
    Vietnamese video), while the original track (`vi-orig`) downloads fine. So the
    original language comes before any translated auto track.
    """
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    lang = (info.get("language") or "").split("-")[0]
    out: list[tuple[str, bool]] = []

    def add(key: str, is_auto: bool) -> None:
        pool = auto if is_auto else manual
        if key and key in pool and (key, is_auto) not in out:
            out.append((key, is_auto))

    for key in sorted((k for k in manual if k == "en" or k.startswith("en-")), key=lambda k: (k != "en", k)):
        add(key, False)
    if lang:
        add(f"{lang}-orig", True)
        if lang != "en":
            add(lang, True)
    else:
        for key in sorted(k for k in auto if str(k).endswith("-orig")):
            add(key, True)
    add("en-orig", True)
    # Auto `en` of a non-English video is a translation and gets rate-limited.
    if not lang or lang == "en":
        add("en", True)
    return out


def pick_subtitle(info: dict) -> tuple[str, bool] | None:
    found = subtitle_candidates(info)
    return found[0] if found else None


def download_subtitle(url: str, lang: str, auto: bool, out_dir: Path) -> Path:
    flag = "--write-auto-subs" if auto else "--write-subs"
    _run(["--skip-download", flag, "--sub-langs", lang, "--sub-format", "json3", "-o", "subs", url], cwd=out_dir)
    path = out_dir / f"subs.{lang}.json3"
    if not path.exists():
        raise FetchError(f"không tải được phụ đề {lang}")
    return path


def download_video(url: str, out_dir: Path) -> Path:
    _run(
        ["-f", VIDEO_FORMAT, "--merge-output-format", "mp4", "-o", "source.%(ext)s", url],
        cwd=out_dir,
        timeout=3600,
    )
    path = out_dir / "source.mp4"
    if not path.exists():
        raise FetchError("tải video xong nhưng không thấy source.mp4")
    return path


def probe_file(path: Path) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    stream = (data.get("streams") or [{}])[0]
    return int(stream.get("width", 0)), int(stream.get("height", 0)), float(data["format"]["duration"])
