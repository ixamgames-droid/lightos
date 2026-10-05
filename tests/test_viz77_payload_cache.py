"""VIZ-77: Payload-Cache je Geraet im ``VisualizerService``.

Gemessen bei VIZ-71: mit Mega Arena (32 Geraete) und laufendem Effekt kostete
``_build_snapshot`` rund 8 ms je Tick im UI-Thread, der Service-Takt schaffte
nur 15-18 Hz statt 44. Seitdem baut der Snapshot den Payload eines Geraets nur
neu, wenn sich sein Ausschnitt im DISPLAY-Frame, seine Geraetefelder, seine
Kanalliste oder (per Event) der State geaendert hat — spaetestens nach
``GATE_MAX_SKIPS`` Bauten wird alles neu gebaut.

Ohne Cache sind die Treffer-Tests rot (``payload_cache_stats`` fehlt bzw. zaehlt
keine Treffer); die Gegenprobe ueber Zufalls-Frames haelt fest, dass der Cache
nie etwas anderes liefert als der ungecachte Bau.
"""
import os
import random
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as app_state_mod
from src.core.dmx.universe import Universe
from src.ui.visualizer.visualizer_service import (
    VisualizerService, VisualizerTarget, _build_fixture_payload, _gobo_style,
)

_app = QApplication.instance() or QApplication([])


# ── Attrappen ────────────────────────────────────────────────────────────────
def _rg(lo, hi, name, kind=""):
    return SimpleNamespace(range_from=lo, range_to=hi, name=name, kind=kind)


def _ch(attr, nr, ranges=()):
    return SimpleNamespace(attribute=attr, channel_number=nr, ranges=list(ranges))


def _par():
    return [_ch("intensity", 1), _ch("color_r", 2), _ch("color_g", 3),
            _ch("color_b", 4), _ch("color_w", 5)]


def _mover():
    return [_ch("pan", 1), _ch("pan_fine", 2), _ch("tilt", 3), _ch("tilt_fine", 4),
            _ch("intensity", 5),
            _ch("shutter", 6, [_rg(0, 7, "Zu", "closed"), _rg(8, 255, "Offen", "open")]),
            _ch("color_wheel", 7, [_rg(0, 63, "Weiss"), _rg(64, 127, "Rot"),
                                   _rg(128, 191, "Blau"), _rg(192, 255, "Gruen")]),
            _ch("gobo_wheel", 8, [_rg(0, 31, "Offen"), _rg(32, 95, "Gobo Punkte"),
                                  _rg(96, 255, "Gobo Stern")]),
            _ch("prism", 9, [_rg(0, 9, "Aus"), _rg(10, 255, "3 Facet Prism")]),
            _ch("prism_rotation", 10), _ch("zoom", 11)]


def _bar():
    """4-Kopf-Mover-Bar: pan/tilt/color je Kopf (attr#N-Vergabe)."""
    chs = []
    n = 1
    for _h in range(4):
        for a in ("pan", "tilt", "color_r", "color_g", "color_b"):
            chs.append(_ch(a, n))
            n += 1
    chs.append(_ch("intensity", n))
    return chs


class _OM:
    """Output-Manager-Attrappe: liefert den Display-Frame je Universum."""

    def __init__(self):
        self.frames: dict = {}

    def get_display_frame(self, u):
        return self.frames.get(u)


def _state(fixtures, universes, om=None):
    st = SimpleNamespace(
        universes=universes,
        visualizer_positions={f.fid: (0, 0, 0) for f in fixtures},
        visualizer_docks={}, visualizer_rotations={}, live_view_positions={},
        output_manager=om, _callbacks=[])
    st.fixtures = fixtures
    st.get_patched_fixtures = lambda: st.fixtures
    st.subscribe = lambda cb: st._callbacks.append(cb)
    st.unsubscribe = lambda cb: None
    return st


def _fx(fid, address, universe=1, **kw):
    return SimpleNamespace(fid=fid, address=address, universe=universe,
                           fixture_profile_id=fid, mode_name="m",
                           channel_count=None, **kw)


