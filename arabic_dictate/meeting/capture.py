"""تسجيل الاجتماع: الميكروفون + صوت النظام معاً (PulseAudio/PipeWire) عبر ffmpeg."""
from __future__ import annotations

import pathlib
import shutil
import signal
import subprocess

from .errors import MeetingError


def default_monitor() -> str:
    """اسم مراقب مخرج الصوت الافتراضي (ما تسمعه من مكبر الصوت)."""
    if shutil.which("pactl") is None:
        raise MeetingError("pactl غير متوفر — يلزم PulseAudio أو PipeWire للتسجيل")
    proc = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True)
    sink = proc.stdout.strip()
    if proc.returncode != 0 or not sink:
        raise MeetingError("تعذّر تحديد مخرج الصوت الافتراضي (pactl get-default-sink)")
    return f"{sink}.monitor"


def record_meeting(
    out_path: pathlib.Path,
    *,
    input_device: str | None = None,
    sample_rate: int = 16000,
) -> pathlib.Path:
    """يسجّل حتى Ctrl+C ثم ينهي الملف بأمان ويعيد مساره."""
    if shutil.which("ffmpeg") is None:
        raise MeetingError("يلزم ffmpeg للتسجيل — ثبّته: sudo apt install ffmpeg")

    monitor = default_monitor()
    microphone = input_device or "@DEFAULT_SOURCE@"
    out_path = out_path.expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-f", "pulse", "-i", microphone,
        "-f", "pulse", "-i", monitor,
        "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        "-y", str(out_path),
    ]
    proc = subprocess.Popen(command)
    interrupted = False
    try:
        proc.wait()
    except KeyboardInterrupt:
        interrupted = True
        print("\n⏹ إيقاف التسجيل وحفظ الملف…", flush=True)
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    if not interrupted and proc.returncode != 0:
        raise MeetingError(f"فشل ffmpeg أثناء التسجيل (رمز {proc.returncode}) — تحقق من إعدادات الصوت")
    if not out_path.exists() or out_path.stat().st_size <= 44:
        raise MeetingError("لم يُسجَّل شيء — تحقق من الميكروفون ومخرج الصوت")
    return out_path
