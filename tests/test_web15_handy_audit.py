"""WEB-15: Befunde aus dem Neuheiten-Audit der Handy-Konsole.

* **Laser-Sperre bei Executor-Tasten:** „Executor: Umschalten (Go)“ und
  „Executor: Flash“ tragen in ``function_id`` den Executor-SLOT, keine
  Funktions-ID. Die Laser-Pruefung schlug ihn bisher als Funktion nach und
  liess die Laser-Cueliste vom Handy aus starten. Dazu eine systematische
  Tabelle: jede Aktionsart von Taste, Fader und Cueliste gegen die Pruefung.
* **vc_pult ganz oder gar nicht:** ein abgelehnter Grand Master laesst den
  Blackout im selben Aufruf unberuehrt.
* **Halten ohne globale Sperre ueber den UI-Rundlauf** und eine einfache
  Grenze je Verbindung.
* **NaN/Infinity in handy_seiten** verwirft nur den kaputten Eintrag.
"""
import json
import math
import os
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web15_")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core import handy_seiten as hs  # noqa: E402
from src.core.app_state import get_state  # noqa: E402
from src.core.engine.executor import PlaybackEngine  # noqa: E402
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

LASER = 9611            # fid eines (vorgetaeuschten) Lasers im Patch
LICHT = 9612            # fid eines gewoehnlichen Geraets
LASER_ADR = (1, 411)
WARTEN = 10.0           # nur Notbremse gegen Haengen, nie die Messgroesse


class _Cue:
    def __init__(self, fid):
        self.number = 1.0
        self.label = "Cue 1"
        self.values = {fid: {"intensity": 255}}
        self.sub_stack_ref = None


class _Stack:
    name = "Liste"

    def __init__(self, fid):
        self.cues = [_Cue(fid)]
        self.current_index = -1


class _Ex:
    """Executor-Attrappe: merkt sich jeden Knopf."""

    def __init__(self, fid):
        self.stack = _Stack(fid)
        self.gedrueckt = []

    def press_btn(self, was):
        self.gedrueckt.append(was)

    def release_btn(self, was):
        self.gedrueckt.append("los:" + was)


