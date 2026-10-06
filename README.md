# 🎙️ الإملاء العربي (arabic-dictate)

إملاء صوتي عربي **محلي بالكامل**: تتكلّم فيحوّل الكلام إلى نص عربي **ويلصقه عند مؤشر الكتابة**
في النافذة النشطة — داخل الطرفية مباشرة. نصك لا يُرسل تلقائياً؛ تراجعه ثم تضغط Enter بنفسك.

ومع ميزة **تفريغ الاجتماعات**: يحوّل تسجيلات الاجتماعات الطويلة إلى نص منظّم مع
**تمييز المتحدثين** — المتحدث ١، المتحدث ٢، المتحدث ٣…

**English:** [README.en.md](README.en.md) · **الدليل الكامل:** [GUIDE.ar.md](GUIDE.ar.md)

[![CI](https://github.com/abdualzizaaa/arabic-dictate/actions/workflows/ci.yml/badge.svg)](https://github.com/abdualzizaaa/arabic-dictate/actions/workflows/ci.yml)
![الترخيص MIT](https://img.shields.io/badge/License-MIT-green.svg)
![بايثون 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![المنصة](https://img.shields.io/badge/Platform-Linux%20(X11)%20%7C%20Windows%20(beta)-lightgrey.svg)
![محلي أولاً](https://img.shields.io/badge/Local--first-100%25-success.svg)

---

## ✨ الميزات

- 🎙 **إملاء فوري**: أيقونة في شريط النظام + اختصار `Ctrl+Alt+D`، والنص يُلصق مكان المؤشر في أي نافذة.
- 🧠 **ثلاثة محرّكات عربية**: نموذج Cohere العربي محلياً (الأدق — ~4.7× الزمن الحقيقي)، ويسبر محلياً
  (بلا إنترنت بعد أول تحميل)، أو سحابياً عبر Cohere API (الأسرع — يحتاج مفتاحاً مجانياً).
- 🛡 **حماية من الهلوسة**: بوابة صمت (WebRTC VAD) + بوابة طاقة ديناميكية + مرشّح عبارات مختلقة —
  لا يُلصق هراء من الضجيج.
- 👥 **تفريغ الاجتماعات** (جديد): تسجيل الميكروفون + صوت النظام معاً، ثم تفريغ بعناوين المتحدثين
  وإخراج `txt` / `srt` / `json` مع إحصاءات الكلام.
- 🔒 **خصوصية**: كل شيء على جهازك؛ لا يُرسل الصوت لأي خدمة إلا إن اخترت محرّك السحابة صراحةً.

## 🚀 تشغيل سريع (Ubuntu / Debian)

```bash
git clone https://github.com/abdualzizaaa/arabic-dictate.git
cd arabic-dictate
./install.sh              # بيئة بايثون + الأمر العام (تثبيت سريع)
arabic-dictate doctor     # تحقّق من البيئة والمحرّكات
```

ثم اضغط أيقونة الميكروفون في شريط النظام أو `Ctrl+Alt+D`، تكلّم، واضغطها مجدداً —
سيُكتب النص عند المؤشر. للترقية إلى المحرّك العربي الأدق (~3GB، مرة واحدة):

```bash
arabic-dictate pull                     # نموذج كوهير العربي المحلي (int8)
arabic-dictate engine cohere-local      # واجعله النشط
```

> **الطرفيات**: مفتاح اللصق الافتراضي `Ctrl+Shift+V`، وهو مضبوط تلقائياً. لتغييره:
> `paste_key` في الإعدادات.

## 🪟 ويندوز 10/11 (تجريبي)

```powershell
git clone https://github.com/abdualzizaaa/arabic-dictate.git
cd arabic-dictate
.\install.ps1 -AddToPath          # أعلام إضافية: -WithMeeting و -AutoStart
arabic-dictate doctor
winget install ffmpeg             # مطلوب لتحويل صيغ الصوت في الاجتماعات
```

- الأيقونة في شريط المهام، والاختصار الافتراضي `Ctrl+Alt+D`، واللصق تلقائي في النافذة النشطة.
- تسجيل الاجتماع يستخدم WASAPI (ميكروفون + صوت النظام) بلا برامج إضافية.
- **قيود معروفة**: لا يعمل اللصق في النوافذ المرفوعة (صلاحيات مدير) أو البرامج ذات الحماية
  الذاتية؛ وبعض البرامج القديمة تلصق بـ `Ctrl+V` بدل `Ctrl+Shift+V` (عدّل `paste_key`).
- نسخة ويندوز **لم تُجرَّب بعد على جهاز حقيقي** — تجاربكم مرحّب بها عبر Issues.

## 📦 متطلبات النظام

> أوامر هذا القسم لأوبنتو/ديبيان؛ لمتطلبات ويندوز راجع قسم ويندوز أعلاه (يكفيها بايثون).

```bash
sudo apt install -y python3-venv python3-gi alsa-utils xdotool xclip libnotify-bin \
  gir1.2-ayatanaappindicator3-0.1 ffmpeg
```

| الحاجة | لماذا |
| --- | --- |
| `alsa-utils` | التسجيل من الميكروفون (`arecord`) |
| `xdotool` + `xclip` | لصق النص في النافذة النشطة (X11) |
| `libnotify-bin` | إشعارات سطح المكتب (`notify-send`) |
| `python3-gi` + `gir1.2-ayatanaappindicator3-0.1` | أيقونة شريط النظام |
| `ffmpeg` | تسجيل الاجتماعات وتحويل صيغ الصوت (اختياري) |

- على GNOME: فعّل امتداد AppIndicators لعرض الأيقونة
  (`gnome-extensions enable ubuntu-appindicators@ubuntu.com`).
- **X11 مدعوم بالكامل.** على Wayland: التحويل يعمل، لكن اللصق والاختصار العام غير موثوقين
  حالياً — راجع «خارطة الطريق».

## 🎙️ المحرّكات — أيها تختار؟

| المحرّك | الدقة في العربية | السرعة (معالج، بدون GPU) | الذاكرة | يحتاج |
| --- | --- | --- | --- | --- |
| `cohere-local` **(الافتراضي)** | **الأفضل** (WER ≈ 25.9)\* | **~4.7× الزمن الحقيقي** | ~4GB | النموذج منزّل (`pull`، ≈3GB مرة واحدة) |
| `whisper-local` | جيدة (WER ≈ 36.9)\* | ~1.0× الزمن الحقيقي | ~2GB | لا شيء (يُحمَّل تلقائياً) |
| `cohere-cloud` | **الأفضل** (نفس النموذج) | ثوانٍ (شبكة) | لا شيء | مفتاح Cohere مجاني (`set-key`) |

\* أرقام WER من لوحة ترتيب Arabic ASR المفتوحة — قابلة للاختلاف حسب اللهجة والمجال.

```bash
arabic-dictate engine                    # اعرض المتاح والحالي
arabic-dictate engine whisper-local      # بدّل المحرّك
arabic-dictate pull                      # نزّل نموذج كوهير المحلي
arabic-dictate set-key <COHERE_API_KEY>  # مفتاح المحرّك السحابي
```

## 👥 تفريغ الاجتماعات (جديد)

سجّل الاجتماع (ميكروفون + صوت النظام معاً)، ثم فرّغه بعناوين المتحدثين:

```bash
arabic-dictate meeting setup                             # نماذج تمييز المتحدثين (~45MB، مرة واحدة)
arabic-dictate meeting record --out meeting.wav          # يتسجّل ميك + صوت النظام — للإيقاف: Ctrl+C
arabic-dictate meeting transcribe meeting.wav --format srt --out ./transcripts
```

نموذج الناتج:

```text
[00:00:12] المتحدث ١:
أهلاً بالجميع، نبدأ بمراجعة مهام الأسبوع الماضي.

[00:00:19] المتحدث ٢:
تم إنجاز تقرير الأداء، وبقي مراجعة الميزانية.
```

- **التمييز بعد الاجتماع** هو المسار العملي على المعالج (ساعة اجتماع تُعالج خلال دقائق؛
  البث الحي بتمييز لحظي يحتاج كرت رسومات).
- المكدّس: **sherpa-onnx** (تراخيص نظيفة) — بلا حساب HuggingFace وبلا قبول شروط.
- عرف عدد المتحدثين؟ `--speakers 3`. اتركه `0` للكشف التلقائي.
- الخرج: `txt` أو `srt` (ترجمات) أو `json` (للتكامل مع أدواتك).

## ⌨️ الأوامر الأساسية

| الأمر | الوظيفة |
| --- | --- |
| `arabic-dictate ensure` | شغّل الخفيّة إن لم تكن تعمل |
| `arabic-dictate start` / `stop` / `toggle` | تحكّم بالتسجيل |
| `arabic-dictate status` | الحالة كاملة (JSON) |
| `arabic-dictate last` / `copy` | آخر نص / انسخه |
| `arabic-dictate transcribe FILE` | حوّل ملفاً صوتياً إلى نص |
| `arabic-dictate meeting …` | تفريغ الاجتماعات: `setup` / `record` / `transcribe` |
| `arabic-dictate warmup` / `unload` | حمّل النموذج مسبقاً / حرّر الذاكرة |
| `arabic-dictate doctor` | فحص شامل للبيئة والمحرّكات |

القائمة الكاملة في [GUIDE.ar.md](GUIDE.ar.md).

## ⚙️ الإعدادات

الملف: `~/.config/arabic-dictate/config.json` — بعد أي تعديل: `arabic-dictate reload`.
أهم المفاتيح: `engine`, `hotkey`, `paste_key`, `inject_mode`, `vad_min_secs`, `vad_threshold`,
ومجموعة `meeting` (عدد المتحدثين، صيغة العناوين، مجلد الخرج). الشرح الكامل في
[GUIDE.ar.md](GUIDE.ar.md).

## 🔒 الخصوصية

- المحرّكان المحليان يعملان **دون إنترنت** بعد التحميل الأول، ولا يخرج صوتك من جهازك.
- `cohere-cloud` اختياري: يرسل مقطعك الصوتي إلى Cohere لتسريع التحويل — لا يُستخدم إلا إن
  اخترته ووضعت مفتاحاً.
- نموذج `cohere-local` يُنزَّل من HuggingFace وتُتحقَّق بصمة ملفاته (SHA-256) بعد التنزيل.

## 🧩 تكاملات اختيارية

- **Command Code**: خطّاف يبدأ الخفيّة تلقائياً مع كل جلسة — راجع
  [integrations/commandcode](integrations/commandcode/README.md).

## 🗺️ خارطة الطريق

- تجربة نسخة ويندوز على أجهزة حقيقية ثم تثبيتها رسمياً.
- دعم Wayland (لصق واختصار عام).
- تفريغ مباشر (بثّ نصي) أثناء الاجتماع بدون عناوين لحظية.
- تسمية المتحدثين بأسمائهم عبر بصمة صوت (تسجيل عيّنة لكل شخص).
- طبقة «دقة عالية» اختيارية لتمييز المتحدثين (pyannote community-1).
- تسريع بواسطة OpenVINO / كروت Intel المدمجة.
- النشر على PyPI.

## 🤝 المساهمة

المساهمات مرحّب بها — ابدأ من [CONTRIBUTING.md](CONTRIBUTING.md)، وكل تفاعل في هذا
المشروع يخضع لـ [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## 📄 الترخيص وشكر

هذا المشروع بترخيص [MIT](LICENSE). يبني على أكتاف مشاريع عظيمة:

- [Cohere Transcribe Arabic](https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026)
  (Apache-2.0) — النموذج العربي، عبر نسخة CPU int8 مجتمعية.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + CTranslate2 — محرّك ويسبر.
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (Apache-2.0) + pyannote segmentation-3.0
  (MIT) + 3D-Speaker CAM++ (Apache-2.0) — تمييز المتحدثين.
- [pystray](https://github.com/moses-palmer/pystray) (LGPLv3) + [Pillow](https://python-pillow.org/)
  لأيقونة ويندوز، و[SoundCard](https://github.com/bastibe/SoundCard) (BSD-3) لصوت ويندوز.
- WebRTC VAD — بوابة الصمت.
