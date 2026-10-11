"""LAS-32 (S1): Bedienung (Dialog) und Meldung je Laser.

Der Dialog legt Zonen an, verschiebt, vergroessert, benennt und loescht sie und
nimmt je Laser die vier Randwinkel + Zuschlag auf. Die Meldung sagt je Laser
„kann Zone X erreichen" / „erreicht keine Zone" / „Randwinkel fehlen — nicht
prüfbar" und ist gelb beschriftet, dass nichts abgeschaltet wird.
"""
import json
import os
import pathlib
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.laser import sperrzonen as S
from src.core.laser.sperrzonen import LaserFeld, Sperrzone, SperrzonenDaten
from src.ui.visualizer import sperrzonen_ui as UI

_app = QApplication.instance() or QApplication([])


class _Fx:
    protocol = ""

    def __init__(self, fid, ftype, label):
        self.fid, self.fixture_type, self.label = fid, ftype, label
        self.fixture_name = label


class _State:
    def __init__(self):
        self.sperrzonen = SperrzonenDaten()
        self._patch = [_Fx(2, "laser", "EL-400"), _Fx(5, "par", "PAR")]
        self.visualizer_positions = {2: (0.0, 4.0, 0.0)}
        self.visualizer_rotations = {2: (0.0, 0.0, 0.0)}
        self.ereignisse = []

    def get_patched_fixtures(self):
        return list(self._patch)

    def _emit(self, event, data=None):
        self.ereignisse.append(event)


def _zone_vorn():
    return Sperrzone(id="z1", name="Publikum", x=0, y=3.0, z=10, breite=4, hoehe=2, tiefe=2)


class HinweisTest(unittest.TestCase):
    def test_ohne_laser_keine_meldung(self):
        st = _State()
        st._patch = [_Fx(5, "par", "PAR")]
        st.sperrzonen.zonen.append(_zone_vorn())
        self.assertEqual(UI.hinweis_html(st), "")
        w = UI.SperrzonenHinweis(st)
        self.assertTrue(w.isHidden())
        w.deleteLater()

    def test_laser_ohne_zonen_meldet_das_gelb(self):
        st = _State()
        text = UI.hinweis_html(st)
        self.assertIn("Laser gepatcht, keine Sperrzonen angelegt", text)
        self.assertIn(UI.GELB, text)
        self.assertIn("schaltet den Laser NICHT ab", text)

    def test_drei_meldungen(self):
        st = _State()
        st.sperrzonen.zonen.append(_zone_vorn())
        self.assertIn("Laser 2 „EL-400“: Randwinkel fehlen — nicht prüfbar",
                      UI.hinweis_html(st))
        st.sperrzonen.setze_feld(2, LaserFeld(links=10, rechts=10, oben=10, unten=10))
        self.assertIn("Laser 2 „EL-400“: kann Zone „Publikum“ erreichen",
                      UI.hinweis_html(st))
        st.visualizer_rotations[2] = (0.0, 180.0, 0.0)     # Laser umgedreht
        self.assertIn("Laser 2 „EL-400“: erreicht keine Zone", UI.hinweis_html(st))
        self.assertNotIn("PAR", UI.hinweis_html(st))

    def test_gelbe_beschriftung_steht_immer_dabei(self):
        st = _State()
        st.sperrzonen.zonen.append(_zone_vorn())
        st.sperrzonen.setze_feld(2, LaserFeld(links=10, rechts=10, oben=10, unten=10))
        for rot in ((0.0, 0.0, 0.0), (0.0, 180.0, 0.0)):
            st.visualizer_rotations[2] = rot
            text = UI.hinweis_html(st)
            self.assertIn(f'<b style="color:{UI.GELB}">', text)
            self.assertIn("Nur Anzeige — schaltet den Laser NICHT ab "
                          "(am Gerät noch nicht abgenommen)", text)

    def test_widget_folgt_dem_stand(self):
        st = _State()
        w = UI.SperrzonenHinweis(st)
        self.assertFalse(w.isHidden())
        self.assertIn("keine Sperrzonen", w.text())
        st.sperrzonen.zonen.append(_zone_vorn())
        w.aktualisieren()
        self.assertIn("nicht prüfbar", w.text())
        w.deleteLater()

    def test_namen_werden_nicht_als_html_gedeutet(self):
        st = _State()
        st.sperrzonen.zonen.append(Sperrzone(id="z", name="<b>Bar</b>", x=0, y=3.0, z=10,
                                             breite=4, hoehe=2, tiefe=2))
        st.sperrzonen.setze_feld(2, LaserFeld(links=10, rechts=10, oben=10, unten=10))
        self.assertIn("&lt;b&gt;Bar&lt;/b&gt;", UI.hinweis_html(st))

    def test_kein_text_der_oberflaeche_verspricht_schutz(self):
        quelle = pathlib.Path(UI.__file__).read_text(encoding="utf-8")
        for wort in ("geschützt", "abgesichert", "überwacht", "Schutzzone"):
            self.assertNotIn(wort, quelle, wort)
        self.assertIn("Kein Laserschutz", UI.GRENZEN_TEXT)


