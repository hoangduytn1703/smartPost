"""The transcript is what the AI uses to pick timestamps: wrong times = wrong cuts."""

import json

from smartpost.services.fetch import extract_youtube_url, subtitle_candidates
from smartpost.services.transcript import fmt_ts, group_lines, parse_json3, parse_ts, to_text


def write(tmp_path, events):
    path = tmp_path / "subs.en.json3"
    path.write_text(json.dumps({"events": events}), encoding="utf-8")
    return path


def test_auto_captions_roll_over_and_newline_events_are_dropped(tmp_path):
    # YouTube auto captions keep each line on screen while the next starts, and add "\n" events
    path = write(tmp_path, [
        {"tStartMs": 0, "dDurationMs": 476000},
        {"tStartMs": 3080, "dDurationMs": 5160, "segs": [{"utf8": "you"}, {"utf8": " were"}]},
        {"tStartMs": 6389, "dDurationMs": 1851, "aAppend": 1, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 6399, "dDurationMs": 5280, "segs": [{"utf8": "it was"}]},
    ])
    cues = parse_json3(path)
    assert [c.text for c in cues] == ["you were", "it was"]
    assert cues[0].end == 6.399  # clipped to the next line, not 8.24


def test_lines_group_by_sentence_or_time():
    from smartpost.services.transcript import Cue

    cues = [Cue(0, 2, "Hello there."), Cue(2, 4, "no"), Cue(4, 7, "punctuation"), Cue(7, 10, "here")]
    lines = group_lines(cues)
    assert lines[0].text == "Hello there."
    assert lines[1].start == 2 and lines[1].text == "no punctuation here"
    assert to_text(lines).splitlines()[1] == "0:02 no punctuation here"


def test_timestamps_round_trip():
    assert parse_ts("1:23") == 83
    assert parse_ts("1:02:03") == 3723
    assert parse_ts("0:05.5") == 5.5
    assert fmt_ts(3723) == "1:02:03"
    assert fmt_ts(83.9) == "1:23"


def test_foreign_video_uses_original_captions_not_translated_english():
    # Translated auto `en` of a Vietnamese video is what YouTube answers with HTTP 429
    info = {
        "language": "vi",
        "subtitles": {},
        "automatic_captions": {"en": [{"ext": "json3"}], "vi-orig": [{"ext": "json3"}], "vi": [{}]},
    }
    assert subtitle_candidates(info)[0] == ("vi-orig", True)
    assert ("en", True) not in subtitle_candidates(info)


def test_english_video_prefers_human_subtitles():
    info = {
        "language": "en",
        "subtitles": {"en-GB": [{}]},
        "automatic_captions": {"en-orig": [{}], "en": [{}]},
    }
    assert subtitle_candidates(info)[0] == ("en-GB", False)


def test_extract_youtube_url_from_pasted_text():
    # The Share button copies extra text; shorts and youtu.be links must work too
    assert extract_youtube_url("watch https://youtu.be/h6fcK_fRYaI?si=x") == (
        "https://www.youtube.com/watch?v=h6fcK_fRYaI"
    )
    assert extract_youtube_url("https://www.youtube.com/shorts/h6fcK_fRYaI") == (
        "https://www.youtube.com/watch?v=h6fcK_fRYaI"
    )
    assert extract_youtube_url("https://www.youtube.com/watch?app=desktop&v=h6fcK_fRYaI&t=3") == (
        "https://www.youtube.com/watch?v=h6fcK_fRYaI"
    )
    assert extract_youtube_url("not a link") is None
