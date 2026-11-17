"""VCB-50 (Herkunft WEB-16): zwei weitere Anzeigen eines Executor-Pegels folgen
einem Wert von AUSSEN (Web/Socket, OSC, MIDI-Mapping, Executor-Leiste — alle
schreiben nur ``Executor.fader_value``, ein Ereignis dafuer gibt es nicht).

1. **VC-Schieberegler im Modus „Playback (Executor)“** (``vc_slider.py``) im
   vorhandenen 400-ms-Statustakt der Virtuellen Konsole:

   * nur Anzeige — 0 Schreibzugriffe in die Engine (gezaehlt);
   * Invert und Bereich richtig zurueckgerechnet, ausserhalb des Bereichs
     geklemmt ohne Flattern; Toleranz ein Reglerschritt;
   * gehalten (Maus und Finger) bleibt er stehen; danach gilt der Bedienerwert,
     die naechste Beruehrung springt nicht;
   * Soft-Takeover: nach dem Nachziehen armiert (Pult-Fader uebernimmt erst
     beim Durchfahren); Motorfader faehrt einmal nach, der Bericht der
     Motorfahrt ist keine Eingabe (MIDI-Attrappe: kein Ping-Pong);
   * andere Modi und der Bearbeiten-Modus bleiben unveraendert;
   * Seitenwechsel: der Regler zeigt den Pegel der neuen Seite.

2. **Feste Fernbedienung im Browser** (``templates/index.html``): holt den
   Stand ueber den vorhandenen Statusweg ``/api/status`` regelmaessig (1 s, nur
   bei sichtbarer Seite) und zieht die Fader nach, ausser dem gehaltenen; das
   Nachziehen sendet nichts. Wie die vorhandenen Web-Tests wird das Skript als
   Text geprueft; der Statusweg ueber den Flask-Test-Client.

Keine echten App-Daten: Sandkasten-AppState aus ``conftest``.
"""
from __future__ import annotations

import os
import re
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_PREFS_DIR",
                      tempfile.mkdtemp(prefix="lightos_prefs_vcb50_"))

from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

import src.core.midi.midi_manager as mgr                             # noqa: E402
from src.core.app_state import get_state                             # noqa: E402
from src.core.midi.midi_mapper import MOTOR_ECHO_FENSTER_S           # noqa: E402
from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider     # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _warte_auf(bedingung, ms: int) -> bool:
    """Auf eine Bedingung warten (kein enger Timer)."""
    ende = time.monotonic() + ms / 1000.0
    while time.monotonic() < ende:
        if bedingung():
            return True
        QTest.qWait(10)
    return bool(bedingung())


def _zaehl_klasse(basis):
    """Executor-Unterklasse, die jeden Schreibzugriff auf ``fader_value`` zaehlt."""

    class _Gezaehlt(basis):
        @property
        def fader_value(self):
            return self.__dict__["_vcb50_fv"]

        @fader_value.setter
        def fader_value(self, v):
            self.__dict__["_vcb50_schreib"] = self.__dict__.get("_vcb50_schreib", 0) + 1
            self.__dict__["_vcb50_fv"] = v

    return _Gezaehlt


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class _FakeMM:
    """MIDI-Attrappe: zeichnet Motor-Sendungen auf (kein echtes Geraet)."""

    def __init__(self):
        self.pb: list[tuple[int, int]] = []

    def send_pitchbend(self, kanal, wert):
        self.pb.append((kanal, wert))
        return True

    def current_output_name(self):
        return "X-Touch"


def _pb(kanal: int, wert14: int):
    return mgr._decode([0xE0 | (kanal - 1), wert14 & 0x7F, (wert14 >> 7) & 0x7F], "X-Touch")


def _cc(kanal: int, nummer: int, wert: int):
    return mgr._decode([0xB0 | (kanal - 1), nummer, wert], "APC")


