# تكامل اختياري مع Command Code

هذا التكامل اختياري تماماً — الأداة تعمل بدونه. وظيفته تشغيل خفيّة الإملاء تلقائياً
عند بدء جلسة Command Code جديدة، بحيث تكون الأيقونة جاهزة فوراً.

## التركيب

1. انسخ الخطّاف إلى مجلد الخطّافات:

   ```bash
   mkdir -p ~/.commandcode/hooks
   cp integrations/commandcode/arabic-dictate-ensure.sh ~/.commandcode/hooks/
   chmod +x ~/.commandcode/hooks/arabic-dictate-ensure.sh
   ```

2. أضف قسم `hooks/SessionStart` في `~/.commandcode/settings.json` (راجع صيغة
   `settings.json` في إصدارك من Command Code):

   ```json
   {
     "hooks": {
       "SessionStart": [
         { "command": "~/.commandcode/hooks/arabic-dictate-ensure.sh" }
       ]
     }
   }
   ```

الخطّاف غير حاجب: يستغرق أجزاء من الثانية إن كانت الخفيّة تعمل، ولا يعطّل الجلسة أبداً.

يمكنك أيضاً تثبيته تلقائياً أثناء تثبيت الأداة:

```bash
./install.sh --with-commandcode
```
