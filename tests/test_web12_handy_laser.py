"""WEB-12: Sicherheits-Korrekturen der Handy-Konsole aus dem Bedientest QA-96 —
Teil Konsole.

* **Kein Weg vom Handy zum Laser ohne den Schalter (QA96-05):** alle
  Widget-Arten (Taste, Fader, Cueliste) mit Laser-Inhalt, auch nachtraeglich
  umgestellt, auch ueber „Automatisch fuellen“, ueber HTTP und Socket; dazu die
  feste Fernbedienung (GO, Executor, Roh-DMX) und der Grand Master.
* **Halter je Verbindung (Codex zu #1030/#1039/#1041):** ein Handy laesst nur
  los, was es selbst haelt.
* **Loeschen/Laden laesst Gehaltenes los (Codex zu #1039).**
* **Spaete Antwort der Oberflaeche (Codex zu #1028):** kein „Fehler“, waehrend
  die Aktion noch laeuft.
* **Am Handy sichtbar (QA96-19/37):** NOT-AUS und verlorene Ziele.
"""
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web12l_")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core import handy_seiten as hs  # noqa: E402
from src.core.app_state import get_state  # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction  # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas  # noqa: E402
from src.ui.virtualconsole import vc_fernbedienung as vf  # noqa: E402
from src.ui.virtualconsole.vc_fernbedienung import VCFernbedienung  # noqa: E402
from src.ui.virtualconsole.vc_slider import SliderMode  # noqa: E402
from src.web import fern_pult, remote_settings, vc_remote  # noqa: E402

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

_app = QApplication.instance() or QApplication([])

LASER = 9601            # fid eines (vorgetaeuschten) Lasers im Patch
LICHT = 9602            # fid eines gewoehnlichen Geraets
LASER_ADR = (1, 401)    # DMX-Adresse des Lasers


class _Cue:
    def __init__(self, nummer, werte):
        self.number = nummer
        self.label = f"Cue {nummer}"
        self.values = werte
        self.sub_stack_ref = None


class _Stack:
    name = "Liste"

    def __init__(self, fid):
        self.cues = [_Cue(1.0, {fid: {"intensity": 255}})]
        self.current_index = -1
        self.aktionen = []

    def go(self):
        self.aktionen.append("go")

    def back(self):
        self.aktionen.append("back")

    def stop(self):
        self.aktionen.append("stop")


class _Ex:
    def __init__(self, fid):
        self.stack = _Stack(fid)
        self.gedrueckt = []
        self.fader_value = 0.0

    def press_btn(self, was):
        self.gedrueckt.append(was)


