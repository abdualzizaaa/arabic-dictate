"""محرّك كوهير العربي المحلي — نسختان:

* ``cpu-optimized`` (افتراضي): نسخة int8 مُهيّأة للمعالج من
  ``sayedM/cohere-transcribe-arabic-cpu-friendly`` مع رأس CTC للفك التخميني.
  تعمل بذاكرة ~2.9GB وبسرعة 4–7× الزمن الحقيقي على معالج بدون كرت رسومات،
  وبفرق دقة لا يُذكر عن النسخة الأصلية (2.06% WER بعد التطبيع).
* ``official``: الأوزان الرسمية عبر ``transformers`` (المستودع مُقيَّد على
  Hugging Face ويحتاج قبول الترخيص). على معالج بدون AVX-512 يكون bf16 بطيئاً
  جداً، لذا النسخة المحسّنة للمعالج هي الخيار العملي هنا.
"""
from __future__ import annotations

import os
import pathlib
import sys
import threading

from .base import Engine, EngineError

DEFAULT_REPO = "sayedM/cohere-transcribe-arabic-cpu-friendly"
DEFAULT_DIR = pathlib.Path.home() / ".local" / "share" / "arabic-dictate" / "models" / "cohere-arabic-cpu"
OFFICIAL_MODEL = "CohereLabs/cohere-transcribe-arabic-07-2026"

REQUIRED_FILES = ("model.safetensors", "quant_map.json", "cpu_model_loader.py", "config.json")


def _release_heap() -> None:
    """يعيد الذاكرة المؤقتة التي استهلكها التحميل إلى نظام التشغيل.

    بدون هذا تبقى ذروة التحميل (~6.5GB) مقيمة في العملية بدل ~4GB الفعلية.
    """
    import ctypes
    import gc
    import sys

    gc.collect()
    if sys.platform == "win32":
        try:
            ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:  # noqa: BLE001
        pass


def model_dir(settings: dict) -> pathlib.Path:
    raw = settings.get("model_dir") or str(DEFAULT_DIR)
    return pathlib.Path(os.path.expanduser(raw))


def model_present(settings: dict) -> bool:
    directory = model_dir(settings)
    return all((directory / name).exists() for name in REQUIRED_FILES)


def pull(settings: dict, repo: str | None = None, on_progress=None) -> str:
    """ينزّل أوزان النموذج إلى مجلد محلي. يُستدعى من الأمر ``arabic-dictate pull``."""
    from huggingface_hub import snapshot_download

    repo = repo or settings.get("repo") or DEFAULT_REPO
    directory = model_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    if on_progress:
        on_progress(f"ينزّل {repo} إلى {directory} (≈3GB)…")
    path = snapshot_download(repo_id=repo, local_dir=str(directory))
    if on_progress:
        on_progress("اكتمل التنزيل")
    return path


