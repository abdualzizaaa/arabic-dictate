"""واجهة الأوامر: arabic-dictate <أمر>."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import config as cfg_mod
from .engines import ORDER


def send(command: str, arg: str | None = None, timeout: float = 180.0) -> dict:
    if not cfg_mod.SOCKET_PATH.exists():
        return {"ok": False, "error": "الخفيّة لا تعمل", "offline": True}
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(cfg_mod.SOCKET_PATH))
        client.sendall((json.dumps({"command": command, "arg": arg}, ensure_ascii=False) + "\n").encode())
        payload = b""
        while not payload.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            payload += chunk
        return json.loads(payload.decode("utf-8") or "{}")
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc), "offline": True}
    finally:
        client.close()


def daemon_running() -> bool:
    if not cfg_mod.SOCKET_PATH.exists():
        return False
    response = send("status", timeout=3.0)
    return bool(response.get("ok"))


def spawn_daemon() -> bool:
    cfg_mod.STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(cfg_mod.LOG_PATH, "ab", buffering=0)
    env = dict(os.environ)
    typelib = str(Path.home() / ".local" / "lib" / "girepository-1.0")
    env["GI_TYPELIB_PATH"] = typelib + (os.pathsep + env["GI_TYPELIB_PATH"] if env.get("GI_TYPELIB_PATH") else "")
    subprocess.Popen(
        [sys.executable, "-m", "arabic_dictate.daemon"],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return True


def cmd_ensure(_args: argparse.Namespace) -> int:
    if daemon_running():
        print("الإملاء العربي: يعمل بالفعل")
        return 0
    spawn_daemon()
    for _ in range(40):
        time.sleep(0.1)
        if daemon_running():
            print("الإملاء العربي: بدأ الآن — اضغط أيقونة الميكروفون أو Ctrl+Alt+D")
            return 0
    print("تعذّر تشغيل الخفيّة. راجع:", cfg_mod.LOG_PATH, file=sys.stderr)
    return 1


def cmd_start(_args: argparse.Namespace) -> int:
    cmd_ensure(_args)
    response = send("start")
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


def cmd_stop(_args: argparse.Namespace) -> int:
    response = send("stop")
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


def cmd_toggle(_args: argparse.Namespace) -> int:
    if not daemon_running():
        spawn_daemon()
        time.sleep(1.0)
    response = send("toggle")
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


def cmd_status(_args: argparse.Namespace) -> int:
    response = send("status", timeout=3.0)
    if response.get("offline"):
        print("الحالة: متوقّف (شغّله بـ arabic-dictate ensure)")
        return 1
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def cmd_engine(args: argparse.Namespace) -> int:
    if args.name:
        response = send("engine", args.name)
        print(json.dumps(response, ensure_ascii=False))
        return 0 if response.get("ok") else 1
    response = send("status", timeout=3.0)
    engines = ", ".join(ORDER)
    print(f"المحرّك الحالي: {response.get('engine', '?')}")
    print(f"المتاح: {engines}")
    return 0


def cmd_last(_args: argparse.Namespace) -> int:
    response = send("last", timeout=5.0)
    if not response.get("ok"):
        print(response.get("error", "غير متاح"), file=sys.stderr)
        return 1
    print(response.get("text", ""))
    return 0


def cmd_copy(_args: argparse.Namespace) -> int:
    response = send("copy", timeout=5.0)
    print(response.get("text", "") or response.get("error", ""))
    return 0 if response.get("ok") else 1


def cmd_quit(_args: argparse.Namespace) -> int:
    response = send("quit", timeout=5.0)
    print(json.dumps(response, ensure_ascii=False))
    return 0


def cmd_warmup(args: argparse.Namespace) -> int:
    cmd_ensure(args)
    response = send("warmup", timeout=5.0)
    print(json.dumps(response, ensure_ascii=False))
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    from . import inject
    from .engines import build

    config = cfg_mod.load()
    if args.engine:
        config["engine"] = args.engine
    path = Path(args.file).expanduser()
    if not path.exists():
        print(f"الملف غير موجود: {path}", file=sys.stderr)
        return 1

    engine = build(config.get("engine", ORDER[0]), config)
    ok, reason = engine.available()
    if not ok:
        print(f"المحرّك غير متاح: {reason}", file=sys.stderr)
        return 1

    started = time.time()
    try:
        text = engine.transcribe(str(path), config.get("language", "ar"))
    except Exception as exc:  # noqa: BLE001
        print(f"فشل التحويل: {exc}", file=sys.stderr)
        return 1
    elapsed = time.time() - started

    print(text)
    print(f"\n— {config.get('engine')} · {elapsed:.1f}s", file=sys.stderr)
    if args.inject:
        ok, message = inject.paste(text, config.get("inject_mode", "paste"), config.get("paste_key", "ctrl+shift+v"))
        print(message, file=sys.stderr)
        return 0 if ok else 1
    return 0


def cmd_set_key(args: argparse.Namespace) -> int:
    cfg_mod.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    key = args.key or sys.stdin.read().strip()
    if not key:
        print("لم يُعطَ مفتاح", file=sys.stderr)
        return 1
    cfg_mod.COHERE_KEY_PATH.write_text(key + "\n", encoding="utf-8")
    os.chmod(cfg_mod.COHERE_KEY_PATH, 0o600)
    print(f"حُفظ المفتاح في {cfg_mod.COHERE_KEY_PATH}")
    return 0


def cmd_unload(_args: argparse.Namespace) -> int:
    response = send("unload", timeout=30.0)
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


def cmd_pull(args: argparse.Namespace) -> int:
    from .engines import cohere_local

    settings = dict(cfg_mod.load().get("cohere_local", {}))
    if args.repo:
        settings["repo"] = args.repo
    try:
        path = cohere_local.pull(settings, repo=args.repo, on_progress=lambda msg: print(f"▶ {msg}", flush=True))
    except Exception as exc:  # noqa: BLE001
        print(f"تعذّر التنزيل: {exc}", file=sys.stderr)
        return 1
    print(f"✓ النموذج في: {path}")
    print("المحرّك جاهز — بدّله بـ: arabic-dictate engine cohere-local")
    return 0


def cmd_meeting_setup(_args: argparse.Namespace) -> int:
    from .meeting.errors import MeetingError
    from .meeting.models import ensure_models

    config = cfg_mod.load()
    embedding = str((config.get("meeting") or {}).get("embedding") or "eres2net")
    try:
        segmentation, embed_path = ensure_models(embedding, on_progress=lambda msg: print(f"▶ {msg}", flush=True))
    except MeetingError as exc:
        print(f"تعذّر تجهيز نماذج التمييز: {exc}", file=sys.stderr)
        return 1
    print("✓ نماذج تمييز المتحدثين جاهزة:")
    print(f"  التقسيم: {segmentation}")
    print(f"  البصمات: {embed_path}")
    return 0


def cmd_meeting_record(args: argparse.Namespace) -> int:
    from .meeting.capture import record_meeting
    from .meeting.errors import MeetingError

    config = cfg_mod.load()
    if args.out:
        out = Path(args.out).expanduser()
    else:
        out = Path(f"meeting-{time.strftime('%Y%m%d-%H%M%S')}.wav")
    print(f"▶ يسجّل الآن (الميكروفون + صوت النظام) → {out}", flush=True)
    print("  للإيقاف: Ctrl+C", flush=True)
    try:
        result = record_meeting(out, input_device=config.get("input_device"))
    except MeetingError as exc:
        print(f"تعذّر التسجيل: {exc}", file=sys.stderr)
        return 1
    print(f"✓ حُفظ التسجيل: {result}")
    print(f"  للتفريغ: arabic-dictate meeting transcribe {result}")
    return 0


def cmd_meeting_transcribe(args: argparse.Namespace) -> int:
    from .meeting import render
    from .meeting.errors import MeetingError
    from .meeting.pipeline import transcribe_meeting

    config = cfg_mod.load()
    meeting_cfg = config.get("meeting") or {}
    template = str(meeting_cfg.get("label_template") or "المتحدث {n}")

    announced = {"diarize": False}

    def on_progress(stage: str, current: int, total: int) -> None:
        if stage == "diarize":
            if not announced["diarize"]:
                announced["diarize"] = True
                print("▶ يحدّد المتحدثين…", flush=True)
        elif stage == "transcribe":
            if current < total:
                print(f"\r▶ يفرّغ المقاطع: {current + 1}/{total}", end="", flush=True)
            else:
                print(f"\r▶ اكتمل تفريغ {total} مقطع.   ", flush=True)

    try:
        result = transcribe_meeting(
            args.file,
            config=config,
            engine_name=args.engine,
            speakers=args.speakers,
            keep_segments=meeting_cfg.get("keep_segments", False),
            on_progress=on_progress,
        )
    except MeetingError as exc:
        print(f"فشل التفريغ: {exc}", file=sys.stderr)
        return 1

    if not result.segments:
        print("لم يُنتج التفريغ أي نص.", file=sys.stderr)
        return 1

    if args.out:
        outdir = Path(args.out).expanduser()
    elif meeting_cfg.get("output_dir"):
        outdir = Path(str(meeting_cfg["output_dir"])).expanduser()
    else:
        outdir = Path.cwd()
    outdir.mkdir(parents=True, exist_ok=True)

    stem = Path(args.file).stem
    written: list[Path] = []
    text_path = outdir / f"{stem}-transcript.txt"
    text_path.write_text(render.render_txt(result, template), encoding="utf-8")
    written.append(text_path)
    json_path = outdir / f"{stem}-transcript.json"
    json_path.write_text(render.render_json(result, template), encoding="utf-8")
    written.append(json_path)
    if args.format == "srt":
        srt_path = outdir / f"{stem}-transcript.srt"
        srt_path.write_text(render.render_srt(result, template), encoding="utf-8")
        written.append(srt_path)
    elif args.format == "md":
        md_path = outdir / f"{stem}-transcript.md"
        md_path.write_text(render.render_markdown(result, template), encoding="utf-8")
        written.append(md_path)

    print()
    render.print_result(result, template)
    print("\nالملفات:")
    for path in written:
        print(f"  {path}")
    if result.segments_dir is not None:
        print(f"  (مقاطع صوتية محفوظة في: {result.segments_dir})")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    from .engines import build

    config = cfg_mod.load()
    print("— الفحص البيئي —")
    checks = {
        "arecord": subprocess.run(["which", "arecord"], capture_output=True).returncode == 0,
        "xdotool": subprocess.run(["which", "xdotool"], capture_output=True).returncode == 0,
        "xclip": subprocess.run(["which", "xclip"], capture_output=True).returncode == 0,
        "notify-send": subprocess.run(["which", "notify-send"], capture_output=True).returncode == 0,
        "X11": bool(os.environ.get("DISPLAY")),
    }
    try:
        import gi  # noqa: F401

        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        checks["indicator"] = True
    except Exception:  # noqa: BLE001
        checks["indicator"] = False
    checks["daemon"] = daemon_running()

    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")

    print("\n— المحرّكات —")
    for name in ORDER:
        engine = build(name, config)
        ok, reason = engine.available()
        label = cfg_mod.ENGINE_LABELS_AR.get(name, name)
        print(f"  {'✓' if ok else '✗'} {name} ({label}){'' if ok else ' — ' + reason}")

    print(f"\nالمحرّك النشط: {config.get('engine')}")
    print(f"الإعدادات: {cfg_mod.ensure_config_file()}")

    print("\n— الاجتماعات —")
    import shutil as _shutil

    from .meeting import models as meeting_models

    try:
        import sherpa_onnx  # noqa: F401

        has_sherpa = True
    except ImportError:
        has_sherpa = False
    embedding = str((config.get("meeting") or {}).get("embedding") or "eres2net")
    meeting_checks = {
        "sherpa-onnx (تمييز المتحدثين)": has_sherpa,
        "ffmpeg (تحويل وتفريغ الصيغ)": _shutil.which("ffmpeg") is not None,
        "pactl (تسجيل صوت النظام)": _shutil.which("pactl") is not None,
        "نماذج التمييز منزّلة": meeting_models.models_ready(embedding),
    }
    for name, ok in meeting_checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    if not all(meeting_checks.values()):
        print('  (جهّزها بـ: pip install "arabic-dictate[meeting]" ثم: arabic-dictate meeting setup)')
    return 0


def cmd_reload(_args: argparse.Namespace) -> int:
    response = send("reload", timeout=5.0)
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arabic-dictate",
        description="إملاء صوتي عربي يكتب في الطرفية عند المؤشر",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ensure", help="شغّل الخفيّة إن لم تكن تعمل").set_defaults(func=cmd_ensure)
    sub.add_parser("start", help="ابدأ التسجيل").set_defaults(func=cmd_start)
    sub.add_parser("stop", help="أوقف التسجيل وحوّل").set_defaults(func=cmd_stop)
    sub.add_parser("toggle", help="بدّل بين التسجيل والإيقاف").set_defaults(func=cmd_toggle)
    sub.add_parser("status", help="حالة الخفيّة").set_defaults(func=cmd_status)
    sub.add_parser("last", help="اطبع آخر نص").set_defaults(func=cmd_last)
    sub.add_parser("copy", help="انسخ آخر نص").set_defaults(func=cmd_copy)
    sub.add_parser("quit", help="أوقف الخفيّة").set_defaults(func=cmd_quit)
    sub.add_parser("warmup", help="حمّل النموذج مسبقاً").set_defaults(func=cmd_warmup)
    sub.add_parser("unload", help="حرّر ذاكرة النموذج المحمّل").set_defaults(func=cmd_unload)
    sub.add_parser("doctor", help="افحص البيئة والمحرّكات").set_defaults(func=cmd_doctor)
    sub.add_parser("reload", help="أعد تحميل الإعدادات").set_defaults(func=cmd_reload)

    pull_parser = sub.add_parser("pull", help="نزّل نموذج كوهير العربي المحلي (≈3GB)")
    pull_parser.add_argument("--repo", help="مستودع Hugging Face بديل")
    pull_parser.set_defaults(func=cmd_pull)

    engine_parser = sub.add_parser("engine", help="اعرض أو غيّر المحرّك")
    engine_parser.add_argument("name", nargs="?", help=", ".join(ORDER))
    engine_parser.set_defaults(func=cmd_engine)

    transcribe_parser = sub.add_parser("transcribe", help="حوّل ملف صوتي إلى نص")
    transcribe_parser.add_argument("file")
    transcribe_parser.add_argument("--engine", choices=ORDER)
    transcribe_parser.add_argument("--inject", action="store_true", help="الصق النص في النافذة النشطة")
    transcribe_parser.set_defaults(func=cmd_transcribe)

    key_parser = sub.add_parser("set-key", help="احفظ مفتاح Cohere API")
    key_parser.add_argument("key", nargs="?", help="اتركه فارغاً للقراءة من stdin")
    key_parser.set_defaults(func=cmd_set_key)

    meeting_parser = sub.add_parser("meeting", help="تفريغ الاجتماعات مع تمييز المتحدثين")
    meeting_sub = meeting_parser.add_subparsers(dest="meeting_command", required=True)

    meeting_setup = meeting_sub.add_parser("setup", help="نزّل نماذج تمييز المتحدثين (~45MB)")
    meeting_setup.set_defaults(func=cmd_meeting_setup)

    meeting_record = meeting_sub.add_parser("record", help="سجّل اجتماعاً (ميكروفون + صوت النظام)")
    meeting_record.add_argument("--out", "-o", help="ملف الخرج (افتراضي: meeting-<التاريخ>.wav)")
    meeting_record.set_defaults(func=cmd_meeting_record)

    meeting_transcribe = meeting_sub.add_parser("transcribe", help="فرّغ تسجيلاً مع تمييز المتحدثين")
    meeting_transcribe.add_argument("file")
    meeting_transcribe.add_argument("--speakers", type=int, default=0, help="عدد المتحدثين إن عرفته (0 = تلقائي)")
    meeting_transcribe.add_argument("--engine", choices=ORDER, help="محرّك التحويل (افتراضياً محرّك الإملاء)")
    meeting_transcribe.add_argument("--format", choices=["txt", "srt", "md"], default="txt", help="صيغة إضافية للحفظ")
    meeting_transcribe.add_argument("--out", "-o", help="مجلد الخرج")
    meeting_transcribe.set_defaults(func=cmd_meeting_transcribe)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
