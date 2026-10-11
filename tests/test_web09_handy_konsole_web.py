"""WEB-09: Handy-Konsole am Web-Server — Freigabe, Rueckmeldung, Seite.

* **Freigabe:** die Schnittstelle liefert und bedient nur Widgets, die auf
  einer Handy-Seite liegen. Alles andere: 403, und es passiert nichts.
* **Socket:** Abgleich beim Verbinden, Meldung bei Aenderung (gedrosselt ueber
  den Takt der Bruecke), Aktionen samt Fader-Reihenfolge, Loslassen gehaltener
  Tasten bei Verbindungsabbruch, Schluessel und Epoche bei jedem Ereignis.
* **Seite:** ``/konsole`` wird ohne eine einzige Adresse nach aussen
  ausgeliefert; die feste Seite verlinkt nur, wenn die Konsole eingeschaltet ist.
"""
import os
import re
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Vor dem Import: Schluessel/Einstellungen in ein Wegwerf-Verzeichnis.
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web09_")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from src.core import handy_seiten as hs
from src.core.app_state import get_state
from src.ui.virtualconsole.vc_button import ButtonAction
from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_fernbedienung import VCFernbedienung
from src.ui.virtualconsole.vc_slider import SliderMode
from src.web import remote_settings, vc_remote

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

_app = QApplication.instance() or QApplication([])

_VORLAGEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src", "web", "templates")


# Eine Adresse nach aussen: mit Protokoll (http://, wss://, …) oder
# protokoll-relativ (//host) als Wert eines Attributs bzw. in url(…).
_EXTERN = r"""(?i)\b[a-z][a-z0-9+.-]*://|["'(=]\s*//[a-z0-9]"""


class _FakeCue:
    def __init__(self, nummer, name):
        self.number = nummer
        self.label = name


class _FakeStack:
    name = "Hauptshow"

    def __init__(self):
        self.cues = [_FakeCue(1.0, "Einlass"), _FakeCue(2.0, "Strophe"),
                     _FakeCue(3.0, "Refrain")]
        self.current_index = 0


class _FakeExecutor:
    def __init__(self):
        self.stack = _FakeStack()

    def press_btn(self, was):
        if was == "go":
            self.stack.current_index = min(2, self.stack.current_index + 1)
        elif was == "back":
            self.stack.current_index = max(0, self.stack.current_index - 1)
        else:
            self.stack.current_index = -1


