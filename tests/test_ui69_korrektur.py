"""UI-69 (Korrektur nach Review): Fehlalarme und Nebenwirkungen der
Speichern-Frage beim Beenden.

1. Reine Live-Bedienung weiterer VC-Elemente ist keine Show-Aenderung:
   XY-Pad (Pan/Tilt, Feld), Tempo-Bus-Regler (Quelle/Tap/Faktor/Fix-BPM),
   Speed-Dial (Multiplikator, Speed-Knoten-Faktor) — auch nicht, wenn sie dabei
   Rolle/Parent/Faktor ihres Tempo-Bus umstellen. Echte Einrichtung (Bus-Rolle
   im Tempo-Tab, Farbe einer Farb-Kachel) zaehlt weiter.
2. Der Vergleich schreibt das VC-Layout NICHT in den State — beim Laden
   uebersprungene Widgets blieben sonst nicht einmal im Auto-Save erhalten.
3. Nach der Absturz-Wiederherstellung gilt die Show als ungespeichert, ohne
   Pfad (Strg+S schrieb sonst in die Auto-Save-Datei) und fragt beim Beenden.
4. Der Auto-Patch des 3D-Visualizers (Live View -> visualizer_positions nach
   ``requestFixtures``) macht eine frisch geoeffnete Show nicht „geaendert".
5. Scheiternde Speicherung im Beenden-Dialog haelt das Fenster offen; Undo
   ueber den echten Undo-Stapel macht die Show wieder unveraendert.
"""
import json
import os
import tempfile
import unittest
import uuid
import zipfile
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.show import show_file as SF


def _app():
    return QApplication.instance() or QApplication([])


# XPLAT-15: Top-Level-Widgets nach jedem Test wirklich abbauen (Muster:
# tests/_qt_lifecycle.py, Vorbild test_vc_canvas_clear_on_new_show.py).
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


# Modulweit statt je Test: die Hauptfenster-Klassen teilen sich ein Fenster
# ueber ihre Tests; abgebaut wird es in ``tearDownClass``.
@_pytest_xplat15.fixture(autouse=True, scope="module")
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _tmp_pfad(name: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"ui69k_{name}_{uuid.uuid4().hex}.lshow")


def _any_pid() -> int:
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine as fdb_engine
    from src.core.database.models import FixtureProfile
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id)).scalars().first())


def _dimmer(fid: int, addr: int = 1):
    from src.core.database.models import PatchedFixture
    return PatchedFixture(
        fid=fid, label=f"Fix {fid}", fixture_profile_id=_any_pid(),
        mode_name="", universe=1, address=addr, channel_count=1,
        manufacturer_name="Test", fixture_name="Test", fixture_type="dimmer")


#: VC-Layout der Test-Show: je ein Bedienelement pro geprueftem Typ.
_VC = {"widgets": [
    {"type": "VCXYPad", "caption": "Pad", "x": 10, "y": 10, "w": 160, "h": 160,
     "mode": "position", "pan": 0.5, "tilt": 0.5},
    {"type": "VCXYPad", "caption": "Feld", "x": 180, "y": 10, "w": 160, "h": 160,
     "mode": "area", "efx_function_id": None},
    {"type": "VCTempoBusController", "caption": "Tempo B", "x": 350, "y": 10,
     "w": 220, "h": 170, "tempo_bus_id": "B", "source": "tap", "factor": 1.0,
     "fixed_bpm": 128.0},
    {"type": "VCSpeedDial", "caption": "Mult", "x": 10, "y": 200, "w": 160, "h": 160,
     "target_mode": "TempoBusMult", "mult": 1.0, "active_factor": 1.0},
    {"type": "VCSpeedDial", "caption": "Knoten C", "x": 180, "y": 200, "w": 160,
     "h": 160, "target_mode": "SpeedNode", "role": "sub", "tempo_bus_id": "C",
     "parent_bus_id": "B", "active_factor": 1.0},
    {"type": "VCColor", "caption": "Rot", "x": 350, "y": 200, "w": 80, "h": 60,
     "color_r": 255, "color_g": 0, "color_b": 0},
]}


