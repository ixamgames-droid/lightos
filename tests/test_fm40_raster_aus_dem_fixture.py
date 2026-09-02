"""FM-40 — die im Fixture hinterlegte Rasterform als Vorgabe im Gruppen-Editor.

Vom Rig gemeldet (02.09.2026): wer ein Panel oder eine Mehrkopf-Leiste patcht
und die Koepfe unter *Patchen → Fixture-Gruppen* raeumlich anordnen will,
bekommt sie immer als EINE Reihe und stellt Spalten/Zeilen jedes Mal von Hand
nach. Dabei ist die Form laengst gespeichert: VIZ-50a legt sie als
``FixtureMode.grid_rows/grid_cols`` ab und ``panel_grid_for`` liest sie — nur
der Gruppen-Editor hat sie nie gefragt.

Festgenagelt wird hier:

1. **Die Form wird nur angeboten, wenn sie zur Kopfzahl passt.** Ein Panel als
   falsches Rechteck abzulegen sieht richtig aus und ist es nicht — dann ist die
   bisherige Rueckfrage ehrlicher als ein stiller Fehlgriff.
2. **Der Vorschlag im Dialog kommt aus dem Geraet, nicht aus der Wurzel.** Der
   geratene Teiler lag beim ZQ06121 (48 Zonen) bei 6 oder 8 — das Geraet hat
   12 Spalten. Er war nicht nur unbequem, er war zuverlaessig falsch.
3. **Ohne hinterlegte Form bleibt alles wie bisher** — der alte Vorschlag, die
   alte Frage. Bestandsverhalten ist Bestandsverhalten.
4. **Das Menue sagt, was passieren wird:** „wie im Geraet hinterlegt (4×12)",
   und ist ausgegraut, wenn es fuer das Geraet nichts zu tun gibt.
5. **Die Daten der realen Panels passen.** Fuer jedes Builtin-Panel mit
   Rasterform gilt zeilen*spalten == Kopfzahl — sonst wuerde die Vorgabe dort
   nie greifen, und der Fix waere am Rig unsichtbar.
"""
import os
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSpinBox
from PySide6.QtGui import QAction

import pytest as _pytest_xplat15                          # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets   # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


def _stub_view(**attrs):
    """Stellvertreter fuer ``FixtureGroupView`` — die FM-40-Methoden werden an
    die ECHTE Klasse gebunden (kein Nachbau), der Rest ist stubbar."""
    from src.ui.views.fixture_group_view import FixtureGroupView as V
    s = SimpleNamespace(**attrs)
    for name in ("_hinterlegte_form", "_ask_block_cols", "_heads_menu_aktualisieren",
                 "_block_platzieren", "_grow_grid_for_block"):
        setattr(s, name, types.MethodType(getattr(V, name), s))
    return s


_FX = SimpleNamespace(fid=7, label="Balken", element_rotation=0,
                      element_flip=False, pixel_order="rowwise")


# ── 1) Die Form wird nur angeboten, wenn sie passt ──────────────────────────

class HinterlegteFormTest(unittest.TestCase):

    def _form(self, gespeichert, n):
        v = _stub_view()
        with patch("src.core.app_state.panel_grid_for", return_value=gespeichert):
            return v._hinterlegte_form(_FX, n)

    def test_passende_form_wird_angeboten(self):
        self.assertEqual(self._form((4, 12), 48), (4, 12))

    def test_ohne_kopfzahl_wird_nicht_gegengeprueft(self):
        v = _stub_view()
        with patch("src.core.app_state.panel_grid_for", return_value=(4, 12)):
            self.assertEqual(v._hinterlegte_form(_FX), (4, 12))

    def test_nichts_hinterlegt_heisst_none(self):
        self.assertIsNone(self._form((0, 0), 48))

    def test_form_passt_nicht_zur_kopfzahl_heisst_none(self):
        """Der gefaehrlichere Fall: 4x12 ist hinterlegt, das Geraet hat aber 40
        Koepfe (anderer Modus). Lieber die alte Frage als ein stilles Rechteck."""
        self.assertIsNone(self._form((4, 12), 40))

    def test_db_fehler_heisst_none_statt_absturz(self):
        v = _stub_view()
        with patch("src.core.app_state.panel_grid_for", side_effect=RuntimeError("db")):
            self.assertIsNone(v._hinterlegte_form(_FX, 48))


