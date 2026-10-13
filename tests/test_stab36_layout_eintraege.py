"""STAB-36 / STAB-35: tote Layout-Eintraege in PySide — harte Abstuerze beim
Durchklicken von Geraeten im Programmer und beim Wechseln zwischen Shows.

Befund (Bedientest QA-96, auf ``main``): ``free(): invalid pointer`` /
„Fatal Python error: Aborted“ (Exit 134) nach einigen Auswahlwechseln im
Programmer bzw. beim dritten Show-Laden — an wechselnden Stellen, immer dort,
wo Qt gerade verzoegert loescht.

Ursache: die Paletten-Seiten (und die Spurliste des Show-Managers) raeumten ihr
Raster mit ``layout.itemAt(i).widget().deleteLater()`` ab. ``itemAt`` legt
einen Python-Wrapper fuer den Layout-Eintrag an, den PySide als Kind des
Layouts am Leben haelt; Qt loescht den Eintrag spaeter selbst, PySide merkt
davon nichts. Der Wrapper bleibt unter der freigegebenen Adresse eingetragen.
Bekommt ein spaeteres, in Python erzeugtes Qt-Objekt dieselbe Adresse, greift
PySide bei dessen Abbau zum alten Wrapper und gibt ihn mitten in der Benutzung
frei. Details: ``src/ui/layout_leeren.py``.

Geprueft wird dreifach:

1. die Ursache selbst, sofort und ohne Zufall (kein toter Wrapper bleibt
   zurueck) — an ``layout_leeren``, an der Paletten-Seite und an der Spurliste;
2. ein Waechter gegen neue ``itemAt``-Stellen an Layouts;
3. die Reproduktion aus dem Bedientest als Schleife in einem KINDPROZESS mit
   echtem Hauptfenster und echter Ereignisschleife (ein Absturz reisst so den
   Testlauf nicht mit). Vor dem Fix gemessen (mitgelieferte Shows): Show-Wechsel
   6 von 6 Laeufen abgestuerzt, Auswahlwechsel nach zwei Show-Wechseln 6 von 6.
"""
from __future__ import annotations

import gc
import os
import re
import shutil
import subprocess
import sys
import tempfile
import weakref
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[1]
_ROLLE = os.environ.get("STAB36_ARBEITER", "")
_MARKE = "STAB36-UEBERLEBT"

#: Mitgelieferte Shows (im Repo versioniert) fuer die Schleifen.
_SHOWS = ("Demo_Show_Full.lshow", "APC_Demo_Show.lshow", "Demo_ZQ_Buehne.lshow",
          "demo_apc_mk2.lshow")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _verzoegert_loeschen():
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


def _lebende_eintraege(layout) -> list:
    """Wrapper fuer Layout-EINTRAEGE (keine Layouts), die PySide noch als Kind
    von ``layout`` fuehrt — also unabhaengig von Python-Variablen am Leben."""
    from PySide6.QtWidgets import QLayout, QLayoutItem
    import shiboken6
    gc.collect()
    gefunden = []
    for o in gc.get_objects():
        if isinstance(o, QLayoutItem) and not isinstance(o, QLayout):
            try:
                if f"({hex(shiboken6.getCppPointer(layout)[0])})" in shiboken6.dump(o):
                    gefunden.append(o)
            except Exception:
                pass
    return gefunden


