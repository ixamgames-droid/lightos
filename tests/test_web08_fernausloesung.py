"""WEB-08: Fernausloesung eines VC-Widgets ueber seine Kennung.

Das Handy "drueckt" das Original im Pult. Geprueft wird deshalb nicht, ob
irgendetwas passiert, sondern ob GENAU dasselbe passiert wie bei einem Klick:
ein echter Mausklick (offscreen) auf ein Zwillings-Widget ist der Massstab.

Dazu die Ablehnungen (unbekannte Kennung, nicht fernbedienbarer Typ, kaputter
Wert, Laser scharf schalten), die Uebergabe in den UI-Thread und die
Web-Schnittstelle mit Schluessel — die standardmaessig AUS ist.
"""
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Vor dem Import: Schluessel/Einstellungen in ein Wegwerf-Verzeichnis.
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web08_")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.virtualconsole.vc_button import ButtonAction
from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_fernbedienung import VCFernbedienung
from src.ui.virtualconsole.vc_frame import VCFrame
from src.ui.virtualconsole.vc_slider import SliderMode
from src.web import remote_settings, vc_remote

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

_app = QApplication.instance() or QApplication([])


def _klick(widget, press=True, release=True):
    """Ein echter Mausklick im Bedien-Modus — der Massstab."""
    mitte = widget.rect().center()
    if press:
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=mitte)
    if release:
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=mitte)


