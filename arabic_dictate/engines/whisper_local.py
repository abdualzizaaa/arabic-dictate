"""محرّك ويسبر المحلي عبر faster-whisper (يعمل بدون إنترنت بعد أول تحميل)."""
from __future__ import annotations

import threading

from .base import Engine, EngineError


class WhisperLocal(Engine):
    name = "whisper-local"
    label_ar = "ويسبر — محلي وسريع"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._model = None
        self._lock = threading.Lock()

    def available(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper غير مثبّت"
        return True, ""

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            from faster_whisper import WhisperModel

            cfg = self.config.get("whisper", {})
            try:
                self._model = WhisperModel(
                    cfg.get("model", "large-v3-turbo"),
                    device=cfg.get("device", "cpu") or "cpu",
                    compute_type=cfg.get("compute_type", "int8"),
                    cpu_threads=int(cfg.get("cpu_threads", 0) or 0),
                )
            except Exception as exc:  # noqa: BLE001
                raise EngineError(f"تعذّر تحميل نموذج ويسبر: {exc}") from exc
            return self._model

    def transcribe(self, wav_path: str, language: str = "ar") -> str:
        model = self._load()
        try:
            segments, _info = model.transcribe(
                wav_path,
                language=language,
                beam_size=int(self.config.get("whisper", {}).get("beam_size", 5)),
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"فشل التحويل: {exc}") from exc

    def warmup(self) -> None:
        self._load()

    def unload(self) -> bool:
        """يحرّر ذاكرة النموذج (~2GB)؛ يُعاد التحميل تلقائياً عند أول استخدام تالٍ."""
        with self._lock:
            if self._model is None:
                return False
            self._model = None
        import gc

        gc.collect()
        return True
