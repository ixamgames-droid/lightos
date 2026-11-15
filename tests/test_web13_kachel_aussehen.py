"""WEB-13: Kacheln der Handy-Konsole im Aussehen der VC-Taste.

(1) ganze Kachel in der Tastenfarbe (aus gedimmt, an voll, Text lesbar),
(2) Effekt-Dynamik (Verlauf mit den Effektfarben, Blinken im Takt) nur bei
    aktiver Taste — die Animation laeuft im Handy, das Pult meldet nur Farben,
    Takt-Art und ganze BPM (keine hohe Nachrichtenrate),
(3) Schalter „Animationen am Handy" (Vorgabe an, gemerkt) und
    ``prefers-reduced-motion``,
(4) eigene Handy-Farbe/-Beschriftung je Kachel: gespeichert in der Show,
    aendert das Original NICHT, alte Shows laden unveraendert,
(5) BLACKOUT, NOT-AUS, gesperrter Laser und verlorenes Ziel bleiben fest.
"""
import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Vor dem Import: Einstellungen in ein Wegwerf-Verzeichnis.
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web13_")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from src.core import handy_seiten as hs  # noqa: E402
from src.core.app_state import get_state  # noqa: E402
from src.ui.virtualconsole import vc_fernbedienung as vf  # noqa: E402
from src.ui.virtualconsole import vc_handy_leiste as leisten_modul  # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction  # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas  # noqa: E402
from src.web import remote_settings, vc_remote  # noqa: E402

_app = QApplication.instance() or QApplication([])
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KONSOLE = os.path.join(_REPO, "src", "web", "templates", "konsole.html")


def _html():
    with open(_KONSOLE, encoding="utf-8") as fh:
        return fh.read()


# ── (4) Datenmodell ──────────────────────────────────────────────────────────

class ModellTest(unittest.TestCase):

    def _abschnitt(self):
        a = hs.seite_hinzufuegen(hs.leer(), "Party")
        a = hs.eintrag_setzen(a, 0, "wtanz1", 0, 0, 2, 1)
        return hs.eintrag_setzen(a, 0, "wtanz2", 2, 0)

    def test_eigenes_aussehen_setzen_und_zuruecksetzen(self):
        a = self._abschnitt()
        neu = hs.eintrag_aussehen(a, 0, "wtanz1", "#FF8800", "  Party!  ")
        e = hs.eintrag(neu, 0, "wtanz1")
        self.assertEqual((e["handy_farbe"], e["handy_text"]), ("#ff8800", "Party!"))
        self.assertTrue(hs.hat_eigenes_aussehen(e))
        self.assertNotIn("handy_farbe", hs.eintrag(a, 0, "wtanz1"))    # Eingabe bleibt
        zurueck = hs.eintrag_aussehen(neu, 0, "wtanz1", None, None)
        self.assertEqual(zurueck, a)
        self.assertIsNone(hs.eintrag_aussehen(a, 0, "wfehlt1", "#000000", "x"))
        self.assertIsNone(hs.eintrag_aussehen(a, 3, "wtanz1", "#000000", "x"))

    def test_ungueltiges_wird_verworfen(self):
        a = self._abschnitt()
        roh = copy.deepcopy(a)
        roh["seiten"][0]["eintraege"][0].update(
            {"handy_farbe": "rot", "handy_text": "   "})
        roh["seiten"][0]["eintraege"][1].update(
            {"handy_farbe": "#12345", "handy_text": "x" * 80})
        n = hs.normalisiere(roh)
        e0, e1 = n["seiten"][0]["eintraege"]
        self.assertNotIn("handy_farbe", e0)
        self.assertNotIn("handy_text", e0)
        self.assertNotIn("handy_farbe", e1)
        self.assertEqual(len(e1["handy_text"]), hs.MAX_HANDY_TEXT)
        for unsinn in (12, None, ["#ffffff"], True):
            self.assertIsNone(hs.handy_farbe_gueltig(unsinn))
            self.assertIsNone(hs.handy_text_gueltig(unsinn))

    def test_verschieben_behaelt_das_aussehen(self):
        a = hs.eintrag_aussehen(self._abschnitt(), 0, "wtanz1", "#00ff00", "Grün")
        b = hs.eintrag_setzen(a, 0, "wtanz1", 0, 4, 2, 2)
        e = hs.eintrag(b, 0, "wtanz1")
        self.assertEqual((e["zeile"], e["hoehe"]), (4, 2))
        self.assertEqual((e["handy_farbe"], e["handy_text"]), ("#00ff00", "Grün"))

    def test_alter_abschnitt_bleibt_unveraendert(self):
        # So schrieb WEB-09/10 die Seiten — ohne Aussehen-Felder.
        alt = {"version": 1, "seiten": [{"name": "Seite 1", "spalten": 4, "zeilen": 10,
               "eintraege": [{"widget": "wabc1", "spalte": 0, "zeile": 0,
                              "breite": 1, "hoehe": 1}]}]}
        self.assertEqual(hs.normalisiere(copy.deepcopy(alt)), alt)