class _Basis(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.fm = self.state.function_manager
        self.fm.stop_all()
        self.state.output_manager.set_blackout(False)
        self.canvas = VCCanvas()
        self.fern = VCFernbedienung(self.canvas)
        self._funktionen = []

    def tearDown(self):
        self.fm.stop_all()
        self.state.output_manager.set_blackout(False)
        for f in self._funktionen:
            self.fm.remove(f.id)
        self.canvas.close()
        self.canvas.deleteLater()

    def _efx(self, name):
        f = self.fm.new_efx(name)
        self._funktionen.append(f)
        return f

    def _taste(self, aktion=ButtonAction.FUNCTION_TOGGLE, fid=None, x=10, eltern=None,
               beschriftung="T"):
        if eltern is None:
            w = self.canvas._add_widget("VCButton", QPoint(x, 10))
        else:
            w = eltern._add_child_widget("VCButton", QPoint(x, 30))
        w.caption = beschriftung
        w.action = aktion
        w.function_id = fid
        return w

    def _eintrag(self, widget):
        return [e for e in self.fern.widgets() if e["id"] == widget.widget_id][0]


# ── Tasten ───────────────────────────────────────────────────────────────────

class TasteWieKlickTest(_Basis):

    def test_umschalten_startet_und_stoppt_wie_ein_klick(self):
        a, b = self._efx("WEB08 A"), self._efx("WEB08 B")
        geklickt = self._taste(fid=a.id, x=10)
        fern = self._taste(fid=b.id, x=100)

        _klick(geklickt)
        r = self.fern.aktion(fern.widget_id, "umschalten")
        self.assertTrue(r["ok"], r)
        self.assertTrue(self.fm.is_running(a.id))
        self.assertTrue(self.fm.is_running(b.id))
        self.assertEqual(self._eintrag(fern)["aktiv"], self._eintrag(geklickt)["aktiv"])
        self.assertTrue(self._eintrag(fern)["aktiv"])
        self.assertFalse(self._eintrag(fern)["gedrueckt"])

        _klick(geklickt)
        self.fern.aktion(fern.widget_id, "umschalten")
        self.assertFalse(self.fm.is_running(a.id))
        self.assertFalse(self.fm.is_running(b.id))
        self.assertFalse(self._eintrag(fern)["aktiv"])

    def test_flash_laeuft_nur_solange_gehalten(self):
        a, b = self._efx("WEB08 FA"), self._efx("WEB08 FB")
        geklickt = self._taste(ButtonAction.FUNCTION_FLASH, a.id, 10)
        fern = self._taste(ButtonAction.FUNCTION_FLASH, b.id, 100)

        _klick(geklickt, release=False)
        self.assertTrue(self.fern.aktion(fern.widget_id, "druecken")["ok"])
        self.assertTrue(self.fm.is_running(a.id))
        self.assertTrue(self.fm.is_running(b.id))
        self.assertTrue(self._eintrag(fern)["gedrueckt"])
        self.assertTrue(fern._pressed)

        _klick(geklickt, press=False)
        self.assertTrue(self.fern.aktion(fern.widget_id, "loslassen")["ok"])
        self.assertFalse(self.fm.is_running(a.id))
        self.assertFalse(self.fm.is_running(b.id))
        self.assertFalse(self._eintrag(fern)["gedrueckt"])

    def test_doppeltes_druecken_loest_nicht_zweimal_aus(self):
        # Ein wiederholt gesendeter Befehl (Funkloch, doppelter Tipp) darf ein
        # Toggle nicht gleich wieder ausschalten.
        a = self._efx("WEB08 D")
        fern = self._taste(fid=a.id)
        self.fern.aktion(fern.widget_id, "druecken")
        r = self.fern.aktion(fern.widget_id, "druecken")
        self.assertTrue(r["ok"])
        self.assertTrue(self.fm.is_running(a.id))
        self.fern.aktion(fern.widget_id, "loslassen")
        self.fern.aktion(fern.widget_id, "loslassen")
        self.assertTrue(self.fm.is_running(a.id))

    def test_solo_frame_gilt_auch_fuer_die_fernausloesung(self):
        a, b = self._efx("WEB08 SA"), self._efx("WEB08 SB")
        frame = self.canvas._add_widget("VCFrame", QPoint(200, 10))
        frame.set_solo(True)
        ta = self._taste(fid=a.id, x=8, eltern=frame)
        tb = self._taste(fid=b.id, x=90, eltern=frame)

        self.fern.aktion(ta.widget_id, "umschalten")
        self.assertTrue(self.fm.is_running(a.id))
        self.fern.aktion(tb.widget_id, "umschalten")
        self.assertFalse(self.fm.is_running(a.id))
        self.assertTrue(self.fm.is_running(b.id))

    def test_exklusiv_stoppt_die_anderen_wie_ein_klick(self):
        a, b, c = self._efx("WEB08 EA"), self._efx("WEB08 EB"), self._efx("WEB08 EC")
        self.fm.start(a.id)
        geklickt = self._taste(fid=b.id, x=10)
        geklickt.exclusive = True
        _klick(geklickt)
        nach_klick = (self.fm.is_running(a.id), self.fm.is_running(b.id))

        self.fm.stop_all()
        self.fm.start(a.id)
        fern = self._taste(fid=c.id, x=100)
        fern.exclusive = True
        self.fern.aktion(fern.widget_id, "umschalten")
        nach_fern = (self.fm.is_running(a.id), self.fm.is_running(c.id))

        self.assertEqual(nach_fern, nach_klick)
        self.assertEqual(nach_fern, (False, True))

    def test_widget_auf_anderer_bank_ist_erreichbar(self):
        # Konzept A: "auch fuer Elemente auf einer anderen Bank".
        a = self._efx("WEB08 Bank")
        fern = self._taste(fid=a.id)
        fern.bank = 3
        self.canvas.set_active_bank(0)
        self.assertFalse(self.canvas.on_active_bank(fern))
        self.assertTrue(self.fern.aktion(fern.widget_id, "umschalten")["ok"])
        self.assertTrue(self.fm.is_running(a.id))

    def test_zusatzaktionen_laufen_mit(self):
        a, b = self._efx("WEB08 Z1"), self._efx("WEB08 Z2")
        fern = self._taste(fid=a.id)
        fern.actions = [{"type": "function", "function_id": b.id, "mode": "on"}]
        self.fern.aktion(fern.widget_id, "umschalten")
        self.assertTrue(self.fm.is_running(a.id))
        self.assertTrue(self.fm.is_running(b.id))

    def test_bearbeiten_modus_sperrt_die_fernausloesung_nicht(self):
        # Wie MIDI und Tastatur: der Bearbeiten-Modus betrifft nur die Maus.
        a = self._efx("WEB08 Edit")
        fern = self._taste(fid=a.id)
        self.canvas.set_edit_mode(True)
        try:
            self.assertTrue(self.fern.aktion(fern.widget_id, "umschalten")["ok"])
            self.assertTrue(self.fm.is_running(a.id))
        finally:
            self.canvas.set_edit_mode(False)


class BlackoutTest(_Basis):
    """Blackout verhaelt sich wie an der Taste — und damit wie im bestehenden
    Web-Remote (``/api/blackout`` setzt UND hebt auf)."""

    def test_globaler_blackout_gehalten(self):
        geklickt = self._taste(ButtonAction.BLACKOUT, x=10)
        fern = self._taste(ButtonAction.BLACKOUT, x=100)
        om = self.state.output_manager

        _klick(geklickt, release=False)
        nach_klick_druck = om.blackout
        _klick(geklickt, press=False)
        nach_klick_los = om.blackout

        self.fern.aktion(fern.widget_id, "druecken")
        nach_fern_druck = om.blackout
        self.fern.aktion(fern.widget_id, "loslassen")
        nach_fern_los = om.blackout

        self.assertEqual((nach_fern_druck, nach_fern_los),
                         (nach_klick_druck, nach_klick_los))
        self.assertEqual((nach_fern_druck, nach_fern_los), (True, False))

    def test_blackout_mit_ziel_trifft_nur_das_ziel(self):
        fern = self._taste(ButtonAction.BLACKOUT)
        fern.blackout_fids = [987654]
        om = self.state.output_manager
        with mock.patch.object(self.state, "set_target_blackout") as setzen, \
                mock.patch.object(self.state, "clear_target_blackout") as loesen:
            self.fern.aktion(fern.widget_id, "druecken")
            setzen.assert_called_once_with(id(fern), [987654], [])
            self.assertFalse(om.blackout)       # NICHT der globale Blackout
            self.fern.aktion(fern.widget_id, "loslassen")
            loesen.assert_called_once_with(id(fern))


class _FakeLaser:
    def __init__(self, armed=False):
        self.armed = armed
        self.rufe = []

    def set_armed(self, on):
        self.rufe.append(("armed", bool(on)))
        self.armed = bool(on)

    def estop_all(self):
        self.rufe.append(("estop",))

    def clear_estop_all(self):
        self.rufe.append(("clear_estop",))


class LaserSicherheitTest(_Basis):
    """Ein Laser wird nur AM PULT scharf geschaltet. Aus der Ferne geht nur die
    sichere Richtung: unscharf und NOT-AUS."""

    def _mit_laser(self, laser):
        p1 = mock.patch.object(self.state, "ensure_laser_output", lambda: laser)
        p2 = mock.patch.object(self.state, "_laser_output", laser, create=True)
        p1.start()
        p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def test_scharf_schalten_wird_abgelehnt(self):
        laser = _FakeLaser(armed=False)
        self._mit_laser(laser)
        fern = self._taste(ButtonAction.LASER_ARM)
        for aktion in ("druecken", "umschalten"):
            r = self.fern.aktion(fern.widget_id, aktion)
            self.assertFalse(r["ok"], r)
            self.assertEqual(r["fehler"], "nur_am_pult")
        self.assertFalse(laser.armed)
        self.assertEqual(laser.rufe, [])
        self.assertFalse(fern._pressed)

    def test_gegenprobe_der_klick_am_pult_schaltet_scharf(self):
        # Ohne diese Probe koennte der Test oben auch gruen sein, weil die
        # Taste gar nichts tut.
        laser = _FakeLaser(armed=False)
        self._mit_laser(laser)
        geklickt = self._taste(ButtonAction.LASER_ARM)
        _klick(geklickt)
        self.assertTrue(laser.armed)

    def test_unscharf_schalten_ist_erlaubt(self):
        laser = _FakeLaser(armed=True)
        self._mit_laser(laser)
        fern = self._taste(ButtonAction.LASER_ARM)
        r = self.fern.aktion(fern.widget_id, "umschalten")
        self.assertTrue(r["ok"], r)
        self.assertFalse(laser.armed)

    def test_not_aus_ist_ausloesbar_und_hebt_nichts_auf(self):
        laser = _FakeLaser(armed=True)
        self._mit_laser(laser)
        fern = self._taste(ButtonAction.LASER_ESTOP)
        r = self.fern.aktion(fern.widget_id, "umschalten")
        self.assertTrue(r["ok"], r)
        self.assertFalse(laser.armed)
        self.assertIn(("estop",), laser.rufe)
        self.assertNotIn(("armed", True), laser.rufe)
        # ein zweiter Druck schaltet nicht wieder scharf
        self.fern.aktion(fern.widget_id, "umschalten")
        self.assertFalse(laser.armed)

    def test_laser_muster_ist_nicht_fernbedienbar(self):
        fern = self._taste(ButtonAction.LASER_PATTERN)
        fern.laser_palette = "Tunnel"
        self.assertEqual([e for e in self.fern.widgets() if e["id"] == fern.widget_id], [])
        r = self.fern.aktion(fern.widget_id, "umschalten")
        self.assertFalse(r["ok"])
        self.assertEqual(r["fehler"], "typ_nicht_erlaubt")


# ── Fader ────────────────────────────────────────────────────────────────────

class FaderTest(_Basis):

    def _fader(self, x=10, modus=SliderMode.GRANDMASTER):
        w = self.canvas._add_widget("VCSlider", QPoint(x, 10))
        w.mode = modus
        return w

    def tearDown(self):
        self.state.output_manager.set_grand_master(1.0)
        super().tearDown()

    def test_setzen_wirkt_wie_der_griff_am_fader(self):
        om = self.state.output_manager
        griff = self._fader(10)
        griff.value = 128                     # derselbe Setter wie Maus/Rad/MIDI
        nach_griff = om.grand_master

        om.set_grand_master(1.0)
        fern = self._fader(100)
        r = self.fern.aktion(fern.widget_id, "setzen", 128)
        self.assertTrue(r["ok"], r)
        self.assertEqual(fern.value, 128)
        self.assertAlmostEqual(om.grand_master, nach_griff, places=6)
        self.assertEqual(self._eintrag(fern)["wert"], 128)
        self.assertEqual(self._eintrag(fern)["typ"], "fader")

    def test_begrenzung_und_umkehr_des_faders_gelten(self):
        om = self.state.output_manager
        fern = self._fader()
        fern.range_min, fern.range_max, fern.invert = 0, 127, False
        self.fern.aktion(fern.widget_id, "setzen", 255)
        self.assertAlmostEqual(om.grand_master, 127 / 255.0, places=3)

    def test_wert_wird_wie_am_fader_geklemmt(self):
        fern = self._fader(modus=SliderMode.LEVEL)
        with mock.patch.object(type(fern), "_apply"):
            self.assertTrue(self.fern.aktion(fern.widget_id, "setzen", 999)["ok"])
            self.assertEqual(fern.value, 255)
            self.assertTrue(self.fern.aktion(fern.widget_id, "setzen", -5)["ok"])
            self.assertEqual(fern.value, 0)
            self.assertTrue(self.fern.aktion(fern.widget_id, "setzen", 99.6)["ok"])
            self.assertEqual(fern.value, 100)

    def test_kaputter_wert_wird_abgelehnt_und_aendert_nichts(self):
        fern = self._fader(modus=SliderMode.LEVEL)
        with mock.patch.object(type(fern), "_apply") as anwenden:
            fern._value = 77
            for wert in (None, "voll", "12", True, float("nan"), float("inf"),
                         [1], {"a": 1}):
                r = self.fern.aktion(fern.widget_id, "setzen", wert)
                self.assertFalse(r["ok"], wert)
                self.assertEqual(r["fehler"], "wert_ungueltig")
            self.assertEqual(fern.value, 77)
            anwenden.assert_not_called()

    def test_taste_kennt_setzen_nicht_und_fader_kein_druecken(self):
        taste = self._taste()
        fader = self._fader(100, SliderMode.LEVEL)
        self.assertEqual(self.fern.aktion(taste.widget_id, "setzen", 5)["fehler"],
                         "aktion_unbekannt")
        self.assertEqual(self.fern.aktion(fader.widget_id, "druecken")["fehler"],
                         "aktion_unbekannt")


# ── Cueliste ─────────────────────────────────────────────────────────────────

class _FakeCue:
    def __init__(self, nummer, name):
        self.number = nummer
        self.label = name


class _FakeStack:
    name = "Hauptshow"

    def __init__(self):
        self.cues = [_FakeCue(1.0, "Einlass"), _FakeCue(2.0, "Strophe"),
                     _FakeCue(3.0, "Refrain")]
        self.current_index = 1


class _FakeExecutor:
    def __init__(self):
        self.stack = _FakeStack()
        self.rufe = []

    def press_btn(self, was):
        self.rufe.append(was)


class CuelisteTest(_Basis):

    def _liste(self):
        w = self.canvas._add_widget("VCCueList", QPoint(10, 10))
        ex = _FakeExecutor()
        w._executor = lambda: ex
        return w, ex

    def test_go_back_stop_nehmen_den_weg_der_knoepfe(self):
        w, ex = self._liste()
        w._btn_go.click()
        w._btn_back.click()
        w._btn_stop.click()
        per_klick, ex.rufe = list(ex.rufe), []

        for aktion in ("go", "back", "stop"):
            self.assertTrue(self.fern.aktion(w.widget_id, aktion)["ok"])
        self.assertEqual(ex.rufe, per_klick)
        self.assertEqual(ex.rufe, ["go", "back", "stop"])

    def test_zustand_nennt_laufende_und_naechste_cue(self):
        w, _ex = self._liste()
        e = self._eintrag(w)
        self.assertEqual(e["typ"], "cueliste")
        self.assertEqual(e["liste"], "Hauptshow")
        self.assertEqual(e["anzahl"], 3)
        self.assertEqual(e["cue_index"], 1)
        self.assertEqual(e["cue"], {"nummer": 2.0, "name": "Strophe"})
        self.assertEqual(e["naechste"], {"nummer": 3.0, "name": "Refrain"})

    def test_cueliste_ohne_liste_ist_trotzdem_auskunftsfaehig(self):
        w = self.canvas._add_widget("VCCueList", QPoint(10, 10))
        w._executor = lambda: None
        e = self._eintrag(w)
        self.assertIsNone(e["liste"])
        self.assertIsNone(e["cue"])
        self.assertTrue(self.fern.aktion(w.widget_id, "go")["ok"])


# ── Liste und Ablehnungen ────────────────────────────────────────────────────

class ListeUndAblehnungTest(_Basis):

    def test_liste_nennt_nur_fernbedienbare_widgets(self):
        taste = self._taste(beschriftung="Strobe")
        fader = self.canvas._add_widget("VCSlider", QPoint(100, 10))
        liste = self.canvas._add_widget("VCCueList", QPoint(200, 10))
        self.canvas._add_widget("VCLabel", QPoint(500, 10))
        self.canvas._add_widget("VCXYPad", QPoint(600, 10))
        frame = self.canvas._add_widget("VCFrame", QPoint(10, 400))
        innen = self._taste(x=8, eltern=frame, beschriftung="Innen")

        eintraege = self.fern.widgets()
        self.assertEqual({e["id"] for e in eintraege},
                         {taste.widget_id, fader.widget_id, liste.widget_id,
                          innen.widget_id})
        e = self._eintrag(taste)
        self.assertEqual(e["typ"], "taste")
        self.assertEqual(e["beschriftung"], "Strobe")
        self.assertEqual(e["farbe"], taste._bg_color.name())
        self.assertEqual(e["textfarbe"], taste._fg_color.name())
        self.assertEqual(e["aktionen"], ["druecken", "loslassen", "umschalten"])
        self.assertEqual(self._eintrag(fader)["aktionen"], ["setzen"])
        self.assertEqual(self._eintrag(liste)["aktionen"], ["go", "back", "stop"])
        # der Kasten selbst ist kein Bedienelement, sein Inhalt schon
        self.assertEqual(self._eintrag(innen)["gruppe"], frame.caption)

    def test_liste_ist_json_tauglich(self):
        import json
        self._taste()
        self.canvas._add_widget("VCSlider", QPoint(100, 10))
        self.canvas._add_widget("VCCueList", QPoint(200, 10))
        json.dumps(self.fern.widgets())

    def test_unbekannte_kennung(self):
        for kennung in ("wgibtesnicht", "", None, 5, "../x", "a" * 500):
            r = self.fern.aktion(kennung, "umschalten")
            self.assertFalse(r["ok"])
            self.assertEqual(r["fehler"], "unbekannte_kennung")

    def test_nicht_erlaubter_typ(self):
        label = self.canvas._add_widget("VCLabel", QPoint(10, 10))
        frame = self.canvas._add_widget("VCFrame", QPoint(200, 10))
        for w in (label, frame):
            r = self.fern.aktion(w.widget_id, "umschalten")
            self.assertEqual(r, {"ok": False, "fehler": "typ_nicht_erlaubt"})

    def test_unbekannte_aktion(self):
        taste = self._taste()
        for aktion in ("explodieren", "", None, 7, "_trigger", "deleteLater"):
            r = self.fern.aktion(taste.widget_id, aktion)
            self.assertEqual(r["fehler"], "aktion_unbekannt")

    def test_fehler_im_widget_wird_zur_ablehnung(self):
        taste = self._taste()
        with mock.patch.object(type(taste), "_trigger", side_effect=RuntimeError("bumm")):
            r = self.fern.aktion(taste.widget_id, "druecken")
        self.assertEqual(r, {"ok": False, "fehler": "fehler"})

    def test_geloeschtes_widget_ist_danach_unbekannt(self):
        taste = self._taste()
        kennung = taste.widget_id
        self.canvas._remove_widget(taste)
        _app.processEvents()
        self.assertEqual(self.fern.aktion(kennung, "umschalten")["fehler"],
                         "unbekannte_kennung")


# ── Uebergabe in den UI-Thread ───────────────────────────────────────────────

class ThreadTest(_Basis):

    def _im_fremden_thread(self, fn, pumpen=True, warte_s=5.0):
        ergebnis = {}

        def lauf():
            ergebnis["wert"] = fn()

        t = threading.Thread(target=lauf, daemon=True)
        t.start()
        ende = time.monotonic() + warte_s
        while t.is_alive() and time.monotonic() < ende:
            if pumpen:
                _app.processEvents()
            time.sleep(0.005)
        t.join(timeout=0.1)
        self.assertFalse(t.is_alive(), "Aufruf aus dem Web-Thread kam nicht zurueck")
        return ergebnis.get("wert")

    def test_aktion_aus_fremdem_thread_laeuft_im_ui_thread(self):
        a = self._efx("WEB08 Thread")
        taste = self._taste(fid=a.id)
        gesehen = []
        original = type(taste)._trigger

        def spion(selbst, press):
            gesehen.append(threading.get_ident())
            return original(selbst, press)

        with mock.patch.object(type(taste), "_trigger", spion):
            r = self._im_fremden_thread(
                lambda: self.fern.aktion(taste.widget_id, "umschalten"))
        self.assertTrue(r["ok"], r)
        self.assertEqual(set(gesehen), {threading.get_ident()})
        self.assertTrue(self.fm.is_running(a.id))

    def test_liste_aus_fremdem_thread(self):
        taste = self._taste()
        liste = self._im_fremden_thread(self.fern.widgets)
        self.assertEqual([e["id"] for e in liste], [taste.widget_id])

    def test_haengender_ui_thread_ergibt_ablehnung_und_keine_spaete_aktion(self):
        # Antwortet die Oberflaeche nicht rechtzeitig, bekommt das Handy "nicht
        # ausgefuehrt" — dann darf die Taste auch nicht Sekunden spaeter doch
        # noch ausloesen.
        a = self._efx("WEB08 Spaet")
        taste = self._taste(fid=a.id)
        self.fern.ZEITLIMIT_S = 0.2
        r = self._im_fremden_thread(
            lambda: self.fern.aktion(taste.widget_id, "umschalten"), pumpen=False)
        self.assertEqual(r, {"ok": False, "fehler": "zeitueberschreitung"})
        _app.processEvents()
        _app.processEvents()
        self.assertFalse(self.fm.is_running(a.id))

    def test_zerstoerte_konsole_ergibt_ablehnung(self):
        fern = self.fern
        canvas2 = VCCanvas()
        fern2 = VCFernbedienung(canvas2)
        canvas2.close()
        import shiboken6
        shiboken6.delete(canvas2)
        self.assertEqual(fern2.widgets(), [])
        self.assertEqual(fern2.aktion("wx", "umschalten")["fehler"], "keine_konsole")
        self.assertIsNotNone(fern)


# ── Web-Schnittstelle ────────────────────────────────────────────────────────

@unittest.skipUnless(HAS_FLASK, "Flask/flask-socketio nicht installiert")
class WebSchnittstelleTest(_Basis):

    def setUp(self):
        super().setUp()
        import src.web.app as webapp
        self.webapp = webapp
        remote_settings.set_vc_remote_enabled(False)
        vc_remote.registriere(self.fern)
        self.app, _sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.app.config["LIGHTOS_REMOTE_TOKEN"] = "geheim123"
        self.client = self.app.test_client()

    def tearDown(self):
        vc_remote.abmelden(self.fern)
        remote_settings.set_vc_remote_enabled(False)
        super().tearDown()

    def _anmelden(self):
        self.assertEqual(self.client.get("/?k=geheim123").status_code, 200)

    def _auf_handy_seite(self):
        """WEB-09: die Schnittstelle bedient nur, was auf einer Handy-Seite
        liegt. Diese Tests pruefen die Fernausloesung selbst — also alles
        Fernbedienbare freigeben (die Freigabe prueft test_web09_…)."""
        self.canvas.handy_konsole_automatisch_fuellen()

    def _aktion(self, kennung, **daten):
        return self.client.post(f"/api/vc/widget/{kennung}/aktion", json=daten)

    def test_standard_ist_aus(self):
        self.assertFalse(remote_settings.DEFAULTS["vc_remote_enabled"])
        self.assertFalse(remote_settings.is_vc_remote_enabled())

    def test_ohne_schluessel_403(self):
        remote_settings.set_vc_remote_enabled(True)
        a = self._efx("WEB08 Web403")
        taste = self._taste(fid=a.id)
        self.assertEqual(self.client.get("/api/vc/widgets").status_code, 403)
        r = self._aktion(taste.widget_id, aktion="umschalten")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(self.fm.is_running(a.id))
        # falscher Schluessel hilft nicht
        self.client.get("/?k=falsch")
        self.assertEqual(self.client.get("/api/vc/widgets").status_code, 403)

    def test_abgeschaltet_liefert_leere_liste_und_fuehrt_nichts_aus(self):
        a = self._efx("WEB08 WebAus")
        taste = self._taste(fid=a.id)
        self._anmelden()
        r = self.client.get("/api/vc/widgets")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ok": True, "aktiv": False, "widgets": []})
        r = self._aktion(taste.widget_id, aktion="umschalten")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json(), {"ok": False, "fehler": "abgeschaltet"})
        self.assertFalse(self.fm.is_running(a.id))

    def test_eingeschaltet_liste_und_aktion(self):
        remote_settings.set_vc_remote_enabled(True)
        a = self._efx("WEB08 WebAn")
        taste = self._taste(fid=a.id, beschriftung="Strobe")
        self.canvas._add_widget("VCLabel", QPoint(300, 10))
        self._auf_handy_seite()
        self._anmelden()

        r = self.client.get("/api/vc/widgets")
        self.assertEqual(r.status_code, 200)
        daten = r.get_json()
        self.assertTrue(daten["aktiv"])
        self.assertEqual([w["id"] for w in daten["widgets"]], [taste.widget_id])
        self.assertEqual(daten["widgets"][0]["beschriftung"], "Strobe")

        r = self._aktion(taste.widget_id, aktion="umschalten")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertTrue(self.fm.is_running(a.id))
        # die Antwort traegt den neuen Zustand — das Handy muss nicht nachfragen
        self.assertTrue(r.get_json()["widget"]["aktiv"])

    def test_fader_ueber_die_schnittstelle(self):
        remote_settings.set_vc_remote_enabled(True)
        fader = self.canvas._add_widget("VCSlider", QPoint(10, 10))
        fader.mode = SliderMode.LEVEL
        self._auf_handy_seite()
        self._anmelden()
        with mock.patch.object(type(fader), "_apply"):
            r = self._aktion(fader.widget_id, aktion="setzen", wert=200)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(fader.value, 200)
            self.assertEqual(r.get_json()["widget"]["wert"], 200)
            r = self._aktion(fader.widget_id, aktion="setzen", wert="viel")
            self.assertEqual(r.status_code, 400)
            self.assertEqual(fader.value, 200)

    def test_ablehnungen_haben_passende_statuscodes(self):
        remote_settings.set_vc_remote_enabled(True)
        taste = self._taste()
        label = self.canvas._add_widget("VCLabel", QPoint(300, 10))
        self._auf_handy_seite()
        self._anmelden()
        self.assertEqual(self._aktion("wgibtesnicht", aktion="umschalten").status_code, 404)
        self.assertEqual(self._aktion(label.widget_id, aktion="umschalten").status_code, 403)
        self.assertEqual(self._aktion(taste.widget_id, aktion="explodieren").status_code, 400)
        self.assertEqual(self._aktion(taste.widget_id).status_code, 400)
        # kaputter Rumpf: kein 500
        r = self.client.post(f"/api/vc/widget/{taste.widget_id}/aktion",
                             data="kein json", content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/vc/widget/{taste.widget_id}/aktion",
                             json=["liste", "statt", "objekt"])
        self.assertEqual(r.status_code, 400)

    def test_ohne_konsole_gibt_es_eine_saubere_antwort(self):
        remote_settings.set_vc_remote_enabled(True)
        vc_remote.abmelden(self.fern)
        self._anmelden()
        r = self.client.get("/api/vc/widgets")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["widgets"], [])
        r = self._aktion("wirgendwas", aktion="umschalten")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["fehler"], "keine_konsole")

    def test_bestehende_befehle_bleiben_unveraendert(self):
        # Die feste Web-Remote-Seite haengt nicht an der neuen Einstellung.
        self._anmelden()
        self.assertEqual(self.client.get("/api/status").status_code, 200)
        r = self.client.post("/api/blackout", json={"enabled": True})
        self.assertEqual(r.get_json(), {"ok": True, "blackout": True})
        self.assertTrue(self.state.output_manager.blackout)
        self.client.post("/api/blackout", json={"enabled": False})
        self.assertFalse(self.state.output_manager.blackout)

    def test_token_wechsel_sperrt_auch_die_neue_schnittstelle(self):
        remote_settings.set_vc_remote_enabled(True)
        self._anmelden()
        self.assertEqual(self.client.get("/api/vc/widgets").status_code, 200)
        remote_settings.regenerate_token()
        self.assertEqual(self.client.get("/api/vc/widgets").status_code, 403)


