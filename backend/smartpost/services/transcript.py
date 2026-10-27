"""Turn YouTube json3 subtitles into cues and a timestamped transcript for the AI."""

import json
from dataclasses import dataclass
from pathlib import Path

SENTENCE_END = (".", "?", "!", '"', "\u201d")
MAX_LINE_SECONDS = 8.0


@dataclass
class Cue:
    start: float
    end: float
    text: str


def parse_json3(path: Path) -> list[Cue]:
    events = json.loads(Path(path).read_text(encoding="utf-8")).get("events", [])
    raw: list[tuple[float, float, str]] = []
    for ev in events:
        text = "".join(s.get("utf8", "") for s in ev.get("segs") or [])
        text = " ".join(text.split())
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000
        raw.append((start, start + ev.get("dDurationMs", 0) / 1000, text))
    raw.sort(key=lambda r: r[0])
    cues = []
    for i, (start, end, text) in enumerate(raw):
        # Auto captions roll: each event stays on screen while the next one starts.
        if i + 1 < len(raw):
            end = min(end, raw[i + 1][0])
        cues.append(Cue(start, max(end, start), text))
    return cues


def group_lines(cues: list[Cue]) -> list[Cue]:
    """Merge cues into sentence-like lines (auto captions have no punctuation, so cap by time)."""
    lines: list[Cue] = []
    cur: Cue | None = None
    for cue in cues:
        if cur is None:
            cur = Cue(cue.start, cue.end, cue.text)
        else:
            cur = Cue(cur.start, cue.end, f"{cur.text} {cue.text}")
        if cur.text.endswith(SENTENCE_END) or cur.end - cur.start >= MAX_LINE_SECONDS:
            lines.append(cur)
            cur = None
    if cur is not None:
        lines.append(cur)
    return lines


def fmt_ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_ts(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).strip().split(":")
    if not parts or len(parts) > 3:
        raise ValueError(f"bad timestamp: {value!r}")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


def to_text(lines: list[Cue]) -> str:
    return "\n".join(f"{fmt_ts(c.start)} {c.text}" for c in lines)
