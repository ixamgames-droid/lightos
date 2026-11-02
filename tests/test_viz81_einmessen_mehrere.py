"""VIZ-81: Einmessen mit mehreren gewaehlten Koepfen.

* „Position uebernehmen" gilt fuer ALLE gewaehlten Koepfe mit Loesung — als EIN
  Undo-Schritt; Koepfe ohne Loesung bleiben unveraendert und werden genannt.
* Schieben bewegt bei Mehrfachauswahl weiterhin alle gleich, sagt das aber
  sichtbar in der Statuszeile.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage.einmessen import EinmessSitzung, Loesung, Messpunkt
from test_viz55_einmessen import FEIN, _fx, _State  # noqa: E402


def _loesung(pos, rot=(0.0, 5.0, 0.0)):
    return Loesung(pos=pos, rot=rot, modus="voll", punkte=4, rest_grad=0.01,
                   gegenprobe_cm=1.0, verschiebung_m=0.3, drehung_grad=5.0)


def _punkte(w, st, fid, n=4):
    """n gueltige, verschiedene Messpunkte fuer ``fid`` (Versatz = aktueller)."""
    f = st.fixtures[fid]
    v = (float(f.aim_offset_pan), float(f.aim_offset_tilt))
    s = w._bridge.einmessen
    s.punkte[fid] = [Messpunkt((float(i), 0.0, 1.0), 0, 0) for i in range(n)]
    s._versatz[fid] = [v] * n


class MehrereKoepfeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def _fenster(self, fixtures):
        import src.ui.visualizer.visualizer_window as VW
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        class _W(VW.VisualizerWindow):
            def __init__(self):
                VW.QMainWindow.__init__(self)

        st = _State(fixtures)
        for f in fixtures:
            st.visualizer_positions[f.fid] = (0.0, 4.0, 0.0)
            st.visualizer_rotations[f.fid] = (0.0, 0.0, 0.0)
        w = _W()
        self.addCleanup(w.deleteLater)
        w._state = st
        w._bridge = SimpleNamespace(einmessen=EinmessSitzung(), _is_moving_head=lambda x: True,
                                    _mover_bar_heads=lambda x: 0, refresh_fixture=MagicMock(),
                                    push_apply_fixture_transform=MagicMock())
        w._patch_list = QListWidget()
        w._patch_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)  # wie die App
        for f in fixtures:
            it = QListWidgetItem(f.label)
            it.setData(Qt.ItemDataRole.UserRole, f.fid)
            w._patch_list.addItem(it)
        box = VW.VisualizerWindow._build_einmessen_box(w)
        self.addCleanup(box.deleteLater)
        for name in ("_spin_x", "_spin_y", "_spin_z", "_spin_rot_x", "_spin_rot_y", "_spin_rot_z"):
            sp = VW.LocaleTolerantDoubleSpinBox()
            sp.setRange(-360, 360)
            setattr(w, name, sp)
        orig = VW.get_channels_for_patched
        VW.get_channels_for_patched = lambda x: FEIN
        self.addCleanup(setattr, VW, "get_channels_for_patched", orig)
        for i in range(w._patch_list.count()):
            w._patch_list.item(i).setSelected(True)
        return w, st

    def test_uebernehmen_fuer_alle_mit_loesung_ein_undo_schritt(self):
        from src.core.undo import get_undo_stack
        w, st = self._fenster([_fx(1, aim_offset_pan=1.0), _fx(2, aim_offset_tilt=-0.5),
                               _fx(3, aim_offset_pan=0.75)])
        st.visualizer_docks = {2: "traverse-1"}
        w._einmess_loesung[1] = _loesung((0.3, 4.1, -0.2))
        w._einmess_loesung[2] = _loesung((-0.4, 3.9, 0.1))
        _punkte(w, st, 1)
        _punkte(w, st, 2)
        w._einmess_status()
        self.assertTrue(w._btn_einmess_uebernehmen.isEnabled())
        self.assertIn("2 von 3", w._btn_einmess_uebernehmen.text())

        stapel = get_undo_stack()
        stapel.clear()
        self.addCleanup(stapel.clear)
        w._einmess_uebernehmen()
        self.assertEqual(st.visualizer_positions[1], (0.3, 4.1, -0.2))
        self.assertEqual(st.visualizer_positions[2], (-0.4, 3.9, 0.1))
        self.assertEqual(st.visualizer_positions[3], (0.0, 4.0, 0.0))     # ohne Loesung
        self.assertEqual((st.fixtures[1].aim_offset_pan, st.fixtures[2].aim_offset_tilt),
                         (0.0, 0.0))
        self.assertEqual(st.fixtures[3].aim_offset_pan, 0.75)              # unberuehrt
        self.assertNotIn(2, st.visualizer_docks)
        text = w._lbl_einmess.text()
        self.assertIn("Position übernommen für 2 Köpfe", text)
        self.assertIn("Ohne Lösung, unverändert: MH 3", text)
        self.assertNotIn(1, w._einmess_loesung)
        self.assertNotIn(2, w._einmess_loesung)

        self.assertTrue(stapel.undo())                                     # EIN Strg+Z
        self.assertFalse(stapel.can_undo())
        self.assertEqual(st.visualizer_positions[1], (0.0, 4.0, 0.0))
        self.assertEqual(st.visualizer_positions[2], (0.0, 4.0, 0.0))
        self.assertEqual(st.fixtures[1].aim_offset_pan, 1.0)
        self.assertEqual(st.fixtures[2].aim_offset_tilt, -0.5)
        self.assertEqual(st.visualizer_docks.get(2), "traverse-1")
        self.assertTrue(stapel.redo())
        self.assertEqual(st.visualizer_positions[2], (-0.4, 3.9, 0.1))
        self.assertEqual(st.fixtures[1].aim_offset_pan, 0.0)

    def test_ohne_jede_loesung_bleibt_gesperrt(self):
        w, st = self._fenster([_fx(1), _fx(2)])
        w._einmess_status()
        self.assertFalse(w._btn_einmess_uebernehmen.isEnabled())
        self.assertEqual(w._btn_einmess_uebernehmen.text(), "Position übernehmen")

    def test_veraltete_loesung_ohne_punkte_wird_nicht_uebernommen(self):
        """Show-Wechsel / Geraet mit gleicher fid neu angelegt / Versatz extern
        geaendert: die Messpunkte fallen weg (``anzahl`` 0), die gemerkte Loesung
        darf den Knopf dann nicht mehr freigeben — sonst schoebe „Position
        uebernehmen (2 von 2 Koepfen)" einen Kopf mit einer fremden Loesung weg."""
        w, st = self._fenster([_fx(1), _fx(2)])
        w._einmess_loesung[1] = _loesung((0.3, 4.1, -0.2))
        _punkte(w, st, 1)
        w._einmess_loesung[2] = _loesung((-0.4, 3.9, 0.1))       # keine Punkte (mehr)
        w._einmess_status()
        self.assertTrue(w._btn_einmess_uebernehmen.isEnabled())
        self.assertNotIn("2 von 2", w._btn_einmess_uebernehmen.text())
        self.assertNotIn(2, w._einmess_loesung)
        from src.core.undo import get_undo_stack
        stapel = get_undo_stack()
        stapel.clear()
        self.addCleanup(stapel.clear)
        w._einmess_uebernehmen()
        self.assertEqual(st.visualizer_positions[1], (0.3, 4.1, -0.2))
        self.assertEqual(st.visualizer_positions[2], (0.0, 4.0, 0.0))
        self.assertIn("Ohne Lösung, unverändert: MH 2", w._lbl_einmess.text())

        # Nur noch der Kopf mit veralteter Loesung gewaehlt -> gesperrt.
        w2, st2 = self._fenster([_fx(1)])
        w2._einmess_loesung[1] = _loesung((0.3, 4.1, -0.2))
        w2._einmess_status()
        self.assertFalse(w2._btn_einmess_uebernehmen.isEnabled())

    def test_schieben_mit_mehrfachauswahl_sagt_dass_alle_gleich_gehen(self):
        w, st = self._fenster([_fx(1), _fx(2)])
        for fid in (1, 2):
            w._bridge.einmessen.ziel_gesetzt(fid, (1.0, 0.0, 1.0))
            st.prog.update({(fid, "pan"): 100, (fid, "pan_fine"): 0,
                            (fid, "tilt"): 90, (fid, "tilt_fine"): 0})
        w._einmess_schieben("pan", +1)
        # Verhalten bleibt: beide um denselben Betrag
        self.assertEqual(st.prog[(1, "pan_fine")], st.prog[(2, "pan_fine")])
        self.assertNotEqual(st.prog[(1, "pan_fine")], 0)
        self.assertIn("alle 2 gewählten Köpfe", w._lbl_einmess.text())

    def test_ein_kopf_kein_mehrfach_hinweis(self):
        w, st = self._fenster([_fx(1)])
        w._bridge.einmessen.ziel_gesetzt(1, (1.0, 0.0, 1.0))
        st.prog.update({(1, "pan"): 100, (1, "pan_fine"): 0, (1, "tilt"): 90, (1, "tilt_fine"): 0})
        w._einmess_schieben("pan", +1)
        w._einmess_status()
        self.assertNotIn("gewählten Köpfe", w._lbl_einmess.text())


if __name__ == "__main__":
    unittest.main()