# ── 2/3) Der Dialog-Vorschlag kommt aus dem Geraet — sonst wie bisher ───────

class VorbelegungTest(unittest.TestCase):

    def _frage(self, n, fx, gespeichert=(0, 0), antwort=(12, True)):
        _app()
        v = _stub_view()
        gesehen = {}

        def _getInt(parent, titel, text, wert, lo, hi, step):
            gesehen.update(text=text, wert=wert, lo=lo, hi=hi)
            return antwort

        with patch("src.core.app_state.panel_grid_for", return_value=gespeichert), \
             patch("src.ui.views.fixture_group_view.QInputDialog.getInt", _getInt):
            ergebnis = v._ask_block_cols(n, fx)
        return ergebnis, gesehen

    def test_vorschlag_kommt_aus_dem_geraet(self):
        ergebnis, g = self._frage(48, _FX, gespeichert=(4, 12))
        self.assertEqual(g["wert"], 12)
        self.assertIn("4×12", g["text"])
        self.assertEqual(ergebnis, 12)

    def test_ohne_geraet_bleibt_der_alte_wurzel_teiler(self):
        """Bestandsverhalten: ein Teiler von 48 nahe sqrt(48)=6,9 — also 6 oder 8,
        und NICHT 12. Genau dieser Vorschlag war am Rig falsch; hier wird
        festgehalten, dass er ohne Geraeteinformation unveraendert bleibt."""
        _, g = self._frage(48, None)
        self.assertIn(g["wert"], (6, 8))
        self.assertNotIn("hinterlegt", g["text"])

    def test_geraet_ohne_form_faellt_auf_den_alten_vorschlag(self):
        _, g = self._frage(48, _FX, gespeichert=(0, 0))
        self.assertIn(g["wert"], (6, 8))

    def test_form_passt_nicht_dann_alter_vorschlag(self):
        _, g = self._frage(40, _FX, gespeichert=(4, 12))
        self.assertNotEqual(g["wert"], 12)
        self.assertNotIn("hinterlegt", g["text"])

    def test_abbrechen_liefert_none(self):
        ergebnis, _ = self._frage(48, _FX, gespeichert=(4, 12), antwort=(12, False))
        self.assertIsNone(ergebnis)


# ── 4) Das Menue sagt, was passieren wird ───────────────────────────────────

class MenueBeschriftungTest(unittest.TestCase):

    def _aktualisiert(self, fx, koepfe, gespeichert):
        _app()
        act = QAction("wie im Gerät hinterlegt")
        v = _stub_view(_act_hinterlegt=act,
                       _target_fixture_leise=lambda: fx)
        with patch("src.core.app_state.panel_grid_for", return_value=gespeichert), \
             patch("src.core.app_state.color_head_count", return_value=koepfe):
            v._heads_menu_aktualisieren()
        return act

    def test_beschriftung_traegt_die_echte_form(self):
        act = self._aktualisiert(_FX, 48, (4, 12))
        self.assertEqual(act.text(), "wie im Gerät hinterlegt (4×12)")
        self.assertTrue(act.isEnabled())

    def test_kein_geraet_gewaehlt_ausgegraut(self):
        act = self._aktualisiert(None, 0, (4, 12))
        self.assertFalse(act.isEnabled())
        self.assertEqual(act.text(), "wie im Gerät hinterlegt")

    def test_einzelkopf_geraet_ausgegraut(self):
        act = self._aktualisiert(_FX, 1, (1, 1))
        self.assertFalse(act.isEnabled())

    def test_form_passt_nicht_ausgegraut(self):
        act = self._aktualisiert(_FX, 40, (4, 12))
        self.assertFalse(act.isEnabled())
        self.assertNotIn("×", act.text())


