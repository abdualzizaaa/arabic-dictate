"""اختبارات مرشّح الهلوسة."""
from __future__ import annotations

from arabic_dictate.textfilters import looks_like_hallucination


def test_known_hallucinations_detected():
    assert looks_like_hallucination("اشتركوا في القناة")
    assert looks_like_hallucination("  شكراً للمشاهدة.  ")
    assert looks_like_hallucination("ترجمة نانسي قنقر")
    assert looks_like_hallucination("Thanks for watching")


def test_regular_text_passes():
    assert not looks_like_hallucination("مرحباً، كيف حالك اليوم؟")
    assert not looks_like_hallucination("نبدأ بمراجعة مهام الأسبوع الماضي")
    assert not looks_like_hallucination("")


def test_long_text_with_known_phrase_passes():
    long_text = "اشتركوا في القناة " + "وهذا كلام حقيقي طويل جداً يمتد لأكثر من ستين حرفاً بكثير " * 2
    assert len(long_text) > 60
    assert not looks_like_hallucination(long_text)
