"""UI-ADDRCONFLICT: Adresskonflikte lassen sich jetzt auflösen, nicht nur melden.

Vorher war der Konflikt eine Sackgasse: die Patch-Ansicht färbte Zeilen rot und
schrieb „⚠ 2 Adresskonflikt(e)!" in die Werkzeugleiste, `validate_and_repair`
(Check 5) meldete beim Laden dasselbe — **report-only**, weil automatisches
Umadressieren eine Show still anders klingen ließe. Was fehlte, war der Schritt
danach: *welche* Geräte, und wohin damit.

Der Dialog listet die überlappenden Paare und bietet je Gerät die nächste freie
Startadresse an. Die Rechnung kommt aus `AppState.suggest_address` — derselben
Quelle wie im Patch-Dialog, kein zweiter Algorithmus.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402
from sqlalchemy import select                                  # noqa: E402
from sqlalchemy.orm import Session                             # noqa: E402

from src.core.app_state import get_state                       # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine  # noqa: E402
from src.core.database.models import PatchedFixture, FixtureProfile  # noqa: E402
from src.core.show.show_file import reset_show                 # noqa: E402
from src.ui.widgets.address_conflict_dialog import (           # noqa: E402
    AddressConflictDialog, find_conflict_pairs)

_app = QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Basis(unittest.TestCase):
    """Zwei PARs (je 8 Kanäle) mit ABSICHTLICH überlappenden Bereichen."""

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.pid = _pid("ZQ01424")
        self._patch(1, address=1)
        self._patch(2, address=5)      # 5–12 ueberlappt 1–8

    def _patch(self, fid, address, universe=1, channel_count=8):
        self.st.add_fixture(PatchedFixture(
            fid=fid, label=f"PAR {fid}", fixture_profile_id=self.pid,
            mode_name="8-Kanal", universe=universe, address=address,
            channel_count=channel_count), undoable=False)

    def _dlg(self):
        d = AddressConflictDialog(self.st)
        self.addCleanup(d.deleteLater)
        return d


class ErkennungTest(_Basis):
    def test_paare_bleiben_paare(self):
        """Für die Anzeige ist „1 überlappt 2" die Aussage — nicht „1 und 2
        sind irgendwie beteiligt"."""
        paare = find_conflict_pairs(self.st.get_patched_fixtures())
        self.assertEqual([(a.fid, b.fid) for a, b in paare], [(1, 2)])

    def test_anderes_universe_ist_kein_konflikt(self):
        self._patch(3, address=1, universe=2)
        paare = find_conflict_pairs(self.st.get_patched_fixtures())
        self.assertEqual([(a.fid, b.fid) for a, b in paare], [(1, 2)])

    def test_luecke_dazwischen_ist_kein_konflikt(self):
        reset_show()
        self._patch(1, address=1)
        self._patch(2, address=9)      # direkt dahinter, kein Ueberlapp
        self.assertEqual(find_conflict_pairs(self.st.get_patched_fixtures()), [])


class DialogInhaltTest(_Basis):
    def test_zeigt_beide_beteiligten_mit_bereich_und_gegner(self):
        z = {r["fid"]: r for r in self._dlg().rows()}
        self.assertEqual(sorted(z), [1, 2])
        self.assertEqual(z[1]["belegt"], "1–8 (8 Kan.)")
        self.assertEqual(z[1]["gegner"], "2")
        self.assertEqual(z[2]["gegner"], "1")

    def test_vorschlag_kommt_aus_suggest_address(self):
        """Kein zweiter Algorithmus: derselbe Vorschlag wie im Patch-Dialog."""
        z = {r["fid"]: r for r in self._dlg().rows()}
        self.assertEqual(z[2]["vorschlag"],
                         self.st.suggest_address(1, 8, exclude_fid=2))

    def test_ohne_konflikt_ist_die_liste_leer(self):
        reset_show()
        self._patch(1, address=1)
        self.assertEqual(self._dlg().rows(), [])


class VerschiebenTest(_Basis):
    def test_verschieben_loest_den_konflikt(self):
        d = self._dlg()
        self.assertTrue(d.verschiebe_fid(2))
        self.assertEqual(find_conflict_pairs(self.st.get_patched_fixtures()), [])

    def test_alle_verschieben_raeumt_die_liste(self):
        """★ Nach jedem Umzug wird neu gerechnet — ein Stapel vorab berechneter
        Vorschläge würde sich gegenseitig die Kanäle wegnehmen."""
        self._patch(3, address=3)      # dritter Ueberlapper
        d = self._dlg()
        d._alle_verschieben()
        self.assertEqual(find_conflict_pairs(self.st.get_patched_fixtures()), [],
                         "nach dem Durchlauf darf kein Paar mehr uebrig sein")
        self.assertEqual(d.rows(), [])

    def test_kein_platz_verschiebt_nichts(self):
        """Ein volles Universe darf nicht in einer halben Aktion enden."""
        reset_show()
        self._patch(1, address=1, channel_count=500)
        self._patch(2, address=100, channel_count=500)
        d = self._dlg()
        vorher = {f.fid: f.address for f in self.st.get_patched_fixtures()}
        self.assertFalse(d.verschiebe_fid(2))
        nachher = {f.fid: f.address for f in self.st.get_patched_fixtures()}
        self.assertEqual(vorher, nachher)

    def test_verschieben_ist_rueckgaengig_machbar(self):
        """`update_fixture` laeuft undoable — sonst waere der Dialog eine
        Einbahnstrasse."""
        from src.core.undo import get_undo_stack
        d = self._dlg()
        d.verschiebe_fid(2)
        self.assertTrue(get_undo_stack().undo())
        adr = {f.fid: f.address for f in self.st.get_patched_fixtures()}
        self.assertEqual(adr[2], 5, "Undo muss die alte Adresse zurueckholen")


if __name__ == "__main__":
    unittest.main()
