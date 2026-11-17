"""WEB-16 (Live-Durchlauf QA-LIVE, 17.11.2026): ein Executor-Pegel, der von
AUSSEN kommt (Web-Fernbedienung, OSC, MIDI, VC-Playback-Fader), erscheint im
Regler der Executor-Leiste.

Vorher setzte ``POST /api/executor/1/fader`` mit 0,5 die Engine auf 0,5, der
Regler blieb aber sichtbar auf 100 % — die naechste Beruehrung sprang.

Harte Anforderungen (der Fader steuert Helligkeit live):

* Nachziehen schreibt NICHTS zurueck in die Engine (gezaehlt: 0 Schreibzugriffe)
  und loest kein ``valueChanged`` aus (kein Echo an Web/OSC/MIDI).
* Haelt der Bediener den Griff (Maus oder Finger), wird er nicht ueberschrieben;
  nach dem Loslassen gilt sein Wert, Regler und Engine stehen gleich.
* Rundungsunterschiede unter einem Reglerschritt bewegen den Griff nicht.
* Ohne Aenderung wird nichts gesetzt.

Echte PlaybackView (offscreen) am Sandkasten-AppState aus ``conftest``.
"""
from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_PREFS_DIR",
                      tempfile.mkdtemp(prefix="lightos_prefs_web16_"))

from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (QApplication, QStyle,                 # noqa: E402
                               QStyleOptionSlider)

from src.core.app_state import get_state                             # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()


def _warte_auf(bedingung, ms: int) -> bool:
    """Auf eine Bedingung warten (kein enger Timer): Ereignisse verarbeiten,
    bis sie gilt oder die Frist ablaeuft."""
    import time
    ende = time.monotonic() + ms / 1000.0
    while time.monotonic() < ende:
        if bedingung():
            return True
        QTest.qWait(10)
    return bool(bedingung())


def _zaehl_klasse(basis):
    """Unterklasse des Executors, die jeden Schreibzugriff auf
    ``fader_value`` zaehlt (Lesen bleibt unveraendert)."""

    class _Gezaehlt(basis):
        @property
        def fader_value(self):
            return self.__dict__["_web16_fv"]

        @fader_value.setter
        def fader_value(self, v):
            self.__dict__["_web16_schreib"] = self.__dict__.get("_web16_schreib", 0) + 1
            self.__dict__["_web16_fv"] = v

    return _Gezaehlt


class _Basis(unittest.TestCase):
    def setUp(self):
        from src.ui.views.playback_view import PlaybackView
        self.state = get_state()
        self.pe = self.state.playback_engine
        self._orig_page = self.pe.current_page
        self.pe.current_page = 0
        self.ex = self.pe.get_executor(1)
        self._orig = (self.ex.__class__, self.ex.fader_value, self.ex.fader_function)
        self.ex.fader_function = "volume"
        wert = 1.0
        self.ex.__class__ = _zaehl_klasse(self._orig[0])
        self.ex.__dict__["_web16_fv"] = wert
        self.addCleanup(self._zurueck)
        self.view = PlaybackView()
        self.view.resize(1200, 700)
        self.view.show()
        QTest.qWaitForWindowExposed(self.view)
        self.w = self.view._executors_widgets[0]
        self.fader = self.w._fader
        self.w._sync_fader_for_function(self.ex)
        self.assertEqual(self.fader.value(), 100)
        self.echo = []
        self.fader.valueChanged.connect(self.echo.append)
        self.ex.__dict__["_web16_schreib"] = 0

    def _zurueck(self):
        try:
            self.view._tick.stop()
            self.view.close()
            self.view.deleteLater()
        except Exception:
            pass
        wert = self.ex.__dict__.pop("_web16_fv", self._orig[1])
        self.ex.__dict__.pop("_web16_schreib", None)
        self.ex.__class__ = self._orig[0]
        self.ex.fader_value = self._orig[1]
        self.ex.fader_function = self._orig[2]
        self.pe.current_page = self._orig_page
        del wert

    # Hilfen
    def schreibzugriffe(self) -> int:
        return self.ex.__dict__.get("_web16_schreib", 0)

    def von_aussen(self, v: float):
        self.ex.__dict__["_web16_fv"] = v      # wie Web/OSC/MIDI, ungezaehlt

    def griff(self) -> QPoint:
        opt = QStyleOptionSlider()
        self.fader.initStyleOption(opt)
        r = self.fader.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt,
            QStyle.SubControl.SC_SliderHandle, self.fader)
        return r.center()


