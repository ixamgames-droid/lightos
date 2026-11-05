"""VIZ-111 (4): Zoom-Effekte als fertige Vorlagen im Effekt-Assistenten.

Der Effekt-Ebenen-Editor kann ``zoom`` als Ziel, aber es gab keine fertige
Vorlage. Jetzt bietet der Assistent „Zoom-Puls", „Zoom-Welle" und „Zoom im
Takt" an — nur fuer Geraete mit Zoom-Kanal.

Wie ``test_effect_wizard_presets.py``: der ECHTE Assistent wird bedient (Typ
anklicken, ``next()``, ``accept()``); Attrappe ist nur die Umgebung (Mini-Rig +
frischer Function-Manager). Kein echter Datenordner, kein DMX-Interface.
"""
import math
import os
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                               # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox     # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _ch(attr, nr):
    return SimpleNamespace(attribute=attr, channel_number=nr, ranges=[])


# Moving Head mit Zoom (Ch 3) und ein PAR ohne Zoom.
_MH = [_ch("intensity", 1), _ch("pan", 2), _ch("zoom", 3)]
_PAR = [_ch("color_r", 1), _ch("color_g", 2), _ch("color_b", 3), _ch("intensity", 4)]
_CH_ZOOM = 3


def _fx(fid, address):
    return SimpleNamespace(fid=fid, universe=1, address=address, label=f"FX {fid}")


@contextmanager
def _rig(kanaele):
    """``kanaele`` = {fid: Kanalliste}. Patcht nur die Umgebung."""
    import src.core.app_state as app_state
    import src.core.engine.function_manager as fm_mod
    from src.core.engine.function_manager import FunctionManager

    fm = FunctionManager()
    fixtures = [_fx(fid, 1 + 10 * i) for i, fid in enumerate(kanaele)]
    fake_state = type("S", (), {
        "get_patched_fixtures": lambda self: list(fixtures),
        "get_selected_fids": lambda self: [],
    })()
    orig = (app_state.get_state, app_state.get_channels_for_patched, fm_mod._manager)
    app_state.get_state = lambda: fake_state
    app_state.get_channels_for_patched = lambda fx: kanaele[fx.fid]
    fm_mod._manager = fm
    try:
        yield fm, fixtures
    finally:
        (app_state.get_state, app_state.get_channels_for_patched,
         fm_mod._manager) = orig


def _zeile(wiz, key):
    from src.ui.widgets.effect_wizard import PRESETS
    label = dict((p[0], p[1]) for p in PRESETS)[key]
    lst = wiz.page(0).list
    for row in range(lst.count()):
        if lst.item(row).text().startswith(label):
            return row
    raise AssertionError(f"Vorlage '{label}' fehlt in der Typ-Liste")


def _fuehren(key, kanaele, *, hold=None):
    from src.ui.widgets.effect_wizard import EffectWizard
    wiz = EffectWizard()
    wiz.restart()
    wiz.page(0).list.setCurrentRow(_zeile(wiz, key))
    wiz.next()      # Lampen
    wiz.next()      # Farben
    wiz.next()      # Tempo/Name
    if hold is not None:
        wiz.page(3).hold.setValue(hold)
    warnungen = []
    with patch.object(QMessageBox, "warning",
                      staticmethod(lambda *a, **k: warnungen.append(a))):
        wiz.accept()
    return wiz, warnungen


_ZWEI_MH_EIN_PAR = {1: _MH, 2: _MH, 3: _PAR}


