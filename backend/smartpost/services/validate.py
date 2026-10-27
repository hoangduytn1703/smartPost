"""Check the AI cut plan against the MASTER PROMPT rules. Pure code, no AI."""

import re

from .transcript import Cue, fmt_ts, parse_ts

PART_COUNT = 4
PART_MIN, PART_MAX = 70.0, 90.0
TOTAL_MIN, TOTAL_MAX = 280.0, 360.0
SNAP_WINDOW = 2.0
HASHTAG_COUNT = 5


def fix_caption(text: str) -> str:
    """The prompt forbids ? ! & in English captions; fix them instead of asking the AI again."""
    text = text.replace("&", "and")
    text = re.sub(r"[?!]+", ".", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+\.", ".", text)
    return " ".join(text.split())


def fix_hashtags(tags: list) -> list[str]:
    out: list[str] = []
    for tag in tags or []:
        word = re.sub(r"[^\w]", "", str(tag), flags=re.UNICODE)
        if word and f"#{word}" not in out:
            out.append(f"#{word}")
    return out[:HASHTAG_COUNT]


def check(data: dict, video_duration: float) -> tuple[list[dict], list[str], list[str]]:
    """Return (parts with float start/end, hashtags, errors). Errors are in the prompt's language."""
    errors: list[str] = []
    raw_parts = data.get("parts") or []
    if len(raw_parts) != PART_COUNT:
        errors.append(f"Cần đúng {PART_COUNT} part, bạn trả {len(raw_parts)}.")
    parts: list[dict] = []
    for i, p in enumerate(raw_parts, 1):
        try:
            start, end = parse_ts(p.get("start", "")), parse_ts(p.get("end", ""))
        except ValueError:
            errors.append(f"Part {i}: mốc thời gian không đọc được ({p.get('start')!r} - {p.get('end')!r}).")
            continue
        parts.append({
            "start": start,
            "end": end,
            "title_line1": str(p.get("title_line1", "")).strip(),
            "title_line2": str(p.get("title_line2", "")).strip(),
            "title_vi": str(p.get("title_vi", "")).strip(),
            "caption_en": fix_caption(str(p.get("caption_en", ""))),
            "caption_vi": str(p.get("caption_vi", "")).strip(),
        })
    errors += check_times(parts, video_duration)
    hashtags = fix_hashtags(data.get("hashtags") or [])
    if len(hashtags) < HASHTAG_COUNT:
        errors.append(f"Cần {HASHTAG_COUNT} hashtag, mới có {len(hashtags)}.")
    return parts, hashtags, errors


def check_times(parts: list[dict], video_duration: float) -> list[str]:
    errors: list[str] = []
    for i, p in enumerate(parts, 1):
        length = p["end"] - p["start"]
        span = f"{fmt_ts(p['start'])} - {fmt_ts(p['end'])}"
        if p["start"] < 0 or (video_duration and p["end"] > video_duration + 1):
            errors.append(f"Part {i} ({span}) nằm ngoài video (dài {fmt_ts(video_duration)}).")
        if not PART_MIN <= length <= PART_MAX:
            errors.append(
                f"Part {i} ({span}) dài {length:.0f} giây, phải từ {PART_MIN:.0f} đến {PART_MAX:.0f} giây."
            )
    for i in range(1, len(parts)):
        prev, cur = parts[i - 1], parts[i]
        if abs(cur["start"] - prev["end"]) > 0.01:
            kind = "khoảng trống" if cur["start"] > prev["end"] else "chồng lấn"
            errors.append(
                f"Part {i} kết thúc {fmt_ts(prev['end'])} nhưng Part {i + 1} bắt đầu {fmt_ts(cur['start'])} ({kind})."
            )
    if parts:
        total = parts[-1]["end"] - parts[0]["start"]
        if not TOTAL_MIN <= total <= TOTAL_MAX:
            errors.append(
                f"Tổng thời lượng {total:.0f} giây, phải từ {TOTAL_MIN:.0f} đến {TOTAL_MAX:.0f} giây."
            )
    return errors


def snap_to_cues(parts: list[dict], cues: list[Cue]) -> list[dict]:
    """Move each cut to the nearest subtitle start (within SNAP_WINDOW) so we never cut mid-word.

    Transcript lines only carry whole seconds; the real sentence may start at 1:23.6. A boundary
    is moved only if both neighbouring parts stay inside the length rules.
    """
    if not parts or not cues:
        return parts
    starts = [c.start for c in cues]
    bounds = [p["start"] for p in parts] + [parts[-1]["end"]]
    for i, b in enumerate(bounds):
        nearest = min(starts, key=lambda s: abs(s - b))
        if abs(nearest - b) > SNAP_WINDOW:
            continue
        trial = bounds[:i] + [nearest] + bounds[i + 1:]
        lengths = [trial[k + 1] - trial[k] for k in range(len(parts))]
        touched = [k for k in (i - 1, i) if 0 <= k < len(parts)]
        if all(PART_MIN <= lengths[k] <= PART_MAX for k in touched):
            bounds = trial
    out = []
    for k, p in enumerate(parts):
        out.append({**p, "start": round(bounds[k], 2), "end": round(bounds[k + 1], 2)})
    return out
