"""The planner must re-ask the AI with concrete errors, and never silently accept a bad plan."""

import json

import pytest

from smartpost.services import planner


def ai_answer(bounds):
    parts = [
        {"start": f"{a // 60}:{a % 60:02d}", "end": f"{b // 60}:{b % 60:02d}", "title_line1": "A",
         "title_line2": "B", "title_vi": "", "caption_en": "c", "caption_vi": ""}
        for a, b in zip(bounds, bounds[1:])
    ]
    return json.dumps({"parts": parts, "hashtags": ["#a", "#b", "#c", "#d", "#e"]})


def test_bad_plan_is_sent_back_with_errors(monkeypatch):
    calls = []
    answers = [ai_answer([0, 50, 130, 210, 290]), ai_answer([0, 80, 160, 240, 320])]

    def fake_call(contents, timeout):
        calls.append(json.loads(json.dumps(contents)))
        return answers[len(calls) - 1]

    monkeypatch.setattr(planner, "_call", fake_call)
    result = planner.make_plan("t", 600, "0:00 hi", [], "https://youtu.be/x")
    assert result["warnings"] == []
    assert result["parts"][0]["end"] == 80
    # Second request carries the model's first answer and the exact rule that failed
    feedback = calls[1][-1]["parts"][0]["text"]
    assert "Part 1" in feedback and "50 giây" in feedback


def test_plan_still_wrong_after_retries_is_returned_with_warnings(monkeypatch):
    monkeypatch.setattr(planner, "_call", lambda contents, timeout: ai_answer([0, 50, 130, 210, 290]))
    result = planner.make_plan("t", 600, "0:00 hi", [], "https://youtu.be/x")
    assert result["warnings"], "user must see that the plan breaks the rules"


def test_video_too_short_fails_before_calling_ai(monkeypatch):
    monkeypatch.setattr(planner, "_call", lambda *a: pytest.fail("AI should not be called"))
    with pytest.raises(planner.PlanError):
        planner.make_plan("t", 200, "0:00 hi", [], "https://youtu.be/x")


def test_no_subtitles_sends_the_youtube_link(monkeypatch):
    seen = {}

    def fake_call(contents, timeout):
        seen["parts"] = contents[0]["parts"]
        return ai_answer([0, 80, 160, 240, 320])

    monkeypatch.setattr(planner, "_call", fake_call)
    result = planner.make_plan("t", 600, None, [], "https://www.youtube.com/watch?v=abc")
    assert seen["parts"][0]["fileData"]["fileUri"] == "https://www.youtube.com/watch?v=abc"
    assert result["source"] == "youtube"
