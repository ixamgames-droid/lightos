"""FM-32: „Matrizen zusammenlegen" setzt kein Geraet mehr in ZWEI Formen ins Raster.

Jede Platzier-Funktion des Gruppen-Editors haelt „ein Geraet steht nie doppelt im
Raster" ein (`place_fixture`/`place_fixture_heads` rufen vorher `_drop_fid_cells`).
`merge_head_matrix_groups` stapelte die Raster dagegen roh: legt man eine Gruppe,
in der die Bar als GANZ-Zelle liegt, mit ihrer Kopf-Matrix zusammen, stand die Bar
danach in **fuenf** Zellen — einmal ganz und viermal kopfweise.

★ Die Entscheidung: **die Kopf-Zellen gewinnen, die Ganz-Zelle faellt weg.**
Beide Varianten sind am selben echten Fall am DMX gemessen worden (Spiider 91ch
Pixel + LED PAR Bar 4×RGB, echte Profile, Farbe je Rasterzelle verschieden):

    Stapelreihenfolge          heute (beides)   Kopf-Zellen   Ganz-Zelle
    Rig + Bar-Koepfe           41 42 43 44      41 42 43 44   21 21 21 21
    Bar-Koepfe + Rig           41 41 41 41       1  2  3  4   41 41 41 41

Zwei Dinge stehen da. Erstens: **heute entscheidet die Stapelreihenfolge**, ob die
Bar vier Pixel zeigt oder eine uniforme Farbe — `RgbMatrixInstance.write` laeuft
row-major ueber das Raster, die spaeter geschriebene Zelle gewinnt. Zweitens: die
Ganz-Zelle kostet die Aufloesung, fuer die das Zusammenlegen ueberhaupt da ist
(24 belegte Zellen -> 21, vier Pixel -> ein Wert), waehrend die Kopf-Zellen alles
koennen, was die Ganz-Zelle kann — vier gleiche Farben sind auch vier Farben.
`test_die_ganz_zelle_wuerde_die_pixel_kosten` haelt diese Gegenprobe fest.

Gemessen wird der **Rasterzustand** (positions_json der neuen Gruppe) und der
**DMX-Ausgang**, nicht die Legende — die zaehlt Kopf-Zellen und war schon vorher
richtig (`test_ui52_legende_zaehlt_zellen.py`).

Nur Produktionswege: Patchen (legt die Auto-Kopf-Matrizen an) → „Matrizen
zusammenlegen" → Gruppen-Combo → Rechtsklick „zu einer Zelle zusammenfassen" →
Speichern → nochmal zusammenlegen. Kein Raster von Hand ins `positions_json`.

Headless (QT_QPA_PLATFORM=offscreen).
"""
from __future__ import annotations
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import (get_state, color_head_count, channels_for_head,
                                get_channels_for_patched)
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import FixtureGroup, FixtureProfile, PatchedFixture
from src.core.dmx.universe import Universe
from src.core.engine.rgb_matrix import (RgbAlgorithm, MatrixStyle, RgbMatrixInstance,
                                        grids_from_positions)
from src.core.group_cells import drop_whole_cells_with_heads, parse_group_cell
from src.core.show.show_file import reset_show
from src.ui.views.fixture_group_view import FixtureGroupView

import pytest as _pytest_xplat15                          # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets    # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


# ── Rein: die Regel selbst ────────────────────────────────────────────────────

