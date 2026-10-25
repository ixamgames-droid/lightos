"""Waechter: Tests lesen Backlog-Eintraege nur ueber ``tests/backlog_eintrag.py``.

``tools/backlog_sammeln.py`` loescht jedes eingesammelte Fragment
``backlog.d/<ID>.md``. Ein Test, der so ein Fragment direkt oeffnet, wird nach
dem naechsten Sammel-Lauf rot, obwohl der Eintrag jetzt in BACKLOG.md steht
(20.10.2026: ``test_eng39_doku.py``, ``test_imp2_mitschnitt_anleitung.py``).

Ausgenommen sind Werkzeug-Tests, die mit Wegwerf-Fragmenten in einem
temporaeren Repo arbeiten oder Pfade nur als Beispiel nennen.
"""
from __future__ import annotations

import pathlib
import re

TESTS = pathlib.Path(__file__).resolve().parent

AUSNAHMEN = {
    "test_backlog_fragmente.py": "Werkzeug-Test backlog_sammeln.py, Wegwerf-Repo",
    "test_backlog_ids.py": "Werkzeug-Test backlog_ids.py, erfundene Fragmente",
    "test_proc19_doku_schnellweg.py": "Pfad nur als Beispiel fuer die Doku-Klasse",
    "test_tool23_backlog_ids_tafel_fragmente.py": "Werkzeug-Test, Wegwerf-Fragmente",
    "test_backlog_fragment_zugriff.py": "dieser Waechter selbst",
}

# "backlog.d/AB-12.md", "backlog.d" / "AB-12.md", ("backlog.d", "AB-12.md")
MUSTER = re.compile(
    r"backlog\.d(?:/|[\"']\s*(?:/|,)\s*f?[\"'])([A-Z][A-Z0-9]*-[0-9A-Za-z]+)\.md")


def treffer(text: str) -> list[tuple[int, str]]:
    return [(text.count("\n", 0, m.start()) + 1, m.group(1))
            for m in MUSTER.finditer(text)]


def test_muster_erkennt_die_ueblichen_schreibweisen():
    d = "backlog" + ".d"
    for probe in (f'ROOT / "{d}" / "ENG-39.md"',
                  f'os.path.join(ROOT, "{d}", "LIZ-1.md")',
                  f'_lies("{d}", "LIZ-1.md")',
                  f'open("{d}/IMP-2.md")'):
        assert treffer(probe), probe
    assert not treffer(f'"{d}/<ID>.md"')
    assert not treffer(f'ROOT / "{d}"')


def test_kein_test_oeffnet_ein_fragment_direkt():
    funde = []
    for datei in sorted(TESTS.glob("*.py")):
        if datei.name in AUSNAHMEN or datei.name == "backlog_eintrag.py":
            continue
        for zeile, item in treffer(datei.read_text(encoding="utf-8")):
            funde.append(f"tests/{datei.name}:{zeile} ({item})")
    assert not funde, (
        "Diese Tests oeffnen ein konkretes Backlog-Fragment direkt — nach dem "
        "naechsten Sammel-Lauf (tools/backlog_sammeln.py) ist es weg und der "
        "Test rot. Statt dessen die Hilfe nutzen: "
        "`from backlog_eintrag import eintrag, status` "
        "(liest Fragment, sonst BACKLOG.md, sonst BACKLOG_ARCHIVE.md):\n  "
        + "\n  ".join(funde))


def test_ausnahmen_gibt_es_noch():
    fehlt = [n for n in AUSNAHMEN if not (TESTS / n).is_file()]
    assert not fehlt, f"Ausnahme ohne Datei, bitte streichen: {fehlt}"
