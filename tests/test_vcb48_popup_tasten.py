"""VCB-48: Pop-up-Tasten in der Virtual Console.

Wunsch des Projektinhabers: Eine VC-Taste oeffnet ein Feld mit selbst
hineingelegten Tasten; das Feld ueberlagert die uebrigen Elemente (kein eigenes
Fenster, nichts darunter bekommt Klicks), DIESELBE Taste schliesst es wieder.
Es funktioniert im Kiosk (bedienbar, nicht bearbeitbar), und es gibt keine
Verschachtelung.

Vorgaben (A): Kinder des geschlossenen Pop-ups bleiben per MIDI/Hotkey
ausloesbar und behalten ihren Zustand; Fader im Pop-up sind erlaubt; das Feld
steht dort, wo es im Editor liegt; im Bearbeiten-Modus laesst es sich zum
Befuellen oeffnen. offen/zu ist Laufzeit (nach dem Laden geschlossen).

Jeder Block hat eine Gegenprobe. Es wird nichts gesendet; nur VCCanvas, kein
MainWindow.
"""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, QPoint, Qt     # noqa: E402
from PySide6.QtTest import QTest                          # noqa: E402
from PySide6.QtWidgets import QApplication                # noqa: E402

from src.ui.virtualconsole import vc_popup                # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton  # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas      # noqa: E402
from src.ui.virtualconsole.vc_frame import VCFrame        # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                          # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


class _Msg:
    def __init__(self, data1, data2=127, msg_type="note_on", channel=0):
        self.msg_type = msg_type
        self.channel = channel
        self.data1 = data1
        self.data2 = data2


class _Mitschnitt(QObject):
    """Zaehlt Maus-Druecke, die bei der Canvas ankommen (auch weitergereichte)."""
    def __init__(self):
        super().__init__()
        self.druecke = 0

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.MouseButtonPress:
            self.druecke += 1
        return False


class _Basis(unittest.TestCase):
    def setUp(self):
        vc_popup.hinweis_zuruecksetzen()
        self.canvas = VCCanvas()
        self.canvas.resize(1200, 800)
        self.canvas.set_active_bank(0)
        self.canvas.show()
        _app.processEvents()

    def tearDown(self):
        try:
            self.canvas._teardown_midi()
            self.canvas._teardown_keyboard()
        except Exception:
            pass
        self.canvas.close()
        self.canvas.setParent(None)
        self.canvas.deleteLater()
        _app.processEvents()

    # -- Aufbau: unten eine normale Taste, darueber ein Pop-up-Feld mit Inhalt,
    #    daneben die Pop-up-Taste. Gebaut wie im Editor (Bearbeiten-Modus).
    def _aufbau(self, *, fader=True):
        c = self.canvas
        c.set_edit_mode(True)
        self.unten = c._add_widget("VCButton", QPoint(528, 248))  # unter freier Feldflaeche
        self.unten.caption = "Unten"
        self.feld = c._add_widget("VCFrame", QPoint(280, 80))
        self.feld.resize(320, 240)
        self.feld.caption = "Farben"
        self.assertTrue(self.feld.set_popup(True))
        self.kind = self.feld._add_child_widget("VCButton", QPoint(20, 40))
        self.kind.caption = "Rot"
        if fader:
            self.fader = self.feld._add_child_widget("VCSlider", QPoint(160, 40))
        self.taste = c._add_widget("VCButton", QPoint(40, 40))
        self.taste.caption = "Farben…"
        self.taste.action = ButtonAction.POPUP_TOGGLE
        self.taste.popup_target = self.feld.popup_id
        self.feld.set_popup_offen(False)
        c.set_edit_mode(False)
        _app.processEvents()

    def _klick(self, w):
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=w.rect().center())
        _app.processEvents()


class OeffnenSchliessenTest(_Basis):

    def test_dieselbe_taste_oeffnet_und_schliesst(self):
        self._aufbau()
        self.assertFalse(self.feld.isVisible())
        self.assertFalse(self.taste._aktionszustand())
        self._klick(self.taste)
        self.assertTrue(self.feld.isVisible())
        self.assertTrue(self.kind.isVisible())
        self.assertTrue(self.taste._aktionszustand())        # Taste zeigt „offen“
        self._klick(self.taste)
        self.assertFalse(self.feld.isVisible())
        self.assertFalse(self.taste._aktionszustand())

    def test_gegenprobe_andere_taste_schaltet_nicht(self):
        self._aufbau()
        self._klick(self.unten)                               # Toggle ohne Ziel
        self.assertFalse(self.feld.isVisible())

    def test_normaler_rahmen_ist_immer_sichtbar(self):
        """Gegenprobe: ohne Pop-up-Eigenschaft bleibt ein Rahmen wie bisher."""
        c = self.canvas
        f = c._add_widget("VCFrame", QPoint(10, 300))
        self.assertTrue(f.isVisible())
        self.assertFalse(f.is_popup())

    def test_steht_wo_im_editor_platziert(self):
        self._aufbau()
        self._klick(self.taste)
        self.assertEqual((self.feld.x(), self.feld.y()), (280, 80))