class _Basis(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.fm = self.state.function_manager
        self.fm.stop_all()
        om = self.state.output_manager
        om.set_blackout(False)
        om.set_grand_master(1.0)
        # Laser im Patch vortaeuschen — dieselben Felder, die der NOT-AUS nutzt
        alt_fids = getattr(self.state, "_laser_fids", frozenset())
        alt_adr = getattr(self.state, "_laser_estop_addrs", {})
        self.state._laser_fids = frozenset({LASER})
        self.state._laser_estop_addrs = {LASER_ADR[0]: frozenset({LASER_ADR[1]})}
        self.addCleanup(setattr, self.state, "_laser_fids", alt_fids)
        self.addCleanup(setattr, self.state, "_laser_estop_addrs", alt_adr)
        self.canvas = VCCanvas()
        self.fern = VCFernbedienung(self.canvas)
        self._funktionen = []
        remote_settings.set_vc_remote_enabled(True)
        remote_settings.set_laser_vom_handy(False)
        vc_remote.registriere(self.fern)
        fern_pult.vergessen()

    def tearDown(self):
        vc_remote.alle_loslassen()
        vc_remote.abmelden(self.fern)
        vc_remote.setze_sender(None)
        remote_settings.set_vc_remote_enabled(False)
        remote_settings.set_laser_vom_handy(False)
        fern_pult.vergessen()
        self.fm.stop_all()
        om = self.state.output_manager
        om.loese_alle_halte_blackouts()
        om.set_blackout(False)
        om.set_grand_master(1.0)
        for f in self._funktionen:
            self.fm.remove(f.id)
        self.canvas.close()
        self.canvas.deleteLater()

    def _szene(self, fid, name):
        f = self.fm.new_scene(name)
        f.set_value(fid, 0, 255)
        self._funktionen.append(f)
        return f

    def _taste(self, aktion=ButtonAction.FUNCTION_TOGGLE, fid=None, x=10, text="T"):
        w = self.canvas._add_widget("VCButton", QPoint(x, 10))
        w.caption = text
        w.action = aktion
        w.function_id = fid
        return w

    def _fader(self, modus=SliderMode.LEVEL, x=200):
        w = self.canvas._add_widget("VCSlider", QPoint(x, 10))
        w.mode = modus
        return w

    def _liste(self, fid, x=400):
        w = self.canvas._add_widget("VCCueList", QPoint(x, 10))
        ex = _Ex(fid)
        w._executor = lambda: ex
        return w, ex

    def _auf_seite(self, *widgets):
        a = hs.seite_hinzufuegen(hs.leer(), "Test")
        for i, w in enumerate(widgets):
            a = hs.eintrag_setzen(a, 0, w.widget_id, i % 4, i // 4)
        self.canvas.setze_handy_seiten(a)

    def _aktion(self, w, aktion, wert=None):
        return self.fern.aktion(w.widget_id, aktion, wert, nur_handy_seiten=True)


# ── Laser: jede Widget-Art ───────────────────────────────────────────────────

class LaserJedeArtTest(_Basis):

    def _faelle(self):
        """(Name, Widget, Aktion, Wert, Pruefung „ist etwas passiert?“) — jeweils
        mit Laser-Inhalt."""
        laser_szene = self._szene(LASER, "WEB12 Laser")
        faelle = []
        t = self._taste(fid=laser_szene.id, x=10)
        faelle.append(("Taste Funktion an/aus", t, "umschalten", None,
                       lambda: self.fm.is_running(laser_szene.id)))
        fl = self._taste(ButtonAction.FUNCTION_FLASH, fid=laser_szene.id, x=60)
        faelle.append(("Taste Funktion gehalten", fl, "umschalten", None,
                       lambda: self.fm.is_running(laser_szene.id)))
        muster = self._taste(ButtonAction.LASER_PATTERN, x=110)
        muster.laser_palette = "Tunnel"
        faelle.append(("Taste Laser-Muster", muster, "umschalten", None, None))
        effekt = self._taste(ButtonAction.EFFECT_ACTION, x=160)
        faelle.append(("Taste Effekt-Aktion ohne Ziel", effekt, "umschalten", None, None))
        zusatz = self._taste(ButtonAction.TAP, x=210)
        zusatz.actions = [{"type": "function", "function_id": laser_szene.id,
                           "mode": "on"}]
        faelle.append(("Taste mit Zusatzaktion", zusatz, "umschalten", None,
                       lambda: self.fm.is_running(laser_szene.id)))
        level = self._fader(SliderMode.LEVEL, x=260)
        level.dmx_universe, level.dmx_channel = LASER_ADR
        faelle.append(("Fader auf Laser-Kanal", level, "setzen", 200,
                       lambda: level.value == 200))
        gm = self._fader(SliderMode.GRANDMASTER, x=310)
        faelle.append(("Fader Grand Master", gm, "setzen", 200, lambda: gm.value == 200))
        sub = self._fader(SliderMode.SUBMASTER, x=360)
        faelle.append(("Fader Submaster global", sub, "setzen", 200, lambda: sub.value == 200))
        prog = self._fader(SliderMode.PROGRAMMER, x=410)
        faelle.append(("Fader Programmer alle", prog, "setzen", 200, lambda: prog.value == 200))
        eff = self._fader(SliderMode.EFFECT_INTENSITY, x=460)
        eff.function_id = laser_szene.id
        faelle.append(("Fader Effekt-Intensitaet", eff, "setzen", 200, lambda: eff.value == 200))
        liste, ex = self._liste(LASER, x=510)
        faelle.append(("Cueliste mit Laser-Cue", liste, "go", None,
                       lambda: ex.gedrueckt == ["go"] or False))
        return faelle

    def test_ohne_schalter_ist_jede_art_gesperrt(self):
        faelle = self._faelle()
        self._auf_seite(*[f[1] for f in faelle])
        with mock.patch.object(type(faelle[0][1]), "_trigger") as taste_los, \
                mock.patch.object(type(faelle[5][1]), "_apply") as fader_los:
            for name, w, aktion, wert, _passiert in faelle:
                with self.subTest(name):
                    self.assertTrue(vf.laser_inhalt(w), name)
                    r = self._aktion(w, aktion, wert)
                    self.assertEqual(r, {"ok": False, "fehler": "laser_gesperrt"}, name)
            taste_los.assert_not_called()
            fader_los.assert_not_called()
        for name, w, _a, _w, passiert in faelle:
            if passiert is not None:
                self.assertFalse(passiert(), name)
        k = self.fern.konsole()
        for name, w, *_ in faelle:
            self.assertEqual(k["widgets"][w.widget_id]["gesperrt"], "laser", name)

    def test_mit_schalter_geht_es(self):
        faelle = self._faelle()
        self._auf_seite(*[f[1] for f in faelle])
        remote_settings.set_laser_vom_handy(True)
        with mock.patch.object(type(faelle[0][1]), "_trigger"), \
                mock.patch.object(type(faelle[5][1]), "_apply"):
            for name, w, aktion, wert, _p in faelle:
                with self.subTest(name):
                    self.assertTrue(self._aktion(w, aktion, wert)["ok"], name)
        self.assertIsNone(self.fern.konsole()["widgets"][faelle[0][1].widget_id]["gesperrt"])

    def test_ohne_laser_inhalt_bleibt_alles_frei(self):
        licht = self._szene(LICHT, "WEB12 Licht")
        t = self._taste(fid=licht.id)
        level = self._fader(SliderMode.LEVEL)
        level.dmx_universe, level.dmx_channel = 1, 77
        bpm = self._fader(SliderMode.BPM, x=300)
        liste, ex = self._liste(LICHT)
        notaus = self._taste(ButtonAction.LASER_ESTOP, x=600)
        dunkel = self._taste(ButtonAction.BLACKOUT, x=650)
        for w in (t, level, bpm, liste, notaus, dunkel):
            self.assertFalse(vf.laser_inhalt(w), type(w).__name__)
        self._auf_seite(t, liste)
        self.assertTrue(self._aktion(t, "umschalten")["ok"])
        self.assertTrue(self.fm.is_running(licht.id))
        self.assertTrue(self._aktion(liste, "go")["ok"])

    def test_ohne_laser_im_patch_ist_nichts_laser_ausser_dem_muster(self):
        self.state._laser_fids = frozenset()
        self.state._laser_estop_addrs = {}
        gm = self._fader(SliderMode.GRANDMASTER)
        muster = self._taste(ButtonAction.LASER_PATTERN)
        self.assertFalse(vf.laser_inhalt(gm))
        self.assertTrue(vf.laser_inhalt(muster))

    def test_loslassen_und_stop_gehen_immer(self):
        laser_szene = self._szene(LASER, "WEB12 Halt")
        remote_settings.set_laser_vom_handy(True)
        fl = self._taste(ButtonAction.FUNCTION_FLASH, fid=laser_szene.id)
        liste, ex = self._liste(LASER)
        self._auf_seite(fl, liste)
        self.assertTrue(vc_remote.halten("handy", fl.widget_id)["ok"])
        self.assertTrue(self.fm.is_running(laser_szene.id))
        remote_settings.set_laser_vom_handy(False)        # waehrend gehalten
        self.assertTrue(vc_remote.loslassen_von("handy", fl.widget_id)["ok"])
        self.assertFalse(self.fm.is_running(laser_szene.id))
        self.assertTrue(self._aktion(liste, "stop")["ok"])
        self.assertEqual(ex.gedrueckt, ["stop"])


class LaserNachtraeglichTest(_Basis):

    def test_taste_nachtraeglich_auf_laser_umgestellt(self):
        licht, laser = self._szene(LICHT, "WEB12 L1"), self._szene(LASER, "WEB12 L2")
        t = self._taste(fid=licht.id)
        self._auf_seite(t)
        self.assertTrue(self._aktion(t, "umschalten")["ok"])
        self._aktion(t, "umschalten")
        t.function_id = laser.id                         # am Pult umgestellt
        self.assertEqual(self._aktion(t, "umschalten")["fehler"], "laser_gesperrt")
        self.assertFalse(self.fm.is_running(laser.id))

    def test_szene_nachtraeglich_um_laser_erweitert(self):
        sz = self._szene(LICHT, "WEB12 Erweitert")
        t = self._taste(fid=sz.id)
        self._auf_seite(t)
        sz.set_value(LASER, 0, 255)                      # Laser in die Szene
        self.assertEqual(self._aktion(t, "umschalten")["fehler"], "laser_gesperrt")

    def test_laser_spaeter_gepatcht(self):
        sz = self._szene(LICHT, "WEB12 Spaet")
        t = self._taste(fid=sz.id)
        self._auf_seite(t)
        self.state._laser_fids = frozenset({LASER, LICHT})   # Geraet als Laser erkannt
        self.assertEqual(self._aktion(t, "umschalten")["fehler"], "laser_gesperrt")

    def test_fader_nachtraeglich_auf_laser_kanal(self):
        f = self._fader(SliderMode.LEVEL)
        f.dmx_universe, f.dmx_channel = 1, 77
        self._auf_seite(f)
        with mock.patch.object(type(f), "_apply"):
            self.assertTrue(self._aktion(f, "setzen", 10)["ok"])
            f.dmx_channel = LASER_ADR[1]
            self.assertEqual(self._aktion(f, "setzen", 200)["fehler"], "laser_gesperrt")
        self.assertEqual(f.value, 10)


class LaserAblegenTest(_Basis):

    def test_automatisch_fuellen_laesst_laser_weg(self):
        laser = self._szene(LASER, "WEB12 Auto")
        drauf = self._taste(text="Licht")
        weg = self._taste(fid=laser.id, x=100, text="Laser")
        muster = self._taste(ButtonAction.LASER_PATTERN, x=200)
        self.canvas.handy_konsole_automatisch_fuellen()
        frei = hs.freigegebene_kennungen(self.canvas.handy_seiten())
        self.assertIn(drauf.widget_id, frei)
        self.assertNotIn(weg.widget_id, frei)
        self.assertNotIn(muster.widget_id, frei)
        remote_settings.set_laser_vom_handy(True)
        self.canvas.handy_konsole_automatisch_fuellen()
        frei = hs.freigegebene_kennungen(self.canvas.handy_seiten())
        self.assertTrue({weg.widget_id, muster.widget_id} <= frei)

    def test_von_hand_ablegen_nur_mit_schalter(self):
        laser = self._szene(LASER, "WEB12 Hand")
        t = self._taste(fid=laser.id)
        ok, grund = self.canvas.handy_ablegen(t)
        self.assertFalse(ok)
        self.assertIn("Laser vom Handy erlauben", grund)
        remote_settings.set_laser_vom_handy(True)
        self.assertTrue(self.canvas.handy_ablegen(t)[0])


@unittest.skipUnless(HAS_FLASK, "flask / flask-socketio nicht installiert")
class LaserWebTest(_Basis):

    def setUp(self):
        super().setUp()
        import src.web.app as webapp
        self.webapp = webapp
        self.app, self.sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.app.config["LIGHTOS_REMOTE_TOKEN"] = "konsoleK1"
        self.client = self.app.test_client()
        self.client.get("/konsole?k=konsoleK1")

    def test_http_und_socket_gesperrt(self):
        laser = self._szene(LASER, "WEB12 Web")
        t = self._taste(fid=laser.id)
        f = self._fader(SliderMode.GRANDMASTER)
        self._auf_seite(t, f)
        r = self.client.post(f"/api/vc/widget/{t.widget_id}/aktion",
                             json={"aktion": "umschalten"})
        self.assertEqual((r.status_code, r.get_json()["fehler"]), (403, "laser_gesperrt"))
        sc = self.sio.test_client(self.app, flask_test_client=self.client)
        self.addCleanup(lambda: sc.is_connected() and sc.disconnect())
        for daten in ({"id": t.widget_id, "aktion": "umschalten"},
                      {"id": t.widget_id, "aktion": "druecken"},
                      {"id": f.widget_id, "aktion": "setzen", "wert": 255, "n": 1}):
            self.assertEqual(sc.emit("vc_aktion", daten, callback=True)["fehler"],
                             "laser_gesperrt", daten)
        self.assertFalse(self.fm.is_running(laser.id))
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_grand_master_aus_der_laser_zone_nur_wer_ihn_hineinzog(self):
        om = self.state.output_manager
        sc = self.sio.test_client(self.app, flask_test_client=self.client)
        self.addCleanup(lambda: sc.is_connected() and sc.disconnect())
        om.set_grand_master(0.0)                             # am Pult zugezogen
        r = sc.emit("vc_pult", {"gm": 255}, callback=True)
        self.assertEqual(r["fehler"], "laser_gesperrt")
        self.assertEqual(r["gm"], 0)
        self.assertEqual(om.grand_master, 0.0)
        # senken geht immer, und wer selbst hineinzog, darf wieder heraus
        om.set_grand_master(1.0)
        self.assertTrue(sc.emit("vc_pult", {"gm": 0}, callback=True)["ok"])
        self.assertTrue(sc.emit("vc_pult", {"gm": 255}, callback=True)["ok"])
        self.assertEqual(om.grand_master, 1.0)
        # mit dem Schalter immer
        om.set_grand_master(0.0)
        remote_settings.set_laser_vom_handy(True)
        self.assertTrue(sc.emit("vc_pult", {"gm": 128}, callback=True)["ok"])

    def test_feste_seite_kommt_nicht_an_den_laser(self):
        self.app.config["LIGHTOS_FESTE_TOKEN"] = "festeK22"
        remote_settings.set_feste_seite_enabled(True)
        remote_settings.set_roh_dmx_enabled(True)
        self.addCleanup(remote_settings.set_feste_seite_enabled, False)
        self.addCleanup(remote_settings.set_roh_dmx_enabled, False)
        c = self.app.test_client()
        c.get("/?k=festeK22")
        ex = _Ex(LASER)
        with mock.patch.object(self.webapp, "_get_state", lambda: _FesterStand(self.state, ex)), \
                mock.patch("src.core.cueliste_ziel.transport_cueliste",
                           lambda _s: ex.stack):
            self.assertEqual(c.post(f"/api/channel/{LASER_ADR[0]}/{LASER_ADR[1]}",
                                    json={"value": 255}).status_code, 403)
            self.assertEqual(c.post("/api/executor/1/go").status_code, 403)
            self.assertEqual(c.post("/api/executor/1/fader",
                                    json={"level": 1.0}).status_code, 403)
            self.assertEqual(c.post("/api/go").status_code, 403)
            self.assertEqual(c.post("/api/back").status_code, 403)
            self.assertEqual(ex.gedrueckt, [])
            self.assertEqual(ex.stack.aktionen, [])
            self.assertEqual(ex.fader_value, 0.0)
            sc = self.sio.test_client(self.app, flask_test_client=c)
            self.addCleanup(lambda: sc.is_connected() and sc.disconnect())
            self.assertEqual(sc.emit("go", callback=True)["fehler"], "laser_gesperrt")
            self.assertEqual(sc.emit("fader", {"slot": 1, "level": 1.0},
                                     callback=True)["fehler"], "laser_gesperrt")
            # senken und STOP gehen
            ex.fader_value = 0.8
            self.assertEqual(c.post("/api/executor/1/fader",
                                    json={"level": 0.1}).status_code, 200)
            self.assertNotEqual(c.post("/api/stop").status_code, 403)


class _FesterStand:
    """Der echte Zustand, aber mit genau einem (Laser-)Executor."""

    def __init__(self, state, ex):
        import types
        self._s = state
        self.playback_engine = types.SimpleNamespace(executors=[ex])
        self.cue_stacks = [ex.stack]
        self.universes = {LASER_ADR[0]: object()}
        self.kanaele = []

    def set_input_channel(self, *a, **k):
        self.kanaele.append(a)

    def __getattr__(self, name):
        return getattr(self._s, name)


# ── Halter je Verbindung ─────────────────────────────────────────────────────

class HalterTest(_Basis):

    def _flash(self):
        f = self._szene(LICHT, "WEB12 Flash")
        t = self._taste(ButtonAction.FUNCTION_FLASH, fid=f.id)
        self._auf_seite(t)
        return t, f

    def test_vom_pult_gehalten_bleibt_beim_loslassen_des_handys(self):
        t, f = self._flash()
        t.fern_taste(True)                              # Pult (Maus/MIDI) haelt
        r = vc_remote.halten("handy", t.widget_id)
        self.assertTrue(r["ok"] and r.get("gehalten_vom_pult"))
        self.assertEqual(vc_remote.gehaltene(), set())
        vc_remote.loslassen_von("handy", t.widget_id)
        self.assertTrue(t._pressed)
        vc_remote.zuschauer_weg("handy")
        self.assertTrue(t._pressed)
        self.assertTrue(self.fm.is_running(f.id))

    def test_zwei_handys_erst_das_letzte_laesst_los(self):
        t, f = self._flash()
        self.assertTrue(vc_remote.halten("a", t.widget_id)["ausgeloest"])
        self.assertTrue(vc_remote.halten("b", t.widget_id)["ok"])
        vc_remote.loslassen_von("a", t.widget_id)
        self.assertTrue(t._pressed)
        vc_remote.zuschauer_weg("b")                    # B verliert das WLAN
        self.assertFalse(t._pressed)
        self.assertFalse(self.fm.is_running(f.id))

    def test_abriss_eines_handys_laesst_das_andere_halten(self):
        t, _f = self._flash()
        vc_remote.halten("a", t.widget_id)
        vc_remote.halten("b", t.widget_id)
        vc_remote.zuschauer_weg("a")
        self.assertTrue(t._pressed)
        self.assertEqual(vc_remote.gehaltene("b"), {t.widget_id})

    def test_blackout_taste_vom_pult_gehalten(self):
        t = self._taste(ButtonAction.BLACKOUT)
        self._auf_seite(t)
        t.fern_taste(True)                              # Pult haelt den Blackout
        vc_remote.halten("handy", t.widget_id)
        vc_remote.loslassen_von("handy", t.widget_id)
        vc_remote.zuschauer_weg("handy")
        self.assertTrue(self.state.output_manager.blackout)

    def test_http_halten_gibt_es_nicht(self):
        if not HAS_FLASK:
            self.skipTest("flask fehlt")
        import src.web.app as webapp
        app, _sio = webapp.create_app()
        app.config["LIGHTOS_REMOTE_TOKEN"] = "konsoleK1"
        c = app.test_client()
        c.get("/konsole?k=konsoleK1")
        t, f = self._flash()
        for aktion in ("druecken", "loslassen"):
            r = c.post(f"/api/vc/widget/{t.widget_id}/aktion", json={"aktion": aktion})
            self.assertEqual(r.status_code, 400)
        self.assertFalse(self.fm.is_running(f.id))


class LoeschenLaesstLosTest(_Basis):

    def test_loeschen_waehrend_gehalten(self):
        f = self._szene(LICHT, "WEB12 Loeschen")
        t = self._taste(ButtonAction.FUNCTION_FLASH, fid=f.id)
        self._auf_seite(t)
        vc_remote.halten("handy", t.widget_id)
        self.assertTrue(self.fm.is_running(f.id))
        self.canvas._remove_widget(t)
        self.assertFalse(self.fm.is_running(f.id))
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_blackout_beim_loeschen_und_typtausch(self):
        om = self.state.output_manager
        for weg in ("loeschen", "typ"):
            with self.subTest(weg):
                t = self._taste(ButtonAction.BLACKOUT)
                self._auf_seite(t)
                vc_remote.halten("handy", t.widget_id)
                self.assertTrue(om.blackout)
                if weg == "loeschen":
                    self.canvas._remove_widget(t)
                else:
                    self.canvas.replace_widget_type(t, "VCSlider")
                self.assertFalse(om.blackout, weg)
                self.assertEqual(vc_remote.gehaltene(), set())

    def test_show_laden_laesst_los(self):
        f = self._szene(LICHT, "WEB12 Laden")
        t = self._taste(ButtonAction.FUNCTION_FLASH, fid=f.id)
        self._auf_seite(t)
        vc_remote.halten("handy", t.widget_id)
        self.canvas.from_dict({"widgets": []})
        self.assertFalse(self.fm.is_running(f.id))
        self.assertEqual(vc_remote.gehaltene(), set())


# ── Spaete Antwort der Oberflaeche ───────────────────────────────────────────

class SpaeteAntwortTest(_Basis):

    def test_begonnene_aktion_meldet_ihr_ergebnis_statt_fehler(self):
        ergebnis = {}
        laeuft = threading.Event()

        def langsam():
            laeuft.set()
            time.sleep(0.45)                 # laenger als zwei Wartezeiten
            return {"ok": True, "spaet": True}

        def web():
            ergebnis["r"] = self.fern._im_ui_thread(langsam, lambda c: {"ok": False,
                                                                        "fehler": c})

        with mock.patch.object(VCFernbedienung, "ZEITLIMIT_S", 0.1):
            faden = threading.Thread(target=web)
            faden.start()
            time.sleep(0.05)                 # Auftrag ist eingereiht …
            _app.processEvents()             # … und beginnt im UI-Thread
            faden.join(timeout=5)
        self.assertTrue(laeuft.is_set())
        self.assertEqual(ergebnis["r"], {"ok": True, "spaet": True})

    def test_nicht_begonnene_aktion_verfaellt_weiter(self):
        gerufen = []
        with mock.patch.object(VCFernbedienung, "ZEITLIMIT_S", 0.05):
            r = []
            faden = threading.Thread(target=lambda: r.append(self.fern._im_ui_thread(
                lambda: gerufen.append(1), lambda c: {"ok": False, "fehler": c})))
            faden.start()
            faden.join(timeout=5)
        _app.processEvents()
        self.assertEqual(r, [{"ok": False, "fehler": "zeitueberschreitung"}])
        self.assertEqual(gerufen, [])


# ── Am Handy sichtbar ────────────────────────────────────────────────────────

class SichtbarTest(_Basis):

    def test_notaus_im_stand_und_als_meldung(self):
        gesendet = []
        vc_remote.setze_sender(lambda e, d: gesendet.append((e, d)))
        vc_remote.zuschauer_dazu("handy")
        self.addCleanup(vc_remote.zuschauer_weg, "handy")
        self.assertIs(self.fern.konsole()["notaus"], False)
        alt = self.state.laser_estop_active
        self.addCleanup(setattr, self.state, "laser_estop_active", alt)
        self.state.laser_estop_active = True
        self.fern._takt()
        self.assertEqual(gesendet[-1][0], "vc_zustand")
        self.assertIs(gesendet[-1][1]["notaus"], True)
        self.assertIs(self.fern.konsole()["notaus"], True)

    def test_verlorenes_ziel_wird_gemeldet(self):
        t = self._taste(fid=987654)                      # Funktion gibt es nicht
        dunkel = self._taste(ButtonAction.BLACKOUT, x=100)
        dunkel.blackout_group_ids = [4242]
        dunkel.blackout_group_refs = {4242: {"uid": "weg", "name": "Bühne", "folder": ""}}
        self._auf_seite(t, dunkel)
        with mock.patch.object(dunkel, "_blackout_verloren_anzeige",
                               return_value=["„Bühne“"]):
            k = self.fern.konsole()
        self.assertEqual(k["widgets"][t.widget_id]["ziel_fehlt"], ["Funktion nicht gefunden"])
        self.assertIn("Bühne", k["widgets"][dunkel.widget_id]["ziel_fehlt"][0])

    def test_seite_zeigt_notaus_sperre_und_verlorenes_ziel(self):
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "src", "web", "templates", "konsole.html")
        with open(pfad, encoding="utf-8") as fh:
            html = fh.read()
        for teil in ('id="notaus"', "LASER NOT-AUS AKTIV", "zeigeNotaus", "d.notaus",
                     "w.gesperrt === 'laser'", "ziel_fehlt", "laser_gesperrt",
                     "blackout_nicht_von_hier"):
            self.assertIn(teil, html, teil)


if __name__ == "__main__":
    unittest.main()
