"""FM-18 — „Kopf gewaehlt: Regler folgen der Auswahl“ war bei den meisten Reglern
eine leere Zusage, und am wichtigsten Geraet gab es die Kopf-Auswahl gar nicht.

Zwei Luecken, beide an der ``HYDRABEAM 4000 RGBW [19-Kanal]`` aus Davids Rig
gemessen (Builtin ``HYDRA4000``, damit der Test nicht an einer lokal
importierten Library haengt):

1. **Die Geraeteliste bot keine Kopf-Zeile an.** ``_head_row_count`` zaehlte nur
   FARBbaenke; die Hydrabeam hat vier Bewegungskoepfe, aber EINE gemeinsame
   RGBW-Bank -> null Kopf-Zeilen. Der FM-17-Fix („Kopf 2 dimmt Kopf 2“) war
   ueber diese Flaeche also gar nicht erreichbar. Ueber die Library sind das
   **108 Modi** (Bewegung >= 2, Farbe < 2).
2. **Der allgemeine Attribut-Regler ignorierte die Kopf-Auswahl.** Farb- und
   Tilt-Bloecke werden pro Kopf gebaut, der Rest (Dimmer, Strobe, Makro …)
   geraeteweit. Bis FM-17 fiel das nicht auf, weil „Kopf 1“ und „ganzes Geraet“
   denselben Schluessel trafen — seit der Kopf-Karte ist der Basis-Schluessel
   bei einem geteilten Master der MASTER.

Der Test misst beides am gebauten Tab, nicht an der Absicht.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import (get_channels_for_patched,           # noqa: E402
                                get_state)
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import (FixtureProfile,               # noqa: E402
                                      PatchedFixture)
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.views.programmer_view import (AttributeSlider,          # noqa: E402
                                          ProgrammerView)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    """Profil-ID ueber den KURZnamen eines Builtins (nie ueber den Anzeigenamen —
    der existiert je nach Rechner nur lokal, Fallenklasse QA-23)."""
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Basis(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Hydra1", fixture_profile_id=_pid("HYDRA4000"),
            mode_name="19-Kanal", universe=1, address=1, channel_count=19,
            fixture_type="moving_head"), undoable=False)

    def _fx(self, fid=1):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _view(self):
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        return v

    def _sliders(self, cells):
        """(attribut, kopf, fids) je Attribut-Regler des gebauten Tabs.

        Frische View je Messung — eine wiederverwendete View liefert per
        ``findChildren`` auch die Regler frueherer Auswahlen (Qt loescht sie
        erst spaeter)."""
        v = self._view()
        self.state.set_selected_cells(list(cells))
        _app().processEvents()
        return [(s._channel.attribute, s._head,
                 tuple(f.fid for f in s._fixtures))
                for s in v.findChildren(AttributeSlider)]


class KopfZeilenTest(_Basis):
    """Lueke 1: die Liste bot ueberhaupt keinen Kopf an."""

    def test_bewegungskoepfe_bekommen_kopf_zeilen(self):
        v = self._view()
        self.assertEqual(
            v._head_row_count(self._fx()), 4,
            "vier Pan/Tilt-Koepfe = vier Kopf-Zeilen, auch wenn sich alle EINE "
            "RGBW-Bank teilen")

    def test_als_eine_lampe_gefuehrt_bleibt_ohne_kopf_zeilen(self):
        """Die Patch-Dialog-Ansage „Als eine Lampe“ schlaegt die Zaehlung —
        sonst widerspraeche die Liste der Geraete-Einstellung."""
        fx = self._fx()
        fx.head_mode = "single"
        self.assertEqual(self._view()._head_row_count(fx), 0)

    def test_makro_modus_zaehlt_ueber_die_bewegungsachse(self):
        """Die 32-Kanal-Hydrabeam hat vier Pan/Tilt-Koepfe und KEINE eigenen
        Farbbaenke (Makro-Modus) — vorher also ebenfalls null Kopf-Zeilen."""
        self.state.add_fixture(PatchedFixture(
            fid=2, label="Hydra32", fixture_profile_id=_pid("HYDRA4000"),
            mode_name="32-Kanal", universe=1, address=100, channel_count=32,
            fixture_type="moving_head"), undoable=False)
        self.assertEqual(self._view()._head_row_count(self._fx(2)), 4)

    def test_einzelkopf_mover_bleibt_ohne_kopf_zeilen(self):
        """Der Bestandsfall: ein gewoehnlicher Moving Head (1 Pan, 1 Tilt) darf
        keine Kopf-Zeile bekommen — sonst waere die Liste bei JEDEM Mover
        ploetzlich zweistoeckig."""
        self.state.add_fixture(PatchedFixture(
            fid=3, label="MH1", fixture_profile_id=_pid("MH16"),
            mode_name="16-Kanal", universe=1, address=200, channel_count=16,
            fixture_type="moving_head"), undoable=False)
        self.assertEqual(self._view()._head_row_count(self._fx(3)), 0)

    def test_einzelner_par_bleibt_ohne_kopf_zeilen(self):
        self.state.add_fixture(PatchedFixture(
            fid=4, label="Par1", fixture_profile_id=_pid("PARW"),
            mode_name="4-Kanal RGBW", universe=1, address=300, channel_count=4),
            undoable=False)
        self.assertEqual(self._view()._head_row_count(self._fx(4)), 0)


class ReglerFolgenDerAuswahlTest(_Basis):
    """Luecke 2: der allgemeine Regler blieb geraeteweit."""

    def _intensity(self, cells):
        return [(kopf, fids) for attr, kopf, fids in self._sliders(cells)
                if attr == "intensity"]

    def test_ohne_kopf_auswahl_bleibt_alles_geraeteweit(self):
        """Der Bestandsfall MUSS unveraendert bleiben: keine Kopf-Auswahl ->
        ausschliesslich geraeteweite Regler (``head=None``)."""
        koepfe = {kopf for kopf, _f in self._intensity(["1"])}
        self.assertEqual(koepfe, {None},
                         "ohne Kopf-Auswahl darf kein Kopf-Regler entstehen")

    def test_kopf_auswahl_bindet_den_dimmer_regler_an_den_kopf(self):
        heads = [kopf for kopf, _f in self._intensity(["1:1"])]
        self.assertIn(1, heads,
                      "„Kopf 2“ gewaehlt -> der Dimmer-Regler muss auf Kopf 2 "
                      "schreiben, nicht auf den geteilten Master")
        self.assertNotIn(None, heads,
                         "ein geraeteweiter Regler daneben wuerde die Ansage "
                         "wieder aufheben")

    def test_der_regler_schreibt_wirklich_auf_den_kanal_des_kopfes(self):
        """Der Beweis am DMX-Kanal — ein Regler, der nur so HEISST, hilft nicht."""
        v = self._view()
        self.state.set_selected_cells(["1:1"])
        _app().processEvents()
        regler = [s for s in v.findChildren(AttributeSlider)
                  if s._channel.attribute == "intensity" and s._head == 1]
        self.assertTrue(regler, "kein Kopf-Dimmer-Regler gebaut")
        regler[0]._apply_value(1, 128)
        fx = self._fx()
        kanal = {c.name: c.channel_number
                 for c in get_channels_for_patched(fx)}
        uni = self.state.universes[fx.universe]

        def dmx(name):
            return uni.get_channel(fx.address + kanal[name] - 1)

        self.assertEqual(dmx("Kopf 2 Dimmer"), 128)
        self.assertEqual(dmx("Master Dimmer"), 128,
                         "der geteilte Master kommt ueber FM-17 mit")
        self.assertEqual(dmx("Kopf 1 Dimmer"), 0)
        self.assertEqual(dmx("Kopf 3 Dimmer"), 0)

    def test_kopf_1_zieht_die_anderen_koepfe_nicht_mit(self):
        """★ Der Fall, der einen Regler zum Luegner gemacht haette.

        Die 56-Kanal-Hydrabeam hat je Kopf ein Strobe und KEINEN gemeinsamen
        Master — „Kopf 1" adressiert dort den Basis-Schluessel ``shutter``, und
        der DMX-Flush spiegelt einen gesetzten Basis-Wert auf jeden Kopf, der
        nichts Eigenes hat. Gemessen vor dem Fix: Kopf 1 + Strobe traf ALLE VIER
        Koepfe, Kopf 2 nur seinen eigenen."""
        self.state.add_fixture(PatchedFixture(
            fid=5, label="Hydra56", fixture_profile_id=_pid("HYDRA4000"),
            mode_name="56-Kanal", universe=1, address=400, channel_count=56,
            fixture_type="moving_head"), undoable=False)
        v = self._view()
        self.state.set_selected_cells(["5:0"])
        _app().processEvents()
        regler = [s for s in v.findChildren(AttributeSlider)
                  if s._channel.attribute == "shutter" and s._head == 0
                  and 5 in [f.fid for f in s._fixtures]]
        self.assertTrue(regler, "kein Kopf-1-Strobe-Regler gebaut")
        regler[0]._apply_value(5, 200)

        fx = self._fx(5)
        uni = self.state.universes[fx.universe]
        strobes = [c for c in get_channels_for_patched(fx)
                   if (c.attribute or "") == "shutter"]
        werte = [uni.get_channel(fx.address + c.channel_number - 1)
                 for c in strobes]
        self.assertEqual(werte[0], 200, "Kopf 1 muss den Wert bekommen")
        self.assertNotIn(200, werte[1:],
                         "die anderen Koepfe duerfen NICHT mitgezogen werden — "
                         f"gemessen: {werte}")

    def test_geteilte_farbe_verliert_ihren_regler_nicht(self):
        """Die Hydrabeam hat EINE RGBW-Bank fuer alle Koepfe. „Kopf 2“ gewaehlt
        darf den Farbregler nicht verschwinden lassen — er bleibt geraeteweit,
        weil es den Kopf fuer dieses Attribut gar nicht gibt."""
        rot = [(kopf, fids) for attr, kopf, fids in self._sliders(["1:1"])
               if attr == "color_r"]
        self.assertTrue(rot, "der Farbregler ist ganz verschwunden")
        self.assertEqual({kopf for kopf, _f in rot}, {None})


if __name__ == "__main__":
    unittest.main()