class _Basis(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.fm = self.state.function_manager
        self.fm.stop_all()
        om = self.state.output_manager
        om.set_blackout(False)
        om.set_grand_master(1.0)
        alt_fids = getattr(self.state, "_laser_fids", frozenset())
        alt_adr = getattr(self.state, "_laser_estop_addrs", {})
        self.state._laser_fids = frozenset({LASER})
        self.state._laser_estop_addrs = {LASER_ADR[0]: frozenset({LASER_ADR[1]})}
        self.addCleanup(setattr, self.state, "_laser_fids", alt_fids)
        self.addCleanup(setattr, self.state, "_laser_estop_addrs", alt_adr)
        # Executor-Seite: Slot 0 = Licht, Slot 1 = Laser
        self.ex_licht, self.ex_laser = _Ex(LICHT), _Ex(LASER)
        p = mock.patch.object(PlaybackEngine, "executors", new_callable=mock.PropertyMock,
                              return_value=[self.ex_licht, self.ex_laser])
        p.start()
        self.addCleanup(p.stop)
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

    def _taste(self, aktion, fid=None, x=10):
        w = self.canvas._add_widget("VCButton", QPoint(x, 10))
        w.caption = "T"
        w.action = aktion
        w.function_id = fid
        return w

    def _auf_seite(self, *widgets):
        a = hs.seite_hinzufuegen(hs.leer(), "Test")
        for i, w in enumerate(widgets):
            a = hs.eintrag_setzen(a, 0, w.widget_id, i % 4, i // 4)
        self.canvas.setze_handy_seiten(a)

    def _aktion(self, w, aktion, wert=None):
        return self.fern.aktion(w.widget_id, aktion, wert, nur_handy_seiten=True)


# ── Fund 1 (Index 4): Executor-Tasten und die Laser-Sperre ───────────────────

class ExecutorTasteLaserTest(_Basis):

    def test_umschalten_auf_laser_executor_ist_gesperrt(self):
        t = self._taste(ButtonAction.TOGGLE, fid=1)          # Slot 1 = Laser
        self._auf_seite(t)
        self.assertTrue(vf.laser_inhalt(t))
        r = self._aktion(t, "umschalten")
        self.assertEqual(r, {"ok": False, "fehler": "laser_gesperrt"})
        self.assertEqual(self.ex_laser.gedrueckt, [])
        self.assertEqual(self.fern.konsole()["widgets"][t.widget_id]["gesperrt"], "laser")

    def test_flash_auf_laser_executor_ist_gesperrt(self):
        t = self._taste(ButtonAction.FLASH, fid=1)
        self._auf_seite(t)
        self.assertTrue(vf.laser_inhalt(t))
        for aktion in ("druecken", "umschalten"):
            with self.subTest(aktion):
                self.assertEqual(self._aktion(t, aktion),
                                 {"ok": False, "fehler": "laser_gesperrt"})
        r = vc_remote.halten("handy", t.widget_id)            # Socket-Weg
        self.assertEqual(r.get("fehler"), "laser_gesperrt")
        self.assertEqual(self.ex_laser.gedrueckt, [])
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_mit_schalter_geht_es(self):
        t = self._taste(ButtonAction.TOGGLE, fid=1)
        self._auf_seite(t)
        remote_settings.set_laser_vom_handy(True)
        self.assertTrue(self._aktion(t, "umschalten")["ok"])
        self.assertEqual(self.ex_laser.gedrueckt, ["go"])

    def test_executor_ohne_laser_bleibt_frei(self):
        t = self._taste(ButtonAction.TOGGLE, fid=0)          # Slot 0 = Licht
        fl = self._taste(ButtonAction.FLASH, fid=0, x=60)
        self._auf_seite(t, fl)
        self.assertFalse(vf.laser_inhalt(t))
        self.assertFalse(vf.laser_inhalt(fl))
        self.assertTrue(self._aktion(t, "umschalten")["ok"])
        self.assertEqual(self.ex_licht.gedrueckt, ["go"])

    def test_slot_gleich_laser_funktions_id_sperrt_nicht_falsch(self):
        # Die Slot-Nummer ist zufaellig die ID einer Laser-Szene — ohne Laser-
        # Executor auf dem Slot darf das keine Sperre ergeben.
        laser_szene = self._szene(LASER, "WEB15 Laser")
        t = self._taste(ButtonAction.TOGGLE, fid=laser_szene.id)
        leer = self._taste(ButtonAction.FLASH, fid=None, x=60)
        self.assertFalse(vf.laser_inhalt(leer))
        with mock.patch.object(PlaybackEngine, "executors", new_callable=mock.PropertyMock,
                               return_value=[self.ex_licht] * (laser_szene.id + 1)):
            self.assertFalse(vf.laser_inhalt(t))
        with mock.patch.object(PlaybackEngine, "executors", new_callable=mock.PropertyMock,
                               return_value=[self.ex_laser] * laser_szene.id):
            self.assertFalse(vf.laser_inhalt(t))  # Slot ausserhalb: tut nichts

    def test_zusatzaktion_bleibt_geprueft(self):
        laser_szene = self._szene(LASER, "WEB15 Zusatz")
        t = self._taste(ButtonAction.TOGGLE, fid=0)
        t.actions = [{"type": "function", "function_id": laser_szene.id, "mode": "on"}]
        self.assertTrue(vf.laser_inhalt(t))


# Tabelle Aktionsart -> erwartete Laser-Pruefung (WEB-15). Jede Aktion, die vom
# Handy eine Funktion, einen Executor oder Werte auf Geraete bringt, muss mit
# Laser-Ziel gesperrt sein. Kommt eine neue ButtonAction dazu, schlaegt
# ``test_jede_tastenaktion_ist_eingeordnet`` an, bis sie hier steht.
_TASTE_LASER = {
    # Aktion: (Einrichtung mit Laser-Ziel, gesperrt?)
    ButtonAction.TOGGLE: ("slot", True),
    ButtonAction.FLASH: ("slot", True),
    ButtonAction.FUNCTION_TOGGLE: ("funktion", True),
    ButtonAction.FUNCTION_FLASH: ("funktion", True),
    ButtonAction.ALL_WHITE: ("funktion", True),
    ButtonAction.EFFECT_ACTION: ("funktion", True),
    ButtonAction.SNAPSHOT: ("snapshot", True),
    ButtonAction.LIBRARY_SNAP: ("snap", True),
    ButtonAction.LASER_PATTERN: ("muster", True),
    # ohne Laser-Ziel moeglich: dunkel, stoppen, Tempo, Auswahl, Musik, Pop-up
    ButtonAction.BLACKOUT: ("funktion", False),
    ButtonAction.STOP_ALL: ("funktion", False),
    ButtonAction.CLEAR: ("funktion", False),
    ButtonAction.TAP: ("funktion", False),
    ButtonAction.AUDIO_BPM: ("funktion", False),
    ButtonAction.BPM_NUDGE_UP: ("funktion", False),
    ButtonAction.BPM_NUDGE_DOWN: ("funktion", False),
    ButtonAction.BPM_MODE_TOGGLE: ("funktion", False),
    ButtonAction.SELECT_GROUP: ("funktion", False),
    ButtonAction.MEDIA_PLAY_PAUSE: ("funktion", False),
    ButtonAction.MEDIA_NEXT: ("funktion", False),
    ButtonAction.MEDIA_PREV: ("funktion", False),
    ButtonAction.TAP_BUS: ("funktion", False),
    ButtonAction.SYNC_BUS: ("funktion", False),
    ButtonAction.ARM_BUS: ("funktion", False),
    ButtonAction.FREEZE: ("funktion", False),
    ButtonAction.STOP_EFFECTS: ("funktion", False),
    ButtonAction.AUTO_SYNC: ("funktion", False),
    ButtonAction.LASER_ESTOP: ("funktion", False),
    ButtonAction.LASER_ARM: ("funktion", False),      # scharf: nur am Pult
    ButtonAction.POPUP_TOGGLE: ("leer", False),
}

_ZUSATZ_LASER = {
    "function": True, "funktion": True, "effect_action": True, "snapshot": True,
    "library_snap": True, "blackout": False, "stop_all": False, "clear": False,
    "clear_non_vc": False, "tap": False,
}


class AktionsartTabelleTest(_Basis):

    def test_jede_tastenaktion_ist_eingeordnet(self):
        self.assertEqual(set(_TASTE_LASER), set(ButtonAction))

    def _einrichten(self, art, laser_szene):
        if art == "slot":
            return {"fid": 1}
        if art == "funktion":
            return {"fid": laser_szene.id}
        return {"fid": None}

    def test_tasten_mit_laser_ziel(self):
        laser_szene = self._szene(LASER, "WEB15 Tabelle")
        with mock.patch.object(vf, "_snapshot_fids", lambda _i: {LASER}), \
                mock.patch.object(vf, "_snap_fids", lambda _i: {LASER}):
            for a, (art, gesperrt) in _TASTE_LASER.items():
                with self.subTest(a.name):
                    t = self._taste(a, **self._einrichten(art, laser_szene))
                    if art == "snapshot":
                        t.snapshot_index = 0
                    if art == "snap":
                        t.snap_id = 5
                    if art == "muster":
                        t.laser_palette = "Tunnel"
                    self.assertEqual(vf.laser_inhalt(t), gesperrt, a.name)
                    if gesperrt:
                        self._auf_seite(t)
                        with mock.patch.object(type(t), "_trigger") as los:
                            r = self._aktion(t, "umschalten")
                        self.assertEqual(r.get("fehler"), "laser_gesperrt", a.name)
                        los.assert_not_called()

    def test_tasten_ohne_laser_ziel_sind_frei(self):
        licht = self._szene(LICHT, "WEB15 Licht")
        for a, (art, _g) in _TASTE_LASER.items():
            if a == ButtonAction.LASER_PATTERN or a == ButtonAction.EFFECT_ACTION:
                continue            # Muster immer Laser; Effekt-Aktion ohne Ziel auch
            with self.subTest(a.name):
                fid = 0 if art == "slot" else (licht.id if art == "funktion" else None)
                t = self._taste(a, fid=fid)
                with mock.patch.object(vf, "_snapshot_fids", lambda _i: {LICHT}), \
                        mock.patch.object(vf, "_snap_fids", lambda _i: {LICHT}):
                    if art == "snapshot":
                        t.snapshot_index = 0
                    if art == "snap":
                        t.snap_id = 5
                    self.assertFalse(vf.laser_inhalt(t), a.name)

    def test_zusatzaktionen(self):
        laser_szene = self._szene(LASER, "WEB15 Zusatz")
        with mock.patch.object(vf, "_snapshot_fids", lambda _i: {LASER}), \
                mock.patch.object(vf, "_snap_fids", lambda _i: {LASER}):
            for typ, gesperrt in _ZUSATZ_LASER.items():
                with self.subTest(typ):
                    t = self._taste(ButtonAction.TAP)
                    t.actions = [{"type": typ, "function_id": laser_szene.id,
                                  "snapshot_index": 0, "snap_id": 5, "mode": "on"}]
                    self.assertEqual(vf.laser_inhalt(t), gesperrt, typ)
                    self.assertEqual(vf.verzoegert_erlaubt(t.actions[0]), not gesperrt, typ)

    def test_jede_fader_art(self):
        laser_szene = self._szene(LASER, "WEB15 Fader")
        modi = {n: getattr(SliderMode, n) for n in dir(SliderMode)
                if n.isupper() and isinstance(getattr(SliderMode, n), str)}
        erwartet = {"LEVEL": True, "PLAYBACK": True, "SUBMASTER": True,
                    "GRANDMASTER": True, "PROGRAMMER": True, "BPM": False,
                    "SPEED": False, "TEMPO_BUS": False, "EFFECT_INTENSITY": True,
                    "EFFECT_SPEED": True, "EFFECT_PARAM": True,
                    "GROUP_DIMMER": True, "FEATURE_DIMMER": True}
        self.assertEqual(set(modi), set(erwartet))
        for n, m in modi.items():
            with self.subTest(n):
                w = self.canvas._add_widget("VCSlider", QPoint(200, 10))
                w.mode = m
                w.dmx_universe, w.dmx_channel = LASER_ADR
                w.playback_slot = 1
                w.function_id = laser_szene.id
                w._group_fids = lambda _s, _g: [LASER]
                w.programmer_group = "Laser"
                self.assertEqual(vf.laser_inhalt(w), erwartet[n], n)
                if erwartet[n]:
                    self._auf_seite(w)
                    with mock.patch.object(type(w), "_apply") as los:
                        r = self._aktion(w, "setzen", 200)
                    self.assertEqual(r.get("fehler"), "laser_gesperrt", n)
                    los.assert_not_called()

    def test_cueliste(self):
        w = self.canvas._add_widget("VCCueList", QPoint(400, 10))
        w._executor = lambda: self.ex_laser
        self._auf_seite(w)
        self.assertTrue(vf.laser_inhalt(w))
        with mock.patch.object(type(w), "_do_go") as go, \
                mock.patch.object(type(w), "_do_back") as back, \
                mock.patch.object(type(w), "_do_stop") as stop:
            for aktion in ("go", "back"):
                self.assertEqual(self._aktion(w, aktion).get("fehler"), "laser_gesperrt")
            self.assertTrue(self._aktion(w, "stop")["ok"])     # STOP geht immer
        go.assert_not_called()
        back.assert_not_called()
        stop.assert_called_once()


# ── Fund 2 (Index 5): vc_pult ganz oder gar nicht ────────────────────────────

class PultGanzOderGarNichtTest(_Basis):

    def test_abgelehnter_gm_setzt_keinen_blackout(self):
        om = self.state.output_manager
        om.set_grand_master(0.0)                     # vom Pult in die Laser-Aus-Zone
        r = self.fern.pult(gm=255, blackout=True, geraet="h1")
        self.assertFalse(r["ok"])
        self.assertEqual(r["fehler"], "laser_gesperrt")
        self.assertFalse(om.blackout_schalter)
        self.assertEqual(float(om.grand_master), 0.0)

    def test_abgelehnter_gm_hebt_eigenen_blackout_nicht_auf(self):
        om = self.state.output_manager
        self.assertTrue(self.fern.pult(blackout=True, geraet="h1")["ok"])
        om.set_grand_master(0.0)
        r = self.fern.pult(gm=255, blackout=False, geraet="h1")
        self.assertEqual(r.get("fehler"), "laser_gesperrt")
        self.assertTrue(om.blackout_schalter)
        # ohne den GM geht das Aufheben weiter
        self.assertTrue(self.fern.pult(blackout=False, geraet="h1")["ok"])
        self.assertFalse(om.blackout_schalter)

    def test_fremder_blackout_laesst_gm_unveraendert(self):
        om = self.state.output_manager
        om.set_grand_master(0.5)
        om.set_blackout(True)                        # vom Pult
        r = self.fern.pult(gm=128, blackout=False, geraet="h1")
        self.assertEqual(r.get("fehler"), "blackout_nicht_von_hier")
        self.assertAlmostEqual(float(om.grand_master), 0.5)
        self.assertTrue(om.blackout_schalter)

    def test_beides_gueltig_setzt_beides(self):
        om = self.state.output_manager
        r = self.fern.pult(gm=128, blackout=True, geraet="h1")
        self.assertTrue(r["ok"])
        self.assertTrue(om.blackout_schalter)
        self.assertAlmostEqual(float(om.grand_master), 128 / 255.0, places=3)

    def test_feste_fernbedienung_unveraendert(self):
        om = self.state.output_manager
        om.set_grand_master(0.0)
        self.assertEqual(fern_pult.gm_setzen(self.state, 1.0, "h1", False).get("fehler"),
                         "laser_gesperrt")
        self.assertTrue(fern_pult.gm_setzen(self.state, 1.0, "h1", True)["ok"])
        self.assertTrue(fern_pult.blackout_setzen(om, True, "h1")["ok"])
        self.assertTrue(fern_pult.blackout_setzen(om, False, "h1")["ok"])


# ── Fund 3 (Index 6): Halten ohne globale Sperre, Grenze je Verbindung ───────

class _LangsameBruecke:
    """Bruecke, deren „druecken“ auf ausgewaehlten Tasten haengt, bis der Test
    sie freigibt. Zaehlt gedrueckt wie eine echte Taste."""

    def __init__(self):
        self.lock = threading.Lock()
        self.langsam = {}                   # kennung -> (angekommen, frei)
        self.gedrueckt = set()
        self.verlauf = []
        self.abweisen = set()

    def langsam_machen(self, kennung):
        self.langsam[kennung] = (threading.Event(), threading.Event())
        return self.langsam[kennung]

    def aktion(self, kennung, aktion, wert=None, nur_handy_seiten=False):
        bremse = self.langsam.get(kennung) if aktion == "druecken" else None
        if bremse is not None:
            bremse[0].set()
            bremse[1].wait(WARTEN)
        with self.lock:
            self.verlauf.append((aktion, kennung))
            if kennung in self.abweisen:
                return {"ok": False, "fehler": "laser_gesperrt"}
            if aktion == "druecken":
                neu = kennung not in self.gedrueckt
                self.gedrueckt.add(kennung)
                return {"ok": True, "ausgeloest": neu}
            if aktion == "loslassen":
                war = kennung in self.gedrueckt
                self.gedrueckt.discard(kennung)
                return {"ok": True, "ausgeloest": war}
        return {"ok": True}

    def loslassen(self, kennungen):
        with self.lock:
            for k in kennungen:
                self.verlauf.append(("los", k))
                self.gedrueckt.discard(k)


def _im_hintergrund(fn, *args):
    ergebnis = {}
    t = threading.Thread(target=lambda: ergebnis.setdefault("r", fn(*args)), daemon=True)
    t.start()
    return t, ergebnis


class HaltenOhneGlobaleSperreTest(unittest.TestCase):

    def setUp(self):
        remote_settings.set_vc_remote_enabled(True)
        self.b = _LangsameBruecke()
        vc_remote.registriere(self.b)
        self._freigeben = []

    def tearDown(self):
        for frei in self._freigeben:
            frei.set()
        vc_remote.alle_loslassen()
        vc_remote.zuschauer_weg("a")
        vc_remote.zuschauer_weg("b")
        vc_remote.abmelden(self.b)
        remote_settings.set_vc_remote_enabled(False)

    def _langsam(self, kennung):
        angekommen, frei = self.b.langsam_machen(kennung)
        self._freigeben.append(frei)
        return angekommen, frei

    def test_loslassen_anderer_taste_wartet_nicht_auf_den_druck(self):
        self.assertTrue(vc_remote.halten("b", "wB")["ausgeloest"])
        angekommen, frei = self._langsam("wA")
        ta, _ = _im_hintergrund(vc_remote.halten, "a", "wA")
        self.assertTrue(angekommen.wait(WARTEN))
        tb, rb = _im_hintergrund(vc_remote.loslassen_von, "b", "wB")
        tb.join(WARTEN)
        self.assertFalse(tb.is_alive(), "Loslassen hing hinter dem Druck eines anderen")
        self.assertTrue(ta.is_alive())                   # der Druck haengt noch
        self.assertTrue(rb["r"]["ok"])
        self.assertNotIn("wB", self.b.gedrueckt)
        frei.set()
        ta.join(WARTEN)
        self.assertEqual(vc_remote.gehaltene("a"), {"wA"})

    def test_abriss_wartet_nicht_auf_den_druck(self):
        self.assertTrue(vc_remote.halten("b", "wB")["ausgeloest"])
        angekommen, frei = self._langsam("wA")
        ta, _ = _im_hintergrund(vc_remote.halten, "a", "wA")
        self.assertTrue(angekommen.wait(WARTEN))
        tb, _ = _im_hintergrund(vc_remote.zuschauer_weg, "b")
        tb.join(WARTEN)
        self.assertFalse(tb.is_alive(), "Abbau hing hinter dem Druck eines anderen")
        self.assertNotIn("wB", self.b.gedrueckt)
        frei.set()
        ta.join(WARTEN)

    def test_loslassen_waehrend_des_eigenen_drucks(self):
        angekommen, frei = self._langsam("wA")
        ta, ra = _im_hintergrund(vc_remote.halten, "a", "wA")
        self.assertTrue(angekommen.wait(WARTEN))
        r = vc_remote.loslassen_von("a", "wA")           # Finger schon wieder weg
        self.assertTrue(r["ok"])
        frei.set()
        ta.join(WARTEN)
        self.assertTrue(ra["r"]["ok"])
        self.assertNotIn("wA", self.b.gedrueckt)          # nicht haengen geblieben
        self.assertEqual(vc_remote.gehaltene("a"), set())

    def test_abriss_waehrend_des_eigenen_drucks(self):
        angekommen, frei = self._langsam("wA")
        ta, _ = _im_hintergrund(vc_remote.halten, "a", "wA")
        self.assertTrue(angekommen.wait(WARTEN))
        vc_remote.zuschauer_weg("a")
        frei.set()
        ta.join(WARTEN)
        self.assertNotIn("wA", self.b.gedrueckt)
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_uebergabe_an_zweites_handy(self):
        # A haelt; B drueckt dieselbe Taste (langsam); A laesst in der Zeit
        # los. Die Taste bleibt gedrueckt, B ist danach Halter.
        self.assertTrue(vc_remote.halten("a", "wX")["ausgeloest"])
        angekommen, frei = self._langsam("wX")
        tb, rb = _im_hintergrund(vc_remote.halten, "b", "wX")
        self.assertTrue(angekommen.wait(WARTEN))
        vc_remote.loslassen_von("a", "wX")
        self.assertIn("wX", self.b.gedrueckt)
        frei.set()
        tb.join(WARTEN)
        self.assertTrue(rb["r"]["ok"])
        self.assertIn("wX", self.b.gedrueckt)
        self.assertEqual(vc_remote.gehaltene("b"), {"wX"})
        vc_remote.loslassen_von("b", "wX")
        self.assertNotIn("wX", self.b.gedrueckt)

    def test_uebergabe_mit_abgelehntem_druck_laesst_los(self):
        self.assertTrue(vc_remote.halten("a", "wX")["ausgeloest"])
        angekommen, frei = self._langsam("wX")
        self.b.abweisen.add("wX")
        tb, rb = _im_hintergrund(vc_remote.halten, "b", "wX")
        self.assertTrue(angekommen.wait(WARTEN))
        vc_remote.loslassen_von("a", "wX")
        frei.set()
        tb.join(WARTEN)
        self.assertFalse(rb["r"]["ok"])
        self.assertNotIn("wX", self.b.gedrueckt)          # niemand haelt mehr
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_zwei_handys_gleichzeitig_beide_halter(self):
        angekommen, frei = self._langsam("wX")
        ta, _ = _im_hintergrund(vc_remote.halten, "a", "wX")
        self.assertTrue(angekommen.wait(WARTEN))
        tb, rb = _im_hintergrund(vc_remote.halten, "b", "wX")   # wartet auf A
        frei.set()
        ta.join(WARTEN)
        tb.join(WARTEN)
        self.assertEqual(vc_remote.gehaltene("a"), {"wX"})
        self.assertEqual(vc_remote.gehaltene("b"), {"wX"})
        vc_remote.loslassen_von("a", "wX")
        self.assertIn("wX", self.b.gedrueckt)
        vc_remote.loslassen_von("b", "wX")
        self.assertNotIn("wX", self.b.gedrueckt)


class _Uhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class VerbindungsGrenzeTest(unittest.TestCase):

    def setUp(self):
        from src.web import vc_grenze
        self.vg = vc_grenze
        self.uhr = _Uhr()
        self.g = vc_grenze.VerbindungsGrenze(uhr=self.uhr)

    def test_n_plus_erste_gleichzeitige_aktion_wird_abgewiesen(self):
        for _ in range(self.g.gleichzeitig):
            self.assertEqual(self.g.herein("s1"), "los")
        self.assertEqual(self.g.herein("s1"), self.vg.ZU_VIELE)
        self.assertEqual(self.g.herein("s2"), "los")       # andere Verbindung frei
        self.assertIsNone(self.g.fertig("s1"))
        self.assertEqual(self.g.herein("s1"), "los")

    def test_fader_zug_wird_zusammengefasst_statt_abgewiesen(self):
        self.assertEqual(self.g.herein("s1", "wF", lambda: 1), "los")
        werte = []
        for v in range(2, 50):
            self.assertEqual(self.g.herein("s1", "wF", lambda v=v: werte.append(v)),
                             "nachgeholt")
        weiter = self.g.fertig("s1", "wF")
        weiter()
        self.assertEqual(werte, [49])                    # nur der letzte Stand
        self.assertIsNone(self.g.fertig("s1", "wF"))
        self.assertEqual(self.g.herein("s1", "wF", lambda: 1), "los")

    def test_schnelles_tippen_und_fader_ohne_bremse(self):
        # 120 Ereignisse je Sekunde (Fader-Zug auf 120-Hz-Display) zehn
        # Sekunden lang, dazu Tippen: nichts wird abgewiesen.
        for i in range(1200):
            self.uhr.t = i / 120.0
            self.assertEqual(self.g.herein("s1", "wF", lambda: None), "los", i)
            self.assertIsNone(self.g.fertig("s1", "wF"))
            if i % 6 == 0:
                self.assertEqual(self.g.herein("s1"), "los", i)
                self.assertIsNone(self.g.fertig("s1"))

    def test_flut_wird_gebremst(self):
        abgewiesen = 0
        for _ in range(5000):                            # alles im selben Augenblick
            if self.g.herein("s1") == "los":
                self.g.fertig("s1")
            else:
                abgewiesen += 1
        self.assertGreater(abgewiesen, 4000)
        self.uhr.t = 1.0                                 # eine Sekunde spaeter wieder
        self.assertEqual(self.g.herein("s1"), "los")

    def test_vergessen(self):
        for _ in range(self.g.gleichzeitig):
            self.g.herein("s1")
        self.g.vergessen("s1")
        self.assertEqual(self.g.herein("s1"), "los")


@unittest.skipUnless(HAS_FLASK, "flask fehlt")
class GrenzeImSocketTest(_Basis):

    def setUp(self):
        super().setUp()
        import src.web.app as webapp
        self.app, self.sio = webapp.create_app()
        self.app.config["LIGHTOS_REMOTE_TOKEN"] = "konsoleK15"
        self.client = self.app.test_client()
        self.client.get("/konsole?k=konsoleK15")
        self.sc = self.sio.test_client(self.app, flask_test_client=self.client)
        self.addCleanup(self.sc.disconnect)
        self.sid = self.sio.lightos_vc_sid_fuer_test(self.sc) \
            if hasattr(self.sio, "lightos_vc_sid_fuer_test") else None

    def _emit(self, ereignis, daten):
        return self.sc.emit(ereignis, daten, callback=True)

    def test_voll_belegte_verbindung(self):
        t = self._taste(ButtonAction.FUNCTION_FLASH, fid=self._szene(LICHT, "W15").id)
        self._auf_seite(t)
        g = self.sio.lightos_vc_grenze
        with mock.patch.object(g, "herein", return_value="zu_viele"):
            self.assertEqual(self._emit("vc_aktion", {"id": t.widget_id, "aktion": "druecken"}),
                             {"ok": False, "fehler": "zu_viele"})
            self.assertEqual(self._emit("vc_aktion",
                                        {"id": t.widget_id, "aktion": "umschalten"})["fehler"],
                             "zu_viele")
            # Loslassen und Blackout AN gehen immer
            self.assertTrue(self._emit("vc_aktion",
                                       {"id": t.widget_id, "aktion": "loslassen"})["ok"])
            self.assertTrue(self._emit("vc_pult", {"blackout": True})["ok"])
        self.assertTrue(self.state.output_manager.blackout_schalter)
        self.assertEqual(vc_remote.HTTP_STATUS.get("zu_viele"), 429)

    def test_normale_bedienung_geht_durch(self):
        f = self._szene(LICHT, "W15 normal")
        t = self._taste(ButtonAction.FUNCTION_TOGGLE, fid=f.id)
        fader = self.canvas._add_widget("VCSlider", QPoint(200, 10))
        fader.mode = SliderMode.BPM
        self._auf_seite(t, fader)
        for i in range(60):
            r = self._emit("vc_aktion", {"id": t.widget_id, "aktion": "umschalten"})
            self.assertTrue(r["ok"], (i, r))
        self.assertFalse(self.fm.is_running(f.id))      # 60 Tipps: wieder aus
        with mock.patch.object(type(fader), "_apply"):
            for i in range(200):
                r = self._emit("vc_aktion", {"id": fader.widget_id, "aktion": "setzen",
                                             "wert": i % 256, "n": i + 1})
                self.assertTrue(r["ok"], (i, r))


# ── Fund 4 (Index 8): NaN/Infinity in handy_seiten ───────────────────────────

class NaNInHandySeitenTest(unittest.TestCase):

    def _roh(self, feld, text):
        eintrag = {"widget": "wabcd1", "spalte": 0, "zeile": 0, "breite": 1, "hoehe": 1}
        roh = json.dumps({"seiten": [{"eintraege": [
            eintrag, {"widget": "wabcd2", "spalte": 1, "zeile": 0}]}]})
        return json.loads(roh.replace(f'"{feld}": {eintrag[feld]}', f'"{feld}": {text}', 1))

    def test_nan_und_unendlich_verwerfen_nur_den_eintrag(self):
        for feld in ("spalte", "zeile", "breite", "hoehe"):
            for text in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(feld=feld, wert=text):
                    roh = self._roh(feld, text)
                    self.assertTrue(math.isnan(roh["seiten"][0]["eintraege"][0][feld])
                                    or math.isinf(roh["seiten"][0]["eintraege"][0][feld]))
                    a = hs.normalisiere(roh)
                    kennungen = [e["widget"] for e in a["seiten"][0]["eintraege"]]
                    self.assertIn("wabcd2", kennungen)

    def test_passt_und_groesse(self):
        a = hs.seite_hinzufuegen(hs.leer(), "S")
        for v in (float("nan"), float("inf"), float("-inf")):
            self.assertFalse(hs.passt(a, 0, v, 0))
            self.assertFalse(hs.passt(a, 0, 0, 0, breite=v))
            b, h = hs.groesse_begrenzen("taste", v, v)
            self.assertTrue(isinstance(b, int) and isinstance(h, int))

    def test_canvas_laedt_rest_der_seiten(self):
        canvas = VCCanvas()
        try:
            w1 = canvas._add_widget("VCButton", QPoint(10, 10))
            w2 = canvas._add_widget("VCButton", QPoint(60, 10))
            d = canvas.to_dict()
            d[hs.SCHLUESSEL] = {"version": 1, "seiten": [{"name": "S", "eintraege": [
                {"widget": w1.widget_id, "spalte": float("nan"), "zeile": 0},
                {"widget": w2.widget_id, "spalte": 1, "zeile": 0}]}]}
            canvas.from_dict(json.loads(json.dumps(d)))
            seiten = canvas.handy_seiten()["seiten"]
            self.assertEqual(len(seiten), 1)
            self.assertEqual(len(seiten[0]["eintraege"]), 1)
        finally:
            canvas.close()
            canvas.deleteLater()


if __name__ == "__main__":
    unittest.main()