class UeberlagerungTest(_Basis):

    def test_offenes_popup_liegt_oben_und_schluckt_klicks(self):
        self._aufbau()
        self._klick(self.taste)
        punkt = self.unten.geometry().center()
        getroffen = self.canvas.childAt(punkt)
        # Was an der Stelle der unteren Taste liegt, gehoert zum Pop-up.
        self.assertIs(getroffen, self.feld)       # freie Flaeche des Pop-ups

        ausgeloest = []
        self.unten._trigger = lambda press: ausgeloest.append(press)
        filt = _Mitschnitt()
        self.canvas.installEventFilter(filt)
        QTest.mouseClick(getroffen, Qt.MouseButton.LeftButton,
                         pos=getroffen.mapFrom(self.canvas, punkt))
        _app.processEvents()
        self.canvas.removeEventFilter(filt)
        self.assertEqual(ausgeloest, [])          # nichts darunter klickt durch
        self.assertEqual(filt.druecke, 0)         # auch nicht die Canvas

    def test_gegenprobe_normaler_rahmen_reicht_klick_an_canvas(self):
        """Ohne Pop-up-Eigenschaft geht ein Klick auf die Rahmenflaeche wie
        bisher an die Canvas weiter — der Mitschnitt sieht ihn also."""
        self._aufbau()
        self._klick(self.taste)
        self.feld.set_popup(False)
        filt = _Mitschnitt()
        self.canvas.installEventFilter(filt)
        QTest.mouseClick(self.feld, Qt.MouseButton.LeftButton, pos=QPoint(300, 220))
        _app.processEvents()
        self.canvas.removeEventFilter(filt)
        self.assertEqual(filt.druecke, 1)

    def test_gegenprobe_geschlossen_trifft_die_untere_taste(self):
        self._aufbau()
        punkt = self.unten.geometry().center()
        self.assertIs(self.canvas.childAt(punkt), self.unten)

    def test_bleibt_oben_wenn_danach_ein_widget_angelegt_wird(self):
        self._aufbau()
        self._klick(self.taste)
        self.canvas._add_widget("VCButton", QPoint(330, 130))
        punkt = QPoint(340, 140)
        w = self.canvas.childAt(punkt)
        while w is not None and w is not self.feld:
            w = w.parentWidget()
        self.assertIs(w, self.feld)


class KioskTest(_Basis):

    def test_kiosk_bedienbar_aber_nicht_bearbeitbar(self):
        self._aufbau()
        self.canvas.set_kiosk(True)
        self.canvas.set_edit_mode(True)                     # wird verweigert
        self.assertFalse(self.canvas._edit_mode)
        self.assertFalse(self.feld._edit_mode)
        self._klick(self.taste)
        self.assertTrue(self.feld.isVisible())              # bedienbar
        # Ziehen am Feld verschiebt nichts, kein Auswahlrahmen.
        geo = self.feld.geometry()
        QTest.mousePress(self.feld, Qt.MouseButton.LeftButton, pos=QPoint(150, 120))
        QTest.mouseMove(self.feld, QPoint(220, 190))
        QTest.mouseRelease(self.feld, Qt.MouseButton.LeftButton, pos=QPoint(220, 190))
        _app.processEvents()
        self.assertEqual(self.feld.geometry(), geo)
        self.assertFalse(self.feld._selected)
        self._klick(self.taste)
        self.assertFalse(self.feld.isVisible())

    def test_gegenprobe_ohne_kiosk_im_editor_verschiebbar(self):
        self._aufbau()
        self.feld.set_popup_offen(True)
        self.canvas.set_edit_mode(True)
        geo = self.feld.geometry()
        QTest.mousePress(self.feld, Qt.MouseButton.LeftButton, pos=QPoint(150, 120))
        QTest.mouseMove(self.feld, QPoint(220, 190))
        QTest.mouseRelease(self.feld, Qt.MouseButton.LeftButton, pos=QPoint(220, 190))
        _app.processEvents()
        self.assertNotEqual(self.feld.geometry(), geo)


