"""UI-145: Klicktest-Befunde Show-Dateien/Autosave/Undo (23.11.2026).

1. Minikarte der 2D-Buehne ist nach „Neue Show" leer (Positionen der alten
   Show bleiben nicht stehen).
2. Kaputte/fehlende Datei: deutsche Meldung statt rohem Ausnahmetext; ein
   verschwundener Eintrag fliegt aus „Zuletzt verwendet".
3. Fenstertitel traegt bei ungespeicherten Aenderungen einen Stern.
4. Rueckgaengig-Text „Gerät „PAR 6“ geändert" statt „Fixture ~PAR 6".
5. Meldungen erscheinen mittig ueber dem Hauptfenster.
6. Lange Namen in „Zuletzt verwendet" werden in der Mitte gekuerzt.
7. Beim Start (``--show``) keine Lademeldung in der Statuszeile.

Alles mit Wegwerf-Shows im Temp-Ordner, offscreen.
"""
import os
import tempfile
import time
import unittest
import uuid
import zipfile
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from src.core.show import show_file as SF  # noqa: E402

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True, scope="module")
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


def _tmp(name: str, endung: str = ".lshow") -> str:
    return os.path.join(tempfile.gettempdir(),
                        f"ui145_{name}_{uuid.uuid4().hex}{endung}")


def _any_pid() -> int:
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine as fdb_engine
    from src.core.database.models import FixtureProfile
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id)).scalars().first())


def _dimmer(fid: int, addr: int, label: str):
    from src.core.database.models import PatchedFixture
    return PatchedFixture(
        fid=fid, label=label, fixture_profile_id=_any_pid(),
        mode_name="", universe=1, address=addr, channel_count=1,
        manufacturer_name="Test", fixture_name="Test", fixture_type="dimmer")


def _warten(app, bedingung, sekunden: float = 5.0) -> bool:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        app.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(bedingung())


ROH = ("zip file", "Expecting", "Errno", "delimiter", "char ")


class OeffnenFehlertextTest(unittest.TestCase):
    """Punkt 2 ohne Fenster: ``load_show`` liefert eine verstaendliche Meldung."""

    def setUp(self):
        self.pfade = []

    def tearDown(self):
        for p in self.pfade:
            try:
                os.remove(p)
            except OSError:
                pass

    def _datei(self, inhalt: bytes) -> str:
        p = _tmp("kaputt")
        with open(p, "wb") as f:
            f.write(inhalt)
        self.pfade.append(p)
        return p

    def _pruefen(self, pfad, *erwartet):
        ok, msg = SF.load_show(pfad)
        self.assertFalse(ok)
        for roh in ROH:
            self.assertNotIn(roh, msg, msg)
        for wort in erwartet:
            self.assertIn(wort, msg, msg)
        return msg

    def test_zufallsbytes(self):
        self._pruefen(self._datei(os.urandom(512)), "keine gültige LightOS-Show",
                      "Ältere Version öffnen")

    def test_leere_datei(self):
        self._pruefen(self._datei(b""), "keine gültige LightOS-Show")

    def test_abgeschnittenes_show_json(self):
        p = _tmp("halb")
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("show.json", '{"version": "1.2", "patch": [ {"fid": 1')
        self.pfade.append(p)
        self._pruefen(p, "beschädigt")

    def test_zip_ohne_show_json(self):
        p = _tmp("ohne")
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("anderes.txt", "x")
        self.pfade.append(p)
        self._pruefen(p, "keine gültige LightOS-Show")

    def test_fehlende_datei(self):
        msg = self._pruefen(_tmp("weg"), "nicht gefunden")
        self.assertIn("verschoben", msg)


class UndoTextTest(unittest.TestCase):
    """Punkt 4: verstaendlicher Rueckgaengig-Text fuer eine Geraete-Aenderung."""

    def test_label_aendern(self):
        _app()
        from src.core.app_state import get_state
        from src.core.undo import get_undo_stack
        st = get_state()
        SF.reset_show()
        try:
            st.add_fixture(_dimmer(1, 1, "PAR 5"), undoable=False)
            get_undo_stack().clear()
            st.update_fixture(1, label="PAR 6")
            text = get_undo_stack().undo_label() or ""
            self.assertNotIn("~", text)
            self.assertEqual("Gerät „PAR 5“ geändert", text)
        finally:
            get_undo_stack().clear()
            SF.reset_show()


class MitteKuerzenTest(unittest.TestCase):
    """Punkt 6 als reine Funktion."""

    def test_kurz_bleibt(self):
        from src.ui import main_window as mw
        self.assertEqual("Show.lshow", mw._mitte_kuerzen("Show.lshow"))

    def test_lang_mittig(self):
        from src.ui import main_window as mw
        name = "A" * 200 + "_ende.lshow"
        kurz = mw._mitte_kuerzen(name)
        self.assertLessEqual(len(kurz), mw.ZULETZT_MAX_ZEICHEN)
        self.assertIn("…", kurz)
        self.assertTrue(kurz.startswith("AAAA"))
        self.assertTrue(kurz.endswith("_ende.lshow"))


