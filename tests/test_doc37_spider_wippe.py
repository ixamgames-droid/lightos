"""DOC-37: „Spider Wippe" der Event-Demo stand still.

Die Linie (``EfxAlgorithm.LINE``) laeuft auf der PAN-Achse; der SPIDER14 hat
keinen Pan, nur zwei Tilt-Motoren. Gemessen am Render-Pfad: ohne Drehung bleiben
beide Tilts bei 128. Der Generator ``build_demo_show_full.py`` dreht seine
Spider-Linie deshalb schon um 90 Grad; ``build_event_demo_2026.py`` tat es nicht.

Geprueft wird beides: dass der Generator die Wippe senkrecht stellt (statisch,
der Generator selbst schreibt eine Show nach ``shows/``) und dass genau das am
echten Geraet Bewegung erzeugt.
"""
import ast
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                        # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.app_state import get_channels_for_patched, get_state   # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins  # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.engine.efx import EfxAlgorithm, EfxFixture             # noqa: E402
from src.core.show.show_file import reset_show                       # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_event_demo_2026.py")


def _baum():
    with open(GENERATOR, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _wippe_aufruf(baum):
    for k in ast.walk(baum):
        if (isinstance(k, ast.Call) and isinstance(k.func, ast.Name) and k.func.id == "efx"
                and k.args and isinstance(k.args[0], ast.Constant)
                and k.args[0].value == "Spider Wippe"):
            return k
    return None


class GeneratorStelltDieWippeSenkrecht(unittest.TestCase):

    def test_wippe_hat_rotation_90(self):
        aufruf = _wippe_aufruf(_baum())
        self.assertIsNotNone(aufruf, "efx(\"Spider Wippe\", …) nicht gefunden")
        self.assertEqual(ast.unparse(aufruf.args[1]), "EfxAlgorithm.LINE")
        rot = {kw.arg: kw.value for kw in aufruf.keywords}.get("rotation")
        self.assertIsNotNone(rot, "ohne rotation laeuft die Linie auf der fehlenden Pan-Achse")
        self.assertEqual(ast.literal_eval(rot), 90.0)

    def test_helfer_reicht_rotation_durch(self):
        helfer = next(k for k in ast.walk(_baum())
                      if isinstance(k, ast.FunctionDef) and k.name == "efx")
        self.assertIn("rotation", [a.arg for a in helfer.args.args])
        quelle = ast.unparse(helfer)
        self.assertIn("e.rotation = rotation", quelle)


class WippeBewegtDenSpider(unittest.TestCase):
    """Am echten Render-Pfad: dieselbe Linie wie im Generator, einmal liegend,
    einmal senkrecht."""

    def _tilt_werte(self, rotation):
        ensure_builtins()
        reset_show()
        st = get_state()
        with Session(fdb_engine()) as s:
            p = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "SPIDER14")).scalars().first()
            pid = p.id
            modus = next(m.name for m in p.modes if len(m.channels) == 14)
        st.add_fixture(PatchedFixture(fid=1, label="SP", fixture_profile_id=pid,
                                      mode_name=modus, universe=1, address=1,
                                      channel_count=14, fixture_type="moving_head"),
                       undoable=False)
        fx = next(f for f in st.get_patched_fixtures() if f.fid == 1)
        tilts = [c.channel_number for c in get_channels_for_patched(fx)
                 if c.attribute == "tilt"]
        self.assertEqual(len(tilts), 2, "SPIDER14 hat zwei Tilt-Motoren")
        fm = st.function_manager
        e = fm.new_efx("Spider Wippe")
        e.algorithm = EfxAlgorithm.LINE
        e.fixtures = [EfxFixture(fid=1)]
        e.speed_hz, e.open_beam = 0.7, True
        e.x_offset = e.y_offset = 128.0
        e.width = e.height = 220
        e.phase_mode = "offset"
        e.rotation = rotation
        e.tempo_bus_id = ""          # Frei-Lauf: unabhaengig von einer BPM
        fm.start(e.id)
        self.addCleanup(fm.stop, e.id)
        werte = set()
        for _ in range(20):
            st._render_frame(0.1)
            werte.add(tuple(st.universes[1].get_channel(t) for t in tilts))
        return werte

    def test_liegende_linie_bewegt_nichts(self):
        """Positivkontrolle fuer den Befund: so stand die Wippe bisher."""
        self.assertEqual(self._tilt_werte(0.0), {(128, 128)})

    def test_senkrechte_linie_wippt(self):
        werte = self._tilt_werte(90.0)
        self.assertGreater(len(werte), 5, werte)


if __name__ == "__main__":
    unittest.main()
