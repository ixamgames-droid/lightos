"""QA-112: Testdateien ohne WebEngine stuerzen unter Windows nicht mehr beim
normalen Interpreter-Ende ab.

**Der Befund (Windows 11 x64, Sitzung D).** Nach QA-110 (gehaerteter Ausstieg
der WebEngine-Sitzungen) blieben drei Dateien, deren Tests alle bestehen, deren
Prozess aber beim normalen Ende abstuerzt: ``test_group_edit_dialog``,
``test_snapshot_ignore``, ``test_button_multi_action``. Das
Windows-Ereignisprotokoll (Event 1000) nennt meist ``ucrtbase.dll`` +0xa527e =
``abort`` (0xC0000409, ohne jede Meldung auf stderr), seltener eine Access
Violation in ``python312.dll`` oder in schon entladenem Code.

**Der Hergang.** Beim Ende leben in allen drei Dateien noch Dialoge, deren
Klasse in Python abgeleitet ist (8× ``GroupEditDialog``, 3×
``SnapshotIgnoreDialog``, 1× ``MultiActionDialog``) — obwohl die Tests sie nur
lokal halten. Sie haengen ueber ein Lambda an ihrem eigenen Knopf
(``clicked.connect(lambda: self._...)``): die Verbindung haelt Qt in C++, fuer
Pythons Speicherbereinigung unsichtbar. So werden sie erst im Abbau des
Interpreters zerstoert, waehrend PySide die ``QApplication`` abraeumt — dort
liegt der Absturz. Keine Threads, keine QThreads, kein eigener Meldungs-Handler
(Mess-Sonde ueber alle drei Dateien).

**Der Fix.** ``conftest.pytest_unconfigure`` loescht unter Windows auf dem
normalen Weg (ohne Haertung, ohne WebEngine) die noch lebenden
Top-Level-Fenster, solange Interpreter und ``QApplication`` voll da sind.

**Wie geprueft wird.** (1) Deterministisch: die Kind-Probe
``tests/_qa112_ende_probe.py`` haelt acht solche Dialoge fest und zaehlt am
Interpreter-Ende die noch lebenden Fenster — es muessen 0 sein. (2) Eine echte
betroffene Datei laeuft zweimal als Kind-pytest und muss mit 0 enden.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
OPFER = "tests/test_group_edit_dialog.py"
PROBE = "tests/_qa112_ende_probe.py"

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="das Aufraeumen beim Ende gilt nur unter Windows")


def _lauf(datei: str, **extra: str):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTEST_CURRENT_TEST", "PYTEST_ADDOPTS", "LIGHTOS_HARDEN_EXIT_ALL",
                        "LIGHTOS_HARDEN_EXIT")}
    env.update({"QT_QPA_PLATFORM": "offscreen", "PYTHONIOENCODING": "utf-8"})
    env.update(extra)
    r = subprocess.run([sys.executable, "-m", "pytest", datei, "-q", "-p", "no:cacheprovider",
                        "-o", "addopts="], cwd=str(REPO), env=env, capture_output=True,
                       timeout=600)
    aus = (r.stdout + r.stderr).decode("utf-8", "replace")
    return r.returncode, aus


def _code(rc: int) -> str:
    return f"{rc} (0x{rc & 0xFFFFFFFF:08X})"


def test_keine_python_fenster_mehr_beim_interpreter_ende(tmp_path):
    zaehlung = tmp_path / "zaehlung.json"
    rc, aus = _lauf(PROBE, QA112_ZAEHLUNG=str(zaehlung))
    assert "1 passed" in aus, aus[-1500:]
    assert zaehlung.exists(), f"atexit-Haken lief nicht\n{aus[-1500:]}"
    fenster = json.loads(zaehlung.read_text(encoding="utf-8"))["fenster"]
    assert fenster == 0, (f"{fenster} Top-Level-Fenster leben noch beim Interpreter-Ende "
                          f"(Rueckgabe {_code(rc)})")
    assert rc == 0, f"Rueckgabe {_code(rc)}\n{aus[-1500:]}"


def test_betroffene_datei_endet_ohne_nativen_absturz():
    for lauf in range(2):
        rc, aus = _lauf(OPFER)
        assert "passed" in aus and "failed" not in aus, aus[-1500:]
        assert rc == 0, f"Lauf {lauf + 1}: Rueckgabe {_code(rc)}\n{aus[-1500:]}"


def test_rotes_ergebnis_bleibt_rot(tmp_path):
    """Gegenprobe: das Aufraeumen darf aus einem roten Lauf keinen gruenen machen."""
    rc, aus = _lauf(PROBE, QA112_ROT="1", QA112_ZAEHLUNG=str(tmp_path / "z.json"))
    assert "1 failed" in aus, aus[-1500:]
    assert rc == 1, f"Rueckgabe {_code(rc)} statt 1\n{aus[-1500:]}"