class VerschachtelungTest(_Basis):

    def test_taste_im_popup_darf_keine_popup_taste_werden(self):
        self._aufbau()
        S = self.kind._build_settings(self.kind, live=False)
        combo = S["action_combo"]
        combo.setCurrentIndex(combo.findData(ButtonAction.POPUP_TOGGLE.value))
        S["apply"]()
        self.assertNotEqual(self.kind.action, ButtonAction.POPUP_TOGGLE)
        self.assertEqual(vc_popup.letzter_hinweis(), vc_popup.HINWEIS_TASTE_IM_POPUP)

    def test_gegenprobe_taste_auf_der_konsole_darf(self):
        self._aufbau()
        S = self.unten._build_settings(self.unten, live=False)
        S["action_combo"].setCurrentIndex(
            S["action_combo"].findData(ButtonAction.POPUP_TOGGLE.value))
        S["popup_combo"].setCurrentIndex(S["popup_combo"].findData(self.feld.popup_id))
        S["apply"]()
        self.assertEqual(self.unten.action, ButtonAction.POPUP_TOGGLE)
        self.assertEqual(self.unten.popup_target, self.feld.popup_id)
        self.assertEqual(vc_popup.letzter_hinweis(), "")

    def test_rahmen_mit_popup_taste_wird_kein_popup(self):
        c = self.canvas
        c.set_edit_mode(True)
        f = c._add_widget("VCFrame", QPoint(10, 300))
        b = f._add_child_widget("VCButton", QPoint(10, 30))
        b.action = ButtonAction.POPUP_TOGGLE
        self.assertFalse(f.set_popup(True))
        self.assertFalse(f.is_popup())
        self.assertEqual(vc_popup.letzter_hinweis(), vc_popup.HINWEIS_FELD_ENTHAELT_POPUP)
        # Gegenprobe: Taste umgestellt -> jetzt erlaubt.
        b.action = ButtonAction.FLASH
        self.assertTrue(f.set_popup(True))

    def test_verschachtelter_rahmen_wird_kein_popup(self):
        c = self.canvas
        aussen = c._add_widget("VCFrame", QPoint(10, 300))
        innen = aussen._add_child_widget("VCFrame", QPoint(10, 30))
        self.assertFalse(innen.set_popup(True))
        self.assertTrue(aussen.set_popup(False) and not aussen.is_popup())

    def test_popup_taste_laesst_sich_nicht_hineinziehen(self):
        self._aufbau()
        self.feld.set_popup_offen(True)
        self.canvas.set_edit_mode(True)
        geo = self.taste.geometry()
        self.taste._orig_rect = geo
        self.taste.move(self.feld.x() + 40, self.feld.y() + 60)
        self.canvas.handle_drag_drop(self.taste)
        self.assertIs(self.taste.parent(), self.canvas)
        self.assertEqual(self.taste.geometry(), geo)          # zurueck an den Platz
        self.assertEqual(vc_popup.letzter_hinweis(), vc_popup.HINWEIS_TASTE_IM_POPUP)

    def test_gegenprobe_normale_taste_laesst_sich_hineinziehen(self):
        self._aufbau()
        self.feld.set_popup_offen(True)
        self.canvas.set_edit_mode(True)
        neu = self.canvas._add_widget("VCButton", QPoint(700, 500))
        neu._orig_rect = neu.geometry()
        neu.move(self.feld.x() + 40, self.feld.y() + 140)
        self.canvas.handle_drag_drop(neu)
        self.assertIs(neu.parent(), self.feld)

    def test_geschlossenes_popup_ist_kein_ablageziel(self):
        self._aufbau()
        self.canvas.set_edit_mode(True)
        neu = self.canvas._add_widget("VCButton", QPoint(700, 500))
        neu.move(self.feld.x() + 40, self.feld.y() + 140)
        self.canvas.handle_drag_drop(neu)
        self.assertIs(neu.parent(), self.canvas)


