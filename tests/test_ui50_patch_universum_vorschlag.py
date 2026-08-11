"""UI-50: Der Patch-Dialog schlaegt das Universum des zuletzt gepatchten
Geraets vor — nicht mehr stur Universum 1.

Vorher startete ``FixtureBrowserDialog._spin_universe`` jedes Mal auf 1, egal
wie die Show gepatcht war. Wer sein Rig auf Universum 3 faehrt, korrigierte das
Feld bei JEDEM neuen Geraet von Hand; wer es vergass, patchte auf ein Universum
ohne Ausgang und suchte den Fehler danach am Rig.

Diese Tests bauen den **echten Dialog gegen einen echten Patch** (kein Attrappen-
AppState): ``reset_show()`` + ``add_fixture`` wie die App, dann der Dialog. Der
Kern ist nicht die Zahl im Spinner, sondern was am Ende **gepatcht** wird —
deshalb geht ``DurchreichenTest`` bis ``result_fixture`` (ueber Suchfeld,
Baum-Auswahl und den echten „Hinzufuegen"-Knopf).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402
from sqlalchemy import select, text                            # noqa: E402
from sqlalchemy.orm import Session                             # noqa: E402

from src.core.app_state import get_state                       # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine  # noqa: E402
from src.core.database.models import (                         # noqa: E402
    PatchedFixture, FixtureProfile)
from src.core.show.show_file import reset_show                 # noqa: E402
from src.ui.widgets.fixture_browser import FixtureBrowserDialog  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Basis(unittest.TestCase):
    def setUp(self):
        reset_show()
        self.st = get_state()
        self.pid = _pid("ZQ01424")

    def _patch(self, fid, universe, address=1, channel_count=8):
        """Patcht wie die App: ueber AppState, mit aufsteigender fid."""
        self.st.add_fixture(PatchedFixture(
            fid=fid, label=f"PAR {fid}", fixture_profile_id=self.pid,
            mode_name="8-Kanal", universe=universe, address=address,
            channel_count=channel_count), undoable=False)

    def _dlg(self) -> FixtureBrowserDialog:
        d = FixtureBrowserDialog(self.st.next_fid())
        self.addCleanup(d.deleteLater)
        return d


class VorbelegungTest(_Basis):
    def test_erbt_universum_des_zuletzt_gepatchten_geraets(self):
        """Das eigentliche Item: Rig auf 3 -> der Dialog steht auf 3."""
        self._patch(1, universe=1)
        self._patch(2, universe=3)
        self.assertEqual(self._dlg()._spin_universe.value(), 3)

    def test_zuletzt_gepatcht_schlaegt_mehrheit_und_maximum(self):
        """Die Produktentscheidung, hart gemacht: zwei Geraete auf 8, das
        JUENGSTE auf 3. „Meiste Geraete" haette 8 vorgeschlagen, „hoechstes
        Universum" auch — der Anwender ist aber schon in 3."""
        self._patch(1, universe=8)
        self._patch(2, universe=8)
        self._patch(3, universe=3)
        self.assertEqual(self._dlg()._spin_universe.value(), 3)

    def test_zuletzt_gepatcht_schlaegt_minimum_und_erstes_geraet(self):
        """Gegenprobe zur Regel oben: das juengste Geraet liegt WEDER auf dem
        kleinsten noch auf dem groessten Universum."""
        self._patch(1, universe=2)
        self._patch(2, universe=5)
        self._patch(3, universe=4)
        self.assertEqual(self._dlg()._spin_universe.value(), 4)

    def test_reihenfolge_der_fids_entscheidet_nicht_die_der_zeilen(self):
        """„Zuletzt gepatcht" = groesste fid. Wird eine LUECKE nachtraeglich
        gefuellt (fid 2 zuletzt eingefuegt), bleibt fid 5 das juengste Geraet."""
        self._patch(1, universe=1)
        self._patch(5, universe=6)
        self._patch(2, universe=2)
        self.assertEqual(self._dlg()._spin_universe.value(), 6)


