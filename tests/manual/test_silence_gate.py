"""اختبار بوابة الصمت ولمرشّح الهلوسة: يجب ألا يُلصق أي نص من ضجيج فقط."""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from arabic_dictate import config as cfg_mod  # noqa: E402
from arabic_dictate.cli import send  # noqa: E402


def main() -> int:
    saved = cfg_mod.load()
    config = cfg_mod.load()
    config["input_device"] = None  # الميكروفون الحقيقي
    cfg_mod.save(config)
    send("reload", timeout=10.0)

    before = send("last", timeout=5.0).get("text", "")
    print(f"آخر نص قبل الاختبار: {before[:50]!r}", flush=True)

    print("▶ تسجيل ٣ ثوانٍ من الصمت/ضجيج الغرفة…", flush=True)
    send("start", timeout=10.0)
    time.sleep(3.0)
    send("stop", timeout=10.0)

    deadline = time.time() + 180
    status: dict = {}
    while time.time() < deadline:
        status = send("status", timeout=10.0)
        if status.get("state") == "idle":
            break
        time.sleep(1.0)

    after = send("last", timeout=5.0).get("text", "")
    error = status.get("last_error", "")
    print(f"الخطأ المعروض: {error!r}", flush=True)
    print(f"آخر نص بعد الاختبار: {after[:50]!r}", flush=True)

    leaked = after != before
    print("النتيجة:", "❌ سُرّب نص من الصمت" if leaked else "✅ لم يُلصق شيء من الصمت", flush=True)

    cfg_mod.save(saved)
    send("reload", timeout=10.0)
    return 1 if leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())