class _Basis(unittest.TestCase):
    def setUp(self):
        self._orig = app_state_mod.get_channels_for_patched
        self.kanaele: dict = {}
        app_state_mod.get_channels_for_patched = lambda f: self.kanaele[f.fid]
        self.u1 = Universe(1)
        self.fx = [_fx(1, 1), _fx(2, 10), _fx(3, 40, invert_pan=True), _fx(4, 100)]
        self.kanaele = {1: _par(), 2: _mover(), 3: _mover(), 4: _bar()}
        self.om = _OM()
        self.st = _state(self.fx, {1: self.u1}, self.om)
        self.svc = VisualizerService(self.st)
        for adr, v in ((1, 255), (2, 200), (10, 100), (14, 255), (15, 20),
                       (40, 30), (100, 77)):
            self.u1.set_channel(adr, v)
        self._frame_aus_puffer()

    def tearDown(self):
        app_state_mod.get_channels_for_patched = self._orig

    def _frame_aus_puffer(self):
        """Der Output-Thread rechnet den Display-Frame aus dem Puffer."""
        self.om.frames[1] = self.u1.get_all()

    def _setze(self, adr, v):
        self.u1.set_channel(adr, v)
        self._frame_aus_puffer()

    def _ungecacht(self):
        out = {}
        for f in self.st.get_patched_fixtures():
            ch = app_state_mod.get_channels_for_patched(f)
            out[f.fid] = _build_fixture_payload(f, self.svc._collect_attrs(f), ch)
        return out

    def _stats(self):
        return self.svc.payload_cache_stats


class TrefferTest(_Basis):
    def test_unveraenderter_ausschnitt_trifft(self):
        a = self.svc._build_snapshot()
        self.assertEqual(self._stats(), {"hits": 0, "builds": 4})
        b = self.svc._build_snapshot()
        self.assertEqual(self._stats(), {"hits": 4, "builds": 0})
        for fid in a:
            self.assertIs(a[fid], b[fid], "Treffer liefert dasselbe Objekt")

    def test_kanal_im_ausschnitt_baut_nur_dieses_geraet(self):
        self.svc._build_snapshot()
        self._setze(3, 99)                         # color_g von Geraet 1
        s = self.svc._build_snapshot()
        self.assertEqual(self._stats(), {"hits": 3, "builds": 1})
        self.assertEqual(s[1], self._ungecacht()[1])
        self.assertEqual(s[1]["g"], 99)

    def test_feinkanal_baut_neu(self):
        self.svc._build_snapshot()
        self._setze(11, 128)                       # pan_fine von Geraet 2
        s = self.svc._build_snapshot()
        self.assertEqual(self._stats()["builds"], 1)
        self.assertEqual(s[2]["pan"], 100 + 128 / 256.0)

    def test_mehrkopf_letzter_kopf_baut_neu(self):
        self.svc._build_snapshot()
        self._setze(100 + 19, 222)                 # color_b#3 (letzter Kopf)
        s = self.svc._build_snapshot()
        self.assertEqual(self._stats()["builds"], 1)
        self.assertEqual(s[4]["heads"][3]["cb"], 222)

    def test_kanal_ausserhalb_aller_geraete_trifft(self):
        self.svc._build_snapshot()
        self._setze(300, 5)
        self.svc._build_snapshot()
        self.assertEqual(self._stats(), {"hits": 4, "builds": 0})

    def test_programmer_event_leert_den_cache_nicht(self):
        """Fader-/XY-Pad-Zuege feuern programmer_changed bei jeder Bewegung —
        der Programmer wirkt nur ueber den Frame, und der steckt im Schluessel."""
        self.svc._build_snapshot()
        self.svc._on_state("programmer_changed", 2)
        self.svc._build_snapshot()
        self.assertEqual(self._stats(), {"hits": 4, "builds": 0})