class ZoomVorlagenTest(unittest.TestCase):

    def test_vorlagen_sind_registriert(self):
        from src.ui.widgets.effect_wizard import PRESETS, ZOOM_PRESETS
        keys = {p[0] for p in PRESETS}
        self.assertTrue({"zoom_pulse", "zoom_wave", "zoom_beat"} <= keys)
        self.assertEqual(ZOOM_PRESETS, {"zoom_pulse", "zoom_wave", "zoom_beat"})

    def test_zoom_puls_ist_ein_sinus_auf_zoom(self):
        from src.core.engine.effect_func import LayeredEffect
        from src.core.engine.effect_layers import LayerType
        with _rig(_ZWEI_MH_EIN_PAR):
            wiz, warn = _fuehren("zoom_pulse", _ZWEI_MH_EIN_PAR, hold=2.0)
        self.assertEqual(warn, [])
        le = wiz.created_function
        self.assertIsInstance(le, LayeredEffect)
        self.assertEqual(le.target_attribute, "zoom")
        self.assertEqual(le.fixture_ids, [1, 2], "PAR ohne Zoom gehoert nicht dazu")
        self.assertAlmostEqual(le.base_value, 0.5)
        self.assertEqual(len(le.layers), 1)
        lay = le.layers[0]
        self.assertIs(lay.type, LayerType.SIN)
        self.assertAlmostEqual(lay.amplitude, 0.5)
        self.assertAlmostEqual(lay.frequency, 0.5, msg="Halten 2 s = ein Zyklus")
        self.assertEqual(lay.fixture_phase_step, 0.0, "Puls: alle gleichzeitig")
        self.assertEqual(le.name, "Zoom-Puls")

    def test_zoom_welle_hat_phasenversatz_je_geraet(self):
        kan = {1: _MH, 2: _MH, 3: _MH, 4: _MH}
        with _rig(kan):
            wiz, warn = _fuehren("zoom_wave", kan)
        self.assertEqual(warn, [])
        le = wiz.created_function
        self.assertEqual(le.target_attribute, "zoom")
        self.assertEqual(le.fixture_ids, [1, 2, 3, 4])
        self.assertAlmostEqual(le.layers[0].fixture_phase_step, 2 * math.pi / 4)
        # Wirkung: zur selben Zeit liefern die Geraete verschiedene Werte.
        werte = {round(le.layers[0].process(le.base_value, 0.3, i), 4) for i in range(4)}
        self.assertEqual(len(werte), 4)

    def test_zoom_im_takt_ist_ein_beat_chaser_eng_weit(self):
        from src.core.engine.chaser import Chaser
        with _rig(_ZWEI_MH_EIN_PAR) as (fm, _):
            wiz, warn = _fuehren("zoom_beat", _ZWEI_MH_EIN_PAR)
            self.assertEqual(warn, [])
            ch = wiz.created_function
            self.assertIsInstance(ch, Chaser)
            self.assertEqual(ch.tempo_bus_id, "Global", "taktgebunden wie die anderen")
            self.assertEqual(len(ch.steps), 2)
            eng, weit = (fm.get(s.function_id) for s in ch.steps)
            w_eng = {(v.fixture_id, v.channel): v.value for v in eng.values}
            w_weit = {(v.fixture_id, v.channel): v.value for v in weit.values}
        # NUR der Zoom-Kanal, nur die Geraete mit Zoom; Dimmer bleibt unberuehrt.
        self.assertEqual(w_eng, {(1, _CH_ZOOM): 0, (2, _CH_ZOOM): 0})
        self.assertEqual(w_weit, {(1, _CH_ZOOM): 255, (2, _CH_ZOOM): 255})

    def test_umgekehrter_zoom_tauscht_eng_und_weit(self):
        import src.core.app_state as app_state
        with _rig({1: _MH}) as (fm, _), \
                patch.object(app_state, "zoom_umgekehrt_for", lambda fx: True):
            wiz, _w = _fuehren("zoom_beat", {1: _MH})
            eng = fm.get(wiz.created_function.steps[0].function_id)
            self.assertEqual([v.value for v in eng.values], [255])

    def test_geraet_ohne_zoom_ist_auf_der_lampenseite_ausgegraut(self):
        from src.ui.widgets.effect_wizard import EffectWizard, KEIN_ZOOM_HINWEIS
        with _rig(_ZWEI_MH_EIN_PAR):
            wiz = EffectWizard()
            wiz.restart()
            wiz.page(0).list.setCurrentRow(_zeile(wiz, "zoom_pulse"))
            wiz.next()
            cbs = {cb.fid: cb for cb in wiz.page(1).checks}
            self.assertTrue(cbs[1].isEnabled() and cbs[1].isChecked())
            self.assertFalse(cbs[3].isEnabled())
            self.assertFalse(cbs[3].isChecked())
            self.assertEqual(cbs[3].toolTip(), KEIN_ZOOM_HINWEIS)
            self.assertFalse(wiz.page(1)._zoom_hinweis.isHidden())
            # Zurueck und eine Nicht-Zoom-Vorlage: wieder frei waehlbar.
            wiz.back()
            wiz.page(0).list.setCurrentRow(_zeile(wiz, "wipe"))
            wiz.next()
            self.assertTrue(cbs[3].isEnabled())
            self.assertTrue(cbs[3].isChecked(),
                            "Vorauswahl (alle) kommt nach dem Zurueckblaettern wieder")
            self.assertTrue(wiz.page(1)._zoom_hinweis.isHidden())

    def test_ohne_zoom_geraet_sind_die_vorlagen_ausgegraut(self):
        from src.ui.widgets.effect_wizard import EffectWizard
        with _rig({1: _PAR, 2: _PAR}):
            wiz = EffectWizard()
            lst = wiz.page(0).list
            for key in ("zoom_pulse", "zoom_wave", "zoom_beat"):
                it = lst.item(_zeile(wiz, key))
                self.assertFalse(it.flags() & Qt.ItemFlag.ItemIsEnabled, key)
                self.assertIn("kein Gerät mit Zoom-Kanal", it.text())
            # Gegenprobe: andere Vorlagen bleiben waehlbar.
            self.assertTrue(lst.item(_zeile(wiz, "wipe")).flags()
                            & Qt.ItemFlag.ItemIsEnabled)

    def test_nur_lampen_ohne_zoom_gewaehlt_meldet_fehler(self):
        """Selbst wenn eine Lampe ohne Zoom durchrutscht, entsteht kein
        stummer Effekt: der Assistent meldet den Fehler."""
        from src.ui.widgets.effect_wizard import EffectWizard
        with _rig(_ZWEI_MH_EIN_PAR):
            wiz = EffectWizard()
            wiz.restart()
            wiz.page(0).list.setCurrentRow(_zeile(wiz, "zoom_pulse"))
            wiz.next()
            for cb in wiz.page(1).checks:
                cb.setChecked(cb.fid == 3)
            wiz.next(); wiz.next()
            warn = []
            with patch.object(QMessageBox, "warning",
                              staticmethod(lambda *a, **k: warn.append(a))):
                wiz.accept()
        self.assertEqual(len(warn), 1)
        self.assertIsNone(wiz.created_function)


