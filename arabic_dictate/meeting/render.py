"""عرض نتائج التفريغ: نص، SRT، JSON، Markdown + إحصاءات."""
from __future__ import annotations

import json
import re

from .pipeline import MeetingResult

_ARABIC_RANGE = re.compile(r"[\u0600-\u06FF]")
_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def speaker_label(template: str, number: int) -> str:
    """يطبّق قالب العنوان ويحوّل الأرقام إلى عربية إن كان القالب عربياً."""
    rendered = str(number)
    if _ARABIC_RANGE.search(template):
        rendered = rendered.translate(_ARABIC_DIGITS)
    return template.format(n=rendered)


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render_txt(result: MeetingResult, template: str) -> str:
    lines: list[str] = []
    for segment in result.segments:
        label = speaker_label(template, segment.speaker + 1)
        lines.append(f"[{format_timestamp(segment.start)}] {label}:")
        lines.append(segment.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_srt(result: MeetingResult, template: str) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(result.segments, 1):
        label = speaker_label(template, segment.speaker + 1)
        blocks.append(str(index))
        blocks.append(f"{_srt_timestamp(segment.start)} --> {_srt_timestamp(segment.end)}")
        blocks.append(f"{label}: {segment.text}")
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def render_markdown(result: MeetingResult, template: str) -> str:
    lines: list[str] = [f"# تفريغ الاجتماع ({format_timestamp(result.duration)})", ""]
    for segment in result.segments:
        label = speaker_label(template, segment.speaker + 1)
        lines.append(f"## {label} — [{format_timestamp(segment.start)}]")
        lines.append("")
        lines.append(segment.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(result: MeetingResult, template: str) -> str:
    payload = {
        "duration": round(result.duration, 2),
        "engine": result.engine,
        "elapsed": round(result.elapsed, 2),
        "speaker_count": result.speaker_count(),
        "speakers": [
            {"number": number + 1, "label": speaker_label(template, number + 1), "seconds": round(seconds, 2)}
            for number, seconds in result.speaker_seconds().items()
        ],
        "segments": [
            {
                "speaker": segment.speaker + 1,
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text,
            }
            for segment in result.segments
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def print_result(result: MeetingResult, template: str) -> None:
    """عرض التفريغ الملوّن + الإحصاءات في الطرفية."""
    colors = ("\033[36m", "\033[33m", "\033[35m", "\033[32m", "\033[34m", "\033[31m")

    for segment in result.segments:
        label = speaker_label(template, segment.speaker + 1)
        color = colors[segment.speaker % len(colors)]
        print(f"\n\033[1m[{format_timestamp(segment.start)}] {color}{label}\033[0m")
        print(segment.text)

    print("\n— الإحصاءات —")
    summary = (
        f"المدة: {format_timestamp(result.duration)} · المتحدثون: {result.speaker_count()}"
        f" · زمن المعالجة: {result.elapsed:.1f}s · المحرّك: {result.engine}"
    )
    print(summary)
    for number, seconds in result.speaker_seconds().items():
        percent = (seconds / result.duration * 100) if result.duration else 0
        label = speaker_label(template, number + 1)
        print(f"  {label}: {format_timestamp(seconds)} ({percent:.0f}%)")
