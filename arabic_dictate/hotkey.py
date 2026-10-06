"""الاختصار العالمي: X11 (XGrabKey) على لينكس، وRegisterHotKey على ويندوز."""
from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable

MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "super",
    "win": "super",
    "mod4": "super",
}

X11_MASKS = {
    "ctrl": "ControlMask",
    "alt": "Mod1Mask",
    "shift": "ShiftMask",
    "super": "Mod4Mask",
}

LOCK_MASKS = ("Mod2Mask", "LockMask")


def parse_hotkey(spec: str) -> tuple[str, list[str]]:
    """'ctrl+alt+d' -> ('d', ['ctrl', 'alt']) — مُعدِّلات معيارية لكل المنصات."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("اختصار فارغ")
    key = parts[-1]
    mods: list[str] = []
    for part in parts[:-1]:
        canonical = MODIFIER_ALIASES.get(part)
        if canonical is None:
            raise ValueError(f"مُعدِّل غير معروف: {part}")
        if canonical not in mods:
            mods.append(canonical)
    if not mods:
        raise ValueError("الاختصار يحتاج مُعدِّلاً واحداً على الأقل (ctrl/alt/super)")
    return key, mods


def create_listener(spec: str, callback: Callable[[], None]):
    """مصنع المستمع حسب المنصّة."""
    if sys.platform == "win32":
        from .win_hotkey import WindowsHotkeyListener

        return WindowsHotkeyListener(spec, callback)
    return HotkeyListener(spec, callback)


class HotkeyListener(threading.Thread):
    """يستمع للاختصار على مستوى الجلسة عبر XGrabKey (لينكس)."""

    def __init__(self, spec: str, callback: Callable[[], None]) -> None:
        super().__init__(daemon=True, name="hotkey")
        self.spec = spec
        self.callback = callback
        self.error: str | None = None
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # noqa: C901
        try:
            from Xlib import XK, X, display
            from Xlib.error import BadAccess, DisplayConnectionError
        except ImportError as exc:  # pragma: no cover
            self.error = f"python-xlib غير متاح: {exc}"
            return

        try:
            key_name, mods = parse_hotkey(self.spec)
        except ValueError as exc:
            self.error = str(exc)
            return

        try:
            disp = display.Display()
        except (DisplayConnectionError, Exception) as exc:  # noqa: BLE001
            self.error = f"تعذّر الاتصال بـ X11: {exc}"
            return

        root = disp.screen().root
        keysym = XK.string_to_keysym(key_name)
        if keysym == 0:
            self.error = f"مفتاح غير معروف: {key_name}"
            return
        keycode = disp.keysym_to_keycode(keysym)

        base = 0
        for mod in mods:
            base |= getattr(X, X11_MASKS[mod])
        masks = {base}
        for lock in LOCK_MASKS:
            masks.add(base | getattr(X, lock))
            for existing in list(masks):
                masks.add(existing | getattr(X, lock))

        grabbed = 0
        for mask in sorted(masks):
            try:
                root.grab_key(keycode, mask, False, X.GrabModeAsync, X.GrabModeAsync)
                grabbed += 1
            except BadAccess:
                continue
        try:
            disp.sync()
        except Exception:  # noqa: BLE001
            pass

        if grabbed == 0:
            self.error = f"الاختصار {self.spec} محجوز من برنامج آخر"
            return

        while not self._stop.is_set():
            try:
                while disp.pending_events():
                    event = disp.next_event()
                    if event.type == X.KeyPress:
                        try:
                            self.callback()
                        except Exception:  # noqa: BLE001
                            pass
                time.sleep(0.04)
            except Exception:  # noqa: BLE001
                time.sleep(0.2)

        try:
            for mask in sorted(masks):
                root.ungrab_key(keycode, mask)
            disp.sync()
        except Exception:  # noqa: BLE001
            pass