class ZoomRenderTest(unittest.TestCase):
    """Der erzeugte Puls schreibt ueber die Zeit wechselnde Werte auf den
    Zoom-Kanal (headless: ``write`` mit festen ``dt``-Schritten = manuelle Uhr)."""

    def test_zoom_kanal_aendert_sich_ueber_die_zeit(self):
        from src.core.dmx.universe import Universe
        kan = {1: _MH}
        with _rig(kan) as (fm, fixtures):
            wiz, warn = _fuehren("zoom_pulse", kan, hold=1.0)
            self.assertEqual(warn, [])
            le = wiz.created_function
            le._running = True
            uni = Universe(1)
            addr_zoom = fixtures[0].address + _CH_ZOOM - 1
            addr_dim = fixtures[0].address
            werte = []
            le.write({1: uni}, fixtures, 0.0)
            werte.append(uni.get_channel(addr_zoom))
            for _ in range(4):                    # 4 x 0,25 s = ein Zyklus
                le.write({1: uni}, fixtures, 0.25)
                werte.append(uni.get_channel(addr_zoom))
            dimmer = uni.get_channel(addr_dim)
        self.assertEqual(werte[0], 127, "Start in der Mitte (0.5)")
        self.assertGreaterEqual(werte[1], 254, "Viertelzyklus: ganz weit")
        self.assertLessEqual(werte[3], 1, "Dreiviertel: ganz eng")
        self.assertGreater(len(set(werte)), 2)
        self.assertEqual(dimmer, 0, "Zoom-Vorlage fasst den Dimmer nicht an")


if __name__ == "__main__":
    unittest.main()
