"""اختبارات منطق ويندوز النقي — تعمل على كل المنصات (بلا ctypes ويندوز)."""
from __future__ import annotations

import pytest

from arabic_dictate import ipc
from arabic_dictate.win_hotkey import hotkey_to_win
from arabic_dictate.win_input import parse_paste_key, utf16_units


# ---------- خرائط الاختصار ----------
def test_hotkey_to_win_maps_modifiers_and_key():
    flags, vk = hotkey_to_win("ctrl+alt+d")
    assert flags == 0x0002 | 0x0001
    assert vk == ord("D")


def test_hotkey_to_win_fkeys_and_special():
    flags, vk = hotkey_to_win("super+f5")
    assert flags == 0x0008
    assert vk == 0x74  # VK_F5
    _, space = hotkey_to_win("ctrl+space")
    assert space == 0x20


def test_hotkey_to_win_rejects_unknown_key():
    with pytest.raises(ValueError):
        hotkey_to_win("ctrl+م")  # حرف عربي غير مدعوم كمفتاح على ويندوز


# ---------- مفاتيح اللصق ----------
def test_parse_paste_key_variants():
    mods, vk = parse_paste_key("ctrl+shift+v")
    assert mods == [0x11, 0x10]
    assert vk == 0x56
    mods, vk = parse_paste_key("Ctrl+V")
    assert mods == [0x11]
    assert vk == 0x56


def test_parse_paste_key_rejects_unsupported():
    with pytest.raises(ValueError):
        parse_paste_key("v")
    with pytest.raises(ValueError):
        parse_paste_key("meta+v")


# ---------- وحدات UTF-16 ----------
def test_utf16_units_handles_arabic_and_surrogates():
    assert utf16_units("د") == [0x062F]
    assert utf16_units("") == []
    assert utf16_units("🗣") == [0xD83D, 0xDDE3]  # زوج بديل (إيموجي)


# ---------- توكن IPC على ويندوز ----------
def test_ipc_authorized_linux_always_true(monkeypatch):
    monkeypatch.setattr(ipc, "IS_WINDOWS", False)
    assert ipc.authorized({}) is True


def test_ipc_authorized_windows_requires_token(monkeypatch):
    monkeypatch.setattr(ipc, "IS_WINDOWS", True)
    monkeypatch.setattr(ipc, "_server_token", None)
    assert ipc.authorized({"token": "x"}) is False
    monkeypatch.setattr(ipc, "_server_token", "secret")
    assert ipc.authorized({"token": "secret"}) is True
    assert ipc.authorized({"token": "wrong"}) is False


def test_ipc_sign_adds_token_on_windows(tmp_path, monkeypatch):
    info = tmp_path / "daemon.json"
    info.write_text('{"port": 1234, "token": "t0k"}', encoding="utf-8")
    monkeypatch.setattr(ipc, "IS_WINDOWS", True)
    monkeypatch.setattr(ipc.cfg_mod, "IPC_INFO_PATH", info)
    signed = ipc.sign({"command": "status"})
    assert signed["token"] == "t0k"


def test_ipc_sign_untouched_on_linux(monkeypatch):
    monkeypatch.setattr(ipc, "IS_WINDOWS", False)
    request = {"command": "status"}
    assert ipc.sign(request) == request
