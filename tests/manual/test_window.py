"""نافذة اختبار: تطبع النص فور لصقه فيها (لمحاكاة الطرفية)."""
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

TIMEOUT = int(sys.argv[1]) if len(sys.argv) > 1 else 60

window = Gtk.Window(title="InjectionTest")
window.set_default_size(760, 120)
window.set_position(Gtk.WindowPosition.CENTER)

entry = Gtk.Entry()
entry.set_placeholder_text("سيُلصق النص هنا…")
entry.set_hexpand(True)
entry.set_margin_top(30)
entry.set_margin_bottom(30)
entry.set_margin_start(30)
entry.set_margin_end(30)
window.add(entry)
window.show_all()


def on_changed(_entry) -> None:
    text = entry.get_text()
    if text:
        print(f"PASTED>>>{text}", flush=True)


entry.connect("changed", on_changed)


def on_key(_widget, event) -> bool:
    """يعامل Ctrl+Shift+V كلصق — نفس ما تفعله الطرفية."""
    ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
    if (event.state & ctrl_shift) == ctrl_shift and event.keyval in (Gdk.KEY_v, Gdk.KEY_V):
        entry.paste_clipboard()
        return True
    return False


window.connect("key-press-event", on_key)
window.connect("destroy", Gtk.main_quit)
GLib.timeout_add_seconds(TIMEOUT, lambda: (Gtk.main_quit(), False)[1])

window.present()
GLib.timeout_add(400, lambda: (entry.grab_focus(), False)[1])
Gtk.main()
