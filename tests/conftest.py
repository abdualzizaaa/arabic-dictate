"""يضمن أن جذر المشروع على مسار الاستيراد عند تشغيل الاختبارات من أي مكان."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
