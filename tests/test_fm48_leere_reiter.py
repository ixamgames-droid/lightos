"""FM-48 (Teil 2): der Programmer zeigt keine leeren Reiter.

In der echten App gesehen (2026-09-29): die Nebelmaschine N-10 bekam einen
Reiter „Color" mit „Keine Color-Kanäle gefunden", der 154-Kanal-Balken ZQ06121
einen leeren Reiter „Weitere" — waehrend Position/Gobo schon verschwanden.
Und am 48-Zonen-Balken stand „Synchron (beide gleich)".

Nur eingebaute Profile (QA-23).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox               # noqa: E402
from sqlalchemy import select                                        # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.app_state import get_state                             # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins  # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                       # noqa: E402
from src.ui.views.programmer_view import ProgrammerView              # noqa: E402

RIG = [  # fid, Kurzname, Modus, Kanaele, Typ
    (1, "EURON10", "2-Kanal (Nebel + Lüfter)", 2, "hazer"),
    (2, "ZQ06121", "154-Kanal 48 Zonen RGB + 8x Weiss", 154, "matrix"),
    (3, "ZQ01424", "8-Kanal RGBW", 8, "par"),
]


def _app():
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class LeereReiterTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()
        ensure_builtins()

    def setUp(self):
        reset_show()
        self.st = get_state()
        adr = 1
        for fid, kurz, modus, n, typ in RIG:
            self.st.add_fixture(PatchedFixture(
                fid=fid, label=kurz, fixture_profile_id=_pid(kurz), mode_name=modus,
                universe=1, address=adr, channel_count=n, fixture_type=typ), undoable=False)
            adr += n
        self.v = ProgrammerView()
        self.addCleanup(self.v.deleteLater)

    def _sichtbar(self, fids):
        self.st.set_selected_fids(fids)
        _app().processEvents()
        t = self.v._main_tabs
        return {t.tabText(i) for i in range(t.count()) if t.isTabVisible(i)}

    def test_nebel_ohne_farbreiter(self):
        s = self._sichtbar([1])
        self.assertNotIn("Color", s)
        self.assertIn("Weitere", s)          # Luefter
        self.assertIn("Intensity", s)        # Nebel-Regler

    def test_balken_ohne_weitere(self):
        s = self._sichtbar([2])
        self.assertIn("Color", s)
        self.assertNotIn("Weitere", s)

    def test_gemischte_auswahl_zeigt_die_vereinigung(self):
        s = self._sichtbar([1, 2])
        self.assertTrue({"Color", "Weitere", "Intensity"} <= s)

    def test_ohne_auswahl_bleiben_die_hinweise_sichtbar(self):
        self._sichtbar([1])
        s = self._sichtbar([])
        self.assertTrue({"Intensity", "Color", "Weitere"} <= s)

    def test_viele_koepfe_heissen_alle_nicht_beide(self):
        self._sichtbar([2])
        texte = [c.itemText(0) for c in self.v.findChildren(QComboBox)
                 if c.count() and c.itemData(0) == "sync"]
        self.assertIn("Synchron (alle gleich)", texte)
        self.assertFalse([t for t in texte if "beide" in t], texte)


if __name__ == "__main__":
    unittest.main()