class NachziehenTest(_Basis):
    def test_wert_von_aussen_erscheint_ohne_rueckschreiben(self):
        self.von_aussen(0.5)
        # im vorhandenen 50-ms-Takt der Ansicht, auf die Bedingung warten
        self.assertTrue(_warte_auf(lambda: self.fader.value() == 50, 3000),
                        f"Regler steht auf {self.fader.value()}")
        self.assertEqual(self.schreibzugriffe(), 0)
        self.assertEqual(self.echo, [])
        self.assertEqual(self.ex.fader_value, 0.5)

    def test_rundung_unter_einem_schritt_bewegt_nichts(self):
        self.von_aussen(0.995)
        self.assertFalse(self.w.fader_nachziehen())
        self.assertEqual(self.fader.value(), 100)
        self.von_aussen(0.505)
        self.assertTrue(self.w.fader_nachziehen())
        v = self.fader.value()
        for wert in (0.505, 0.5049, 0.5051, v / 100.0):
            self.von_aussen(wert)
            self.assertFalse(self.w.fader_nachziehen(), wert)
            self.assertEqual(self.fader.value(), v)
        self.assertEqual(self.schreibzugriffe(), 0)
        self.assertEqual(self.echo, [])

    def test_ohne_aenderung_wird_nichts_gesetzt(self):
        gesetzt = []
        alt = self.fader.setValue
        self.fader.setValue = lambda v: (gesetzt.append(v), alt(v))
        try:
            for _ in range(20):
                self.view._executor_fader_nachziehen()
        finally:
            del self.fader.setValue
        self.assertEqual(gesetzt, [])

    def test_crossfade_fader_bleibt_auf_null(self):
        self.ex.fader_function = "crossfade"
        self.w._sync_fader_for_function(self.ex)
        self.assertEqual(self.fader.value(), 0)
        self.von_aussen(0.7)
        self.assertFalse(self.w.fader_nachziehen())
        self.assertEqual(self.fader.value(), 0)


class GehaltenTest(_Basis):
    def _gehalten(self) -> bool:
        from src.ui.ziehen_scrollen import finger_haelt
        return self.fader.isSliderDown() or finger_haelt(self.fader)

    def _halten_test(self, druecken, loslassen):
        self.von_aussen(0.5)
        self.assertTrue(self.w.fader_nachziehen())
        self.assertEqual(self.fader.value(), 50)
        druecken(self.griff())
        self.assertTrue(_warte_auf(self._gehalten, 2000))
        self.ex.__dict__["_web16_schreib"] = 0
        self.von_aussen(0.2)                      # kommt waehrend des Haltens
        self.assertFalse(self.w.fader_nachziehen())
        # mehrere Takte der Ansicht; am Finger reicht ziehen_scrollen den Druck
        # erst nach dem langen Druck nach — bis dahin und danach: kein Nachziehen
        self.assertTrue(_warte_auf(self.fader.isSliderDown, 3000))
        QTest.qWait(150)
        self.assertEqual(self.fader.value(), 50)
        self.assertEqual(self.schreibzugriffe(), 0)
        loslassen()
        self.assertTrue(_warte_auf(lambda: not self._gehalten(), 2000))
        # Wert des Bedieners gilt, Regler und Engine stehen gleich
        self.assertAlmostEqual(self.ex.fader_value, 0.5)
        QTest.qWait(150)
        self.assertEqual(self.fader.value(), 50)
        self.assertFalse(self.w.fader_nachziehen())

    def test_maus_haelt_griff(self):
        ort = {}

        def druck(p):
            ort["p"] = p
            QTest.mousePress(self.fader, Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier, p)
        self._halten_test(
            druck,
            lambda: QTest.mouseRelease(self.fader, Qt.MouseButton.LeftButton,
                                       Qt.KeyboardModifier.NoModifier, ort["p"]))

    def test_finger_haelt_griff(self):
        from src.ui import ziehen_scrollen as zs
        f = zs.einrichten(_app)
        alt = f.aktiv
        f.aktiv = True
        self.addCleanup(setattr, f, "aktiv", alt)
        self.addCleanup(f._abbrechen)
        win = self.view.window()
        ort = {}

        def druck(p):
            ort["p"] = self.fader.mapTo(win, p)
            QTest.touchEvent(win, _DEV).press(0, ort["p"], win).commit()
        self._halten_test(
            druck,
            lambda: QTest.touchEvent(win, _DEV).release(0, ort["p"], win).commit())

    def test_finger_kurz_auf_dem_griff_wird_nicht_ueberschrieben(self):
        """Der zurueckgehaltene Fingerdruck (UI-113) zaehlt schon als Halten:
        sonst rueckte der Griff unter dem Finger weg und der nachgereichte
        Druck laege auf der Rille."""
        from src.ui import ziehen_scrollen as zs
        f = zs.einrichten(_app)
        alt = f.aktiv
        f.aktiv = True
        self.addCleanup(setattr, f, "aktiv", alt)
        self.addCleanup(f._abbrechen)
        win = self.view.window()
        p = self.fader.mapTo(win, self.griff())
        QTest.touchEvent(win, _DEV).press(0, p, win).commit()
        self.assertTrue(_warte_auf(lambda: zs.finger_haelt(self.fader), 1000))
        self.von_aussen(0.2)
        self.assertFalse(self.w.fader_nachziehen())
        self.assertEqual(self.fader.value(), 100)
        QTest.touchEvent(win, _DEV).release(0, p, win).commit()
        QApplication.processEvents()

    def test_ziehen_geht_wie_bisher_in_die_engine(self):
        self.fader.setValue(30)                   # wie ein Zug des Bedieners
        self.assertAlmostEqual(self.ex.fader_value, 0.3)
        self.assertEqual(self.schreibzugriffe(), 1)
        self.assertFalse(self.w.fader_nachziehen())
        self.assertEqual(self.schreibzugriffe(), 1)


