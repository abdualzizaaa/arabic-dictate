"""اختبار المسار الكامل: تسجيل → بوابة صمت → تحويل → إدراج في نافذة نشطة.

يشغّل الخفيّة فعلياً ويغذّيها بمقطع عربي حقيقي عبر مراقب مخرج الصوت،
محاكياً تماماً ما يحدث عندما تتكلم في الميكروفون.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from arabic_dictate import config as cfg_mod  # noqa: E402
from arabic_dictate.cli import send  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SAMPLE = pathlib.Path("/tmp/ar_e2e.wav")
WINDOW_TIMEOUT = 300


def prepare_sample() -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", "2", "-t", "8", "-i", "/tmp/ar_test.wav", str(SAMPLE)],
        check=True,
    )


def monitor_source() -> str:
    sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True).stdout.strip()
    return f"{sink}.monitor"


def wait_for_idle(timeout: float = 240.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = send("status", timeout=10.0)
        if last.get("state") == "idle" and (last.get("last_text") or last.get("last_error")):
            return last
        time.sleep(1.0)
    return last


def main() -> int:
    prepare_sample()
    original = cfg_mod.load()
    config = cfg_mod.load()
    config["input_device"] = monitor_source()
    config["vad_min_secs"] = 0.5
    cfg_mod.save(config)
    print(f"جهاز الإدخال: {config['input_device']}", flush=True)
    print(f"المحرّك: {config.get('engine')}", flush=True)

    send("reload", timeout=10.0)

    window = subprocess.Popen(
        [sys.executable, str(HERE / "test_window.py"), str(WINDOW_TIMEOUT)],
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    captured: dict[str, str] = {}

    def reader() -> None:
        for line in window.stdout:  # type: ignore[union-attr]
            if line.startswith("PASTED>>>"):
                captured["text"] = line.split("PASTED>>>", 1)[1].strip()

    threading.Thread(target=reader, daemon=True).start()

    try:
        time.sleep(2.5)
        for wid in subprocess.run(
            ["xdotool", "search", "--name", "InjectionTest"], capture_output=True, text=True
        ).stdout.split():
            subprocess.run(["xdotool", "windowactivate", "--sync", wid], capture_output=True)
            subprocess.run(["xdotool", "windowfocus", "--sync", wid], capture_output=True)
        time.sleep(0.8)

        print("▶ بدء التسجيل…", flush=True)
        print(send("start", timeout=15.0), flush=True)
        time.sleep(0.6)
        subprocess.run(["paplay", str(SAMPLE)], check=True)
        print("⏹ تشغيل المقطع انتهى — إيقاف التسجيل", flush=True)
        print(send("stop", timeout=15.0), flush=True)

        status = wait_for_idle()
        print("— حالة الخفيّة —", flush=True)
        print(
            json.dumps({k: status.get(k) for k in ("state", "last_engine", "last_error")}, ensure_ascii=False),
            flush=True,
        )
        print(f"نص التحويل: {status.get('last_text', '')!r}", flush=True)

        for _ in range(40):
            if captured.get("text"):
                break
            time.sleep(0.5)
        print(f"وصل إلى النافذة: {captured.get('text')!r}", flush=True)

        ok = bool(captured.get("text")) and captured["text"].strip() == (status.get("last_text") or "").strip()
        print("النتيجة:", "✅ نجح المسار الكامل" if ok else "❌ فشل المسار الكامل", flush=True)
        return 0 if ok else 1
    finally:
        window.kill()
        cfg_mod.save(original)
        send("reload", timeout=10.0)


if __name__ == "__main__":
    raise SystemExit(main())