class DropWholeCellsWithHeadsTest(unittest.TestCase):
    """`group_cells.drop_whole_cells_with_heads` — die Regel ohne Show-DB."""

    def test_ganz_zelle_weicht_den_kopf_zellen(self):
        zellen = {(0, 0): 2, (0, 1): "2:0", (1, 1): "2:1"}
        self.assertEqual(drop_whole_cells_with_heads(zellen),
                         {(0, 1): "2:0", (1, 1): "2:1"})

    def test_ohne_ueberschneidung_unveraendert(self):
        """Positivkontrolle: nur Ganz-Zellen, nur Kopf-Zellen, gemischte GERAETE —
        alles bleibt, solange kein Geraet in zwei Formen steht."""
        zellen = {"0,0": 5, "1,0": "9:0", "2,0": "9:1", "3,0": 7}
        self.assertEqual(drop_whole_cells_with_heads(zellen), zellen)

    def test_unbekannte_zellwerte_bleiben_stehen(self):
        """Was kein Geraet nennt, wird nicht angefasst (kein stiller Datenverlust)."""
        zellen = {"0,0": "kaputt", "1,0": None, "2,0": "5:0"}
        self.assertEqual(drop_whole_cells_with_heads(zellen), zellen)

    def test_leeres_raster(self):
        self.assertEqual(drop_whole_cells_with_heads({}), {})
        self.assertEqual(drop_whole_cells_with_heads(None), {})


# ── Der echte Fall ────────────────────────────────────────────────────────────

