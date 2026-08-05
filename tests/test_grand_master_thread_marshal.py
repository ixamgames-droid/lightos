"""GM-THREAD: Ein Grand-Master-Push aus einem Fremd-Thread darf keine
Qt-Widgets im Fremd-Thread anfassen.

``OutputManager.set_grand_master`` ruft seine Abonnenten **inline im aufrufenden
Thread**. Einer der Aufrufer ist der MidiDispatch-Thread: ``MidiMapper``
verarbeitet ``ACTION_GRAND_MASTER`` dort, und das **ausgelieferte**
APC-mini-Profil legt CC 56 — den Master-Fader — auf genau diese Aktion. Wer den
Regler bewegt, laesst damit den MIDI-Thread ``QSlider.setValue()``,
``QLabel.setText()`` und ``QWidget.update()`` aufrufen.

★ Das ist wortgleich die Ursache aus ``crash.log 2026-06-14`` („MIDI-Thread
fasste Widgets direkt an -> Access Violation"), gegen die
``MainWindow._page_changed_sig`` eingezogen wurde — nur eben am Nachbar-Callback,
der damals uebersehen wurde. Der bestehende Test dazu ist
``tests/test_playback_page_threadsafe.py``.

Gemessen wird deshalb **nicht** „kein Absturz" (auf Linux/x64 stuerzt es meist
nicht, es korrumpiert nur gelegentlich — genau deshalb faellt es erst am ARM-Rig
auf), sondern der **Thread, in dem der Widget-Aufruf wirklich passiert**. Dazu
werden die gefaehrlichen Qt-Methoden instrumentiert und ihre Thread-Kennung
aufgezeichnet.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app, runden: int = 12):
    """Gequeuete Signale zustellen. Ohne das kaeme der marshallte Aufruf nie an —
    und der Test koennte 'nie im Fremd-Thread' nicht von 'gar nicht' trennen."""
    for _ in range(runden):
        app.processEvents()


def _push_aus_fremd_thread(om, wert: float) -> list:
    """set_grand_master aus einem ECHTEN Fremd-Thread rufen (wie MidiDispatch)."""
    fehler: list = []

    def worker():
        try:
            om.set_grand_master(wert)
        except BaseException as e:          # pragma: no cover - darf nicht passieren
            fehler.append(e)

    t = threading.Thread(target=worker, name="FakeMidiDispatch")
    t.start()
    t.join(timeout=5.0)
    assert not t.is_alive(), "set_grand_master aus dem Fremd-Thread haengt"
    return fehler


# ---------------------------------------------------------------------------
# Die Signale existieren ueberhaupt
# ---------------------------------------------------------------------------

def test_mainwindow_hat_gm_marshalling_signal():
    from src.ui.main_window import MainWindow
    assert isinstance(MainWindow.__dict__.get("_gm_changed_sig"), Signal), \
        "MainWindow braucht ein Signal, um den GM-Push zu marshallen"


def test_vcslider_hat_gm_marshalling_signal():
    from src.ui.virtualconsole.vc_slider import VCSlider
    assert isinstance(VCSlider.__dict__.get("_gm_pushed_sig"), Signal), \
        "VCSlider braucht ein Signal, um den GM-Push zu marshallen"


# ---------------------------------------------------------------------------
# ★ Der eigentliche Beleg: in WELCHEM Thread laufen die Widget-Aufrufe?
# ---------------------------------------------------------------------------

def test_header_fader_wird_nicht_aus_dem_fremd_thread_angefasst():
    app = _app()
    from src.core.app_state import get_state
    from src.ui.main_window import MainWindow

    fenster = MainWindow()
    _pump(app)
    ui_thread = threading.get_ident()
    gesehen: list[int] = []

    # Genau die drei Aufrufe instrumentieren, die _sync_header_gm macht.
    for widget, methode in ((fenster._slider_gm, "setValue"),
                            (fenster._slider_gm, "blockSignals"),
                            (fenster._lbl_gm_val, "setText")):
        original = getattr(widget, methode)

        def spion(*args, _o=original, **kwargs):
            gesehen.append(threading.get_ident())
            return _o(*args, **kwargs)

        setattr(widget, methode, spion)

    om = get_state().output_manager
    fehler = _push_aus_fremd_thread(om, 0.42)
    assert not fehler, f"set_grand_master warf im Fremd-Thread: {fehler}"
    _pump(app)

    assert gesehen, ("der Header-Fader wurde gar nicht nachgefuehrt — dann misst "
                     "dieser Test nichts (GDS-1 waere kaputt)")
    fremd = [t for t in gesehen if t != ui_thread]
    assert not fremd, (
        f"{len(fremd)} von {len(gesehen)} Widget-Aufrufen liefen im Fremd-Thread "
        f"(UI-Thread {ui_thread}, gesehen {set(gesehen)}) — genau die Ursache aus "
        f"crash.log 2026-06-14")

    fenster.close()
    fenster.deleteLater()
    _pump(app)


def test_vc_grandmaster_fader_wird_nicht_aus_dem_fremd_thread_neu_gezeichnet():
    app = _app()
    from src.core.app_state import get_state
    from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

    fader = VCSlider("GM")
    fader.mode = SliderMode.GRANDMASTER
    # Der Abonnent haengt am Wechsel in den GRANDMASTER-Modus.
    fader._ensure_grandmaster_sync()
    _pump(app)

    ui_thread = threading.get_ident()
    gesehen: list[int] = []
    original = fader.update

    def spion(*args, _o=original, **kwargs):
        gesehen.append(threading.get_ident())
        return _o(*args, **kwargs)

    fader.update = spion

    om = get_state().output_manager
    fehler = _push_aus_fremd_thread(om, 0.37)
    assert not fehler, f"set_grand_master warf im Fremd-Thread: {fehler}"
    _pump(app)

    assert gesehen, ("der VC-Fader hat sich gar nicht neu gezeichnet — dann misst "
                     "dieser Test nichts")
    fremd = [t for t in gesehen if t != ui_thread]
    assert not fremd, (
        f"QWidget.update() lief {len(fremd)}x im Fremd-Thread "
        f"(UI-Thread {ui_thread}, gesehen {set(gesehen)})")

    fader.deleteLater()
    _pump(app)


# ---------------------------------------------------------------------------
# Verhalten unveraendert — das Marshalling darf nichts kaputtmachen
# ---------------------------------------------------------------------------

def test_wert_kommt_trotz_marshalling_wirklich_an():
    """Gegenrichtung: ein Test, der nur „nie im Fremd-Thread" prueft, bestuende
    auch, wenn der Callback gar nicht mehr feuerte."""
    app = _app()
    from src.core.app_state import get_state
    from src.ui.main_window import MainWindow

    fenster = MainWindow()
    _pump(app)
    om = get_state().output_manager
    _push_aus_fremd_thread(om, 0.25)
    _pump(app)
    assert fenster._slider_gm.value() == 25, \
        f"Header-Fader zeigt {fenster._slider_gm.value()} statt 25 %"
    assert fenster._lbl_gm_val.text() == "25%"

    fenster.close()
    fenster.deleteLater()
    _pump(app)


def test_eigener_drag_des_vc_faders_laeuft_weiter_direkt_durch():
    """★ Der `_gm_self_push`-Guard der VC haengt daran, dass der eigene Push
    SYNCHRON zurueckkommt: er wird um `set_grand_master` herum gesetzt und im
    `finally` wieder geloescht. AutoConnection stellt Emits aus demselben Thread
    direkt zu — genau deshalb bleibt der Guard wirksam. Waere hier versehentlich
    eine QueuedConnection erzwungen worden, kaeme der Callback erst NACH dem
    `finally` an und der Fader ueberschriebe seinen eigenen Griff-Wert.

    ★ Der Spion sitzt bewusst auf der KLASSE und wird VOR dem Verbinden gesetzt,
    nicht danach auf der Instanz: sonst ersetzte der Test die Verbindung durch
    seine eigene und maesse deren Zustellart statt der aus dem Produktivcode.
    (Genau daran ist die erste Fassung dieses Tests gescheitert — mit erzwungener
    QueuedConnection blieb sie gruen.)
    """
    app = _app()
    from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

    gesehen: list[bool] = []
    original = VCSlider._on_grand_master_pushed

    def spion(self, gm, _o=original):
        gesehen.append(self._gm_self_push)
        return _o(self, gm)

    VCSlider._on_grand_master_pushed = spion
    try:
        fader = VCSlider("GM")
        fader.mode = SliderMode.GRANDMASTER
        fader._ensure_grandmaster_sync()   # verbindet die (gepatchte) Methode
        _pump(app)
        gesehen.clear()                    # was der Aufbau selbst ausgeloest hat

        fader._gm_self_push = True
        fader._gm_pushed_sig.emit(0.5)     # Emit aus DIESEM (UI-)Thread
        fader._gm_self_push = False
    finally:
        VCSlider._on_grand_master_pushed = original

    assert gesehen == [True], (
        "der eigene Push kam nicht synchron zurueck — der _gm_self_push-Guard "
        f"greift damit nicht mehr (gesehen: {gesehen}; leer = die Verbindung "
        f"ist gequeued statt direkt)")

    fader.deleteLater()
    _pump(app)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