class DialogTest(unittest.TestCase):
    def setUp(self):
        self.st = _State()
        self.dlg = UI.SperrzonenDialog(self.st)

    def tearDown(self):
        self.dlg.close()
        self.dlg.deleteLater()
        _app.processEvents()

    def test_grenzen_stehen_oben_im_dialog(self):
        from PySide6.QtWidgets import QLabel
        lab = self.dlg.findChild(QLabel, "sperrzonenGrenzen")
        self.assertIn("NICHT ab", lab.text())
        self.assertIn("Laserschutzbeauftragten", lab.text())
        self.assertIn("nur Anzeige", self.dlg.windowTitle())

    def test_anlegen_benennen_verschieben_groesse_loeschen(self):
        self.assertEqual(self.st.sperrzonen.zonen, [])
        self.assertFalse(self.dlg._form_host.isEnabled())
        self.dlg._btn_neu.click()
        self.assertEqual(len(self.st.sperrzonen.zonen), 1)
        zone = self.st.sperrzonen.zonen[0]
        self.assertEqual(zone.name, "Publikum")
        self.assertIn("sperrzonen_changed", self.st.ereignisse)
        self.assertTrue(self.dlg._form_host.isEnabled())

        self.st.ereignisse.clear()
        self.dlg._name.setText("Bar")
        self.dlg._name.textEdited.emit("Bar")
        self.assertEqual(zone.name, "Bar")
        self.assertEqual(self.dlg._liste.currentItem().text(), "Bar")

        self.dlg._zspins["x"].setValue(3.5)
        self.dlg._zspins["y"].setValue(1.0)
        self.dlg._zspins["z"].setValue(-2.0)
        self.assertEqual((zone.x, zone.y, zone.z), (3.5, 1.0, -2.0))
        self.dlg._zspins["breite"].setValue(12.0)
        self.dlg._zspins["hoehe"].setValue(2.5)
        self.dlg._zspins["tiefe"].setValue(7.0)
        self.assertEqual((zone.breite, zone.hoehe, zone.tiefe), (12.0, 2.5, 7.0))
        self.dlg._dreh.setValue(45.0)
        self.assertEqual(zone.dreh_y, 45.0)
        self.assertGreaterEqual(self.st.ereignisse.count("sperrzonen_changed"), 8)

        self.dlg._btn_neu.click()
        self.assertEqual([z.name for z in self.st.sperrzonen.zonen], ["Bar", "Publikum"])
        self.assertEqual(self.dlg._liste.currentRow(), 1)
        self.dlg._liste.setCurrentRow(0)
        self.dlg._btn_loeschen.click()
        self.assertEqual([z.name for z in self.st.sperrzonen.zonen], ["Publikum"])
        self.dlg._btn_loeschen.click()
        self.assertEqual(self.st.sperrzonen.zonen, [])
        self.assertFalse(self.dlg._form_host.isEnabled())

    def test_groesse_kann_nicht_null_werden(self):
        self.dlg._btn_neu.click()
        self.dlg._zspins["breite"].setValue(0.0)
        self.assertGreaterEqual(self.st.sperrzonen.zonen[0].breite, S.ZONE_MIN_M)

    def test_randwinkel_starten_als_nicht_angegeben(self):
        self.assertEqual(self.dlg._tabelle.rowCount(), 1)       # nur der Laser
        spins = self.dlg._feld_spins[2]
        for rand in S.RAENDER:
            self.assertEqual(spins[rand].text(), "nicht angegeben")
        self.assertEqual(spins["zuschlag"].value(), 5.0)
        self.assertEqual(spins["zuschlag"].minimum(), 2.0)

    def test_randwinkel_eintragen(self):
        spins = self.dlg._feld_spins[2]
        spins["links"].setValue(12.0)
        feld = self.st.sperrzonen.feld(2)
        self.assertEqual(feld.links, 12.0)
        self.assertFalse(feld.vollstaendig)
        for rand, wert in (("rechts", 20.0), ("oben", 5.0), ("unten", 30.0)):
            spins[rand].setValue(wert)
        feld = self.st.sperrzonen.feld(2)
        self.assertTrue(feld.vollstaendig)
        self.assertEqual((feld.links, feld.rechts, feld.oben, feld.unten),
                         (12.0, 20.0, 5.0, 30.0))
        spins["zuschlag"].setValue(0.0)                         # Minimum greift
        self.assertEqual(self.st.sperrzonen.feld(2).zuschlag, 2.0)
        spins["oben"].setValue(-1.0)                            # wieder „nicht angegeben"
        self.assertIsNone(self.st.sperrzonen.feld(2).oben)

    def test_meldung_im_dialog_wechselt_mit_der_eingabe(self):
        self.st.sperrzonen.zonen.append(_zone_vorn())
        self.dlg.neu_laden()
        self.assertIn("nicht prüfbar", self.dlg._hinweis.text())
        for rand in S.RAENDER:
            self.dlg._feld_spins[2][rand].setValue(10.0)
        self.assertIn("kann Zone „Publikum“ erreichen", self.dlg._hinweis.text())
        self.dlg._zspins["x"].setValue(60.0)                    # Zone weit weg
        self.assertIn("erreicht keine Zone", self.dlg._hinweis.text())

    def test_abschnitt_aus_neuerem_stand_ist_nicht_bearbeitbar(self):
        self.st.sperrzonen = SperrzonenDaten(fremd={"version": 99, "zonen": [{"x": 1}]})
        self.dlg.neu_laden()
        self.assertFalse(self.dlg._btn_neu.isEnabled())
        self.dlg._zone_neu()
        self.assertEqual(self.st.sperrzonen.to_dict(), {"version": 99, "zonen": [{"x": 1}]})
        self.assertFalse(self.dlg._feld_spins[2]["links"].isEnabled())


