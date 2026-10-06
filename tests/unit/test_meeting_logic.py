"""اختبارات منطق الاجتماعات (بلا نماذج أو صوت حقيقي)."""
from __future__ import annotations

from arabic_dictate.meeting.diarize import Turn
from arabic_dictate.meeting.pipeline import MeetingResult, Segment, merge_turns
from arabic_dictate.meeting.render import (
    format_timestamp,
    render_json,
    render_srt,
    render_txt,
    speaker_label,
)


def test_merge_turns_joins_close_same_speaker_turns():
    turns = [Turn(0.0, 2.0, 0), Turn(2.2, 4.0, 0), Turn(4.1, 6.0, 1)]
    merged = merge_turns(turns, max_secs=30, gap_secs=0.5)
    assert len(merged) == 2
    assert merged[0].speaker == 0
    assert merged[0].start == 0.0
    assert merged[0].end == 4.0
    assert merged[1].speaker == 1


def test_merge_turns_keeps_distant_same_speaker_separate():
    turns = [Turn(0.0, 1.0, 0), Turn(5.0, 6.0, 0)]
    merged = merge_turns(turns, max_secs=30, gap_secs=0.5)
    assert len(merged) == 2


def test_merge_turns_splits_long_segments():
    turns = [Turn(0.0, 75.0, 0)]
    merged = merge_turns(turns, max_secs=30, gap_secs=0.5)
    assert len(merged) == 3
    assert all(segment.end - segment.start <= 30 for segment in merged)
    assert merged[0].start == 0.0
    assert merged[-1].end == 75.0


def test_speaker_label_uses_arabic_digits_for_arabic_templates():
    assert speaker_label("المتحدث {n}", 2) == "المتحدث ٢"
    assert speaker_label("Speaker {n}", 3) == "Speaker 3"


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(3725.9) == "01:02:05"


def test_render_txt_srt_json():
    result = MeetingResult(
        segments=[Segment(0, 0.0, 3.0, "أهلاً بالجميع"), Segment(1, 3.5, 5.0, "حياك الله")],
        duration=5.0,
        engine="whisper-local",
        elapsed=1.0,
    )
    txt = render_txt(result, "المتحدث {n}")
    assert "المتحدث ١" in txt
    assert "أهلاً بالجميع" in txt

    srt = render_srt(result, "المتحدث {n}")
    assert "00:00:00,000 --> 00:00:03,000" in srt
    assert srt.startswith("1\n")

    payload = render_json(result, "المتحدث {n}")
    assert '"speaker": 1' in payload
    assert '"speaker_count": 2' in payload
    assert '"duration": 5.0' in payload
