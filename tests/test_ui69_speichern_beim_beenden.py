"""UI-69: Beenden fragt bei einer aus Datei geladenen Show nach dem Speichern.

Live-Funktionstest (01.10.2026): Show geoeffnet, Cueliste angelegt, Datei ->
Beenden -> sofort zu, keine Rueckfrage. ``MainWindow._has_unsaved_changes()``
lieferte bei gesetztem ``_current_show_path`` fest ``False`` — Aenderungen
landeten nur im 5-min-Auto-Save.

Jetzt vergleicht ``show_file.show_hat_aenderungen`` den Show-Inhalt mit dem beim
letzten Laden/Speichern gemerkten Stand. Geprueft wird hier:

* direkt nach dem Laden: KEINE Aenderung (auch nicht nach nachlaufenden
  Aufbauarbeiten der Views),
* reine Live-Bedienung (Programmer, Fader, BPM, Funktions-Intensitaet,
  Executor-Fader): KEINE Aenderung,
* echte Arbeit an der Show (Cueliste, Funktion, VC-Layout): Aenderung — und
  Beenden fragt dann; Abbrechen haelt das Fenster offen,
* nach dem Speichern / „Neue Show": wieder unveraendert.
"""
import os
import tempfile
import unittest
import uuid
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


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class LiveWerteSindKeineAenderungTest(unittest.TestCase):
    """Die Abgrenzung Live-Bedienung / Show-Arbeit auf Datenebene."""

    def _show(self, **ueber):
        d = {
            "programmer": {"1": {"dimmer": 255}},
            "functions": {"functions": [
                {"id": 1, "name": "A", "intensity": 1.0, "speed": 1.0}]},
            "tempo_buses": [{"bus_id": "b", "bpm": 120.0}],
            "tempo_grandmaster": {"armed": False, "bpm": 0.0, "auto_sync": True},
            "executors": {"current_page": 0, "page_names": [], "pages": [[
                {"slot": 1, "label": "Exec 1", "fader_value": 0.4,
                 "fader_function": "volume", "btn1": "go", "btn2": "back",
                 "btn3": "flash", "stack_index": -1}]]},
            "live_view": {"positions": {}, "meta": {"zoom": 1.0, "grid_size": 20}},
            "virtual_console": {"widgets": [
                {"type": "VCFrame", "caption": "F", "children": [
                    {"type": "VCSlider", "caption": "S", "value": 10},
                    {"type": "VCSpeedDial", "bpm": 120, "active_factor": 1.0}]},
                {"type": "VCButton", "caption": "B", "value": 3}]},
        }
        d.update(ueber)
        return d

    def test_live_felder_fallen_raus_show_felder_bleiben(self):
        roh = self._show()
        ohne = SF._ohne_live_werte(roh)
        self.assertNotIn("programmer", ohne)
        self.assertNotIn("intensity", ohne["functions"]["functions"][0])
        self.assertEqual("A", ohne["functions"]["functions"][0]["name"])
        self.assertNotIn("bpm", ohne["tempo_buses"][0])
        self.assertEqual({"auto_sync": True}, ohne["tempo_grandmaster"])
        # Executor im Werkszustand, nur der Fader verstellt -> wie nicht da
        self.assertEqual([[]], ohne["executors"]["pages"])
        self.assertEqual({"grid_size": 20}, ohne["live_view"]["meta"])
        frame = ohne["virtual_console"]["widgets"][0]
        self.assertNotIn("value", frame["children"][0])
        self.assertNotIn("bpm", frame["children"][1])
        # Nur Fader/Speed-Dial verlieren ihre Bedienwerte, nicht jedes "value"
        self.assertEqual(3, ohne["virtual_console"]["widgets"][1]["value"])
        # Das Original bleibt unangetastet (es wird gleich gespeichert)
        self.assertEqual(10, roh["virtual_console"]["widgets"][0]["children"][0]["value"])
        self.assertIn("programmer", roh)

    def test_belegter_executor_bleibt_im_vergleich(self):
        roh = self._show()
        roh["executors"]["pages"][0][0]["stack_index"] = 0
        ohne = SF._ohne_live_werte(roh)
        self.assertEqual(1, len(ohne["executors"]["pages"][0]))
        self.assertNotIn("fader_value", ohne["executors"]["pages"][0][0])