# ── 1. Ursache: kein Wrapper ueberlebt seinen Layout-Eintrag ────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestLayoutLeeren:

    def test_mechanismus_itemat_wrapper_ueberlebt_den_eintrag(self):
        """Haelt die Annahme fest, auf der der Fix beruht (PySide-Verhalten):
        nur das Widget loeschen laesst den ``itemAt``-Wrapper „gueltig“ auf
        einem Eintrag zurueck, den Qt laengst freigegeben hat."""
        from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget
        import shiboken6
        _app()
        w = QWidget()
        g = QGridLayout(w)
        b = QPushButton("a")
        g.addWidget(b, 0, 0)
        schwach = weakref.ref(g.itemAt(0))
        gc.collect()
        assert schwach() is not None, "itemAt-Wrapper haengt nicht mehr am Layout"
        b.deleteLater()
        del b
        _verzoegert_loeschen()
        assert g.count() == 0
        if schwach() is None or not shiboken6.isValid(schwach()):
            pytest.skip("diese PySide-Version raeumt den Wrapper selbst ab")
        w.deleteLater()

    def test_layout_leeren_laesst_keinen_wrapper_zurueck(self):
        from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel,
                                       QPushButton, QWidget)
        from src.ui.layout_leeren import layout_leeren
        _app()
        w = QWidget()
        g = QGridLayout(w)
        knoepfe = [QPushButton(str(i)) for i in range(6)]
        for i, b in enumerate(knoepfe):
            g.addWidget(b, i // 3, i % 3)
        unter = QHBoxLayout()
        unter.addWidget(QLabel("x"))
        unter.addStretch(1)
        g.addLayout(unter, 2, 0)
        g.setRowStretch(3, 1)
        schwach = [weakref.ref(g.itemAt(i)) for i in range(g.count())]
        assert all(s() is not None for s in schwach)

        layout_leeren(g)

        assert g.count() == 0
        assert not _lebende_eintraege(g)
        assert all(b.isHidden() for b in knoepfe)
        # das Unter-Layout IST sein eigener Eintrag und lebt, solange die
        # Variable hier es haelt
        del knoepfe, unter
        _verzoegert_loeschen()
        gc.collect()
        assert all(s() is None for s in schwach), "Wrapper haengt noch am Layout"
        # und das Raster ist weiter benutzbar
        g.addWidget(QPushButton("neu"), 0, 0)
        assert g.count() == 1
        w.deleteLater()

    def test_layout_leeren_vertraegt_leer_und_none(self):
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        from src.ui.layout_leeren import layout_leeren
        _app()
        w = QWidget()
        lay = QVBoxLayout(w)
        layout_leeren(lay)
        layout_leeren(None)
        assert lay.count() == 0
        w.deleteLater()

    def test_paletten_seite_hinterlaesst_keine_toten_eintraege(self):
        from src.core.engine.palette import Palette, PaletteManager, PaletteType
        from src.ui.views.palette_view import PaletteButton, PalettePage
        _app()
        manager = PaletteManager()
        for p in list(manager.get_by_type(PaletteType.COLOR)):
            manager.remove(p)
        for i in range(8):
            manager.add(Palette(name=f"P{i}", type=PaletteType.COLOR,
                                folder="A" if i % 2 else ""))
        seite = PalettePage(PaletteType.COLOR, manager)
        erwartet = seite._grid.count()
        assert erwartet >= 8
        for _ in range(5):
            seite._refresh()
            _verzoegert_loeschen()
            assert seite._grid.count() == erwartet
            assert not _lebende_eintraege(seite._grid), (
                "nach dem Neuaufbau haengen Wrapper geloeschter Layout-Eintraege "
                "am Raster (STAB-36)")
        sichtbar = [b for b in seite.findChildren(PaletteButton)]
        assert len(sichtbar) == 8
        seite.deleteLater()

    def test_spurliste_hinterlaesst_keine_toten_eintraege(self):
        from types import SimpleNamespace
        from src.ui.views.show_manager_view import TrackLabelPanel
        _app()
        spuren = [SimpleNamespace(name=f"Spur {i}", muted=False) for i in range(4)]
        smv = SimpleNamespace(_current_show=SimpleNamespace(tracks=spuren))
        liste = TrackLabelPanel(smv)
        for _ in range(5):
            liste.refresh()
            _verzoegert_loeschen()
            # vier Zeilen + EIN Abstandhalter — frueher kam je Aufruf einer dazu
            assert liste.layout().count() == 5
            assert not _lebende_eintraege(liste.layout())
        liste.deleteLater()


# ── 2. Waechter ─────────────────────────────────────────────────────────────

#: Dateien unter ``src/``, die ``.itemAt(`` aufrufen duerfen — mit Grund.
_ITEMAT_ERLAUBT = {
    "src/ui/layout_leeren.py": "nimmt den Eintrag direkt danach heraus",
    "src/ui/views/efx_view.py": "liest nur; das Formular lebt so lang wie seine Zeilen",
    "src/ui/views/snap_file_panel.py": "Listen-Eintrag unter dem Mauszeiger, kein Layout",
    "src/ui/views/function_manager_view.py": "Baum-Eintrag unter dem Mauszeiger, kein Layout",
    "src/ui/widgets/flow_layout.py": "eigenes Layout, definiert itemAt selbst",
}


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
def test_kein_neues_itemat_an_layouts():
    """``layout.itemAt(i)`` hinterlaesst einen Wrapper, der den Eintrag
    ueberlebt, sobald Qt ihn selbst loescht. Wer ein Layout leeren will, nimmt
    ``src.ui.layout_leeren.layout_leeren``; wer nur lesen will, traegt die
    Datei hier mit Begruendung ein."""
    treffer = {}
    for pfad in sorted((REPO / "src").rglob("*.py")):
        text = pfad.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\.itemAt(Position)?\(", text):
            treffer[pfad.relative_to(REPO).as_posix()] = True
    neu = sorted(set(treffer) - set(_ITEMAT_ERLAUBT))
    assert not neu, (
        "neue itemAt-Aufrufe (STAB-36: layout_leeren benutzen oder hier mit "
        f"Grund eintragen): {neu}")


# ── 3. Reproduktion als Schleife im Kindprozess ─────────────────────────────


def _schritte_fahren(schritte, abstand_ms: int):
    """Schritte in einer ECHTEN Ereignisschleife abarbeiten — nur dort gibt Qt
    die verzoegert geloeschten Objekte so frei wie in der laufenden App."""
    from PySide6.QtCore import QEventLoop, QTimer
    schleife = QEventLoop()
    folge = iter(schritte)
    fehler = []

    def naechster():
        try:
            schritt = next(folge)
        except StopIteration:
            schleife.quit()
            return
        try:
            schritt()
        except Exception as e:      # sichtbar machen statt in Qt versickern
            fehler.append(e)
            schleife.quit()
            return
        QTimer.singleShot(abstand_ms, naechster)

    QTimer.singleShot(abstand_ms, naechster)
    schleife.exec()
    if fehler:
        raise fehler[0]


@pytest.mark.skipif(not _ROLLE, reason="laeuft nur als Kindprozess der Schleifen-Tests")
@pytest.mark.timeout(110)
def test_arbeiter():
    """Kindprozess: echtes Hauptfenster (offscreen), Shows wechseln bzw.
    Geraete im Programmer durchklicken. Endet mit Exit 0 und der Marke — oder
    stirbt mit dem Absturz, den der Elternprozess dann meldet."""
    import faulthandler
    faulthandler.enable()
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox
    _app()
    from src.core.show import show_file
    from src.ui import main_window
    from src.ui.views.programmer_view import ProgrammerView

    arbeit = tempfile.mkdtemp(prefix="stab36_")
    kopien = []
    for i, name in enumerate(_SHOWS):
        ziel = os.path.join(arbeit, f"{i}_{name}")
        shutil.copyfile(REPO / "shows" / name, ziel)
        kopien.append(ziel)
    for knopf in ("warning", "information", "critical"):
        setattr(QMessageBox, knopf, staticmethod(lambda *a, **k: None))

    show_file.reset_show()
    fenster = main_window.MainWindow()
    fenster.resize(1600, 1000)
    fenster.show()
    runden = int(os.environ.get("STAB36_RUNDEN", "3"))

    def laden(pfad):
        def schritt():
            print("LADE", os.path.basename(pfad), flush=True)
            ok, meldung = show_file.load_show(pfad)
            assert ok, meldung
            fenster._refresh_all_views()
        return schritt

    if _ROLLE == "show":
        _schritte_fahren([laden(k) for k in kopien * runden], 50)
    else:
        laden(kopien[0])()
        fenster._switch_section(2)                      # Programmer
        programmer = fenster.findChildren(ProgrammerView)[0]
        baum = programmer._fixture_list
        assert baum.topLevelItemCount() >= 2, "Show ohne Geraete im Baum"

        def klick(nr):
            def schritt():
                print("KLICK", nr, flush=True)
                # jedes Mal frisch nachschlagen: ein Neuaufbau ersetzt die Zeilen
                eintrag = baum.topLevelItem(nr % min(5, baum.topLevelItemCount()))
                QTest.mouseClick(baum.viewport(), Qt.MouseButton.LeftButton,
                                 Qt.KeyboardModifier.NoModifier,
                                 baum.visualItemRect(eintrag).center())
            return schritt

        # Wie im Bedientest gehen dem Durchklicken ein paar Neuaufbauten der
        # Ansichten voraus (Shows geladen, F5): dabei entstanden die toten
        # Eintraege, ueber die das Durchklicken spaeter stolperte. Ohne diesen
        # Vorlauf traf die Schleife mit den mitgelieferten Shows auf ``main``
        # in 20 Laeufen keinen einzigen (Zufall der Speicheradressen).
        vorher = [laden(kopien[1]), laden(kopien[0])]
        vorher += [fenster._refresh_all_views] * 6
        _schritte_fahren(vorher + [klick(i) for i in range(20 * runden)], 50)

    print(_MARKE, flush=True)
    # Bewusst hart beenden: geprueft wird die Schleife, nicht der Abbau eines
    # ganzen Hauptfensters am Prozessende (eigenes Thema, eigene Tests).
    sys.stdout.flush()
    os._exit(0)


def _kind_umgebung(tmp_path, rolle: str, runden: int) -> dict:
    """Eigener Sandkasten fuer das Kind (QA-53: nie die Show-DB des
    Elternlaufs erben)."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["STAB36_ARBEITER"] = rolle
    env["STAB36_RUNDEN"] = str(runden)
    env["LIGHTOS_SHOW_DB"] = str(tmp_path / "show.db")
    env["LIGHTOS_CRASH_LOG"] = str(tmp_path / "crash.log")
    daten = tmp_path / "daten"
    daten.mkdir(exist_ok=True)
    env["XDG_DATA_HOME"] = str(daten)
    env["APPDATA"] = str(daten)
    env.pop("LIGHTOS_UNIVERSES_JSON", None)
    env.pop("LIGHTOS_SACN_CID", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


def _schleife_im_kind(tmp_path, rolle: str, laeufe: int, runden: int):
    for lauf in range(1, laeufe + 1):
        ordner = tmp_path / f"lauf{lauf}"
        ordner.mkdir()
        fertig = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-s",
             "-p", "no:cacheprovider", "-o", "addopts=",
             f"tests/{Path(__file__).name}::test_arbeiter"],
            cwd=str(REPO), env=_kind_umgebung(ordner, rolle, runden),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=115)
        aus = (fertig.stdout or "") + "\n" + (fertig.stderr or "")
        schritte = len(re.findall(r"^(?:LADE|KLICK) ", aus, flags=re.M))
        assert fertig.returncode == 0 and _MARKE in aus, (
            f"Lauf {lauf} von {laeufe} ({rolle}): Kindprozess endete mit "
            f"{fertig.returncode} nach {schritte} Schritten — nativer Absturz "
            f"oder Fehler:\n{aus[-3000:]}")


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.timeout(200)
def test_show_wechsel_in_schleife_stuerzt_nicht_ab(tmp_path):
    """STAB-35: zwoelf Show-Wechsel je Lauf. Vor dem Fix starb der Kindprozess
    beim dritten bis fuenften Laden (6 von 6 Laeufen)."""
    _schleife_im_kind(tmp_path, "show", laeufe=2, runden=3)


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.timeout(200)
def test_auswahlwechsel_in_schleife_stuerzt_nicht_ab(tmp_path):
    """STAB-36: 60 Auswahlwechsel im Programmer je Lauf, nach zwei
    Show-Wechseln. Vor dem Fix starb der Kindprozess nach wenigen Klicks mit
    ``free(): invalid pointer`` (6 von 6 Laeufen)."""
    _schleife_im_kind(tmp_path, "auswahl", laeufe=2, runden=3)
