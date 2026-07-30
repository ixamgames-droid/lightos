"""VIZ-LIVEVIEW-FOOTGUN: eine 2D-Zuweisung verschiebt ausdrückliche 3D-Positionen.

2D und 3D sind zwei Projektionen **desselben** SceneGraph-Knotens: ein
2D-Pixelpaar leitet über ``live_to_world3d`` die 3D-x/z ab, die Höhe bleibt. Im
interaktiven Betrieb ist das genau richtig — man zieht ein Symbol im Grundriss
und das Gerät wandert.

In einem **Build-Skript** ist es eine Falle. Am echten AppState gemessen::

    st.visualizer_positions = {1: (3.0, 6.0, -4.0)}   # Truss-Koordinaten
    st.live_view_positions  = {1: (100.0, 500.0)}     # 2D-Raster danach
    -> visualizer_positions == {1: (-10.0, 6.0, 15.0)}

x und z kommen jetzt aus dem Pixelraster; nur die Höhe überlebt. In der
Mega-Arena-Show landeten die Mover so bei z = 20 m — und weil nur Fixtures MIT
2D-Eintrag betroffen sind, sah es aus wie „manche Geräte stehen falsch".

Der Riegel warnt, **ohne das Verhalten zu ändern** (wer das Raster bewusst
setzt, bekommt es) und nur bei der Ganz-Dict-Zuweisung — dem Weg der
Build-Skripte. Interaktives Ziehen schreibt einzelne Einträge und läuft hier
nicht durch.
"""
import io
import os
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from src.core.app_state import get_state                         # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine    # noqa: E402
from src.core.database.models import PatchedFixture, FixtureProfile  # noqa: E402
from src.core.show.show_file import reset_show                   # noqa: E402
from src.core.stage.coords import world3d_to_live                # noqa: E402


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class LiveViewFootgunTest(unittest.TestCase):
    def setUp(self):
        reset_show()
        self.st = get_state()
        self.st.add_fixture(PatchedFixture(
            fid=1, label="MH1", fixture_profile_id=_pid("MH16"),
            mode_name="16-Kanal", universe=1, address=1, channel_count=16),
            undoable=False)

    def _zuweisen(self, zweid) -> str:
        """2D zuweisen und die Ausgabe einfangen."""
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            self.st.live_view_positions = zweid
        return puffer.getvalue()

    def test_die_falle_besteht_weiterhin(self):
        """Erst dokumentieren, was passiert — sonst prüft der Rest ins Blaue."""
        self.st.visualizer_positions = {1: (3.0, 6.0, -4.0)}
        self._zuweisen({1: (100.0, 500.0)})
        x, y, z = dict(self.st.visualizer_positions)[1]
        self.assertAlmostEqual(y, 6.0, msg="die Hoehe ueberlebt")
        self.assertNotAlmostEqual(x, 3.0, msg="x kommt jetzt aus dem 2D-Raster")
        self.assertNotAlmostEqual(z, -4.0)

    def test_warnung_nennt_geraet_und_beide_positionen(self):
        self.st.visualizer_positions = {1: (3.0, 6.0, -4.0)}
        text = self._zuweisen({1: (100.0, 500.0)})
        self.assertIn("WARNUNG", text)
        self.assertIn("fid 1", text)
        self.assertIn("(3.0, -4.0)", text, "die alte Position muss dastehen")
        self.assertIn("world3d_to_live", text, "der Ausweg muss dastehen")

    def test_kein_laerm_wenn_2d_aus_3d_abgeleitet_ist(self):
        """★ Der empfohlene Weg darf nicht warnen — sonst gewöhnt man sich die
        Warnung ab."""
        self.st.visualizer_positions = {1: (3.0, 6.0, -4.0)}
        text = self._zuweisen({1: world3d_to_live(3.0, -4.0)})
        self.assertNotIn("WARNUNG", text)
        x, _y, z = dict(self.st.visualizer_positions)[1]
        self.assertAlmostEqual(x, 3.0)
        self.assertAlmostEqual(z, -4.0)

    def test_kein_laerm_ohne_ausdrueckliche_3d_position(self):
        """Der Normalfall: 2D-Show ohne 3D-Positionen — nichts wird verschoben."""
        text = self._zuweisen({1: (100.0, 500.0)})
        self.assertNotIn("WARNUNG", text)

    def test_kein_laerm_bei_leerer_zuweisung(self):
        self.st.visualizer_positions = {1: (3.0, 6.0, -4.0)}
        self.assertNotIn("WARNUNG", self._zuweisen({}))

    def test_verhalten_bleibt_unveraendert(self):
        """Der Riegel warnt nur — er darf nichts verhindern (sonst braeche er
        jede Bestands-Show, die das Raster bewusst setzt)."""
        self.st.visualizer_positions = {1: (3.0, 6.0, -4.0)}
        self._zuweisen({1: (100.0, 500.0)})
        self.assertEqual(dict(self.st.live_view_positions)[1], (100.0, 500.0))


if __name__ == "__main__":
    unittest.main()
