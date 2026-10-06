#!/usr/bin/env bash
# يبدأ خفيّة الإملاء العربي تلقائياً عند بدء أي جلسة Command Code.
# SessionStart غير حاجب، لذا لا يمكن أن يؤخّر أو يمنع فتح الجلسة.
set -uo pipefail

export PATH="$HOME/.local/bin:$PATH"

if command -v arabic-dictate >/dev/null 2>&1; then
  arabic-dictate ensure >/dev/null 2>&1 || true
fi

exit 0
