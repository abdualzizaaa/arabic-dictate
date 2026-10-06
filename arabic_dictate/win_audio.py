"""تسجيل الصوت على ويندوز عبر soundcard (WASAPI): ميكروفون + صوت النظام (loopback).

الوحدة قابلة للاستيراد على أي نظام؛ مكتبة soundcard تُحمَّل عند أول تسجيل.
"""
from __future__ import annotations

import os
import pathlib
import tempfile
import threading
import time
import wave

import numpy as np

from .audio import SAMPLE_RATE


def _pick_mic(sc, name: str | None):
    """يختار الميكروفون بالإسم (مطابقة جزئية) أو الافتراضي."""
    if not name:
        return sc.default_microphone()
    try:
        return sc.get_microphone(id=name, include_loopback=False)
    except Exception:  # noqa: BLE001 - نجرب المطابقة الجزئية
        lowered = name.lower()
        for mic in sc.all_microphones(include_loopback=False):
            if lowered in mic.name.lower():
                return mic
    raise RuntimeError(f"تعذّر العثور على ميكروفون باسم: {name}")


def _resample(samples: np.ndarray, rate: int, target: int = SAMPLE_RATE) -> np.ndarray:
    """إعادة تشكيل بسيطة: مرشّح صندوقي للمضاعفات الصحيحة، وإلا استيفاء خطي."""
    if rate == target or samples.size == 0:
        return samples
    if rate % target == 0:
        factor = rate // target
        trimmed = samples[: len(samples) - (len(samples) % factor)]
        return trimmed.reshape(-1, factor).mean(axis=1)
    source = np.arange(len(samples), dtype=np.float64)
    target_index = np.linspace(0, len(samples) - 1, int(len(samples) * target / rate))
    return np.interp(target_index, source, samples)


def _write_wav(path: pathlib.Path, samples: np.ndarray) -> None:
    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm16.tobytes())


class WindowsRecorder:
    """واجهة مطابقة لمسجّل لينكس: start() / stop() / recording / elapsed."""

    def __init__(self, input_device: str | None = None) -> None:
        self.input_device = input_device or None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._frames: list[np.ndarray] = []
        self._rate = SAMPLE_RATE
        self._error: str | None = None
        self._path: pathlib.Path | None = None
        self._started_at = 0.0

    @property
    def recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def elapsed(self) -> float:
        return time.time() - self._started_at if self._started_at else 0.0

    def start(self) -> pathlib.Path:
        if self.recording:
            raise RuntimeError("التسجيل يعمل بالفعل")
        handle, name = tempfile.mkstemp(prefix="dictate-", suffix=".wav")
        os.close(handle)
        self._path = pathlib.Path(name)
        self._frames = []
        self._error = None
        self._stop.clear()
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._capture, daemon=True, name="win-mic")
        self._thread.start()
        for _ in range(25):  # مهلة قصيرة حتى تبدأ العيّنات بالوصول
            if self._frames or self._error:
                break
            time.sleep(0.02)
        return self._path

    def _capture(self) -> None:
        import soundcard as sc

        try:
            mic = _pick_mic(sc, self.input_device)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            return
        for rate in (SAMPLE_RATE, 48000):
            try:
                frames: list[np.ndarray] = []
                with mic.recorder(samplerate=rate, channels=1, blocksize=1600) as rec:
                    self._rate = rate
                    while not self._stop.is_set():
                        data = rec.record(numframes=1600)
                        mono = data[:, 0] if data.ndim == 2 else data
                        frames.append(np.asarray(mono, dtype=np.float32))
                self._frames = frames
                return
            except Exception as exc:  # noqa: BLE001
                self._error = str(exc)

    def stop(self) -> pathlib.Path | None:
        if self._thread is None:
            return None
        self._stop.set()
        self._thread.join(timeout=6)
        self._thread = None
        self._started_at = 0.0
        if self._error and not self._frames:
            raise RuntimeError(f"تعذّر التسجيل من الميكروفون: {self._error}")
        if self._path is None:
            return None
        samples = np.concatenate(self._frames) if self._frames else np.array([], dtype=np.float32)
        samples = _resample(samples, self._rate)
        _write_wav(self._path, samples)
        return self._path


def record_meeting_windows(
    out_path: pathlib.Path,
    *,
    input_device: str | None = None,
    sample_rate: int = SAMPLE_RATE,
) -> pathlib.Path:
    """تسجيل الميكروفون + صوت النظام (WASAPI loopback) ودمجهما حتى Ctrl+C."""
    import soundcard as sc

    out_path = out_path.expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        loopback = sc.get_microphone(sc.default_speaker().name, include_loopback=True)
        mic = _pick_mic(sc, input_device)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"تعذّر الوصول لتسجيل صوت النظام: {exc}") from exc

    frames: list[np.ndarray] = []
    stop = threading.Event()
    state: dict[str, object] = {"error": None, "rate": sample_rate}

    def capture() -> None:
        for rate in (sample_rate, 48000):
            try:
                captured: list[np.ndarray] = []
                # قناتان للـ loopback: القناة الواحدة معطوبة في WASAPI (خلل موثّق في soundcard)
                with loopback.recorder(samplerate=rate, channels=2, blocksize=1600) as rec_loop, \
                        mic.recorder(samplerate=rate, channels=1, blocksize=1600) as rec_mic:
                    state["rate"] = rate
                    while not stop.is_set():
                        loop_data = rec_loop.record(numframes=1600)
                        mic_data = rec_mic.record(numframes=1600)
                        count = min(len(loop_data), len(mic_data))
                        if count == 0:
                            continue
                        mixed = loop_data[:count].mean(axis=1) + mic_data[:count, 0]
                        captured.append(np.asarray(mixed, dtype=np.float32))
                frames.extend(captured)
                return
            except Exception as exc:  # noqa: BLE001
                state["error"] = str(exc)

    thread = threading.Thread(target=capture, daemon=True, name="win-meeting")
    thread.start()
    print("▶ يسجّل الآن (الميكروفون + صوت النظام)… للإيقاف: Ctrl+C", flush=True)
    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\n⏹ إيقاف التسجيل وحفظ الملف…", flush=True)
    stop.set()
    thread.join(timeout=8)

    if not frames:
        raise RuntimeError(f"لم يُسجَّل شيء — تحقّق من الميكروفون ومخرج الصوت ({state['error']})")

    samples = _resample(np.concatenate(frames), int(state["rate"]))  # type: ignore[arg-type]
    _write_wav(out_path, samples)
    return out_path