class InvalidierungTest(_Basis):
    def test_adresse_geaendert_ohne_event(self):
        self.svc._build_snapshot()
        self.fx[0].address = 2                     # gepatcht, Event kommt spaeter
        s = self.svc._build_snapshot()
        self.assertEqual(self._stats()["builds"], 1)
        self.assertEqual(s[1], self._ungecacht()[1])
        self.assertEqual(s[1]["intensity"], 200)

    def test_invert_flag_ohne_event(self):
        self.svc._build_snapshot()
        self.fx[1].invert_tilt = True
        s = self.svc._build_snapshot()
        self.assertEqual(self._stats()["builds"], 1)
        self.assertEqual(s[2], self._ungecacht()[2])

    def test_patch_event_baut_alles(self):
        self.svc._build_snapshot()
        self.svc._on_state("patch_changed", None)
        self.svc._build_snapshot()
        self.assertEqual(self._stats(), {"hits": 0, "builds": 4})

    def test_nullpunkt_aenderung_baut_alles(self):
        """Nullpunkte stehen nicht im Payload (sie reisen ueber die Geraeteliste),
        aber ihre Aenderung meldet sich als Patch-Event — der Cache faellt mit."""
        self.svc._build_snapshot()
        self.fx[1].pan_null = 12
        self.svc._on_state("patch_changed", None)
        self.svc._build_snapshot()
        self.assertEqual(self._stats()["hits"], 0)

    def test_profil_aenderung_neue_kanalliste(self):
        """Ein Profil-Edit leert den Kanal-Cache: es kommt eine NEUE Liste."""
        self.svc._build_snapshot()
        neu = _par()
        neu[0], neu[1] = _ch("color_r", 1), _ch("intensity", 2)
        self.kanaele[1] = neu
        s = self.svc._build_snapshot()
        self.assertEqual(self._stats()["builds"], 1)
        self.assertEqual((s[1]["r"], s[1]["intensity"]), (255, 200))

    def test_profil_gobo_range_neu(self):
        self.svc._build_snapshot()
        self._setze(10 + 7, 50)                    # Gobo-Wert von Geraet 2
        vorher = self.svc._build_snapshot()[2]["gobo"]
        self.assertEqual(vorher, self._ungecacht()[2]["gobo"])
        neu = _mover()
        neu[7] = _ch("gobo_wheel", 8, [_rg(0, 255, "Offen")])
        self.kanaele[2] = neu
        nachher = self.svc._build_snapshot()[2]["gobo"]
        self.assertNotEqual(nachher, vorher)
        self.assertEqual(nachher, self._ungecacht()[2]["gobo"])

    def test_show_wechsel_event(self):
        self.svc._build_snapshot()
        self.svc._on_state("show_loaded", None)
        self.svc._build_snapshot()
        self.assertEqual(self._stats()["hits"], 0)

    def test_show_wechsel_neue_objekte_gleiche_fid(self):
        """Neue Show, fids beginnen wieder bei 1 — auch ohne Event kein Treffer
        auf dem Geraet der alten Show."""
        self.svc._build_snapshot()
        self.st.fixtures = [_fx(1, 1), _fx(2, 10), _fx(3, 40, invert_pan=True),
                            _fx(4, 100)]
        self.svc._build_snapshot()
        self.assertEqual(self._stats()["hits"], 0)

    def test_entferntes_geraet_faellt_aus_dem_cache(self):
        self.svc._build_snapshot()
        self.st.visualizer_positions.pop(4)
        s = self.svc._build_snapshot()
        self.assertNotIn(4, s)
        self.assertNotIn(4, self.svc._payload_cache)

    def test_force_full_resync_leert(self):
        self.svc._build_snapshot()
        self.svc.force_full_resync()
        self.svc._build_snapshot()
        self.assertEqual(self._stats()["hits"], 0)


