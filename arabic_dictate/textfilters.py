"""مرشّحات النص: رفض العبارات التي تخترعها النماذج من الصمت أو الضجيج.

وحدة مستقلة عن GTK والخفيّة حتى تكون قابلة للاختبار والاستخدام في سير العمل
الدفعي (transcribe/meeting) أيضاً.
"""
from __future__ import annotations

# نصوص يعرف ويسبر باختراعها من الصمت أو الضجيج — نرفضها بدل لصق هراء.
KNOWN_HALLUCINATIONS = (
    "اشتركوا في القناة",
    "اشترك في القناة",
    "لا تنسوا الاشتراك",
    "ترجمة نانسي قنقر",
    "نانسي قنقر",
    "المزيد من الفيديوهات",
    "شكرا للمشاهدة",
    "شكراً للمشاهدة",
    "موسيقى",
    "تصفيق",
    "Subtitles by",
    "Thanks for watching",
)

MAX_SHORT_TEXT = 60


def looks_like_hallucination(text: str) -> bool:
    """يعتبر النص هلوسة إن طابق عبارة معروفة وكان قصيراً (العبارة الطويلة قد تكون كلاماً حقيقياً)."""
    cleaned = text.strip().strip(" .,،!؟?")
    if not cleaned or len(cleaned) > MAX_SHORT_TEXT:
        return False
    return any(fragment in cleaned for fragment in KNOWN_HALLUCINATIONS)