class _RigBasis(unittest.TestCase):
    """Zwei Mehrkopf-Geraete patchen — das legt je eine Auto-Kopf-Matrix an."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spiider", fixture_profile_id=_pid("SPIIDER"),
            mode_name="91-Kanal Pixel RGB (Mode 7)", universe=1, address=1,
            channel_count=91, manufacturer_name="Robe",
            fixture_name="Robin Spiider (Pixel-Wash)",
            fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="Bar", fixture_profile_id=_pid("PARBAR4"),
            mode_name="12-Kanal 4×RGB", universe=1, address=100, channel_count=12,
            manufacturer_name="Generic", fixture_name="LED PAR Bar 4×",
            fixture_type="led_bar"), undoable=False)
        self.view = FixtureGroupView()
        self.addCleanup(self.view.deleteLater)

    # ── die echten Wege ──────────────────────────────────────────────────────

    def _fixture(self, fid: int):
        fx = next((f for f in self.state.get_patched_fixtures() if f.fid == fid), None)
        self.assertIsNotNone(fx, f"Geraet {fid} nicht gepatcht")
        return fx

    def _koepfe(self, fid: int) -> int:
        """Kopfzahl AUS DEM PROFIL — keine Zahl von Hand (die Bibliothek darf
        wachsen, ohne dass der Test danebenliegt)."""
        n = int(color_head_count(self._fixture(fid)))
        self.assertGreaterEqual(n, 2, f"Geraet {fid} ist kein Multi-Head")
        return n

    def _auto_gid(self, fid: int) -> int:
        """Die beim Patchen automatisch angelegte Kopf-Matrix dieses Geraets."""
        with Session(self.state._show_engine) as s:
            for g in s.execute(select(FixtureGroup)).scalars():
                if f'"{fid}:0"' in (g.positions_json or ""):
                    return int(g.id)
        self.fail(f"keine Auto-Kopf-Matrix fuer Geraet {fid} gefunden")

    def _lade(self, gid: int) -> tuple[int, int, dict]:
        with Session(self.state._show_engine) as s:
            g = s.get(FixtureGroup, int(gid))
            self.assertIsNotNone(g, f"Gruppe {gid} fehlt in der Show-DB")
            return int(g.cols), int(g.rows), json.loads(g.positions_json or "{}")

    def _merge(self, gids, name) -> int:
        gid = self.state.merge_head_matrix_groups(list(gids), name)
        self.assertIsNotNone(gid, "Zusammenlegen hat keine Gruppe geliefert")
        return int(gid)

    def _gruppe_waehlen(self, gid: int):
        """Wie der Nutzer: Gruppenliste nachziehen und die Gruppe in der Combo
        waehlen → currentIndexChanged → _load_group."""
        self.view._reload_group_list()
        combo = self.view._combo_group
        idx = combo.findData(gid)
        self.assertGreaterEqual(idx, 0, "Gruppe steht nicht in der Auswahlliste")
        if combo.currentIndex() == idx:
            combo.setCurrentIndex((idx + 1) % combo.count())
        combo.setCurrentIndex(idx)

    def _rechtsklick(self, wert: str, eintrag: str):
        """Rechtsklick auf die Zelle mit diesem Wert und Klick auf ``eintrag`` —
        durch den ECHTEN Menue-Eingang (`cell_context_menu` → `_on_cell_menu` →
        das wirklich aufgehende Popup)."""
        gw = self.view._grid_widget
        treffer = [c for c, v in gw.positions.items() if str(v) == str(wert)]
        self.assertEqual(len(treffer), 1, f"Zelle {wert!r} nicht eindeutig im Raster")
        col, row = treffer[0]
        gesehen: dict = {}

        def _klick():
            m = QApplication.activePopupWidget()
            gesehen["menu"] = m
            if m is None:
                return
            act = next((a for a in m.actions() if a.text() == eintrag), None)
            gesehen["aktion"] = act
            if act is not None:
                act.trigger()
            m.close()

        QTimer.singleShot(0, _klick)
        gw.cell_context_menu.emit(col, row, QPoint(0, 0))
        self.assertIsNotNone(gesehen.get("menu"), "Rechtsklick hat kein Menue gezeigt")
        self.assertIsNotNone(gesehen.get("aktion"),
                             f"„{eintrag}“ fehlt im GEZEIGTEN Menue an {wert!r}")

    def _rig_mit_ganzer_bar(self) -> int:
        """Der Fall aus dem Item, ueber die Bedienung gebaut: beide Auto-Kopf-
        Matrizen zusammenlegen, dann die Bar per Rechtsklick zu EINER Zelle
        zusammenfassen und speichern."""
        rig = self._merge([self._auto_gid(1), self._auto_gid(2)], "Rig")
        self._gruppe_waehlen(rig)
        self._rechtsklick("2:0", '„Bar“ zu einer Zelle zusammenfassen')
        with patch("src.ui.views.fixture_group_view.QMessageBox"):
            self.view._save_group()
        _c, _r, pos = self._lade(rig)
        self.assertEqual(self._formen(pos, 2), {"ganz"},
                         "Vorbedingung: die Bar liegt im Rig als GANZ-Zelle")
        return rig

    # ── Ablesen ──────────────────────────────────────────────────────────────

    @staticmethod
    def _formen(positions: dict, fid: int) -> set:
        """Welche Formen dieses Geraet im Raster hat: {"ganz"} / {"kopf"} / beides."""
        formen = set()
        for v in positions.values():
            f, head = parse_group_cell(v)
            if f == fid:
                formen.add("ganz" if head is None else "kopf")
        return formen

    @staticmethod
    def _zellen_von(positions: dict, fid: int) -> dict:
        return {k: v for k, v in positions.items() if parse_group_cell(v)[0] == fid}

    def _rot_je_kopf(self, positions: dict, cols: int, rows: int, fid: int) -> list:
        """DMX-Rotwert JEDES Kopfes dieses Geraets, nachdem eine Matrix ueber
        genau dieses Raster geschrieben hat. Jede Rasterzelle bekommt einen
        anderen Rotwert (Zellindex+1) — so ist am Ausgang ablesbar, WELCHE Zelle
        den Kopf gefahren hat."""
        fid_grid, head_grid = grids_from_positions(positions, cols, rows)
        m = RgbMatrixInstance(name="fm32", cols=cols, rows=rows,
                              fixture_grid=fid_grid, head_grid=head_grid,
                              algorithm=RgbAlgorithm.PLAIN)
        m.style = MatrixStyle.RGB
        m.start()
        m._render = lambda step: [(min(255, i + 1), 0, 0) for i in range(cols * rows)]
        u = Universe(1)
        m.write({1: u}, list(self.state.get_patched_fixtures()), 0.0)
        fx = self._fixture(fid)
        chans = get_channels_for_patched(fx)
        out = []
        for h in range(self._koepfe(fid)):
            ch = channels_for_head(chans, h)["color_r"]
            out.append(u.get_channel(int(fx.address) + int(ch.channel_number) - 1))
        return out


class MergeKeineDoppelformTest(_RigBasis):

    # ── 1) Der Fall aus dem Item ─────────────────────────────────────────────

    def test_bar_steht_nach_dem_zusammenlegen_nur_noch_kopfweise(self):
        rig = self._rig_mit_ganzer_bar()
        gid = self._merge([rig, self._auto_gid(2)], "Rig + Bar-Köpfe")
        cols, rows, pos = self._lade(gid)

        # Wache gegen Leerlauf: das Raster traegt beide Geraete, Schwellen aus
        # dem Profil (Spiider-Pixel + Bar-Koepfe), nicht von Hand gesetzt.
        self.assertEqual(len(self._zellen_von(pos, 1)), self._koepfe(1))
        self.assertEqual(len(pos), self._koepfe(1) + self._koepfe(2))

        for fid in (1, 2):
            self.assertEqual(self._formen(pos, fid), {"kopf"},
                             f"Geraet {fid} steht in zwei Formen im Raster: "
                             f"{sorted(self._zellen_von(pos, fid).items())}")
        self.assertEqual(sorted(parse_group_cell(v)[1]
                                for v in self._zellen_von(pos, 2).values()),
                         list(range(self._koepfe(2))),
                         "die Bar-Koepfe sind nicht vollstaendig im Raster")
        # Die Rastergroesse bleibt, wie sie gestapelt wurde — die frei gewordene
        # Zelle ist eine Luecke, keine Verschiebung.
        self.assertEqual(cols, self._koepfe(1))
        self.assertEqual(rows, 3)

    def test_nur_noch_kopfform_egal_in_welcher_stapelreihenfolge(self):
        """Heute entscheidet die Reihenfolge, WELCHE Form auf DMX gewinnt. Die
        Regel darf nicht von ihr abhaengen.

        ★ Der Name sagt bewusst „nur noch Kopfform" und NICHT „kein Geraet steht
        zweimal": geprueft werden die FORMEN eines Geraets, nicht die Zahl seiner
        Zellen. Ein Geraet kann danach immer noch mehrfach im Raster stehen —
        naemlich kopfweise doppelt (FM-37). Der frueherer Name trug genau die
        breitere Zusage, und wer ihn greppt, haelt FM-37 fuer bewacht. Gefunden
        in der Gegenpruefung, gemessen: 28 statt 24 Zellen, `2:0` liegt an `0,1`
        UND `0,2` — und diese Zusicherung hier bleibt dabei gruen."""
        rig = self._rig_mit_ganzer_bar()
        auto2 = self._auto_gid(2)
        for reihenfolge in ([rig, auto2], [auto2, rig]):
            with self.subTest(reihenfolge=reihenfolge):
                _c, _r, pos = self._lade(self._merge(reihenfolge, "Fall"))
                self.assertEqual(self._formen(pos, 2), {"kopf"},
                                 f"Bar-Zellen: {sorted(self._zellen_von(pos, 2).items())}")

    # ── 2) Warum die Kopf-Zellen gewinnen — am DMX ───────────────────────────

    def test_die_bar_koepfe_bleiben_einzeln_ansprechbar(self):
        """Der Ertrag der Entscheidung: jede Zelle faehrt GENAU ihren Kopf, in
        beiden Stapelreihenfolgen dieselbe Aufloesung (vier verschiedene Werte)."""
        rig = self._rig_mit_ganzer_bar()
        auto2 = self._auto_gid(2)
        for reihenfolge in ([rig, auto2], [auto2, rig]):
            with self.subTest(reihenfolge=reihenfolge):
                cols, rows, pos = self._lade(self._merge(reihenfolge, "Fall"))
                rot = self._rot_je_kopf(pos, cols, rows, 2)
                self.assertEqual(len(set(rot)), self._koepfe(2),
                                 f"die Bar-Koepfe zeigen nicht mehr je eine "
                                 f"eigene Farbe: {rot}")
                self.assertNotIn(0, rot, f"ein Kopf bleibt dunkel: {rot}")

    def test_die_ganz_zelle_wuerde_die_pixel_kosten(self):
        """Die verworfene Variante, am selben echten Fall gemessen: liesse man die
        GANZ-Zelle gewinnen, faehren alle Bar-Koepfe denselben Wert und vier
        Rasterzellen fallen weg. Diese Gegenprobe traegt die Begruendung der
        Entscheidung — sie misst die Alternative, nicht den Produktionsweg."""
        rig = self._rig_mit_ganzer_bar()
        cols, rows, pos = self._lade(self._merge([rig, self._auto_gid(2)], "Fall"))
        # dasselbe Raster, aber mit der umgekehrten Vorrangregel: die Bar-Zellen
        # raus, dafuer die GANZ-Zelle an der Stelle, an der sie im Rig liegt.
        ganz_zelle = next(k for k, v in self._lade(rig)[2].items()
                          if parse_group_cell(v) == (2, None))
        ganz = {k: v for k, v in pos.items() if parse_group_cell(v)[0] != 2}
        ganz[ganz_zelle] = 2

        rot_kopf = self._rot_je_kopf(pos, cols, rows, 2)
        rot_ganz = self._rot_je_kopf(ganz, cols, rows, 2)
        self.assertEqual(len(set(rot_kopf)), self._koepfe(2), rot_kopf)
        self.assertEqual(len(set(rot_ganz)), 1,
                         f"die Gegenprobe misst nicht, was sie soll: {rot_ganz}")
        self.assertEqual(len(pos) - len(ganz), self._koepfe(2) - 1,
                         "die Ganz-Zelle wuerde mehr Rasterzellen kosten als sie bringt")

    # ── 3) Positivkontrollen ─────────────────────────────────────────────────

    def test_zwei_kopf_matrizen_ohne_ueberschneidung_werden_unveraendert_gestapelt(self):
        """Der haeufige Fall: zwei Kopf-Matrizen VERSCHIEDENER Geraete. Verglichen
        wird gegen das rohe Stapeln (im Test nachgerechnet) — die Regel darf hier
        nichts anfassen."""
        g1, g2 = self._auto_gid(1), self._auto_gid(2)
        c1, r1, p1 = self._lade(g1)
        c2, r2, p2 = self._lade(g2)
        erwartet = dict(p1)
        for k, v in p2.items():
            c, r = (int(x) for x in k.split(","))
            erwartet[f"{c},{r + r1}"] = v

        cols, rows, pos = self._lade(self._merge([g1, g2], "Rig"))
        self.assertEqual((cols, rows), (max(c1, c2), r1 + r2))
        self.assertEqual(pos, erwartet, "das gesunde Stapeln hat sich veraendert")
        self.assertEqual(len(pos), self._koepfe(1) + self._koepfe(2))
        self.assertEqual(self._formen(pos, 1), {"kopf"})
        self.assertEqual(self._formen(pos, 2), {"kopf"})

    def test_quell_gruppen_bleiben_unangetastet(self):
        """Nicht-destruktiv: die Ganz-Zelle verschwindet NUR im Ergebnis — das Rig
        behaelt seine, die Auto-Kopf-Matrix ihre Kopf-Zellen."""
        rig = self._rig_mit_ganzer_bar()
        auto2 = self._auto_gid(2)
        vorher = (self._lade(rig), self._lade(auto2))
        self._merge([rig, auto2], "Fall")
        self.assertEqual((self._lade(rig), self._lade(auto2)), vorher)


if __name__ == "__main__":
    unittest.main()
