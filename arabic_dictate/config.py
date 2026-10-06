"""إعدادات ومسارات أداة الإملاء العربية."""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any

APP_NAME = "arabic-dictate"

HOME = pathlib.Path.home()
CONFIG_DIR = pathlib.Path(os.environ.get("ARABIC_DICTATE_CONFIG_DIR", HOME / ".config" / APP_NAME))
CONFIG_PATH = CONFIG_DIR / "config.json"
COHERE_KEY_PATH = CONFIG_DIR / "cohere.key"
STATE_DIR = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / APP_NAME
STATE_DIR.mkdir(parents=True, exist_ok=True)
SOCKET_PATH = STATE_DIR / "daemon.sock"
LOG_PATH = STATE_DIR / "daemon.log"

DEFAULTS: dict[str, Any] = {
    "engine": "cohere-local",
    "language": "ar",
    "input_device": None,
    "inject_mode": "paste",
    "paste_key": "ctrl+shift+v",
    "trailing_space": True,
    "notify": True,
    "keep_audio": False,
    "hotkey_enabled": True,
    "hotkey": "ctrl+alt+d",
    "vad_min_secs": 0.35,
    "vad_threshold": 260,
    "whisper": {
        "model": "large-v3-turbo",
        "device": "cpu",
        "compute_type": "int8",
        "beam_size": 5,
        "cpu_threads": 0,
    },
    "cohere_cloud": {
        "model": "cohere-transcribe-arabic-07-2026",
        "endpoint": "https://api.cohere.com/v2/audio/transcriptions",
    },
    "cohere_local": {
        "backend": "cpu-optimized",
        "repo": "sayedM/cohere-transcribe-arabic-cpu-friendly",
        "model_dir": "~/.local/share/arabic-dictate/models/cohere-arabic-cpu",
        "official_model": "CohereLabs/cohere-transcribe-arabic-07-2026",
        "use_draft_head": True,
        "warmup_run": True,
        "threads": 10,
        "max_new_tokens": 256,
    },
    "meeting": {
        "engine": None,
        "embedding": "eres2net",
        "speakers": 0,
        "clustering_threshold": 0.7,
        "max_segment_secs": 30,
        "merge_gap_secs": 0.5,
        "label_template": "المتحدث {n}",
        "output_dir": None,
        "keep_segments": False,
    },
}

ENGINE_LABELS_AR = {
    "whisper-local": "ويسبر — محلي وسريع",
    "cohere-local": "كوهير عربي — محلي (الأدق)",
    "cohere-cloud": "كوهير — سحابي (الأدق والأسرع)",
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return _merge(DEFAULTS, json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULTS)
    return dict(DEFAULTS)


def save(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_config_file() -> pathlib.Path:
    if not CONFIG_PATH.exists():
        save(DEFAULTS)
    return CONFIG_PATH


def cohere_api_key() -> str:
    key = os.environ.get("COHERE_API_KEY", "").strip()
    if key:
        return key
    if COHERE_KEY_PATH.exists():
        return COHERE_KEY_PATH.read_text(encoding="utf-8").strip()
    return ""