class _Basis(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.fm = self.state.function_manager
        self.fm.stop_all()
        self.state.output_manager.set_blackout(False)
        self.state.output_manager.set_grand_master(1.0)
        self.canvas = VCCanvas()
        self.fern = VCFernbedienung(self.canvas)
        self._funktionen = []
        remote_settings.set_vc_remote_enabled(True)
        vc_remote.registriere(self.fern)

    def tearDown(self):
        vc_remote.alle_loslassen()
        vc_remote.abmelden(self.fern)
        vc_remote.setze_sender(None)
        remote_settings.set_vc_remote_enabled(False)
        self.fm.stop_all()
        self.state.output_manager.set_blackout(False)
        self.state.output_manager.set_grand_master(1.0)
        for f in self._funktionen:
            self.fm.remove(f.id)
        self.canvas.close()
        self.canvas.deleteLater()

    def _efx(self, name):
        f = self.fm.new_efx(name)
        self._funktionen.append(f)
        return f

    def _taste(self, aktion=ButtonAction.FUNCTION_TOGGLE, fid=None, x=10, text="T"):
        w = self.canvas._add_widget("VCButton", QPoint(x, 10))
        w.caption = text
        w.action = aktion
        w.function_id = fid
        return w

    def _fader(self, x=200):
        w = self.canvas._add_widget("VCSlider", QPoint(x, 10))
        w.mode = SliderMode.LEVEL
        return w

    def _auf_seite(self, *widgets):
        """Legt genau diese Widgets auf eine Handy-Seite (1 x 1, nebeneinander)."""
        a = hs.seite_hinzufuegen(hs.leer(), "Test")
        for i, w in enumerate(widgets):
            a = hs.eintrag_setzen(a, 0, w.widget_id, i % 4, i // 4)
        self.assertTrue(self.canvas.setze_handy_seiten(a))


# ── Freigabe an der Bruecke ──────────────────────────────────────────────────

class FreigabeBrueckeTest(_Basis):

    def test_liste_nur_von_den_seiten(self):
        drauf, draussen = self._taste(x=10), self._taste(x=100)
        self._auf_seite(drauf)
        self.assertEqual([w["id"] for w in self.fern.widgets(nur_handy_seiten=True)],
                         [drauf.widget_id])
        # ohne die Einschraenkung (Editor, Tests) bleibt die volle Liste
        self.assertEqual({w["id"] for w in self.fern.widgets()},
                         {drauf.widget_id, draussen.widget_id})

    def test_aktion_ausserhalb_der_seiten_wird_abgelehnt_und_tut_nichts(self):
        a, b = self._efx("WEB09 drauf"), self._efx("WEB09 draussen")
        drauf, draussen = self._taste(fid=a.id, x=10), self._taste(fid=b.id, x=100)
        self._auf_seite(drauf)
        r = self.fern.aktion(draussen.widget_id, "umschalten", nur_handy_seiten=True)
        self.assertEqual(r, {"ok": False, "fehler": "nicht_freigegeben"})
        self.assertFalse(self.fm.is_running(b.id))
        self.assertFalse(draussen._pressed)
        self.assertTrue(self.fern.aktion(drauf.widget_id, "umschalten",
                                         nur_handy_seiten=True)["ok"])
        self.assertTrue(self.fm.is_running(a.id))

    def test_von_der_seite_genommen_ist_sofort_gesperrt(self):
        a = self._efx("WEB09 weg")
        t = self._taste(fid=a.id)
        self._auf_seite(t)
        self.canvas.setze_handy_seiten(hs.leer())
        r = self.fern.aktion(t.widget_id, "umschalten", nur_handy_seiten=True)
        self.assertEqual(r["fehler"], "nicht_freigegeben")
        self.assertFalse(self.fm.is_running(a.id))

    def test_ohne_seiten_ist_nichts_freigegeben(self):
        t = self._taste()
        self.assertEqual(self.fern.widgets(nur_handy_seiten=True), [])
        self.assertEqual(self.fern.aktion(t.widget_id, "umschalten",
                                          nur_handy_seiten=True)["fehler"],
                         "nicht_freigegeben")

    def test_konsole_liefert_seiten_zustand_und_pult(self):
        t = self._taste(text="Strobe")
        f = self._fader()
        liste = self.canvas._add_widget("VCCueList", QPoint(400, 10))
        ex = _FakeExecutor()
        liste._executor = lambda: ex
        draussen = self._taste(x=100)
        self.canvas.handy_konsole_automatisch_fuellen()
        self.canvas.setze_handy_seiten(
            hs.eintrag_entfernen(self.canvas.handy_seiten(), 0, draussen.widget_id))
        with mock.patch.object(type(f), "_apply"):
            f.value = 128
        self.state.output_manager.set_grand_master(0.5)
        k = self.fern.konsole()
        self.assertEqual(set(k["widgets"]), {t.widget_id, f.widget_id, liste.widget_id})
        self.assertEqual(k["widgets"][t.widget_id]["beschriftung"], "Strobe")
        self.assertEqual(k["widgets"][f.widget_id]["wert"], 128)
        self.assertEqual(k["widgets"][liste.widget_id]["cue"],
                         {"nummer": 1.0, "name": "Einlass"})
        self.assertEqual(k["widgets"][liste.widget_id]["naechste"],
                         {"nummer": 2.0, "name": "Strophe"})
        self.assertEqual(k["gm"], 128)
        self.assertIs(k["blackout"], False)
        self.assertEqual(k["seiten"], self.canvas.handy_seiten()["seiten"])

    def test_nicht_mehr_fernbedienbar_bleibt_als_leeres_feld(self):
        t = self._taste()
        self._auf_seite(t)
        t.action = ButtonAction.LASER_PATTERN       # nachtraeglich umgestellt
        k = self.fern.konsole()
        self.assertEqual(k["widgets"], {})
        self.assertEqual(len(k["seiten"][0]["eintraege"]), 1)   # Platz bleibt
        self.assertEqual(self.fern.aktion(t.widget_id, "umschalten",
                                          nur_handy_seiten=True)["fehler"],
                         "typ_nicht_erlaubt")

    def test_pult_setzt_grand_master_und_blackout(self):
        om = self.state.output_manager
        r = self.fern.pult(gm=64)
        self.assertEqual((r["ok"], r["gm"]), (True, 64))
        self.assertAlmostEqual(om.grand_master, 64 / 255, places=4)
        self.assertTrue(self.fern.pult(blackout=True)["blackout"])
        self.assertTrue(om.blackout)
        self.assertFalse(self.fern.pult(blackout=False)["blackout"])
        # kaputte Werte: abgelehnt, nichts verstellt
        for kaputt in ({"gm": "viel"}, {"gm": True}, {"gm": float("nan")},
                       {"blackout": "ja"}, {"blackout": 1}):
            self.assertEqual(self.fern.pult(**kaputt)["fehler"], "wert_ungueltig", kaputt)
        self.assertAlmostEqual(om.grand_master, 64 / 255, places=4)
        self.assertFalse(om.blackout)


# ── Rueckmeldung: der Takt der Bruecke ───────────────────────────────────────

class RueckmeldungTest(_Basis):

    def setUp(self):
        super().setUp()
        self.gesendet = []
        vc_remote.setze_sender(lambda ereignis, daten: self.gesendet.append((ereignis, daten)))

    def tearDown(self):
        vc_remote.zuschauer_weg("handy")
        super().tearDown()

    def test_ohne_zuschauer_wird_nichts_gemeldet(self):
        t = self._taste()
        self._auf_seite(t)
        self.fern._takt()
        t.fern_taste(True)
        self.fern._takt()
        self.assertEqual(self.gesendet, [])

    def test_aenderung_wird_als_delta_gemeldet(self):
        a = self._efx("WEB09 Push")
        t, andere = self._taste(fid=a.id, x=10), self._taste(x=100)
        f = self._fader()
        self._auf_seite(t, andere, f)
        vc_remote.zuschauer_dazu("handy")
        abgleich = self.fern.konsole()
        self.fern._takt()
        self.assertEqual(self.gesendet, [])                 # nichts geaendert

        # am Pult gedrueckt (nicht vom Handy): das Handy erfaehrt es
        t.fern_taste(True)
        t.fern_taste(False)
        self.fern._takt()
        self.assertEqual(len(self.gesendet), 1)
        ereignis, d = self.gesendet[0]
        self.assertEqual(ereignis, "vc_zustand")
        self.assertEqual(set(d["widgets"]), {t.widget_id})  # nur das geaenderte
        self.assertTrue(d["widgets"][t.widget_id]["aktiv"])
        self.assertEqual(d["rev"], abgleich["rev"] + 1)
        self.assertNotIn("gm", d)

        with mock.patch.object(type(f), "_apply"):
            f.value = 77
        self.state.output_manager.set_grand_master(0.25)
        self.state.output_manager.set_blackout(True)
        self.fern._takt()
        _e, d = self.gesendet[1]
        self.assertEqual(d["widgets"][f.widget_id]["wert"], 77)
        self.assertEqual(d["gm"], 64)
        self.assertIs(d["blackout"], True)
        self.assertEqual(d["rev"], abgleich["rev"] + 2)

    def test_gedrosselt_viele_aenderungen_eine_meldung(self):
        f = self._fader()
        self._auf_seite(f)
        vc_remote.zuschauer_dazu("handy")
        self.fern.konsole()
        with mock.patch.object(type(f), "_apply"):
            for v in range(0, 200):
                f.value = v
        self.fern._takt()
        self.fern._takt()
        self.assertEqual(len(self.gesendet), 1)
        self.assertEqual(self.gesendet[0][1]["widgets"][f.widget_id]["wert"], 199)
        self.assertEqual(self.fern._takt_timer.interval(), VCFernbedienung.TAKT_MS)
        self.assertTrue(self.fern._takt_timer.isActive())
        self.assertGreaterEqual(VCFernbedienung.TAKT_MS, 50)

    def test_geaenderte_seiten_gehen_als_ganzes_hinaus(self):
        t = self._taste()
        self._auf_seite(t)
        vc_remote.zuschauer_dazu("handy")
        self.fern.konsole()
        neu = self._taste(x=100, text="Neu")
        self.canvas.handy_konsole_automatisch_fuellen()
        self.fern._takt()
        ereignis, d = self.gesendet[-1]
        self.assertEqual(ereignis, "vc_konsole")
        self.assertTrue(d["aktiv"])
        self.assertEqual(set(d["widgets"]), {t.widget_id, neu.widget_id})
        self.assertEqual(d["seiten"], self.canvas.handy_seiten()["seiten"])

    def test_nur_die_angemeldete_bruecke_meldet(self):
        t = self._taste()
        self._auf_seite(t)
        andere = VCCanvas()
        self.addCleanup(andere.deleteLater)
        zweite = VCFernbedienung(andere)
        vc_remote.zuschauer_dazu("handy")
        self.fern.konsole()
        zweite._takt()
        zweite._takt()
        self.assertEqual(self.gesendet, [])

    def test_abgeschaltet_wird_nichts_gesendet(self):
        t = self._taste()
        self._auf_seite(t)
        vc_remote.zuschauer_dazu("handy")
        self.fern.konsole()
        remote_settings.set_vc_remote_enabled(False)
        t.fern_taste(True)
        self.fern._takt()
        self.assertEqual(self.gesendet, [])


# ── Loslassen ────────────────────────────────────────────────────────────────

class LoslassenTest(_Basis):

    def test_zuschauer_weg_laesst_seine_tasten_los(self):
        a, b = self._efx("WEB09 Halt A"), self._efx("WEB09 Halt B")
        ta = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id, x=10)
        tb = self._taste(ButtonAction.FUNCTION_FLASH, fid=b.id, x=100)
        self._auf_seite(ta, tb)
        for handy, t in (("eins", ta), ("zwei", tb)):
            vc_remote.zuschauer_dazu(handy)
            self.assertTrue(vc_remote.widget_aktion(t.widget_id, "druecken")["ok"])
            vc_remote.gehalten_merken(handy, t.widget_id, True)
        self.assertTrue(self.fm.is_running(a.id) and self.fm.is_running(b.id))
        vc_remote.zuschauer_weg("eins")
        self.assertFalse(ta._pressed)
        self.assertFalse(self.fm.is_running(a.id))
        self.assertTrue(tb._pressed)                     # das andere Handy haelt weiter
        self.assertEqual(vc_remote.gehaltene(), {tb.widget_id})
        vc_remote.alle_loslassen()
        self.assertFalse(tb._pressed)
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_loslassen_wartet_nicht_auf_die_oberflaeche(self):
        # Verbindungsabbruch kommt aus dem Web-Thread. Ist die Oberflaeche
        # gerade beschaeftigt, darf das Loslassen weder haengen noch verfallen.
        a = self._efx("WEB09 Halt Thread")
        t = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id)
        t.fern_taste(True)
        self.assertTrue(self.fm.is_running(a.id))
        with mock.patch.object(VCFernbedienung, "ZEITLIMIT_S", 0.05):
            faden = threading.Thread(target=self.fern.loslassen, args=([t.widget_id],))
            faden.start()
            faden.join(timeout=2.0)
            self.assertFalse(faden.is_alive(), "Loslassen blockiert den Web-Thread")
            self.assertTrue(t._pressed)                  # UI hat noch nichts abgearbeitet
            import time
            time.sleep(0.15)                             # laenger als jedes Zeitlimit
        _app.processEvents()
        self.assertFalse(t._pressed)
        self.assertFalse(self.fm.is_running(a.id))

    def test_loslassen_geht_auch_ohne_freigabe(self):
        a = self._efx("WEB09 Halt Seite weg")
        t = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id)
        self._auf_seite(t)
        vc_remote.zuschauer_dazu("handy")
        vc_remote.widget_aktion(t.widget_id, "druecken")
        vc_remote.gehalten_merken("handy", t.widget_id, True)
        self.canvas.setze_handy_seiten(hs.leer())        # waehrend gehalten wird
        vc_remote.zuschauer_weg("handy")
        self.assertFalse(t._pressed)
        self.assertFalse(self.fm.is_running(a.id))

    def test_ausschalten_laesst_los(self):
        a = self._efx("WEB09 Halt Aus")
        t = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id)
        self._auf_seite(t)
        vc_remote.zuschauer_dazu("handy")
        vc_remote.widget_aktion(t.widget_id, "druecken")
        vc_remote.gehalten_merken("handy", t.widget_id, True)
        gesendet = []
        vc_remote.setze_sender(lambda e, d: gesendet.append((e, d)))
        remote_settings.set_vc_remote_enabled(False)
        vc_remote.einstellung_geaendert()
        self.assertFalse(t._pressed)
        self.assertEqual(gesendet[-1][0], "vc_konsole")
        self.assertIs(gesendet[-1][1]["aktiv"], False)
        self.assertEqual(gesendet[-1][1]["seiten"], [])

    def test_blackout_taste_wird_losgelassen(self):
        t = self._taste(ButtonAction.BLACKOUT)
        self._auf_seite(t)
        vc_remote.zuschauer_dazu("handy")
        vc_remote.widget_aktion(t.widget_id, "druecken")
        vc_remote.gehalten_merken("handy", t.widget_id, True)
        self.assertTrue(self.state.output_manager.blackout)
        vc_remote.zuschauer_weg("handy")
        self.assertFalse(self.state.output_manager.blackout)


