"""UI-109 (Hinweis aus dem Gegenlesen von #1230): der schnelle Weg des
Patch-Fingerabdrucks der 2D-Ansicht, gegen ein ECHTES ``PatchedFixture``.

UI-90 liest die Patch-Felder seither direkt aus dem ``__dict__`` der
ORM-Instanz statt ueber den SQLAlchemy-Deskriptor (~0,4 ms je Bild). Geprueft
war das bisher nur mit Attrappen. Hier mit den Objekten, die die App wirklich
liefert (``get_patched_fixtures``), und mit dem Fall, an dem der schnelle Weg
falsch werden kann: ein VERFALLENES Objekt (nach ``commit``/``expire``) traegt
seine Spaltenwerte nicht mehr im ``__dict__`` — ``dict.get`` lieferte dann
still ``None`` fuer jedes Feld, und ein geaenderter Patch fiele dem Abdruck
nicht auf. Dann muss der Deskriptor-Weg ran (der laedt nach).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.core.app_state import get_state  # noqa: E402
from src.core.database.models import PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show  # noqa: E402
from src.ui.views.live_view import StageCanvas  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _langsam(f) -> tuple:
    """Der Deskriptor-Weg — so war der Abdruck vor UI-90 gebaut."""
    return (f.fid,) + tuple(getattr(f, k, None) for k in StageCanvas._PATCH_FELDER)


class PatchFingerabdruckTest(unittest.TestCase):

    def setUp(self):
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=7, label="Mover links", fixture_profile_id=4242, mode_name="16-Kanal",
            universe=2, address=33, channel_count=16, fixture_type="moving_head",
            pan_range_deg=540, tilt_range_deg=270, pan_zero_dmx=127.5,
            invert_pan=True), undoable=False)

    def tearDown(self):
        reset_show()

    def _fx(self):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == 7)

    def test_schneller_weg_mit_echtem_geraet(self):
        f = self._fx()
        self.assertIn("_sa_instance_state", f.__dict__,
                      "Vorbedingung: das Cache-Objekt nimmt den __dict__-Weg")
        fp = StageCanvas._patch_fingerabdruck(f)
        self.assertEqual(fp, _langsam(f))
        self.assertEqual(fp[:3], (7, 2, 33))
        self.assertIn("Mover links", fp)
        self.assertIn(127.5, fp)

    def test_geaenderter_patch_aendert_den_abdruck(self):
        vorher = StageCanvas._patch_fingerabdruck(self._fx())
        self.assertTrue(self.state.update_fixture(7, address=101, undoable=False))
        f = self._fx()
        nachher = StageCanvas._patch_fingerabdruck(f)
        self.assertNotEqual(nachher, vorher)
        self.assertEqual(nachher, _langsam(f))

    def test_verfallenes_objekt_nimmt_den_deskriptor_weg(self):
        with Session(self.state._show_engine) as s:
            f = s.execute(select(PatchedFixture).where(PatchedFixture.fid == 7)).scalars().one()
            s.expire(f)
            self.assertNotIn("address", f.__dict__, "Vorbedingung: Spalten verfallen")
            self.assertEqual(StageCanvas._patch_fingerabdruck(f), _langsam(f))

    def test_teilweise_verfallenes_objekt(self):
        with Session(self.state._show_engine) as s:
            f = s.execute(select(PatchedFixture).where(PatchedFixture.fid == 7)).scalars().one()
            s.expire(f, ["address"])
            self.assertNotIn("address", f.__dict__)
            fp = StageCanvas._patch_fingerabdruck(f)
            self.assertEqual(fp, _langsam(f))
            self.assertIn(33, fp)


if __name__ == "__main__":
    unittest.main()
