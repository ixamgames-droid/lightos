"""WEB-09: Datenmodell der Handy-Konsole — die Handy-Seiten.

Die Seiten sind Verknuepfungen auf Widgets der grossen Konsole (Kennung aus
WEB-08) in einem Raster 4 x 10. Sie liegen im VC-Layout und gehen damit ueber
dieselben Wege wie die Widgets: Show, „Canvas exportieren/importieren",
Rueckgaengig.

Geprueft wird das Modell selbst (ohne Qt), „Automatisch fuellen" und der Weg
durch die Konsole: Speichern/Laden, Show von frueher, verwaiste
Verknuepfungen, doppelte Kennungen, Rueckgaengig/Wiederholen.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from src.core import handy_seiten as hs
from src.ui.virtualconsole import vc_widget
from src.ui.virtualconsole.vc_button import ButtonAction
from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_frame import VCFrame

_app = QApplication.instance() or QApplication([])


def _taste(kennung, text="T", funktion="FunctionToggle"):
    return {"id": kennung, "typ": "taste", "funktion": funktion, "beschriftung": text}


def _fader(kennung):
    return {"id": kennung, "typ": "fader", "beschriftung": "F"}


def _cueliste(kennung):
    return {"id": kennung, "typ": "cueliste", "beschriftung": "Liste"}


def _belegung(seite) -> dict:
    """Zelle -> Kennung; schlaegt fehl, wenn zwei Eintraege dieselbe Zelle belegen."""
    zellen = {}
    for e in seite["eintraege"]:
        for z in range(e["zeile"], e["zeile"] + e["hoehe"]):
            for s in range(e["spalte"], e["spalte"] + e["breite"]):
                assert (s, z) not in zellen, f"Zelle {(s, z)} doppelt belegt"
                assert 0 <= s < hs.SPALTEN and 0 <= z < hs.ZEILEN, "ausserhalb des Rasters"
                zellen[(s, z)] = e["widget"]
    return zellen


def _eintrag(abschnitt, kennung):
    for nr, seite in enumerate(abschnitt["seiten"]):
        for e in seite["eintraege"]:
            if e["widget"] == kennung:
                return nr, e
    return None, None


# ── Modell ───────────────────────────────────────────────────────────────────

class ModellTest(unittest.TestCase):

    def test_raster_ist_vier_mal_zehn(self):
        self.assertEqual((hs.SPALTEN, hs.ZEILEN), (4, 10))

    def test_kennungsmuster_gleicht_dem_der_widgets(self):
        # Das Modell wiederholt das Muster, um ohne Qt auszukommen.
        self.assertEqual(hs._KENNUNG_MUSTER.pattern, vc_widget._KENNUNG_MUSTER.pattern)

    def test_leer_und_unsinn(self):
        for roh in (None, [], "x", 5, {}, {"seiten": "nein"}, {"seiten": [1, None]}):
            self.assertEqual(hs.normalisiere(roh), hs.leer(), roh)
        self.assertTrue(hs.ist_leer(hs.leer()))

    def test_mehrere_seiten_mit_namen(self):
        a = hs.seite_hinzufuegen(hs.leer(), "Show")
        a = hs.seite_hinzufuegen(a)
        a = hs.seite_hinzufuegen(a, "   ")
        self.assertEqual([s["name"] for s in a["seiten"]], ["Show", "Seite 2", "Seite 3"])
        a = hs.seite_umbenennen(a, 1, "Farben  und   Effekte, sehr langer Name hier")
        self.assertEqual(a["seiten"][1]["name"], "Farben und Effekte, sehr")
        a = hs.seite_entfernen(a, 0)
        self.assertEqual(len(a["seiten"]), 2)
        self.assertIsNone(hs.seite_entfernen(a, 7))

    def test_hoechstzahl_der_seiten(self):
        a = hs.leer()
        for _ in range(hs.MAX_SEITEN):
            a = hs.seite_hinzufuegen(a)
        self.assertIsNone(hs.seite_hinzufuegen(a))
        viele = {"seiten": [{"name": str(i)} for i in range(hs.MAX_SEITEN + 5)]}
        self.assertEqual(len(hs.normalisiere(viele)["seiten"]), hs.MAX_SEITEN)

    def test_eintrag_setzen_verschieben_entfernen(self):
        a = hs.seite_hinzufuegen(hs.leer())
        a = hs.eintrag_setzen(a, 0, "wtaste01", 0, 0)
        a = hs.eintrag_setzen(a, 0, "wfader01", 1, 0, 1, 3)
        self.assertEqual(hs.freigegebene_kennungen(a), {"wtaste01", "wfader01"})
        # belegt: abgelehnt, nichts veraendert
        self.assertIsNone(hs.eintrag_setzen(a, 0, "wtaste02", 1, 2))
        # verschieben: der eigene Platz zaehlt nicht als belegt
        b = hs.eintrag_setzen(a, 0, "wfader01", 1, 1, 1, 3)
        self.assertEqual(_eintrag(b, "wfader01")[1]["zeile"], 1)
        self.assertEqual(hs.anzahl_eintraege(b), 2)
        # die Eingabe bleibt unberuehrt (Vorher-Stand fuer das Rueckgaengig)
        self.assertEqual(_eintrag(a, "wfader01")[1]["zeile"], 0)
        c = hs.eintrag_entfernen(b, 0, "wtaste01")
        self.assertEqual(hs.freigegebene_kennungen(c), {"wfader01"})
        self.assertIsNone(hs.eintrag_entfernen(c, 0, "wtaste01"))

    def test_ausserhalb_des_rasters_wird_abgelehnt(self):
        a = hs.seite_hinzufuegen(hs.leer())
        self.assertIsNone(hs.eintrag_setzen(a, 0, "wtaste01", 4, 0))
        self.assertIsNone(hs.eintrag_setzen(a, 0, "wtaste01", 3, 0, 2, 1))
        self.assertIsNone(hs.eintrag_setzen(a, 0, "wtaste01", 0, 8, 1, 3))
        self.assertIsNone(hs.eintrag_setzen(a, 0, "wtaste01", -1, 0))
        self.assertIsNone(hs.eintrag_setzen(a, 0, "wtaste01", 0, 0, 0, 1))
        self.assertIsNone(hs.eintrag_setzen(a, 3, "wtaste01", 0, 0))
        self.assertIsNone(hs.eintrag_setzen(a, 0, "12345", 0, 0))

    def test_normalisieren_verwirft_kaputte_eintraege(self):
        roh = {"version": 1, "seiten": [{"name": "A", "eintraege": [
            {"widget": "wgut0001", "spalte": 0, "zeile": 0, "breite": 2, "hoehe": 1},
            {"widget": "wueber01", "spalte": 1, "zeile": 0},             # ueberlappt
            {"widget": "wgut0001", "spalte": 0, "zeile": 5},             # zweimal
            {"widget": "wraus001", "spalte": 3, "zeile": 9, "breite": 2},  # zu breit
            {"widget": "123456", "spalte": 0, "zeile": 2},               # keine Kennung
            {"widget": "wbool001", "spalte": True, "zeile": 2},          # kein int
            {"widget": "wtext001", "spalte": "1", "zeile": 2},
            "kein dict",
            {"widget": "wgut0002", "spalte": 2.0, "zeile": 3},           # 2.0 == 2
        ]}]}
        a = hs.normalisiere(roh)
        self.assertEqual([e["widget"] for e in a["seiten"][0]["eintraege"]],
                         ["wgut0001", "wgut0002"])
        self.assertEqual(a["seiten"][0]["eintraege"][1],
                         {"widget": "wgut0002", "spalte": 2, "zeile": 3,
                          "breite": 1, "hoehe": 1})
        _belegung(a["seiten"][0])

    def test_verwaiste_fallen_mit_bekannten_kennungen_weg(self):
        a = hs.seite_hinzufuegen(hs.leer())
        a = hs.eintrag_setzen(a, 0, "wda00001", 0, 0)
        a = hs.eintrag_setzen(a, 0, "wweg0001", 1, 0)
        self.assertEqual(hs.freigegebene_kennungen(hs.normalisiere(a)),
                         {"wda00001", "wweg0001"})
        self.assertEqual(hs.freigegebene_kennungen(hs.normalisiere(a, {"wda00001"})),
                         {"wda00001"})

    def test_abschnitt_ist_json_tauglich(self):
        a = hs.automatisch_fuellen([_taste("wtaste01"), _fader("wfader01")])
        self.assertEqual(hs.normalisiere(json.loads(json.dumps(a))), a)


# ── Automatisch fuellen ──────────────────────────────────────────────────────

class AutomatischFuellenTest(unittest.TestCase):

    def test_nichts_ergibt_keine_seite(self):
        self.assertEqual(hs.automatisch_fuellen([]), hs.leer())
        self.assertEqual(hs.automatisch_fuellen(None), hs.leer())

    def test_groessen_je_art(self):
        a = hs.automatisch_fuellen([
            _cueliste("wcue0001"), _taste("wtaste01", "Rot"),
            _taste("wlang001", "Publikumslicht"), _fader("wfader01"),
            _taste("wblack01", "BO", "Blackout"), _taste("wnot0001", "Stop", "LaserEstop"),
        ])
        gr = lambda k: (_eintrag(a, k)[1]["breite"], _eintrag(a, k)[1]["hoehe"])
        self.assertEqual(gr("wcue0001"), (4, 3))
        self.assertEqual(gr("wtaste01"), (1, 1))
        self.assertEqual(gr("wlang001"), (2, 1))      # lange Beschriftung
        self.assertEqual(gr("wnot0001"), (2, 1))      # Not-Taste
        self.assertEqual(gr("wfader01"), (1, 3))      # senkrecht
        self.assertEqual(gr("wblack01"), (4, 1))

    def test_anordnung_cueliste_oben_blackout_unten(self):
        tasten = [_taste(f"wtaste{i:02d}") for i in range(8)]
        fader = [_fader(f"wfader{i:02d}") for i in range(4)]
        a = hs.automatisch_fuellen(
            [_taste("wblack01", "BO", "Blackout")] + fader + tasten + [_cueliste("wcue0001")])
        self.assertEqual(len(a["seiten"]), 1)
        zellen = _belegung(a["seiten"][0])
        self.assertEqual({zellen[(s, 0)] for s in range(4)}, {"wcue0001"})
        self.assertEqual({zellen[(s, 9)] for s in range(4)}, {"wblack01"})
        # Tasten in der Reihenfolge der Konsole, zeilenweise unter der Cueliste
        self.assertEqual([zellen[(s, 3)] for s in range(4)],
                         ["wtaste00", "wtaste01", "wtaste02", "wtaste03"])
        # Fader nebeneinander auf gleicher Hoehe
        zeilen = {_eintrag(a, f["id"])[1]["zeile"] for f in fader}
        self.assertEqual(zeilen, {5})
        self.assertEqual([zellen[(s, 5)] for s in range(4)], [f["id"] for f in fader])

    def test_fader_beginnen_in_eigener_zeile(self):
        # 5 Tasten = eine volle und eine angebrochene Zeile: die Fader fuellen
        # die Luecke NICHT auf, sie stehen darunter in einer Reihe.
        a = hs.automatisch_fuellen([_taste(f"wtaste{i:02d}") for i in range(5)]
                                   + [_fader("wfader01"), _fader("wfader02")])
        self.assertEqual(_eintrag(a, "wfader01")[1]["zeile"], 2)
        self.assertEqual(_eintrag(a, "wfader02")[1]["zeile"], 2)

    def test_ueberlauf_geht_auf_weitere_seiten(self):
        viele = [_taste(f"wtaste{i:03d}") for i in range(95)]
        a = hs.automatisch_fuellen(viele + [_taste("wblack01", "BO", "Blackout")])
        self.assertEqual(len(a["seiten"]), 3)            # 36 + 40 + 19
        self.assertEqual(hs.anzahl_eintraege(a), 96)
        for seite in a["seiten"]:
            _belegung(seite)
        self.assertEqual([s["name"] for s in a["seiten"]], ["Seite 1", "Seite 2", "Seite 3"])
        # Blackout nur auf der ersten Seite, unten
        self.assertEqual(_eintrag(a, "wblack01")[0], 0)
        self.assertEqual(_eintrag(a, "wblack01")[1]["zeile"], 9)
        self.assertEqual(hs.freigegebene_kennungen(a),
                         {t["id"] for t in viele} | {"wblack01"})

    def test_jedes_widget_genau_einmal(self):
        a = hs.automatisch_fuellen([_taste("wtaste01"), _taste("wtaste01"),
                                    {"id": "wxy00001", "typ": "xypad"},
                                    {"id": "nichts"}, "unsinn", _fader("wfader01")])
        self.assertEqual(hs.freigegebene_kennungen(a), {"wtaste01", "wfader01"})
        self.assertEqual(hs.anzahl_eintraege(a), 2)

    def test_mehr_als_alle_seiten_fassen_bricht_nicht(self):
        zu_viele = [_cueliste(f"wcue{i:04d}") for i in range(hs.MAX_SEITEN * 3 + 4)]
        a = hs.automatisch_fuellen(zu_viele)
        self.assertEqual(len(a["seiten"]), hs.MAX_SEITEN)
        self.assertEqual(hs.anzahl_eintraege(a), hs.MAX_SEITEN * 3)


# ── Durch die Konsole ────────────────────────────────────────────────────────

class _MitKonsole(unittest.TestCase):
    def setUp(self):
        self.canvas = VCCanvas()

    def tearDown(self):
        self.canvas.close()
        self.canvas.deleteLater()

    def _konsole_fuellen(self):
        self.taste = self.canvas._add_widget("VCButton", QPoint(10, 10))
        self.taste.caption = "Strobe"
        self.fader = self.canvas._add_widget("VCSlider", QPoint(100, 10))
        self.liste = self.canvas._add_widget("VCCueList", QPoint(200, 10))
        self.kasten = self.canvas._add_widget("VCFrame", QPoint(10, 300))
        self.im_kasten = self.kasten._add_child_widget("VCButton", QPoint(10, 30))
        self.label = self.canvas._add_widget("VCLabel", QPoint(500, 10))
        self.muster = self.canvas._add_widget("VCButton", QPoint(600, 10))
        self.muster.action = ButtonAction.LASER_PATTERN


class KonsoleTest(_MitKonsole):

    def test_neue_konsole_hat_keine_seiten_und_schreibt_keinen_abschnitt(self):
        self.canvas._add_widget("VCButton", QPoint(10, 10))
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())
        self.assertNotIn(hs.SCHLUESSEL, self.canvas.to_dict())

    def test_automatisch_fuellen_nimmt_nur_fernbedienbares(self):
        self._konsole_fuellen()
        anzahl, seiten = self.canvas.handy_konsole_automatisch_fuellen()
        self.assertEqual((anzahl, seiten), (4, 1))
        self.assertEqual(
            hs.freigegebene_kennungen(self.canvas.handy_seiten()),
            {self.taste.widget_id, self.fader.widget_id, self.liste.widget_id,
             self.im_kasten.widget_id})
        # Beschriftung, Kasten und Laser-Muster sind nicht fernbedienbar
        for w in (self.label, self.kasten, self.muster):
            self.assertNotIn(w.widget_id,
                             hs.freigegebene_kennungen(self.canvas.handy_seiten()))

    def test_speichern_und_laden_nimmt_die_seiten_mit(self):
        self._konsole_fuellen()
        self.canvas.handy_konsole_automatisch_fuellen()
        seiten = self.canvas.handy_seiten()
        d = json.loads(json.dumps(self.canvas.to_dict()))
        self.assertEqual(d[hs.SCHLUESSEL], seiten)
        self.assertEqual(d[hs.SCHLUESSEL]["version"], hs.VERSION)

        neu = VCCanvas()
        self.addCleanup(neu.deleteLater)
        neu.from_dict(d)
        self.assertEqual(neu.handy_seiten(), seiten)
        # jede Verknuepfung trifft im neuen Canvas wieder ein Widget gleicher Art
        for kennung in hs.freigegebene_kennungen(seiten):
            alt = self.canvas.widget_mit_kennung(kennung)
            wieder = neu.widget_mit_kennung(kennung)
            self.assertIsNotNone(wieder, kennung)
            self.assertEqual(type(wieder).__name__, type(alt).__name__)
        self.assertEqual(neu.to_dict(), d)

    def test_canvas_exportieren_und_importieren(self):
        # „Canvas exportieren…/importieren…" der Werkzeugleiste.
        self._konsole_fuellen()
        self.canvas.handy_konsole_automatisch_fuellen()
        seiten = self.canvas.handy_seiten()
        pfad = os.path.join(tempfile.mkdtemp(prefix="lightos_web09_"), "layout.json")
        from src.ui.virtualconsole import vc_canvas as modul
        with mock.patch.object(modul.QFileDialog, "getSaveFileName",
                               return_value=(pfad, "")):
            self.canvas._save()
        with open(pfad, encoding="utf-8") as f:
            self.assertEqual(json.load(f)[hs.SCHLUESSEL], seiten)
        neu = VCCanvas()
        self.addCleanup(neu.deleteLater)
        with mock.patch.object(modul.QFileDialog, "getOpenFileName",
                               return_value=(pfad, "")):
            neu._load()
        self.assertEqual(neu.handy_seiten(), seiten)

    def test_alt_show_laedt_unveraendert(self):
        alt = {"widgets": [
            {"type": "VCButton", "caption": "Strobe", "x": 8, "y": 8, "w": 72, "h": 72},
            {"type": "VCSlider", "caption": "Master", "x": 96, "y": 8, "w": 60, "h": 200},
        ]}
        self.canvas.from_dict(alt)
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())
        d = self.canvas.to_dict()
        self.assertEqual(set(d), {"widgets"})
        self.assertEqual([w["caption"] for w in d["widgets"]], ["Strobe", "Master"])

    def test_alt_show_gilt_nicht_als_geaendert_neue_seiten_schon(self):
        from src.core.show.show_file import _vc_ohne_live_werte
        alt = {"widgets": [
            {"type": "VCButton", "caption": "Strobe", "x": 8, "y": 8, "w": 72, "h": 72}]}
        self.canvas.from_dict(alt)
        geladen = self.canvas.to_dict()
        vorher = _vc_ohne_live_werte(geladen)
        # Laden allein aendert nichts am Inhalt
        self.assertEqual(vorher, _vc_ohne_live_werte(self.canvas.to_dict()))
        self.assertNotIn(hs.SCHLUESSEL, vorher)
        # Seiten anlegen ist eine Aenderung, die gespeichert werden will
        self.canvas.handy_konsole_automatisch_fuellen()
        nachher = _vc_ohne_live_werte(self.canvas.to_dict())
        self.assertNotEqual(vorher, nachher)
        self.assertIn(hs.SCHLUESSEL, nachher)

    def test_kaputter_abschnitt_kostet_nicht_die_konsole(self):
        for kaputt in ("text", 7, [1, 2], {"seiten": 3}, {"seiten": [{"eintraege": "x"}]}):
            self.canvas.from_dict({"widgets": [
                {"type": "VCButton", "caption": "A", "x": 8, "y": 8, "w": 72, "h": 72}],
                hs.SCHLUESSEL: kaputt})
            self.assertEqual(len(self.canvas.alle_widgets()), 1, kaputt)
            self.assertEqual(hs.anzahl_eintraege(self.canvas.handy_seiten()), 0)

    def test_verwaiste_verknuepfung_faellt_beim_laden_weg(self):
        self._konsole_fuellen()
        self.canvas.handy_konsole_automatisch_fuellen()
        d = json.loads(json.dumps(self.canvas.to_dict()))
        weg = self.fader.widget_id
        d["widgets"] = [w for w in d["widgets"] if w.get("id") != weg]
        neu = VCCanvas()
        self.addCleanup(neu.deleteLater)
        neu.from_dict(d)
        frei = hs.freigegebene_kennungen(neu.handy_seiten())
        self.assertNotIn(weg, frei)
        self.assertEqual(len(frei), 3)
        self.assertNotIn(weg, json.dumps(neu.to_dict()[hs.SCHLUESSEL]))

    def test_geloeschtes_widget_verschwindet_von_der_seite(self):
        self._konsole_fuellen()
        self.canvas.handy_konsole_automatisch_fuellen()
        kennung = self.taste.widget_id
        self.canvas._remove_widget(self.taste)
        self.assertNotIn(kennung, hs.freigegebene_kennungen(self.canvas.handy_seiten()))
        self.assertNotIn(kennung, json.dumps(self.canvas.to_dict()[hs.SCHLUESSEL]))

    def test_doppelte_kennung_verknuepfung_bleibt_beim_ersten(self):
        # Von Hand zusammenkopierte Datei: zwei Widgets, eine Kennung. Das erste
        # behaelt sie (WEB-08) — und damit auch den Platz auf der Handy-Seite.
        d = {"widgets": [
            {"type": "VCButton", "id": "wdoppelt0001", "caption": "Erste",
             "x": 8, "y": 8, "w": 72, "h": 72},
            {"type": "VCButton", "id": "wdoppelt0001", "caption": "Zweite",
             "x": 96, "y": 8, "w": 72, "h": 72}],
            hs.SCHLUESSEL: {"version": 1, "seiten": [{"name": "A", "eintraege": [
                {"widget": "wdoppelt0001", "spalte": 0, "zeile": 0,
                 "breite": 1, "hoehe": 1}]}]}}
        self.canvas.from_dict(d)
        self.assertEqual(hs.freigegebene_kennungen(self.canvas.handy_seiten()),
                         {"wdoppelt0001"})
        self.assertEqual(self.canvas.widget_mit_kennung("wdoppelt0001").caption, "Erste")

    def test_signal_bei_aenderung(self):
        rufe = []
        self.canvas.handy_seiten_changed.connect(lambda: rufe.append(1))
        self.canvas._add_widget("VCButton", QPoint(10, 10))
        self.canvas.handy_konsole_automatisch_fuellen()
        self.assertEqual(len(rufe), 1)
        # dieselbe Anordnung noch einmal: keine Aenderung, kein Undo-Schritt
        tiefe = len(self.canvas._undo_stack)
        self.assertFalse(self.canvas.setze_handy_seiten(self.canvas.handy_seiten()))
        self.assertEqual(len(rufe), 1)
        self.assertEqual(len(self.canvas._undo_stack), tiefe)

    def test_setzen_verwirft_verknuepfungen_auf_fremde_kennungen(self):
        t = self.canvas._add_widget("VCButton", QPoint(10, 10))
        a = hs.seite_hinzufuegen(hs.leer())
        a = hs.eintrag_setzen(a, 0, t.widget_id, 0, 0)
        a = hs.eintrag_setzen(a, 0, "wgibtsnicht1", 1, 0)
        self.assertTrue(self.canvas.setze_handy_seiten(a))
        self.assertEqual(hs.freigegebene_kennungen(self.canvas.handy_seiten()),
                         {t.widget_id})


class UndoTest(_MitKonsole):

    def test_automatisch_fuellen_rueckgaengig_und_wiederholen(self):
        self._konsole_fuellen()
        self.canvas.handy_konsole_automatisch_fuellen()
        gefuellt = self.canvas.handy_seiten()
        self.assertTrue(self.canvas.can_undo())
        self.canvas.undo()
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())
        self.assertEqual(len(self.canvas.alle_widgets()), 7)   # Widgets unberuehrt
        self.canvas.redo()
        self.assertEqual(self.canvas.handy_seiten(), gefuellt)

    def test_aenderung_am_modell_ist_ein_schritt(self):
        t = self.canvas._add_widget("VCButton", QPoint(10, 10))
        self.canvas.handy_konsole_automatisch_fuellen()
        erster = self.canvas.handy_seiten()
        verschoben = hs.eintrag_setzen(erster, 0, t.widget_id, 2, 4, 2, 1)
        self.assertTrue(self.canvas.setze_handy_seiten(verschoben))
        zweite_seite = hs.seite_hinzufuegen(self.canvas.handy_seiten(), "Effekte")
        self.assertTrue(self.canvas.setze_handy_seiten(zweite_seite))
        self.assertEqual(len(self.canvas.handy_seiten()["seiten"]), 2)
        self.canvas.undo()
        self.assertEqual(self.canvas.handy_seiten(), verschoben)
        self.canvas.undo()
        self.assertEqual(self.canvas.handy_seiten(), erster)
        self.canvas.redo()
        self.canvas.redo()
        self.assertEqual(self.canvas.handy_seiten(), zweite_seite)

    def test_widget_loeschen_rueckgaengig_bringt_die_verknuepfung_zurueck(self):
        self._konsole_fuellen()
        self.canvas.handy_konsole_automatisch_fuellen()
        vorher = self.canvas.handy_seiten()
        kennung = self.fader.widget_id
        self.canvas._remove_widget(self.fader)
        self.assertNotIn(kennung, hs.freigegebene_kennungen(self.canvas.handy_seiten()))
        self.canvas.undo()
        self.assertEqual(self.canvas.handy_seiten(), vorher)
        self.assertEqual(type(self.canvas.widget_mit_kennung(kennung)).__name__, "VCSlider")

    def test_laden_leert_den_verlauf_samt_seiten(self):
        self.canvas._add_widget("VCButton", QPoint(10, 10))
        self.canvas.handy_konsole_automatisch_fuellen()
        self.canvas.from_dict({"widgets": []})
        self.assertFalse(self.canvas.can_undo())
        self.assertEqual(self.canvas.handy_seiten(), hs.leer())


class KnopfTest(unittest.TestCase):
    """Der vorlaeufige Einstieg in der Werkzeugleiste der virtuellen Konsole."""

    def setUp(self):
        from src.ui.views.virtual_console_view import VirtualConsoleView
        self.view = VirtualConsoleView()

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()

    def test_knopf_fuellt_und_fragt_vor_dem_ersetzen(self):
        from src.ui.views import virtual_console_view as modul
        canvas = self.view._canvas
        knopf = self.view._btn_handy_fuellen
        self.assertIn("Handy", knopf.text())
        self.assertIn("Handy-Konsole automatisch füllen", knopf.toolTip())
        self.assertTrue(knopf.property("edit_only"))

        t = canvas._add_widget("VCButton", QPoint(10, 10))
        with mock.patch.object(modul.QMessageBox, "information") as info, \
                mock.patch.object(modul.QMessageBox, "question") as frage:
            knopf.click()
            frage.assert_not_called()          # noch nichts da, nichts zu ersetzen
            self.assertEqual(info.call_count, 1)
        self.assertEqual(hs.freigegebene_kennungen(canvas.handy_seiten()), {t.widget_id})

        # Jetzt gibt es Seiten: von Hand umgestellt, dann „Nein" — bleibt.
        umgestellt = hs.eintrag_setzen(canvas.handy_seiten(), 0, t.widget_id, 3, 7)
        canvas.setze_handy_seiten(umgestellt)
        with mock.patch.object(modul.QMessageBox, "information"), \
                mock.patch.object(modul.QMessageBox, "question",
                                  return_value=modul.QMessageBox.StandardButton.No):
            knopf.click()
        self.assertEqual(canvas.handy_seiten(), umgestellt)
        with mock.patch.object(modul.QMessageBox, "information"), \
                mock.patch.object(modul.QMessageBox, "question",
                                  return_value=modul.QMessageBox.StandardButton.Yes):
            knopf.click()
        self.assertNotEqual(canvas.handy_seiten(), umgestellt)

    def test_ohne_fernbedienbares_gibt_es_einen_hinweis_statt_leerer_seiten(self):
        from src.ui.views import virtual_console_view as modul
        self.view._canvas._add_widget("VCLabel", QPoint(10, 10))
        with mock.patch.object(modul.QMessageBox, "information") as info:
            self.view._btn_handy_fuellen.click()
        self.assertIn("Keine fernbedienbaren", info.call_args[0][2])
        self.assertEqual(self.view._canvas.handy_seiten(), hs.leer())


if __name__ == "__main__":
    unittest.main()