class VisualizerAutoPatchTest(unittest.TestCase):
    """Befund 4: der Auto-Patch nach ``requestFixtures`` ist keine Aenderung.

    Steht VOR den Hauptfenster-Tests: deren Views bleiben am State haengen und
    gleichen beim Laden die 3D-Positionen schon selbst an — dann haette der
    Auto-Patch hier nichts mehr zu tun (die Vorbedingung im Test meldet das)."""

    def setUp(self):
        _app()
        from src.core.app_state import get_state
        self.state = get_state()
        SF.reset_show()
        self.state.add_fixture(_dimmer(1, 1), undoable=False)
        self.pfad = _tmp_pfad("viz")
        SF.save_show(self.pfad)
        # Show im Legacy-Format (ohne Szenegraph) mit einer 3D-Position, deren
        # Rundweg ueber die Live-View-Pixel nicht exakt zurueckfuehrt (so in
        # echten Shows): der Auto-Patch schreibt beim ersten requestFixtures
        # eine um Rundungsfehler andere Position.
        with zipfile.ZipFile(self.pfad) as z:
            inhalt = {n: z.read(n) for n in z.namelist()}
        daten = json.loads(inhalt["show.json"])
        daten.pop("scene_graph", None)
        daten["visualizer"]["positions"] = {"1": [0.1 + 0.2, 4.2, 1.0 / 3.0]}
        inhalt["show.json"] = json.dumps(daten).encode("utf-8")
        with zipfile.ZipFile(self.pfad, "w") as z:
            for n, b in inhalt.items():
                z.writestr(n, b)
        ok, msg = SF.load_show(self.pfad)
        self.assertTrue(ok, msg)
        self.vorher = dict(self.state.visualizer_positions)
        self.assertIn(1, self.vorher)
        self.assertFalse(SF.show_hat_aenderungen(self.state))

    def tearDown(self):
        try:
            os.remove(self.pfad)
        except OSError:
            pass
        SF.reset_show()

    def _bridge(self):
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        b = VisualizerBridge(self.state)
        self.addCleanup(b.dispose)
        return b

    def test_auto_patch_nach_dem_oeffnen_ist_keine_aenderung(self):
        self._bridge().requestFixtures()
        self.assertNotEqual(self.vorher, dict(self.state.visualizer_positions),
                            "Vorbedingung: der Auto-Patch hat die 3D-Position geschrieben")
        self.assertFalse(SF.show_hat_aenderungen(self.state),
                         "abgeleitete 3D-Position nach reinem Oeffnen = Fehlalarm")

    def test_echte_aenderung_bleibt_sichtbar(self):
        # Vorher schon echte 3D-Arbeit (ausgeblendeter Kegel): dann fuehrt der
        # Auto-Patch nichts nach — die Frage bleibt.
        self.state.visualizer_beams_off = {1}
        self.assertTrue(SF.show_hat_aenderungen(self.state))
        self._bridge().requestFixtures()
        self.assertTrue(SF.show_hat_aenderungen(self.state))
        self.state.visualizer_beams_off = set()
        self.assertTrue(SF.show_hat_aenderungen(self.state),
                        "die abgeleitete Position wurde nicht nachgefuehrt, weil "
                        "der 3D-Block vorher schon abwich")

    def test_live_view_verschieben_zaehlt(self):
        self._bridge().requestFixtures()
        self.state.live_view_positions = {1: (400.0, 300.0)}
        self._bridge().requestFixtures()
        self.assertTrue(SF.show_hat_aenderungen(self.state),
                        "Verschieben in der Live View ist Show-Arbeit")


class _MitHauptfenster(unittest.TestCase):
    """Ein MainWindow fuer alle Tests der Klasse (der Bau ist teuer); jeder Test
    oeffnet die Show frisch."""

    pfad = None
    win = None

    @classmethod
    def _show_bauen(cls, state):
        raise NotImplementedError

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.core.app_state import get_state
        from src.ui import main_window as mw
        cls.mw = mw
        cls.state = get_state()
        SF.reset_show()
        cls._show_bauen(cls.state)
        cls.pfad = _tmp_pfad(cls.__name__)
        SF.save_show(cls.pfad)
        cls.win = mw.MainWindow()

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.pfad)
        except OSError:
            pass
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        # Fenster der Klasse wirklich abbauen: ihre Views haengen sonst weiter am
        # State und reagieren auf das Laden der naechsten Testklasse.
        destroy_all_top_level_widgets(cls.app)
        SF.reset_show()
        cls.app.processEvents()

    def _oeffnen(self):
        with mock.patch.object(self.mw.QMessageBox, "warning", lambda *a, **k: None):
            self.win._open_show_path(self.pfad)
        self.app.processEvents()
        self.app.processEvents()
        self.assertEqual(self.pfad, self.win._current_show_path)
        self.assertFalse(self.win._has_unsaved_changes(),
                         "Vorbedingung: frisch geoeffnet = unveraendert")

    def _widget(self, cls, caption):
        for w in self.win._vc_view._canvas.findChildren(cls):
            if w.caption == caption:
                return w
        self.fail(f"VC-Element {caption!r} nicht aufgebaut")


