"""WEB-14: Einzel-Auswahl am Handy sichtbar machen und eigene Handy-Gruppen.

(b) Kacheln, deren Original-Tasten in einem Rahmen mit Einzel-Auswahl
    (Solo-Frame) liegen, meldet die Bruecke mit ``einzel`` (Rahmen-Kennung und
    -Titel); das Handy zeichnet sie als Gruppe (blauer Rahmen, „immer nur
    eine“) — als Overlay, das keine Zelle belegt.
(c) eigene Handy-Gruppen: gespeichert in der Show (alte Shows unveraendert),
    eine Kachel in hoechstens einer Gruppe, am Handy ist immer hoechstens EINE
    Taste der Gruppe aktiv („keine aktiv“ erlaubt). Ausgeschaltet wird ueber
    denselben Weg wie ein Handy-Druck — nie eine Taste, die das Handy sonst
    nicht bedienen duerfte (Laser-Sperre, gehalten, Blackout/NOT-AUS).
"""
import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Vor dem Import: Einstellungen in ein Wegwerf-Verzeichnis.
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web14_")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from src.core import handy_seiten as hs  # noqa: E402
from src.core.app_state import get_state  # noqa: E402
from src.ui.virtualconsole import vc_fernbedienung as vf  # noqa: E402
from src.ui.virtualconsole import vc_handy_leiste as leisten_modul  # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton  # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas  # noqa: E402
from src.web import remote_settings, vc_remote  # noqa: E402

_app = QApplication.instance() or QApplication([])
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KONSOLE = os.path.join(_REPO, "src", "web", "templates", "konsole.html")


def _html():
    with open(_KONSOLE, encoding="utf-8") as fh:
        return fh.read()


