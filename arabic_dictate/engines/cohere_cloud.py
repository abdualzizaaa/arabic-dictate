"""محرّك كوهير السحابي — Cohere Transcribe Arabic عبر الـ API."""
from __future__ import annotations

from .. import config as cfg_mod
from .base import Engine, EngineError


class CohereCloud(Engine):
    name = "cohere-cloud"
    label_ar = "كوهير — سحابي (الأدق والأسرع)"

    def _settings(self) -> dict:
        return self.config.get("cohere_cloud", {})

    def available(self) -> tuple[bool, str]:
        if not cfg_mod.cohere_api_key():
            return False, f"لا يوجد مفتاح API — ضعه في {cfg_mod.COHERE_KEY_PATH}"
        try:
            import requests  # noqa: F401
        except ImportError:
            return False, "مكتبة requests غير مثبّتة"
        return True, ""

    def transcribe(self, wav_path: str, language: str = "ar") -> str:
        import requests

        key = cfg_mod.cohere_api_key()
        if not key:
            raise EngineError("مفتاح Cohere API غير موجود")

        settings = self._settings()
        try:
            with open(wav_path, "rb") as audio:
                response = requests.post(
                    settings.get("endpoint", "https://api.cohere.com/v2/audio/transcriptions"),
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": ("audio.wav", audio, "audio/wav")},
                    data={
                        "model": settings.get("model", "cohere-transcribe-arabic-07-2026"),
                        "language": language,
                    },
                    timeout=120,
                )
        except requests.RequestException as exc:
            raise EngineError(f"تعذّر الاتصال بـ Cohere: {exc}") from exc

        if response.status_code == 401:
            raise EngineError("مفتاح Cohere مرفوض (401)")
        if response.status_code == 429:
            raise EngineError("تجاوزت حدود الاستخدام المجاني (429) — جرّب لاحقاً")
        if response.status_code >= 400:
            raise EngineError(
                f"خطأ من Cohere ({response.status_code}): {response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise EngineError(f"رد غير مفهوم من Cohere: {response.text[:200]}") from exc

        text = payload.get("text") or payload.get("transcript") or ""
        if not text and isinstance(payload.get("transcriptions"), list):
            first = payload["transcriptions"][0] if payload["transcriptions"] else {}
            text = first.get("text", "") if isinstance(first, dict) else str(first)
        return str(text).strip()