# ── Konsole: setzen, speichern, Original unberuehrt ──────────────────────────

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

    def _taste(self, aktion=ButtonAction.FUNCTION_TOGGLE, text="Tanz 1", x=10, fid=None):
        w = self.canvas._add_widget("VCButton", QPoint(x, 10))
        w.caption = text
        w.action = aktion
        w.function_id = fid
        return w

    def _auf_seite(self, *widgets):
        a = hs.seite_hinzufuegen(hs.leer(), "Test")
        for i, w in enumerate(widgets):
            a = hs.eintrag_setzen(a, 0, w.widget_id, i % 4, i // 4)
        self.assertTrue(self.canvas.setze_handy_seiten(a))


class KonsoleTest(_MitKonsole):

    def test_aendert_das_original_nicht(self):
        t = self._taste()
        t._bg_color = QColor("#3355aa")
        self._auf_seite(t)
        vorher_widget = json.dumps(t.to_dict(), sort_keys=True)
        vorher_caption, vorher_farbe = t.caption, t._bg_color.name()
        schritte = len(self.canvas._undo_stack)
        self.assertTrue(self.canvas.handy_aussehen_setzen(0, t.widget_id, "#ff8800", "Party!"))
        self.assertEqual(len(self.canvas._undo_stack), schritte + 1)
        self.assertEqual((t.caption, t._bg_color.name()), (vorher_caption, vorher_farbe))
        self.assertEqual(json.dumps(t.to_dict(), sort_keys=True), vorher_widget)
        a = self.canvas.handy_auskunft(t)
        self.assertEqual((a["beschriftung"], a["farbe"]), ("Tanz 1", "#3355aa"))
        e = hs.eintrag(self.canvas.handy_seiten(), 0, t.widget_id)
        self.assertEqual((e["handy_farbe"], e["handy_text"]), ("#ff8800", "Party!"))
        # gleiches noch einmal: nichts geaendert, kein Schritt
        self.assertFalse(self.canvas.handy_aussehen_setzen(0, t.widget_id, "#ff8800", "Party!"))
        self.canvas.undo()
        self.assertFalse(hs.hat_eigenes_aussehen(
            hs.eintrag(self.canvas.handy_seiten(), 0, t.widget_id)))

    def test_wird_in_der_show_gespeichert_und_geladen(self):
        t = self._taste()
        self._auf_seite(t)
        self.canvas.handy_aussehen_setzen(0, t.widget_id, "#ff8800", "Party!")
        datei = json.loads(json.dumps(self.canvas.to_dict()))
        zweite = VCCanvas()
        self.addCleanup(zweite.deleteLater)
        zweite.from_dict(datei)
        e = hs.eintrag(zweite.handy_seiten(), 0, t.widget_id)
        self.assertEqual((e["handy_farbe"], e["handy_text"]), ("#ff8800", "Party!"))
        w = zweite.widget_mit_kennung(t.widget_id)
        self.assertEqual(w.caption, "Tanz 1")
        self.assertEqual(zweite.to_dict(), self.canvas.to_dict())

    def test_alte_show_laedt_unveraendert(self):
        # Show-JSON im Stand vor WEB-13 erzeugen: Seiten ohne Aussehen-Felder.
        t = self._taste()
        self._auf_seite(t)
        alt = json.loads(json.dumps(self.canvas.to_dict()))
        for seite in alt[hs.SCHLUESSEL]["seiten"]:
            for e in seite["eintraege"]:
                self.assertFalse(set(e) & set(hs.AUSSEHEN_FELDER))
        zweite = VCCanvas()
        self.addCleanup(zweite.deleteLater)
        zweite.from_dict(copy.deepcopy(alt))
        self.assertEqual(json.loads(json.dumps(zweite.to_dict())), alt)
        e = hs.eintrag(zweite.handy_seiten(), 0, t.widget_id)
        self.assertFalse(hs.hat_eigenes_aussehen(e))

    def test_warnkacheln_sind_nicht_umfaerbbar(self):
        bo = self._taste(ButtonAction.BLACKOUT, "BLACKOUT")
        na = self._taste(ButtonAction.LASER_ESTOP, "NOT-AUS", x=120)
        fader = self.canvas._add_widget("VCSlider", QPoint(240, 10))
        self._auf_seite(bo, na, fader)
        vorher = self.canvas.handy_seiten()
        for w in (bo, na):
            self.assertEqual(self.canvas.handy_aussehen_erlaubt(w.widget_id), (False, False))
            self.assertFalse(self.canvas.handy_aussehen_setzen(0, w.widget_id, "#00ff00", None))
            self.assertFalse(self.canvas.handy_aussehen_setzen(0, w.widget_id, None, "Harmlos"))
        self.assertEqual(self.canvas.handy_seiten(), vorher)
        # Fader: nur die Beschriftung
        self.assertEqual(self.canvas.handy_aussehen_erlaubt(fader.widget_id), (False, True))
        self.assertFalse(self.canvas.handy_aussehen_setzen(0, fader.widget_id, "#00ff00", None))
        self.assertTrue(self.canvas.handy_aussehen_setzen(0, fader.widget_id, None, "Nebel"))


# ── (2) Effekt-Dynamik an der Bruecke ────────────────────────────────────────

class DynamikTest(_MitKonsole):

    def setUp(self):
        super().setUp()
        self.fern = vf.VCFernbedienung(self.canvas)
        remote_settings.set_vc_remote_enabled(True)
        vc_remote.registriere(self.fern)
        self.gesendet = []
        vc_remote.setze_sender(lambda e, d: self.gesendet.append((e, d)))

    def tearDown(self):
        vc_remote.zuschauer_weg("handy")
        vc_remote.alle_loslassen()
        vc_remote.abmelden(self.fern)
        vc_remote.setze_sender(None)
        remote_settings.set_vc_remote_enabled(False)
        super().tearDown()

    def _efx(self, bus=""):
        f = self.fm.new_efx("WEB13 Effekt")
        f.tempo_bus_id = bus
        self._funktionen.append(f)
        return f

    def _farben(self, w, hexe):
        return mock.patch.object(type(w), "_color_badge_colors",
                                 lambda _self: [QColor(h) for h in hexe])

    def test_nur_solange_die_taste_aktiv_ist(self):
        t = self._taste(fid=self._efx().id)
        with self._farben(t, ["#ff0000", "#00ff00", "#0000ff"]):
            self.assertIsNone(vf.beschreibe(t)["effekt"])          # aus: ruhig
            t.fern_taste(True)
            t.fern_taste(False)
            d = vf.beschreibe(t)
        self.assertTrue(d["aktiv"])
        self.assertEqual(d["effekt"], {"farben": ["#ff0000", "#00ff00", "#0000ff"],
                                       "takt": False})

    def test_takt_mit_bpm_vom_bus(self):
        t = self._taste(fid=self._efx(bus="A").id)
        t.fern_taste(True)
        t.fern_taste(False)
        from src.core.engine import tempo_bus
        with mock.patch.object(tempo_bus.TempoBusManager, "bus_for_effect",
                               lambda _s, _b: SimpleNamespace(bpm=127.6)):
            d = vf.beschreibe(t)
        self.assertEqual(d["effekt"], {"farben": [], "takt": True, "bpm": 128})

    def test_bpm_schwankung_loest_keine_meldung_aus(self):
        t = self._taste(fid=self._efx(bus="A").id)
        self._auf_seite(t)
        t.fern_taste(True)
        t.fern_taste(False)
        vc_remote.zuschauer_dazu("handy")
        from src.core.engine import tempo_bus
        bus = SimpleNamespace(bpm=120.2)
        with mock.patch.object(tempo_bus.TempoBusManager, "bus_for_effect",
                               lambda _s, _b: bus):
            self.fern.konsole()
            self.fern._takt()
            for wert in (120.4, 119.8, 120.1, 119.6):
                bus.bpm = wert
                self.fern._takt()
            self.assertEqual(self.gesendet, [])                   # gleiche ganze BPM
            bus.bpm = 140.0
            self.fern._takt()
        self.assertEqual(len(self.gesendet), 1)
        self.assertEqual(self.gesendet[0][1]["widgets"][t.widget_id]["effekt"]["bpm"], 140)

    def test_warnkacheln_ohne_dynamik(self):
        bo = self._taste(ButtonAction.BLACKOUT, "BLACKOUT")
        self.assertIsNone(vf.effekt_dynamik(bo))
        t = self._taste(fid=self._efx().id, x=120)
        t.fern_taste(True)
        t.fern_taste(False)
        with self._farben(t, ["#ff0000", "#0000ff"]), \
                mock.patch.object(vf, "_ziel_fehlt", return_value=["Funktion nicht gefunden"]):
            self.assertIsNone(vf.beschreibe(t)["effekt"])
        with self._farben(t, ["#ff0000", "#0000ff"]), \
                mock.patch.object(vf, "laser_inhalt", return_value=True), \
                mock.patch("src.core.laser.fern_freigabe.laser_erlaubt", return_value=False):
            d = vf.beschreibe(t)
        self.assertEqual(d["gesperrt"], "laser")
        self.assertIsNone(d["effekt"])

    def test_konsole_traegt_das_aussehen_der_kachel(self):
        t = self._taste()
        self._auf_seite(t)
        self.canvas.handy_aussehen_setzen(0, t.widget_id, "#ff8800", "Party!")
        k = self.fern.konsole()
        e = k["seiten"][0]["eintraege"][0]
        self.assertEqual((e["handy_farbe"], e["handy_text"]), ("#ff8800", "Party!"))
        self.assertEqual(k["widgets"][t.widget_id]["beschriftung"], "Tanz 1")


# ── Am Pult: Seitenleiste und Dialog ─────────────────────────────────────────

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
        self.t = self.canvas._add_widget("VCButton", QPoint(20, 20))
        self.t.caption = "Tanz 1"
        self.t.action = ButtonAction.FUNCTION_TOGGLE
        self.bo = self.canvas._add_widget("VCButton", QPoint(140, 20))
        self.bo.caption = "BLACKOUT"
        self.bo.action = ButtonAction.BLACKOUT
        self.canvas.handy_ablegen(self.t, 0, 0, 0)
        self.canvas.handy_ablegen(self.bo, 0, 0, 2)
        _app.processEvents()

    def tearDown(self):
        self.rahmen.close()
        self.rahmen.deleteLater()
        _app.processEvents()

    def _menue(self, spalte, zeile):
        menu = self.raster.baue_kontextmenue(self.raster.zelle_mitte(spalte, zeile))
        self.addCleanup(menu.deleteLater)
        return {a.objectName(): a for a in menu.actions()}

    def test_dialog_ergebnis_und_zuruecksetzen(self):
        dlg = self.leiste.aussehen_dialog(self.t.widget_id)
        self.addCleanup(dlg.deleteLater)
        self.assertIn("Tanz 1", dlg.feld_text.placeholderText())
        self.assertEqual(dlg.ergebnis(), (None, None))
        dlg.feld_text.setText("Party!")
        dlg.setze_farbe("#FF8800")
        self.assertEqual(dlg.ergebnis(), ("#ff8800", "Party!"))
        dlg.zuruecksetzen()
        self.assertEqual(dlg.ergebnis(), (None, None))

    def test_ueber_den_dialog_gesetzt(self):
        dlg = self.leiste.aussehen_dialog(self.t.widget_id)
        dlg.feld_text.setText("Party!")
        dlg.setze_farbe("#ff8800")
        with mock.patch.object(leisten_modul.HandyAussehenDialog, "exec",
                               return_value=leisten_modul.QDialog.DialogCode.Accepted), \
                mock.patch.object(self.leiste, "aussehen_dialog", return_value=dlg):
            self.assertTrue(self.leiste.aussehen_bearbeiten(self.t.widget_id))
        e = hs.eintrag(self.canvas.handy_seiten(), 0, self.t.widget_id)
        self.assertEqual((e["handy_farbe"], e["handy_text"]), ("#ff8800", "Party!"))
        self.assertEqual(self.t.caption, "Tanz 1")
        # Kontextmenue bietet jetzt auch das Zuruecksetzen
        aktionen = self._menue(0, 0)
        self.assertTrue(aktionen["handy_aussehen"].isEnabled())
        aktionen["handy_aussehen_zurueck"].trigger()
        self.assertFalse(hs.hat_eigenes_aussehen(
            hs.eintrag(self.canvas.handy_seiten(), 0, self.t.widget_id)))

    def test_blackout_im_menue_gesperrt(self):
        aktionen = self._menue(0, 2)
        self.assertFalse(aktionen["handy_aussehen"].isEnabled())
        self.assertIsNone(self.leiste.aussehen_dialog(self.bo.widget_id))

    def test_knopf_folgt_der_auswahl_und_vorschau_malt(self):
        knopf = self.leiste._btn_aussehen
        self.raster.waehle(self.t.widget_id)
        self.assertTrue(knopf.isEnabled())
        self.raster.waehle(self.bo.widget_id)
        self.assertFalse(knopf.isEnabled())
        self.leiste.aussehen_setzen(self.t.widget_id, "#ff8800", "Party!")
        self.raster.grab()                                       # malt ohne Fehler
        a, eigen = leisten_modul.handy_aussehen(
            self.canvas.handy_auskunft(self.t),
            hs.eintrag(self.canvas.handy_seiten(), 0, self.t.widget_id))
        self.assertTrue(eigen)
        self.assertEqual((a["beschriftung"], a["farbe"]), ("Party!", "#ff8800"))
        bo, eigen = leisten_modul.handy_aussehen(
            self.canvas.handy_auskunft(self.bo), {"handy_farbe": "#00ff00", "handy_text": "x"})
        self.assertFalse(eigen)
        self.assertEqual(bo["beschriftung"], "BLACKOUT")

    def test_lesbare_textfarbe(self):
        f = leisten_modul._lesbare_textfarbe
        self.assertEqual(f(QColor("#ffff00")).name(), "#10141a")
        self.assertEqual(f(QColor("#0000ff")).name(), "#ffffff")


# ── Handy-Seite: Rechnungen (node) und Aufbau ────────────────────────────────

def _node():
    return shutil.which("node")


@unittest.skipUnless(_node(), "node nicht installiert")
class SeitenRechnungTest(unittest.TestCase):

    def _js(self, ausdruck):
        html = _html()
        a = html.index("/* ── Farben")
        b = html.index("/* WEB13-FARBEN-ENDE */")
        code = html[a:b] + "\nprocess.stdout.write(JSON.stringify(" + ausdruck + "));\n"
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "t.js")
            with open(pfad, "w", encoding="utf-8") as fh:
                fh.write(code)
            out = subprocess.run([_node(), pfad], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_aus_gedimmt_an_voll_text_lesbar(self):
        r = self._js("['#ffff00','#0000ff','#ff8800','#101010'].map(function(h){"
                     "var k=kachelFarben(h);"
                     "function z(t){return t.replace(/rgb\\(|\\)/g,'').split(',').map(Number);}"
                     "return {k:k, ausL:leuchtdichte(z(k.aus.oben)), anL:leuchtdichte(z(k.an.oben)),"
                     "ausK:kontrast(mische(z(k.aus.oben),z(k.aus.unten),0.5), k.aus.text==='#ffffff'?HELL:DUNKEL),"
                     "anK:kontrast(mische(z(k.an.oben),z(k.an.unten),0.5), k.an.text==='#ffffff'?HELL:DUNKEL)};})")
        gelb, blau, orange, schwarz = r
        self.assertEqual(gelb["k"]["an"]["text"], "#10141a")
        self.assertEqual(blau["k"]["an"]["text"], "#ffffff")
        for x in r:
            self.assertLess(x["ausL"], x["anL"])                 # aus ist dunkler
            self.assertGreaterEqual(x["ausK"], 4.5, x)           # Text lesbar
            self.assertGreaterEqual(x["anK"], 4.5, x)
        self.assertIsNone(self._js("kachelFarben('rot')"))

    def test_effekt_stil(self):
        s = self._js("effektStil({farben:['#ff0000','#00ff00','x'],takt:true,bpm:120})")
        self.assertTrue(s["lauf"])
        self.assertEqual(s["verlauf"], "linear-gradient(90deg,#ff0000,#00ff00,#ff0000)")
        self.assertEqual((s["takt"], s["bpm"], s["taktDauer"]), (True, 120, "0.5s"))
        s = self._js("effektStil({farben:['#ff0000'],takt:true,bpm:9999})")
        self.assertFalse(s["lauf"])
        # ueber 180 BPM nur jeder zweite Schlag: nie mehr als 3 Blitze je Sekunde
        self.assertEqual((s["bpm"], s["taktDauer"]), (300, "0.4s"))
        s = self._js("effektStil({farben:['#ff0000'],takt:true,bpm:180})")
        self.assertEqual(s["taktDauer"], "0.333s")
        s = self._js("effektStil({farben:['#ff0000'],takt:true,bpm:181})")
        self.assertEqual(s["taktDauer"], "0.663s")
        s = self._js("effektStil(null)")
        self.assertFalse(s["lauf"] or s["takt"])
        self.assertEqual(self._js("effektStil({takt:true}).bpm"), 120)

    def test_warnkacheln_fest(self):
        r = self._js("[festesAussehen({funktion:'Blackout'}),festesAussehen({funktion:'LaserEstop'}),"
                     "festesAussehen({gesperrt:'laser'}),festesAussehen({ziel_fehlt:['x']}),"
                     "festesAussehen({funktion:'FunctionToggle',ziel_fehlt:[]})]")
        self.assertEqual(r, [True, True, True, True, False])


class SeitenAufbauTest(unittest.TestCase):

    def test_schalter_und_reduzierte_bewegung(self):
        html = _html()
        self.assertIn('id="anim"', html)
        self.assertIn('role="switch"', html)
        self.assertIn("lightos_konsole_anim", html)
        self.assertIn("prefers-reduced-motion: reduce", html)
        self.assertIn("body.ruhig .taste.lauf", html)
        # Vorgabe an: nur ein gemerktes '0' schaltet aus
        self.assertIn("merkLies(MERK_ANIM) !== '0'", html)

    def test_marke_und_eigenes_aussehen_nur_ohne_warnaussehen(self):
        html = _html()
        self.assertIn("marke.textContent = 'Handy'", html)
        self.assertIn("var eigenFarbe = !fest && eigen.handy_farbe", html)
        self.assertIn("var eigenText = !fest && eigen.handy_text", html)
        # Effekt-Dynamik nur bei aktiver, gefaerbter Taste
        self.assertIn("effektStil(neu.aktiv && f && k ? neu.effekt : null)", html)

    def test_keine_animation_per_skript_takt(self):
        # Die Animation laeuft rein per CSS: kein setInterval/requestAnimationFrame.
        html = _html()
        self.assertNotIn("setInterval", html)
        self.assertNotIn("requestAnimationFrame", html)
        self.assertIsNone(re.search(r"@import|url\(\s*['\"]?https?:", html))


if __name__ == "__main__":
    unittest.main()
