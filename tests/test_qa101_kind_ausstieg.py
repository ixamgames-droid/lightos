"""QA-101 — Kindprozesse der Schleifentests enden auch unter Windows sauber.

Vier Schleifentests (eng35, eng37, stab36, stab38) fahren die Bedienung in
einem Kindprozess, der am Ende eine Fertig-Marke druckt und sich hart beendet.
Der Elternteil verlangt Rueckgabe 0 und die Marke. Unter Windows lief
``os._exit`` nach nicht zugestellten ``deleteLater()`` in eine
Zugriffsverletzung im DLL-Abbau — mitunter mit Rueckgabe 0xC0000005, nach
bestandener Schleife. ``tests/_kind_ausstieg.py`` beendet dort per
``TerminateProcess``.

Geprueft wird hier:

* Marke + harter Ausstieg ergibt Rueckgabe 0, ein anderer Code bleibt erhalten;
* ein Absturz VOR der Marke bleibt rot (die Pruefung wird nicht schwaecher);
* der Ausloeser von QA-101 (nicht zugestellte Loeschung) endet ohne
  Zugriffsverletzung — unter Windows mit Gegenprobe, dass ``os._exit`` sie hat;
* die vier Schleifen-Arbeiter nutzen die Hilfe statt ``os._exit``.
"""
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
MARKE = "QA101-FERTIG"

ARBEITER = ("test_eng35_editoren.py", "test_eng37_modify_editor.py",
            "test_stab36_layout_eintraege.py",
            "test_stab38_matrix_parameterfelder.py")