def _seiten(*kennungen):
    a = hs.seite_hinzufuegen(hs.leer(), "Party")
    for i, k in enumerate(kennungen):
        a = hs.eintrag_setzen(a, 0, k, i % 4, i // 4)
    return a


# ── Datenmodell ──────────────────────────────────────────────────────────────

class ModellTest(unittest.TestCase):

    def test_anlegen_bearbeiten_aufloesen(self):
        a = _seiten("wtanz1", "wtanz2", "wblau1", "wwarm1")
        g = hs.gruppe_setzen(a, None, "  Grund  farbe ", ["wblau1", "wwarm1", "wblau1"])
        self.assertEqual(g[hs.GRUPPEN], [{"name": "Grund farbe",
                                          "widgets": ["wblau1", "wwarm1"]}])
        self.assertNotIn(hs.GRUPPEN, a)                     # Eingabe bleibt
        self.assertEqual(hs.gruppe_von(g, "wwarm1"), 0)
        self.assertIsNone(hs.gruppe_von(g, "wtanz1"))
        g2 = hs.gruppe_setzen(g, 0, "", ["wwarm1"])
        self.assertEqual(g2[hs.GRUPPEN], [{"name": "Gruppe 1", "widgets": ["wwarm1"]}])
        self.assertEqual(hs.gruppe_entfernen(g2, 0), a)
        self.assertIsNone(hs.gruppe_entfernen(g2, 3))
        self.assertIsNone(hs.gruppe_setzen(g2, 5, "x", ["wtanz1"]))
        self.assertEqual(hs.aus_gruppe_nehmen(g2, "wwarm1"), a)
        self.assertIsNone(hs.aus_gruppe_nehmen(g2, "wtanz1"))

    def test_eine_kachel_nur_in_einer_gruppe(self):
        a = _seiten("wtanz1", "wtanz2", "wblau1")
        g = hs.gruppe_setzen(a, None, "A", ["wtanz1", "wtanz2"])
        g = hs.gruppe_setzen(g, None, "B", ["wtanz2", "wblau1"])     # wandert nach B
        self.assertEqual([x["widgets"] for x in g[hs.GRUPPEN]],
                         [["wtanz1"], ["wtanz2", "wblau1"]])
        # Datei von Hand doppelt: die erste Gruppe gewinnt
        roh = copy.deepcopy(a)
        roh[hs.GRUPPEN] = [{"name": "X", "widgets": ["wtanz1"]},
                           {"name": "Y", "widgets": ["wtanz1", "wblau1"]}]
        n = hs.normalisiere(roh)
        self.assertEqual([x["widgets"] for x in n[hs.GRUPPEN]], [["wtanz1"], ["wblau1"]])

    def test_nur_kacheln_auf_einer_seite_und_unsinn_faellt_weg(self):
        a = _seiten("wtanz1", "wtanz2")
        roh = copy.deepcopy(a)
        roh[hs.GRUPPEN] = [{"name": 7, "widgets": ["wfehlt1", "wtanz1", 3, None]},
                           {"name": "leer", "widgets": ["wfehlt2"]},
                           "kaputt", {"widgets": "wtanz2"}]
        n = hs.normalisiere(roh)
        self.assertEqual(n[hs.GRUPPEN], [{"name": "Gruppe 1", "widgets": ["wtanz1"]}])
        # Kachel von der Seite genommen -> aus der Gruppe, leere Gruppe weg
        ohne = hs.eintrag_entfernen(n, 0, "wtanz1")
        self.assertNotIn(hs.GRUPPEN, hs.normalisiere(ohne))
        self.assertEqual(hs.normalisiere({"version": 1, "seiten": [],
                                          hs.GRUPPEN: "x"}), hs.leer())

    def test_grenze_der_gruppenzahl(self):
        kennungen = [f"wk{i:04d}" for i in range(hs.MAX_GRUPPEN + 1)]
        a = hs.leer()
        for nr in range(3):
            a = hs.seite_hinzufuegen(a)
        for i, k in enumerate(kennungen):
            a = hs.eintrag_setzen(a, i // 40, k, i % 4, (i // 4) % 10)
        for k in kennungen[:hs.MAX_GRUPPEN]:
            a = hs.gruppe_setzen(a, None, k, [k])
        self.assertEqual(len(a[hs.GRUPPEN]), hs.MAX_GRUPPEN)
        self.assertIsNone(hs.gruppe_setzen(a, None, "zuviel", [kennungen[-1]]))

    def test_alter_abschnitt_bleibt_unveraendert(self):
        alt = {"version": 1, "seiten": [{"name": "Seite 1", "spalten": 4, "zeilen": 10,
               "eintraege": [{"widget": "wabc1", "spalte": 0, "zeile": 0,
                              "breite": 1, "hoehe": 1}]}]}
        n = hs.normalisiere(copy.deepcopy(alt))
        self.assertEqual(n, alt)
        self.assertNotIn(hs.GRUPPEN, n)


# ── Konsole: Gruppen anlegen, speichern, alte Shows ──────────────────────────

class _MitKonsole(unittest.TestCase):

    def setUp(self):
        self.state = get_state()
        self.fm = self.state.function_manager
        self.fm.stop_all()
        self.canvas = VCCanvas()
        self._funktionen = []

    def tearDown(self):
        self.fm.stop_all()
        for f in self._funktionen:
            self.fm.remove(f.id)
        self.canvas.close()
        self.canvas.deleteLater()
        _app.processEvents()

    def _efx(self, name):
        f = self.fm.new_efx(name)
        self._funktionen.append(f)
        return f

    def _taste(self, aktion=ButtonAction.FUNCTION_TOGGLE, text="Tanz", x=10,
               fid=None, parent=None):
        if parent is None:
            w = self.canvas._add_widget("VCButton", QPoint(x, 10))
        else:
            w = VCButton(text, parent=parent)
        w.caption = text
        w.action = aktion
        if aktion in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
            w.function_id = fid if fid is not None else self._efx(f"WEB14 {text}").id
        return w

    def _rahmen(self, titel, solo=False, x=300):
        r = self.canvas._add_widget("VCFrame", QPoint(x, 200))
        r.caption = titel
        r.set_solo(solo)
        return r

    def _auf_seite(self, *widgets):
        self.assertTrue(self.canvas.setze_handy_seiten(
            _seiten(*[w.widget_id for w in widgets])))


class KonsoleTest(_MitKonsole):

    def test_anlegen_mit_rueckgaengig(self):
        a, b = self._taste(text="Warm"), self._taste(text="Blau", x=120)
        self._auf_seite(a, b)
        schritte = len(self.canvas._undo_stack)
        ok, grund = self.canvas.handy_gruppe_setzen(None, "Grundfarbe",
                                                   [a.widget_id, b.widget_id])
        self.assertTrue(ok, grund)
        self.assertEqual(len(self.canvas._undo_stack), schritte + 1)
        self.assertEqual(self.canvas.handy_gruppen(),
                         [{"name": "Grundfarbe", "widgets": [a.widget_id, b.widget_id]}])
        self.assertTrue(self.canvas.handy_aus_gruppe_nehmen(a.widget_id))
        self.assertTrue(self.canvas.handy_gruppe_entfernen(0))
        self.assertEqual(self.canvas.handy_gruppen(), [])
        self.canvas.undo()
        self.canvas.undo()
        self.assertEqual(len(self.canvas.handy_gruppen()[0]["widgets"]), 2)

    def test_sicherheitstasten_nie_in_einer_gruppe(self):
        t = self._taste(text="Tanz")
        verboten = [self._taste(aktion, text=aktion.value, x=60 * i + 120)
                    for i, aktion in enumerate((ButtonAction.BLACKOUT,
                                                ButtonAction.LASER_ESTOP,
                                                ButtonAction.STOP_ALL,
                                                ButtonAction.LASER_ARM))]
        fader = self.canvas._add_widget("VCSlider", QPoint(500, 10))
        self._auf_seite(t, *verboten, fader)
        for w in verboten + [fader]:
            with self.subTest(getattr(w, "caption", "fader")):
                ok, grund = self.canvas.handy_gruppe_erlaubt(w.widget_id)
                self.assertFalse(ok)
                self.assertTrue(grund)
                ok, _ = self.canvas.handy_gruppe_setzen(None, "x", [t.widget_id, w.widget_id])
                self.assertFalse(ok)
        self.assertEqual(self.canvas.handy_gruppen(), [])
        # nicht auf einer Handy-Seite
        weg = self._taste(text="Weg", x=600)
        self.assertFalse(self.canvas.handy_gruppe_setzen(None, "x", [weg.widget_id])[0])

    def test_wird_in_der_show_gespeichert_und_geladen(self):
        a, b = self._taste(text="Warm"), self._taste(text="Blau", x=120)
        self._auf_seite(a, b)
        self.canvas.handy_gruppe_setzen(None, "Grundfarbe", [a.widget_id, b.widget_id])
        datei = json.loads(json.dumps(self.canvas.to_dict()))
        self.assertEqual(datei[hs.SCHLUESSEL][hs.GRUPPEN],
                         [{"name": "Grundfarbe", "widgets": [a.widget_id, b.widget_id]}])
        zweite = VCCanvas()
        self.addCleanup(zweite.deleteLater)
        zweite.from_dict(datei)
        self.assertEqual(zweite.handy_gruppen(), self.canvas.handy_gruppen())
        self.assertEqual(zweite.to_dict(), self.canvas.to_dict())

    def test_alte_show_laedt_unveraendert(self):
        # Show-JSON im Stand vor WEB-14 erzeugen: Seiten ohne ``gruppen``.
        a, b = self._taste(text="Warm"), self._taste(text="Blau", x=120)
        self._auf_seite(a, b)
        alt = json.loads(json.dumps(self.canvas.to_dict()))
        self.assertNotIn(hs.GRUPPEN, alt[hs.SCHLUESSEL])
        zweite = VCCanvas()
        self.addCleanup(zweite.deleteLater)
        zweite.from_dict(copy.deepcopy(alt))
        self.assertEqual(json.loads(json.dumps(zweite.to_dict())), alt)
        self.assertEqual(zweite.handy_gruppen(), [])

    def test_automatisch_fuellen_behaelt_gruppen(self):
        a, b = self._taste(text="Warm"), self._taste(text="Blau", x=120)
        self._auf_seite(a, b)
        self.canvas.handy_gruppe_setzen(None, "Grundfarbe", [a.widget_id, b.widget_id])
        self.canvas.handy_konsole_automatisch_fuellen()
        self.assertEqual(self.canvas.handy_gruppen()[0]["widgets"],
                         [a.widget_id, b.widget_id])


# ── (b) Einzel-Auswahl des Pults an der Bruecke ──────────────────────────────

class EinzelAuswahlTest(_MitKonsole):

    def test_solo_rahmen_wird_gemeldet(self):
        solo = self._rahmen("Tanz", solo=True)
        frei = self._rahmen("Stimmung", solo=False, x=600)
        t1 = self._taste(text="Tanz 1", parent=solo)
        t2 = self._taste(text="Tanz 2", parent=solo)
        s1 = self._taste(text="Warm", parent=frei)
        lose = self._taste(text="Lose", x=900)
        self.assertEqual(vf.beschreibe(t1)["einzel"], {"id": solo.widget_id, "titel": "Tanz"})
        self.assertEqual(vf.beschreibe(t2)["einzel"]["id"], solo.widget_id)
        self.assertIsNone(vf.beschreibe(s1)["einzel"])
        self.assertIsNone(vf.beschreibe(lose)["einzel"])
        solo.set_solo(False)                 # am Pult umgestellt -> keine Gruppe mehr
        self.assertIsNone(vf.beschreibe(t1)["einzel"])

    def test_vom_handy_greift_die_regel_des_rahmens(self):
        fern = vf.VCFernbedienung(self.canvas)
        solo = self._rahmen("Tanz", solo=True)
        t1 = self._taste(text="Tanz 1", parent=solo)
        t2 = self._taste(text="Tanz 2", parent=solo)
        self._auf_seite(t1, t2)
        self.assertTrue(fern.aktion(t1.widget_id, "umschalten", nur_handy_seiten=True)["ok"])
        self.assertTrue(fern.aktion(t2.widget_id, "umschalten", nur_handy_seiten=True)["ok"])
        self.assertEqual([t1.leuchtet(), t2.leuchtet()], [False, True])
        k = fern.konsole()
        self.assertEqual(k["widgets"][t1.widget_id]["einzel"]["titel"], "Tanz")
        self.assertEqual(k["gruppen"], [])


# ── (c) eigene Handy-Gruppen an der Bruecke ──────────────────────────────────

class HandyGruppeTest(_MitKonsole):

    def setUp(self):
        super().setUp()
        self.fern = vf.VCFernbedienung(self.canvas)
        # wie im echten Betrieb: Tasten aus verschiedenen Rahmen
        r1 = self._rahmen("Stimmung", x=300)
        r2 = self._rahmen("Effekte", x=700)
        self.a = self._taste(text="Warm", parent=r1)
        self.b = self._taste(text="Blau", parent=r2)
        self.c = self._taste(text="Lauflicht", x=10)
        self.fremd = self._taste(text="Nebel", x=120)
        self._auf_seite(self.a, self.b, self.c, self.fremd)
        ok, grund = self.canvas.handy_gruppe_setzen(
            None, "Grundfarbe", [self.a.widget_id, self.b.widget_id, self.c.widget_id])
        self.assertTrue(ok, grund)
        self.gruppe = [self.a, self.b, self.c]

    def _tipp(self, w):
        return self.fern.aktion(w.widget_id, "umschalten", nur_handy_seiten=True)

    def _aktiv(self):
        return [w.caption for w in self.gruppe if w.leuchtet()]

    def test_immer_nur_eine_aktiv(self):
        for w in (self.a, self.b, self.c, self.a, self.c, self.b):
            r = self._tipp(w)
            self.assertTrue(r["ok"], r)
            self.assertEqual(self._aktiv(), [w.caption])
        # Pult-Zustand stimmt mit dem Handy ueberein: die Funktion laeuft nur einmal
        laufend = [w for w in self.gruppe if self.fm.is_running(w.function_id)]
        self.assertEqual(laufend, [self.b])

    def test_keine_aktiv_ist_erlaubt(self):
        self._tipp(self.a)
        self.assertEqual(self._aktiv(), ["Warm"])
        self.assertTrue(self._tipp(self.a)["ok"])            # nochmal = aus
        self.assertEqual(self._aktiv(), [])

    def test_fremde_taste_und_pult_unberuehrt(self):
        self._tipp(self.fremd)
        self._tipp(self.a)
        self.assertTrue(self.fremd.leuchtet())               # nicht in der Gruppe
        # Am Pult (Klick ohne Handy) gilt die Handy-Gruppe nicht
        self.b.fern_taste(True)
        self.b.fern_taste(False)
        self.assertEqual(self._aktiv(), ["Warm", "Blau"])
        r = self.fern.aktion(self.c.widget_id, "umschalten")   # nicht vom Handy
        self.assertTrue(r["ok"])
        self.assertEqual(self._aktiv(), ["Warm", "Blau", "Lauflicht"])
        # der naechste Handy-Tipp raeumt auf
        self._tipp(self.c)                                     # c aus
        self._tipp(self.c)                                     # c an, Rest aus
        self.assertEqual(self._aktiv(), ["Lauflicht"])

    def test_ueber_den_handy_weg_mit_halten(self):
        remote_settings.set_vc_remote_enabled(True)
        vc_remote.registriere(self.fern)
        self.addCleanup(remote_settings.set_vc_remote_enabled, False)
        self.addCleanup(vc_remote.abmelden, self.fern)
        self.addCleanup(vc_remote.alle_loslassen)
        self.assertTrue(vc_remote.widget_aktion(self.a.widget_id, "umschalten")["ok"])
        r = vc_remote.halten("handy1", self.b.widget_id)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["gruppe_aus"], [self.a.widget_id])
        self.assertEqual(self._aktiv(), ["Blau"])
        vc_remote.loslassen_von("handy1", self.b.widget_id)
        self.assertEqual(self._aktiv(), ["Blau"])            # Toggle bleibt an
        k = vc_remote.konsole()
        self.assertEqual(k["gruppen"], [{"name": "Grundfarbe", "widgets": [
            self.a.widget_id, self.b.widget_id, self.c.widget_id]}])

    def test_gehaltene_taste_wird_nicht_losgelassen(self):
        self.a.fern_taste(True)                  # am Pult/anderem Handy gehalten
        r = self._tipp(self.b)
        self.assertEqual(r, {"ok": False, "fehler": vf.GRUPPE_BLOCKIERT})
        self.assertTrue(self.a._pressed)
        self.assertFalse(self.b.leuchtet())
        self.assertEqual(vc_remote.status_fuer(r), 409)
        self.a.fern_taste(False)

    def test_laser_gesperrte_taste_wird_nicht_ausgeschaltet(self):
        self._tipp(self.a)
        from src.core.laser import fern_freigabe as ff
        with mock.patch.object(vf, "laser_inhalt", lambda w, state=None: w is self.a), \
                mock.patch.object(ff, "laser_erlaubt", return_value=False):
            r = self._tipp(self.b)
            self.assertEqual(r["fehler"], vf.GRUPPE_BLOCKIERT)
            self.assertEqual(self._aktiv(), ["Warm"])
            # die gesperrte Taste selbst: Ablehnung mit dem Laser-Grund
            self._tipp(self.a)
            self.assertEqual(self._tipp(self.a)["fehler"], vf.LASER_GESPERRT)
        self.assertEqual(self._aktiv(), ["Warm"])

    def test_nicht_mehr_freigegebene_taste_wird_nicht_angefasst(self):
        self._tipp(self.a)
        # a von der Seite nehmen -> nicht mehr in der Gruppe, bleibt an
        self.assertTrue(self.canvas.handy_eintrag_entfernen(0, self.a.widget_id))
        self._tipp(self.b)
        self.assertEqual(self._aktiv(), ["Warm", "Blau"])
        self.assertEqual(self.canvas.handy_gruppen()[0]["widgets"],
                         [self.b.widget_id, self.c.widget_id])

    def test_blackout_aus_manipulierter_datei_bleibt_aussen_vor(self):
        bo = self._taste(ButtonAction.BLACKOUT, text="BLACKOUT", x=900)
        na = self._taste(ButtonAction.LASER_ESTOP, text="NOT-AUS", x=1000)
        a = _seiten(*[w.widget_id for w in (self.a, self.b, self.c, self.fremd, bo, na)])
        a[hs.GRUPPEN] = [{"name": "Boese", "widgets": [
            bo.widget_id, na.widget_id, self.a.widget_id]}]
        self.assertTrue(self.canvas.setze_handy_seiten(a))
        om = self.state.output_manager
        vorher = om.blackout
        bo.fern_taste(True)                      # Blackout am Pult gehalten
        try:
            self._tipp(self.a)
            self.assertTrue(bo._pressed)        # nicht angefasst
            self.assertTrue(self.a.leuchtet())
            # Gruppe am Handy ohne Blackout/NOT-AUS
            k = self.fern.konsole()
            self.assertEqual(k["gruppen"], [{"name": "Boese", "widgets": [self.a.widget_id]}])
        finally:
            bo.fern_taste(False)
        self.assertEqual(om.blackout, vorher)
        # ein Druck auf BLACKOUT schaltet keine Gruppen-Taste aus
        with mock.patch.object(vf, "_gruppe_der_taste",
                               wraps=vf._gruppe_der_taste) as gefragt:
            self.fern.aktion(bo.widget_id, "druecken", nur_handy_seiten=True)
            self.fern.aktion(bo.widget_id, "loslassen", nur_handy_seiten=True)
        gefragt.assert_not_called()
        self.assertTrue(self.a.leuchtet())
        self.assertFalse(vf.gruppe_erlaubt(bo)[0])
        self.assertFalse(vf.gruppe_erlaubt(na)[0])

    def test_gruppenwechsel_meldet_vollstaendig(self):
        remote_settings.set_vc_remote_enabled(True)
        vc_remote.registriere(self.fern)
        gesendet = []
        vc_remote.setze_sender(lambda e, d: gesendet.append((e, d)))
        vc_remote.zuschauer_dazu("handy")
        try:
            self.fern._takt()
            gesendet.clear()
            self.canvas.handy_gruppe_setzen(0, "Farbe", [self.a.widget_id])
            self.fern._takt()
            self.assertEqual(gesendet[-1][0], "vc_konsole")
            self.assertEqual(gesendet[-1][1]["gruppen"],
                             [{"name": "Farbe", "widgets": [self.a.widget_id]}])
        finally:
            vc_remote.zuschauer_weg("handy")
            vc_remote.abmelden(self.fern)
            vc_remote.setze_sender(None)
            remote_settings.set_vc_remote_enabled(False)


# ── Seitenleiste am Pult ─────────────────────────────────────────────────────

class LeisteTest(unittest.TestCase):

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
        self.t1 = self._taste("Warm", 20)
        self.t2 = self._taste("Blau", 140)
        self.bo = self._taste("BLACKOUT", 260, ButtonAction.BLACKOUT)
        self.canvas.handy_ablegen(self.t1, 0, 0, 0)
        self.canvas.handy_ablegen(self.t2, 0, 1, 0)
        self.canvas.handy_ablegen(self.bo, 0, 0, 2)
        _app.processEvents()

    def tearDown(self):
        self.rahmen.close()
        self.rahmen.deleteLater()
        _app.processEvents()

    def _taste(self, text, x, aktion=ButtonAction.FUNCTION_TOGGLE):
        w = self.canvas._add_widget("VCButton", QPoint(x, 20))
        w.caption = text
        w.action = aktion
        return w

    def _menue(self, spalte, zeile):
        menu = self.raster.baue_kontextmenue(self.raster.zelle_mitte(spalte, zeile))
        self.addCleanup(menu.deleteLater)
        return {a.objectName(): a for a in menu.actions()}

    def test_dialog_zeigt_kacheln_blackout_nicht_waehlbar(self):
        self.assertTrue(self.leiste._btn_gruppe.isEnabled())
        dlg = self.leiste.gruppe_dialog()
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg.feld_name.text(), "Gruppe 1")
        self.assertEqual(dlg.liste.count(), 3)
        dlg.setze_auswahl([self.t1.widget_id, self.t2.widget_id, self.bo.widget_id])
        dlg.feld_name.setText("Grundfarbe")
        self.assertEqual(dlg.ergebnis(), ("Grundfarbe", [self.t1.widget_id, self.t2.widget_id]))

    def test_ueber_den_dialog_angelegt_und_im_menue(self):
        dlg = self.leiste.gruppe_dialog(None, [self.t1.widget_id])
        dlg.setze_auswahl([self.t1.widget_id, self.t2.widget_id])
        dlg.feld_name.setText("Grundfarbe")
        with mock.patch.object(leisten_modul.HandyGruppeDialog, "exec",
                               return_value=leisten_modul.QDialog.DialogCode.Accepted), \
                mock.patch.object(self.leiste, "gruppe_dialog", return_value=dlg):
            self.assertTrue(self.leiste.gruppe_bearbeiten(None))
        self.assertEqual(self.canvas.handy_gruppen(), [
            {"name": "Grundfarbe", "widgets": [self.t1.widget_id, self.t2.widget_id]}])
        aktionen = self._menue(0, 0)
        self.assertIn("handy_gruppe_bearbeiten", aktionen)
        self.assertIn("„Grundfarbe“", aktionen["handy_gruppe_bearbeiten"].text())
        # zweite Gruppe: t1 steht drin, ist aber nicht waehlbar
        dlg2 = self.leiste.gruppe_dialog()
        self.addCleanup(dlg2.deleteLater)
        texte = [dlg2.liste.item(i).text() for i in range(dlg2.liste.count())]
        self.assertTrue(any("schon in „Grundfarbe“" in t for t in texte), texte)
        dlg2.setze_auswahl([self.t1.widget_id])
        self.assertEqual(dlg2.ergebnis()[1], [])
        self.raster.grab()                                   # malt ohne Fehler
        aktionen["handy_gruppe_raus"].trigger()
        self.assertEqual(self.canvas.handy_gruppen()[0]["widgets"], [self.t2.widget_id])
        self._menue(1, 0)["handy_gruppe_aufloesen"].trigger()
        self.assertEqual(self.canvas.handy_gruppen(), [])

    def test_blackout_menue_ohne_gruppe(self):
        aktionen = self._menue(0, 2)
        self.assertFalse(aktionen["handy_gruppe_neu_mit"].isEnabled())
        self.assertFalse(self.leiste.gruppe_setzen(None, "x", [self.bo.widget_id]))
        self.assertEqual(self.canvas.handy_gruppen(), [])

    def test_ausserhalb_bearbeiten_kein_dialog(self):
        self.view._btn_edit.setChecked(False)
        _app.processEvents()
        self.assertIsNone(self.leiste.gruppe_dialog())
        self.assertFalse(self.leiste._btn_gruppe.isEnabled())


