"""إدخال ويندوز: الحافظة + محاكاة لوحة المفاتيح عبر ctypes (بلا اعتماديات إضافية).

الوحدة قابلة للاستيراد على أي نظام (مكتبات ويندوز تُحمَّل عند أول استخدام)،
والدوال النقية فيها تُختبَر في CI على المنصتين.
"""
from __future__ import annotations

import time

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12

_MODIFIER_VK = {"ctrl": VK_CONTROL, "alt": VK_MENU, "shift": VK_SHIFT}

_user32 = None
_kernel32 = None
_input_struct = None


def _libs():
    """يحمّل مكتبات ويندوز ويضبط توقيعات الدوال الصحيحة (مرة واحدة)."""
    global _user32, _kernel32
    if _user32 is not None:
        return _user32, _kernel32
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

    _user32, _kernel32 = user32, kernel32
    return _user32, _kernel32


def _input_type():
    """يبني هياكل SendInput مرة واحدة (تُستورد ctypes كسولاً)."""
    global _input_struct
    if _input_struct is not None:
        return _input_struct
    import ctypes
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _Union(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _Union)]

    _input_struct = INPUT
    return _input_struct


# ---------- دوال نقية (قابلة للاختبار على أي نظام) ----------
def parse_paste_key(paste_key: str) -> tuple[list[int], int]:
    """'ctrl+shift+v' -> ([VK_CONTROL, VK_SHIFT], 0x56)."""
    parts = [p.strip().lower() for p in paste_key.split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"مفتاح لصق غير مدعوم على ويندوز: {paste_key}")
    *mods, key = parts
    modifier_vks = []
    for mod in mods:
        vk = _MODIFIER_VK.get(mod)
        if vk is None:
            raise ValueError(f"مُعدِّل غير مدعوم على ويندوز: {mod}")
        modifier_vks.append(vk)
    if len(key) != 1 or not key.isascii() or not key.isalnum():
        raise ValueError(f"مفتاح لصق غير مدعوم على ويندوز: {key}")
    return modifier_vks, ord(key.upper())


def utf16_units(text: str) -> list[int]:
    """وحدات UTF-16 لإرسال أي محرف (العربية والإيموجي) عبر SendInput."""
    data = text.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


# ---------- إرسال المفاتيح ----------
def _send_key(vk: int = 0, scan: int = 0, flags: int = 0) -> bool:
    import ctypes

    user32, _ = _libs()
    inp = _input_type()()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = scan
    inp.u.ki.dwFlags = flags
    inp.u.ki.time = 0
    inp.u.ki.dwExtraInfo = None
    return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) == 1


def send_paste(paste_key: str = "ctrl+shift+v") -> bool:
    modifier_vks, key_vk = parse_paste_key(paste_key)
    for vk in modifier_vks:
        _send_key(vk=vk)
    ok = _send_key(vk=key_vk)
    _send_key(vk=key_vk, flags=KEYEVENTF_KEYUP)
    for vk in reversed(modifier_vks):
        _send_key(vk=vk, flags=KEYEVENTF_KEYUP)
    return ok


def type_text(text: str) -> bool:
    ok = True
    for unit in utf16_units(text):
        ok = _send_key(scan=unit, flags=KEYEVENTF_UNICODE) and ok
        ok = _send_key(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP) and ok
    return ok


# ---------- الحافظة ----------
def _open_clipboard(retries: int = 10) -> bool:
    user32, _ = _libs()
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def set_clipboard(text: str) -> bool:
    import ctypes

    user32, kernel32 = _libs()
    if not _open_clipboard():
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        payload = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        # الملكية انتقلت إلى النظام — لا نحرّر المقبض بعد نجاح SetClipboardData
        return True
    finally:
        user32.CloseClipboard()


def clipboard_text() -> str:
    import ctypes

    user32, kernel32 = _libs()
    if not _open_clipboard():
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return str(ctypes.wstring_at(pointer))
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def active_window_title() -> str:
    import ctypes

    user32, _ = _libs()
    hwnd = user32.GetForegroundWindow()
    length = int(user32.GetWindowTextLengthW(hwnd))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value or "?"


# ---------- الواجهة الموحّدة مع لينكس ----------
def paste(text: str, mode: str = "paste", paste_key: str = "ctrl+shift+v") -> tuple[bool, str]:
    """نظير دالة اللصق في لينكس (نفس المخارج والرسائل)."""
    if not text:
        return False, "نص فارغ"
    if not set_clipboard(text):
        return False, "تعذّر النسخ إلى الحافظة"
    for _ in range(10):
        time.sleep(0.03)
        if clipboard_text() == text:
            break
    else:
        return False, "تعذّر التحقق من الحافظة"
    if mode == "clipboard":
        return True, "تم النسخ إلى الحافظة"
    if mode == "type":
        return (True, "تمت الكتابة") if type_text(text) else (False, "فشلت الكتابة الحرفية")
    try:
        ok = send_paste(paste_key)
    except ValueError as exc:
        return False, str(exc)
    return (True, "تم اللصق") if ok else (False, "فشل إرسال مفتاح اللصق")
