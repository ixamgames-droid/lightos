"""QA-REPORTLOSS — die Exit-Härtung darf pytests Fehlerbericht nicht verschlucken.

**Was schiefging.** `tests/conftest.py` beendet den Prozess per `os._exit()`, um die
sporadisch crashende native Abbauphase zu überspringen (XPLAT-08/QA-11). Dieser Aufruf
saß in `pytest_sessionfinish` — und kam damit dem TerminalReporter zuvor, der seine
Zusammenfassung (`= FAILURES =`, die `FAILED …`-Zeilen, `short test summary info`)
ebenfalls dort schreibt. Gemessen an einem Lauf mit sieben echten Fehlschlägen:
**mit** Härtung 10 Zeilen Log und **keine** einzige `FAILED`-Zeile, ohne Härtung
54 Zeilen mit allen sieben.

**Warum das gefährlich war.** `tools/verify_segmented.sh` stuft ein rotes Segment danach
ein, ob im Log `FAILED` steht: kein `FAILED` heißt „nativer Abbau-Crash nach dem
Ergebnis" (QA-24, keine Dringlichkeit). Eine gehärtete Testdatei mit **echten**
Fehlschlägen sah damit exakt aus wie ein harmloser Teardown-Crash. Die Fehldiagnose war
ins Werkzeug eingebaut — und ausgerechnet die WebEngine-Dateien, für die die Härtung
gebaut wurde, waren betroffen.

Der Exit sitzt jetzt in `pytest_unconfigure`, also nach der kompletten
Session-Auswertung und immer noch weit vor der crashenden Abbauphase.

Dieser Test fährt eine echte pytest-Subsession mit einem absichtlich fehlschlagenden
Test und prüft beides: der Bericht ist da **und** der Exitcode stimmt.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FAILING_TEST = textwrap.dedent(
    '''
    def test_absichtlich_rot():
        assert 1 == 2, "dieser Fehlschlag MUSS im Bericht auftauchen"


    def test_gruen():
        assert True
    '''
)


def _run_subsession(tmp_path, env_extra):
    """Eine eigene pytest-Session in einem Unterprozess fahren.

    Bewusst mit `-p no:cacheprovider` und eigenem rootdir-freiem Zielpfad, damit die
    Subsession nicht die Konfiguration der äußeren Suite erbt. `tests/conftest.py`
    wird über `-p` explizit geladen — nur so greift die Härtung, die hier ja geprüft
    werden soll.
    """
    testfile = tmp_path / "test_reportloss_probe.py"
    testfile.write_text(_FAILING_TEST, encoding="utf-8")

    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.pop("LIGHTOS_HARDEN_EXIT", None)
    env.pop("LIGHTOS_HARDEN_EXIT_ALL", None)
    env.update(env_extra)
    # Die Probe-Datei liegt ausserhalb von tests/ -> conftest.py greift nicht
    # automatisch. Explizit als Plugin laden, damit die Haertung aktiv ist.
    #
    # ⚠️ Das Repo-Root MUSS mit in den PYTHONPATH: `tests/conftest.py` importiert
    # `src.core.paths`, und das kam bisher nur ueber `cwd=_REPO_ROOT` in den
    # sys.path — das faellt mit dem cwd-Wechsel unten weg.
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.join(_REPO_ROOT, "tests"), _REPO_ROOT, env.get("PYTHONPATH", "")])

    return _run_pytest_in(tmp_path, testfile.name, env, ("-rf", "--tb=line"))


def _run_pytest_in(ordner, dateiname, env, extra_args=()):
    """pytest-Untersitzung starten — cwd IM Zielordner, Argument nur der Dateiname.

    ⚠️ NIEMALS auf ``cwd=_REPO_ROOT`` + absoluten ``tmp_path``-Pfad zurueckbauen
    (so stand es an BEIDEN Aufrufstellen dieser Datei bis 2026-08-04). Genau
    deshalb gibt es diesen gemeinsamen Helfer: der Fehler war zweimal derselbe,
    und beim ersten Anlauf wurde nur eine der beiden Stellen repariert — die
    andere fiel im naechsten Messlauf durch (5 von 12 rot).

    WARUM (XPLAT-WIN): ``tmp_path`` liegt unterhalb des Temp-Ordners. Zeigt ein
    pytest-Argument dorthin, sammelt pytest den Temp-Ordner und vergleicht in
    ``_pytest/main.py`` jeden Eintrag darin::

        if sys.platform == "win32" and not is_match:
            is_match = samefile_nofollow(node.path, matchparts[0])   # -> lstat()

    Das ist eine WINDOWS-ONLY-Stelle (Kurzpfad-Behandlung, pytest #11895) — auf
    Linux existiert sie nicht, deshalb faellt das dort nie auf.

    Gemessen 2026-08-04 auf Davids Rechner: 7722 Eintraege im Temp-Ordner, von
    denen dutzende pro 6 Sekunden entstehen und vergehen — gewoehnliche
    ``tempfile``-Nutzung der parallel laufenden Segmente (``lightos_fixtures_*``,
    ``tmp*``, …). Einer ist beim ``lstat`` immer schon weg ->
    ``FileNotFoundError`` in der SAMMELPHASE der Untersitzung, also bevor
    ueberhaupt ein Test lief.

    Das war die gefaehrliche Sorte Fehlschlag: nach aussen fehlte schlicht das
    „FAILED" in der Ausgabe — exakt das Bild des QA-REPORTLOSS-Defekts, den diese
    Datei bewacht. Der Waechter meldete also seinen eigenen Befund, ausgeloest
    von etwas voellig anderem.

    Mit cwd im Zielordner beginnt pytests Sammelbaum dort (eine einzige Datei)
    und fasst den Temp-Ordner nie an. Seriell faellt nichts davon auf — deshalb
    war es bis zum ersten PARALLELEN Windows-Gate-Lauf unsichtbar.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", dateiname, "-q",
         "-p", "no:cacheprovider", "-p", "conftest", *extra_args],
        cwd=str(ordner), env=env, capture_output=True, text=True, timeout=300)