def _kind(code: str, tmp_path) -> tuple[int, str]:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["LIGHTOS_SHOW_DB"] = str(tmp_path / "show.db")
    env["LIGHTOS_CRASH_LOG"] = str(tmp_path / "crash.log")
    daten = tmp_path / "daten"
    daten.mkdir(exist_ok=True)
    env["XDG_DATA_HOME"] = str(daten)
    env["APPDATA"] = str(daten)
    env.pop("LIGHTOS_UNIVERSES_JSON", None)
    env.pop("LIGHTOS_SACN_CID", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    vorspann = (f"import sys\nsys.path[:0] = [{str(REPO)!r}, {str(TESTS)!r}]\n"
                "import faulthandler\nfaulthandler.enable()\n")
    r = subprocess.run([sys.executable, "-c", vorspann + textwrap.dedent(code)],
                       cwd=str(REPO), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=90)
    return r.returncode, (r.stdout or "") + "\n" + (r.stderr or "")


def _bestanden(rc: int, aus: str) -> bool:
    """Dieselbe Bedingung wie in den vier Schleifentests."""
    return rc == 0 and MARKE in aus


def test_marke_und_harter_ausstieg_ergibt_null(tmp_path):
    rc, aus = _kind(f"""
        from _kind_ausstieg import harter_ausstieg
        print({MARKE!r}, flush=True)
        harter_ausstieg(0)
        raise SystemExit(7)          # darf nie erreicht werden
    """, tmp_path)
    assert _bestanden(rc, aus), (rc, aus[-2000:])


def test_anderer_exit_code_bleibt_erhalten(tmp_path):
    rc, aus = _kind("""
        from _kind_ausstieg import harter_ausstieg
        harter_ausstieg(3)
    """, tmp_path)
    assert rc == 3, (rc, aus[-2000:])


def test_ausgabe_ohne_zeilenende_geht_nicht_verloren(tmp_path):
    """Der Ausstieg leert stdout selbst — auch ohne flush beim print."""
    rc, aus = _kind(f"""
        import sys
        from _kind_ausstieg import harter_ausstieg
        sys.stdout.write("vorher-" + {MARKE!r})
        harter_ausstieg(0)
    """, tmp_path)
    assert _bestanden(rc, aus) and "vorher-" + MARKE in aus, (rc, aus[-2000:])


def test_absturz_vor_der_marke_bleibt_rot(tmp_path):
    """Ein nativer Absturz mitten in der Schleife darf nicht gruen werden."""
    rc, aus = _kind(f"""
        import faulthandler
        from _kind_ausstieg import harter_ausstieg
        print("RUNDE 1", flush=True)
        faulthandler._sigsegv()      # absichtlicher Absturz vor der Marke
        print({MARKE!r}, flush=True)
        harter_ausstieg(0)
    """, tmp_path)
    assert rc != 0, aus[-2000:]
    assert MARKE not in aus, aus[-2000:]
    assert not _bestanden(rc, aus)


# Ausloeser aus QA-101: Editoren gezeigt, per deleteLater() abgebaut, ohne dass
# die Loeschung zugestellt wird (processEvents stellt DeferredDelete ohne
# Event-Schleife nicht zu) — wie am Ende von test_eng35_editoren.test_arbeiter.
_AUSLOESER = """
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.core.engine.function_manager import get_function_manager
    from test_eng35_editoren import _editoren
    editoren = _editoren(get_function_manager())
    for _n, _f, ed in editoren:
        ed.show()
    app.processEvents()
    for _n, _f, ed in editoren:
        ed.close()
        ed.deleteLater()
    app.processEvents()
    print({marke!r}, flush=True)
"""


def test_nicht_zugestellte_loeschung_endet_ohne_zugriffsverletzung(tmp_path):
    rc, aus = _kind(_AUSLOESER.format(marke=MARKE) + """
    from _kind_ausstieg import harter_ausstieg
    harter_ausstieg(0)
    """, tmp_path)
    assert _bestanden(rc, aus), (rc, aus[-3000:])
    assert "fatal exception" not in aus and "Fatal Python error" not in aus, \
        aus[-3000:]


_VERLETZUNG = "Windows fatal exception: access violation"


def _gegenprobe_pruefen(rc: int, aus: str) -> None:
    """CDX-63 (Codex zu #1162): die Verletzung ist nur auf der gemessenen
    Installation belegt (Windows 11 ARM, emuliertes Python). Tritt sie hier
    nicht auf, ist das kein Fehler der App oder der Hilfe — dann wird die
    Gegenprobe uebersprungen statt rot (auch, wenn Qt den Fehler behebt). Die
    Hilfe selbst prueft ``test_harter_ausstieg_ruft_unter_windows_terminate``
    ohne echten Absturz."""
    assert MARKE in aus, aus[-3000:]
    if _VERLETZUNG not in aus:
        pytest.skip("Qt-Abbaufehler auf dieser Installation nicht nachstellbar "
                    f"(rc={rc}) — Gegenprobe entfaellt")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-Abbau (ExitProcess)")
def test_gegenprobe_os_exit_laeuft_unter_windows_in_die_verletzung(tmp_path):
    """Ohne die Hilfe meldet faulthandler die Verletzung in os._exit — sonst
    pruefte der Test oben nichts. (Die Rueckgabe ist dabei meist trotzdem 0;
    gemessen am 29.10.2026 auf Windows 11 ARM in jedem Lauf.)"""
    rc, aus = _kind(_AUSLOESER.format(marke=MARKE) + """
    import os
    os._exit(0)
    """, tmp_path)
    _gegenprobe_pruefen(rc, aus)


def test_gegenprobe_ohne_verletzung_wird_uebersprungen():
    """CDX-63: kein Abbaufehler auf dieser Installation -> uebersprungen,
    nicht rot; ein Absturz VOR der Marke bleibt rot."""
    with pytest.raises(pytest.skip.Exception):
        _gegenprobe_pruefen(0, f"{MARKE}\n")
    _gegenprobe_pruefen(0, f"{MARKE}\n{_VERLETZUNG}\n")   # nachgestellt: ok
    with pytest.raises(AssertionError):
        _gegenprobe_pruefen(0xC0000005, _VERLETZUNG)


def test_harter_ausstieg_ruft_unter_windows_terminate(monkeypatch):
    """CDX-63: der Windows-Weg der Hilfe, ohne echten Absturz und auf jedem
    System: TerminateProcess mit dem Exit-Code; os._exit nur als Rueckfall."""
    import ctypes
    import _kind_ausstieg as K

    aufrufe = []

    class _Fn:
        def __init__(self, name, wert=None):
            self.name, self.wert = name, wert

        def __call__(self, *a):
            aufrufe.append((self.name, a))
            return self.wert

    class _K32:
        def __init__(self, *_a, **_k):
            self.GetCurrentProcess = _Fn("GetCurrentProcess", 1234)
            self.TerminateProcess = _Fn("TerminateProcess", 1)

    class _Ende(BaseException):
        pass

    def _exit(rc):
        aufrufe.append(("os._exit", (rc,)))
        raise _Ende

    monkeypatch.setattr(K.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", _K32, raising=False)
    monkeypatch.setattr(K.os, "_exit", _exit)
    with pytest.raises(_Ende):
        K.harter_ausstieg(3)
    assert ("TerminateProcess", (1234, 3)) in aufrufe, aufrufe
    assert aufrufe.index(("TerminateProcess", (1234, 3))) < aufrufe.index(
        ("os._exit", (3,)))


@pytest.mark.parametrize("datei", ARBEITER)
def test_schleifen_arbeiter_nutzen_den_harten_ausstieg(datei):
    text = (TESTS / datei).read_text(encoding="utf-8")
    arbeiter = text[text.index("def test_arbeiter"):]
    arbeiter = arbeiter[:arbeiter.index("\ndef ", 1)]
    assert "harter_ausstieg(0)" in arbeiter, datei
    assert not re.search(r"^\s*os\._exit\(", arbeiter, flags=re.M), (
        f"{datei}: os._exit im Arbeiter — unter Windows stirbt das Kind "
        "dann mitunter nach der Marke (QA-101)")
