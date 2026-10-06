"""تفريغ الاجتماعات وتمييز المتحدثين (ميزة اختيارية — تحتاج الإضافة [meeting])."""
from __future__ import annotations

from .errors import MeetingError
from .pipeline import MeetingResult, Segment, transcribe_meeting

__all__ = ["MeetingError", "MeetingResult", "Segment", "transcribe_meeting"]
