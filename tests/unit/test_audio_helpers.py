"""اختبارات بوابة الصمت بملفات WAV مُصنّعة — تعمل بلا ميكروفون."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from arabic_dictate import audio

RATE = 16000


def _write_wav(path: Path, samples: np.ndarray) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(samples.astype(np.int16).tobytes())


def _tone(seconds: float, amplitude: int, freq: float = 440.0) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.int16)


@pytest.fixture(autouse=True)
def force_rms_fallback(monkeypatch):
    """نُعطّل WebRTC VAD هنا: النغمة المُصنّعة ليست كلاماً بشرياً."""
    monkeypatch.setattr(audio, "_webrtc_speech_mask", lambda *args, **kwargs: None)


def test_rms_and_peak_on_tone():
    tone = _tone(0.1, 1000)
    assert audio._peak(tone.tobytes()) == 1000
    assert 600 < audio._rms(tone.tobytes()) <= 1000


def test_empty_file_rejected(tmp_path: Path):
    path = tmp_path / "empty.wav"
    _write_wav(path, np.array([], dtype=np.int16))
    ok, info = audio.trim_silence(path, 260, 0.35)
    assert not ok
    assert info["reason"] == "empty"


def test_quiet_noise_rejected(tmp_path: Path):
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 30, RATE * 2)
    path = tmp_path / "noise.wav"
    _write_wav(path, noise)
    ok, _info = audio.trim_silence(path, 260, 0.35)
    assert not ok


def test_speech_burst_kept_and_trimmed(tmp_path: Path):
    silence = np.zeros(RATE, dtype=np.int16)
    burst = _tone(1.0, 6000)
    path = tmp_path / "burst.wav"
    _write_wav(path, np.concatenate([silence, burst, silence]))
    ok, info = audio.trim_silence(path, 260, 0.35)
    assert ok
    assert 0.9 <= info["duration"] <= 2.4


def test_sweep_temp_files_removes_only_old(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(audio.tempfile, "gettempdir", lambda: str(tmp_path))
    old = tmp_path / "dictate-old.wav"
    fresh = tmp_path / "dictate-fresh.wav"
    other = tmp_path / "keep-me.wav"
    for path in (old, fresh, other):
        path.write_bytes(b"x")
    import os
    import time

    past = time.time() - 48 * 3600
    os.utime(old, (past, past))
    removed = audio.sweep_temp_files(max_age_hours=24)
    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
    assert other.exists()
