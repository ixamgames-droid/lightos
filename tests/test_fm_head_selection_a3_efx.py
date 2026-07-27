"""FM-HEADLAYOUT A3 (Teil 1): EFX kann EINEN KOPF als Ziel haben.

Bisher war ein EFX-Ziel immer ein ganzes Gerät; bei Mehrkopf-Movern rollte die
FM-16b-Kopfwelle über ALLE Köpfe. Jetzt kann ein Ziel ein einzelner Kopf sein
(``EfxFixture.head``) — dann bewegt der Effekt ausschließlich dessen Kanäle.

Die drei Punkte, auf die es ankommt:
* **Show-Format additiv:** ``head`` wird nur bei echten Kopf-Zielen geschrieben →
  Altshows laden unverändert UND ihr Dump bleibt byte-identisch (Fixpunkt).
* **Eine Rechen-Quelle:** ``_values()`` (fid-gekeyt, von Vorschau + Bestandstests
  genutzt) ist jetzt eine Projektion auf ``_target_values()`` (je Ziel) — nur so
  behalten zwei Kopf-Ziele desselben Geräts ihre eigene Phase.
* **Kopf-genauer Schreibpfad** über ``channels_for_head`` (dieselbe Quelle wie die
  Pro-Kopf-Matrix): mehrfach vorkommende Attribute gehören dem Kopf, einmalige
  (Master-Dimmer) bleiben geteilt.
"""
from __future__ import annotations
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.efx import EfxAlgorithm, EfxFixture, EfxInstance


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.ranges = []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    protocol = ""
    invert_pan = False
    invert_tilt = False
    swap_pan_tilt = False
    spider_dual_tilt = False

    def __init__(self, fid=1, universe=1, address=1, channel_count=8):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = channel_count
        self.fixture_type = "moving_head"
        self.label = f"Bar {fid}"


# 4-Kopf-Mover: pan/tilt VIERMAL (Kopf 0..3) + EIN gemeinsamer Master-Dimmer.
_HEAD_CHANS = [
    _Ch("pan", 1), _Ch("tilt", 2),
    _Ch("pan", 3), _Ch("tilt", 4),
    _Ch("pan", 5), _Ch("tilt", 6),
    _Ch("pan", 7), _Ch("tilt", 8),
    _Ch("intensity", 9),
]


def _efx(targets, **kw) -> EfxInstance:
    e = EfxInstance(name="T")
    e.algorithm = EfxAlgorithm.CIRCLE
    e.fixtures = list(targets)
    e.width = 200.0
    e.height = 200.0
    e.speed_hz = 0.0          # Phase bleibt stehen -> deterministisch
    e._running = True
    for k, v in kw.items():
        setattr(e, k, v)
    return e


