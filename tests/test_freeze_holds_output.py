"""BUG-FBW Slice 3 — Freeze haelt jetzt ALLES an, nicht nur den Tempo-Bus.

Davids Meldung (2026-08-01): „Freeze hat nicht immer alles eingefroren."
Seine Entscheidung (2026-08-02) auf die offene Frage: **ja**, Freeze soll alles
anhalten.

Vorher rief der Knopf nur ``tempo_bus.toggle_freeze()`` — was nicht am Tempo-Bus
hing, lief weiter. **Die naheliegende Reparatur war nachweislich falsch:** ein
„dt=0"-Freeze haette ``rgb_matrix``, ``efx`` und die Cue-Fades gar nicht
angehalten, weil die ihren Fortschritt aus ``time.monotonic()`` ziehen und nicht
aus dem uebergebenen ``dt``. Deshalb liegt der Freeze auf der **Render-Stufe**:
``_render_frame`` rechnet gar nicht mehr, die Universen behalten ihren Stand,
der Sende-Thread schickt genau den weiter.

Drei Dinge muss dieser Test belegen, und alle drei am DMX statt am Zustand:

1. der Output haelt wirklich, auch wenn ein Effekt laeuft;
2. **Blackout und Laser-NOT-AUS greifen im eingefrorenen Zustand weiter durch** —
   ein Freeze darf den Notaus nicht aushebeln (sie liegen in
   ``OutputManager._send_all``, also NACH dem Renderer);
3. beim Auftauen springt nichts: die monotonic-Anker werden um die eingefrorene
   Dauer nachgezogen.
"""
from __future__ import annotations

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_channels_for_patched, get_state  # noqa: E402
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import (FixtureProfile,               # noqa: E402
                                      PatchedFixture)
from src.core.engine.scene import Scene                             # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Uhr:
    """Kontrollierte Zeit — echte Wartezeiten machen Tests langsam und flakey."""
    def __init__(self, start=1000.0):
        self.jetzt = start

    def __call__(self):
        return self.jetzt

    def weiter(self, sekunden):
        self.jetzt += sekunden


class _Basis(unittest.TestCase):

    def setUp(self):
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="MH1", fixture_profile_id=_pid("MH16"),
            mode_name="16-Kanal", universe=1, address=1,
            channel_count=16, fixture_type="moving_head"), undoable=False)
        self.addCleanup(lambda: self.state.set_freeze(False))
        self.addCleanup(self.state.clear_programmer)

    def _frame(self):
        self.state._render_frame(0.02)
        return self.state.universes[1].get_all()

    def _addr(self, attribute: str) -> int:
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 1)
        treffer = [fx.address + c.channel_number - 1
                   for c in get_channels_for_patched(fx)
                   if c.attribute == attribute]
        self.assertTrue(treffer, f"Vorbedingung: Profil hat {attribute!r}")
        return treffer[0]


class HaeltTest(_Basis):
    """Haelt der Output wirklich?"""

    def test_programmer_aenderung_kommt_im_freeze_nicht_durch(self):
        """Der Programmer flusht bei JEDEM Wert direkt ins Universe, am
        Renderer vorbei — ohne den Schnappschuss in der Ausgabestufe leckte ein
        gehaltener Fader durch den Freeze. Deshalb hier am GESENDETEN Frame
        gemessen, nicht am Universum."""
        om = self.state.output_manager
        dim = self._addr("intensity")
        self.state.set_programmer_value(1, "intensity", 100)
        self._frame()
        om._send_all()
        self.assertEqual(om._display_frame[1][dim - 1], 100)

        self.state.set_freeze(True)
        self.state.set_programmer_value(1, "intensity", 250)
        self._frame()
        om._send_all()

        self.assertEqual(om._display_frame[1][dim - 1], 100,
                         "eingefroren heisst eingefroren")

    def test_nach_dem_auftauen_kommt_wieder_alles_durch(self):
        dim = self._addr("intensity")
        self.state.set_programmer_value(1, "intensity", 100)
        self._frame()
        self.state.set_freeze(True)
        self.state.set_programmer_value(1, "intensity", 250)
        self._frame()

        self.state.set_freeze(False)
        om = self.state.output_manager
        self._frame()
        om._send_all()
        self.assertEqual(om._display_frame[1][dim - 1], 250)

    def test_laufende_szene_friert_mit_ein(self):
        """Genau der Fall, den der Tempo-Bus-Freeze nicht erwischte."""
        dim = self._addr("intensity")
        fm = self.state.function_manager
        sc = Scene("Halb")
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 1)
        ch = next(c for c in get_channels_for_patched(fx)
                  if c.attribute == "intensity")
        sc.set_value(1, ch.channel_number, 120)
        fm.add(sc)
        self.addCleanup(lambda: fm.remove(sc.id))
        fm.start(sc.id)
        self.assertEqual(self._frame()[dim - 1], 120)

        self.state.set_freeze(True)
        fm.stop(sc.id)
        self.assertEqual(self._frame()[dim - 1], 120,
                         "auch das STOPPEN darf im Freeze nicht durchschlagen")

    def test_zweimal_einfrieren_ist_kein_fehler(self):
        self.assertTrue(self.state.set_freeze(True))
        self.assertTrue(self.state.set_freeze(True))
        self.assertFalse(self.state.set_freeze(False))
        self.assertFalse(self.state.set_freeze(False))


