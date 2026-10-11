"""WEB-10: Seitenleiste „Handy-Konsole" im VC-Editor.

In der Leiste baut man die Handy-Konsole von Hand: Elemente der grossen Konsole
als Verknuepfung ablegen (Ziehen oder Rechtsklick), im Raster 4 x 10 verschieben,
in der Groesse aendern, herunternehmen; Seiten anlegen, umbenennen, loeschen,
umordnen. Jede Aenderung ist EIN Rueckgaengig-Schritt der Konsole.

Geprueft wird ueber die Oberflaeche (Kontextmenue, Mausereignisse, Knoepfe) und
ueber die ``handy_*``-Methoden der Konsole, auf denen die Leiste steht.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Vor dem Import: Einstellungen in ein Wegwerf-Verzeichnis.
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web10_")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from src.core import handy_seiten as hs
from src.ui.virtualconsole import vc_handy_leiste as leisten_modul
from src.ui.virtualconsole.vc_button import ButtonAction
from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY, VCCanvas
from src.ui.virtualconsole.vc_fernbedienung import VCFernbedienung, beschreibe
from src.web import remote_settings, vc_remote

_app = QApplication.instance() or QApplication([])

JA = leisten_modul.QMessageBox.StandardButton.Yes
NEIN = leisten_modul.QMessageBox.StandardButton.No


def _eintrag(canvas, kennung, seite=0):
    return hs.eintrag(canvas.handy_seiten(), seite, kennung)


def _feld(e):
    return (e["spalte"], e["zeile"], e["breite"], e["hoehe"])


# ── Modell ───────────────────────────────────────────────────────────────────

class ModellTest(unittest.TestCase):

    def test_groessen_je_art(self):
        g = hs.groesse_begrenzen
        # Taste 1 x 1 … 4 x 2
        self.assertEqual(g("taste", 1, 1), (1, 1))
        self.assertEqual(g("taste", 9, 9), (4, 2))
        self.assertEqual(g("taste", 0, 0), (1, 1))
        # Fader senkrecht 1 x 2 … 1 x 5
        self.assertEqual(g("fader", 1, 1), (1, 2))
        self.assertEqual(g("fader", 1, 9), (1, 5))
        self.assertEqual(g("fader", 3, 4), (1, 4))      # breit UND hoch: bleibt senkrecht
        # … oder waagerecht 2 x 1 … 4 x 1 (die Handy-Ansicht legt ihn quer)
        self.assertEqual(g("fader", 2, 1), (2, 1))
        self.assertEqual(g("fader", 7, 1), (4, 1))
        # Cueliste immer volle Breite, 2 … 4 hoch
        self.assertEqual(g("cueliste", 1, 1), (4, 2))
        self.assertEqual(g("cueliste", 2, 9), (4, 4))
        for typ, groesse in (("taste", hs.GROESSE_TASTE), ("taste", hs.GROESSE_BLACKOUT),
                             ("taste", hs.GROESSE_TASTE_BREIT), ("fader", hs.GROESSE_FADER),
                             ("cueliste", hs.GROESSE_CUELISTE)):
            self.assertTrue(hs.groesse_erlaubt(typ, *groesse), (typ, groesse))

    def test_die_handy_ansicht_legt_breite_fader_quer(self):
        # Darauf stuetzt sich die waagerechte Fader-Groesse.
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "src", "web", "templates", "konsole.html")
        with open(pfad, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("e.breite > e.hoehe", html)
        self.assertIn(".fader.quer", html)

    def test_seiten_ordnen_und_verschieben(self):
        a = hs.leer()
        for name in ("A", "B", "C"):
            a = hs.seite_hinzufuegen(a, name)
        a = hs.eintrag_setzen(a, 0, "wabc1", 0, 0)
        neu = hs.seiten_ordnen(a, [2, 0, 1])
        self.assertEqual([s["name"] for s in neu["seiten"]], ["C", "A", "B"])
        self.assertEqual(hs.seiten_mit(neu, "wabc1"), [1])        # Inhalt wandert mit
        self.assertEqual([s["name"] for s in a["seiten"]], ["A", "B", "C"])   # Eingabe bleibt
        for unsinn in ([0, 1], [0, 0, 1], [0, 1, 3], "012", None, [True, 1, 2]):
            self.assertIsNone(hs.seiten_ordnen(a, unsinn), unsinn)
        self.assertEqual([s["name"] for s in hs.seite_verschieben(a, 0, 2)["seiten"]],
                         ["B", "C", "A"])
        self.assertIsNone(hs.seite_verschieben(a, 0, 3))

    def test_naechster_platz(self):
        a = hs.seite_hinzufuegen(hs.leer())
        nr_s_z = hs.naechster_platz(a, "wneu1", 1, 1)[1:]
        self.assertEqual(nr_s_z, (0, 0, 0))
        # Seite voll -> eine neue Seite entsteht
        a = hs.eintrag_setzen(a, 0, "wvoll", 0, 0, 4, 2)
        for z in range(2, 10, 2):
            a = hs.eintrag_setzen(a, 0, f"wvoll{z}", 0, z, 4, 2)
        self.assertEqual(hs.freie_zellen(a, 0), 0)
        neu, nr, s, z = hs.naechster_platz(a, "wneu1", 1, 1)
        self.assertEqual((len(neu["seiten"]), nr, s, z), (2, 1, 0, 0))
        self.assertEqual(len(a["seiten"]), 1)
        # Bei zwoelf vollen Seiten ist Schluss
        voll = {"version": 1, "seiten": [
            {"name": f"S{i}", "eintraege": [
                {"widget": f"wx{i}{z}", "spalte": 0, "zeile": z, "breite": 4, "hoehe": 2}
                for z in range(0, 10, 2)]} for i in range(hs.MAX_SEITEN)]}
        self.assertIsNone(hs.naechster_platz(voll, "wneu1", 1, 1))


# ── Konsole + Seitenleiste ───────────────────────────────────────────────────

class _MitAnsicht(unittest.TestCase):
    """Die ganze VC-Ansicht in einem Fenster fester Groesse (1500 x 760 — was
    bei 1500 x 850 unter Menue und Reitern bleibt)."""

    def setUp(self):
        remote_settings.set_vc_remote_enabled(False)
        from src.ui.views.virtual_console_view import VirtualConsoleView
        self.rahmen = QWidget()
        self.rahmen.setFixedSize(1500, 760)
        self.view = VirtualConsoleView(self.rahmen)
        self.view.setGeometry(0, 0, 1500, 760)
        self.canvas = self.view._canvas
        self.leiste = self.view._handy_leiste
        self.raster = self.leiste.raster
        self.view._btn_sidebar.setChecked(False)
        self.view._btn_edit.setChecked(True)
        self.view._btn_handy.setChecked(True)
        self.rahmen.show()
        _app.processEvents()

    def tearDown(self):
        vc_remote.setze_sender(None)
        remote_settings.set_vc_remote_enabled(False)
        self.rahmen.close()
        self.rahmen.deleteLater()
        _app.processEvents()

    def _taste(self, x=20, y=20, text="T", aktion=ButtonAction.FUNCTION_TOGGLE):
        t = self.canvas._add_widget("VCButton", QPoint(x, y))
        t.caption = text
        t.action = aktion
        t.show()
        return t

    def _fader(self, x=200, y=20):
        f = self.canvas._add_widget("VCSlider", QPoint(x, y))
        f.show()
        return f

    def _schritte(self):
        return len(self.canvas._undo_stack)

    def _global(self, spalte, zeile):
        return self.raster.mapToGlobal(self.raster.zelle_mitte(spalte, zeile))

    def _ziehe_im_raster(self, von: QPoint, nach: QPoint):
        QTest.mousePress(self.raster, Qt.MouseButton.LeftButton, pos=von)
        QTest.mouseMove(self.raster, nach)
        QTest.mouseRelease(self.raster, Qt.MouseButton.LeftButton, pos=nach)

    def _ziehe_in_die_leiste(self, widget, spalte, zeile, loslassen=True):
        """Ein VC-Widget mit der Maus auf eine Zelle der Seitenleiste ziehen."""
        start = QPoint(widget.width() // 2, widget.height() // 2)
        ziel = widget.mapFromGlobal(self._global(spalte, zeile))
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(widget, start + QPoint(30, 0))       # erst ein Stueck verschieben
        QTest.mouseMove(widget, ziel)
        if loslassen:
            QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=ziel)


class WerkzeugleisteTest(_MitAnsicht):

    def test_knopf_blendet_die_leiste_ein_und_aus(self):
        knopf = self.view._btn_handy
        self.assertIn("📱", knopf.text())
        self.assertTrue(knopf.isCheckable())
        self.assertFalse(knopf.property("edit_only"))        # auch im Betrieb (Vorschau)
        self.assertTrue(self.leiste.isVisible())
        knopf.setChecked(False)
        self.assertFalse(self.leiste.isVisible())
        knopf.setChecked(True)
        self.assertTrue(self.leiste.isVisible())

    def test_ablegen_per_rechtsklick_blendet_die_leiste_ein(self):
        self.view._btn_handy.setChecked(False)
        t = self._taste()
        menu = t._baue_kontextmenue()
        self.addCleanup(menu.deleteLater)
        [a for a in menu.actions() if a.objectName() == "handy_ablegen"][0].trigger()
        self.assertTrue(self.view._btn_handy.isChecked())
        self.assertTrue(self.leiste.isVisible())
        self.assertIsNotNone(self.raster._eintrag(t.widget_id))

    def test_kein_doppel_zum_vorlaeufigen_knopf_aus_web09(self):
        self.assertFalse(hasattr(self.view, "_btn_handy_fuellen"))
        from PySide6.QtWidgets import QPushButton
        texte = [b.text() for b in self.view._toolbar_widget.findChildren(QPushButton)]
        self.assertEqual([t for t in texte if "füllen" in t], [])
        self.assertEqual(len([t for t in texte if "Handy" in t]), 1)

    def test_passt_neben_die_konsole(self):
        self.assertGreaterEqual(self.leiste.width(), 300)
        self.assertLessEqual(self.leiste.width(), 340)
        # nichts abgeschnitten: das Raster hat seine Mindesthoehe bekommen …
        self.assertGreaterEqual(self.raster.height(), self.raster.minimumHeight())
        # … und die Konsole daneben bleibt der groesste Teil.
        self.assertGreater(self.view._main_scroll.width(), 600)
        # jede Zelle ist mit dem Finger treffbar
        zw, zh = self.raster._zelle()
        self.assertGreaterEqual(zw, 36)
        self.assertGreaterEqual(zh, 36)
        from PySide6.QtWidgets import QPushButton
        for knopf in self.leiste.findChildren(QPushButton):
            self.assertGreaterEqual(knopf.height(), 36, knopf.text())
        self.assertGreaterEqual(self.leiste._reiter.tabSizeHint(0).height(), 36)

    def test_nur_im_bearbeiten_modus_bedienbar(self):
        t = self._taste()
        self.canvas.handy_ablegen(t)
        self.view._btn_edit.setChecked(False)
        vorher = self.canvas.handy_seiten()
        for knopf in (self.leiste._btn_fuellen, self.leiste._btn_leeren,
                      self.leiste._btn_seite_neu, self.leiste._btn_seite_weg):
            self.assertFalse(knopf.isEnabled(), knopf.text())
        self.assertFalse(self.leiste._reiter.isMovable())
        self._ziehe_im_raster(self.raster.zelle_mitte(0, 0), self.raster.zelle_mitte(2, 4))
        self.raster.waehle(t.widget_id)
        QTest.keyClick(self.raster, Qt.Key.Key_Delete)
        self.assertIsNone(self.raster.baue_kontextmenue(self.raster.zelle_mitte(0, 0)))
        self.assertFalse(self.leiste.seite_loeschen(0))
        self.assertIsNone(self.leiste.seite_hinzufuegen())
        self.assertFalse(self.leiste.seiten_ordnen([0]))
        self.assertFalse(self.leiste.zieh_vorschau(t, self._global(1, 1)))
        self.assertFalse(self.leiste.zieh_ablegen(t, self._global(1, 1)))
        self.assertEqual(self.canvas.handy_seiten(), vorher)
        self.assertIn("Vorschau", self.leiste._lbl_hinweis.text())
        # Verbindung bleibt auch im Betrieb ein Griff
        self.assertTrue(self.leiste._schalter.isEnabled())
        self.assertTrue(self.leiste._btn_verbinden.isEnabled())


class AblegenTest(_MitAnsicht):

    def _handy_aktion(self, widget):
        menu = widget._baue_kontextmenue()
        self.addCleanup(menu.deleteLater)
        treffer = [a for a in menu.actions() if a.objectName() == "handy_ablegen"]
        self.assertEqual(len(treffer), 1)
        return treffer[0], menu

    def test_kontextmenue_legt_auf_den_naechsten_freien_platz(self):
        a, b = self._taste(text="A"), self._taste(x=140, text="B")
        akt, _ = self._handy_aktion(a)
        self.assertTrue(akt.isEnabled())
        self.assertIn("Auf Handy-Konsole legen", akt.text())
        vorher = self._schritte()
        akt.trigger()
        self.assertEqual(self._schritte(), vorher + 1)          # EIN Schritt (samt neuer Seite)
        self.assertEqual(len(self.canvas.handy_seiten()["seiten"]), 1)
        self.assertEqual(_feld(_eintrag(self.canvas, a.widget_id)), (0, 0, 1, 1))
        self._handy_aktion(b)[0].trigger()
        self.assertEqual(_feld(_eintrag(self.canvas, b.widget_id)), (1, 0, 1, 1))
        # Fader bekommt seine Standardgroesse und einen Platz, an den er passt
        f = self._fader()
        self._handy_aktion(f)[0].trigger()
        self.assertEqual(_feld(_eintrag(self.canvas, f.widget_id)), (2, 0, 1, 3))
        # die Seitenleiste zeigt es sofort
        self.assertEqual(self.leiste._reiter.count(), 1)
        self.assertIn("3 Verknüpfungen", self.leiste._lbl_hinweis.text())

    def test_volle_seite_dann_naechste_seite(self):
        fuell = [self._taste(x=20 + 10 * i, text=f"F{i}") for i in range(5)]
        a = hs.seite_hinzufuegen(hs.leer())
        for i, t in enumerate(fuell):
            a = hs.eintrag_setzen(a, 0, t.widget_id, 0, 2 * i, 4, 2)
        self.canvas.setze_handy_seiten(a)
        neu = self._taste(x=300, text="Neu")
        ok, wo = self.canvas.handy_ablegen(neu)
        self.assertTrue(ok)
        self.assertEqual(wo, "Seite 2")
        self.assertEqual(hs.seiten_mit(self.canvas.handy_seiten(), neu.widget_id), [1])
        self.assertEqual(self.canvas.handy_seite_nr(), 1)        # die Leiste folgt
        self.assertEqual(self.leiste._reiter.currentIndex(), 1)

    def test_nicht_fernbedienbar_ist_ausgegraut_mit_grund(self):
        xy = self.canvas._add_widget("VCXYPad", QPoint(300, 200))
        laser = self._taste(x=500, text="Muster", aktion=ButtonAction.LASER_PATTERN)
        vorher = self._schritte()
        for widget, wort in ((xy, "XY-Pad"), (laser, "Laser-Muster")):
            akt, menu = self._handy_aktion(widget)
            self.assertFalse(akt.isEnabled())
            self.assertIn("nicht möglich", akt.text())
            self.assertIn(wort, akt.toolTip())
            self.assertIn("nicht fernbedienbar", akt.toolTip())
            grund = [a for a in menu.actions() if a.objectName() == "handy_ablegen_grund"]
            self.assertEqual(len(grund), 1)                     # der Grund steht IM Menue
            self.assertIn(wort, grund[0].text())
            self.assertFalse(grund[0].isEnabled())
            ok, text = self.canvas.handy_ablegen(widget)
            self.assertFalse(ok)
            self.assertIn("nicht fernbedienbar", text)
            ok, _ = self.canvas.handy_ablegen(widget, 0, 0, 0)
            self.assertFalse(ok)
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())
        self.assertEqual(self._schritte(), vorher)               # kein Rueckgaengig-Schritt

    def test_ablegbar_ist_genau_was_die_fernausloesung_kennt(self):
        # Kein eigener Massstab: die Leiste laesst ablegen, was ``beschreibe``
        # bedienen kann — und nichts sonst (Laser-Sperren aus WEB-08 bleiben).
        for typ in WIDGET_REGISTRY:
            w = self.canvas._add_widget(typ, QPoint(10, 10))
            ok, grund = self.canvas.handy_ablegbar(w)
            self.assertEqual(ok, beschreibe(w) is not None, typ)
            self.assertEqual(bool(grund), not ok, typ)
        muster = self._taste(aktion=ButtonAction.LASER_PATTERN)
        self.assertEqual(self.canvas.handy_ablegbar(muster)[0], False)
        scharf = self._taste(aktion=ButtonAction.LASER_ARM)
        notaus = self._taste(aktion=ButtonAction.LASER_ESTOP)
        self.assertTrue(self.canvas.handy_ablegbar(scharf)[0])
        self.assertTrue(self.canvas.handy_ablegbar(notaus)[0])
        # Auf der Seite zu liegen hebt die Sperre nicht auf: scharf nur am Pult.
        self.canvas.handy_ablegen(scharf)
        fern = VCFernbedienung(self.canvas)
        with mock.patch.object(type(scharf), "_aktionszustand", return_value=False):
            antwort = fern.aktion(scharf.widget_id, "umschalten", nur_handy_seiten=True)
        self.assertEqual(antwort, {"ok": False, "fehler": "nur_am_pult"})

    def test_je_seite_einmal_auf_mehreren_seiten_erlaubt(self):
        t = self._taste()
        self.assertTrue(self.canvas.handy_ablegen(t)[0])
        akt, _ = self._handy_aktion(t)
        self.assertFalse(akt.isEnabled())                       # liegt auf dieser Seite schon
        self.assertIn("Liegt schon auf „Seite 1“", akt.toolTip())
        ok, text = self.canvas.handy_ablegen(t)
        self.assertFalse(ok)
        self.assertIn("Liegt schon", text)
        self.assertEqual(hs.anzahl_eintraege(self.canvas.handy_seiten()), 1)
        # zweite Seite waehlen -> dort darf es noch einmal liegen
        self.leiste.seite_hinzufuegen()
        self.assertEqual(self.canvas.handy_seite_nr(), 1)
        akt, _ = self._handy_aktion(t)
        self.assertTrue(akt.isEnabled())
        akt.trigger()
        self.assertEqual(hs.seiten_mit(self.canvas.handy_seiten(), t.widget_id), [0, 1])
        # und so uebersteht es Speichern/Laden (das Format verwirft nur ein
        # zweites Vorkommen auf DERSELBEN Seite)
        self.assertEqual(hs.normalisiere(self.canvas.handy_seiten()),
                         self.canvas.handy_seiten())

    def test_ziehen_in_die_leiste_legt_ab_und_laesst_das_original_stehen(self):
        t = self._taste(x=40, y=40, text="Zieh")
        self.leiste.seite_hinzufuegen()
        lage = t.geometry()
        vorher = self._schritte()
        self._ziehe_in_die_leiste(t, 2, 4, loslassen=False)
        # waehrend des Ziehens: Zielzelle sichtbar, Widget wieder an seinem Platz
        self.assertEqual(self.raster._fremd,
                         {"spalte": 2, "zeile": 4, "breite": 1, "hoehe": 1, "ok": True})
        self.assertEqual(t.geometry(), lage)
        ziel = t.mapFromGlobal(self._global(2, 4))
        QTest.mouseRelease(t, Qt.MouseButton.LeftButton, pos=ziel)
        self.assertEqual(_feld(_eintrag(self.canvas, t.widget_id)), (2, 4, 1, 1))
        self.assertEqual(t.geometry(), lage)                    # verknuepft, nicht verschoben
        self.assertIs(t.parent(), self.canvas)
        self.assertIsNone(self.raster._fremd)
        self.assertEqual(self._schritte(), vorher + 1)          # EIN Schritt, kein Verschiebe-Schritt
        self.assertEqual(self.raster.auswahl(), t.widget_id)

    def test_ziehen_ohne_seite_legt_die_erste_an(self):
        t = self._taste(x=40, y=40)
        vorher = self._schritte()
        self._ziehe_in_die_leiste(t, 1, 2)
        self.assertEqual(len(self.canvas.handy_seiten()["seiten"]), 1)
        self.assertEqual(_feld(_eintrag(self.canvas, t.widget_id)), (1, 2, 1, 1))
        self.assertEqual(self._schritte(), vorher + 1)

    def test_ziehen_auf_belegten_platz_wird_abgelehnt(self):
        a, b = self._taste(x=40, y=40, text="A"), self._taste(x=40, y=140, text="B")
        self.canvas.handy_ablegen(a, 0, 1, 1)
        vorher_seiten, vorher = self.canvas.handy_seiten(), self._schritte()
        lage = b.geometry()
        self._ziehe_in_die_leiste(b, 1, 1, loslassen=False)
        self.assertIs(self.raster._fremd["ok"], False)          # Zielzelle rot
        QTest.mouseRelease(b, Qt.MouseButton.LeftButton,
                           pos=b.mapFromGlobal(self._global(1, 1)))
        self.assertEqual(self.canvas.handy_seiten(), vorher_seiten)
        self.assertEqual(self._schritte(), vorher)
        self.assertEqual(b.geometry(), lage)
        self.assertIn("kein Platz", self.leiste.letzte_meldung())

    def test_ziehen_am_rand_schiebt_grosse_elemente_herein(self):
        f = self._fader(x=40, y=40)
        self.leiste.seite_hinzufuegen()
        self._ziehe_in_die_leiste(f, 3, 9)                      # 1 x 3 passte dort nicht
        self.assertEqual(_feld(_eintrag(self.canvas, f.widget_id)), (3, 7, 1, 3))
        liste = self.canvas._add_widget("VCCueList", QPoint(300, 40))
        liste.show()
        self.assertEqual(self.canvas.handy_zielfeld(liste, 0, 2, 0), (0, 0, 4, 3, True))
        self.assertEqual(self.canvas.handy_zielfeld(liste, 0, 2, 6), (0, 6, 4, 3, False))

    def test_ziehen_eines_nicht_fernbedienbaren_widgets(self):
        xy = self.canvas._add_widget("VCXYPad", QPoint(40, 40))
        xy.show()
        self.leiste.seite_hinzufuegen()
        vorher_seiten, vorher = self.canvas.handy_seiten(), self._schritte()
        lage = xy.geometry()
        self._ziehe_in_die_leiste(xy, 0, 0, loslassen=False)
        self.assertIs(self.raster._fremd["ok"], False)
        QTest.mouseRelease(xy, Qt.MouseButton.LeftButton,
                           pos=xy.mapFromGlobal(self._global(0, 0)))
        self.assertEqual(self.canvas.handy_seiten(), vorher_seiten)
        self.assertEqual(self._schritte(), vorher)
        self.assertEqual(xy.geometry(), lage)
        self.assertIn("nicht fernbedienbar", self.leiste.letzte_meldung())

    def test_verschieben_auf_der_konsole_geht_weiter_wie_bisher(self):
        t = self._taste(x=40, y=40)
        QTest.mousePress(t, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        QTest.mouseMove(t, QPoint(120, 60))
        QTest.mouseRelease(t, Qt.MouseButton.LeftButton, pos=QPoint(120, 60))
        self.assertEqual((t.x(), t.y()), (140, 80))
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())

    def test_ziehen_in_die_ausgeblendete_leiste_tut_nichts(self):
        t = self._taste(x=40, y=40)
        ziel = self._global(1, 1)
        self.view._btn_handy.setChecked(False)
        self.assertFalse(self.canvas.handy_zieh_bewegt(t, ziel))
        self.assertFalse(self.canvas.handy_zieh_losgelassen(t, ziel))
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())


class BearbeitenTest(_MitAnsicht):

    def setUp(self):
        super().setUp()
        self.t = self._taste(text="Eins")
        self.u = self._taste(x=140, text="Zwei")
        self.f = self._fader()
        self.liste = self.canvas._add_widget("VCCueList", QPoint(300, 200))
        self.canvas.handy_ablegen(self.t, 0, 0, 0)
        self.canvas.handy_ablegen(self.u, 0, 1, 0)
        self.canvas.handy_ablegen(self.f, 0, 3, 0)
        self.canvas.handy_ablegen(self.liste, 0, 0, 6)
        _app.processEvents()

    def test_kachel_verschieben(self):
        vorher = self._schritte()
        self._ziehe_im_raster(self.raster.zelle_mitte(0, 0), self.raster.zelle_mitte(2, 4))
        self.assertEqual(_feld(_eintrag(self.canvas, self.t.widget_id)), (2, 4, 1, 1))
        self.assertEqual(self._schritte(), vorher + 1)
        self.assertEqual(self.raster.auswahl(), self.t.widget_id)

    def test_verschieben_auf_belegtes_feld_bleibt_aus(self):
        vorher_seiten, vorher = self.canvas.handy_seiten(), self._schritte()
        QTest.mousePress(self.raster, Qt.MouseButton.LeftButton, pos=self.raster.zelle_mitte(0, 0))
        QTest.mouseMove(self.raster, self.raster.zelle_mitte(1, 0))
        self.assertEqual(self.raster._zieh["ziel"], (1, 0, 1, 1))
        self.assertIs(self.raster._zieh["ok"], False)           # Vorschau zeigt „belegt"
        QTest.mouseRelease(self.raster, Qt.MouseButton.LeftButton, pos=self.raster.zelle_mitte(1, 0))
        self.assertEqual(self.canvas.handy_seiten(), vorher_seiten)
        self.assertEqual(self._schritte(), vorher)
        self.assertIn("kein Platz", self.leiste.letzte_meldung())
        # auch die Konsole selbst lehnt es ab
        self.assertFalse(self.canvas.handy_eintrag_aendern(0, self.t.widget_id, 1, 0))
        self.assertFalse(self.canvas.handy_eintrag_aendern(0, self.t.widget_id, 3, 9, 2, 1))

    def test_ein_klick_ohne_bewegung_aendert_nichts(self):
        vorher = self._schritte()
        QTest.mouseClick(self.raster, Qt.MouseButton.LeftButton, pos=self.raster.zelle_mitte(1, 0))
        self.assertEqual(self._schritte(), vorher)
        self.assertEqual(self.raster.auswahl(), self.u.widget_id)
        QTest.mouseClick(self.raster, Qt.MouseButton.LeftButton, pos=self.raster.zelle_mitte(2, 3))
        self.assertIsNone(self.raster.auswahl())

    def test_groesse_der_taste_ueber_den_griff(self):
        self.canvas.handy_eintrag_aendern(0, self.t.widget_id, 0, 3)
        _app.processEvents()
        vorher = self._schritte()
        self._ziehe_im_raster(self.raster.griff_punkt(self.t.widget_id),
                              self.raster.zelle_mitte(1, 4))
        self.assertEqual(_feld(_eintrag(self.canvas, self.t.widget_id)), (0, 3, 2, 2))
        self.assertEqual(self._schritte(), vorher + 1)
        # weiter ziehen als erlaubt: hoechstens 4 x 2
        self._ziehe_im_raster(self.raster.griff_punkt(self.t.widget_id),
                              self.raster.zelle_mitte(3, 5))
        self.assertEqual(_feld(_eintrag(self.canvas, self.t.widget_id)), (0, 3, 4, 2))
        # und wieder klein
        self._ziehe_im_raster(self.raster.griff_punkt(self.t.widget_id),
                              self.raster.zelle_mitte(0, 3))
        self.assertEqual(_feld(_eintrag(self.canvas, self.t.widget_id)), (0, 3, 1, 1))

    def test_groesse_stoesst_an_nachbarn(self):
        vorher_seiten = self.canvas.handy_seiten()
        self._ziehe_im_raster(self.raster.griff_punkt(self.t.widget_id),
                              self.raster.zelle_mitte(1, 0))    # dort liegt „Zwei"
        self.assertEqual(self.canvas.handy_seiten(), vorher_seiten)

    def test_groesse_des_faders_senkrecht_und_quer(self):
        k = self.f.widget_id
        self.assertEqual(_feld(_eintrag(self.canvas, k)), (3, 0, 1, 3))
        self._ziehe_im_raster(self.raster.griff_punkt(k), self.raster.zelle_mitte(3, 5))
        self.assertEqual(_feld(_eintrag(self.canvas, k)), (3, 0, 1, 5))      # Hoechstgroesse
        self._ziehe_im_raster(self.raster.griff_punkt(k), self.raster.zelle_mitte(3, 0))
        self.assertEqual(_feld(_eintrag(self.canvas, k)), (3, 0, 1, 2))      # Mindestgroesse
        # quer legen: an einen freien Platz, dann nach rechts in EINER Zeile
        self.canvas.handy_eintrag_aendern(0, k, 0, 3)
        _app.processEvents()
        self._ziehe_im_raster(self.raster.griff_punkt(k), self.raster.zelle_mitte(2, 3))
        self.assertEqual(_feld(_eintrag(self.canvas, k)), (0, 3, 3, 1))
        # Konsole begrenzt auch ohne Leiste
        self.assertTrue(self.canvas.handy_eintrag_aendern(0, k, 0, 3, 9, 1))
        self.assertEqual(_feld(_eintrag(self.canvas, k)), (0, 3, 4, 1))

    def test_groesse_der_cueliste(self):
        k = self.liste.widget_id
        self.assertEqual(_feld(_eintrag(self.canvas, k)), (0, 6, 4, 3))
        self._ziehe_im_raster(self.raster.griff_punkt(k), self.raster.zelle_mitte(1, 9))
        self.assertEqual(_feld(_eintrag(self.canvas, k)), (0, 6, 4, 4))      # bleibt 4 breit
        self._ziehe_im_raster(self.raster.griff_punkt(k), self.raster.zelle_mitte(3, 6))
        self.assertEqual(_feld(_eintrag(self.canvas, k)), (0, 6, 4, 2))      # mindestens 2 hoch

    def test_entfernen_mit_entf_laesst_das_original(self):
        kennung = self.t.widget_id
        vorher = self._schritte()
        QTest.mouseClick(self.raster, Qt.MouseButton.LeftButton, pos=self.raster.zelle_mitte(0, 0))
        QTest.keyClick(self.raster, Qt.Key.Key_Delete)
        self.assertIsNone(_eintrag(self.canvas, kennung))
        self.assertEqual(self._schritte(), vorher + 1)
        self.assertIs(self.canvas.widget_mit_kennung(kennung), self.t)       # Original bleibt
        self.assertIn(self.t, self.canvas.alle_widgets())
        self.assertIsNone(self.raster.auswahl())
        QTest.keyClick(self.raster, Qt.Key.Key_Delete)          # nichts gewaehlt: nichts passiert
        self.assertEqual(self._schritte(), vorher + 1)

    def test_entfernen_per_rechtsklick(self):
        kennung = self.u.widget_id
        self.assertIsNone(self.raster.baue_kontextmenue(self.raster.zelle_mitte(2, 3)))   # frei
        menu = self.raster.baue_kontextmenue(self.raster.zelle_mitte(1, 0))
        self.addCleanup(menu.deleteLater)
        akt = [a for a in menu.actions() if a.objectName() == "handy_nehmen"][0]
        self.assertEqual(akt.text(), "Von der Handy-Konsole nehmen")
        akt.trigger()
        self.assertIsNone(_eintrag(self.canvas, kennung))
        self.assertIs(self.canvas.widget_mit_kennung(kennung), self.u)
        self.assertEqual(hs.anzahl_eintraege(self.canvas.handy_seiten()), 3)

    def test_rueckgaengig_und_wiederholen_je_schritt(self):
        staende = [self.canvas.handy_seiten()]

        def schritt(tun):
            n = self._schritte()
            tun()
            self.assertEqual(self._schritte(), n + 1, "genau ein Rückgängig-Schritt")
            staende.append(self.canvas.handy_seiten())
            self.assertNotEqual(staende[-1], staende[-2])

        schritt(lambda: self._ziehe_im_raster(self.raster.zelle_mitte(0, 0),
                                               self.raster.zelle_mitte(0, 2)))        # verschieben
        schritt(lambda: self._ziehe_im_raster(self.raster.griff_punkt(self.t.widget_id),
                                               self.raster.zelle_mitte(1, 3)))        # Groesse
        schritt(lambda: self.canvas.handy_eintrag_entfernen(0, self.u.widget_id))      # entfernen
        schritt(self.leiste.seite_hinzufuegen)                                         # Seite neu
        schritt(lambda: self.leiste.seite_umbenennen(1, "Effekte"))                    # umbenennen
        schritt(lambda: self.canvas.handy_ablegen(self.u))                             # ablegen (S. 2)
        schritt(lambda: self.leiste.seiten_ordnen([1, 0]))                             # umordnen
        with mock.patch.object(leisten_modul.QMessageBox, "question", return_value=JA):
            schritt(lambda: self.leiste.seite_loeschen(0))                             # loeschen
            schritt(self.leiste.alles_leeren)                                          # leeren
        for erwartet in reversed(staende[:-1]):
            self.canvas.undo()
            self.assertEqual(self.canvas.handy_seiten(), erwartet)
        self.assertEqual(self.leiste._reiter.count(), 1)        # die Leiste geht mit
        for erwartet in staende[1:]:
            self.canvas.redo()
            self.assertEqual(self.canvas.handy_seiten(), erwartet)
        self.assertEqual(self.leiste._reiter.count(), 0)
        # die Originale hat nichts davon beruehrt
        for w in (self.t, self.u, self.f, self.liste):
            self.assertIsNotNone(self.canvas.widget_mit_kennung(w.widget_id))

    def test_widget_loeschen_nimmt_die_kachel_mit_und_rueckgaengig_bringt_sie(self):
        kennung = self.u.widget_id
        rufe = []
        self.canvas.handy_seiten_changed.connect(lambda: rufe.append(1))
        self.canvas._remove_widget(self.u)
        self.assertEqual(len(rufe), 1)                           # die Leiste erfaehrt es
        self.assertIsNone(self.raster._eintrag(kennung))
        self.assertIn("3 Verknüpfungen", self.leiste._lbl_hinweis.text())
        self.canvas.undo()
        self.assertIsNotNone(self.raster._eintrag(kennung))


class SeitenTest(_MitAnsicht):

    def test_hinzufuegen_bis_zwoelf(self):
        for i in range(hs.MAX_SEITEN):
            self.assertTrue(self.leiste._btn_seite_neu.isEnabled())
            self.leiste._btn_seite_neu.click()
            self.assertEqual(self.leiste._reiter.count(), i + 1)
            self.assertEqual(self.leiste._reiter.currentIndex(), i)      # die neue ist gewaehlt
        self.assertFalse(self.leiste._btn_seite_neu.isEnabled())
        self.assertIsNone(self.leiste.seite_hinzufuegen())
        self.assertIsNone(self.canvas.handy_seite_hinzufuegen())
        self.assertEqual(len(self.canvas.handy_seiten()["seiten"]), hs.MAX_SEITEN)
        self.assertEqual(self.leiste._reiter.tabText(11), "Seite 12")

    def test_umbenennen_per_doppelklick(self):
        self.leiste.seite_hinzufuegen()
        with mock.patch.object(leisten_modul.QInputDialog, "getText",
                               return_value=("  Effekte   Bühne ", True)) as frage:
            self.leiste._reiter.tabBarDoubleClicked.emit(0)
        self.assertEqual(frage.call_args.kwargs["text"], "Seite 1")
        self.assertEqual(self.canvas.handy_seiten()["seiten"][0]["name"], "Effekte Bühne")
        self.assertEqual(self.leiste._reiter.tabText(0), "Effekte Bühne")
        n = self._schritte()
        with mock.patch.object(leisten_modul.QInputDialog, "getText", return_value=("X", False)):
            self.leiste._reiter.tabBarDoubleClicked.emit(0)          # abgebrochen
        self.assertEqual(self.canvas.handy_seiten()["seiten"][0]["name"], "Effekte Bühne")
        self.assertEqual(self._schritte(), n)
        self.leiste.seite_umbenennen(0, "x" * 99)
        self.assertEqual(len(self.canvas.handy_seiten()["seiten"][0]["name"]), hs.MAX_NAME)

    def test_loeschen_fragt_nur_bei_belegter_seite(self):
        t = self._taste()
        self.canvas.handy_ablegen(t)                             # Seite 1, belegt
        self.leiste.seite_hinzufuegen()                          # Seite 2, leer
        self.leiste.seite_hinzufuegen()                          # Seite 3, leer
        with mock.patch.object(leisten_modul.QMessageBox, "question") as frage:
            self.assertTrue(self.leiste.seite_loeschen(2))       # leer: ohne Rueckfrage
            frage.assert_not_called()
        self.assertEqual(len(self.canvas.handy_seiten()["seiten"]), 2)
        self.canvas.setze_handy_seite_nr(0)
        with mock.patch.object(leisten_modul.QMessageBox, "question",
                               return_value=NEIN) as frage:
            self.leiste._btn_seite_weg.click()
            self.assertEqual(frage.call_count, 1)
            self.assertIn("1 Verknüpfung", frage.call_args[0][2])
        self.assertEqual(len(self.canvas.handy_seiten()["seiten"]), 2)   # „Nein": bleibt
        with mock.patch.object(leisten_modul.QMessageBox, "question", return_value=JA):
            self.leiste._btn_seite_weg.click()
        seiten = self.canvas.handy_seiten()["seiten"]
        self.assertEqual([s["name"] for s in seiten], ["Seite 2"])
        self.assertIsNotNone(self.canvas.widget_mit_kennung(t.widget_id))    # Original bleibt
        self.assertEqual(self.leiste._reiter.count(), 1)

    def test_gezeigte_seite_bleibt_beim_loeschen_davor(self):
        for _ in range(3):
            self.leiste.seite_hinzufuegen()
        self.leiste.seite_umbenennen(2, "Dritte")
        self.assertEqual(self.canvas.handy_seite_nr(), 2)
        self.leiste.seite_loeschen(0)
        self.assertEqual(self.canvas.handy_seite_nr(), 1)
        self.assertEqual(self.leiste._reiter.tabText(self.leiste._reiter.currentIndex()), "Dritte")

    def test_reihenfolge_per_ziehen_ist_ein_schritt(self):
        t = self._taste()
        for name in ("A", "B", "C"):
            self.canvas.handy_seite_hinzufuegen(name)
        self.canvas.handy_ablegen(t, 0, 0, 0)                   # liegt auf „A"
        self.canvas.setze_handy_seite_nr(0)
        reiter = self.leiste._reiter
        self.assertTrue(reiter.isMovable())
        n = self._schritte()
        # Reiter „A" mit der Maus ganz nach rechts ziehen. Qt tauscht dabei
        # Nachbarn einzeln; uebernommen wird erst beim Loslassen.
        _app.processEvents()
        von, bis = reiter.tabRect(0).center(), reiter.tabRect(2).center()
        QTest.mousePress(reiter, Qt.MouseButton.LeftButton, pos=von)
        for x in range(von.x(), bis.x() + 30, 6):
            QTest.mouseMove(reiter, QPoint(x, von.y()))
        self.assertEqual(reiter.reihenfolge(), [1, 2, 0])       # zwei Tausche …
        self.assertEqual(self._schritte(), n)                    # … noch nichts uebernommen
        self.leiste._takt_schlag()                               # der Takt reisst nichts ab
        self.assertEqual(reiter.reihenfolge(), [1, 2, 0])
        QTest.mouseRelease(reiter, Qt.MouseButton.LeftButton,
                           pos=QPoint(bis.x() + 24, von.y()))
        seiten = self.canvas.handy_seiten()["seiten"]
        self.assertEqual([s["name"] for s in seiten], ["B", "C", "A"])
        self.assertEqual(self._schritte(), n + 1)
        self.assertEqual(hs.seiten_mit(self.canvas.handy_seiten(), t.widget_id), [2])
        self.assertEqual(self.canvas.handy_seite_nr(), 2)        # die gezeigte wandert mit
        self.assertEqual([reiter.tabText(i) for i in range(3)], ["B", "C", "A"])
        self.assertEqual(reiter.reihenfolge(), [0, 1, 2])
        self.canvas.undo()
        self.assertEqual([s["name"] for s in self.canvas.handy_seiten()["seiten"]],
                         ["A", "B", "C"])
        self.assertEqual([reiter.tabText(i) for i in range(3)], ["A", "B", "C"])
        # ohne Maus (Tastatur/Programm) gilt jeder Tausch sofort
        reiter.moveTab(2, 0)
        self.assertEqual([s["name"] for s in self.canvas.handy_seiten()["seiten"]],
                         ["C", "A", "B"])

    def test_reiter_waehlt_die_seite_fuer_das_ablegen(self):
        a, b = self._taste(text="A"), self._taste(x=140, text="B")
        self.leiste.seite_hinzufuegen()
        self.leiste.seite_hinzufuegen()
        self.leiste._reiter.setCurrentIndex(0)
        self.assertEqual(self.canvas.handy_seite_nr(), 0)
        self.canvas.handy_ablegen(a)
        self.leiste._reiter.setCurrentIndex(1)
        self.canvas.handy_ablegen(b)
        self.assertEqual(hs.seiten_mit(self.canvas.handy_seiten(), a.widget_id), [0])
        self.assertEqual(hs.seiten_mit(self.canvas.handy_seiten(), b.widget_id), [1])


class KnoepfeTest(_MitAnsicht):

    def test_automatisch_fuellen_fragt_vor_dem_ersetzen(self):
        t = self._taste()
        knopf = self.leiste._btn_fuellen
        self.assertEqual(knopf.text(), "Automatisch füllen")
        with mock.patch.object(leisten_modul.QMessageBox, "question") as frage:
            knopf.click()
            frage.assert_not_called()                           # noch nichts da
        self.assertEqual(self.canvas.handy_kennungen(), {t.widget_id})
        self.assertIn("1 Element", self.leiste.letzte_meldung())
        umgestellt = hs.eintrag_setzen(self.canvas.handy_seiten(), 0, t.widget_id, 3, 7)
        self.canvas.setze_handy_seiten(umgestellt)
        with mock.patch.object(leisten_modul.QMessageBox, "question", return_value=NEIN):
            knopf.click()
        self.assertEqual(self.canvas.handy_seiten(), umgestellt)
        n = self._schritte()
        with mock.patch.object(leisten_modul.QMessageBox, "question", return_value=JA):
            knopf.click()
        self.assertNotEqual(self.canvas.handy_seiten(), umgestellt)
        self.assertEqual(self._schritte(), n + 1)

    def test_automatisch_fuellen_ohne_fernbedienbares(self):
        self.canvas._add_widget("VCLabel", QPoint(10, 10))
        with mock.patch.object(leisten_modul.QMessageBox, "information") as info:
            self.leiste._btn_fuellen.click()
        self.assertIn("Keine fernbedienbaren", info.call_args[0][2])
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())

    def test_alles_leeren_mit_rueckfrage(self):
        self.assertFalse(self.leiste._btn_leeren.isEnabled())   # nichts zu leeren
        t = self._taste()
        self.canvas.handy_ablegen(t)
        self.leiste.seite_hinzufuegen()
        self.assertTrue(self.leiste._btn_leeren.isEnabled())
        vorher = self.canvas.handy_seiten()
        with mock.patch.object(leisten_modul.QMessageBox, "question",
                               return_value=NEIN) as frage:
            self.leiste._btn_leeren.click()
            self.assertEqual(frage.call_count, 1)
        self.assertEqual(self.canvas.handy_seiten(), vorher)
        n = self._schritte()
        with mock.patch.object(leisten_modul.QMessageBox, "question", return_value=JA):
            self.leiste._btn_leeren.click()
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())
        self.assertEqual(self._schritte(), n + 1)
        self.assertIsNotNone(self.canvas.widget_mit_kennung(t.widget_id))
        self.canvas.undo()
        self.assertEqual(self.canvas.handy_seiten(), vorher)


class AbzeichenTest(_MitAnsicht):

    def test_abzeichen_nur_fuer_abgelegte_und_nur_beim_bearbeiten(self):
        a, b = self._taste(text="A"), self._taste(x=140, text="B")
        self.assertFalse(a.hat_handy_abzeichen())
        self.canvas.handy_ablegen(a)
        self.assertTrue(a.hat_handy_abzeichen())
        self.assertFalse(b.hat_handy_abzeichen())
        zeichen = a.findChild(QWidget, "handy_abzeichen")
        # stoert die Bedienung nicht: fuer die Maus durchlaessig, klein, in der Ecke
        self.assertTrue(zeichen.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertLessEqual(zeichen.width(), 20)
        self.assertGreater(zeichen.x(), a.width() // 2)
        self.assertLess(zeichen.y(), a.height() // 2)
        a.resize(200, 90)
        _app.processEvents()
        self.assertEqual(zeichen.x(), 200 - zeichen.width() - zeichen.RAND)   # wandert mit
        # im Betrieb kein Abzeichen
        self.view._btn_edit.setChecked(False)
        self.assertFalse(a.hat_handy_abzeichen())
        self.view._btn_edit.setChecked(True)
        self.assertTrue(a.hat_handy_abzeichen())
        # heruntergenommen -> weg
        self.canvas.handy_eintrag_entfernen(0, a.widget_id)
        self.assertFalse(a.hat_handy_abzeichen())
        # Rueckgaengig baut die Widgets neu — das Abzeichen ist wieder da
        self.canvas.undo()
        self.assertTrue(self.canvas.widget_mit_kennung(a.widget_id).hat_handy_abzeichen())

    def test_abzeichen_stoert_auswahl_und_ziehen_nicht(self):
        a = self._taste(x=40, y=40)
        self.canvas.handy_ablegen(a)
        _app.processEvents()
        zeichen = a.findChild(QWidget, "handy_abzeichen")
        mitte = zeichen.geometry().center()
        self.assertIs(a.childAt(mitte), None)                    # der Klick geht ans Widget
        QTest.mousePress(a, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        QTest.mouseMove(a, QPoint(60, 40))
        QTest.mouseRelease(a, Qt.MouseButton.LeftButton, pos=QPoint(60, 40))
        self.assertEqual((a.x(), a.y()), (80, 60))


class SpeichernTest(_MitAnsicht):

    def test_speichern_und_laden_der_show(self):
        t, f = self._taste(text="Strobe"), self._fader()
        self.canvas.handy_ablegen(t, 0, 2, 1)
        self.canvas.handy_eintrag_aendern(0, t.widget_id, 2, 1, 2, 2)
        self.leiste.seite_hinzufuegen()
        self.leiste.seite_umbenennen(1, "Fader")
        self.canvas.handy_ablegen(f, 1, 0, 0)
        self.canvas.handy_ablegen(t, 1, 3, 0)                    # dieselbe Taste auf Seite 2
        seiten = self.canvas.handy_seiten()
        datei = json.loads(json.dumps(self.view.to_dict()))
        self.assertEqual(datei[hs.SCHLUESSEL], seiten)

        zweite = VCCanvas()
        self.addCleanup(zweite.deleteLater)
        self.addCleanup(zweite.close)
        zweite.from_dict(datei)
        self.assertEqual(zweite.handy_seiten(), seiten)
        self.assertEqual(zweite.to_dict(), self.view.to_dict())

        # in die Ansicht zurueckgeladen: Leiste und Abzeichen stehen wieder
        self.view.from_dict(datei)
        _app.processEvents()
        self.assertEqual(self.canvas.handy_seiten(), seiten)
        self.assertEqual([self.leiste._reiter.tabText(i) for i in range(2)],
                         ["Seite 1", "Fader"])
        self.assertTrue(self.canvas.widget_mit_kennung(t.widget_id).hat_handy_abzeichen())
        self.assertFalse(self.canvas.can_undo())                 # Laden leert den Verlauf


class VerbindungTest(_MitAnsicht):

    def test_schalter_ist_dieselbe_einstellung_wie_im_dialog(self):
        schalter = self.leiste._schalter
        self.assertFalse(schalter.isChecked())
        self.assertEqual(self.leiste._lbl_zustand.text(), "aus")
        with mock.patch.object(vc_remote, "einstellung_geaendert") as geaendert:
            schalter.click()
            geaendert.assert_called_once()                      # Handys erfahren es sofort
        self.assertTrue(remote_settings.is_vc_remote_enabled())
        self.assertEqual(schalter.text(), "Handy-Konsole: an")
        schalter.click()
        self.assertFalse(remote_settings.is_vc_remote_enabled())
        # Umgekehrt: im Dialog (also in der Einstellung) umgelegt -> der Takt zieht nach
        remote_settings.set_vc_remote_enabled(True)
        self.leiste._takt_schlag()
        self.assertTrue(schalter.isChecked())
        self.assertTrue(self.leiste._lbl_zustand.text().startswith("an"))
        remote_settings.set_vc_remote_enabled(False)
        self.leiste._takt_schlag()
        self.assertFalse(schalter.isChecked())
        self.assertEqual(self.leiste._lbl_zustand.text(), "aus")

    def test_zustand_nennt_die_verbundenen_handys(self):
        text = self.leiste.zustand_text
        self.assertEqual(text(False, True, 3), "aus")
        self.assertEqual(text(True, True, 0), "an · 0 Handys verbunden")
        self.assertEqual(text(True, True, 1), "an · 1 Handy verbunden")
        self.assertEqual(text(True, True, 2), "an · 2 Handys verbunden")
        self.assertIn("Web-Interface läuft nicht", text(True, False, 0))
        remote_settings.set_vc_remote_enabled(True)
        from src.web import app as web_app
        vc_remote.setze_sender(lambda *_a: None)
        vc_remote.zuschauer_dazu("handy-1")
        vc_remote.zuschauer_dazu("handy-2")
        try:
            with mock.patch.object(web_app, "is_running", return_value=True):
                self.leiste._takt_schlag()
            self.assertEqual(self.leiste._lbl_zustand.text(), "an · 2 Handys verbunden")
        finally:
            vc_remote.zuschauer_weg("handy-1")
            vc_remote.zuschauer_weg("handy-2")

    def test_verbinden_oeffnet_den_bestehenden_dialog(self):
        self.assertEqual(self.leiste._btn_verbinden.text(), "Verbinden…")
        dialog = mock.Mock()
        with mock.patch.object(self.view, "window",
                               return_value=mock.Mock(_open_web_remote_dialog=dialog)):
            self.leiste._btn_verbinden.click()
        dialog.assert_called_once_with()
        # ohne Hauptfenster: ein Hinweis, wo der Dialog steht
        from src.ui.views import virtual_console_view as ansicht
        with mock.patch.object(self.view, "window", return_value=object()), \
                mock.patch.object(ansicht.QMessageBox, "information") as info:
            self.leiste._btn_verbinden.click()
        self.assertIn("Web-Remote: Verbindung & Token", info.call_args[0][2])

    def test_platz_fuer_den_qr_code_ist_reserviert_aber_leer(self):
        platz = self.leiste.findChild(QWidget, "handy_qr_platz")
        self.assertIsNotNone(platz)
        self.assertFalse(platz.isVisible())
        self.assertEqual(platz.findChildren(QWidget), [])

    def test_aenderung_erscheint_sofort_am_verbundenen_handy(self):
        fern = self.view._fernbedienung
        remote_settings.set_vc_remote_enabled(True)
        vc_remote.registriere(fern)
        gesendet = []
        vc_remote.setze_sender(lambda ereignis, daten: gesendet.append((ereignis, daten)))
        vc_remote.zuschauer_dazu("handy")
        try:
            t = self._taste(text="Neu")
            fern.konsole()                                       # erster Abgleich
            fern._takt()
            self.assertEqual(gesendet, [])
            self._ziehe_in_die_leiste(t, 1, 1)
            fern._takt()
            self.assertEqual([e for e, _ in gesendet], ["vc_konsole"])
            daten = gesendet[-1][1]
            self.assertEqual(daten["seiten"], self.canvas.handy_seiten()["seiten"])
            self.assertEqual(daten["widgets"][t.widget_id]["beschriftung"], "Neu")
            # Groesse geaendert -> wieder die ganze Seite
            self.canvas.handy_eintrag_aendern(0, t.widget_id, 1, 1, 2, 2)
            fern._takt()
            self.assertEqual(gesendet[-1][1]["seiten"][0]["eintraege"][0]["breite"], 2)
            # heruntergenommen -> nicht mehr freigegeben
            self.canvas.handy_eintrag_entfernen(0, t.widget_id)
            fern._takt()
            self.assertEqual(gesendet[-1][1]["widgets"], {})
            self.assertEqual(fern.aktion(t.widget_id, "umschalten",
                                         nur_handy_seiten=True)["fehler"], "nicht_freigegeben")
        finally:
            vc_remote.zuschauer_weg("handy")


class VorschauTest(_MitAnsicht):

    def test_raster_malt_alle_arten_ohne_fehler(self):
        t = self._taste(text="Strobe", aktion=ButtonAction.FLASH)
        bo = self._taste(x=140, text="BLACKOUT", aktion=ButtonAction.BLACKOUT)
        notaus = self._taste(x=260, text="NOT-AUS", aktion=ButtonAction.LASER_ESTOP)
        f, quer = self._fader(), self._fader(x=400)
        liste = self.canvas._add_widget("VCCueList", QPoint(300, 200))
        self.canvas.handy_ablegen(liste, 0, 0, 0)
        self.canvas.handy_ablegen(t, 0, 0, 3)
        self.canvas.handy_ablegen(notaus, 0, 2, 3)
        self.canvas.handy_ablegen(f, 0, 0, 4)
        self.canvas.handy_ablegen(quer, 0, 1, 4)
        self.canvas.handy_eintrag_aendern(0, quer.widget_id, 1, 4, 3, 1)
        self.canvas.handy_ablegen(bo, 0, 0, 9)
        self.assertEqual(_feld(_eintrag(self.canvas, bo.widget_id)), (0, 9, 4, 1))
        # nachtraeglich nicht mehr fernbedienbar: bleibt als leeres Feld stehen
        t.action = ButtonAction.LASER_PATTERN
        self.raster.waehle(f.widget_id)
        with mock.patch("builtins.print") as gedruckt:
            bild = self.leiste.grab()
            self.leiste._takt_schlag()
        fehler = [a for a in gedruckt.call_args_list if "ERROR" in str(a)]
        self.assertEqual(fehler, [])
        self.assertFalse(bild.isNull())
        # gemalt wurde wirklich etwas Buntes (GO-Knopf der Cueliste ist blau)
        punkt = self.raster.kachel_rect(liste.widget_id).center()
        ort = self.raster.mapTo(self.leiste, QPoint(punkt.x() - 40, self.raster.kachel_rect(
            liste.widget_id).bottom() - 12))
        farbe = bild.toImage().pixelColor(ort)
        self.assertGreater(farbe.blue(), farbe.red() + 60)

    def test_farbe_wie_am_handy(self):
        voll, text = leisten_modul.handy_farbe("#000000")
        self.assertEqual((voll.red(), voll.green(), voll.blue()), (88, 166, 255))
        voll, text = leisten_modul.handy_farbe("#400000")       # dunkel -> aufgehellt
        self.assertEqual(voll.red(), 180)
        voll, text = leisten_modul.handy_farbe("#ffffff")
        self.assertEqual(text.name(), "#10141a")                # heller Grund: dunkle Schrift
        self.assertIsNone(leisten_modul.handy_farbe("keine"))
        self.assertIsNone(leisten_modul.handy_farbe(None))


if __name__ == "__main__":
    unittest.main()