# ── HTTP ─────────────────────────────────────────────────────────────────────

@unittest.skipUnless(HAS_FLASK, "flask / flask-socketio nicht installiert")
class _WebBasis(_Basis):
    def setUp(self):
        super().setUp()
        import src.web.app as webapp
        self.webapp = webapp
        self.app, self.sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.app.config["LIGHTOS_REMOTE_TOKEN"] = "geheim123"
        self.client = self.app.test_client()

    def _anmelden(self, client=None):
        self.assertEqual((client or self.client).get("/?k=geheim123").status_code, 200)

    def _aktion(self, kennung, **daten):
        return self.client.post(f"/api/vc/widget/{kennung}/aktion", json=daten)

    def _socket(self, client=None):
        sc = self.sio.test_client(self.app, flask_test_client=client or self.client)
        self.addCleanup(lambda: sc.is_connected() and sc.disconnect())
        return sc

    @staticmethod
    def _empfangen(sc, name):
        return [m["args"][0] for m in sc.get_received() if m["name"] == name]


class FreigabeHttpTest(_WebBasis):

    def test_widget_ausserhalb_der_seiten_403(self):
        a, b = self._efx("WEB09 Http drauf"), self._efx("WEB09 Http draussen")
        drauf, draussen = self._taste(fid=a.id, x=10), self._taste(fid=b.id, x=100)
        self._auf_seite(drauf)
        self._anmelden()
        r = self._aktion(draussen.widget_id, aktion="umschalten")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json(), {"ok": False, "fehler": "nicht_freigegeben"})
        self.assertFalse(self.fm.is_running(b.id))
        self.assertEqual(self._aktion(drauf.widget_id, aktion="umschalten").status_code, 200)
        self.assertTrue(self.fm.is_running(a.id))
        # die Liste nennt nur das freigegebene
        liste = self.client.get("/api/vc/widgets").get_json()
        self.assertEqual([w["id"] for w in liste["widgets"]], [drauf.widget_id])

    def test_fader_ausserhalb_403_und_unveraendert(self):
        f = self._fader()
        self._anmelden()
        with mock.patch.object(type(f), "_apply"):
            f.value = 10
            r = self._aktion(f.widget_id, aktion="setzen", wert=200)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(f.value, 10)

    def test_konsole_abruf(self):
        t = self._taste(text="Strobe")
        self._taste(x=100, text="Geheim")
        self._auf_seite(t)
        self.assertEqual(self.client.get("/api/vc/konsole").status_code, 403)
        self._anmelden()
        k = self.client.get("/api/vc/konsole").get_json()
        self.assertTrue(k["ok"] and k["aktiv"])
        self.assertEqual(list(k["widgets"]), [t.widget_id])
        self.assertEqual(k["seiten"][0]["name"], "Test")
        self.assertNotIn("Geheim", self.client.get("/api/vc/konsole").get_data(as_text=True))

    def test_konsole_abgeschaltet_ist_leer(self):
        t = self._taste()
        self._auf_seite(t)
        remote_settings.set_vc_remote_enabled(False)
        self._anmelden()
        k = self.client.get("/api/vc/konsole").get_json()
        self.assertEqual((k["aktiv"], k["seiten"], k["widgets"]), (False, [], {}))
        r = self.client.post("/api/vc/pult", json={"gm": 0})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.state.output_manager.grand_master, 1.0)

    def test_pult_ueber_http(self):
        self._anmelden()
        r = self.client.post("/api/vc/pult", json={"gm": 128})
        self.assertEqual((r.status_code, r.get_json()["gm"]), (200, 128))
        self.assertEqual(self.client.post("/api/vc/pult", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/vc/pult", json=[1]).status_code, 400)
        self.assertEqual(self.client.post("/api/vc/pult", json={"gm": "x"}).status_code, 400)
        frisch = self.app.test_client()
        self.assertEqual(frisch.post("/api/vc/pult", json={"gm": 0}).status_code, 403)
        self.assertAlmostEqual(self.state.output_manager.grand_master, 128 / 255, places=4)

    def test_laser_sicherheit_gilt_auch_auf_der_seite(self):
        # Auf einer Handy-Seite zu liegen hebt keine der WEB-08-Sperren auf.
        scharf = self._taste(ButtonAction.LASER_ARM, x=10)
        muster = self._taste(ButtonAction.LASER_PATTERN, x=100)
        self._auf_seite(scharf, muster)
        self._anmelden()
        with mock.patch.object(type(scharf), "_aktionszustand", return_value=False), \
                mock.patch.object(type(scharf), "_trigger") as ausgeloest:
            r = self._aktion(scharf.widget_id, aktion="umschalten")
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.get_json()["fehler"], "nur_am_pult")
            r = self._aktion(muster.widget_id, aktion="umschalten")
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.get_json()["fehler"], "typ_nicht_erlaubt")
            ausgeloest.assert_not_called()
        self.assertNotIn(muster.widget_id,
                         self.client.get("/api/vc/konsole").get_json()["widgets"])

    def test_aktionen_laufen_mit_notaus_sperre(self):
        from src.core import app_state
        t = self._taste()
        self._auf_seite(t)
        self._anmelden()
        gesehen = []
        with mock.patch.object(type(t), "_trigger",
                               lambda _s, _p: gesehen.append(
                                   app_state.laser_notaus_loesen_gesperrt())):
            self.assertEqual(self._aktion(t.widget_id, aktion="umschalten").status_code, 200)
        self.assertEqual(gesehen, [True, True])