class BridgeTest(unittest.TestCase):
    """Der Weg in die Szene: ein JSON-Text im Poll-Zustand ``sperrzonen``."""

    def _bridge(self, st):
        from src.ui.visualizer.visualizer_window import VisualizerBridge

        class _B:
            pass
        b = _B()
        b._state = st
        b._poll_state = {}
        return VisualizerBridge, b

    def test_abgleich_stellt_zonen_und_vollstaendige_felder_in_den_poll(self):
        st = _State()
        st.sperrzonen.zonen.append(_zone_vorn())
        VB, b = self._bridge(st)
        VB._sync_sperrzonen(b)
        d = json.loads(b._poll_state["sperrzonen"])
        self.assertEqual([z["name"] for z in d["zonen"]], ["Publikum"])
        self.assertEqual(d["felder"], [])            # Randwinkel fehlen -> kein Feld
        rev = b._poll_rev["sperrzonen"]
        VB._sync_sperrzonen(b)
        self.assertEqual(b._poll_rev["sperrzonen"], rev, "gleicher Stand, neue Revision")
        st.sperrzonen.setze_feld(2, LaserFeld(links=1, rechts=2, oben=3, unten=4))
        VB._sync_sperrzonen(b)
        d = json.loads(b._poll_state["sperrzonen"])
        self.assertEqual(d["felder"], [{"fid": 2, "links": 1.0, "rechts": 2.0,
                                        "oben": 3.0, "unten": 4.0, "zuschlag": 5.0}])
        self.assertGreater(b._poll_rev["sperrzonen"], rev)

    def test_bridge_reagiert_auf_aenderung_show_und_patch(self):
        st = _State()
        VB, b = self._bridge(st)
        for ereignis in ("sperrzonen_changed",):
            b._poll_state.clear()
            VB._on_state(b, ereignis, None)
            self.assertIn("sperrzonen", b._poll_state, ereignis)

    def test_anzeige_fehler_bricht_das_aufraeumen_nicht_ab(self):
        """Ein Bridge-Objekt ohne Poll-Zustand (oder ein kaputter Bestand) darf
        ``_on_state`` nicht werfen lassen — danach laeuft das Entfernen
        geloeschter Geraete."""
        from types import SimpleNamespace
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        VisualizerBridge._sync_sperrzonen(SimpleNamespace(_state=_State()))
        kaputt = _State()
        kaputt.sperrzonen = "kein Bestand"
        VB, b = self._bridge(kaputt)
        VB._sync_sperrzonen(b)
        self.assertNotIn("sperrzonen", b._poll_state)