class VCLiveBedienungTest(_MitHauptfenster):
    """Befund 1: Bedienen im Run-Modus fragt nicht nach dem Speichern."""

    @classmethod
    def _show_bauen(cls, state):
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        mgr = get_tempo_bus_manager()
        mgr.ensure_bus("B").set_role("master")
        mgr.ensure_bus("C")
        mgr.ensure_bus("D").set_role("master")   # von keinem VC-Element gesteuert
        state._vc_layout = json.loads(json.dumps(_VC))

    def test_xypad_position(self):
        from src.ui.virtualconsole.vc_xypad import VCXYPad
        self._oeffnen()
        pad = self._widget(VCXYPad, "Pad")
        pad._pos_to_value(QPoint(30, 140))           # Pad ziehen
        pad._set_axis_norm("pan", 0.9)               # MIDI-Regler
        self.assertNotEqual(0.5, pad.to_dict()["pan"], "Pad wurde nicht bewegt")
        self.assertFalse(self.win._has_unsaved_changes(),
                         "XY-Pad bewegen ist Live-Bedienung (pan/tilt)")

    def test_xypad_feld_markieren(self):
        from src.ui.virtualconsole.vc_xypad import VCXYPad
        self._oeffnen()
        feld = self._widget(VCXYPad, "Feld")
        feld._area = (0.1, 0.2, 0.6, 0.7)            # wie mouseMove im Feld-Modus
        feld._apply_area()
        self.assertIn("area", feld.to_dict())
        self.assertFalse(self.win._has_unsaved_changes(),
                         "Feld im XY-Pad markieren ist Live-Bedienung (area)")

    def test_tempo_bus_regler(self):
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        from src.ui.virtualconsole.vc_tempo_bus_controller import VCTempoBusController
        self._oeffnen()
        tbc = self._widget(VCTempoBusController, "Tempo B")
        tbc.set_source("sound")          # Bus B wird Sub (role/parent/Faktor)
        self.assertEqual("sub", get_tempo_bus_manager().get("B").role,
                         "Vorbedingung: der Regler stellt den Bus um")
        self.assertFalse(self.win._has_unsaved_changes(),
                         "Quelle Sound: source + Bus-Rolle sind Live-Bedienung")
        tbc._tap()                       # setzt source='tap', Bus wieder Master
        tbc.set_factor(2.0)
        tbc.set_source("fix")
        tbc.fixed_bpm += 3.0             # wie das Mausrad im Fix-Modus
        tbc._apply_source()
        self.assertFalse(self.win._has_unsaved_changes(),
                         "Tap/Faktor/Fix-BPM sind Live-Bedienung")

    def test_speed_dial_multiplikator_und_knoten(self):
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        from src.ui.virtualconsole.vc_speedial import VCSpeedDial
        self._oeffnen()
        self._widget(VCSpeedDial, "Mult")._set_factor(2.0)       # -> mult
        self.assertFalse(self.win._has_unsaved_changes(),
                         "Faktor am Multiplikator-Dial ist Live-Bedienung (mult)")
        self._widget(VCSpeedDial, "Knoten C")._set_factor(4.0)   # -> bus_multiplier
        self.assertEqual(4.0, get_tempo_bus_manager().get("C").bus_multiplier)
        self.assertFalse(self.win._has_unsaved_changes(),
                         "Faktor am Speed-Knoten ist Live-Bedienung (bus_multiplier)")

    def test_einrichtung_zaehlt_weiter(self):
        """Gegenprobe: die Ausnahmen gelten nur fuer Bedienung."""
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        from src.ui.virtualconsole.vc_color import VCColor
        from PySide6.QtGui import QColor
        self._oeffnen()
        # Bus D steuert kein VC-Element -> Rolle im Tempo-Tab = Einrichtung
        get_tempo_bus_manager().get("D").set_role("sub")
        self.assertTrue(self.win._has_unsaved_changes(),
                        "Rolle eines nicht VC-gesteuerten Bus ist Einrichtung")
        get_tempo_bus_manager().get("D").set_role("master")
        self.assertFalse(self.win._has_unsaved_changes())
        # Farbe einer Farb-Kachel = was die Kachel tut, kein Bedienwert
        self._widget(VCColor, "Rot").set_color(QColor(0, 0, 255))
        self.assertTrue(self.win._has_unsaved_changes(),
                        "neue Kachelfarbe muss als Aenderung zaehlen")