class PositivkontrolleTest(_Basis):
    """Ein Vorschlag, der immer etwas vorschlaegt, ist so unbrauchbar wie
    keiner: hier steht, wann er NICHT eingreift."""

    def test_leerer_patch_bleibt_bei_1(self):
        self.assertEqual(self.st.get_patched_fixtures(), [])
        self.assertEqual(self._dlg()._spin_universe.value(), 1)

    def test_rig_auf_universum_1_bleibt_bei_1(self):
        self._patch(1, universe=1)
        self._patch(2, universe=1)
        self.assertEqual(self._dlg()._spin_universe.value(), 1)

    def test_vorbelegung_ist_kein_schloss(self):
        """Der Vorschlag darf nur vorbelegen. Wer das Feld anfasst, patcht
        dorthin — sonst waere aus dem Komfort eine Sperre geworden."""
        self._patch(1, universe=3)
        dlg = self._dlg()
        self.assertEqual(dlg._spin_universe.value(), 3)
        dlg._spin_universe.setValue(7)
        self.assertEqual(_hinzufuegen(dlg).universe, 7)


class RobustheitTest(_Basis):
    def test_universum_ausserhalb_des_eingabebereichs_faellt_auf_1(self):
        """Von Hand editierte Show-Datei: 99 waere im Spinner still auf 32
        geklemmt worden — eine Zahl, die niemand gepatcht hat. Dann lieber die
        neutrale 1."""
        self._patch(1, universe=99)
        self.assertEqual(self._dlg()._spin_universe.value(), 1)

    def test_universum_null_faellt_auf_1(self):
        """Untere Grenze. Gemessen faengt dieser Test nur die Entscheidung
        „neutrale 1" gegen „an den Rand klemmen" ab — die 0 allein wuerde der
        Spinner ohnehin auf 1 hochziehen; die 99 oben nicht."""
        self._patch(1, universe=0)
        self.assertEqual(self._dlg()._spin_universe.value(), 1)

    def test_kaputter_universe_wert_haelt_den_dialog_nicht_auf(self):
        """Die Show-DB ist eine von Hand editierbare SQLite-Datei, und SQLite
        nimmt auch Text in einer Zahlenspalte an. Der Patch-Dialog ist das
        Werkzeug, mit dem man so etwas repariert — er darf daran nicht
        scheitern, sondern faellt auf 1 zurueck (Lehre aus OUT-50: dort machte
        genau so ein Wert den Ausgabe-Dialog unbenutzbar)."""
        self._patch(1, universe=3)
        with self.st._session() as s:
            s.execute(text(
                "UPDATE patched_fixtures SET universe='drei' WHERE fid=1"))
            s.commit()
        self.st._reload_patch_cache()
        self.assertEqual(self.st.get_patched_fixtures()[0].universe, "drei")
        self.assertEqual(self._dlg()._spin_universe.value(), 1)


class DurchreichenTest(_Basis):
    """Bis ans Ende: was der Dialog vorbelegt, muss auch gepatcht werden."""

    def test_vorbelegung_landet_im_neuen_geraet(self):
        self._patch(1, universe=3, address=1)
        neu = _hinzufuegen(self._dlg())
        self.assertEqual(neu.universe, 3)

    def test_adressvorschlag_folgt_dem_vorbelegten_universum(self):
        """Die Kopplung, die den Fehler frueher teuer machte: der
        Adressvorschlag rechnet gegen das Universum im Feld. Stand da eine 1,
        waehrend das Rig auf 3 laeuft, schlug er die 1 vor — belegt in 3."""
        self._patch(1, universe=3, address=1, channel_count=8)
        neu = _hinzufuegen(self._dlg())
        self.assertEqual((neu.universe, neu.address), (3, 9))


def _hinzufuegen(dlg: FixtureBrowserDialog) -> PatchedFixture:
    """Geht den echten Anwenderweg: suchen, Geraet im Baum waehlen,
    „Hinzufuegen" druecken. Liefert das erzeugte Fixture."""
    dlg._search.setText("ZQ01424")            # -> textChanged -> _load_tree
    item = dlg._tree.topLevelItem(0)
    assert item is not None, "Suchtreffer erwartet (Builtin ZQ01424)"
    dlg._tree.setCurrentItem(item)            # -> currentItemChanged
    assert dlg._btn_add.isEnabled(), "Hinzufuegen muss nach der Auswahl gehen"
    dlg._btn_add.click()
    assert dlg.result_fixture is not None
    return dlg.result_fixture


if __name__ == "__main__":
    unittest.main()