class RegistrierungTest(_Basis):

    def test_ansicht_meldet_ihre_konsole_an(self):
        from src.ui.views.virtual_console_view import VirtualConsoleView
        view = VirtualConsoleView()
        try:
            b = vc_remote.bruecke()
            self.assertIsNotNone(b)
            self.assertIs(b.canvas(), view._canvas)
        finally:
            view.close()
            view.deleteLater()

    def test_abmelden_einer_fremden_bruecke_laesst_die_aktive_stehen(self):
        vc_remote.registriere(self.fern)
        canvas2 = VCCanvas()
        try:
            fremd = VCFernbedienung(canvas2)
            vc_remote.abmelden(fremd)
            self.assertIs(vc_remote.bruecke(), self.fern)
        finally:
            vc_remote.abmelden(self.fern)
            canvas2.close()
            canvas2.deleteLater()


if __name__ == "__main__":
    unittest.main()


# ── Laser-NOT-AUS: aus der Ferne nur ausloesbar, nie aufhebbar ───────────────
#
# Am Pult loest ein bewusst gesetzter Laser-Wert (Shutter, Musterbank, Gobo,
# Macro) den NOT-AUS wieder (``AppState.set_programmer_value``). Ein Fader oder
# eine Snap-Taste mit solchen Werten taete das auch vom Handy aus — die feste
# Web-Remote-Seite kann das nicht (sie schreibt in die Eingangs-Schicht, die
# Aus-Maske bleibt). Die Fernausloesung darf hier nicht mehr koennen.

