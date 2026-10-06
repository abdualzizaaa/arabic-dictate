"""إدراج النص في النافذة النشطة (طرفية X11) — لصق آمن للعربية.

ملاحظة مهمة: xclip يتفرّع لخلفية ليبقى مالكاً للحافظة، لذا لا نلتقط مخرجاته
(وإلا انتظرنا إلى الأبد على أنبوب مفتوح) ونضع مهلة لكل أمر.
"""
from __future__ import annotations

import subprocess
import time

DEVNULL = subprocess.DEVNULL


def _run(args: list[str], data: bytes | None = None, timeout: float = 8.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        input=data,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def set_clipboard(text: str) -> bool:
    # لا أنابيب إطلاقاً: xclip يتفرّع ليبقى مالكاً للحافظة فيمسك أنبوب stderr
    # ويجعل أي انتظار يتعلّق للأبد.
    try:
        proc = subprocess.run(
            ["xclip", "-selection", "clipboard", "-in"],
            input=text.encode("utf-8"),
            stdout=DEVNULL,
            stderr=DEVNULL,
            timeout=8.0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    if proc.returncode != 0:
        return False

    # نتأكد أن الحافظة تحمل النص فعلاً قبل اللصق
    for _ in range(12):
        time.sleep(0.05)
        if clipboard_text() == text:
            return True
    return clipboard_text() == text


def clipboard_text() -> str:
    try:
        proc = _run(["xclip", "-selection", "clipboard", "-o"], timeout=4.0)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", "replace")


def active_window_title() -> str:
    try:
        proc = _run(["xdotool", "getactivewindow", "getwindowname"], timeout=4.0)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "?"
    return proc.stdout.decode("utf-8", "replace").strip() or "?"


def paste(text: str, mode: str = "paste", paste_key: str = "ctrl+shift+v") -> tuple[bool, str]:
    """mode: paste (لصق بمفتاح) | type (كتابة حرفية) | clipboard (نسخ فقط)."""
    if not text:
        return False, "نص فارغ"

    if not set_clipboard(text):
        return False, "تعذّر النسخ إلى الحافظة (xclip غير متاح؟)"

    if mode == "clipboard":
        return True, "تم النسخ إلى الحافظة"

    if mode == "type":
        try:
            proc = _run(["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", text], timeout=60.0)
        except subprocess.TimeoutExpired:
            return False, "انتهت مهلة xdotool type"
        if proc.returncode == 0:
            return True, "تمت الكتابة"
        return False, f"فشل xdotool type: {proc.stderr.decode('utf-8', 'replace').strip()[:150]}"

    try:
        proc = _run(["xdotool", "key", "--clearmodifiers", paste_key], timeout=10.0)
    except subprocess.TimeoutExpired:
        return False, "انتهت مهلة اللصق"
    if proc.returncode == 0:
        return True, "تم اللصق"
    return False, f"فشل اللصق: {proc.stderr.decode('utf-8', 'replace').strip()[:150]}"