class BeendenFragtNachDemSpeichernTest(unittest.TestCase):
    """Kompletter Ablauf im echten MainWindow (Bau ist teuer -> ein Test)."""

    def test_geladene_show_aenderungen_erkennen_und_fragen(self):
        app = _app()
        from src.core.app_state import get_state
        from src.core.engine.cue_stack import CueStack
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        from src.ui import main_window as mw

        state = get_state()
        SF.reset_show()
        fn = state.function_manager.new_scene("UI69-Szene")
        state.cue_stacks.append(CueStack("Vorhanden"))
        # Bewusst ein KNAPPES VC-Layout in der Datei: die Flaeche ergaenzt beim
        # Aufbau Standardfelder — das darf nicht als Aenderung gelten.
        state._vc_layout = {"widgets": [
            {"type": "VCButton", "caption": "Knopf", "x": 10, "y": 10, "w": 80, "h": 40},
            {"type": "VCSlider", "caption": "Fader", "x": 100, "y": 10, "w": 60, "h": 200}]}
        pfad = os.path.join(tempfile.gettempdir(),
                            f"ui69_{uuid.uuid4().hex}.lshow")
        SF.save_show(pfad)

        win = mw.MainWindow()
        try:
            win._open_show_path(pfad)
            self.assertEqual(pfad, win._current_show_path)
            self.assertFalse(win._has_unsaved_changes(),
                             "Laden allein darf nicht als Aenderung gelten")
            app.processEvents()
            app.processEvents()
            self.assertFalse(win._has_unsaved_changes(),
                             "nachlaufender View-Aufbau nach dem Laden ist keine Aenderung")

            # ── Live-Bedienung: KEINE Show-Aenderung ──
            fn = state.function_manager.all()[0]
            fn.intensity = 0.3                      # VC-Fader auf Funktion
            fn.speed = 2.0                          # Speed-Dial
            get_tempo_bus_manager().set_grandmaster_bpm(128.0)
            with state._prog_lock:
                state.programmer[1] = {"dimmer": 200}
            canvas = win._vc_view._canvas
            from src.ui.virtualconsole.vc_widget import VCWidget
            self.assertEqual(2, len(canvas.findChildren(VCWidget)),
                             "VC-Layout der Datei wurde nicht aufgebaut")
            self.assertFalse(win._has_unsaved_changes(),
                             "Programmer/Fader/BPM duerfen nicht nach Speichern fragen")

            # ── Echte Arbeit an der Show: Cueliste anlegen (der Live-Fall) ──
            state.cue_stacks.append(CueStack("Neu angelegt"))
            self.assertTrue(win._has_unsaved_changes(),
                            "neue Cueliste in geladener Show nicht erkannt (UI-69)")

            # Beenden fragt — „Abbrechen" laesst das Fenster offen.
            fragen = []

            def _frage(*a, **k):
                fragen.append(a)
                return QMessageBox.StandardButton.Cancel

            ev = QCloseEvent()
            with mock.patch.object(mw, "_exit_prompt_suppressed", lambda: False), \
                 mock.patch.object(mw.QMessageBox, "question", _frage):
                win.closeEvent(ev)
            self.assertEqual(1, len(fragen), "Beenden hat nicht nachgefragt")
            self.assertFalse(ev.isAccepted(), "Abbrechen muss das Beenden stoppen")

            # Speichern -> wieder unveraendert
            self.assertTrue(win._do_save(pfad))
            self.assertFalse(win._has_unsaved_changes(),
                             "nach dem Speichern noch als geaendert gemeldet")

            # Rueckgaengig gemachte Aenderung = unveraendert
            state.cue_stacks.append(CueStack("Kurz"))
            self.assertTrue(win._has_unsaved_changes())
            state.cue_stacks.pop()
            self.assertFalse(win._has_unsaved_changes())

            # Funktion umbenennen (Show-Arbeit, kein Live-Feld)
            fn.name = "Umbenannt"
            self.assertTrue(win._has_unsaved_changes())
            self.assertTrue(win._do_save(pfad))

            # VC-Layout: Bedienelement hinzufuegen ist eine Aenderung,
            # den Fader danach zu bewegen nicht.
            canvas._add_widget("VCSlider", QPoint(40, 40))
            self.assertTrue(win._has_unsaved_changes(),
                            "neues VC-Bedienelement nicht erkannt")
            self.assertTrue(win._do_save(pfad))
            from src.ui.virtualconsole.vc_slider import VCSlider
            for slider in canvas.findChildren(VCSlider):
                slider._value = 77
            self.assertFalse(win._has_unsaved_changes(),
                             "Fader bewegen ist Live-Bedienung, keine Show-Aenderung")

            # Auto-Save ersetzt das Speichern nicht
            state.cue_stacks.append(CueStack("Nur im Auto-Save"))
            with mock.patch.object(win, "_autosave_path",
                                   lambda: pfad + ".auto.lshow"):
                win._autosave_dirty = True
                win._do_autosave()
            self.assertTrue(win._has_unsaved_changes(),
                            "Auto-Save darf die Speichern-Frage nicht erledigen")
            try:
                os.remove(pfad + ".auto.lshow")
            except OSError:
                pass

            # „Neue Show" mit Aenderungen fragt; „Verwerfen" leert, danach sauber.
            fragen.clear()

            def _verwerfen(*a, **k):
                fragen.append(a)
                return QMessageBox.StandardButton.Discard

            with mock.patch.object(mw, "_exit_prompt_suppressed", lambda: False), \
                 mock.patch.object(mw.QMessageBox, "question", _verwerfen):
                win._new_show()
            self.assertEqual(1, len(fragen), "„Neue Show' fragt nur einmal")
            self.assertIn("speichern", fragen[0][2])
            self.assertIsNone(win._current_show_path)
            self.assertEqual([], list(state.cue_stacks))
            self.assertFalse(win._has_unsaved_changes())
        finally:
            try:
                os.remove(pfad)
            except OSError:
                pass
            try:
                win.deleteLater()
            except Exception:
                pass
            app.processEvents()
            SF.reset_show()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