class EinbauTest(unittest.TestCase):
    """Die Meldung sitzt in der Laser-Ansicht, der Dialog am 3D-Fenster."""

    def test_laser_ansicht_zeigt_die_meldung(self):
        from unittest import mock
        import src.ui.views.laser_view as lv
        st = _State()
        st.get_selected_fids = lambda: []
        st.sperrzonen.zonen.append(_zone_vorn())
        with mock.patch.object(lv, "get_state", lambda: st):
            view = lv.LaserView(follow_selection=False)
        try:
            w = view.findChild(UI.SperrzonenHinweis, "sperrzonenHinweis")
            self.assertIsNotNone(w, "Laser-Ansicht ohne Sperrzonen-Meldung")
            self.assertFalse(w.isHidden())
            self.assertIn("Randwinkel fehlen — nicht prüfbar", w.text())
            self.assertIn("NICHT ab", w.text())
        finally:
            view.deleteLater()
            _app.processEvents()

    def test_3d_fenster_oeffnet_den_dialog(self):
        import src.ui.visualizer.visualizer_window as VW

        class _Fenster(VW.VisualizerWindow):
            def __init__(self, state):
                VW.QMainWindow.__init__(self)
                self._state = state

        st = _State()
        win = _Fenster(st)
        try:
            VW.VisualizerWindow._on_sperrzonen_dialog(win)
            dlg = win._sperrzonen_dlg
            self.assertIsInstance(dlg, UI.SperrzonenDialog)
            self.assertFalse(dlg.isModal())
            st.sperrzonen.zonen.append(_zone_vorn())
            VW.VisualizerWindow._on_sperrzonen_dialog(win)      # zweiter Aufruf: neu geladen
            self.assertIs(win._sperrzonen_dlg, dlg)
            self.assertEqual(dlg._liste.count(), 1)
            dlg.close()
        finally:
            win.deleteLater()
            _app.processEvents()

    def test_werkzeugleiste_hat_den_eintrag(self):
        quelle = (pathlib.Path(__file__).resolve().parent.parent / "src" / "ui"
                  / "visualizer" / "visualizer_window.py").read_text(encoding="utf-8")
        self.assertIn('QAction("Sperrzonen…", self)', quelle)
        self.assertIn("act_sperrzonen.triggered.connect(self._on_sperrzonen_dialog)", quelle)


if __name__ == "__main__":
    unittest.main()
