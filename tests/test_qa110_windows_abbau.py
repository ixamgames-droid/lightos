"""QA-110: WebEngine-Sitzungen stuerzen unter Windows nach allen Tests nicht
mehr beim Prozessende ab.

**Der Befund (gemessen 01.11.2026, Windows 11 x64).** Neun Dateien endeten im
Gate als „nativer Abbau“, obwohl alle Tests bestanden; je 10 Laeufe einzeln:
``test_las35_planer`` 10/10, ``test_viz75_buehnen_elemente_hoehe`` 10/10,
``test_viz55_einmessen`` 9/10. Das Windows-Ereignisprotokoll (Event 1000)
nannte fuer 100 von 136 Python-Abstuerzen des Tages dieselbe Stelle:
``pyside6.abi3.dll`` +0x1c91e = ``PySide::SignalManager::retrieveMetaObject``.

**Der Hergang.** Fuer WebEngine-Sitzungen (``QWebEngineView`` geladen) beendet
``conftest.pytest_unconfigure`` den Prozess hart mit ``os._exit``. Unter
Linux ist das ``_exit()`` — keine Bibliotheks-Destruktoren. Unter Windows ruft
``os._exit`` aber ``ExitProcess``, und das entlaedt noch alle DLLs: Qt raeumt
dabei auf und fragt die noch lebenden, in Python abgeleiteten Top-Level-
Widgets (``SperrzonenPlaner``, ``EinmessAssistent`` …) nach ihrem
``metaObject()`` — PySide greift dafuer in einen Interpreter, der schon
abgebaut wird. Gegenproben je 10x auf den drei Dateien: Top-Level-Widgets vor
dem Ausstieg loeschen -> 0/30; ``TerminateProcess`` (kein DLL-Entladen, wie
``_exit`` unter Linux) -> 0/30.

**Wie geprueft wird.** Eine echte betroffene Datei laeuft als Kind-pytest mit
scharfer Haertung; sie muss mit 0 enden statt mit einem Windows-Fehlercode.
Die Gegenprobe stellt sicher, dass der harte Ausstieg ein ROTES Ergebnis
weiterhin als rot meldet.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
OPFER = "tests/test_viz75_buehnen_elemente_hoehe.py"     # ohne Fix 10/10 Absturz
PROBE = "tests/_qa110_abbau_probe.py"

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="os._exit entlaedt nur unter Windows die DLLs")


def _lauf(datei: str, **extra: str):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTEST_CURRENT_TEST", "PYTEST_ADDOPTS", "LIGHTOS_HARDEN_EXIT_ALL")}
    env.update({"LIGHTOS_HARDEN_EXIT": "1", "QT_QPA_PLATFORM": "offscreen",
                "PYTHONIOENCODING": "utf-8"})
    env.update(extra)
    r = subprocess.run([sys.executable, "-m", "pytest", datei, "-q", "-p", "no:cacheprovider",
                        "-o", "addopts="], cwd=str(REPO), env=env, capture_output=True,
                       timeout=600)
    aus = (r.stdout + r.stderr).decode("utf-8", "replace")
    return r.returncode, aus


def _code(rc: int) -> str:
    return f"{rc} (0x{rc & 0xFFFFFFFF:08X})"


def test_webengine_sitzung_endet_ohne_nativen_absturz():
    for lauf in range(2):
        rc, aus = _lauf(OPFER)
        assert "passed" in aus and "failed" not in aus, aus[-1500:]
        assert rc == 0, f"Lauf {lauf + 1}: Rueckgabe {_code(rc)}\n{aus[-1500:]}"


def test_harter_ausstieg_meldet_rot_weiter():
    rc, aus = _lauf(PROBE, QA110_ROT="1")
    assert "1 failed" in aus, aus[-1500:]
    assert rc == 1, f"Rueckgabe {_code(rc)} statt 1\n{aus[-1500:]}"


def test_harter_ausstieg_meldet_gruen_weiter():
    rc, aus = _lauf(PROBE)
    assert "1 passed" in aus, aus[-1500:]
    assert rc == 0, f"Rueckgabe {_code(rc)}\n{aus[-1500:]}"
