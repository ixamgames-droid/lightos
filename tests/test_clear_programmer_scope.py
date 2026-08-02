"""BUG-CLEAR — „Programmer leeren hat manchmal nicht alles geleert".

Davids Meldung aus dem Betrieb (2026-08-01). Das *manchmal* war keine Laune und
kein Race: der Knopf „Löschen" im Programmer-Tab hat **zwei Reichweiten**.
``ProgrammerView._clear_programmer`` verzweigt auf ``_selected_fids`` — ohne
Auswahl leert er alles, mit Auswahl nur diese Geräte. Sein Hilfetext versprach
dagegen „alle hier manuell gesetzten Werte", und im Programmer ist fast immer
etwas gewählt, weil man die Auswahl zum Einstellen braucht.

Die Tests messen deshalb ZWEI Dinge getrennt:

* **die Reichweite selbst** — was nach dem Druck noch scharf ist (Bestand, wird
  hier festgenagelt, nicht geändert);
* **was der Knopf darüber SAGT** — Beschriftung und Hilfetext müssen der
  Reichweite folgen. Genau daran hing Davids Fehleindruck, und genau das kann
  ein Test prüfen, den ein Blick auf den Code nicht ersetzt (Fallenklasse 12:
  sichtbarer Zustand ≠ Logikzustand).

Dazu die Gegenprobe für den globalen Weg: er muss wirklich ALLES erwischen —
auch Werte pro Kopf (``attr#N``) und die über Web/OSC gesetzten Roh-Kanäle.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import (FixtureProfile,               # noqa: E402
                                      PatchedFixture)
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.views.programmer_view import ProgrammerView             # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    """Profil-ID ueber den KURZnamen (nie ueber den Anzeigenamen — der haengt an
    der lokalen Library, Fallenklasse QA-23)."""
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Basis(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        for fid, addr in ((1, 1), (2, 20), (3, 40)):
            self.state.add_fixture(PatchedFixture(
                fid=fid, label=f"MH{fid}", fixture_profile_id=_pid("MH16"),
                mode_name="16-Kanal", universe=1, address=addr,
                channel_count=16, fixture_type="moving_head"), undoable=False)
        # Mehrkopf-Geraet fuer die attr#N-Faelle: die HYDRABEAM aus Davids Rig
        # hat vier Bewegungskoepfe (Builtin, damit der Test nicht an einer lokal
        # importierten Library haengt).
        self.state.add_fixture(PatchedFixture(
            fid=4, label="Hydra", fixture_profile_id=_pid("HYDRA4000"),
            mode_name="19-Kanal", universe=1, address=100,
            channel_count=19, fixture_type="moving_head"), undoable=False)
        self.addCleanup(self.state.clear_programmer)

    def _view(self) -> ProgrammerView:
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        return v

    def _werte_setzen(self):
        for fid in (1, 2, 3):
            self.state.set_programmer_value(fid, "intensity", 200)

    def _programmer(self):
        return {fid: dict(attrs) for fid, attrs in self.state.programmer.items()}


class ReichweiteTest(_Basis):
    """Was der Knopf TUT — Bestandsverhalten, hier festgenagelt."""

    def test_mit_auswahl_bleiben_die_uebrigen_geraete_scharf(self):
        """Davids Fall: das *manchmal* ist die Auswahl."""
        v = self._view()
        self._werte_setzen()
        v._selected_fids = [1]
        v._clear_programmer()

        self.assertEqual(sorted(self._programmer()), [2, 3],
                         "mit Auswahl leert der Knopf NUR die gewählten Geräte")

    def test_ohne_auswahl_ist_der_programmer_wirklich_leer(self):
        v = self._view()
        self._werte_setzen()
        v._selected_fids = []
        v._clear_programmer()

        self.assertEqual(self._programmer(), {})

    def test_gewaehlter_kopf_leert_trotzdem_das_ganze_geraet(self):
        """Entscheidung auf Protokoll: die Kopf-Zeile ist eine Verfeinerung der
        GERAETE-Auswahl. Beim Aufräumen ist „mehr" die sichere Richtung — ein
        halb geleertes Gerät wäre genau die Sorte Rest, um die es hier geht."""
        v = self._view()
        self.state.set_programmer_value(4, "intensity", 200)
        self.state.set_programmer_value(4, "intensity", 90, head=1)
        self.assertGreaterEqual(len(self._programmer().get(4, {})), 2,
                                "Vorbedingung: Gerät hat Werte auf zwei Schlüsseln")

        v._selected_fids = [4]
        v._selected_cells = ["4:1"]        # nur Kopf 2 in der Liste markiert
        v._clear_programmer()

        self.assertNotIn(4, self._programmer(),
                         "kein Kopf darf scharf zurueckbleiben")


class BeschriftungTest(_Basis):
    """Was der Knopf SAGT — das war der eigentliche Fehler."""

    def test_zuordnung_ist_ohne_view_pruefbar(self):
        text_ohne, hilfe_ohne = ProgrammerView._clear_button_labels(0)
        text_mit, hilfe_mit = ProgrammerView._clear_button_labels(3)

        self.assertEqual(text_ohne, "Alles löschen")
        self.assertIn("Auswahl", text_mit)
        self.assertIn("3", text_mit, "die Anzahl gehört sichtbar auf den Knopf")
        self.assertIn("übrigen bleiben", hilfe_mit,
                      "der Hilfetext muss sagen, was NICHT geleert wird")
        self.assertNotEqual(hilfe_ohne, hilfe_mit)

    def test_knopf_folgt_der_eigenen_auswahl(self):
        v = self._view()
        self.assertEqual(v._btn_clear.text(), "Alles löschen",
                         "frisch gebaut ist nichts gewählt")

        v._selected_fids = [1, 2]
        v._rebuild_attr_editor()
        self.assertEqual(v._btn_clear.text(), "Auswahl löschen (2)")

        v._selected_fids = []
        v._rebuild_attr_editor()
        self.assertEqual(v._btn_clear.text(), "Alles löschen",
                         "Auswahl aufgehoben -> wieder die volle Reichweite")

    def test_knopf_folgt_auch_einer_FREMDEN_auswahl(self):
        """Die Auswahl kommt oft von aussen (Gruppe im Preset-Browser, VC-Taste
        „Gruppe auswählen", Kommandozeile) — dieser Weg laeuft nicht durch die
        eigene Liste, sondern ueber SELECTION_CHANGED."""
        v = self._view()
        self.state.set_selected_fids([2, 3])
        v._sync_follow_selection()

        self.assertEqual(v._btn_clear.text(), "Auswahl löschen (2)")

    def test_hilfetext_und_beschriftung_bleiben_synchron(self):
        """Sonst steht die alte Reichweite im Hilfe-Modus (U-3), waehrend der
        Knopf schon die neue traegt — die schlechtere Haelfte des Fehlers."""
        v = self._view()
        v._selected_fids = [1]
        v._rebuild_attr_editor()

        self.assertIn("1", v._btn_clear.text())
        self.assertEqual(v._btn_clear.whatsThis(), v._btn_clear.toolTip())
        self.assertIn("übrigen bleiben", v._btn_clear.whatsThis())


class GlobalerWegTest(_Basis):
    """Die Gegenprobe: der globale Weg muss wirklich alles erwischen."""

    def test_global_erwischt_auch_werte_pro_kopf(self):
        self.state.set_programmer_value(4, "intensity", 200)
        self.state.set_programmer_value(4, "intensity", 90, head=1)
        self.state.set_programmer_value(4, "pan", 40, head=2)

        self.state.clear_programmer()

        self.assertEqual(self._programmer(), {},
                         "attr#N-Schluessel duerfen nicht ueberleben")

    def test_global_gibt_auch_web_osc_rohkanaele_frei(self):
        """WEB-01: ueber Web/OSC gesetzte Einzelkanaele liegen NICHT im
        Programmer, sondern in der Input-Schicht — fuer David sind sie trotzdem
        „was ich gesetzt habe"."""
        self.state.set_input_channel(1, 400, 222)
        self.assertTrue(self.state.input_layer.get(1),
                        "Vorbedingung: der Rohkanal steht in der Input-Schicht")

        self.state.clear_programmer()

        self.assertFalse(self.state.input_layer.get(1),
                         "der globale Clear ist der Release-Pfad (WEB-01)")

    def test_auswahlweiser_clear_laesst_rohkanaele_stehen(self):
        """Bestand, bewusst und hier festgehalten: Roh-Kanaele sind nicht
        fid-basiert, ein Geraete-Clear kann sie gar nicht zuordnen. Seit der
        Knopf „Auswahl löschen" heisst, verspricht er sie auch nicht mehr."""
        self.state.set_input_channel(1, 401, 111)
        self.state.clear_programmer(1)

        self.assertEqual(self.state.input_layer.get(1, {}).get(401), 111)


if __name__ == "__main__":
    unittest.main()