# ── Socket ───────────────────────────────────────────────────────────────────

class SocketTest(_WebBasis):

    def test_ohne_schluessel_keine_verbindung(self):
        sc = self.sio.test_client(self.app, flask_test_client=self.app.test_client())
        self.assertFalse(sc.is_connected())

    def test_abgleich_beim_verbinden(self):
        t = self._taste(text="Strobe")
        self._taste(x=100, text="Geheim")
        self._auf_seite(t)
        self._anmelden()
        sc = self._socket()
        self.assertTrue(sc.is_connected())
        self.assertEqual(sc.emit("vc_hallo", {}, callback=True), {"ok": True})
        k = self._empfangen(sc, "vc_konsole")[-1]
        self.assertTrue(k["aktiv"])
        self.assertEqual(list(k["widgets"]), [t.widget_id])
        self.assertEqual(vc_remote.zuschauer(), 1)

    def test_push_bei_aenderung_am_pult(self):
        a = self._efx("WEB09 Socket Push")
        t = self._taste(fid=a.id)
        self._auf_seite(t)
        self._anmelden()
        sc = self._socket()
        sc.emit("vc_hallo", {}, callback=True)
        rev = self._empfangen(sc, "vc_konsole")[-1]["rev"]
        self.fern._takt()
        self.assertEqual(self._empfangen(sc, "vc_zustand"), [])
        t.fern_taste(True)                               # jemand drueckt am Pult
        t.fern_taste(False)
        self.fern._takt()
        meldungen = self._empfangen(sc, "vc_zustand")
        self.assertEqual(len(meldungen), 1)
        self.assertTrue(meldungen[0]["widgets"][t.widget_id]["aktiv"])
        self.assertEqual(meldungen[0]["rev"], rev + 1)

    def test_push_geht_nur_an_zuschauer(self):
        t = self._taste()
        self._auf_seite(t)
        self._anmelden()
        zuschauer = self._socket()
        zuschauer.emit("vc_hallo", {}, callback=True)
        fest = self._socket()                            # die feste Seite: kein vc_hallo
        zuschauer.get_received()
        fest.get_received()
        t.fern_taste(True)
        self.fern._takt()
        self.assertEqual(len(self._empfangen(zuschauer, "vc_zustand")), 1)
        self.assertEqual(fest.get_received(), [])

    def test_wiederverbindung_bekommt_den_ganzen_stand(self):
        a = self._efx("WEB09 Socket Wieder")
        t = self._taste(fid=a.id)
        f = self._fader()
        self._auf_seite(t, f)
        self._anmelden()
        sc = self._socket()
        sc.emit("vc_hallo", {}, callback=True)
        sc.disconnect()
        self.assertEqual(vc_remote.zuschauer(), 0)
        # waehrend das Handy weg ist, aendert sich das Pult
        t.fern_taste(True)
        t.fern_taste(False)
        with mock.patch.object(type(f), "_apply"):
            f.value = 42
        self.state.output_manager.set_blackout(True)
        self.fern._takt()
        sc2 = self._socket()
        sc2.emit("vc_hallo", {}, callback=True)
        k = self._empfangen(sc2, "vc_konsole")[-1]
        self.assertTrue(k["widgets"][t.widget_id]["aktiv"])
        self.assertEqual(k["widgets"][f.widget_id]["wert"], 42)
        self.assertIs(k["blackout"], True)
        # und ab hier laufen die Meldungen lueckenlos weiter
        self.state.output_manager.set_blackout(False)
        self.fern._takt()
        d = self._empfangen(sc2, "vc_zustand")[-1]
        self.assertEqual(d, {"blackout": False, "rev": k["rev"] + 1})

    def test_aktion_ueber_den_socket(self):
        a = self._efx("WEB09 Socket Aktion")
        t = self._taste(fid=a.id)
        draussen = self._taste(x=100)
        liste = self.canvas._add_widget("VCCueList", QPoint(400, 10))
        ex = _FakeExecutor()
        liste._executor = lambda: ex
        self._auf_seite(t, liste)
        self._anmelden()
        sc = self._socket()
        r = sc.emit("vc_aktion", {"id": t.widget_id, "aktion": "umschalten"}, callback=True)
        self.assertTrue(r["ok"])
        self.assertTrue(r["widget"]["aktiv"])
        self.assertTrue(self.fm.is_running(a.id))
        r = sc.emit("vc_aktion", {"id": liste.widget_id, "aktion": "go"}, callback=True)
        self.assertEqual(r["widget"]["cue"], {"nummer": 2.0, "name": "Strophe"})
        r = sc.emit("vc_aktion", {"id": draussen.widget_id, "aktion": "umschalten"},
                    callback=True)
        self.assertEqual(r, {"ok": False, "fehler": "nicht_freigegeben"})
        self.assertFalse(draussen._pressed)
        for kaputt in (None, "text", [1], {}, {"id": 5, "aktion": "go"}):
            r = sc.emit("vc_aktion", kaputt, callback=True)
            self.assertFalse(r["ok"], kaputt)

    def test_fader_fluessig_und_in_der_richtigen_reihenfolge(self):
        f = self._fader()
        self._auf_seite(f)
        self._anmelden()
        sc = self._socket()
        with mock.patch.object(type(f), "_apply"):
            for n, v in enumerate(range(0, 256, 5), start=1):
                r = sc.emit("vc_aktion", {"id": f.widget_id, "aktion": "setzen",
                                          "wert": v, "n": n}, callback=True)
                self.assertTrue(r["ok"])
            self.assertEqual(f.value, 255)
            # ein verspaeteter aelterer Wert ueberholt den neueren nicht
            r = sc.emit("vc_aktion", {"id": f.widget_id, "aktion": "setzen",
                                      "wert": 3, "n": 2}, callback=True)
            self.assertEqual(r, {"ok": True, "veraltet": True})
            self.assertEqual(f.value, 255)
            # ohne Nummer wird immer ausgefuehrt (HTTP-artige Aufrufer)
            sc.emit("vc_aktion", {"id": f.widget_id, "aktion": "setzen", "wert": 9},
                    callback=True)
            self.assertEqual(f.value, 9)

    def test_pult_ueber_den_socket(self):
        self._anmelden()
        sc = self._socket()
        r = sc.emit("vc_pult", {"gm": 51, "n": 5}, callback=True)
        self.assertEqual((r["ok"], r["gm"]), (True, 51))
        r = sc.emit("vc_pult", {"gm": 200, "n": 4}, callback=True)   # verspaetet
        self.assertTrue(r.get("veraltet"))
        self.assertAlmostEqual(self.state.output_manager.grand_master, 0.2, places=3)
        r = sc.emit("vc_pult", {"blackout": True}, callback=True)
        self.assertTrue(r["blackout"])
        self.assertTrue(self.state.output_manager.blackout)

    def test_gehaltene_taste_wird_bei_abbruch_losgelassen(self):
        a = self._efx("WEB09 Socket Halt")
        flash = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id, x=10)
        dunkel = self._taste(ButtonAction.BLACKOUT, x=100)
        self._auf_seite(flash, dunkel)
        self._anmelden()
        sc = self._socket()
        sc.emit("vc_hallo", {}, callback=True)
        self.assertEqual(sc.emit("vc_aktion", {"id": flash.widget_id, "aktion": "druecken"},
                                 callback=True)["widget"]["bedienung"], "halten")
        sc.emit("vc_aktion", {"id": dunkel.widget_id, "aktion": "druecken"}, callback=True)
        self.assertTrue(self.fm.is_running(a.id))
        self.assertTrue(self.state.output_manager.blackout)
        sc.disconnect()                                  # WLAN weg
        self.assertFalse(flash._pressed)
        self.assertFalse(self.fm.is_running(a.id))
        self.assertFalse(dunkel._pressed)
        self.assertFalse(self.state.output_manager.blackout)
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_ordentlich_losgelassen_bleibt_bei_abbruch_unberuehrt(self):
        a = self._efx("WEB09 Socket Halt2")
        flash = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id)
        self._auf_seite(flash)
        self._anmelden()
        sc = self._socket()
        sc.emit("vc_aktion", {"id": flash.widget_id, "aktion": "druecken"}, callback=True)
        sc.emit("vc_aktion", {"id": flash.widget_id, "aktion": "loslassen"}, callback=True)
        self.assertEqual(vc_remote.gehaltene(), set())
        flash.fern_taste(True)                           # jetzt haelt jemand am Pult
        sc.disconnect()
        self.assertTrue(flash._pressed)                  # nicht vom Handy gehalten

    def test_loslassen_das_nicht_ankommt_wird_nachgeholt(self):
        """Antwortet die Oberflaeche beim Loslassen nicht rechtzeitig, darf die
        Taste nicht haengen bleiben: sie gilt danach nicht mehr als gehalten,
        ein Verbindungsabbruch liesse sie also auch nicht mehr los."""
        a = self._efx("WEB09 Socket Halt3")
        flash = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id)
        self._auf_seite(flash)
        self._anmelden()
        sc = self._socket()
        sc.emit("vc_aktion", {"id": flash.widget_id, "aktion": "druecken"}, callback=True)
        self.assertTrue(flash._pressed)
        with mock.patch.object(self.fern, "aktion",
                               return_value={"ok": False, "fehler": "zeitueberschreitung"}):
            r = sc.emit("vc_aktion", {"id": flash.widget_id, "aktion": "loslassen"},
                        callback=True)
        self.assertEqual(r["fehler"], "zeitueberschreitung")
        self.assertFalse(flash._pressed)
        self.assertFalse(self.fm.is_running(a.id))
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_gehalten_und_von_der_seite_genommen_wird_losgelassen(self):
        a = self._efx("WEB09 Socket Halt4")
        flash = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id)
        self._auf_seite(flash)
        self._anmelden()
        sc = self._socket()
        sc.emit("vc_aktion", {"id": flash.widget_id, "aktion": "druecken"}, callback=True)
        self.canvas.setze_handy_seiten(hs.leer())
        r = sc.emit("vc_aktion", {"id": flash.widget_id, "aktion": "loslassen"},
                    callback=True)
        self.assertEqual(r["fehler"], "nicht_freigegeben")
        self.assertFalse(flash._pressed)

    def test_loslassen_ohne_eigenen_druck_holt_nichts_nach(self):
        """Der Nachhol-Weg prueft keine Freigabe — er darf deshalb nur greifen,
        wenn DIESES Handy die Taste hielt. Eine am Pult gehaltene Taste
        ausserhalb der Seiten bleibt gedrueckt."""
        draussen = self._taste(ButtonAction.FUNCTION_FLASH)
        draussen.fern_taste(True)
        self._anmelden()
        sc = self._socket()
        r = sc.emit("vc_aktion", {"id": draussen.widget_id, "aktion": "loslassen"},
                    callback=True)
        self.assertEqual(r["fehler"], "nicht_freigegeben")
        self.assertTrue(draussen._pressed)

    def test_kennung_die_kein_text_ist_wird_abgelehnt(self):
        self._anmelden()
        sc = self._socket()
        for kennung in ([1], {"a": 1}, 5, None):
            for aktion in ("setzen", "druecken", "loslassen", ["go"]):
                r = sc.emit("vc_aktion", {"id": kennung, "aktion": aktion, "wert": 1,
                                          "n": 1}, callback=True)
                self.assertEqual(r, {"ok": False, "fehler": "anfrage_ungueltig"})

    def test_abgelehnter_druck_gilt_nicht_als_gehalten(self):
        draussen = self._taste(ButtonAction.FUNCTION_FLASH)
        self._anmelden()
        sc = self._socket()
        r = sc.emit("vc_aktion", {"id": draussen.widget_id, "aktion": "druecken"},
                    callback=True)
        self.assertFalse(r["ok"])
        self.assertEqual(vc_remote.gehaltene(), set())

    def test_schluesselwechsel_sperrt_die_offene_verbindung(self):
        # Die Verbindung wurde mit gueltigem Schluessel aufgebaut. Nach „Token
        # neu erzeugen" darf sie nichts mehr ausloesen — auch wenn sie (anders
        # als im laufenden Server) noch nicht getrennt wurde.
        a = self._efx("WEB09 Socket Epoche")
        t = self._taste(fid=a.id)
        f = self._fader()
        self._auf_seite(t, f)
        with mock.patch.object(type(f), "_apply"):
            f._value = 10
            for ereignis, daten in (
                    ("vc_aktion", {"id": t.widget_id, "aktion": "umschalten"}),
                    ("vc_aktion", {"id": f.widget_id, "aktion": "setzen", "wert": 200}),
                    ("vc_pult", {"gm": 0}),
                    ("vc_pult", {"blackout": True}),
                    ("vc_hallo", {})):
                handy = self.app.test_client()
                self._anmelden(handy)
                sc = self._socket(handy)
                self.assertTrue(sc.emit("vc_hallo", {}, callback=True)["ok"], ereignis)
                remote_settings.regenerate_token()
                r = sc.emit(ereignis, daten, callback=True)
                self.assertEqual(r, {"ok": False, "fehler": "kein_zugang"}, ereignis)
                self.assertFalse(sc.is_connected(), ereignis)    # und sie wird getrennt
                # mit dem alten Anmelde-Cookie kommt keine neue Verbindung zustande
                self.assertFalse(self.sio.test_client(
                    self.app, flask_test_client=handy).is_connected())
        self.assertFalse(self.fm.is_running(a.id))
        self.assertEqual(f.value, 10)
        self.assertEqual(self.state.output_manager.grand_master, 1.0)
        self.assertFalse(self.state.output_manager.blackout)
        self.assertEqual(vc_remote.zuschauer(), 0)

    def test_abgeschaltet_am_socket(self):
        a = self._efx("WEB09 Socket Aus")
        t = self._taste(fid=a.id)
        self._auf_seite(t)
        self._anmelden()
        sc = self._socket()
        remote_settings.set_vc_remote_enabled(False)
        r = sc.emit("vc_aktion", {"id": t.widget_id, "aktion": "umschalten"}, callback=True)
        self.assertEqual(r, {"ok": False, "fehler": "abgeschaltet"})
        self.assertEqual(sc.emit("vc_pult", {"gm": 0}, callback=True)["fehler"],
                         "abgeschaltet")
        sc.emit("vc_hallo", {}, callback=True)
        self.assertIs(self._empfangen(sc, "vc_konsole")[-1]["aktiv"], False)
        self.assertFalse(self.fm.is_running(a.id))

    def test_server_stopp_laesst_los_und_meldet_ab(self):
        a = self._efx("WEB09 Socket Stopp")
        flash = self._taste(ButtonAction.FUNCTION_FLASH, fid=a.id)
        self._auf_seite(flash)
        vc_remote.zuschauer_dazu("handy")
        vc_remote.widget_aktion(flash.widget_id, "druecken")
        vc_remote.gehalten_merken("handy", flash.widget_id, True)
        self.webapp.stop_server()
        self.assertFalse(flash._pressed)
        self.assertEqual(vc_remote.zuschauer(), 0)
        self.assertFalse(vc_remote.melde("vc_zustand", {}))

    def test_bestehende_ereignisse_der_festen_seite_bleiben(self):
        self._anmelden()
        sc = self._socket()
        sc.emit("blackout", {"enabled": True})
        self.assertTrue(self.state.output_manager.blackout)
        sc.emit("blackout", {"enabled": False})
        self.assertFalse(self.state.output_manager.blackout)