class SpeichernLadenTest(_Basis):

    def test_rundlauf_und_beim_laden_geschlossen(self):
        self._aufbau()
        self._klick(self.taste)                       # offen speichern
        d = json.loads(json.dumps(self.canvas.to_dict()))
        feld_d = [w for w in d["widgets"] if w["type"] == "VCFrame"][0]
        self.assertTrue(feld_d["popup"])
        self.assertEqual(feld_d["popup_id"], self.feld.popup_id)
        self.assertNotIn("offen", json.dumps(feld_d))
        typen = sorted(k["type"] for k in feld_d["children"])
        self.assertEqual(typen, ["VCButton", "VCSlider"])     # Fader im Pop-up

        self.canvas.from_dict(d)
        _app.processEvents()
        felder = vc_popup.alle_popups(self.canvas)
        self.assertEqual(len(felder), 1)
        feld = felder[0]
        self.assertFalse(feld.isVisible())                    # geschlossen geladen
        tasten = [w for w in self.canvas.findChildren(VCButton)
                  if w.action == ButtonAction.POPUP_TOGGLE]
        self.assertEqual(len(tasten), 1)
        self._klick(tasten[0])
        self.assertTrue(feld.isVisible())
        self.assertEqual(self.canvas.to_dict(), d)            # nichts verloren

    def test_alte_show_ohne_popup_unveraendert(self):
        alt = {"widgets": [
            {"type": "VCFrame", "caption": "Box", "bank": -1, "x": 10, "y": 10,
             "w": 300, "h": 200, "bg": "#161b22", "fg": "#8b949e",
             "page_count": 1, "show_header": True, "solo": False, "children": [
                 {"type": "VCButton", "caption": "A", "bank": -1, "x": 10, "y": 30,
                  "w": 72, "h": 72, "action": "Flash", "vc_page": 0}]},
            {"type": "VCButton", "caption": "B", "bank": -1, "x": 400, "y": 10,
             "w": 72, "h": 72, "action": "Toggle"}]}
        self.canvas.from_dict(json.loads(json.dumps(alt)))
        neu = self.canvas.to_dict()
        txt = json.dumps(neu)
        self.assertNotIn("popup", txt)
        frame = [w for w in self.canvas.findChildren(VCFrame)][0]
        self.assertTrue(frame.isVisible())
        self.assertFalse(frame.is_popup())
        # Gegenprobe: dasselbe Layout mit popup=True wird ein (geschlossenes) Pop-up.
        alt["widgets"][0]["popup"] = True
        alt["widgets"][0]["popup_id"] = "abc123"
        self.canvas.from_dict(alt)
        frame = [w for w in self.canvas.findChildren(VCFrame)][0]
        self.assertTrue(frame.is_popup())
        self.assertFalse(frame.isVisible())

    def test_verschachteltes_popup_aus_datei_wird_normaler_rahmen(self):
        d = {"widgets": [{"type": "VCFrame", "x": 0, "y": 0, "w": 300, "h": 200,
                          "children": [{"type": "VCFrame", "popup": True,
                                        "popup_id": "x1", "x": 5, "y": 30,
                                        "w": 100, "h": 100}]}]}
        self.canvas.from_dict(d)
        frames = self.canvas.findChildren(VCFrame)
        self.assertEqual(len(frames), 2)
        self.assertFalse(any(f.is_popup() for f in frames))

    def test_umbenennen_bricht_verknuepfung_nicht(self):
        self._aufbau()
        self.feld.caption = "Ganz anders"
        d = self.canvas.to_dict()
        self.canvas.from_dict(d)
        taste = [w for w in self.canvas.findChildren(VCButton)
                 if w.action == ButtonAction.POPUP_TOGGLE][0]
        self._klick(taste)
        feld = vc_popup.alle_popups(self.canvas)[0]
        self.assertEqual(feld.caption, "Ganz anders")
        self.assertTrue(feld.isVisible())

    def test_gegenprobe_falsche_kennung_oeffnet_nichts(self):
        self._aufbau()
        self.taste.popup_target = "gibtsnicht"
        self._klick(self.taste)
        self.assertFalse(self.feld.isVisible())
        self.assertEqual(vc_popup.letzter_hinweis(), vc_popup.HINWEIS_ZIEL_FEHLT)

    def test_andere_tasten_schreiben_kein_popup_feld(self):
        b = self.canvas._add_widget("VCButton", QPoint(10, 10))
        self.assertNotIn("popup_target", b.to_dict())
        b.action = ButtonAction.POPUP_TOGGLE
        self.assertIn("popup_target", b.to_dict())