# ── Handy-Seite: Gruppen-Rahmen (node) und Aufbau ────────────────────────────

def _node():
    return shutil.which("node")


@unittest.skipUnless(_node(), "node nicht installiert")
class GruppenRechnungTest(unittest.TestCase):

    def _js(self, vorher, ausdruck):
        html = _html()
        a = html.index("/* ── WEB-14: Gruppen sichtbar machen")
        b = html.index("/* WEB14-GRUPPEN-ENDE */")
        code = (vorher + "\n" + html[a:b] + "\nprocess.stdout.write(JSON.stringify("
                + ausdruck + "));\n")
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "t.js")
            with open(pfad, "w", encoding="utf-8") as fh:
                fh.write(code)
            out = subprocess.run([_node(), pfad], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    _STAND = (
        "var E=[{widget:'wa',spalte:0,zeile:0,breite:1,hoehe:1},"
        "{widget:'wb',spalte:1,zeile:0,breite:1,hoehe:1},"
        "{widget:'wc',spalte:0,zeile:2,breite:2,hoehe:1},"
        "{widget:'wx',spalte:0,zeile:1,breite:1,hoehe:1},"
        "{widget:'wf',spalte:3,zeile:0,breite:1,hoehe:3}];"
        "var stand={widgets:{"
        "wa:{typ:'taste',einzel:{id:'r1',titel:'Tanz'}},"
        "wb:{typ:'taste',einzel:{id:'r1',titel:'Tanz'}},"
        "wc:{typ:'taste',einzel:null},wx:{typ:'taste',einzel:{id:'r2',titel:'Allein'}},"
        "wf:{typ:'fader'}},"
        "gruppen:[{name:'Grundfarbe',widgets:['wa','wc']}]};")

    def test_gruppen_der_seite(self):
        r = self._js(self._STAND, "gruppenDerSeite(E).map(function(g){return [g.art,g.titel,"
                                  "g.eintraege.map(function(e){return e.widget;})];})")
        self.assertEqual(r, [["einzel", "Tanz (immer nur eine)", ["wa", "wb"]],
                             ["handy", "Grundfarbe (nur Handy)", ["wa", "wc"]]])
        # ein Rahmen mit nur einer Kachel auf der Seite ist keine sichtbare Gruppe

    def test_gemeinsamer_kasten_nur_ohne_fremde_kachel(self):
        r = self._js(self._STAND, "gruppenFelder(gruppenDerSeite(E)[0],E)")
        self.assertEqual(r, [{"spalte": 0, "zeile": 0, "breite": 2, "hoehe": 1,
                              "titel": True, "einzeln": False}])
        # wa (0,0) und wc (0..1, Zeile 2): dazwischen liegt wx -> je Kachel
        r = self._js(self._STAND, "gruppenFelder(gruppenDerSeite(E)[1],E)")
        self.assertEqual([(f["spalte"], f["zeile"], f["titel"], f["einzeln"]) for f in r],
                         [(0, 0, True, True), (0, 2, False, True)])


class SeitenAufbauTest(unittest.TestCase):

    def test_rahmen_belegen_keine_zelle(self):
        html = _html()
        self.assertIn(".gruppe{position:relative;pointer-events:none", html)
        self.assertIn("(immer nur eine)", html)
        self.assertIn("(nur Handy)", html)
        self.assertIn(".gruppe.handy{border:2px dashed #f2cc60", html)
        self.assertIn(".gruppe.einzel{border:2px solid #58a6ff", html)
        self.assertIn("gruppe_blockiert:", html)
        self.assertIn("zeichneGruppen();", html)


if __name__ == "__main__":
    unittest.main()
