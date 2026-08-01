"""FM-10: Zielen auf eine Mover-Bar bewegt jetzt die echten Köpfe.

Eine Mover-Bar hat pro Kopf einen echten Pan- UND Tilt-Motor — sie fällt aber
unter ``is_spider_fixture`` (sie hat ja auch mehrere Farbbänke) und landete
deshalb im Aim-Werkzeug im STATISCHEN Zweig. Dort wird nur
``visualizer_rotations`` gesetzt: eine rein **visuelle** Drehung des Gehäuses.

★ Das ist der eigentliche Befund: **am echten Gerät passierte gar nichts.** Im
3D drehte sich die Bar, das Rig blieb stehen. Der Backlog-Eintrag las sich wie
eine Komfort-Frage („wäre wünschenswert"), war aber eine tote Funktion.

Der Test prüft deshalb das, was zählt: landen nach dem Zielen Pan/Tilt-Werte
auf den Kanälen **jedes** Kopfes?
"""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import (get_channels_for_patched, get_state,  # noqa: E402
                                is_spider_fixture)
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.visualizer.visualizer_window import VisualizerBridge    # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _pid(short):
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class MoverBarAimTest(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Bar", fixture_profile_id=_pid("MOVBAR4"),
            mode_name="22-Kanal", channel_count=22, universe=1, address=1,
            fixture_type="moving_head"), undoable=False)
        self.state.visualizer_positions[1] = (0.0, 5.0, 0.0)
        # aimFixturesAt lebt auf der BRIDGE (dem QObject, das JS ruft), nicht
        # auf dem Fenster — die Bridge ohne __init__ bauen, sonst zieht sie die
        # halbe Fenster-Welt nach.
        self.win = VisualizerBridge.__new__(VisualizerBridge)
        self.win._state = self.state

    def _fx(self):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == 1)

    def test_voraussetzung_die_bar_gilt_als_spider(self):
        """Die Ausgangslage, die den Fehler erzeugte: sie IST ein Spider im
        Sinne der Farb-Erkennung — genau deshalb griff der falsche Zweig."""
        self.assertTrue(is_spider_fixture(self._fx()))

    def test_bar_wird_als_mehrkopf_mover_erkannt(self):
        self.assertEqual(self.win._mover_bar_heads(self._fx()), 4)

    def test_echter_spider_ist_keine_bar(self):
        """Ein Spider kippt nur (0 oder 1 Pan) — der darf NICHT in den neuen
        Zweig laufen, sonst schriebe man ihm Pan-Werte auf Kanäle, die es
        nicht gibt."""
        self.state.add_fixture(PatchedFixture(
            fid=2, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", channel_count=14, universe=1, address=100,
            fixture_type="moving_head"), undoable=False)
        fx2 = next(f for f in self.state.get_patched_fixtures() if f.fid == 2)
        self.assertEqual(self.win._mover_bar_heads(fx2), 0)

    def test_einzelkopf_mover_ist_keine_bar(self):
        self.state.add_fixture(PatchedFixture(
            fid=3, label="MH", fixture_profile_id=_pid("MH16"),
            mode_name="16-Kanal", channel_count=16, universe=1, address=200,
            fixture_type="moving_head"), undoable=False)
        fx3 = next(f for f in self.state.get_patched_fixtures() if f.fid == 3)
        self.assertEqual(self.win._mover_bar_heads(fx3), 0)

    def test_zielen_schreibt_auf_jeden_kopf(self):
        """★ Der Kern: vorher landete NICHTS im Programmer, es wurde nur die
        3D-Rotation gesetzt."""
        self.win.pyAimApplied = type("S", (), {"emit": staticmethod(lambda *a: None)})()
        self.win.aimFixturesAt(json.dumps({"fids": [1], "x": 4.0, "y": 0.0, "z": 3.0}))
        prog = self.state.programmer.get(1, {})
        self.assertTrue(prog, "Zielen hat gar nichts geschrieben")
        for h in range(4):
            for attr in ("pan", "tilt"):
                key = attr if h == 0 else f"{attr}#{h}"
                self.assertIn(key, prog, f"Kopf {h + 1}: {attr} fehlt ({sorted(prog)})")

    def test_die_koepfe_zeigen_in_dieselbe_richtung(self):
        """Parallel ist die bewusste Naeherung: WO auf der Schiene ein Kopf
        sitzt, weiss nur das 3D-Modell. Der Test haelt die Entscheidung fest,
        damit sie nicht versehentlich zerfaellt."""
        self.win.pyAimApplied = type("S", (), {"emit": staticmethod(lambda *a: None)})()
        self.win.aimFixturesAt(json.dumps({"fids": [1], "x": 4.0, "y": 0.0, "z": 3.0}))
        prog = self.state.programmer.get(1, {})
        pans = {prog.get("pan" if h == 0 else f"pan#{h}") for h in range(4)}
        self.assertEqual(len(pans), 1, f"Koepfe sollen parallel zeigen: {pans}")


if __name__ == "__main__":
    unittest.main()
