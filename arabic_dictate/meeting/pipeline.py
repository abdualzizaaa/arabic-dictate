"""خط أنابيب تفريغ الاجتماع:

  تحويل إلى 16kHz أحادي ← تمييز متحدثين ← مقاطع متجانسة المتحدث
  ← تفريغ كل مقطع بالمحرّك المختار ← دمج ← نتيجة مع إحصاءات.

لماذا «مقاطع متجانسة المتحدث»؟ لأن محرّكات التحويل الحالية تُنتج نصاً بلا
توقيتات موثوقة؛ ببناء مقاطع لا تتجاوز تغيّر المتحدث نبني كل نص على متحدث واحد
ونحصل على عناوين صحيحة دون أي محاذنة كلمات.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ..engines import EngineError, build
from ..textfilters import looks_like_hallucination
from .diarize import Turn, diarize
from .errors import MeetingError

MIN_SEGMENT_SECS = 0.2


@dataclass
class Segment:
    speaker: int
    start: float
    end: float
    text: str = ""


@dataclass
class MeetingResult:
    segments: list[Segment]
    duration: float
    engine: str
    elapsed: float
    segments_dir: pathlib.Path | None = None

    def speaker_count(self) -> int:
        return len({segment.speaker for segment in self.segments})

    def speaker_seconds(self) -> dict[int, float]:
        totals: dict[int, float] = {}
        for segment in self.segments:
            totals[segment.speaker] = totals.get(segment.speaker, 0.0) + (segment.end - segment.start)
        return dict(sorted(totals.items()))


def ensure_wav_16k(path: pathlib.Path) -> tuple[pathlib.Path, bool]:
    """يعيد (ملف wav بمعدل 16kHz أحادي، هل هو ملف مؤقت نُنظّفه لاحقاً)."""
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wav:
                if wav.getframerate() == 16000 and wav.getnchannels() == 1 and wav.getsampwidth() == 2:
                    return path, False
        except (wave.Error, EOFError, OSError):
            pass
    if shutil.which("ffmpeg") is None:
        raise MeetingError("يلزم ffmpeg لتحويل صيغ الصوت — ثبّته: sudo apt install ffmpeg")
    handle, tmp_name = tempfile.mkstemp(prefix="arabic-meeting-", suffix=".wav")
    import os

    os.close(handle)
    tmp = pathlib.Path(tmp_name)
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(tmp)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise MeetingError(f"تعذّر تحويل الملف عبر ffmpeg: {proc.stderr.strip()[:200]}")
    return tmp, True


def read_wav(path: pathlib.Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    return np.frombuffer(frames, dtype=np.int16), rate


def write_wav(path: pathlib.Path, samples: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.astype(np.int16).tobytes())


def merge_turns(turns: list[Turn], *, max_secs: float = 30.0, gap_secs: float = 0.5) -> list[Segment]:
    """يدمج مقاطع نفس المتحدث المتقاربة ويقسّم الطويل منها."""
    merged: list[Segment] = []
    for turn in sorted(turns, key=lambda item: item.start):
        if (
            merged
            and merged[-1].speaker == turn.speaker
            and turn.start - merged[-1].end <= gap_secs
        ):
            merged[-1].end = max(merged[-1].end, turn.end)
        else:
            merged.append(Segment(speaker=turn.speaker, start=turn.start, end=turn.end))

    output: list[Segment] = []
    for segment in merged:
        duration = segment.end - segment.start
        if duration <= max_secs:
            output.append(segment)
            continue
        parts = int(np.ceil(duration / max_secs))
        step = duration / parts
        for index in range(parts):
            output.append(
                Segment(
                    speaker=segment.speaker,
                    start=segment.start + index * step,
                    end=segment.start + (index + 1) * step,
                )
            )
    return output


def _coalesce(segments: list[Segment]) -> list[Segment]:
    """يدمج المقاطع المتجاورة لنفس المتحدث بعد التفريغ (نص متصل بلا تكرار عناوين)."""
    output: list[Segment] = []
    for segment in segments:
        if output and output[-1].speaker == segment.speaker:
            output[-1].end = segment.end
            output[-1].text = f"{output[-1].text} {segment.text}".strip()
        else:
            output.append(
                Segment(speaker=segment.speaker, start=segment.start, end=segment.end, text=segment.text)
            )
    return output


def transcribe_meeting(
    path: str | pathlib.Path,
    *,
    config: dict,
    engine_name: str | None = None,
    language: str | None = None,
    speakers: int | None = None,
    threshold: float | None = None,
    max_segment_secs: float | None = None,
    merge_gap_secs: float | None = None,
    keep_segments: bool | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> MeetingResult:
    meeting_cfg = dict(config.get("meeting") or {})
    engine_name = engine_name or meeting_cfg.get("engine") or config.get("engine")
    language = language or config.get("language", "ar")
    speakers = int(speakers if speakers is not None else meeting_cfg.get("speakers", 0) or 0)
    threshold = float(threshold if threshold is not None else meeting_cfg.get("clustering_threshold", 0.7))
    max_secs = float(max_segment_secs if max_segment_secs is not None else meeting_cfg.get("max_segment_secs", 30))
    gap = float(merge_gap_secs if merge_gap_secs is not None else meeting_cfg.get("merge_gap_secs", 0.5))
    keep = bool(keep_segments if keep_segments is not None else meeting_cfg.get("keep_segments", False))
    embedding = str(meeting_cfg.get("embedding") or "eres2net")

    source = pathlib.Path(path).expanduser()
    if not source.exists():
        raise MeetingError(f"الملف غير موجود: {source}")

    started = time.time()
    wav_path, is_temp = ensure_wav_16k(source)
    segments_dir = pathlib.Path(tempfile.mkdtemp(prefix="arabic-meeting-segments-"))
    try:
        samples, rate = read_wav(wav_path)
        duration = len(samples) / float(rate)
        if duration < 1.0:
            raise MeetingError("التسجيل قصير جداً — لا يمكن تمييز متحدثين")

        if on_progress:
            on_progress("diarize", 0, 1)
        float_samples = samples.astype(np.float32) / 32768.0

        def diarize_progress(done: int, total: int) -> None:
            if on_progress:
                on_progress("diarize", done, total)

        turns = diarize(
            float_samples,
            rate,
            speakers=speakers,
            threshold=threshold,
            embedding=embedding,
            progress=diarize_progress,
        )
        if not turns:
            raise MeetingError("لم يُعثر على كلام في التسجيل")

        pending = merge_turns(turns, max_secs=max_secs, gap_secs=gap)
        engine = build(engine_name, config)
        ok, reason = engine.available()
        if not ok:
            raise MeetingError(f"محرّك التحويل غير متاح: {reason}")

        total = len(pending)
        for index, segment in enumerate(pending, 1):
            if on_progress:
                on_progress("transcribe", index - 1, total)
            clip = samples[int(segment.start * rate): int(segment.end * rate)]
            if clip.size < rate * MIN_SEGMENT_SECS:
                segment.text = ""
                continue
            segment_wav = segments_dir / f"seg-{index:05d}.wav"
            write_wav(segment_wav, clip, rate)
            try:
                text = engine.transcribe(str(segment_wav), language).strip()
            except EngineError as exc:
                raise MeetingError(f"فشل التحويل في المقطع {index}/{total}: {exc}") from exc
            segment.text = "" if looks_like_hallucination(text) else text
        if on_progress:
            on_progress("transcribe", total, total)

        segments = _coalesce([segment for segment in pending if segment.text.strip()])
        return MeetingResult(
            segments=segments,
            duration=duration,
            engine=engine_name,
            elapsed=time.time() - started,
            segments_dir=segments_dir if keep else None,
        )
    finally:
        if is_temp:
            wav_path.unlink(missing_ok=True)
        if not keep:
            shutil.rmtree(segments_dir, ignore_errors=True)