# ── Die Seite ────────────────────────────────────────────────────────────────

class SeiteTest(_WebBasis):

    def test_seite_wird_ausgeliefert_und_macht_den_handshake(self):
        r = self.client.get("/konsole")
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r.headers.get("Cache-Control", ""))
        # ohne Schluessel: die Huelle ja, Daten nein
        self.assertEqual(self.client.get("/api/vc/konsole").status_code, 403)
        self.assertEqual(self.client.get("/konsole?k=falsch").status_code, 200)
        self.assertEqual(self.client.get("/api/vc/konsole").status_code, 403)
        # der Link mit Schluessel meldet an — er taugt als Lesezeichen
        self.assertEqual(self.client.get("/konsole?k=geheim123").status_code, 200)
        self.assertEqual(self.client.get("/api/vc/konsole").status_code, 200)

    def test_huelle_traegt_keine_daten_der_show(self):
        t = self._taste(text="StrengGeheimeTaste")
        self._auf_seite(t)
        html = self.client.get("/konsole?k=geheim123").get_data(as_text=True)
        self.assertNotIn("StrengGeheimeTaste", html)
        self.assertNotIn(t.widget_id, html)
        self.assertNotIn("geheim123", html)

    def test_keine_externen_adressen(self):
        html = self.client.get("/konsole").get_data(as_text=True)
        self.assertEqual(re.findall(_EXTERN, html), [])
        # jede eingebundene Datei kommt vom eigenen Server
        quellen = re.findall(r"""(?i)(?:src|href)\s*=\s*["']([^"']+)["']""", html)
        self.assertIn("/static/socket.io.min.js", quellen)
        for q in quellen:
            self.assertTrue(q.startswith("/") and not q.startswith("//"), q)
        # WEB-11: <link> gibt es jetzt (Manifest, Symbole) — die Schleife oben
        # prueft, dass auch ihre Ziele vom eigenen Server kommen.
        self.assertNotRegex(html, r"(?i)@import|url\s*\(|<img\b|<iframe\b")
        self.assertEqual(self.client.get("/static/socket.io.min.js").status_code, 200)

    def test_vorlage_selbst_ist_frei_von_externen_adressen(self):
        with open(os.path.join(_VORLAGEN, "konsole.html"), encoding="utf-8") as f:
            roh = f.read()
        self.assertEqual(re.findall(_EXTERN, roh), [])

    def test_seite_sperrt_zoom_und_scrollen(self):
        html = self.client.get("/konsole").get_data(as_text=True)
        self.assertRegex(html, r'name="viewport"[^>]*user-scalable=no')
        self.assertIn("maximum-scale=1", html)
        self.assertIn("touch-action:none", html)
        self.assertIn("overscroll-behavior:none", html)
        self.assertIn("overflow:hidden", html)
        for ereignis in ("gesturestart", "contextmenu", "touchmove"):
            self.assertIn(ereignis, html)

    def test_seite_spricht_die_schnittstelle_die_es_gibt(self):
        html = self.client.get("/konsole").get_data(as_text=True)
        for teil in ("vc_hallo", "vc_aktion", "vc_pult", "vc_konsole", "vc_zustand",
                     "/api/vc/konsole", "druecken", "loslassen", "umschalten",
                     "setzen", "'go'", "'back'", "'stop'"):
            self.assertIn(teil, html, teil)
        # bei getrennter Verbindung ist die Bedienung gesperrt
        self.assertIn('id="sperre"', html)
        self.assertIn("Bedienung gesperrt", html)

    def test_feste_seite_verlinkt_nur_wenn_eingeschaltet(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/konsole"', html)
        remote_settings.set_vc_remote_enabled(False)
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("/konsole", html)
        self.assertIn("LightOS Remote", html)            # die Seite selbst bleibt


# ── Der Schalter im Dialog ───────────────────────────────────────────────────

class SchalterTest(unittest.TestCase):

    def setUp(self):
        remote_settings.set_vc_remote_enabled(False)
        self.addCleanup(remote_settings.set_vc_remote_enabled, False)

    def _dialog(self):
        import types
        from PySide6.QtWidgets import QCheckBox, QDialog, QLineEdit, QWidget
        from src.ui import main_window as mw

        class _Fenster(QWidget):
            def statusBar(self):
                return types.SimpleNamespace(showMessage=lambda *a, **k: None)

        fenster = _Fenster()
        self.addCleanup(fenster.deleteLater)
        gebaut = {}

        def _exec(dlg):
            gebaut["haken"] = dlg.findChild(QCheckBox, "web_remote_handy_konsole")
            gebaut["link"] = dlg.findChild(QLineEdit, "web_remote_konsole_link")
            return 0

        for ziel, name, wert in ((QDialog, "exec", _exec),
                                 (remote_settings, "get_token", lambda: "abc")):
            fleck = mock.patch.object(ziel, name, wert)
            fleck.start()
            self.addCleanup(fleck.stop)
        mw.MainWindow._open_web_remote_dialog(fenster)
        return gebaut

    def test_standard_aus_und_sichtbarer_schalter(self):
        self.assertIs(remote_settings.DEFAULTS["vc_remote_enabled"], False)
        g = self._dialog()
        self.assertIsNotNone(g["haken"], "Schalter „Handy-Konsole“ fehlt im Dialog")
        self.assertIn("Handy-Konsole", g["haken"].text())
        self.assertFalse(g["haken"].isChecked())
        self.assertTrue(g["link"].isHidden())

    def test_schalter_schaltet_ein_und_aus(self):
        g = self._dialog()
        with mock.patch.object(vc_remote, "einstellung_geaendert") as gemeldet:
            g["haken"].setChecked(True)
            self.assertTrue(remote_settings.is_vc_remote_enabled())
            self.assertFalse(g["link"].isHidden())
            self.assertTrue(g["link"].text().endswith("/konsole?k=abc"))
            g["haken"].setChecked(False)
            self.assertFalse(remote_settings.is_vc_remote_enabled())
            self.assertTrue(g["link"].isHidden())
            self.assertEqual(gemeldet.call_count, 2)


if __name__ == "__main__":
    unittest.main()