@pytest.mark.parametrize("env_extra, label", [
    ({}, "ohne Haertung"),
    ({"LIGHTOS_HARDEN_EXIT_ALL": "1"}, "mit genereller Haertung"),
])
def test_failure_report_survives(tmp_path, env_extra, label):
    proc = _run_subsession(tmp_path, env_extra)
    out = proc.stdout + proc.stderr

    assert "FAILED" in out, (
        f"pytest-Bericht fehlt ({label}) — genau der QA-REPORTLOSS-Defekt: die "
        "Exit-Haertung beendet den Prozess, bevor der TerminalReporter seine "
        "Zusammenfassung schreibt. Ein rotes Segment mit echten Fehlschlaegen sieht "
        "dann aus wie ein harmloser Teardown-Crash.\n"
        f"--- Ausgabe ---\n{out}")
    assert "test_absichtlich_rot" in out, (
        f"Der Name des fehlgeschlagenen Tests fehlt im Bericht ({label}).\n{out}")
    assert proc.returncode != 0, (
        f"Exitcode muss den Fehlschlag melden ({label}), war {proc.returncode}")


def test_hardening_reports_the_real_exit_status(tmp_path):
    """Die Härtung darf den Exitcode nicht schönen — nur die Abbauphase überspringen."""
    gruen = tmp_path / "test_nur_gruen.py"
    gruen.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["LIGHTOS_HARDEN_EXIT_ALL"] = "1"
    # Repo-Root MUSS mit rein: tests/conftest.py importiert src.core.paths, und
    # das kam bisher nur ueber cwd=_REPO_ROOT in den sys.path.
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.join(_REPO_ROOT, "tests"), _REPO_ROOT, env.get("PYTHONPATH", "")])

    # Ueber den gemeinsamen Helfer — cwd im Zielordner, s. dessen Docstring.
    proc = _run_pytest_in(tmp_path, gruen.name, env)
    assert proc.returncode == 0, (
        "Eine gruene Session muss mit 0 enden, auch unter der Haertung.\n"
        f"{proc.stdout}{proc.stderr}")
