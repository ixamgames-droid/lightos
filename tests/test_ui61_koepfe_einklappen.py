"""UI-61 — die Kopf-Zeilen im Programmer sind einklappbar.

Vom Rig gemeldet (03.09.2026): „dann sitzt die Liste sehr, sehr schnell sehr
unuebersichtlich". Gemessen baute ``ProgrammerView._refresh_fixture_list`` eine
**flache** Liste — je Geraet eine Zeile, darunter je Kopf eine weitere. Beim
ZQ06121 sind das **49 Zeilen fuer EIN Geraet**, beim Pixel Panel 144 waeren es
145.

Jetzt ist es ein Baum: die Kopf-Zeilen sind **Kinder** ihres Geraets,
voreingestellt **zugeklappt**. Wer die Koepfe einzeln braucht, klappt auf.

★ Was diese Datei besonders festhaelt, weil es die teuren Stellen sind:

1. **Auswahl und Sichtbarkeit sind zwei Dinge.** Eine markierte Kopf-Zeile
   zaehlt auch dann, wenn ihr Geraet zugeklappt ist — sonst verlaere ein
   Zuklappen still die Auswahl.
2. **Der Klappzustand ueberlebt den Neuaufbau.** ``_refresh_fixture_list``
   laeuft bei jeder Patch-Aenderung; ohne Merker klappt jede Adressaenderung
   alles wieder zu.
3. **„Alle" haengt nicht an den Pfeilen.** Was „alle Geraete" bedeutet, darf
   nicht davon abhaengen, wie der Nutzer seine Klapp-Zustaende stehen hat.
4. **Der Zellschluessel bleibt unveraendert** (``"fid"`` / ``"fid:head"``,
   FM-HEADLAYOUT Slice 5) — er wird ueber ``parse_group_cell`` gelesen, und
   ``int(v)`` wirft dort. Ein Baum-Umbau darf ihn nicht anfassen.
"""
from __future__ import annotations
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.ui.views.programmer_view import ProgrammerView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Basis(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        # Ein Mehrkopf-Geraet (Kopf-Zeilen) und ein Einzelkopf-PAR (keine).
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=20, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        self.view = ProgrammerView()
        self.addCleanup(self.view.deleteLater)

    # ── Helfer: bewusst ueber den Helfer der VIEW, nicht ueber einen eigenen ──
    def _zellen(self):
        return [it.data(0, Qt.ItemDataRole.UserRole)
                for it in self.view._alle_items()]

    def _geraet(self, fid: int):
        wurzel = self.view._fixture_list.invisibleRootItem()
        for i in range(wurzel.childCount()):
            it = wurzel.child(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == str(fid):
                return it
        raise AssertionError(f"Geraete-Zeile fuer fid {fid} fehlt")


class BaumAufbauTest(_Basis):

    def test_koepfe_sind_kinder_ihres_geraets(self):
        """Der Kern: vorher Geschwister in einer flachen Liste, jetzt Kinder."""
        spider = self._geraet(1)
        self.assertGreaterEqual(spider.childCount(), 2,
                                "das Mehrkopf-Geraet hat keine Kopf-Kinder")
        kinder = [spider.child(i).data(0, Qt.ItemDataRole.UserRole)
                  for i in range(spider.childCount())]
        self.assertEqual(kinder[0], "1:0")
        self.assertTrue(all(c.startswith("1:") for c in kinder))

    def test_zellschluessel_unveraendert(self):
        """FM-HEADLAYOUT Slice 5: der Baum-Umbau darf die Syntax nicht anfassen —
        `parse_group_cell` liest sie, und `int(v)` wirft bei „1:0"."""
        zellen = self._zellen()
        self.assertIn("1", zellen)
        self.assertIn("1:0", zellen)
        self.assertIn("2", zellen)

    def test_einzelkopf_geraet_hat_keine_kinder(self):
        """Positivkontrolle: ein PAR bekommt keinen Pfeil und keinen Zusatz."""
        par = self._geraet(2)
        self.assertEqual(par.childCount(), 0)
        self.assertNotIn("Köpfe", par.text(0))

    def test_geraetezeile_nennt_die_kopfzahl(self):
        """Zugeklappt ist sonst nicht zu sehen, DASS es Koepfe gibt — und ein
        Pfeil allein sagt nicht, wie viele dahinter liegen."""
        spider = self._geraet(1)
        self.assertIn(f"({spider.childCount()} Köpfe)", spider.text(0))

    def test_voreinstellung_ist_zugeklappt(self):
        self.assertFalse(self._geraet(1).isExpanded(),
                         "die Koepfe stehen offen — genau die Unuebersichtlichkeit")


class KlappzustandTest(_Basis):

    def test_klappzustand_ueberlebt_den_neuaufbau(self):
        """`_refresh_fixture_list` laeuft bei JEDER Patch-Aenderung. Ohne Merker
        klappt eine Adressaenderung dem Nutzer alles wieder zu."""
        self._geraet(1).setExpanded(True)
        self.view._refresh_fixture_list()
        self.assertTrue(self._geraet(1).isExpanded())

    def test_zuklappen_wird_auch_gemerkt(self):
        """Die Gegenrichtung — sonst laesst sich ein einmal geoeffnetes Geraet
        nicht mehr dauerhaft schliessen."""
        self._geraet(1).setExpanded(True)
        self._geraet(1).setExpanded(False)
        self.view._refresh_fixture_list()
        self.assertFalse(self._geraet(1).isExpanded())

    def test_der_merker_haengt_am_fid_nicht_an_der_zeile(self):
        """Nach einem Neuaufbau steht das Geraet womoeglich woanders; ein Index
        waere dann der falsche Knoten."""
        self._geraet(1).setExpanded(True)
        self.assertIn(1, self.view._offene_koepfe)
        self.assertNotIn(2, self.view._offene_koepfe)


class AuswahlUndSichtbarkeitTest(_Basis):

    def test_kopf_auswahl_ueberlebt_das_zuklappen(self):
        """★ Auswahl und Sichtbarkeit sind zwei Dinge. Ein zugeklapptes Geraet
        darf seine Kopf-Auswahl nicht still verlieren."""
        self._geraet(1).setExpanded(True)
        kopf = self._geraet(1).child(1)
        kopf.setSelected(True)
        self.view._on_fixture_selected()
        self.assertIn("1:1", self.view._selected_cells)
        self._geraet(1).setExpanded(False)
        self.assertIn("1:1", {it.data(0, Qt.ItemDataRole.UserRole)
                              for it in self.view._alle_items() if it.isSelected()})

    def test_externe_kopf_auswahl_klappt_auf(self):
        """Sonst steht die Auswahl unsichtbar hinter einem zugeklappten Pfeil —
        der Nutzer sieht Regler fuer einen Kopf, den er nirgends markiert sieht."""
        self.assertFalse(self._geraet(1).isExpanded())
        self.state.set_selected_cells(["1:0"])
        self.view._sync_follow_selection()
        self.assertTrue(self._geraet(1).isExpanded(),
                        "die getroffene Kopf-Zeile blieb hinter dem Pfeil verborgen")

    def test_alle_haengt_nicht_an_den_pfeilen(self):
        """Was „Alle" bedeutet, darf nicht davon abhaengen, wie der Nutzer seine
        Klapp-Zustaende stehen hat — deshalb bewusst kein `selectAll()`."""
        self.assertFalse(self._geraet(1).isExpanded())
        self.view._select_all()
        gewaehlt = {it.data(0, Qt.ItemDataRole.UserRole)
                    for it in self.view._alle_items() if it.isSelected()}
        self.assertIn("1", gewaehlt)
        self.assertIn("2", gewaehlt)
        self.assertIn("1:0", gewaehlt,
                      'eine zugeklappte Kopf-Zeile fiel aus „Alle“ heraus')

    def test_geraete_auswahl_markiert_keine_kopfzeilen(self):
        """Bestandsvertrag (FM16E-Fehlerklasse): eine fid-Auswahl meint IMMER das
        ganze Geraet und darf keine Kopf-Zeilen mitmarkieren."""
        self.view._select_fids([1])
        gewaehlt = {it.data(0, Qt.ItemDataRole.UserRole)
                    for it in self.view._alle_items() if it.isSelected()}
        self.assertEqual(gewaehlt, {"1"})


if __name__ == "__main__":
    unittest.main()
