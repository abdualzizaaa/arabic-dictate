"""واجهة الأيقونة الموحّدة.

- لينكس: GTK3 + AyatanaAppIndicator3 — كما كانت الخدمة تماماً.
- ويندوز: pystray (في ``win_tray.PystrayTray``).

الخدمة تنادي: ``update()`` لرسم الحالة، ``notify()`` للإشعارات، و``run()``/``stop()``
لحلقة الواجهة. كل تنفيذ يقرأ حالة الخدمة بنفسه.
"""
from __future__ import annotations

import subprocess
import sys

from . import config as cfg_mod


class TrayUnavailable(RuntimeError):
    """بيئة الأيقونة غير متوفرة (typelib أو مكتبة ناقصة)."""


def create_tray(service):
    if sys.platform == "win32":
        from .win_tray import PystrayTray

        return PystrayTray(service)
    return GtkTray(service)


class GtkTray:
    """أيقونة شريط النظام على لينكس (AppIndicator)."""

    ICON_IDLE = "audio-input-microphone"
    ICON_RECORDING = "media-record"
    ICON_BUSY = "emblem-synchronizing"

    def __init__(self, service) -> None:
        self.service = service
        self._stopped = False
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppIndicator
            from gi.repository import Gtk
        except (ValueError, ImportError) as exc:
            raise TrayUnavailable("مكتبة AyatanaAppIndicator3 غير متوفرة") from exc

        self._Gtk = Gtk
        self._indicator = AppIndicator.Indicator.new(
            "arabic-dictate", self.ICON_IDLE, AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self._indicator.set_title("الإملاء العربي")
        self._menu = self._build_menu()
        self._indicator.set_menu(self._menu)

    # ---------- القائمة ----------
    def _build_menu(self):
        from .engines import ORDER, build

        Gtk = self._Gtk
        service = self.service
        menu = Gtk.Menu()

        self._status_item = Gtk.MenuItem(label="الحالة: جاهز")
        self._status_item.set_sensitive(False)
        menu.append(self._status_item)

        self._toggle_item = Gtk.MenuItem(label="🎙  ابدأ التسجيل")
        self._toggle_item.connect("activate", lambda *_: service.toggle())
        menu.append(self._toggle_item)

        menu.append(Gtk.SeparatorMenuItem())

        engine_root = Gtk.MenuItem(label="المحرّك")
        engine_menu = Gtk.Menu()
        group = []
        for name in ORDER:
            ok, reason = build(name, service.config).available()
            label = cfg_mod.ENGINE_LABELS_AR.get(name, name)
            if not ok:
                label = f"{label} — غير متاح"
            item = Gtk.RadioMenuItem(label=label)
            if group:
                item.join_group(group[0])
            group.append(item)
            item.set_active(name == service.config.get("engine"))
            item.set_sensitive(ok)
            if reason:
                item.set_tooltip_text(reason)
            item.connect("toggled", self._on_engine_toggled, name)
            engine_menu.append(item)
        engine_root.set_submenu(engine_menu)
        menu.append(engine_root)

        copy_item = Gtk.MenuItem(label="📋  انسخ آخر نص")
        copy_item.connect("activate", lambda *_: service._copy_last())
        menu.append(copy_item)

        settings_item = Gtk.MenuItem(label="⚙  ملف الإعدادات")
        settings_item.connect("activate", lambda *_: service._open_settings())
        menu.append(settings_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="خروج")
        quit_item.connect("activate", lambda *_: service.quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _on_engine_toggled(self, item, name: str) -> None:
        if not item.get_active():
            return
        ok, message = self.service.set_engine(name)
        if ok:
            self.service.notify("تم تغيير المحرّك", message)
        self.service._refresh()

    # ---------- الواجهة ----------
    def update(self) -> None:
        if self._stopped:
            return
        state = self.service.state
        if state == "recording":
            self._indicator.set_icon_full(self.ICON_RECORDING, "يسجّل الآن")
        elif state == "working":
            self._indicator.set_icon_full(self.ICON_BUSY, "يحوّل الصوت إلى نص")
        else:
            self._indicator.set_icon_full(self.ICON_IDLE, "جاهز")
        if self._toggle_item is not None:
            if state == "recording":
                self._toggle_item.set_label("⏹  إيقاف وإدراج النص")
            elif state == "working":
                self._toggle_item.set_label("…  جارٍ التحويل")
            else:
                self._toggle_item.set_label("🎙  ابدأ التسجيل")
        if self._status_item is not None:
            self._status_item.set_label(f"الحالة: {self.service._state_ar()}")

    def notify(self, title: str, body: str = "") -> None:
        try:
            subprocess.Popen(
                ["notify-send", "-a", "الإملاء العربي", "-i", "audio-input-microphone", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def run(self) -> None:
        self._Gtk.main()

    def stop(self) -> None:
        self._stopped = True
        self._Gtk.main_quit()