class HauptfensterTest(unittest.TestCase):
    """Punkte 1, 2 (Zuletzt-Liste), 3, 5, 6, 7 am echten Hauptfenster."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.core.app_state import get_state
        from src.ui import main_window as mw
        cls.mw = mw
        cls.state = get_state()
        SF.reset_show()
        cls.state.add_fixture(_dimmer(1, 1, "PAR 1"), undoable=False)
        cls.state.add_fixture(_dimmer(2, 2, "PAR 2"), undoable=False)
        cls.state.live_view_positions = {1: (100.0, 100.0), 2: (400.0, 300.0)}
        cls.pfad = _tmp("show")
        SF.save_show(cls.pfad)
        cls.zuletzt: list[str] = []
        cls._patches = [
            mock.patch.object(mw, "_load_recent_files", lambda: list(cls.zuletzt)),
            mock.patch.object(mw, "_save_recent_files",
                              lambda p: cls.zuletzt.__setitem__(slice(None), list(p))),
            mock.patch.object(mw, "_add_recent_file", lambda p: cls.zuletzt.insert(0, p)),
        ]
        for p in cls._patches:
            p.start()
        cls.win = mw.MainWindow()

    @classmethod
    def tearDownClass(cls):
        for p in cls._patches:
            p.stop()
        try:
            os.remove(cls.pfad)
        except OSError:
            pass
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        SF.reset_show()
        cls.app.processEvents()

    def _oeffnen(self, **kw):
        with mock.patch.object(self.mw.QMessageBox, "warning", lambda *a, **k: None):
            self.win._open_show_path(self.pfad, **kw)
        self.app.processEvents()
        self.app.processEvents()

    def _canvas(self):
        from src.ui.views.live_view import StageCanvas
        leinwaende = self.win.findChildren(StageCanvas)
        self.assertTrue(leinwaende, "keine 2D-Buehne im Hauptfenster")
        return leinwaende[0]

    # Punkt 1
    def test_minikarte_nach_neuer_show_leer(self):
        self._oeffnen()
        canvas = self._canvas()
        self.assertTrue(_warten(self.app, lambda: len(canvas._positions) == 2),
                        canvas._positions)
        with mock.patch.object(self.mw.QMessageBox, "question",
                               lambda *a, **k: QMessageBox.StandardButton.Yes), \
             mock.patch.object(self.win, "_has_unsaved_changes", lambda: False):
            self.win._new_show()
        self.assertEqual([], self.state.get_patched_fixtures())
        self.assertTrue(_warten(self.app, lambda: not canvas._positions),
                        f"Minikarte zeigt alte Geraete: {canvas._positions}")

    # Punkt 3
    def test_stern_im_titel(self):
        self._oeffnen()
        self.assertFalse(self.win.windowTitle().startswith("*"),
                         self.win.windowTitle())
        self.state.update_fixture(1, label="PAR 6")
        self.assertTrue(_warten(self.app,
                                lambda: self.win.windowTitle().startswith("* ")),
                        self.win.windowTitle())
        self.assertTrue(self.win.property("ungespeichert"))
        # Speichern nimmt den Stern weg
        self.assertTrue(self.win._do_save(self.pfad))
        self.app.processEvents()
        self.assertTrue(_warten(self.app,
                                lambda: not self.win.windowTitle().startswith("*")),
                        self.win.windowTitle())

    # Punkt 2 (Zuletzt-Liste)
    def test_fehlende_datei_fliegt_aus_zuletzt(self):
        weg = _tmp("verschoben")
        self.zuletzt[:] = [weg, self.pfad]
        self.win._rebuild_recent_menu()
        meldungen = []
        with mock.patch.object(self.mw.QMessageBox, "warning",
                               lambda *a, **k: meldungen.append(a)):
            self.win._open_show_path(weg)
        self.assertEqual([self.pfad], self.zuletzt)
        self.assertEqual(1, len(meldungen))
        text = meldungen[0][2]
        self.assertIn("nicht gefunden", text)
        self.assertIn("Zuletzt verwendet", text)
        self.assertNotIn("Errno", text)

    # Punkt 6
    def test_zuletzt_lange_namen_gekuerzt(self):
        lang = os.path.join(tempfile.gettempdir(), "B" * 230 + ".lshow")
        self.zuletzt[:] = [lang]
        self.win._rebuild_recent_menu()
        acts = [a for a in self.win._recent_menu.actions()
                if a.toolTip() == lang]
        self.assertEqual(1, len(acts))
        self.assertLessEqual(len(acts[0].text()), self.mw.ZULETZT_MAX_ZEICHEN)
        self.assertIn("…", acts[0].text())
        self.assertTrue(acts[0].text().endswith(".lshow"))

    # Punkt 7
    def test_start_ohne_lademeldung(self):
        self.win.statusBar().clearMessage()
        self._oeffnen(beim_start=True)
        self.assertEqual("", self.win.statusBar().currentMessage())
        # nach einem Handgriff (Datei → Öffnen) bleibt die Meldung
        self._oeffnen()
        self.assertIn("geladen", self.win.statusBar().currentMessage())

    # Punkt 5
    def test_meldung_mittig_ueber_hauptfenster(self):
        self.win.show()
        self.win.move(50, 40)
        self.app.processEvents()
        box = QMessageBox(QMessageBox.Icon.Warning, "Fehler", "Testmeldung",
                          QMessageBox.StandardButton.Ok, self.win)
        # Fenstermanager-Ersatz: die Box liegt zuerst am Rand
        box.move(5000, 0)
        box.show()
        try:
            mitte = self.win.frameGeometry().center()
            frei = self.win.screen().availableGeometry()

            def _mittig():
                g = box.frameGeometry()
                # Soll: mittig ueber dem Fenster, auf den Bildschirm begrenzt
                # (der Offscreen-Bildschirm ist kleiner als das Hauptfenster).
                x = max(frei.left(), min(mitte.x() - g.width() // 2,
                                         frei.right() - g.width() + 1))
                y = max(frei.top(), min(mitte.y() - g.height() // 2,
                                        frei.bottom() - g.height() + 1))
                return abs(g.x() - x) <= 20 and abs(g.y() - y) <= 20
            self.assertTrue(_warten(self.app, _mittig),
                            (box.frameGeometry(), self.win.frameGeometry()))
        finally:
            box.close()
            box.deleteLater()
            self.win.hide()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