class _Basis(unittest.TestCase):
    """Executor 1 der Seiten 0 und 1 zaehlen Schreibzugriffe; der Fader steht
    im Modus PLAYBACK auf Slot 0 und zeigt 100 %."""

    def setUp(self):
        VCSlider.soft_takeover = False
        self.addCleanup(setattr, VCSlider, "soft_takeover", False)
        self.state = get_state()
        self.pe = self.state.playback_engine
        self._orig_page = self.pe.current_page
        self.pe.current_page = 0
        self.addCleanup(setattr, self.pe, "current_page", self._orig_page)
        self.ex = self._zaehlen(self.pe.pages[0][0], 1.0)
        self.ex2 = self._zaehlen(self.pe.pages[1][0], 1.0)
        self.s = self._fader()

    def _zaehlen(self, ex, wert):
        orig = (ex.__class__, ex.fader_value, ex.fader_function)
        ex.fader_function = "volume"
        ex.__class__ = _zaehl_klasse(orig[0])
        ex.__dict__["_vcb50_fv"] = wert
        ex.__dict__["_vcb50_schreib"] = 0

        def zurueck():
            ex.__dict__.pop("_vcb50_fv", None)
            ex.__dict__.pop("_vcb50_schreib", None)
            ex.__class__ = orig[0]
            ex.fader_value = orig[1]
            ex.fader_function = orig[2]
        self.addCleanup(zurueck)
        return ex

    def _fader(self, parent=None):
        s = VCSlider("Ex 1", parent)
        s.mode = SliderMode.PLAYBACK
        s.playback_slot = 0
        s._value = 255
        s.resize(60, 260)
        return s

    def schreib(self, ex=None) -> int:
        return (ex or self.ex).__dict__.get("_vcb50_schreib", 0)

    def von_aussen(self, v: float, ex=None):
        (ex or self.ex).__dict__["_vcb50_fv"] = v     # wie Web/OSC/MIDI, ungezaehlt


# ── 1. VC-Schieberegler ──────────────────────────────────────────────────────

class NachziehenTest(_Basis):
    def test_folgt_aussenwert_ohne_schreibzugriff(self):
        self.von_aussen(0.5)
        self.assertTrue(self.s.pegel_nachziehen(), "ohne Fix: Regler bleibt auf 255")
        self.assertEqual(self.s.value, 128)
        self.assertEqual(self.s._effective_value(), 128)
        for _ in range(5):
            self.assertFalse(self.s.pegel_nachziehen(), "nur bei Aenderung")
        self.assertEqual(self.schreib(), 0)
        self.assertEqual(self.ex.fader_value, 0.5)

    def test_toleranz_ein_reglerschritt(self):
        self.von_aussen(254.6 / 255)           # rundet auf 255: keine Aenderung
        self.assertFalse(self.s.pegel_nachziehen())
        self.von_aussen(254.0 / 255)           # ein Schritt: bleibt stehen
        self.assertFalse(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 255)
        self.von_aussen(253.0 / 255)           # zwei Schritte: zieht nach
        self.assertTrue(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 253)
        self.assertEqual(self.schreib(), 0)

    def test_invert(self):
        self.s.invert = True
        self.s._value = 0                      # invertiert: unten = voll
        self.von_aussen(0.25)
        self.assertTrue(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 255 - 64)
        self.assertEqual(self.s._effective_value(), 64)
        self.assertFalse(self.s.pegel_nachziehen())
        self.assertEqual(self.schreib(), 0)

    def test_bereich_und_klemmen_ohne_flattern(self):
        self.s.range_min, self.s.range_max = 50, 150
        self.s._value = 0
        self.von_aussen(102 / 255)
        self.assertTrue(self.s.pegel_nachziehen())
        self.assertAlmostEqual(self.s._effective_value(), 102, delta=1)
        # ausserhalb des Bereichs: Griff an den Anschlag, danach Ruhe
        self.von_aussen(1.0)
        self.assertTrue(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 255)
        self.assertEqual(self.s._effective_value(), 150)
        gesetzt = []
        alt = self.s.update
        self.s.update = lambda *a: (gesetzt.append(1), alt(*a))
        try:
            for _ in range(10):
                self.assertFalse(self.s.pegel_nachziehen(), "kein Flattern")
        finally:
            del self.s.update
        self.assertEqual(gesetzt, [])
        self.von_aussen(0.0)
        self.assertTrue(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 0)
        self.assertEqual(self.schreib(), 0)

    def test_invert_und_bereich_zusammen(self):
        self.s.invert = True
        self.s.range_min, self.s.range_max = 0, 128
        self.von_aussen(64 / 255)
        self.assertTrue(self.s.pegel_nachziehen())
        self.assertAlmostEqual(self.s._effective_value(), 64, delta=1)
        self.assertAlmostEqual(self.s.value, 128, delta=2)
        self.assertEqual(self.schreib(), 0)

    def test_eigener_zug_geht_wie_bisher_in_die_engine(self):
        self.s.value = 100                      # wie ein Zug des Bedieners
        self.assertAlmostEqual(self.ex.fader_value, 100 / 255)
        self.assertEqual(self.schreib(), 1)
        self.assertFalse(self.s.pegel_nachziehen(), "eigener Wert ist kein Aussenwert")
        self.assertEqual(self.schreib(), 1)

    def test_andere_modi_unveraendert(self):
        self.von_aussen(0.2)
        for modus in (SliderMode.LEVEL, SliderMode.SUBMASTER, SliderMode.GRANDMASTER,
                      SliderMode.SPEED, SliderMode.BPM):
            with self.subTest(modus=modus):
                self.s.mode = modus
                self.s._value = 200
                self.assertFalse(self.s.pegel_nachziehen())
                self.assertEqual(self.s.value, 200)
        self.assertEqual(self.schreib(), 0)

    def test_ohne_slot_nichts(self):
        self.s.playback_slot = None
        self.von_aussen(0.2)
        self.assertFalse(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 255)

    def test_bearbeiten_modus_nichts(self):
        self.s.set_edit_mode(True)
        self.von_aussen(0.2)
        self.assertFalse(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 255)
        self.s.set_edit_mode(False)
        self.assertTrue(self.s.pegel_nachziehen())

    def test_alte_show_laedt_wie_bisher(self):
        """Keine neue Persistenz: ein Alt-Layout (ohne neue Felder) laedt, und
        ``to_dict`` schreibt dieselben Schluessel wie vorher."""
        alt = {"type": "VCSlider", "caption": "Ex 1", "x": 10, "y": 10, "w": 60,
               "h": 200, "mode": "Playback", "function_id": 0, "value": 77}
        s = VCSlider("neu")
        s.apply_dict(alt)
        self.assertEqual(s.mode, SliderMode.PLAYBACK)
        self.assertEqual(s.playback_slot, 0)
        self.assertEqual(s.value, 77)
        d = s.to_dict()
        for k in d:
            self.assertNotIn("pegel", k)
            self.assertNotIn("nachzieh", k)