class PageWechselTest(_Basis):
    """Nach einem Page-Wechsel zeigt der Regler den Pegel der NEUEN Seite —
    auch wenn der Griff waehrend des Wechsels gehalten wird; das Loslassen
    ueberschreibt den Pegel der neuen Seite nicht."""

    def _ex2(self, wert):
        ex2 = self.pe.get_executor(1, page=1)
        self.addCleanup(setattr, ex2, "fader_value", ex2.fader_value)
        ex2.fader_value = wert
        return ex2

    def test_page_wechsel_zeigt_neue_seite(self):
        ex2 = self._ex2(0.33)
        self.von_aussen(0.8)
        self.view._executor_fader_nachziehen()
        self.assertEqual(self.fader.value(), 80)
        self.pe.set_page(1)
        self.assertTrue(_warte_auf(lambda: self.fader.value() == 33, 2000),
                        f"Regler steht auf {self.fader.value()}")
        self.assertAlmostEqual(ex2.fader_value, 0.33)
        self.pe.set_page(0)
        self.assertTrue(_warte_auf(lambda: self.fader.value() == 80, 2000))
        self.assertEqual(self.schreibzugriffe(), 0)
        self.assertAlmostEqual(self.ex.fader_value, 0.8)

    def test_gehalten_ueber_page_wechsel(self):
        ex2 = self._ex2(0.33)
        p = self.griff()
        QTest.mousePress(self.fader, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, p)
        self.pe.set_page(1)
        QTest.qWait(150)
        QTest.mouseRelease(self.fader, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier, p)
        self.assertAlmostEqual(ex2.fader_value, 0.33)
        self.assertTrue(_warte_auf(lambda: self.fader.value() == 33, 2000))
        self.assertAlmostEqual(self.ex.fader_value, 1.0)


try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, "flask / flask-socketio nicht installiert")
class WebEndeZuEndeTest(_Basis):
    def test_post_fader_erscheint_im_regler(self):
        import src.web.app as webapp
        from src.web import remote_settings
        app, _sio = webapp.create_app()
        app.config["TESTING"] = True
        app.config["LIGHTOS_FESTE_TOKEN"] = "festeW16"
        remote_settings.set_feste_seite_enabled(True)
        self.addCleanup(remote_settings.set_feste_seite_enabled, False)
        c = app.test_client()
        self.assertEqual(c.get("/?k=festeW16").status_code, 200)
        r = c.post("/api/executor/1/fader", json={"level": 0.5})
        self.assertEqual(r.status_code, 200, r.get_data())
        self.assertEqual(self.schreibzugriffe(), 1)     # nur der Web-Schreibzugriff
        self.assertTrue(_warte_auf(lambda: self.fader.value() == 50, 3000),
                        f"Regler steht auf {self.fader.value()}")
        self.assertEqual(self.schreibzugriffe(), 1)     # Nachziehen: 0 weitere
        self.assertEqual(self.echo, [])
        st = c.get("/api/status").get_json()
        self.assertEqual(st["executors"][0], 0.5)


if __name__ == "__main__":
    unittest.main()
