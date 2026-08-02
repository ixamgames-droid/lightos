"""BUG-FBW — „Alles Weiß macht nicht alles weiß" (David 2026-08-01).

Der Knopf ``ButtonAction.ALL_WHITE`` setzt nichts selbst; er startet die an ihn
GEBUNDENE Weiss-Szene — „die Szene weiss das, nicht der Button" steht so im
Code. Daraus folgen zwei Arten, still zu wenig zu tun:

1. **gar keine Bindung** → der Druck macht nichts, ohne jede Rueckmeldung. Das
   ist die schlimmste Variante, weil der Knopf einsinkt und aufleuchtet wie
   jeder andere: er meldet Erfolg.
2. **eine Weiss-Szene aus einer Zeit mit weniger Geraeten** → die spaeter
   dazugepatchten bleiben dunkel. Am Rig sieht das identisch aus.

Geaendert wird das VERHALTEN nicht (ob „Alles Weiß" alle gepatchten Geraete
setzen soll, ist eine Produktentscheidung und steht weiter im Backlog) — der
Knopf sagt jetzt nur, was er abdeckt. Die Tests trennen deshalb:

* **die Rechnung** (``core.engine.function_coverage``) — inklusive der Faelle,
  in denen sie sich ehrlich fuer „weiss ich nicht" entscheiden muss;
* **die Anzeige** (``VCButton._coverage_hint``) — was am Knopf steht.
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
from src.core.engine.function_coverage import (coverage_of_bindings,  # noqa: E402
                                               covered_fixture_ids)
from src.core.engine.scene import Scene                             # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.virtualconsole.vc_button import (ButtonAction,          # noqa: E402
                                             VCButton)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Sammlung:
    """Minimal-Sammlung — deckt die ``function_ids``-Form ab."""
    def __init__(self, ids):
        self.function_ids = list(ids)


class _Schritt:
    def __init__(self, fid):
        self.function_id = fid


class _Chaser:
    def __init__(self, ids):
        self.steps = [_Schritt(i) for i in ids]


class _Matrix:
    """Ein Effekt, dessen Ziele erst zur Laufzeit entstehen — nicht bestimmbar."""


class RechnungTest(unittest.TestCase):
    """Die Abdeckungs-Rechnung, ohne Qt und ohne AppState."""

    def _szene(self, fids, sid=1) -> Scene:
        sc = Scene("weiss", sid)
        for fid in fids:
            sc.set_value(fid, 1, 255)
        return sc

    def test_szene_nennt_ihre_geraete(self):
        self.assertEqual(covered_fixture_ids(self._szene([3, 7, 3]), lambda _: None),
                         {3, 7})

    def test_leere_szene_deckt_nichts_ab_ist_aber_bestimmbar(self):
        """Wichtige Unterscheidung: leere Menge ≠ ``None``. Eine leere Szene ist
        eine sichere Aussage („deckt nichts ab"), kein Unwissen."""
        self.assertEqual(covered_fixture_ids(self._szene([]), lambda _: None), set())

    def test_sammlung_vereinigt_ihre_mitglieder(self):
        katalog = {1: self._szene([1, 2], 1), 2: self._szene([2, 5], 2)}
        self.assertEqual(
            covered_fixture_ids(_Sammlung([1, 2]), katalog.get), {1, 2, 5})

    def test_chaser_vereinigt_seine_schritte(self):
        katalog = {1: self._szene([4], 1), 2: self._szene([9], 2)}
        self.assertEqual(covered_fixture_ids(_Chaser([1, 2]), katalog.get), {4, 9})

    def test_unbekannter_typ_ist_None_und_nicht_leer(self):
        """Die Regel, an der alles haengt: im Zweifel ``None``. „Leer" wuerde als
        „deckt nichts ab" gelesen und eine falsche Warnung erzeugen."""
        self.assertIsNone(covered_fixture_ids(_Matrix(), lambda _: None))

    def test_ein_unbekanntes_mitglied_macht_die_ganze_sammlung_unbestimmbar(self):
        katalog = {1: self._szene([1], 1), 2: _Matrix()}
        self.assertIsNone(covered_fixture_ids(_Sammlung([1, 2]), katalog.get))

    def test_zyklus_haengt_sich_nicht_auf(self):
        """Sammlung A enthaelt B enthaelt A — ohne Tiefenbegrenzung endlos."""
        katalog = {}
        katalog[1] = _Sammlung([2])
        katalog[2] = _Sammlung([1])
        self.assertIsNone(covered_fixture_ids(katalog[1], katalog.get))

    def test_ohne_bindung_ist_die_abdeckung_leer_nicht_unbekannt(self):
        """Daran haengt „nicht belegt": keine Bindung ist eine sichere Aussage."""
        self.assertEqual(coverage_of_bindings([], lambda _: None), set())


class AnzeigeTest(unittest.TestCase):
    """Was am Knopf steht."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        for fid, addr in ((1, 1), (2, 20), (3, 40), (4, 60)):
            self.state.add_fixture(PatchedFixture(
                fid=fid, label=f"PAR{fid}", fixture_profile_id=_pid("MH16"),
                mode_name="16-Kanal", universe=1, address=addr,
                channel_count=16, fixture_type="moving_head"), undoable=False)
        self._szenen: list[int] = []

    def tearDown(self):
        fm = self.state.function_manager
        for sid in self._szenen:
            try:
                fm.remove(sid)
            except Exception:
                pass

    def _weiss_szene(self, fids) -> int:
        fm = self.state.function_manager
        sc = Scene("Alles Weiss")
        for fid in fids:
            sc.set_value(fid, 1, 255)
        fm.add(sc)
        self._szenen.append(sc.id)
        return sc.id

    def _knopf(self, function_id=None) -> VCButton:
        b = VCButton()
        self.addCleanup(b.deleteLater)
        b.action = ButtonAction.ALL_WHITE
        if function_id is not None:
            b.function_id = function_id
        return b

    def test_ohne_bindung_sagt_der_knopf_dass_er_nichts_tut(self):
        """Genau der Fall, der bisher als Erfolg durchging."""
        self.assertEqual(self._knopf()._coverage_hint(), "⚠ nicht belegt")

    def test_unvollstaendige_szene_nennt_das_verhaeltnis(self):
        """Davids wahrscheinlicherer Fall: die Weiss-Szene ist aelter als das Rig."""
        sid = self._weiss_szene([1, 2])          # 2 von 4 gepatchten
        self.assertEqual(self._knopf(sid)._coverage_hint(), "⚠ 2/4 Geräte")

    def test_vollstaendige_szene_bekommt_keinen_hinweis(self):
        """Kein Daueralarm: deckt sie alles ab, ist nichts zu melden."""
        sid = self._weiss_szene([1, 2, 3, 4])
        self.assertIsNone(self._knopf(sid)._coverage_hint())

    def test_neu_gepatchtes_geraet_taucht_im_hinweis_sofort_auf(self):
        """Der eigentliche Auftrag: die Szene veraltet, wenn das Rig waechst.

        Zugleich die Gegenprobe gegen einen Cache — genau daran waere ein
        privater Paint-Cache still veraltet (Lehre FM-16b-Preview).
        """
        sid = self._weiss_szene([1, 2, 3, 4])
        knopf = self._knopf(sid)
        self.assertIsNone(knopf._coverage_hint())

        self.state.add_fixture(PatchedFixture(
            fid=5, label="Neu", fixture_profile_id=_pid("MH16"),
            mode_name="16-Kanal", universe=1, address=80,
            channel_count=16, fixture_type="moving_head"), undoable=False)

        self.assertEqual(knopf._coverage_hint(), "⚠ 4/5 Geräte",
                         "das neue Geraet fehlt der alten Weiss-Szene")

    def test_unbestimmbare_bindung_behauptet_nichts(self):
        """Ein Matrix-Effekt rechnet seine Ziele erst zur Laufzeit aus. Lieber
        kein Hinweis als eine erfundene Zahl."""
        fm = self.state.function_manager
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        m = RgbMatrixInstance("Matrix")
        fm.add(m)
        self._szenen.append(m.id)

        self.assertIsNone(self._knopf(m.id)._coverage_hint())

    def test_andere_aktionen_bekommen_den_hinweis_nicht(self):
        """Der Hinweis gehoert dem Panik-Knopf — ein gewoehnlicher Funktions-
        Taster ohne Bindung ist beim Bauen normal und darf nicht warnen."""
        b = VCButton()
        self.addCleanup(b.deleteLater)
        b.action = ButtonAction.FUNCTION_TOGGLE
        self.assertIsNone(b._coverage_hint())

    def test_hinweis_steht_wirklich_auf_der_taste(self):
        """Gegenprobe zur reinen Logik: der Text muss den Paint-Pfad erreichen —
        sonst ist die Warnung korrekt berechnet und trotzdem unsichtbar."""
        from PySide6.QtGui import QPixmap, QPainter
        knopf = self._knopf()
        knopf.caption = "Alles Weiß"
        knopf.resize(120, 80)
        pm = QPixmap(knopf.size())
        pm.fill()
        gemalt: list[str] = []
        echt = QPainter.drawText

        def _mit(self_p, *a, **kw):
            for arg in a:
                if isinstance(arg, str):
                    gemalt.append(arg)
            return echt(self_p, *a, **kw)

        QPainter.drawText = _mit
        try:
            knopf.render(pm)
        finally:
            QPainter.drawText = echt

        self.assertTrue(any("nicht belegt" in t for t in gemalt),
                        f"Warnung fehlt im gemalten Text: {gemalt}")


if __name__ == "__main__":
    unittest.main()