class UebersprungeneWidgetsBleibenTest(_MitHauptfenster):
    """Befund 2: der Vergleich ueberschreibt state._vc_layout nicht."""

    @classmethod
    def _show_bauen(cls, state):
        state._vc_layout = {"widgets": [
            {"type": "VCButton", "caption": "Knopf", "x": 10, "y": 10, "w": 80, "h": 40},
            # Typ aus einer neueren Version: die Flaeche kann ihn nicht bauen
            {"type": "VCAusDerZukunft", "caption": "Neu", "x": 100, "y": 10,
             "w": 80, "h": 40}]}

    @staticmethod
    def _typen(layout):
        return [w.get("type") for w in (layout or {}).get("widgets", [])]

    def test_vergleich_laesst_rohes_widget_im_state(self):
        self._oeffnen()                       # merkt + vergleicht mehrfach
        self.assertFalse(self.win._has_unsaved_changes())
        self.assertIn("VCAusDerZukunft", self._typen(self.state._vc_layout),
                      "Vergleich hat das beim Laden uebersprungene Widget "
                      "aus dem State geloescht")
        # ... und damit landet es auch im Auto-Save (Absturz-Sicherung)
        auto = _tmp_pfad("auto")
        try:
            with mock.patch.object(self.win, "_autosave_path", lambda: auto):
                self.win._autosave_dirty = True
                self.win._do_autosave()
            with zipfile.ZipFile(auto) as z:
                daten = json.loads(z.read("show.json"))
            self.assertIn("VCAusDerZukunft", self._typen(daten["virtual_console"]),
                          "Auto-Save hat das uebersprungene Widget verloren")
        finally:
            try:
                os.remove(auto)
            except OSError:
                pass


class WiederherstellungTest(_MitHauptfenster):
    """Befund 3: nach der Auto-Save-Wiederherstellung fragt Beenden."""

    @classmethod
    def _show_bauen(cls, state):
        # Bewusst ohne Cuelisten/Funktionen: auch so muss Beenden fragen.
        state._vc_layout = {"widgets": [
            {"type": "VCButton", "caption": "Nur VC", "x": 10, "y": 10, "w": 80, "h": 40}]}

    def test_wiederhergestellte_show_ist_ungespeichert(self):
        mw = self.mw
        zuletzt = []
        with mock.patch.object(mw, "_recovery_prompt_suppressed", lambda: False), \
             mock.patch.object(mw, "_load_recent_files", lambda: []), \
             mock.patch.object(mw, "_add_recent_file", zuletzt.append), \
             mock.patch.object(self.win, "_autosave_path", lambda: self.pfad), \
             mock.patch.object(mw.QMessageBox, "question",
                               lambda *a, **k: QMessageBox.StandardButton.Yes), \
             mock.patch.object(mw.QMessageBox, "warning", lambda *a, **k: None):
            self.win._check_autosave_recovery()
        self.app.processEvents()
        from src.ui.virtualconsole.vc_widget import VCWidget
        self.assertEqual(["Nur VC"], [w.caption for w in
                                      self.win._vc_view._canvas.findChildren(VCWidget)],
                         "Vorbedingung: Auto-Save wurde geladen")
        self.assertIsNone(self.win._current_show_path,
                          "Strg+S wuerde in die Auto-Save-Datei schreiben")
        self.assertNotIn(self.pfad, zuletzt, "Auto-Save gehoert nicht in die Zuletzt-Liste")
        self.assertTrue(self.win._has_unsaved_changes(),
                        "wiederhergestellter Stand steht in keiner Show-Datei")

        # Beenden fragt; „Speichern" fuehrt zu „Speichern unter"
        fragen, dialoge = [], []

        def _speichern(*a, **k):
            fragen.append(a)
            return QMessageBox.StandardButton.Save

        def _unter(*a, **k):
            dialoge.append(a)
            return ("", "")                       # Nutzer bricht ab
        ev = QCloseEvent()
        with mock.patch.object(mw, "_exit_prompt_suppressed", lambda: False), \
             mock.patch.object(mw.QMessageBox, "question", _speichern), \
             mock.patch.object(mw.QFileDialog, "getSaveFileName", _unter):
            self.win.closeEvent(ev)
        self.assertEqual(1, len(fragen), "Beenden hat nicht gefragt")
        self.assertIn("Auto-Save", fragen[0][2])
        self.assertEqual(1, len(dialoge), "Speichern muss nach einem Ziel fragen")
        self.assertFalse(ev.isAccepted())

        # Nach echtem Speichern ist der Stand gesichert
        ziel = _tmp_pfad("ziel")
        try:
            with mock.patch.object(mw.QFileDialog, "getSaveFileName",
                                   lambda *a, **k: (ziel, "")):
                self.assertTrue(self.win._save_show())
            self.assertEqual(ziel, self.win._current_show_path)
            self.assertFalse(self.win._has_unsaved_changes())
        finally:
            try:
                os.remove(ziel)
            except OSError:
                pass


