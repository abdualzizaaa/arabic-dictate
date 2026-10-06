#!/usr/bin/env bash
# تثبيت أداة الإملاء العربي (بدون sudo).
# الاستخدام: ./install.sh [--with-cohere-local] [--with-meeting] [--with-commandcode]
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT"
export PATH="$HOME/.local/bin:$PATH"

WITH_COHERE=0
WITH_MEETING=0
WITH_COMMANDCODE=0
for arg in "$@"; do
  case "$arg" in
    --with-cohere-local) WITH_COHERE=1 ;;
    --with-meeting) WITH_MEETING=1 ;;
    --with-commandcode) WITH_COMMANDCODE=1 ;;
    *) echo "وسيط غير معروف: $arg" >&2; exit 1 ;;
  esac
done

say() { printf "▶ %s\n" "$1"; }
warn() { printf "⚠  %s\n" "$1" >&2; }

# ١) فحوصات أساسية
say "١/٦ — فحص المتطلبات"
missing=()
for tool in arecord xdotool xclip notify-send; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ "${#missing[@]}" -gt 0 ]; then
  warn "أدوات نظام ناقصة: ${missing[*]}"
  if command -v apt-get >/dev/null 2>&1; then
    echo "   ثبّتها بالأمر:"
    echo "   sudo apt install -y python3-venv python3-gi alsa-utils xdotool xclip libnotify-bin \\"
    echo "     gir1.2-ayatanaappindicator3-0.1 ffmpeg"
  else
    warn "هذا المثبّت مُعدّ لـ Debian/Ubuntu — ثبّت المتطلبات يدوياً حسب توزيعتك."
  fi
fi
command -v python3 >/dev/null 2>&1 || { echo "خطأ: python3 غير موجود" >&2; exit 1; }

# ٢) typelib لأيقونة شريط النظام (Debian/Ubuntu بدون sudo)
say "٢/٦ — typelib لأيقونة شريط النظام"
mkdir -p "$HOME/.local/lib/girepository-1.0"
TYPELIB="$HOME/.local/lib/girepository-1.0/AyatanaAppIndicator3-0.1.typelib"
if [ -f "$TYPELIB" ]; then
  echo "   ✓ موجود مسبقاً"
elif command -v apt-get >/dev/null 2>&1; then
  TMP="$(mktemp -d)"
  if (cd "$TMP" && apt-get download gir1.2-ayatanaappindicator3-0.1 >/dev/null 2>&1 \
      && dpkg -x ./*.deb extracted \
      && find extracted -name "*.typelib" -exec cp {} "$HOME/.local/lib/girepository-1.0/" \;); then
    echo "   ✓ تم"
  else
    warn "تعذّر تنزيل typelib — ثبّت gir1.2-ayatanaappindicator3-0.1 من مدير الحزم"
  fi
  rm -rf "$TMP"
else
  warn "تخطّي typelib (نظام غير Debian/Ubuntu)"
fi

# ٣) بيئة بايثون والحزم
say "٣/٦ — بيئة بايثون والحزم"
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q --upgrade pip
EXTRAS="whisper"
if [ "$WITH_COHERE" = "1" ]; then EXTRAS="$EXTRAS,cohere-local"; fi
if [ "$WITH_MEETING" = "1" ]; then EXTRAS="$EXTRAS,meeting"; fi
.venv/bin/pip install -q -e ".[$EXTRAS]"
echo "   ✓ ثُبّتت الحزمة مع الإضافات: $EXTRAS"

# ٤) الأمر العام
say "٤/٦ — الأمر العام"
mkdir -p "$HOME/.local/bin"
chmod +x bin/arabic-dictate
ln -sf "$PROJECT/bin/arabic-dictate" "$HOME/.local/bin/arabic-dictate"
echo "   ✓ ~/.local/bin/arabic-dictate"

# ٥) خطّاف Command Code (اختياري)
say "٥/٦ — خطّاف Command Code"
if [ "$WITH_COMMANDCODE" = "1" ]; then
  mkdir -p "$HOME/.commandcode/hooks"
  cp integrations/commandcode/arabic-dictate-ensure.sh "$HOME/.commandcode/hooks/"
  chmod +x "$HOME/.commandcode/hooks/arabic-dictate-ensure.sh"
  echo "   ✓ نُسخ — أضف hooks/SessionStart إلى settings.json (راجع integrations/commandcode/README.md)"
else
  echo "   تخطّي — فعّله لاحقاً بـ: ./install.sh --with-commandcode"
fi

# ٦) النماذج الاختيارية
say "٦/٦ — النماذج"
if [ "$WITH_COHERE" = "1" ]; then
  arabic-dictate pull || warn "تعذّر تنزيل نموذج كوهير — أعد المحاولة بـ: arabic-dictate pull"
else
  echo "   نموذج كوهير (المحرّك الأدق): تخطّي — نزّله لاحقاً بـ: arabic-dictate pull"
fi
if [ "$WITH_MEETING" = "1" ]; then
  arabic-dictate meeting setup || warn "تعذّر تنزيل نماذج الاجتماعات — أعد المحاولة بـ: arabic-dictate meeting setup"
fi

echo
echo "تم التثبيت. الخطوات التالية:"
echo "  arabic-dictate ensure     # شغّل الخفيّة"
echo "  arabic-dictate doctor     # فحص شامل"
echo "  arabic-dictate pull       # (اختياري) نموذج كوهير العربي الأدق (~3GB)"
echo "  arabic-dictate warmup     # (نصيحة) تسخين النموذج قبل أول استخدام"
