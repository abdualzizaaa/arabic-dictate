"""الاختصار العالمي على ويندوز عبر RegisterHotKey في خيط رسائل مستقل.

الوحدة قابلة للاستيراد على أي نظام (ctypes يُحمَّل كسولاً)، ودوال الخرائط
النقية (``hotkey_to_win``) تُختبَر في CI.
"""
from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable

from .hotkey import parse_hotkey

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 1

WIN_MODS = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "super": 0x0008}

SPECIAL_VK = {
    "space": 0x20,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "backspace": 0x08,
}

_user32 = None


def _libs():
    global _user32
    if _user32 is None:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        _user32 = user32
    return _user32


def _vk_for(key: str) -> int:
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    if key in SPECIAL_VK:
        return SPECIAL_VK[key]
    raise ValueError(f"مفتاح غير مدعوم على ويندوز: {key}")


def hotkey_to_win(spec: str) -> tuple[int, int]:
    """'ctrl+alt+d' -> (MOD_CONTROL|MOD_ALT, 0x44) — دالة نقية قابلة للاختبار."""
    key, mods = parse_hotkey(spec)
    flags = 0
    for mod in mods:
        flags |= WIN_MODS[mod]
    return flags, _vk_for(key)


class WindowsHotkeyListener(threading.Thread):
    """خيط واحد: يسجّل الاختصار ثم يضخّ رسائل ويندوز حتى الإيقاف."""

    def __init__(self, spec: str, callback: Callable[[], None]) -> None:
        super().__init__(daemon=True, name="win-hotkey")
        self.spec = spec
        self.callback = callback
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread_id: int | None = None

    def stop(self) -> None:
        self._stop.set()
        if self._thread_id:
            try:
                user32 = _libs()
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:  # noqa: BLE001
                pass

    def run(self) -> None:  # noqa: C901
        from ctypes import wintypes

        try:
            flags, vk = hotkey_to_win(self.spec)
        except ValueError as exc:
            self.error = str(exc)
            return

        user32 = _libs()
        kernel32 = ctypes.WinDLL("kernel32")
        self._thread_id = int(kernel32.GetCurrentThreadId())
        if not user32.RegisterHotKey(None, HOTKEY_ID, flags, vk):
            self.error = f"الاختصار {self.spec} محجوز من برنامج آخر"
            return
        try:
            message = wintypes.MSG()
            while not self._stop.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result in (0, -1):
                    break
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    try:
                        self.callback()
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
