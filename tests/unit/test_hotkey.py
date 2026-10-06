"""اختبارات تحليل الاختصار العالمي."""
from __future__ import annotations

import pytest

from arabic_dictate.hotkey import parse_hotkey


def test_parse_valid_combination():
    key, mods = parse_hotkey("ctrl+alt+d")
    assert key == "d"
    assert "ctrl" in mods
    assert "alt" in mods


def test_parse_is_case_insensitive():
    key, mods = parse_hotkey("SUPER+Shift+K")
    assert key == "k"
    assert "super" in mods
    assert "shift" in mods


def test_aliases_map_to_canonical_modifiers():
    key, mods = parse_hotkey("control+win+d")
    assert key == "d"
    assert mods == ["ctrl", "super"]


def test_modifier_required():
    with pytest.raises(ValueError):
        parse_hotkey("d")


def test_unknown_modifier_rejected():
    with pytest.raises(ValueError):
        parse_hotkey("hyper+d")


def test_empty_spec_rejected():
    with pytest.raises(ValueError):
        parse_hotkey("")
