"""تمييز المتحدثين عبر sherpa-onnx (استيراد كسول — الحزمة الأساسية لا تتأثر).

القرار المعماري: sherpa-onnx بنماذج pyannote segmentation-3.0 (MIT) و3D-Speaker
CAM++/ERes2Net (Apache-2.0) — بلا نماذج مُقيَّدة وبلا حساب HuggingFace، وزمن
المعالجة عملي على المعالج.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .errors import MeetingError
from .models import DEFAULT_EMBEDDING, ensure_models


@dataclass(frozen=True)
class Turn:
    """مقطع صوتي لمتحدث واحد. speaker فهرس صفري (يُعرض «المتحدث ١» = 0+1)."""

    start: float
    end: float
    speaker: int


def diarize(
    samples: np.ndarray,
    sample_rate: int,
    *,
    speakers: int = 0,
    threshold: float = 0.5,
    num_threads: int = 0,
    embedding: str = DEFAULT_EMBEDDING,
    progress: Callable[[int, int], None] | None = None,
) -> list[Turn]:
    """يعيد مقاطع (start, end, speaker) مرتبة زمنياً.

    samples: float32 بمجال [-1, 1] وبمعدل sample_rate (16kHz).
    speakers: 0 = كشف تلقائي عبر threshold؛ أو العدد المعروف.
    embedding: "eres2net" (افتراضي) أو "titanet" (أسرع).
    """
    try:
        import sherpa_onnx  # noqa: PLC0415 - استيراد كسول مقصود
    except ImportError as exc:
        raise MeetingError(
            'حزمة sherpa-onnx غير مثبّتة — ثبّتها بالأمر: pip install "arabic-dictate[meeting]"'
        ) from exc

    segmentation_model, embedding_model = ensure_models(embedding)
    if num_threads <= 0:
        num_threads = max(1, min(4, (os.cpu_count() or 4) // 3))

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(segmentation_model),
                window_shift_ratio=0.1,
            ),
            num_threads=num_threads,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(embedding_model),
            num_threads=num_threads,
        ),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=int(speakers) if speakers > 0 else -1,
            threshold=float(threshold),
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise MeetingError("إعداد نماذج التمييز غير صالح — تحقق من وجود الملفات (arabic-dictate meeting setup)")

    diarization = sherpa_onnx.OfflineSpeakerDiarization(config)
    if sample_rate != diarization.sample_rate:
        raise MeetingError(f"معدل العينات غير متوقع: {sample_rate} بدل {diarization.sample_rate}")

    kwargs = {}
    if progress is not None:

        def _callback(done: int, total: int) -> int:
            progress(done, total)
            return 0

        kwargs["callback"] = _callback

    result = diarization.process(samples, **kwargs).sort_by_start_time()
    return [Turn(start=float(item.start), end=float(item.end), speaker=int(item.speaker)) for item in result]
