"""سجل المحرّكات المتاحة."""
from __future__ import annotations

from .base import Engine, EngineError
from .cohere_cloud import CohereCloud
from .cohere_local import CohereLocal
from .whisper_local import WhisperLocal

REGISTRY: dict[str, type[Engine]] = {
    WhisperLocal.name: WhisperLocal,
    CohereLocal.name: CohereLocal,
    CohereCloud.name: CohereCloud,
}

ORDER = ["whisper-local", "cohere-local", "cohere-cloud"]


def build(name: str, config: dict) -> Engine:
    cls = REGISTRY.get(name)
    if cls is None:
        raise EngineError(f"محرّك غير معروف: {name}")
    return cls(config)


__all__ = ["Engine", "EngineError", "REGISTRY", "ORDER", "build"]
