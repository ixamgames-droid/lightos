"""ENG-16/ENG-17: der Layer-Effekt schreibt jetzt wie jeder andere Schreiber.

Zwei Befunde in derselben Schleife (`LayeredEffect.write`):

**ENG-16 — die Geraete-Flags wurden ignoriert.** `apply_pan_tilt_orientation` ist
die EINE Stelle, die `invert_pan`/`invert_tilt`/`swap_pan_tilt` umsetzt;
Programmer-Flush und Render-Pfad gehen durch sie, dieser Schreiber ging als
einziger daran vorbei. Gemessen an einem Geraet mit `invert_pan`: Programmer
schrieb 55, der Layer-Effekt 200.

★ Dieselbe Konventions-Klasse wie VIZ-55, nur andersherum: dort wandte `aim.py`
die Flags ZWEIMAL an, hier gar nicht. Zwei Abweichungen von derselben Regel in
zwei Tagen, in beide Richtungen — die Regel stand eben nur als Kommentar in
`efx.py`.

**ENG-17 — nur der erste Kopf wurde bedient.** Ein `break` nach dem ersten
Treffer liess an einer Vierkopf-Bar drei Koepfe stehen: Layer `[200,0,0,0]`
gegen Programmer `[200,200,200,200]`.

Gemessen wird durchgehend **am Universum**, und immer gegen den Programmer-Pfad
als Referenz: „beide schreiben dasselbe" ist die eigentliche Zusicherung, eine
erwartete Zahl waere nur die halbe Wahrheit.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.engine.effect_func import LayeredEffect


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


class _Durchreicher:
    """Neutraler Layer: gibt den Basiswert unveraendert weiter.

    ``write()`` steigt ohne Layer sofort aus — ohne diesen hier misst der Test
    gar nichts (die erste Fassung tat genau das und schrieb ueberall 0).
    """

    def process(self, val, t, idx):
        return val

    def to_dict(self):
        return {}


EIN_KOPF = [_Ch("pan", 1), _Ch("tilt", 2)]
VIER_KOEPFE = [_Ch("pan", i + 1) for i in range(4)]


def _fixture(**flags):
    return SimpleNamespace(
        fid=1, universe=1, address=1,
        invert_pan=flags.get("invert_pan", False),
        invert_tilt=flags.get("invert_tilt", False),
        swap_pan_tilt=flags.get("swap_pan_tilt", False))


class LayerUndProgrammerSchreibenDasselbeTest(unittest.TestCase):

    def setUp(self):
        self._orig = A.get_channels_for_patched

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _layer(self, chans, fixture, attr="pan", wert=200):
        A.get_channels_for_patched = lambda f: chans
        e = LayeredEffect("t")
        e.fixture_ids = [1]
        e.target_attribute = attr
        e.base_value = wert / 255.0
        e.layers = [_Durchreicher()]
        e._running = True
        uni = Universe(1)
        e.write({1: uni}, [fixture], dt=0.0)
        return [uni.get_channel(i) for i in range(1, len(chans) + 1)]

    def _programmer(self, chans, fixture, attrs):
        """Der ECHTE Render-Pfad als Referenz — keine Nachbildung."""
        A.get_channels_for_patched = lambda f: chans
        st = AppState.__new__(AppState)
        st._fix_index = {1: (fixture, chans)}
        uni = Universe(1)
        st._apply_fixture_map({1: uni}, {1: attrs})
        return [uni.get_channel(i) for i in range(1, len(chans) + 1)]

    # ── ENG-16 ───────────────────────────────────────────────────────────────

    def test_flags_wirken_wie_im_programmer_pfad(self):
        for name, flags in (("invert_pan", {"invert_pan": True}),
                            ("invert_tilt", {"invert_tilt": True}),
                            ("swap", {"swap_pan_tilt": True}),
                            ("swap+invert", {"swap_pan_tilt": True,
                                             "invert_pan": True})):
            with self.subTest(flags=name):
                fx = _fixture(**flags)
                self.assertEqual(
                    self._layer(EIN_KOPF, fx),
                    self._programmer(EIN_KOPF, fx, {"pan": 200}),
                    f"Layer-Effekt und Programmer laufen bei {name} auseinander")

    def test_bei_swap_wandert_der_wert_auf_den_anderen_kanal(self):
        """Die Stelle, an der die naheliegende Loesung scheitert.

        Wer stur auf ``target_attribute`` schreibt statt auf die Schluessel des
        ERGEBNIS-dicts, verliert den Wert bei ``swap`` ganz: aus ``{'pan': v}``
        wird ``{'tilt': v}``.
        """
        fx = _fixture(swap_pan_tilt=True)
        werte = self._layer(EIN_KOPF, fx)
        self.assertEqual(werte[0], 0, "Pan-Kanal muesste bei Swap leer bleiben")
        self.assertEqual(werte[1], 200, "Der Wert ist bei Swap verlorengegangen")

    def test_geraet_ohne_flags_unveraendert(self):
        """Positivkontrolle: ohne Flags war nie etwas kaputt und bleibt es."""
        fx = _fixture()
        self.assertEqual(self._layer(EIN_KOPF, fx), [200, 0])
        self.assertEqual(self._layer(EIN_KOPF, fx),
                         self._programmer(EIN_KOPF, fx, {"pan": 200}))

    def test_nicht_pan_tilt_attribute_bleiben_unberuehrt(self):
        """Ein Dimmer-Effekt darf von den Pan/Tilt-Flags nichts merken."""
        chans = [_Ch("intensity", 1)]
        fx = _fixture(invert_pan=True, swap_pan_tilt=True)
        self.assertEqual(self._layer(chans, fx, attr="intensity"), [200])

    # ── ENG-17 ───────────────────────────────────────────────────────────────

    def test_alle_koepfe_werden_bedient(self):
        fx = _fixture()
        self.assertEqual(
            self._layer(VIER_KOEPFE, fx),
            self._programmer(VIER_KOEPFE, fx, {"pan": 200}),
            "Der Layer-Effekt laesst Koepfe stehen, die der Programmer bedient")

    def test_ein_kopf_bleibt_byte_genau_gleich(self):
        """Positivkontrolle zur Mehrkopf-Aenderung: ein Einkopf-Geraet darf sich
        nicht bewegen, nur weil die Schleife jetzt weiterlaeuft."""
        fx = _fixture()
        self.assertEqual(self._layer([_Ch("pan", 1)], fx), [200])


if __name__ == "__main__":
    unittest.main()
