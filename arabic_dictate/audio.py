"""تسجيل الصوت من الميكروفون + بوابة صمت لمنع هلوسة النموذج."""
from __future__ import annotations

import os
import signal
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
CHANNELS = 1

# الكلام يظهر كنبضات أعلى بكثير من أرضية الضجيج؛ الضجيج المستمر مسطّح.
DYNAMIC_RATIO = 2.0


def _samples(buf: bytes) -> np.ndarray:
    """عيّنات S16_LE — نطرح أي بايت يتيم حتى لا يفشل التحويل إلى int16."""
    if len(buf) % 2:
        buf = buf[:-1]
    return np.frombuffer(buf, dtype=np.int16)


def _rms(buf: bytes) -> int:
    values = _samples(buf)
    if values.size == 0:
        return 0
    return int(np.sqrt(np.mean(values.astype(np.float64) ** 2)))


def _peak(buf: bytes) -> int:
    values = _samples(buf)
    return int(np.abs(values.astype(np.int32)).max()) if values.size else 0


def sweep_temp_files(max_age_hours: float = 24.0) -> int:
    """يحذف ملفات dictate-*.wav المتروكة من جلسات سابقة تعطّلت أو انقطعت."""
    removed = 0
    cutoff = time.time() - max_age_hours * 3600
    for path in Path(tempfile.gettempdir()).glob("dictate-*.wav"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed


class Recorder:
    """يسجّل عبر arecord ويوقف التسجيل بلطف حتى تُكتب ترويسة الملف."""

    def __init__(self, input_device: str | None = None) -> None:
        self.input_device = input_device or None
        self._proc: subprocess.Popen | None = None
        self._path: Path | None = None
        self._started_at = 0.0

    @property
    def recording(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def elapsed(self) -> float:
        return time.time() - self._started_at if self._started_at else 0.0

    def start(self) -> Path:
        if self.recording:
            raise RuntimeError("التسجيل يعمل بالفعل")
        fd, name = tempfile.mkstemp(prefix="dictate-", suffix=".wav")
        Path(name).unlink(missing_ok=True)
        self._path = Path(name)
        env = None
        if self.input_device:
            env = {**os.environ, "PULSE_SOURCE": self.input_device}
        self._proc = subprocess.Popen(
            [
                "arecord",
                "-q",
                "-f", "S16_LE",
                "-r", str(SAMPLE_RATE),
                "-c", str(CHANNELS),
                "-t", "wav",
                str(self._path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        self._started_at = time.time()
        # arecord يحتاج جزءاً من الثانية ليُنشئ الملف
        for _ in range(50):
            if self._path.exists() and self._path.stat().st_size > 44:
                break
            time.sleep(0.02)
        return self._path

    def stop(self) -> Path | None:
        if self._proc is None:
            return None
        proc, path = self._proc, self._path
        self._proc = None
        self._path = None
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._started_at = 0.0
        if path is None or not path.exists():
            return None
        _repair_wav_header(path)
        return path


def _repair_wav_header(path: Path) -> None:
    """arecord قد لا يُحدّث أحجام الترويسة عند الإيقاف — نصلحها يدوياً."""
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getnframes() > 0:
                return
    except (wave.Error, EOFError, OSError):
        pass
    raw = path.read_bytes()
    if len(raw) <= 44:
        return
    data = raw[44:]
    header = bytearray(raw[:44])
    struct.pack_into("<I", header, 4, 36 + len(data))
    struct.pack_into("<I", header, 40, len(data))
    path.write_bytes(bytes(header) + data)


def trim_silence(path: str | Path, threshold: int, min_secs: float) -> tuple[bool, dict]:
    """يقصّ الصمت ويرفض المقاطع التي لا تحتوي كلاماً حقيقياً.

    ثلاث طبقات معاً، لأن WebRTC VAD وحده يصنّف ضجيج المروحة كلاماً:
      1. WebRTC VAD يحدّد الإطارات الصوتية المرشّحة.
      2. بوابة ديناميكية: الكلام bursts عالية فوق أرضية الضجيج، أما الضجيج فمسطّح.
      3. حد أدنى لمدة الكلام المتصل.
    """
    with wave.open(str(path), "rb") as wav:
        params = wav.getparams()
        frames = wav.readframes(wav.getnframes())

    width, rate = params.sampwidth, params.framerate
    if not frames:
        return False, {"reason": "empty"}

    mask = _webrtc_speech_mask(frames, rate)
    if mask is None:
        return _trim_silence_rms(path, threshold, min_secs, params, frames, width, rate)

    window = int(rate * 0.03) * width
    levels = [_rms(frames[i:i + window]) for i in range(0, len(frames) - window + 1, window)]
    if not levels:
        return False, {"reason": "empty"}

    p20 = _percentile(levels, 0.20)
    p90 = _percentile(levels, 0.90)

    # (٢) الكلام يجب أن يكون أعلى بوضوح من أرضية الضجيج المحيطة
    floor = max(threshold, int(p20 * DYNAMIC_RATIO))
    if p90 < floor:
        return False, {
            "reason": "noise",
            "p20": p20,
            "p90": p90,
            "floor": floor,
            "ratio": round(p90 / max(p20, 1), 2),
        }

    gate = max(threshold, int(p20 * 1.5))
    speech = [i for i, flag in enumerate(mask) if flag and i < len(levels) and levels[i] >= gate]
    if not speech:
        return False, {"reason": "silent", "p20": p20, "p90": p90}
    if len(speech) * 0.03 < min_secs or _longest_run(speech) * 0.03 < min(min_secs, 0.30):
        return False, {"reason": "too_short", "speech": len(speech) * 0.03}

    total = len(levels)
    first, last = speech[0], speech[-1]
    pad = 12  # ٣٦٠ مللي ثانية حول الكلام
    start = max(0, first - pad)
    end = min(total, last + 1 + pad)
    clip = frames[start * window:end * window]
    duration = len(clip) / float(rate * width)
    if duration < min_secs:
        return False, {"reason": "too_short", "duration": duration}

    with wave.open(str(path), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(clip)

    return True, {
        "duration": duration,
        "speech": len(speech) * 0.03,
        "method": "webrtc+dynamic",
        "p20": p20,
        "p90": p90,
    }


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def _longest_run(indices: list[int]) -> int:
    best = current = 1
    for prev, cur in zip(indices, indices[1:], strict=False):
        current = current + 1 if cur - prev <= 1 else 1
        best = max(best, current)
    return best


def _webrtc_speech_mask(frames: bytes, rate: int, frame_ms: int = 30) -> list[bool] | None:
    try:
        import webrtcvad
    except ImportError:
        return None
    if rate not in (8000, 16000, 32000, 48000):
        return None
    vad = webrtcvad.Vad(3)
    step = int(rate * frame_ms / 1000) * 2
    mask: list[bool] = []
    for offset in range(0, len(frames) - step + 1, step):
        try:
            mask.append(vad.is_speech(frames[offset:offset + step], rate))
        except Exception:  # noqa: BLE001
            mask.append(False)
    return mask or None


def _trim_silence_rms(
    path: str | Path,
    threshold: int,
    min_secs: float,
    params,
    frames: bytes,
    width: int,
    rate: int,
) -> tuple[bool, dict]:
    window = int(rate * 0.03) * width
    chunks = [frames[i:i + window] for i in range(0, len(frames), window)]
    levels = [_rms(c) for c in chunks if c]
    if not levels:
        return False, {"reason": "empty"}

    peak = _peak(frames)
    gate = max(threshold, int(peak * 0.06))

    first = next((i for i, lvl in enumerate(levels) if lvl >= gate), None)
    if first is None:
        return False, {"reason": "silent", "peak": peak, "duration": len(frames) / (rate * width)}

    last = len(levels) - 1
    while last > first and levels[last] < gate:
        last -= 1

    pad = int(0.2 / 0.03)
    start_chunk = max(0, first - pad)
    end_chunk = min(len(chunks), last + 1 + pad)
    speech = b"".join(chunks[start_chunk:end_chunk])
    duration = len(speech) / float(rate * width)

    if duration < min_secs:
        return False, {"reason": "too_short", "duration": duration}

    with wave.open(str(path), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(speech)

    removed = (len(frames) - len(speech)) / float(rate * width)
    return True, {"duration": duration, "peak": peak, "method": "rms", "removed": removed}
