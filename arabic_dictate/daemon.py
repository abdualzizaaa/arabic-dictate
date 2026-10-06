"""الخفيّة: أيقونة في شريط النظام + مقبس تحكّم + التسجيل والتحويل والإدراج.

طبقة المنصّة: الواجهة (الأيقونة) في ``tray.py``، والنقل في ``ipc.py``،
والمكوّنات المتبقية (تسجيل/اختصار/لصق) تُختار حسب المنصّة عبر مصانع.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import audio, inject, ipc
from . import config as cfg_mod
from .engines import ORDER, EngineError, build
from .hotkey import create_listener
from .textfilters import looks_like_hallucination
from .tray import create_tray

_GLIB = None


def _glib():
    """GLib على لينكس (يُحمَّل عند أول استخدام فقط)؛ None على ويندوز."""
    global _GLIB
    if _GLIB is None and sys.platform != "win32":
        from gi.repository import GLib

        _GLIB = GLib
    return _GLIB


class _Dispatch:
    """يجسّر تحديثات الواجهة إلى خيطها:

    على لينكس عبر GLib (idle/timeout) كما كان، وعلى ويندوز مباشرةً —
    الواجهة هناك (pystray) تُحمى بأقفال الخدمة.
    """

    def call_soon(self, fn, *args) -> None:
        glib = _glib()
        if glib is not None:
            glib.idle_add(fn, *args)
        else:
            fn(*args)

    def call_later(self, seconds: float, fn) -> None:
        glib = _glib()
        if glib is not None:
            glib.timeout_add(int(seconds * 1000), lambda: (fn(), False)[1])
        else:
            timer = threading.Timer(seconds, fn)
            timer.daemon = True
            timer.start()

    def every(self, seconds: float, fn) -> None:
        glib = _glib()
        if glib is not None:
            glib.timeout_add_seconds(int(seconds), lambda: (fn(), True)[1])
        else:

            def loop() -> None:
                while True:
                    time.sleep(seconds)
                    try:
                        fn()
                    except Exception:  # noqa: BLE001
                        pass

            threading.Thread(target=loop, daemon=True, name="ticker").start()


class DictationService:
    def __init__(self) -> None:
        self.config = cfg_mod.load()
        self.recorder = audio.create_recorder(self.config.get("input_device"))
        self.state = "idle"  # idle | recording | working
        self.last_text = ""
        self.last_engine = ""
        self.last_error = ""
        self._engine = None
        self._tray = None
        self._hotkey = None
        self._server = None
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._quitting = False
        self._dispatch = _Dispatch()

    # ---------- المحرّك ----------
    @property
    def engine(self):
        name = self.config.get("engine", ORDER[0])
        if self._engine is None or self._engine.name != name:
            chosen = build(name, self.config)
            ok, reason = chosen.available()
            if not ok:
                # لا نترك المستخدم بلا إملاء: ننتقل مؤقتاً لأول محرّك متاح
                for alternative in ORDER:
                    if alternative == name:
                        continue
                    candidate = build(alternative, self.config)
                    if candidate.available()[0]:
                        chosen = candidate
                        self.notify(
                            "تعذّر تشغيل المحرّك المطلوب",
                            f"{reason}\nانتقلت مؤقتاً إلى: {cfg_mod.ENGINE_LABELS_AR.get(alternative, alternative)}",
                        )
                        break
            self._engine = chosen
        return self._engine

    def set_engine(self, name: str) -> tuple[bool, str]:
        if name not in ORDER:
            return False, f"محرّك غير معروف: {name}"
        self.config["engine"] = name
        cfg_mod.save(self.config)
        self._engine = None
        return True, cfg_mod.ENGINE_LABELS_AR.get(name, name)

    # ---------- التسجيل ----------
    def toggle(self) -> str:
        if self.state == "recording":
            return self.stop_recording()
        if self.state == "working":
            return "التحويل جارٍ الآن…"
        return self.start_recording()

    def start_recording(self) -> str:
        with self._lock:
            if self.state != "idle":
                return "مشغول"
            try:
                self.recorder.start()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                self.notify("تعذّر بدء التسجيل", str(exc))
                return f"خطأ: {exc}"
            self.state = "recording"
        self._refresh()
        self.notify("🎙 تكلّم الآن", "اضغط الأيقونة مرة أخرى للإيقاف والإدراج")
        return "recording"

    def stop_recording(self) -> str:
        with self._lock:
            if self.state != "recording":
                return "لا يوجد تسجيل"
            self.state = "working"
        self._refresh()
        # إيقاف arecord قد يستغرق ثوانيَ في أسوأ الحالات — يجري خارج خيط الواجهة
        threading.Thread(target=self._stop_worker, daemon=True).start()
        return "transcribing"

    def _stop_worker(self) -> None:
        wav = self.recorder.stop()
        if wav is None:
            with self._lock:
                self.state = "idle"
            self._refresh()
            self.notify("لم يُسجَّل صوت", "تحقّق من الميكروفون")
            return
        self._transcribe_worker(str(wav))

    # ---------- التحويل ----------
    def _transcribe_worker(self, wav_path: str) -> None:
        try:
            self._transcribe(wav_path)
        finally:
            if not self.config.get("keep_audio", False):
                Path(wav_path).unlink(missing_ok=True)

    def _transcribe(self, wav_path: str) -> None:
        engine = self.engine
        engine_name = engine.name
        started = time.time()
        try:
            ok, info = (True, {})
            if self.config.get("vad_min_secs", 0.35) > 0:
                ok, info = audio.trim_silence(
                    wav_path,
                    int(self.config.get("vad_threshold", 260)),
                    float(self.config.get("vad_min_secs", 0.35)),
                )
                if not ok:
                    reason = info.get("reason")
                    message = (
                        "لم أسمع كلاماً — الصوت هادئ جداً"
                        if reason in {"silent", "empty"}
                        else "المقطع قصير جداً"
                    )
                    self._dispatch.call_soon(self._finish, None, message, engine_name, 0.0)
                    return

            text = engine.transcribe(wav_path, self.config.get("language", "ar"))
            elapsed = time.time() - started
            if not text:
                self._dispatch.call_soon(self._finish, None, "لم يُنتج المحرّك أي نص", engine_name, elapsed)
                return
            if looks_like_hallucination(text):
                self._dispatch.call_soon(
                    self._finish,
                    None,
                    f"سمعت ضجيجاً لا كلاماً (تجاهلت: {text.strip()[:40]})",
                    engine_name,
                    elapsed,
                )
                return
            self._dispatch.call_soon(self._finish, text, None, engine_name, elapsed)
        except EngineError as exc:
            self._dispatch.call_soon(self._finish, None, str(exc), engine_name, time.time() - started)
        except Exception as exc:  # noqa: BLE001
            self._dispatch.call_soon(self._finish, None, f"خطأ غير متوقع: {exc}", engine_name, time.time() - started)

    def _finish(self, text: str | None, error: str | None, engine_name: str, elapsed: float) -> bool:
        with self._lock:
            self.state = "idle"
        self.last_engine = engine_name
        if error:
            self.last_error = error
            self.notify("تعذّر التحويل", error[:220])
            self._refresh()
            return False

        self.last_text = text or ""
        self.last_error = ""
        if self.config.get("trailing_space", True) and self.last_text and not self.last_text.endswith(" "):
            self.last_text += " "

        # الإدراج في خيط منفصل حتى لا تتجمّد واجهة الأيقونة والمقبس أبداً
        threading.Thread(
            target=self._inject_worker,
            args=(self.last_text, engine_name, elapsed),
            daemon=True,
        ).start()
        self._refresh()
        return False

    def _inject_worker(self, text: str, engine_name: str, elapsed: float) -> None:
        mode = self.config.get("inject_mode", "paste")
        ok, message = inject.paste(text, mode, self.config.get("paste_key", "ctrl+shift+v"))
        label = cfg_mod.ENGINE_LABELS_AR.get(engine_name, engine_name)
        if ok:
            self.notify(
                "✅ النص جاهز — راجعه ثم أرسل",
                f"{label} · {elapsed:.1f}s · {message}",
            )
        else:
            self.notify("تم التحويل لكن فشل الإدراج", message)

    # ---------- الإشعارات ----------
    def notify(self, title: str, body: str = "") -> None:
        if not self.config.get("notify", True) or self._tray is None:
            return
        self._tray.notify(title, body)

    # ---------- الواجهة ----------
    def _refresh(self) -> None:
        self._dispatch.call_soon(self._paint)

    def _paint(self) -> None:
        if self._quitting or self._tray is None:
            return
        self._tray.update()

    def _state_ar(self) -> str:
        if self.state == "recording":
            return f"يسجّل ({self.recorder.elapsed:.0f} ث)"
        if self.state == "working":
            return "يحوّل…"
        return "جاهز"

    def _copy_last(self) -> None:
        if not self.last_text:
            self.notify("لا يوجد نص بعد", "سجّل أولاً")
            return
        inject.set_clipboard(self.last_text)
        self.notify("نُسخ آخر نص", self.last_text[:120])

    def _open_settings(self) -> None:
        path = cfg_mod.ensure_config_file()
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - يفتح ملف الإعدادات بالمحرّر الافتراضي
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------- المقبس ----------
    def _handle_command(self, request: dict) -> dict:
        command = str(request.get("command", "status")).lower()
        arg = request.get("arg")

        if command == "status":
            return {
                "ok": True,
                "state": self.state,
                "engine": self.config.get("engine"),
                "engine_label": cfg_mod.ENGINE_LABELS_AR.get(self.config.get("engine", ""), ""),
                "last_text": self.last_text,
                "last_engine": self.last_engine,
                "last_error": self.last_error,
                "uptime": round(time.time() - self._started_at, 1),
            }
        if command == "toggle":
            return {"ok": True, "action": self.toggle(), "state": self.state}
        if command == "start":
            return {"ok": True, "action": self.start_recording(), "state": self.state}
        if command == "stop":
            return {"ok": True, "action": self.stop_recording(), "state": self.state}
        if command == "engine":
            if arg:
                ok, message = self.set_engine(str(arg))
                self._refresh()
                return {"ok": ok, "message": message, "engine": self.config.get("engine")}
            return {"ok": True, "engine": self.config.get("engine")}
        if command == "last":
            return {"ok": True, "text": self.last_text, "engine": self.last_engine}
        if command == "copy":
            self._copy_last()
            return {"ok": True, "text": self.last_text}
        if command == "warmup":
            name = self.config.get("engine")
            threading.Thread(target=lambda: self._warmup(name), daemon=True).start()
            return {"ok": True, "message": f"يحمّل محرّك {name} في الخلفية"}
        if command == "unload":
            if self.state != "idle":
                return {"ok": False, "message": "لا يمكن التحرير أثناء التسجيل أو التحويل"}
            freed = bool(self._engine and self._engine.unload())
            self._engine = None
            return {
                "ok": True,
                "message": "حُرّرت ذاكرة النموذج — سيُعاد التحميل عند أول استخدام" if freed else "لا يوجد نموذج محمّل",
            }
        if command == "reload":
            self.config = cfg_mod.load()
            # نُبقي النموذج محمّلاً إن لم يتغيّر المحرّك (تجنّب إعادة تحميل بطيئة)
            if self._engine is not None and self._engine.name != self.config.get("engine"):
                self._engine = None
            if not self.recorder.recording:
                self.recorder = audio.create_recorder(self.config.get("input_device"))
            self._refresh()
            return {"ok": True, "message": "أُعيد تحميل الإعدادات"}
        if command == "quit":
            self._dispatch.call_soon(self.quit)
            return {"ok": True, "message": "إلى اللقاء"}
        return {"ok": False, "error": f"أمر غير معروف: {command}"}

    def _warmup(self, name: str) -> None:
        try:
            # نُسخّن المحرّك الحقيقي المستخدم للتحويل، لا نسخة مؤقتة تُهمَل
            engine = self.engine
            engine.warmup()
            self.notify("المحرّك جاهز", cfg_mod.ENGINE_LABELS_AR.get(engine.name, name))
        except Exception as exc:  # noqa: BLE001
            self.notify("تعذّر التحميل المسبق", str(exc)[:200])

    # ---------- المقبس (خيط موحّد يعمل على المنصتين) ----------
    def _start_socket(self) -> bool:
        try:
            server = ipc.start_server()
        except ipc.AlreadyRunningError:
            return False
        self._server = server
        server.setblocking(True)
        threading.Thread(target=self._serve_forever, daemon=True, name="ipc-server").start()
        return True

    def _serve_forever(self) -> None:
        server = self._server
        if server is None:
            return
        while not self._quitting:
            try:
                conn, _ = server.accept()
            except OSError:
                break
            with conn:
                conn.settimeout(5.0)
                try:
                    payload = b""
                    while not payload.endswith(b"\n") and len(payload) < 65536:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        payload += chunk
                    request = json.loads(payload.decode("utf-8") or "{}")
                    if not ipc.authorized(request):
                        response = {"ok": False, "error": "غير مصرّح"}
                    else:
                        response = self._handle_command(request)
                except Exception as exc:  # noqa: BLE001
                    response = {"ok": False, "error": str(exc)}
                try:
                    conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
                except OSError:
                    pass

    # ---------- التشغيل ----------
    def quit(self) -> bool:
        self._quitting = True
        try:
            if self.recorder.recording:
                self.recorder.stop()
            if self._hotkey:
                self._hotkey.stop()
            if self._server:
                self._server.close()
            ipc.cleanup_server()
        except Exception:  # noqa: BLE001
            pass
        if self._tray is not None:
            self._tray.stop()
        return False

    def run(self) -> int:
        try:
            self._tray = create_tray(self)
        except RuntimeError as exc:
            print(f"خطأ: {exc}", flush=True)
            return 2

        audio.sweep_temp_files()

        if not self._start_socket():
            print("هناك خفيّة تعمل بالفعل — لا حاجة لتشغيل ثانية.", flush=True)
            return 3

        if self.config.get("hotkey_enabled", True):
            self._hotkey = create_listener(self.config.get("hotkey", "ctrl+alt+d"), self._on_hotkey)
            self._hotkey.start()
            self._dispatch.call_later(0.9, self._check_hotkey)

        self._refresh()
        self.notify("الإملاء العربي يعمل", "اضغط أيقونة الميكروفون أو Ctrl+Alt+D")
        self._dispatch.every(1, self._tick)
        self._tray.run()
        return 0

    def _on_hotkey(self) -> None:
        self._dispatch.call_soon(self._hotkey_toggle)

    def _hotkey_toggle(self) -> bool:
        self.toggle()
        return False

    def _check_hotkey(self) -> bool:
        error = getattr(self._hotkey, "error", None)
        if error:
            print(f"تحذير: تعذّر تفعيل الاختصار العالمي: {error}", flush=True)
            self.notify(
                "تعذّر تفعيل الاختصار العالمي",
                f"{error}\nاستخدم الأيقونة، أو غيّر hotkey من الإعدادات",
            )
        return False

    def _tick(self) -> bool:
        if self.state == "recording":
            self._refresh()
        return True


def main() -> int:
    return DictationService().run()


if __name__ == "__main__":
    raise SystemExit(main())