class NotAusKernTest(unittest.TestCase):
    """Die Sperre selbst, am echten Latch (Aufbau wie test_laser_dmx_estop)."""

    def setUp(self):
        import importlib.util
        import src.core.app_state as A
        pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "test_laser_dmx_estop.py")
        spec = importlib.util.spec_from_file_location("_las_estop_helfer", pfad)
        self.helfer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helfer)
        self.A = A
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: self.helfer._CHANNELS[fx.fid]
        self.st = self.helfer._make_state()

    def tearDown(self):
        self.A.get_channels_for_patched = self._orig

    def test_im_fern_kontext_bleibt_der_not_aus_stehen(self):
        self.st.set_laser_estop(True)
        with self.A.laser_notaus_nicht_loesbar():
            for attr in ("shutter", "laser_bank", "gobo_wheel", "gobo_wheel#1"):
                self.st.set_programmer_value(7, attr, 200)
                self.assertTrue(self.st.laser_estop_active, attr)
        # der Wert ist geschrieben, die Ausgabe bleibt trotzdem dunkel
        self.assertEqual(self.st.programmer[7]["shutter"], 200)
        self.st._render_frame(0.02)
        for adresse in (10, 11, 12, 13):
            self.assertEqual(self.st.universes[1].get_channel(adresse), 0)

    def test_gegenprobe_am_pult_loest_der_wert_weiterhin(self):
        self.st.set_laser_estop(True)
        with self.A.laser_notaus_nicht_loesbar():
            pass                            # Kontext verlassen -> Sperre weg
        self.assertFalse(self.A.laser_notaus_loesen_gesperrt())
        self.st.set_programmer_value(7, "shutter", 200)
        self.assertFalse(self.st.laser_estop_active)

    def test_sperre_gilt_nur_im_eigenen_thread_und_verschachtelt(self):
        gesehen = []
        with self.A.laser_notaus_nicht_loesbar():
            with self.A.laser_notaus_nicht_loesbar():
                pass
            self.assertTrue(self.A.laser_notaus_loesen_gesperrt())
            t = threading.Thread(
                target=lambda: gesehen.append(self.A.laser_notaus_loesen_gesperrt()))
            t.start()
            t.join(5)
        self.assertEqual(gesehen, [False])
        self.assertFalse(self.A.laser_notaus_loesen_gesperrt())

    def test_sperre_faellt_auch_nach_einer_ausnahme(self):
        with self.assertRaises(ValueError):
            with self.A.laser_notaus_nicht_loesbar():
                raise ValueError("x")
        self.assertFalse(self.A.laser_notaus_loesen_gesperrt())


