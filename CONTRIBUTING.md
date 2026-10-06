# المساهمة في الإملاء العربي

شكراً لاهتمامك! هذا دليل سريع للمساهمة في المشروع.

## بيئة التطوير

```bash
git clone https://github.com/abdulazizaaa/arabic-dictate.git
cd arabic-dictate
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e ".[whisper,meeting,dev]"
```

- `.[dev]` يجلب `pytest` و `ruff`.
- بعض الاعتماديات النظامية (xdotool, xclip, arecord, gtk) تُوفَّر من توزيعتك — راجع
  متطلبات النظام في [README](README.md).
- اختبارات النظام التي تحتاج نافذة/ميكروفوناً حقيقياً موجودة في `tests/manual/`.

## الاختبارات والفحص

```bash
.venv/bin/pytest tests/unit -q     # اختبارات وحدية تعمل بلا شاشة — وهي ما يشغّله CI
.venv/bin/ruff check .             # فحص الأسلوب
```

## قواعد المساهمة

- **تغيير واحد مركّز لكل Pull Request** — إصلاح أو ميزة واحدة.
- **أضف اختباراً وحدياً** (لا يحتاج شاشة/ميكروفون) لأي منطق جديد.
- **حافظ على اللغة العربية الواضحة** لكل نص يراه المستخدم — الرسائل، الإشعارات، الأخطاء.
- شغّل `ruff check .` و `pytest tests/unit` قبل الإرسال — CI يتحقق منهما أيضاً.
- للميزات الكبيرة أو التغييرات المعمارية: افتح Issue أولاً لنناقش التصميم.

## هيكل المشروع (مختصر)

```
arabic_dictate/
  cli.py        الأوامر
  daemon.py     الخفيّة: أيقونة + مقبس + سير العمل
  audio.py      التسجيل وبوابة الصمت
  inject.py     اللصق الآمن للعربية (X11)
  hotkey.py     الاختصار العالمي (X11)
  engines/      محرّكات التحويل الثلاثة
  meeting/      تفريغ الاجتماعات وتمييز المتحدثين
tests/unit/     اختبارات pytest (تعمل في CI)
tests/manual/   اختبارات تحتاج شاشة/ميكروفوناً
```

---

## English summary

Contributions are welcome. Set up with a virtualenv and
`pip install -e ".[whisper,meeting,dev]"`, then run `.venv/bin/pytest tests/unit -q` and
`.venv/bin/ruff check .` before opening a PR. Keep one focused change per PR, add headless unit
tests for new logic, and keep all user-facing text in clear Arabic. For large features, open an
issue first to discuss the design.