class SicherheitTest(_Basis):
    """Ein Freeze darf den Notaus nicht aushebeln."""

    def _gesendet(self, om, univ=1) -> bytes:
        om._send_all()
        return om._display_frame[univ]

    def test_blackout_greift_auch_im_freeze(self):
        """Blackout liegt in der Sende-Schleife, also NACH dem Renderer — genau
        deshalb ist der Freeze auf der Render-Stufe sicher. Hier gemessen statt
        aus dem Code geschlossen."""
        om = self.state.output_manager
        dim = self._addr("intensity")
        self.state.set_programmer_value(1, "intensity", 200)
        self._frame()
        self.state.set_freeze(True)

        self.assertEqual(self._gesendet(om)[dim - 1], 200, "Vorbedingung: hell")

        om.set_blackout(True)
        self.addCleanup(lambda: om.set_blackout(False))
        self.assertEqual(self._gesendet(om)[dim - 1], 0,
                         "Blackout muss auch eingefroren durchgreifen")

    def test_grand_master_greift_auch_im_freeze(self):
        om = self.state.output_manager
        dim = self._addr("intensity")
        self.state.set_programmer_value(1, "intensity", 200)
        self._frame()
        self.state.set_freeze(True)
        self.assertEqual(self._gesendet(om)[dim - 1], 200)

        alt = om.grand_master
        om.grand_master = 0.0
        self.addCleanup(lambda: setattr(om, "grand_master", alt))
        self.assertEqual(self._gesendet(om)[dim - 1], 0,
                         "der Master muss auch eingefroren wirken")


class AuftauenTest(_Basis):
    """Beim Auftauen darf nichts springen."""

    def test_matrix_anker_wird_um_die_eingefrorene_dauer_nachgezogen(self):
        """Ohne das Nachziehen rechnete die Matrix die ganze eingefrorene Dauer
        beim ersten Tick danach in EINEM Schritt ab — ein sichtbarer Sprung."""
        import src.core.app_state as A
        from src.core.engine.rgb_matrix import RgbMatrixInstance

        uhr = _Uhr()
        echt = A.time.monotonic
        A.time.monotonic = uhr
        self.addCleanup(lambda: setattr(A.time, "monotonic", echt))

        m = RgbMatrixInstance("M")
        m._last_tick = uhr() - 0.02          # so, als haette er gerade getickt
        fm = self.state.function_manager
        fm.add(m)
        self.addCleanup(lambda: fm.remove(m.id))
        fm.start(m.id)
        vor_freeze = m._last_tick

        self.state.set_freeze(True)
        uhr.weiter(10.0)                     # zehn Sekunden eingefroren
        self.state.set_freeze(False)

        self.assertAlmostEqual(m._last_tick, vor_freeze + 10.0, places=3,
                               msg="der Anker muss um die eingefrorene Dauer "
                                   "weiterwandern, sonst springt der Effekt")

    def test_cue_fade_wird_mitgezogen(self):
        """Ein 3-Sekunden-Fade waere nach einem 10-Sekunden-Freeze sonst beim
        Auftauen sofort fertig, statt dort weiterzumachen, wo er stand."""
        import src.core.app_state as A
        from src.core.engine.cue_stack import CueStack, FadeState

        uhr = _Uhr()
        echt = A.time.monotonic
        A.time.monotonic = uhr
        self.addCleanup(lambda: setattr(A.time, "monotonic", echt))

        stack = CueStack("S")
        stack._fade = FadeState({}, {}, duration=3.0, delay=0.0)
        stack._fade.start_time = uhr()
        vorher = stack._fade.start_time

        class _Ex:
            pass
        ex = _Ex()
        ex.stack = stack

        class _PE:
            executors = [ex]
        alt = self.state.playback_engine
        self.state.playback_engine = _PE()
        self.addCleanup(lambda: setattr(self.state, "playback_engine", alt))

        self.state.set_freeze(True)
        uhr.weiter(10.0)
        self.state.set_freeze(False)

        self.assertAlmostEqual(stack._fade.start_time, vorher + 10.0, places=3)

    def test_von_hand_gescrubbter_fade_bleibt_unangetastet(self):
        """Ein manueller Crossfade haengt an der Faderposition, nicht an der
        Zeit — ihn zu verschieben waere falsch."""
        import src.core.app_state as A
        from src.core.engine.cue_stack import CueStack, FadeState

        uhr = _Uhr()
        echt = A.time.monotonic
        A.time.monotonic = uhr
        self.addCleanup(lambda: setattr(A.time, "monotonic", echt))

        stack = CueStack("S")
        stack._fade = FadeState({}, {}, duration=3.0, delay=0.0)
        stack._fade.manual = True
        stack._fade.start_time = uhr()
        vorher = stack._fade.start_time

        stack.shift_clock(10.0)
        self.assertEqual(stack._fade.start_time, vorher)

    def test_der_ton_wird_bewusst_nicht_eingefroren(self):
        """Eine laufende Musik-Blende ist kein Licht. ``audio_func`` hat deshalb
        kein ``shift_clock`` — festgehalten, damit es niemand „nachruestet",
        ohne die Entscheidung zu kennen."""
        from src.core.engine.audio_func import AudioFunction
        from src.core.engine.function import Function
        self.assertIs(AudioFunction.shift_clock, Function.shift_clock,
                      "AudioFunction darf shift_clock NICHT ueberschreiben — "
                      "eine laufende Musik-Blende ist kein Licht")


if __name__ == "__main__":
    unittest.main()