class MidiHotkeyTest(_Basis):

    def test_kind_im_geschlossenen_popup_per_midi_und_hotkey(self):
        self._aufbau(fader=False)
        self.kind.midi_data1 = 40
        self.kind.key_binding = "F7"
        druecke = []
        self.kind._trigger_primary = lambda press: druecke.append(press)
        self.assertFalse(self.kind.isVisible())
        self.canvas._handle_midi(_Msg(40, 127))
        self.canvas._handle_midi(_Msg(40, 0))
        self.assertEqual(druecke, [True, False])
        self.assertTrue(self.canvas._on_hotkey("F7", True))
        self.assertEqual(druecke, [True, False, True])
        # Zustand bleibt beim Oeffnen/Schliessen erhalten.
        self.kind._snap_active = True
        self.feld.set_popup_offen(True)
        self.feld.set_popup_offen(False)
        self.assertTrue(self.kind._snap_active)

    def test_gegenprobe_falsche_note_loest_nicht_aus(self):
        self._aufbau(fader=False)
        self.kind.midi_data1 = 40
        druecke = []
        self.kind._trigger_primary = lambda press: druecke.append(press)
        self.canvas._handle_midi(_Msg(41, 127))
        self.assertEqual(druecke, [])

    def test_popup_taste_per_midi(self):
        self._aufbau(fader=False)
        self.taste.midi_data1 = 50
        self.canvas._handle_midi(_Msg(50, 127))
        self.canvas._handle_midi(_Msg(50, 0))
        self.assertTrue(self.feld.isVisible())
        self.canvas._handle_midi(_Msg(50, 127))
        self.canvas._handle_midi(_Msg(50, 0))
        self.assertFalse(self.feld.isVisible())

    def test_apc_feedback_zeigt_offen(self):
        from src.core.midi.apc_mk2_feedback import ApcMk2Feedback
        self._aufbau(fader=False)
        fb = ApcMk2Feedback.__new__(ApcMk2Feedback)
        self.assertFalse(fb._is_active(self.taste))
        self.feld.set_popup_offen(True)
        self.assertTrue(fb._is_active(self.taste))


class UndoTest(_Basis):

    def test_popup_eigenschaft_ist_undobar(self):
        c = self.canvas
        c.set_edit_mode(True)
        f = c._add_widget("VCFrame", QPoint(10, 300))
        f._open_properties = lambda: f.set_popup(True)
        f._edit_properties()
        self.assertTrue(f.is_popup())
        c.undo()
        frames = c.findChildren(VCFrame)
        self.assertEqual(len(frames), 1)
        self.assertFalse(frames[0].is_popup())
        self.assertTrue(frames[0].isVisible())
        c.redo()
        self.assertTrue(c.findChildren(VCFrame)[0].is_popup())

    def test_gegenprobe_unveraenderter_dialog_kein_undo_punkt(self):
        c = self.canvas
        c.set_edit_mode(True)
        f = c._add_widget("VCFrame", QPoint(10, 300))
        n = len(c._undo_stack)
        f._open_properties = lambda: None
        f._edit_properties()
        self.assertEqual(len(c._undo_stack), n)

    def test_undo_im_editor_laesst_offenes_popup_offen(self):
        self._aufbau()
        self.canvas.set_edit_mode(True)
        self.feld.set_popup_offen(True)
        self.canvas._push_undo()
        self.feld._add_child_widget("VCButton", QPoint(20, 150))
        self.canvas.undo()
        feld = vc_popup.alle_popups(self.canvas)[0]
        self.assertTrue(feld.popup_offen())
        self.assertTrue(feld.isVisible())


class EditorOeffnenTest(_Basis):

    def test_im_bearbeiten_modus_per_menue_oeffnen(self):
        self._aufbau()
        self.canvas.set_edit_mode(True)
        self.assertFalse(self.feld.isVisible())
        # Klick auf die Taste im Bearbeiten-Modus waehlt nur aus ...
        self._klick(self.taste)
        self.assertFalse(self.feld.isVisible())
        # ... geoeffnet wird ueber das Menue der Taste / der Konsole.
        from PySide6.QtWidgets import QMenu
        m = QMenu()
        self.taste._extend_context_menu(m)
        texte = [a.text() for a in m.actions()]
        self.assertIn("Pop-up-Feld öffnen", texte)
        [a for a in m.actions() if a.text() == "Pop-up-Feld öffnen"][0].trigger()
        self.assertTrue(self.feld.isVisible())

    def test_gegenprobe_normale_taste_hat_keinen_menuepunkt(self):
        self._aufbau()
        from PySide6.QtWidgets import QMenu
        m = QMenu()
        self.unten._extend_context_menu(m)
        self.assertFalse(any("Pop-up" in a.text() for a in m.actions()))


if __name__ == "__main__":
    unittest.main()
