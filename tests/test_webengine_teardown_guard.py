"""XPLAT-09 — Waechter: wer einen ``QWebEngineView`` baut, muss ihn richtig abbauen.

Der Defekt war nicht auffaellig, sondern still: elf Testdateien bauten pro
Testmethode einen echten ``QWebEngineView`` und raeumten mit
``deleteLater()`` + ``processEvents()``-Pumpe ab. Das stellt ``DeferredDelete``
nie zu (Begruendung ausfuehrlich in ``tests/_qt_webengine.py``), der View blieb
am Leben, und der Prozess starb an ``SIGSEGV`` — bei neun Dateien erst beim
Prozessende, also **nach** dem gemeldeten ``N passed``. Genau deshalb fiel es
lange nicht auf: die Testergebnisse waren gruen, nur der Exitcode war es nicht.

Dieser Waechter ist billig (reine Quelltext-Pruefung, kein Qt) und schliesst den
Rueckweg: eine neue WebEngine-Testdatei mit dem alten Abbaumuster faellt sofort
auf, statt erst dann, wenn die Datei genug Ladezyklen ansammelt, um mitten im
Lauf zu sterben.

Die funktionale Absicherung sind die elf Dateien selbst — sie enden seit dem Fix
mit Exitcode 0, und das segmentierte Gate bewertet Exitcodes.
"""
from __future__ import annotations

import os
import re
import subprocess

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)

_BUILDS_VIEW = re.compile(r"QWebEngineView\s*\(\s*\)")
_HELPER_IMPORT = "destroy_webengine_view"
# Der rohe Abbau, der den Crash verursacht hat.
_RAW_TEARDOWN = re.compile(r"\.deleteLater\s*\(\s*\)")


def _webengine_test_files():
    """Alle versionierten Testdateien, die einen echten View instanziieren."""
    out = subprocess.run(["git", "ls-files", "tests/*.py"], cwd=_REPO_ROOT,
                         capture_output=True, text=True, check=True).stdout
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        path = os.path.join(_REPO_ROOT, rel)
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        if _BUILDS_VIEW.search(src):
            yield rel, src


def test_every_webengine_test_uses_the_shared_teardown():
    missing = [rel for rel, src in _webengine_test_files()
               if _HELPER_IMPORT not in src]
    assert not missing, (
        "Diese Testdateien bauen einen QWebEngineView, benutzen aber nicht "
        "`destroy_webengine_view` aus tests/_qt_webengine.py (XPLAT-09). Ohne den "
        "Helfer bleibt der View nach deleteLater() am Leben — die Datei laeuft "
        "solange 'gruen', bis sie genug Ladezyklen hat, dann SIGSEGV:\n  "
        + "\n  ".join(missing))


def test_no_webengine_test_calls_deletelater_directly():
    """Der Helfer ist der einzige Ort, an dem ``deleteLater()`` stehen darf.

    Sonst schleicht sich das alte Muster als zusaetzliche Zeile *neben* dem
    Helferaufruf wieder ein (und die zweite Zustellung fehlt dann fuer sie).
    """
    offenders = []
    for rel, src in _webengine_test_files():
        for lineno, line in enumerate(src.splitlines(), 1):
            if _RAW_TEARDOWN.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Direkter deleteLater()-Aufruf in einer WebEngine-Testdatei (XPLAT-09) — "
        "der Abbau gehoert in destroy_webengine_view(), sonst fehlt die "
        "DeferredDelete-Zustellung:\n  " + "\n  ".join(offenders))


def test_helper_module_is_not_collected_as_a_test():
    """``_qt_webengine.py`` darf nicht wie eine Testdatei heissen."""
    assert os.path.isfile(os.path.join(_TESTS_DIR, "_qt_webengine.py"))
    assert not os.path.basename("_qt_webengine.py").startswith("test_")
