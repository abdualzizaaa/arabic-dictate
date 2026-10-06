"""واجهة محرّكات التحويل من الكلام إلى نص."""
from __future__ import annotations


class EngineError(RuntimeError):
    pass


class Engine:
    name = "base"
    label_ar = "محرّك"

    def __init__(self, config: dict) -> None:
        self.config = config

    def available(self) -> tuple[bool, str]:
        """(متاح؟, سبب) — يُستخدم لعرض الحالة في القائمة."""
        return True, ""

    def transcribe(self, wav_path: str, language: str = "ar") -> str:
        raise NotImplementedError

    def warmup(self) -> None:
        """تحميل مسبق اختياري للنموذج."""

    def unload(self) -> bool:
        """تحرير ذاكرة النموذج إن كان المحرّك يحمّله. يعيد True إن حُرّر شيء."""
        return False
