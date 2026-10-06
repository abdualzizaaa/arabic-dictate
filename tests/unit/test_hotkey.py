"""اختبارات تحليل الاختصار العالمي."""
from __future__ import annotations

import pytest

from arabic_dictate.hotkey import parse_hotkey


def test_parse_valid_combination():
    key, mods = parse_hotkey("ctrl+alt+d")
    assert key == "d"
    assert "ControlMask" in mods
    assert "Mod1Mask" in mods


def test_parse_is_case_insensitive():
    key, mods = parse_hotkey("SUPER+Shift+K")
    assert key == "k"
    assert "Mod4Mask" in mods
    assert "ShiftMask" in mods


def test_modifier_required():
    with pytest.raises(ValueError):
        parse_hotkey("d")


def test_unknown_modifier_rejected():
    with pytest.raises(ValueError):
        parse_hotkey("hyper+d")


def test_empty_spec_rejected():
    with pytest.raises(ValueError):
        parse_hotkey("")
