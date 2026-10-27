"""The MASTER PROMPT rules decide whether a cut plan can be posted as-is.

If these checks are too loose, clips that are too short/long or that skip/repeat
footage reach TikTok; if they are too strict, good AI plans get re-asked for nothing.
"""

from smartpost.services import validate
from smartpost.services.transcript import Cue


def plan(bounds, **extra):
    parts = [
        {
            "start": f"{int(a // 60)}:{int(a % 60):02d}",
            "end": f"{int(b // 60)}:{int(b % 60):02d}",
            "title_line1": "A",
            "title_line2": "B",
            "caption_en": "Caption",
        }
        for a, b in zip(bounds, bounds[1:])
    ]
    return {"parts": parts, "hashtags": ["#a", "#b", "#c", "#d", "#e"], **extra}


def test_valid_plan_has_no_errors():
    parts, tags, errors = validate.check(plan([60, 140, 220, 300, 380]), 600)
    assert errors == []
    assert [p["start"] for p in parts] == [60, 140, 220, 300]
    assert len(tags) == 5


def test_part_too_short_is_rejected():
    # 60 s part: shorter than the 70 s minimum, would be a weak TikTok clip
    _, _, errors = validate.check(plan([0, 60, 140, 220, 300]), 600)
    assert any("Part 1" in e and "60 giây" in e for e in errors)


def test_gap_and_overlap_are_rejected():
    # A gap loses footage, an overlap repeats it in the next part
    data = plan([0, 80, 160, 240, 320])
    data["parts"][1]["start"] = "1:25"
    data["parts"][2]["start"] = "2:35"
    _, _, errors = validate.check(data, 600)
    assert any("khoảng trống" in e for e in errors)
    assert any("chồng lấn" in e for e in errors)


def test_wrong_part_count_breaks_total_length():
    # 4 parts of 70-90 s always total 280-360 s, so the total rule only trips on a wrong count
    _, _, errors = validate.check(plan([0, 70, 140, 210, 280]), 600)
    assert errors == []
    _, _, errors = validate.check(plan([0, 70, 140, 210]), 600)
    assert any("Cần đúng 4 part" in e for e in errors)
    assert any("Tổng thời lượng" in e for e in errors)


def test_part_beyond_video_end():
    _, _, errors = validate.check(plan([0, 80, 160, 240, 320]), 300)
    assert any("nằm ngoài video" in e for e in errors)


def test_caption_forbidden_characters_are_fixed_not_rejected():
    # The prompt forbids ? ! & in captions; code fixes it so we do not pay for another AI round
    data = plan([0, 80, 160, 240, 320])
    data["parts"][0]["caption_en"] = "Why does this happen?! Science & you"
    parts, _, errors = validate.check(data, 600)
    assert errors == []
    assert parts[0]["caption_en"] == "Why does this happen. Science and you"


def test_hashtags_are_normalised_and_capped():
    assert validate.fix_hashtags(["space", "#Black Hole", "#space", "a", "b", "c", "d"]) == [
        "#space", "#BlackHole", "#a", "#b", "#c",
    ]


def test_snap_moves_cut_to_sentence_start():
    # Transcript lines carry whole seconds; the real sentence starts at 80.6 s
    parts = [{"start": 0.0, "end": 80.0}, {"start": 80.0, "end": 160.0}]
    cues = [Cue(0.0, 5, "a"), Cue(80.6, 85, "b"), Cue(159.2, 162, "c")]
    out = validate.snap_to_cues(parts, cues)
    assert out[0]["end"] == out[1]["start"] == 80.6
    assert out[1]["end"] == 159.2


def test_snap_never_breaks_length_rule():
    # Moving the cut to 71.5 would make part 2 90.5 s long (over the max): keep 72
    parts = [{"start": 0.0, "end": 72.0}, {"start": 72.0, "end": 162.0}]
    cues = [Cue(71.5, 75, "a")]
    out = validate.snap_to_cues(parts, cues)
    assert out[0]["end"] == 72.0