class GehaltenTest(_Basis):
    def setUp(self):
        super().setUp()
        self.s.show()
        QTest.qWaitForWindowExposed(self.s)
        self.addCleanup(self.s.close)

    def _griff(self) -> QPoint:
        return QPoint(self.s.width() // 2, self.s._handle_y())

    def test_maus_halten_bleibt_stehen_danach_bedienerwert(self):
        p = self._griff()
        QTest.mousePress(self.s, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, p)
        self.assertTrue(self.s.gehalten())
        self.von_aussen(0.2)                    # kommt waehrend des Haltens
        self.assertFalse(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 255)
        self.assertEqual(self.schreib(), 0)
        QTest.mouseRelease(self.s, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier, p)
        self.assertFalse(self.s.gehalten())
        # Bedienerwert gilt: Engine und Griff stehen gleich, kein Sprung
        self.assertAlmostEqual(self.ex.fader_value, 1.0)
        self.assertFalse(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 255)

    def test_klick_ohne_aussenwert_schreibt_nichts(self):
        p = self._griff()
        QTest.mousePress(self.s, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, p)
        QTest.mouseRelease(self.s, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier, p)
        self.assertEqual(self.schreib(), 0)

    def test_naechster_zug_nach_nachziehen_springt_nicht(self):
        self.von_aussen(0.5)
        self.assertTrue(self.s.pegel_nachziehen())
        p = self._griff()
        QTest.mousePress(self.s, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, p)
        QTest.mouseMove(self.s, p + QPoint(0, -4))
        v = self.s.value
        self.assertLessEqual(abs(v - 128), 10, f"Sprung auf {v}")
        QTest.mouseRelease(self.s, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier, p + QPoint(0, -4))
        self.assertAlmostEqual(self.ex.fader_value, v / 255)


class FingerTest(_Basis):
    """Echter Touch-Ablauf ueber ziehen_scrollen (wie UI-118)."""

    def setUp(self):
        super().setUp()
        from src.ui import ziehen_scrollen as zs
        from src.ui.views.virtual_console_view import GrowingScrollArea
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        f = zs.einrichten(_app)
        alt = f.aktiv
        f.aktiv = True
        self.addCleanup(setattr, f, "aktiv", alt)
        self.addCleanup(f._abbrechen)
        self.canvas = VCCanvas()
        self.s = self.canvas._add_widget("VCSlider", QPoint(20, 20))
        self.s.mode = SliderMode.PLAYBACK
        self.s.playback_slot = 0
        self.s._value = 255
        self.s.resize(60, 260)
        self.area = GrowingScrollArea()
        self.area.setWidget(self.canvas)
        self.area.resize(500, 350)
        self.area.show()
        QTest.qWaitForWindowExposed(self.area)
        self.canvas.set_edit_mode(False)
        QApplication.processEvents()
        self.addCleanup(self.area.close)
        self.vp = self.area.viewport()

    def test_finger_halten_bleibt_stehen_danach_bedienerwert(self):
        p = self.s.mapTo(self.vp, QPoint(self.s.width() // 2, self.s._handle_y()))
        QTest.touchEvent(self.vp, _DEV).press(0, p, self.vp).commit()
        self.assertTrue(_warte_auf(self.s.gehalten, 2000), "Finger haelt")
        self.von_aussen(0.2)
        self.assertFalse(self.s.pegel_nachziehen())
        QTest.qWait(50)
        self.assertEqual(self.s.value, 255)
        self.assertEqual(self.schreib(), 0)
        QTest.touchEvent(self.vp, _DEV).release(0, p, self.vp).commit()
        self.assertTrue(_warte_auf(lambda: not self.s.gehalten(), 2000))
        self.assertAlmostEqual(self.ex.fader_value, 1.0, msg="Bedienerwert gilt")
        self.assertFalse(self.s.pegel_nachziehen())
        self.assertEqual(self.s.value, 255)

    def test_seitenwechsel_zeigt_pegel_der_neuen_seite(self):
        self.s.bank = -1                           # auf allen Banks sichtbar
        self.von_aussen(0.3, self.ex2)
        self.pe.current_page = 1                   # Engine-Seite wie set_page
        self.canvas.set_active_bank(1)
        self.assertEqual(self.s.value, round(0.3 * 255))
        self.assertEqual(self.schreib(self.ex2), 0)
        self.assertEqual(self.schreib(), 0)
        self.pe.current_page = 0
        self.canvas.set_active_bank(0)
        self.assertEqual(self.s.value, 255)

    def test_fader_einer_verlassenen_bank_bleibt(self):
        self.s.bank = 0                            # nur auf Bank 1 (Index 0)
        self.von_aussen(0.3, self.ex2)
        self.pe.current_page = 1
        self.canvas.set_active_bank(1)
        self.assertFalse(self.s.pegel_nachziehen(), "unsichtbar, nicht aktiv")
        self.assertEqual(self.s.value, 255)
        self.assertEqual(self.schreib(self.ex2), 0)

    def test_bearbeiten_modus_beim_seitenwechsel_nichts(self):
        self.s.bank = -1
        self.canvas.set_edit_mode(True)
        self.von_aussen(0.3, self.ex2)
        self.pe.current_page = 1
        self.canvas.set_active_bank(1)
        self.assertEqual(self.s.value, 255)


class PickupUndMotorTest(_Basis):
    def setUp(self):
        super().setUp()
        self.mm = _FakeMM()
        alt = mgr.get_midi_manager
        mgr.get_midi_manager = lambda: self.mm
        self.addCleanup(setattr, mgr, "get_midi_manager", alt)

    def test_soft_takeover_armiert_naechste_beruehrung_springt_nicht(self):
        VCSlider.soft_takeover = True
        self.s.apply_midi_binding("cc", 1, 48)      # APC-Fader ohne Motor
        self.s.handle_midi(_cc(1, 48, 127))          # Pult-Fader oben (= 255)
        self.ex.__dict__["_vcb50_schreib"] = 0
        self.von_aussen(0.5)
        self.assertTrue(self.s.pegel_nachziehen())
        self.assertTrue(self.s._pickup_armed, "wartet aufs Durchfahren")
        self.assertEqual(self.schreib(), 0)
        # Pult-Fader steht noch oben: eine kleine Bewegung dort springt NICHT
        self.s.handle_midi(_cc(1, 48, 120))
        self.assertEqual(self.s.value, 128)
        self.assertEqual(self.schreib(), 0)
        self.assertAlmostEqual(self.ex.fader_value, 0.5)
        # durchfaehrt den neuen Wert: ab jetzt uebernimmt er
        self.s.handle_midi(_cc(1, 48, 60))
        self.assertFalse(self.s._pickup_armed)
        self.assertEqual(self.schreib(), 1)

    def test_ohne_midi_bindung_kein_pickup_hinweis(self):
        VCSlider.soft_takeover = True
        self.von_aussen(0.5)
        self.assertTrue(self.s.pegel_nachziehen())
        self.assertFalse(self.s._pickup_armed)

    def test_motorfader_faehrt_einmal_nach_kein_ping_pong(self):
        VCSlider.soft_takeover = True
        uhr = _Uhr()
        self.s._motor._uhr = uhr
        self.s.apply_midi_binding("pitchbend", 2, 0)
        self.s.midi_motor = True
        uhr.t += 5
        self.von_aussen(0.5)
        self.assertTrue(self.s.pegel_nachziehen())
        soll = round(128 / 255 * 16383)
        self.assertEqual(self.mm.pb, [(2, soll)], "Motor folgt dem Pegel")
        self.assertFalse(self.s._pickup_armed, "Motor hat den Fader hingefahren")
        # Bericht der Motorfahrt kommt zurueck: keine Eingabe, kein Schreiben
        uhr.t += MOTOR_ECHO_FENSTER_S / 2
        self.assertTrue(self.s.handle_midi(_pb(2, soll - 40)))
        self.assertTrue(self.s.handle_midi(_pb(2, soll)))
        self.assertEqual(self.schreib(), 0)
        self.assertEqual(self.s.value, 128)
        # weitere Takte: nichts mehr an den Motor, nichts in die Engine
        for _ in range(10):
            uhr.t += 0.4
            self.assertFalse(self.s.pegel_nachziehen())
        self.assertEqual(len(self.mm.pb), 1)
        self.assertEqual(self.schreib(), 0)


class StatustaktTest(_Basis):
    """Der vorhandene 400-ms-Statustakt der VC zieht nach — kein eigener Timer."""

    def test_vc_ansicht_zieht_im_statustakt_nach(self):
        from src.ui.views.virtual_console_view import VirtualConsoleView
        v = VirtualConsoleView()
        self.addCleanup(v.close)
        v.resize(1200, 800)
        v.show()
        QApplication.processEvents()
        s = v._canvas._add_widget("VCSlider", QPoint(20, 20))
        s.mode = SliderMode.PLAYBACK
        s.playback_slot = 0
        s._value = 255
        v._canvas.set_edit_mode(False)
        self.von_aussen(0.4)
        self.assertTrue(_warte_auf(lambda: s.value == round(0.4 * 255), 3000),
                        f"Regler steht auf {s.value}")
        self.assertEqual(self.schreib(), 0)
        self.assertEqual(v._active_fx_timer.interval(), 400)
        self.assertEqual([t for t in s.findChildren(type(v._active_fx_timer))
                          if t is not s._motor_timer], [], "kein Timer je Widget")


# ── 2. Feste Fernbedienung im Browser ───────────────────────────────────────

def _seite() -> str:
    with open(os.path.join(_REPO, "src", "web", "templates", "index.html"),
              encoding="utf-8") as fh:
        return fh.read()


def _funktion(text: str, name: str) -> str:
    """Rumpf einer JS-Funktion (bis zur schliessenden Klammer auf Spalte 0)."""
    m = re.search(r"^function " + name + r"\(.*?^}", text, re.S | re.M)
    assert m, name
    return m.group(0)


class FesteSeiteSkriptTest(unittest.TestCase):
    def test_holt_den_stand_regelmaessig_ueber_den_statusweg(self):
        html = _seite()
        holen = _funktion(html, "statusHolen")
        self.assertIn("fetch('/api/status')", holen)
        self.assertIn("faderNachziehen(d.executors)", holen)
        m = re.search(r"const ABFRAGE_MS = (\d+);", html)
        self.assertTrue(m, "ohne Fix: nur eine Abfrage beim Oeffnen")
        self.assertGreaterEqual(int(m.group(1)), 1000, "sparsam")
        self.assertRegex(html, r"setInterval\(\(\) => \{ if \(!document\.hidden\) "
                               r"statusHolen\(\); \}, ABFRAGE_MS\)")
        self.assertIn("visibilitychange", html)
        self.assertIn("if (abfrageLaeuft) return;", holen, "keine Abfrage-Stapel")

    def test_nachziehen_sendet_nichts(self):
        rumpf = _funktion(_seite(), "faderNachziehen")
        for verboten in ("socket.emit", "setFader(", "dispatchEvent", "fetch(",
                         "oninput", "new Event"):
            self.assertNotIn(verboten, rumpf, verboten)
        self.assertIn("fader.value = soll", rumpf)
        self.assertIn("!== soll", rumpf, "nur bei Aenderung setzen")

    def test_gehaltener_und_eben_bewegter_fader_ausgenommen(self):
        html = _seite()
        rumpf = _funktion(html, "faderNachziehen")
        self.assertIn("if (gehalten[slot]) return;", rumpf)
        self.assertIn("zuletztBewegt[slot]", rumpf)
        for ereignis in ("onpointerdown", "onpointerup", "onpointercancel",
                         "ontouchstart", "ontouchend", "ontouchcancel"):
            self.assertIn(ereignis + '="faderHalten(', html, ereignis)
        self.assertIn("zuletztBewegt[slot] = Date.now();", _funktion(html, "setFader"))

    def test_sichere_aktionen_unberuehrt(self):
        html = _seite()
        self.assertIn("socket.emit('blackout', {enabled: blackout});",
                      _funktion(html, "toggleBlackout"))
        self.assertIn("socket.emit('fader', {slot, level});", _funktion(html, "setFader"))
        self.assertNotIn("blackout", _funktion(html, "faderNachziehen").lower())


try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, "flask / flask-socketio nicht installiert")
class StatuswegTest(unittest.TestCase):
    """Der VORHANDENE Statusweg liefert den aktuellen Fader-Stand (keine neue
    Route) — auch nach einer Aenderung von aussen."""

    def setUp(self):
        import types
        import src.web.app as webapp
        from src.web import remote_settings

        class _Ex:
            def __init__(self, v):
                self.fader_value = v
        self.executors = [_Ex(1.0), _Ex(0.25)]
        state = types.SimpleNamespace(
            playback_engine=types.SimpleNamespace(executors=self.executors),
            universes={1: object()}, cue_stacks=[], mock_mode=True,
            get_patched_fixtures=lambda: [])
        alt = webapp._get_state
        webapp._get_state = lambda: state
        self.addCleanup(setattr, webapp, "_get_state", alt)
        self.app, _sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.app.config["LIGHTOS_FESTE_TOKEN"] = "festeVCB50"
        remote_settings.set_feste_seite_enabled(True)
        self.addCleanup(remote_settings.set_feste_seite_enabled, False)
        self.c = self.app.test_client()
        self.assertEqual(self.c.get("/?k=festeVCB50").status_code, 200)
        self.webapp = webapp

    def test_status_liefert_aktuellen_stand(self):
        self.assertEqual(self.c.get("/api/status").get_json()["executors"], [1.0, 0.25])
        self.executors[0].fader_value = 0.5           # von aussen (Pult/OSC/MIDI)
        self.assertEqual(self.c.get("/api/status").get_json()["executors"], [0.5, 0.25])

    def test_keine_neue_route(self):
        regeln = {r.rule for r in self.app.url_map.iter_rules()}
        self.assertIn("/api/status", regeln)
        for r in regeln:
            self.assertNotIn("nachzieh", r)
            self.assertNotIn("pegel", r)

    def test_ohne_recht_kein_stand(self):
        self.assertEqual(self.app.test_client().get("/api/status").status_code, 403)


if __name__ == "__main__":
    unittest.main()
