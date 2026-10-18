"""UI-96: Im Kiosk-Modus gibt es keine Bibliothek-Seitenleiste und keinen
anderen Bearbeitungsweg in der Virtual Console.

Befund (Sitzung D, Windows, 18.10.2026): ``--kiosk`` verspricht laut Hilfe
„nur Virtual Console, keine Bearbeitung", rechts stand aber die Seitenleiste
„Bibliothek" mit Ziehen auf Tasten, Rechtsklick „Auf VC-Taste legen" und den
Knoepfen Speichern, Ordner +, Anwenden, Chase +, Loeschen. Entscheidung des
Projektinhabers: im Kiosk die Seitenleiste ganz ausblenden.

Diese Datei bewacht ausserdem die weiteren klaren Bearbeitungswege, die im
Kiosk offen waren: Bearbeiten-Modus, MIDI Lernen, Canvas importieren,
Undo/Redo (Knoepfe und Strg+Z/Strg+Y) und die Zuweisungs-Modi des Canvas.
Ausserhalb des Kiosk bleibt alles wie vorher (Gegenprobe je Punkt).

Es wird nichts gesendet; ein MainWindow wird nur im letzten Block gebaut.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton              # noqa: E402

from src.ui.views import virtual_console_view as vcv                 # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _knoepfe(view, text_anfang):
    return [b for b in view._toolbar_widget.findChildren(QPushButton)
            if b.text().startswith(text_anfang)]


def _sichtbar(view, w) -> bool:
    return w.isVisibleTo(view)


class _Ansicht(unittest.TestCase):
    KIOSK = True

    def setUp(self):
        self.app = _app()
        self.view = vcv.VirtualConsoleView(kiosk=self.KIOSK)
        self.view._active_fx_timer.stop()
        self.view.resize(1400, 800)
        self.view.show()
        self.view._active_fx_timer.stop()
        self.app.processEvents()

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()


class KioskOhneBibliothekTest(_Ansicht):

    def test_seitenleiste_wird_nicht_gebaut(self):
        self.assertIsNone(self.view._sidebar)
        self.assertEqual(self.view.findChildren(vcv.SnapshotSidebar), [])
        # Auch das Bibliotheks-Panel (Speichern, Ordner +, Anwenden, …) fehlt.
        from src.ui.views.snap_file_panel import SnapFilePanel
        self.assertEqual(self.view.findChildren(SnapFilePanel), [])

    def test_kein_bibliothek_knopf(self):
        self.assertIsNone(self.view._btn_sidebar)
        self.assertEqual(_knoepfe(self.view, "◀ Bibliothek"), [])
        self.assertEqual(_knoepfe(self.view, "▶ Bibliothek"), [])

    def test_umschalten_holt_seitenleiste_nicht_zurueck(self):
        # Direkter Aufruf (wie ein frueher gespeicherter Zustand / ein Kuerzel)
        self.view._toggle_sidebar(True)
        self.assertIsNone(self.view._sidebar)
        self.assertEqual(self.view.findChildren(vcv.SnapshotSidebar), [])

    def test_kein_hinweistext_auf_vc_taste_legen(self):
        from PySide6.QtWidgets import QLabel
        texte = [lb.text() for lb in self.view.findChildren(QLabel)]
        self.assertFalse(any("Auf VC-Taste legen" in t for t in texte), texte)

    def test_splitter_hat_nur_canvas_und_inspector(self):
        self.assertEqual(self.view._splitter.count(), 2)

    def test_showevent_und_effekt_takt_ohne_seitenleiste(self):
        self.view.hide()
        self.view.show()
        self.view._update_active_fx()
        self.app.processEvents()
        self.assertIsNone(self.view._sidebar)


class KioskOhneBearbeitungTest(_Ansicht):

    def test_bearbeiten_knopf_weg_und_modus_gesperrt(self):
        self.assertFalse(_sichtbar(self.view, self.view._btn_edit))
        self.assertFalse(self.view._btn_edit.isEnabled())
        self.view._btn_edit.setChecked(True)      # wie ein Kuerzel / Klick
        self.assertFalse(self.view._edit_mode)
        self.assertFalse(self.view._btn_edit.isChecked())
        self.assertFalse(self.view._canvas._edit_mode)
        self.view._toggle_edit(True)              # direkter Aufruf
        self.assertFalse(self.view._edit_mode)
        self.assertFalse(self.view._canvas._edit_mode)
        for btn in self.view._toolbar_widget.findChildren(QPushButton):
            if btn.property("edit_only"):
                self.assertFalse(_sichtbar(self.view, btn), btn.text())

    def test_canvas_bleibt_ausserhalb_bearbeiten(self):
        self.assertTrue(self.view._canvas.kiosk)
        self.view._canvas.set_edit_mode(True)
        self.assertFalse(self.view._canvas._edit_mode)

    def test_midi_lernen_gesperrt(self):
        b = self.view._btn_midi_learn
        self.assertFalse(_sichtbar(self.view, b))
        self.assertFalse(b.isEnabled())
        b.setChecked(True)
        self.assertFalse(b.isChecked())
        self.assertFalse(self.view._midi_learn_active)
        self.assertIsNone(getattr(self.view._canvas, "_awaiting_button_click_for", None))

    def test_zuweisungsmodi_des_canvas_gesperrt(self):
        c = self.view._canvas
        c.start_midi_learn()
        c.start_snapshot_assign(1)
        c.start_function_assign(1)
        c.start_snap_assign(1)
        self.assertIsNone(getattr(c, "_awaiting_button_click_for", None))

    def test_canvas_import_gesperrt(self):
        self.assertFalse(_sichtbar(self.view, self.view._btn_load))
        # QMessageBox.warning mitpatchen: fehlt die Sperre, landet _load mit dem
        # erfundenen Pfad im Fehlerzweig — ohne Patch haengt der Test dort am
        # modalen Dialog statt sauber rot zu werden.
        with mock.patch.object(vcv.VCCanvas, "from_dict") as fd, \
                mock.patch("src.ui.virtualconsole.vc_canvas.QFileDialog."
                           "getOpenFileName", return_value=("x.json", "")) as dlg, \
                mock.patch("src.ui.virtualconsole.vc_canvas.QMessageBox."
                           "warning") as warn:
            self.view._load()
            self.view._canvas._load()
        dlg.assert_not_called()
        fd.assert_not_called()
        warn.assert_not_called()

    def test_undo_redo_gesperrt(self):
        c = self.view._canvas
        with mock.patch.object(c, "undo") as u, mock.patch.object(c, "redo") as r:
            self.view._vc_undo()
            self.view._vc_redo()
        u.assert_not_called()
        r.assert_not_called()

    def test_keine_undo_kuerzel(self):
        from PySide6.QtGui import QShortcut
        tasten = {s.key().toString() for s in self.view.findChildren(QShortcut)}
        for k in ("Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z"):
            self.assertNotIn(k, tasten)

    def test_bedienung_bleibt(self):
        # Bank, Touch-Lock, Pickup bleiben — der Kiosk ist eine Bedienoberflaeche.
        for b in (self.view._btn_bank_prev, self.view._btn_bank_next,
                  self.view._btn_touch_lock, self.view._btn_pickup):
            self.assertTrue(_sichtbar(self.view, b), b.text())
            self.assertTrue(b.isEnabled(), b.text())

    def test_layout_aus_show_laedt_weiter(self):
        # Show-Laden (from_dict) ist kein Bearbeiten — die Konsole muss kommen.
        self.view.from_dict({"widgets": [
            {"type": "VCButton", "x": 10, "y": 10, "w": 80, "h": 60}]})
        self.app.processEvents()
        from src.ui.virtualconsole.vc_button import VCButton
        tasten = self.view._canvas.findChildren(VCButton)
        self.assertEqual(len(tasten), 1)
        self.assertFalse(tasten[0]._edit_mode)


class OhneKioskUnveraendertTest(_Ansicht):
    KIOSK = False

    def test_seitenleiste_da_und_umschaltbar(self):
        self.assertIsInstance(self.view._sidebar, vcv.SnapshotSidebar)
        self.assertEqual(self.view._splitter.count(), 3)
        self.assertTrue(_sichtbar(self.view, self.view._sidebar))
        self.view._btn_sidebar.setChecked(False)
        self.assertFalse(_sichtbar(self.view, self.view._sidebar))
        self.view._btn_sidebar.setChecked(True)
        self.assertTrue(_sichtbar(self.view, self.view._sidebar))

    def test_bearbeiten_midi_import_undo_verfuegbar(self):
        self.assertTrue(_sichtbar(self.view, self.view._btn_edit))
        self.assertTrue(_sichtbar(self.view, self.view._btn_midi_learn))
        self.assertTrue(_sichtbar(self.view, self.view._btn_load))
        self.view._btn_edit.setChecked(True)
        self.assertTrue(self.view._edit_mode)
        self.assertTrue(self.view._canvas._edit_mode)
        self.view._btn_edit.setChecked(False)
        c = self.view._canvas
        self.assertFalse(c.kiosk)
        c.start_snap_assign(1)
        self.assertEqual(c._awaiting_button_click_for, "library_snap")
        c.cancel_snap_assign()
        from PySide6.QtGui import QShortcut
        tasten = {s.key().toString() for s in self.view.findChildren(QShortcut)}
        self.assertIn("Ctrl+Z", tasten)
        with mock.patch.object(c, "undo") as u:
            self.view._vc_undo()
        u.assert_called_once()


class CanvasKioskNachtraeglichTest(unittest.TestCase):
    """Jeder der vier Zuweisungs-/Lern-Modi endet beim nachtraeglichen
    Einschalten des Kiosk vollstaendig — nicht nur ``_awaiting_button_click_for``
    (das setzt jede cancel-Methode zurueck), sondern auch das je Modus
    gemerkte Ziel."""

    def _canvas(self):
        _app()
        c = vcv.VCCanvas()
        self.addCleanup(lambda: (c.deleteLater(), _app().processEvents()))
        return c

    def test_set_kiosk_beendet_bearbeiten(self):
        c = self._canvas()
        c.set_edit_mode(True)
        c.set_kiosk(True)
        self.assertFalse(c._edit_mode)

    def test_set_kiosk_beendet_midi_lernen(self):
        c = self._canvas()
        c.start_midi_learn()
        taste = mock.Mock(_midi_armed=True)
        c._midi_learn_btn = taste          # Taste schon bewaffnet
        c.set_kiosk(True)
        self.assertIsNone(c._awaiting_button_click_for)
        self.assertIsNone(c._midi_learn_btn)
        self.assertFalse(taste._midi_armed)

    def test_set_kiosk_beendet_snapshot_zuweisung(self):
        c = self._canvas()
        c.start_snapshot_assign(2)
        c.set_kiosk(True)
        self.assertIsNone(c._awaiting_button_click_for)
        self.assertIsNone(c._assign_snapshot_index)

    def test_set_kiosk_beendet_funktions_zuweisung(self):
        c = self._canvas()
        c.start_function_assign(3)
        c.set_kiosk(True)
        self.assertIsNone(c._awaiting_button_click_for)
        self.assertIsNone(c._assign_function_id)

    def test_set_kiosk_beendet_snap_zuweisung(self):
        c = self._canvas()
        c.start_snap_assign(4)
        c.set_kiosk(True)
        self.assertIsNone(c._awaiting_button_click_for)
        self.assertIsNone(c._assign_snap_id)


class TempoBusControllerKioskTest(unittest.TestCase):
    """Gegenpruefung UI-96: Der Tempo-Bus-Controller oeffnet im Bedienmodus beim
    Klick auf die Effekte-Zeile ein Menue (Effekt entfernen, „Effekte hinzufuegen /
    Parameter…" = Eigenschaften-Dialog). Im Kiosk ist das ein Bearbeitungsweg und
    gesperrt. Quelle, Faktor, SYNC und die Bus-Wahl bleiben Bedienung."""

    KIOSK = True

    def setUp(self):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent
        from src.ui.virtualconsole.vc_tempo_bus_controller import (
            VCTempoBusController)
        self.app = _app()
        self.canvas = vcv.VCCanvas()
        self.canvas.resize(600, 400)
        self.canvas.set_kiosk(self.KIOSK)
        self.tb = VCTempoBusController(parent=self.canvas)
        self.tb.setGeometry(10, 10, 260, 180)
        self.tb.set_edit_mode(False)
        self.function_ids = []

        def klick(pos):
            ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos),
                             QPointF(self.tb.mapToGlobal(pos)),
                             Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier)
            self.tb.mousePressEvent(ev)
        self.klick = klick

    def tearDown(self):
        self.tb.deleteLater()
        self.canvas.deleteLater()
        self.app.processEvents()

    def test_effekte_zeile_oeffnet_kein_menue(self):
        with mock.patch.object(self.tb, "_open_effects_menu") as menue, \
                mock.patch.object(self.tb, "_open_properties") as dlg:
            self.klick(self.tb._effects_rect().center())
        if self.KIOSK:
            menue.assert_not_called()
        else:
            menue.assert_called_once()
        dlg.assert_not_called()

    def test_menue_und_dialog_direkt_gesperrt(self):
        mod = "src.ui.virtualconsole.vc_tempo_bus_controller."
        with mock.patch(mod + "QMenu") as menue, \
                mock.patch(mod + "QDialog") as dlg:
            menue.return_value.exec.return_value = None
            self.tb._open_effects_menu(QPoint(0, 0))
            if self.KIOSK:
                self.tb._open_properties()
        if self.KIOSK:
            menue.assert_not_called()
            dlg.assert_not_called()
        else:
            menue.assert_called_once()

    def test_bus_wahl_bleibt_bedienung(self):
        with mock.patch.object(self.tb, "_open_bus_menu") as bus:
            self.klick(self.tb._bus_rect().center())
        bus.assert_called_once()


class TempoBusControllerOhneKioskTest(TempoBusControllerKioskTest):
    KIOSK = False


class HauptfensterKioskTest(unittest.TestCase):
    """Das Hauptfenster reicht ``kiosk`` an die VC-Ansicht weiter."""

    @classmethod
    def setUpClass(cls):
        _app()
        import src.ui.main_window as MW
        cls.w = MW.MainWindow(kiosk=True, touch=True)
        cls.w._hw_timer.stop()
        cls.w.resize(1280, 800)
        cls.w.show()
        _app().processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.w.hide()
        cls.w.deleteLater()
        _app().processEvents()

    def test_vc_im_kiosk_ohne_bibliothek(self):
        vc = self.w._vc_view
        self.assertTrue(vc.kiosk)
        self.assertIsNone(vc._sidebar)
        self.assertEqual(vc.findChildren(vcv.SnapshotSidebar), [])
        self.assertIs(self.w._stack.currentWidget(), vc)
        self.assertFalse(vc._btn_edit.isVisibleTo(self.w))


if __name__ == "__main__":
    unittest.main()