class CohereLocal(Engine):
    name = "cohere-local"
    label_ar = "كوهير عربي — محلي (الأدق)"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._load_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._model = None
        self._processor = None
        self._head = None
        self._loader = None

    # ---------- إعدادات ----------
    def _settings(self) -> dict:
        settings = dict(self.config.get("cohere_local", {}))
        settings.setdefault("backend", "cpu-optimized")
        settings.setdefault("repo", DEFAULT_REPO)
        settings.setdefault("use_draft_head", True)
        settings.setdefault("warmup_run", True)
        settings.setdefault("threads", min(10, os.cpu_count() or 4))
        settings.setdefault("max_new_tokens", 256)
        if not settings.get("model_dir"):
            settings["model_dir"] = str(DEFAULT_DIR)
        return settings

    def backend(self) -> str:
        return self._settings()["backend"]

    # ---------- التوفّر ----------
    def available(self) -> tuple[bool, str]:
        if self.backend() == "official":
            return self._official_available()
        settings = self._settings()
        if not model_present(settings):
            return False, "النموذج غير منزّل — شغّل: arabic-dictate pull"
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError as exc:
            return False, f"ينقص اعتماد: {exc.name}"
        return True, ""

    def _official_available(self) -> tuple[bool, str]:
        try:
            import transformers
        except ImportError:
            return False, "transformers غير مثبّت"
        from packaging.version import Version

        if Version(transformers.__version__) < Version("5.4"):
            return False, f"transformers {transformers.__version__} قديم — نحتاج 5.4+"
        if not hasattr(transformers, "CohereAsrForConditionalGeneration"):
            return False, "نسخة transformers لا تدعم Cohere ASR"
        return True, "الأوزان الرسمية مُقيَّدة على Hugging Face — تحتاج قبول الترخيص"

    # ---------- التحميل ----------
    def _load_cpu(self, settings: dict):
        directory = str(model_dir(settings))
        if directory not in sys.path:
            sys.path.insert(0, directory)
        import torch

        torch.set_grad_enabled(False)
        torch.set_num_threads(int(settings["threads"]))

        try:
            import cpu_model_loader
        except ImportError as exc:
            raise EngineError(f"تعذّر تحميل مشغّل النموذج من {directory}: {exc}") from exc

        model, processor = cpu_model_loader.load_cpu_model(directory, verbose=False)
        head = None
        if settings["use_draft_head"]:
            try:
                head, _ = cpu_model_loader.load_draft_head(directory)
            except Exception:  # noqa: BLE001 - الرأس اختياري، الفك العادي يكفي
                head = None
        return cpu_model_loader, model, processor, head

    def _load_official(self, settings: dict):
        import torch
        from transformers import AutoProcessor, CohereAsrForConditionalGeneration

        torch.set_grad_enabled(False)
        torch.set_num_threads(int(settings["threads"]))
        name = settings.get("official_model", OFFICIAL_MODEL)
        processor = AutoProcessor.from_pretrained(name)
        model = CohereAsrForConditionalGeneration.from_pretrained(name, dtype="float32")
        model.eval()
        return None, model, processor, None

    def load(self) -> None:
        if self._model is not None:
            return
        settings = self._settings()
        with self._load_lock:
            if self._model is not None:
                return
            try:
                if settings["backend"] == "official":
                    loader, model, processor, head = self._load_official(settings)
                else:
                    loader, model, processor, head = self._load_cpu(settings)
            except EngineError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise EngineError(f"تعذّر تحميل نموذج كوهير: {exc}") from exc
            self._loader, self._model, self._processor, self._head = loader, model, processor, head
        if settings.get("warmup_run", True):
            self._warmup_pass()
        _release_heap()

    def _warmup_pass(self) -> None:
        """تشغيل صامت أول لتسخين أنوية int8 — بدونه أول تحويل حقيقي يستغرق ~14s."""
        try:
            import numpy as np

            if self.backend() == "official":
                return
            self._loader.transcribe(
                self._model,
                self._processor,
                np.zeros(16000, dtype="float32"),
                language="ar",
                head=self._head,
                max_new_tokens=8,
            )
        except Exception:  # noqa: BLE001 - التسخين تحسين لا شرط
            pass

    def unload(self) -> bool:
        """يحرّر ~3GB من الذاكرة؛ يُعاد التحميل تلقائياً عند أول استخدام."""
        with self._load_lock:
            if self._model is None:
                return False
            self._model = self._processor = self._head = self._loader = None
        _release_heap()
        return True

    def warmup(self) -> None:
        self.load()

    # ---------- التحويل ----------
    def transcribe(self, wav_path: str, language: str = "ar") -> str:
        settings = self._settings()
        self.load()
        with self._process_lock:  # النموذج ليس آمناً للاستدعاء المتزامن
            try:
                if settings["backend"] == "official":
                    return self._transcribe_official(wav_path, language)
                return self._transcribe_cpu(wav_path, language, settings)
            except EngineError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise EngineError(f"فشل التحويل: {exc}") from exc

    def _transcribe_cpu(self, wav_path: str, language: str, settings: dict) -> str:
        head = self._head if language == "ar" else None
        text = self._loader.transcribe(
            self._model,
            self._processor,
            wav_path,
            language=language,
            head=head,
            max_new_tokens=int(settings["max_new_tokens"]),
        )
        return str(text).strip()

    def _transcribe_official(self, wav_path: str, language: str) -> str:
        import soundfile as sf

        audio, rate = sf.read(wav_path, dtype="float32")
        if getattr(audio, "ndim", 1) > 1:
            audio = audio.mean(axis=1)
        inputs = self._processor(audio, sampling_rate=rate, return_tensors="pt", language=language)
        outputs = self._model.generate(**inputs, max_new_tokens=256)
        text = self._processor.decode(outputs, skip_special_tokens=True)
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        return str(text).strip()
