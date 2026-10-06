#!/usr/bin/env python3
"""قياس سرعة المحرّكات (RTF) على ملف صوتي.

مثال:
    .venv/bin/python scripts/bench.py sample.wav --engine cohere-local --engine whisper-local --runs 3
"""
from __future__ import annotations

import argparse
import pathlib
import resource
import sys
import time
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from arabic_dictate import config as cfg_mod  # noqa: E402
from arabic_dictate.engines import ORDER, build  # noqa: E402


def wav_duration(path: pathlib.Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate() or 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="قياس زمن التحويل (RTF) لمحرّكات الإملاء العربي")
    parser.add_argument("file", help="ملف WAV")
    parser.add_argument("--engine", choices=ORDER, action="append", dest="engines", help="محرّك (يتكرر)")
    parser.add_argument("--runs", type=int, default=2, help="عدد التشغيلات لكل محرّك")
    args = parser.parse_args()

    path = pathlib.Path(args.file).expanduser()
    if not path.exists():
        print(f"الملف غير موجود: {path}", file=sys.stderr)
        return 1
    duration = wav_duration(path)
    config = cfg_mod.load()
    engines = args.engines or [config.get("engine", ORDER[0])]

    print(f"الملف: {path.name} · المدة: {duration:.1f}s · التشغيلات: {args.runs}")
    for name in engines:
        engine = build(name, config)
        ok, reason = engine.available()
        if not ok:
            print(f"— {name}: غير متاح ({reason})")
            continue
        load_started = time.time()
        engine.warmup()
        print(f"— {name}: التحميل والتسخين {time.time() - load_started:.1f}s")
        times: list[float] = []
        for index in range(args.runs):
            started = time.time()
            text = engine.transcribe(str(path), config.get("language", "ar"))
            elapsed = time.time() - started
            times.append(elapsed)
            rtf = elapsed / duration if duration else 0.0
            print(f"    تشغيل {index + 1}: {elapsed:.2f}s (RTF {rtf:.3f}) — {len(text)} حرفاً")
        best = min(times)
        print(f"    الأفضل: {best:.2f}s · RTF {best / duration:.3f}")

    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"ذروة الذاكرة لهذه العملية: {peak_mb:.0f}MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
