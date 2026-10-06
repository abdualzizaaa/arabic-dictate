"""اختبارات الإعدادات: الدمج العميق والقيم الافتراضية."""
from __future__ import annotations

from arabic_dictate import config as cfg_mod


def test_merge_is_deep_and_non_destructive():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 9}, "c": 4}
    merged = cfg_mod._merge(base, override)
    assert merged["a"] == {"x": 1, "y": 9}
    assert merged["b"] == 3
    assert merged["c"] == 4
    assert base["a"] == {"x": 1, "y": 2}


def test_merge_handles_empty_override():
    base = {"a": {"x": 1}}
    assert cfg_mod._merge(base, {}) == base
    assert cfg_mod._merge(base, None) == base


def test_defaults_contain_expected_keys():
    assert cfg_mod.DEFAULTS["engine"] == "cohere-local"
    assert cfg_mod.DEFAULTS["keep_audio"] is False
    assert cfg_mod.DEFAULTS["whisper"]["device"] == "cpu"
    meeting = cfg_mod.DEFAULTS["meeting"]
    assert meeting["speakers"] == 0
    assert "{n}" in meeting["label_template"]


def test_engine_labels_cover_engine_order():
    from arabic_dictate.engines import ORDER

    for name in ORDER:
        assert name in cfg_mod.ENGINE_LABELS_AR
