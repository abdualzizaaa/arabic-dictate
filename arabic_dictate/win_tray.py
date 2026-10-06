"""أيقونة ويندوز في شريط المهام عبر pystray (نظير GtkTray على لينكس)."""
from __future__ import annotations

from . import config as cfg_mod


def make_image(state: str):
    """أيقونة دائرية ملوّنة بحالة الخدمة (بلا ملفات صور خارجية)."""
    from PIL import Image, ImageDraw

    colors = {
        "recording": (198, 40, 40, 255),
        "working": (249, 168, 37, 255),
        "idle": (46, 125, 50, 255),
    }
    color = colors.get(state, (120, 120, 120, 255))
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=color)
    draw.rounded_rectangle((26, 13, 38, 37), radius=6, fill=(255, 255, 255, 255))
    draw.arc((20, 28, 44, 48), start=0, end=180, fill=(255, 255, 255, 255), width=3)
    draw.line((32, 46, 32, 56), fill=(255, 255, 255, 255), width=3)
    return image


class PystrayTray:
    """أيقونة pystray — تُحدَّث من خيوط العمال (محميّة بـ try/except وأقفال الخدمة)."""

    def __init__(self, service) -> None:
        try:
            import pystray
        except ImportError as exc:
            raise RuntimeError(
                'مكتبة pystray غير مثبّتة — ثبّتها بالأمر: pip install "arabic-dictate[windows]"'
            ) from exc

        from .engines import ORDER, build

        self._pystray = pystray
        self.service = service
        self._stopped = False
        self._engine_info: dict[str, tuple[bool, str]] = {}
        for name in ORDER:
            ok, reason = build(name, service.config).available()
            self._engine_info[name] = (ok, reason)

        Menu = pystray.Menu
        Item = pystray.MenuItem

        def engine_item(name: str):
            # ملاحظة: pystray يتحقق من توقيع دوال الأحداث (وسيطان فقط)، لذا نستخدم إغلاقات
            def on_click(icon, item):
                self._on_engine(name)

            def label(item):
                return self._engine_label(name)

            def checked(item):
                return self.service.config.get("engine") == name

            return Item(
                label,
                on_click,
                radio=True,
                checked=checked,
                enabled=self._engine_info[name][0],
            )

        engine_items = [engine_item(name) for name in ORDER]
        self.icon = pystray.Icon(
            "arabic-dictate",
            icon=make_image("idle"),
            title="الإملاء العربي",
            menu=Menu(
                Item(lambda item: self._status_text(), lambda icon, item: None, enabled=False),
                Item(lambda item: self._toggle_text(), lambda icon, item: self._on_toggle()),
                Menu.SEPARATOR,
                Item("المحرّك", Menu(*engine_items)),
                Item("📋  انسخ آخر نص", lambda icon, item: self.service._copy_last()),
                Item("⚙  ملف الإعدادات", lambda icon, item: self.service._open_settings()),
                Menu.SEPARATOR,
                Item("خروج", lambda icon, item: self.service.quit()),
            ),
        )

    # ---------- نصوص ديناميكية (تُقيَّم عند فتح القائمة) ----------
    def _status_text(self) -> str:
        return f"الحالة: {self.service._state_ar()}"

    def _toggle_text(self) -> str:
        state = self.service.state
        if state == "recording":
            return "⏹  إيقاف وإدراج النص"
        if state == "working":
            return "…  جارٍ التحويل"
        return "🎙  ابدأ التسجيل"

    def _engine_label(self, name: str) -> str:
        label = cfg_mod.ENGINE_LABELS_AR.get(name, name)
        if not self._engine_info[name][0]:
            return f"{label} — غير متاح"
        return label

    # ---------- أفعال ----------
    def _on_toggle(self) -> None:
        self.service.toggle()
        self.update()

    def _on_engine(self, name: str) -> None:
        ok, message = self.service.set_engine(name)
        if ok:
            self.service.notify("تم تغيير المحرّك", message)
        self.service._refresh()

    # ---------- الواجهة ----------
    def update(self) -> None:
        if self._stopped:
            return
        try:
            self.icon.icon = make_image(self.service.state)
            self.icon.title = f"الإملاء العربي — {self.service._state_ar()}"
            self.icon.update_menu()
        except Exception:  # noqa: BLE001 - التحديث لا يجب أن يُسقط الخدمة أبداً
            pass

    def notify(self, title: str, body: str = "") -> None:
        try:
            if self.icon.visible:
                self.icon.notify(body or title, title)
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        self.icon.run()

    def stop(self) -> None:
        self._stopped = True
        self.icon.stop()