# ── Platzierung: ein 4x12-Panel landet als 4x12 ────────────────────────────

class PlatzierungTest(unittest.TestCase):

    def _grid_view(self, cols, rows):
        from src.ui.views.fixture_group_view import FixtureGridWidget
        _app()
        gw = FixtureGridWidget()
        gw.set_grid(cols, rows)
        sc, sr = QSpinBox(), QSpinBox()
        sc.setRange(1, 64); sr.setRange(1, 64)
        sc.setValue(cols); sr.setValue(rows)
        v = _stub_view(_grid_widget=gw, _spin_cols=sc, _spin_rows=sr)
        return v, gw, sc, sr

    def _zellen_von(self, gw, fid):
        from src.ui.views.fixture_group_view import _split_cell
        return sorted((c, r) for (c, r), val in gw.positions.items()
                      if _split_cell(val)[0] == fid)

    def test_48_koepfe_landen_als_4x12_rechteck(self):
        v, gw, _, _ = self._grid_view(12, 6)
        ok = v._block_platzieren(_FX, 48, 12, "t")
        self.assertTrue(ok)
        zellen = self._zellen_von(gw, 7)
        self.assertEqual(len(zellen), 48)
        self.assertEqual({c for c, _ in zellen}, set(range(12)))
        self.assertEqual({r for _, r in zellen}, set(range(4)))

    def test_zu_kleines_raster_waechst_mit(self):
        """Ein 4x4-Raster kann kein 4x12 aufnehmen — die Vorgabe darf daran
        nicht scheitern, sondern vergroessert das Raster (nie verkleinern)."""
        v, gw, sc, sr = self._grid_view(4, 4)
        ok = v._block_platzieren(_FX, 48, 12, "t")
        self.assertTrue(ok)
        self.assertEqual((gw.cols, gw.rows), (12, 4))
        self.assertEqual((sc.value(), sr.value()), (12, 4))
        self.assertEqual(len(self._zellen_von(gw, 7)), 48)


# ── 5) Die Daten der realen Panels passen zur Kopfzahl ──────────────────────

class RealePanelsTest(unittest.TestCase):
    """Fuer JEDES Builtin mit hinterlegter Rasterform muss zeilen*spalten der
    Zahl der ``color_r``-Baenke entsprechen — genau das ist die Bedingung, unter
    der ``_hinterlegte_form`` die Vorgabe anbietet. Stimmt sie fuer ein Geraet
    nicht, greift FM-40 dort nie, und niemand merkt es."""

    @classmethod
    def setUpClass(cls):
        from _fixture_quelle import frische_library
        cls._eng = frische_library(cls)

    def test_jede_hinterlegte_form_passt_zur_kopfzahl(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import (FixtureProfile, FixtureMode,
                                              FixtureChannel)
        gefunden = []
        with Session(self._eng) as s:
            profile = s.execute(select(FixtureProfile).options(
                selectinload(FixtureProfile.modes)
                .selectinload(FixtureMode.channels))).scalars().all()
            for p in profile:
                for m in p.modes:
                    if not (m.grid_rows and m.grid_cols):
                        continue
                    koepfe = sum(1 for c in m.channels if c.attribute == "color_r")
                    gefunden.append((p.short_name, m.name))
                    with self.subTest(profil=p.short_name, modus=m.name):
                        self.assertEqual(
                            m.grid_rows * m.grid_cols, koepfe,
                            f"{p.short_name}/{m.name}: Raster {m.grid_rows}x"
                            f"{m.grid_cols} passt nicht zu {koepfe} Koepfen")
        # Der Test darf nicht leer gruen sein: die vier bekannten Panels muessen
        # dabei sein, sonst prueft er nichts.
        kurz = {k for k, _ in gefunden}
        self.assertTrue({"ZQ06121", "STAIRMB5X5", "DOTZMATRIX", "STAIRPP144"} <= kurz,
                        f"Panels mit Rasterform: {sorted(kurz)}")


if __name__ == "__main__":
    unittest.main()
