"""تنزيل نماذج تمييز المتحدثين (sherpa-onnx) مع التحقق من SHA-256.

النماذج تُنزَّل من إصدارات GitHub الرسمية لمشروع k2-fsa — بلا حساب
HuggingFace وبلا قبول شروط:
  - التقسيم: pyannote segmentation-3.0 (ترخيص MIT) بصيغة int8.
  - البصمات: 3D-Speaker ERes2Net (Apache-2.0، الافتراضي) أو
    NVIDIA TitaNet Small (CC-BY-4.0، أسرع ~2.7× على المعالج).
"""
from __future__ import annotations

import hashlib
import pathlib
import tarfile
import urllib.request
from collections.abc import Callable

from .errors import MeetingError

MODELS_DIR = pathlib.Path.home() / ".local" / "share" / "arabic-dictate" / "models" / "sherpa"

_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"

SEGMENTATION_URL = f"{_BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
_SEGMENTATION_DIR = "sherpa-onnx-pyannote-segmentation-3-0"
SEGMENTATION_FILE = f"{_SEGMENTATION_DIR}/model.int8.onnx"
SEGMENTATION_SHA256 = "d582f4b4c6b48205de7e0643c57df0df5615a3c176189be3fc461e9d18827b5d"

EMBEDDINGS: dict[str, dict[str, str]] = {
    "eres2net": {
        "url": f"{_BASE}/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
        "file": "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
        "sha256": "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b",
        "title": "3D-Speaker ERes2Net (Apache-2.0)",
    },
    "titanet": {
        "url": f"{_BASE}/speaker-recongition-models/nemo_en_titanet_small.onnx",
        "file": "nemo_en_titanet_small.onnx",
        "sha256": "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e",
        "title": "NVIDIA TitaNet Small (CC-BY-4.0)",
    },
}
DEFAULT_EMBEDDING = "eres2net"

_USER_AGENT = "arabic-dictate/1.0 (+https://github.com/abdulazizaaa/arabic-dictate)"


def segmentation_path() -> pathlib.Path:
    return MODELS_DIR / SEGMENTATION_FILE


def embedding_path(name: str = DEFAULT_EMBEDDING) -> pathlib.Path:
    entry = EMBEDDINGS.get(name)
    if entry is None:
        raise MeetingError(f"نموذج بصمات غير معروف: {name} — المتاح: {', '.join(EMBEDDINGS)}")
    return MODELS_DIR / entry["file"]


def models_ready(embedding: str = DEFAULT_EMBEDDING) -> bool:
    return segmentation_path().exists() and embedding_path(embedding).exists()


def ensure_models(
    embedding: str = DEFAULT_EMBEDDING,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[pathlib.Path, pathlib.Path]:
    """يضمن وجود النماذج محلياً، وينزّلها عند الحاجة، ويتحقق من بصماتها."""
    if embedding not in EMBEDDINGS:
        raise MeetingError(f"نموذج بصمات غير معروف: {embedding} — المتاح: {', '.join(EMBEDDINGS)}")
    if not segmentation_path().exists():
        _fetch_segmentation(on_progress)
    if not embedding_path(embedding).exists():
        _fetch_embedding(embedding, on_progress)
    return segmentation_path(), embedding_path(embedding)


def _fetch_segmentation(on_progress: Callable[[str], None] | None) -> None:
    if on_progress:
        on_progress("ينزّل نموذج تقسيم المتحدثين (pyannote segmentation-3.0 int8)…")
    with _download(SEGMENTATION_URL, on_progress) as archive:
        target = MODELS_DIR.resolve()
        try:
            with tarfile.open(archive, "r:bz2") as tar:
                members = [m for m in tar.getmembers() if m.name.startswith(_SEGMENTATION_DIR + "/")]
                if not members:
                    raise MeetingError("أرشيف التقسيم لا يحتوي المجلد المتوقع")
                for member in members:
                    if ".." in pathlib.PurePosixPath(member.name).parts:
                        raise MeetingError("أرشيف غير آمن")
                tar.extractall(target, members=members)  # noqa: S202 - تحققنا من الأعضاء أعلاه
        except (tarfile.TarError, OSError) as exc:
            raise MeetingError(f"تعذّر فك أرشيف نموذج التقسيم: {exc}") from exc
    _verify(segmentation_path(), SEGMENTATION_SHA256, on_progress)


def _fetch_embedding(name: str, on_progress: Callable[[str], None] | None) -> None:
    entry = EMBEDDINGS[name]
    if on_progress:
        on_progress(f"ينزّل نموذج بصمات المتحدثين ({entry['title']})…")
    with _download(entry["url"], on_progress) as download:
        download.replace(embedding_path(name))
    _verify(embedding_path(name), entry["sha256"], on_progress)


def _download(url: str, on_progress: Callable[[str], None] | None) -> pathlib.Path:
    """ينزّل إلى ملف مؤقت داخل مجلد النماذج ويعيد مساره."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / (url.rsplit("/", 1)[-1] + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310 - رابط ثابت من الإعداد
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            last_percent = -10
            with open(dest, "wb") as out:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if on_progress and total:
                        percent = done * 100 // total
                        if percent >= last_percent + 10:
                            last_percent = percent
                            on_progress(f"التنزيل: {percent}%")
    except OSError as exc:
        dest.unlink(missing_ok=True)
        raise MeetingError(f"تعذّر تنزيل النموذج: {exc}") from exc
    return dest


def _verify(path: pathlib.Path, expected: str, on_progress: Callable[[str], None] | None) -> None:
    if not expected:
        return
    actual = sha256(path)
    if actual != expected:
        path.unlink(missing_ok=True)
        raise MeetingError(
            f"بصمة SHA-256 غير متطابقة لـ {path.name} — حُذف الملف. أعد المحاولة أو أبلغ عن مشكلة."
        )
    if on_progress:
        on_progress(f"✓ {path.name} (بصمة سليمة)")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
