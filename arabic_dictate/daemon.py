"""الخفيّة: أيقونة في شريط النظام + مقبس تحكّم + التسجيل والتحويل والإدراج."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk  # noqa: E402

from . import audio, inject  # noqa: E402
from . import config as cfg_mod  # noqa: E402
from .engines import ORDER, EngineError, build  # noqa: E402
from .hotkey import HotkeyListener  # noqa: E402
from .textfilters import looks_like_hallucination  # noqa: E402

try:  # pragma: no cover - يعتمد على وجود الـ typelib
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except (ValueError, ImportError):  # pragma: no cover
    AppIndicator = None

APP_ID = "arabic-dictate"
ICON_IDLE = "audio-input-microphone"
ICON_RECORDING = "media-record"
ICON_BUSY = "emblem-synchronizing"


class DictationService:
    def __init__(self) -> None:
        self.config = cfg_mod.load()
        self.recorder = audio.Recorder(self.config.get("input_device"))
        self.state = "idle"  # idle | recording | working
        self.last_text = ""
        self.last_engine = ""
        self.last_error = ""
        self._engine = None
        self._indicator = None
        self._menu = None
        self._toggle_item = None
        self._status_item = None
        self._hotkey: HotkeyListener | None = None
        self._server: socket.socket | None = None
        self._lock = threading.Lock()
        self._started_at = time.time()

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
                    GLib.idle_add(self._finish, None, message, engine_name, 0.0)
                    return

            text = engine.transcribe(wav_path, self.config.get("language", "ar"))
            elapsed = time.time() - started
            if not text:
                GLib.idle_add(self._finish, None, "لم يُنتج المحرّك أي نص", engine_name, elapsed)
                return
            if looks_like_hallucination(text):
                GLib.idle_add(
                    self._finish,
                    None,
                    f"سمعت ضجيجاً لا كلاماً (تجاهلت: {text.strip()[:40]})",
                    engine_name,
                    elapsed,
                )
                return
            GLib.idle_add(self._finish, text, None, engine_name, elapsed)
        except EngineError as exc:
            GLib.idle_add(self._finish, None, str(exc), engine_name, time.time() - started)
        except Exception as exc:  # noqa: BLE001
            GLib.idle_add(self._finish, None, f"خطأ غير متوقع: {exc}", engine_name, time.time() - started)

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
        if not self.config.get("notify", True):
            return
        try:
            subprocess.Popen(
                ["notify-send", "-a", "الإملاء العربي", "-i", "audio-input-microphone", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    # ---------- القائمة ----------
    def _refresh(self) -> None:
        def update() -> bool:
            if self._indicator is None:
                return False
            if self.state == "recording":
                self._indicator.set_icon_full(ICON_RECORDING, "يسجّل الآن")
            elif self.state == "working":
                self._indicator.set_icon_full(ICON_BUSY, "يحوّل الصوت إلى نص")
            else:
                self._indicator.set_icon_full(ICON_IDLE, "جاهز")
            if self._toggle_item is not None:
                if self.state == "recording":
                    self._toggle_item.set_label("⏹  إيقاف وإدراج النص")
                elif self.state == "working":
                    self._toggle_item.set_label("…  جارٍ التحويل")
                else:
                    self._toggle_item.set_label("🎙  ابدأ التسجيل")
            if self._status_item is not None:
                self._status_item.set_label(f"الحالة: {self._state_ar()}")
            return False

        GLib.idle_add(update)

    def _state_ar(self) -> str:
        if self.state == "recording":
            return f"يسجّل ({self.recorder.elapsed:.0f} ث)"
        if self.state == "working":
            return "يحوّل…"
        return "جاهز"

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        self._status_item = Gtk.MenuItem(label="الحالة: جاهز")
        self._status_item.set_sensitive(False)
        menu.append(self._status_item)

        self._toggle_item = Gtk.MenuItem(label="🎙  ابدأ التسجيل")
        self._toggle_item.connect("activate", lambda *_: self.toggle())
        menu.append(self._toggle_item)

        menu.append(Gtk.SeparatorMenuItem())

        engine_root = Gtk.MenuItem(label="المحرّك")
        engine_menu = Gtk.Menu()
        group: list[Gtk.RadioMenuItem] = []
        for name in ORDER:
            ok, reason = build(name, self.config).available()
            label = cfg_mod.ENGINE_LABELS_AR.get(name, name)
            if not ok:
                label = f"{label} — غير متاح"
            item = Gtk.RadioMenuItem(label=label)
            if group:
                item.join_group(group[0])
            group.append(item)
            item.set_active(name == self.config.get("engine"))
            item.set_sensitive(ok)
            if reason:
                item.set_tooltip_text(reason)
            item.connect("toggled", self._on_engine_toggled, name)
            engine_menu.append(item)
        engine_root.set_submenu(engine_menu)
        menu.append(engine_root)

        copy_item = Gtk.MenuItem(label="📋  انسخ آخر نص")
        copy_item.connect("activate", lambda *_: self._copy_last())
        menu.append(copy_item)

        settings_item = Gtk.MenuItem(label="⚙  ملف الإعدادات")
        settings_item.connect("activate", lambda *_: self._open_settings())
        menu.append(settings_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="خروج")
        quit_item.connect("activate", lambda *_: self.quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _on_engine_toggled(self, item: Gtk.RadioMenuItem, name: str) -> None:
        if not item.get_active():
            return
        ok, message = self.set_engine(name)
        if ok:
            self.notify("تم تغيير المحرّك", message)
        self._refresh()

    def _copy_last(self) -> None:
        if not self.last_text:
            self.notify("لا يوجد نص بعد", "سجّل أولاً")
            return
        inject.set_clipboard(self.last_text)
        self.notify("نُسخ آخر نص", self.last_text[:120])

    def _open_settings(self) -> None:
        path = cfg_mod.ensure_config_file()
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
                self.recorder = audio.Recorder(self.config.get("input_device"))
            self._refresh()
            return {"ok": True, "message": "أُعيد تحميل الإعدادات"}
        if command == "quit":
            GLib.idle_add(self.quit)
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

    def _serve_socket(self, server: socket.socket) -> bool:
        try:
            conn, _ = server.accept()
        except BlockingIOError:
            return True
        except OSError:
            return False
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
                response = self._handle_command(request)
            except Exception as exc:  # noqa: BLE001
                response = {"ok": False, "error": str(exc)}
            try:
                conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            except OSError:
                pass
        return True

    def _start_socket(self) -> bool:
        if cfg_mod.SOCKET_PATH.exists():
            # إن كان المقبس القديم يستجيب فهناك خفيّة حيّة — لا نسحقها
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(1.0)
            alive = False
            try:
                probe.connect(str(cfg_mod.SOCKET_PATH))
                alive = True
            except OSError:
                pass
            finally:
                probe.close()
            if alive:
                return False
            cfg_mod.SOCKET_PATH.unlink(missing_ok=True)
        try:
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(cfg_mod.SOCKET_PATH))
        except OSError:
            return False
        os.chmod(cfg_mod.SOCKET_PATH, 0o600)
        server.listen(8)
        server.setblocking(False)
        self._server = server
        GLib.io_add_watch(server, GLib.IO_IN, lambda *_: self._serve_socket(server))
        return True

    # ---------- التشغيل ----------
    def quit(self) -> bool:
        try:
            if self.recorder.recording:
                self.recorder.stop()
            if self._hotkey:
                self._hotkey.stop()
            if self._server:
                self._server.close()
            cfg_mod.SOCKET_PATH.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        Gtk.main_quit()
        return False

    def run(self) -> int:
        if AppIndicator is None:
            print("خطأ: مكتبة AyatanaAppIndicator3 غير متوفرة", flush=True)
            return 2

        audio.sweep_temp_files()

        self._indicator = AppIndicator.Indicator.new(
            APP_ID, ICON_IDLE, AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self._indicator.set_title("الإملاء العربي")
        self._menu = self._build_menu()
        self._indicator.set_menu(self._menu)

        if not self._start_socket():
            print("هناك خفيّة تعمل بالفعل — لا حاجة لتشغيل ثانية.", flush=True)
            return 3

        if self.config.get("hotkey_enabled", True):
            self._hotkey = HotkeyListener(self.config.get("hotkey", "ctrl+alt+d"), self._on_hotkey)
            self._hotkey.start()
            GLib.timeout_add(900, self._check_hotkey)

        self._refresh()
        self.notify("الإملاء العربي يعمل", "اضغط أيقونة الميكروفون أو Ctrl+Alt+D")
        GLib.timeout_add_seconds(1, self._tick)
        Gtk.main()
        return 0

    def _on_hotkey(self) -> None:
        GLib.idle_add(self._hotkey_toggle)

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