class GescheitertesSpeichernTest(_MitHauptfenster):
    """Befund 5a: scheitert das Speichern im Beenden-Dialog, bleibt das Fenster
    offen (Testluecke)."""

    @classmethod
    def _show_bauen(cls, state):
        from src.core.engine.cue_stack import CueStack
        state.cue_stacks.append(CueStack("Da"))

    def _beenden_mit_speichern(self, **patches):
        mw = self.mw
        ev = QCloseEvent()
        with mock.patch.object(mw, "_exit_prompt_suppressed", lambda: False), \
             mock.patch.object(mw.QMessageBox, "question",
                               lambda *a, **k: QMessageBox.StandardButton.Save), \
             mock.patch.object(mw.QMessageBox, "warning", lambda *a, **k: None):
            with contextlib_exit(patches):
                self.win.closeEvent(ev)
        return ev

    def test_speichern_unter_ohne_pfad(self):
        from src.core.engine.cue_stack import CueStack
        self._oeffnen()
        self.win._current_show_path = None          # nie gespeicherte Show
        self.state.cue_stacks.append(CueStack("Neu"))
        ev = self._beenden_mit_speichern(**{
            "QFileDialog.getSaveFileName": lambda *a, **k: ("", "")})
        self.assertFalse(ev.isAccepted(),
                         "abgebrochenes „Speichern unter' darf nicht beenden")

    def test_save_show_wirft(self):
        from src.core.engine.cue_stack import CueStack
        self._oeffnen()
        self.state.cue_stacks.append(CueStack("Neu"))

        def _kaputt(*a, **k):
            raise OSError("Datentraeger voll")
        ev = self._beenden_mit_speichern(**{"save_show": _kaputt})
        self.assertFalse(ev.isAccepted(), "gescheitertes Speichern darf nicht beenden")
        self.assertTrue(self.win._has_unsaved_changes(),
                        "nach gescheitertem Speichern gilt der Stand nicht als gesichert")


def contextlib_exit(patches: dict):
    """Patches fuer ``_beenden_mit_speichern``: ``QFileDialog.x`` am
    main_window-Modul, ``save_show`` in der Show-Schicht."""
    import contextlib
    from src.ui import main_window as mw
    stack = contextlib.ExitStack()
    for name, wert in patches.items():
        if name == "save_show":
            stack.enter_context(mock.patch.object(SF, "save_show", wert))
        else:
            klasse, attr = name.split(".")
            stack.enter_context(mock.patch.object(getattr(mw, klasse), attr, wert))
    return stack


class UndoStapelTest(_MitHauptfenster):
    """Befund 5b: Undo ueber den echten Undo-Stapel. (Cuelisten anlegen ist
    nicht undo-faehig — ``AppState.new_cue_stack`` pusht nichts —, darum das
    Patchen eines Geraets, die erste undo-faehige Show-Arbeit.)"""

    @classmethod
    def _show_bauen(cls, state):
        state.add_fixture(_dimmer(1, 1), undoable=False)

    def test_undo_macht_wieder_unveraendert(self):
        from src.core.undo import get_undo_stack
        self._oeffnen()
        self.assertFalse(get_undo_stack().can_undo(), "Laden leert den Verlauf")
        self.state.add_fixture(_dimmer(2, 5), undoable=True)
        self.assertTrue(self.win._has_unsaved_changes(), "neues Geraet nicht erkannt")
        self.win._do_undo()
        self.assertEqual([1], [f.fid for f in self.state.get_patched_fixtures()])
        self.assertFalse(self.win._has_unsaved_changes(),
                         "nach Undo ist die Show wieder wie gespeichert")
        self.win._do_redo()
        self.assertTrue(self.win._has_unsaved_changes())
        self.win._do_undo()


if __name__ == "__main__":
    unittest.main()
