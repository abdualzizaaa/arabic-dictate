"""اختبار الإدراج: هل يصل النص العربي إلى نافذة نشطة عبر نفس مسار الطرفية؟"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from arabic_dictate import inject  # noqa: E402

SAMPLE = "مرحبا، هذا اختبار الإملاء العربي في الطرفية — الأرقام: 1234."
HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    window = subprocess.Popen(
        [sys.executable, str(HERE / "test_window.py"), "60"],
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
        ids = subprocess.run(
            ["xdotool", "search", "--name", "InjectionTest"], capture_output=True, text=True, timeout=10
        ).stdout.split()
        if not ids:
            print("❌ لم تُفتح نافذة الاختبار", flush=True)
            return 1
        for wid in ids:
            subprocess.run(["xdotool", "windowactivate", "--sync", wid], capture_output=True, timeout=10)
            subprocess.run(["xdotool", "windowfocus", "--sync", wid], capture_output=True, timeout=10)
        time.sleep(1.0)
        print(f"النافذة النشطة: {inject.active_window_title()}", flush=True)

        ok, message = inject.paste(SAMPLE, "paste", "ctrl+shift+v")
        print(f"الإدراج: {ok} — {message}", flush=True)

        for _ in range(30):
            if captured.get("text"):
                break
            time.sleep(0.5)
        got = captured.get("text", "")
        print(f"المستلم في النافذة: {got!r}", flush=True)
        success = got.strip() == SAMPLE.strip()
        print("النتيجة:", "✅ نجح الإدراج" if success else "❌ فشل الإدراج", flush=True)
        return 0 if success else 1
    finally:
        window.kill()


if __name__ == "__main__":
    raise SystemExit(main())