class EfxHeadTargetWriteTest(unittest.TestCase):
    """Renderpfad: ein Kopf-Ziel bewegt NUR diesen Kopf."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _HEAD_CHANS
        self.addCleanup(lambda: setattr(A, "get_channels_for_patched", self._orig))
        self.uni = Universe(1)
        self.fx = _Fx()

    def _write(self, e):
        e.write({1: self.uni}, [self.fx], 0.0)

    def test_head_target_touches_only_that_heads_channels(self):
        e = _efx([EfxFixture(fid=1, head=1)])
        self._write(e)
        # Kopf 1 = pan CH3 / tilt CH4 -> beschrieben; alle anderen Pan/Tilt bleiben 0.
        self.assertNotEqual((self.uni.get_channel(3), self.uni.get_channel(4)), (0, 0),
                            "Kopf 1 wurde nicht bewegt")
        for ch in (1, 2, 5, 6, 7, 8):
            self.assertEqual(self.uni.get_channel(ch), 0,
                             f"CH{ch} gehört einem anderen Kopf und wurde bewegt")

    def test_head_zero_target_is_the_first_occurrence(self):
        e = _efx([EfxFixture(fid=1, head=0)])
        self._write(e)
        self.assertNotEqual((self.uni.get_channel(1), self.uni.get_channel(2)), (0, 0))
        for ch in (3, 4, 5, 6, 7, 8):
            self.assertEqual(self.uni.get_channel(ch), 0)

    def test_whole_device_target_still_drives_all_heads(self):
        # Regressionsschutz FM-16b: ohne head bleibt die Kopfwelle über alle Köpfe.
        e = _efx([EfxFixture(fid=1)], head_spread=1.0)
        self._write(e)
        moved = [ch for ch in (1, 3, 5, 7) if self.uni.get_channel(ch) != 0]
        self.assertGreaterEqual(len(moved), 2,
                                f"Kopfwelle fehlt, bewegte Pan-Kanäle: {moved}")

    def test_shared_master_dimmer_is_written_for_a_head_target(self):
        # open_beam setzt intensity; der EINE Master-Dimmer ist geteilt und muss
        # auch bei einem Kopf-Ziel gesetzt werden, sonst bleibt der Kopf dunkel.
        e = _efx([EfxFixture(fid=1, head=2)], open_beam=True)
        self._write(e)
        self.assertEqual(self.uni.get_channel(9), 255,
                         "gemeinsamer Master-Dimmer wurde beim Kopf-Ziel nicht gesetzt")

    def test_two_head_targets_of_one_device_keep_separate_phases(self):
        # Der Kern der _target_values-Umstellung: zwei Ziele DESSELBEN Geräts mit
        # verschiedenem Offset dürfen sich nicht überschreiben.
        #
        # ⚠ Geräte-Fächer AUS (spread=0, phase_mode="sync"): sonst addiert
        # _fan_for(i, n) je Ziel i/n*spread dazu, und ein Offset von 0.5 hebt sich
        # bei zwei Zielen mit dem Fächer exakt auf (0.5 + 0.5 = 1.0 ≡ 0.0) — der
        # Test wäre dann grün-blind für genau den Fehler, den er sucht.
        e = _efx([EfxFixture(fid=1, head=0, start_offset=0.0),
                  EfxFixture(fid=1, head=1, start_offset=0.5)],
                 spread=0.0, phase_mode="sync")
        self._write(e)
        head0 = (self.uni.get_channel(1), self.uni.get_channel(2))
        head1 = (self.uni.get_channel(3), self.uni.get_channel(4))
        self.assertNotEqual(head0, head1,
                            "beide Köpfe stehen gleich — die Phasen wurden "
                            "im fid-gekeyten Dict überschrieben")

    def test_values_projection_matches_target_values(self):
        e = _efx([EfxFixture(fid=1, head=0), EfxFixture(fid=2, head=1)])
        tv = e._target_values()
        self.assertEqual(len(tv), 2)
        self.assertEqual(e._values(), {1: tv[0], 2: tv[1]},
                         "_values ist keine Projektion von _target_values mehr")


class EfxHeadPersistenceTest(unittest.TestCase):
    """Show-Format: additiv, Altshows unverändert."""

    def test_head_survives_roundtrip(self):
        e = _efx([EfxFixture(fid=3, head=2, start_offset=0.25)])
        back = EfxInstance.from_dict(e.to_dict())
        self.assertEqual(back.fixtures[0].fid, 3)
        self.assertEqual(back.fixtures[0].head, 2)
        self.assertAlmostEqual(back.fixtures[0].start_offset, 0.25)

    def test_whole_device_dump_has_no_head_key(self):
        # Fixpunkt-Schutz: eine Altshow darf beim Speichern NICHT plötzlich
        # ein head-Feld bekommen (sonst ändert der erste Save jede Show-Datei).
        e = _efx([EfxFixture(fid=3)])
        self.assertEqual(e.to_dict()["fixtures"], [{"fid": 3, "offset": 0.0}])

    def test_old_show_without_head_loads_as_whole_device(self):
        d = _efx([EfxFixture(fid=4)]).to_dict()
        d["fixtures"] = [{"fid": 4, "offset": 0.0}]      # so sieht eine Altshow aus
        back = EfxInstance.from_dict(d)
        self.assertIsNone(back.fixtures[0].head)

    def test_garbage_head_falls_back_to_whole_device(self):
        d = _efx([EfxFixture(fid=4)]).to_dict()
        d["fixtures"] = [{"fid": 4, "offset": 0.0, "head": "quatsch"}]
        back = EfxInstance.from_dict(d)
        self.assertIsNone(back.fixtures[0].head,
                          "kaputtes head-Feld darf das Ziel nicht verlieren")

    def test_negative_head_is_clamped(self):
        d = _efx([EfxFixture(fid=4)]).to_dict()
        d["fixtures"] = [{"fid": 4, "offset": 0.0, "head": -3}]
        self.assertEqual(EfxInstance.from_dict(d).fixtures[0].head, 0)

    def test_double_roundtrip_is_a_fixpoint(self):
        e = _efx([EfxFixture(fid=3, head=1), EfxFixture(fid=4)])
        d1 = e.to_dict()
        d2 = EfxInstance.from_dict(d1).to_dict()
        self.assertEqual(d1["fixtures"], d2["fixtures"])


class EfxViewTargetBuilderTest(unittest.TestCase):
    """Ziel-Bauer der EFX-Ansicht: Kopf-Auswahl -> Kopf-Ziele (eine Quelle für
    alle drei Zuweisungs-Stellen)."""

    def _targets(self, heads_map, fids=(1, 2)):
        """``_targets_for`` mit gestubbter Kopf-Auswahl.

        ⚠ Die EfxView hat KEIN ``self._state`` — sie holt den State pro Zugriff
        aus ``get_state()``. Der Stub muss also GENAU DA ansetzen, sonst testet man
        eine Struktur, die es nicht gibt (mein erster Wurf tat das und riss den
        Bestandstest ``test_efx_follow_no_clobber`` mit)."""
        import src.core.app_state as _A
        from src.ui.views.efx_view import EfxView
        orig = _A.get_state
        _A.get_state = lambda: types.SimpleNamespace(
            selected_heads_for=lambda fid: heads_map.get(int(fid)))
        self.addCleanup(lambda: setattr(_A, "get_state", orig))
        return EfxView._targets_for(types.SimpleNamespace(), list(fids))

    def test_head_selection_expands_into_one_target_per_head(self):
        targets = self._targets({1: {0, 2}, 2: None})
        self.assertEqual([(t.fid, t.head) for t in targets],
                         [(1, 0), (1, 2), (2, None)])

    def test_no_head_api_falls_back_to_whole_devices(self):
        import src.core.app_state as _A
        from src.ui.views.efx_view import EfxView
        orig = _A.get_state
        _A.get_state = lambda: types.SimpleNamespace()   # State ohne die neue API
        self.addCleanup(lambda: setattr(_A, "get_state", orig))
        targets = EfxView._targets_for(types.SimpleNamespace(), [5, 6])
        self.assertEqual([(t.fid, t.head) for t in targets], [(5, None), (6, None)])

    def test_labels_name_the_head(self):
        from src.ui.views.efx_view import EfxView
        self.assertEqual(EfxView._target_label(EfxFixture(fid=7)), "Fixture #7")
        self.assertEqual(EfxView._target_label(EfxFixture(fid=7, head=2)),
                         "Fixture #7 · K3")


if __name__ == "__main__":
    unittest.main()