class DisplayFrameTest(_Basis):
    """WYSIWYG: der Schluessel kommt aus dem Display-Frame, nicht dem Puffer."""

    def test_blackout_wirkt_im_naechsten_bau(self):
        self.svc._build_snapshot()
        self.om.frames[1] = bytes(512)             # Blackout: Puffer unveraendert
        s = self.svc._build_snapshot()
        self.assertEqual(s[1]["intensity"], 0)
        self.assertEqual(self._stats()["hits"], 0)

    def test_not_aus_maske_wirkt_sofort(self):
        self.svc._build_snapshot()
        buf = bytearray(self.u1.get_all())
        buf[40 - 1] = 0                            # NOT-AUS maskiert Geraet 3
        self.om.frames[1] = bytes(buf)
        s = self.svc._build_snapshot()
        self.assertEqual(self._stats(), {"hits": 3, "builds": 1})
        self.assertEqual(s[3], self._ungecacht()[3])

    def test_puffer_aenderung_ohne_neuen_frame_bleibt_unsichtbar(self):
        self.svc._build_snapshot()
        self.u1.set_channel(1, 0)                  # nur Rohpuffer
        s = self.svc._build_snapshot()
        self.assertEqual(s[1]["intensity"], 255)
        self.assertEqual(self._stats()["hits"], 4)

    def test_blackout_kommt_als_diff_beim_ziel_an(self):
        gesehen = []
        t = VisualizerTarget("t", lambda js: None,
                             emit_payloads=lambda arr, full, seq: gesehen.append(arr))
        self.svc._targets.append(t)
        t.active = True
        self.svc._tick()
        self.om.frames[1] = bytes(512)
        self.svc._tick()
        self.assertTrue(gesehen[-1])
        self.assertTrue(all(p["intensity"] == 0 for p in gesehen[-1]))

    def test_ohne_display_frame_rohpuffer(self):
        self.om.frames.clear()
        self.svc._build_snapshot()
        self.u1.set_channel(2, 7)
        s = self.svc._build_snapshot()
        self.assertEqual(s[1]["r"], 7)
        self.assertEqual(self._stats()["builds"], 1)


class SicherheitsnetzTest(_Basis):
    def test_spaetestens_nach_gate_max_skips_alles_neu(self):
        self.svc._build_snapshot()
        hits = []
        for _ in range(VisualizerService.GATE_MAX_SKIPS + 1):
            self.svc._build_snapshot()
            hits.append(self._stats()["hits"])
        self.assertEqual(hits[:-1], [4] * VisualizerService.GATE_MAX_SKIPS)
        self.assertEqual(hits[-1], 0)

    def test_aenderung_ohne_event_und_schluessel_greift_spaetestens_dort(self):
        """Ein Range-Name, IN PLACE geaendert (weder Schluessel noch Event
        sehen das), erscheint spaetestens beim Sicherheitsnetz-Bau."""
        self._setze(10 + 7, 50)
        vorher = self.svc._build_snapshot()[2]["gobo"]
        self.kanaele[2][7].ranges[1].name = "Offen"
        # unmemoisiert nachrechnen: auch der Gobo-Merkzettel sieht den
        # In-place-Edit nicht
        soll = _gobo_style(self.svc._collect_attrs(self.fx[1]), self.kanaele[2])
        self.assertNotEqual(soll, vorher)
        werte = [self.svc._build_snapshot()[2]["gobo"]
                 for _ in range(VisualizerService.GATE_MAX_SKIPS + 1)]
        self.assertEqual(werte[-1], soll)


class GegenprobeTest(_Basis):
    def test_zufalls_frames_identisch_zum_ungecachten_bau(self):
        rnd = random.Random(77)
        self.fx.append(_fx(5, 200, swap_pan_tilt=True, invert_pan=True))
        self.kanaele[5] = _mover()
        self.fx.append(_fx(6, 505))                 # ragt ueber Kanal 512
        self.kanaele[6] = _bar()
        for f in self.fx[-2:]:
            self.st.visualizer_positions[f.fid] = (0, 0, 0)
        adressen = list(range(1, 513))
        treffer = neubau = 0
        for runde in range(400):
            # wenige Kanaele je Runde, damit Treffer UND Neubauten vorkommen
            for adr in rnd.sample(adressen, rnd.choice((0, 1, 3, 20))):
                self.u1.set_channel(adr, rnd.randrange(256))
            if runde % 37 == 0:
                self.svc._on_state("programmer_changed", None)
            if runde % 53 == 0:
                self.svc._on_state("patch_changed", None)
            self._frame_aus_puffer()
            if runde % 11 == 0:                     # Blackout-Frames dazwischen
                self.om.frames[1] = bytes(512)
            self.assertEqual(self.svc._build_snapshot(), self._ungecacht(),
                             f"Runde {runde}")
            treffer += self._stats()["hits"]
            neubau += self._stats()["builds"]
        self.assertGreater(treffer, 500)
        self.assertGreater(neubau, 200)


if __name__ == "__main__":
    unittest.main()