class NotAusFernTest(_Basis):
    """Die Fernausloesung setzt die Sperre — der Klick am Pult nicht."""

    def setUp(self):
        super().setUp()
        import types
        from src.core.app_state import laser_notaus_loesen_gesperrt
        self.gesehen = []
        self._alt = {}
        for name in ("set_programmer_value", "get_patched_fixtures"):
            self._alt[name] = self.state.__dict__.get(name, None)
        self.state.get_patched_fixtures = lambda: [types.SimpleNamespace(fid=7)]
        self.state.set_programmer_value = (
            lambda *a, **k: self.gesehen.append(laser_notaus_loesen_gesperrt()))

    def tearDown(self):
        for name, alt in self._alt.items():
            if alt is None:
                self.state.__dict__.pop(name, None)
            else:
                setattr(self.state, name, alt)
        super().tearDown()

    def _shutter_fader(self, x):
        w = self.canvas._add_widget("VCSlider", QPoint(x, 10))
        w.mode = SliderMode.PROGRAMMER
        w.programmer_attr = "shutter"
        w.programmer_scope = "all"
        return w

    def test_fader_aus_der_ferne_schreibt_unter_der_sperre(self):
        fern = self._shutter_fader(10)
        self.gesehen.clear()
        r = self.fern.aktion(fern.widget_id, "setzen", 200)
        self.assertTrue(r["ok"], r)
        self.assertTrue(self.gesehen, "der Fader hat nichts geschrieben")
        self.assertTrue(all(self.gesehen), self.gesehen)

    def test_gegenprobe_der_griff_am_pult_ist_nicht_gesperrt(self):
        griff = self._shutter_fader(10)
        self.gesehen.clear()
        griff.value = 200
        self.assertTrue(self.gesehen, "der Fader hat nichts geschrieben")
        self.assertFalse(any(self.gesehen), self.gesehen)

    def _taste_mit_spaeter_zusatzaktion(self, x):
        from src.core.app_state import laser_notaus_loesen_gesperrt
        w = self._taste(ButtonAction.CLEAR, x=x)
        w.actions = [{"type": "clear", "delay": 0.02}]
        spaet = []
        w._execute_extra = lambda e: spaet.append(laser_notaus_loesen_gesperrt())
        return w, spaet

    def _warte(self, liste):
        from PySide6.QtTest import QTest
        for _ in range(100):
            if liste:
                return
            QTest.qWait(10)

    def test_verzoegerte_zusatzaktion_aus_der_ferne_bleibt_gesperrt(self):
        w, spaet = self._taste_mit_spaeter_zusatzaktion(10)
        r = self.fern.aktion(w.widget_id, "umschalten")
        self.assertTrue(r["ok"], r)
        self.assertEqual(spaet, [], "die Zusatzaktion sollte verzoegert laufen")
        self._warte(spaet)
        self.assertEqual(spaet, [True])

    def test_gegenprobe_verzoegerte_zusatzaktion_am_pult(self):
        w, spaet = self._taste_mit_spaeter_zusatzaktion(10)
        w._taste(True)
        w._taste(False)
        self._warte(spaet)
        self.assertEqual(spaet, [False])
