"""Regression fuer den QtWebEngine-sicheren Prozessabschluss."""
from __future__ import annotations

import subprocess
import sys


def test_finalize_and_exit_runs_atexit_hooks(tmp_path):
    marker = tmp_path / "finalized.txt"
    code = (
        "import atexit\n"
        "from main import _finalize_and_exit\n"
        f"p = {str(marker)!r}\n"
        "atexit.register(lambda: open(p, 'w', encoding='utf-8').write('ok'))\n"
        "_finalize_and_exit(7)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=15,
        env=None,
    )
    assert result.returncode == 7
    assert marker.read_text(encoding="utf-8") == "ok"
