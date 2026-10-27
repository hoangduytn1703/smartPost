"""Ask Gemini (MASTER PROMPT) where to cut, then verify the answer with code."""

import json
import logging
import time
from pathlib import Path

import httpx

from .. import config
from . import validate
from .transcript import Cue, fmt_ts

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "master_prompt.md"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FIX_ATTEMPTS = 2

_STR = {"type": "STRING"}
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "parts": {
            "type": "ARRAY",
            "minItems": validate.PART_COUNT,
            "maxItems": validate.PART_COUNT,
            "items": {
                "type": "OBJECT",
                "properties": {k: _STR for k in (
                    "start", "end", "title_line1", "title_line2", "title_vi", "caption_en", "caption_vi"
                )},
                "required": ["start", "end", "title_line1", "title_line2", "title_vi", "caption_en", "caption_vi"],
            },
        },
        "hashtags": {"type": "ARRAY", "items": _STR},
    },
    "required": ["parts", "hashtags"],
}


class PlanError(Exception):
    pass


def _call(contents: list[dict], timeout: float) -> str:
    keys = config.gemini_keys()
    if not keys:
        raise PlanError("Chưa có Gemini API key (GEMINI_API_KEYS trong .env)")
    body = {
        "contents": contents,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "temperature": 0.7,
        },
    }
    url = API.format(model=config.GEMINI_MODEL)
    last = ""
    for attempt in range(len(keys) * 2):
        key = keys[attempt % len(keys)]
        try:
            resp = httpx.post(url, params={"key": key}, json=body, timeout=timeout)
        except httpx.HTTPError as exc:
            last = f"lỗi mạng: {exc}"
            time.sleep(3)
            continue
        if resp.status_code == 200:
            cand = (resp.json().get("candidates") or [{}])[0]
            text = "".join(
                p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought")
            )
            if text.strip():
                return text
            last = f"Gemini trả rỗng (finishReason={cand.get('finishReason')})"
            continue
        last = f"Gemini HTTP {resp.status_code}: {resp.text[:300]}"
        if resp.status_code in (429, 500, 503):
            time.sleep(2 if resp.status_code == 429 else 5)
            continue
        break
    raise PlanError(last)


def _parse(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(f"Gemini trả JSON hỏng: {exc}")


def make_plan(
    title: str,
    duration: float,
    transcript: str | None,
    cues: list[Cue],
    youtube_url: str,
) -> dict:
    """Return {"parts": [...], "hashtags": [...], "warnings": [...], "source": ...}.

    With a transcript the AI reads text (fast, cheap, exact timestamps). Without one Gemini
    watches the YouTube video itself.
    """
    if duration and duration < validate.TOTAL_MIN:
        raise PlanError(
            f"Video chỉ dài {fmt_ts(duration)}, không đủ cho 4 part (tối thiểu {fmt_ts(validate.TOTAL_MIN)})."
        )
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    if transcript:
        parts = [{"text": f"{prompt}\n\n---\n\nOriginal Video Title: {title}\n\nTranscript:\n{transcript}"}]
        source, timeout = "transcript", 240
    else:
        parts = [
            {"fileData": {"fileUri": youtube_url, "mimeType": "video/*"}},
            {"text": f"{prompt}\n\n---\n\nOriginal Video Title: {title}\n\n"
                     "Video này không có phụ đề: hãy tự nghe video để lấy timestamp."},
        ]
        source, timeout = "youtube", 600
    contents = [{"role": "user", "parts": parts}]

    errors: list[str] = []
    for attempt in range(FIX_ATTEMPTS + 1):
        raw = _call(contents, timeout)
        data = _parse(raw)
        result_parts, hashtags, errors = validate.check(data, duration)
        if not errors:
            return {
                "parts": validate.snap_to_cues(result_parts, cues),
                "hashtags": hashtags,
                "warnings": [],
                "source": source,
            }
        log.info("plan attempt %d rejected: %s", attempt + 1, errors)
        contents += [
            {"role": "model", "parts": [{"text": raw}]},
            {"role": "user", "parts": [{"text": (
                "Kết quả chưa đúng luật:\n- " + "\n- ".join(errors)
                + "\nHãy tính lại cẩn thận và trả lại TOÀN BỘ JSON đã sửa."
            )}]},
        ]
    if len(result_parts) != validate.PART_COUNT:
        raise PlanError("AI vẫn sai sau khi sửa: " + " ".join(errors))
    # Usable but off-spec: let the user fix the times on the review screen.
    return {"parts": result_parts, "hashtags": hashtags, "warnings": errors, "source": source}
