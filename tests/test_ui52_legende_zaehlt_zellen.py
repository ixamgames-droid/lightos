"""UI-52: Die Legende zaehlt die belegten Kopf-Zellen, nicht `max(head)+1`.

Beide „Farbe → Gerät"-Legenden (Fixture-Gruppen-Editor UND Matrix-Editor)
schrieben je Geraet ``heads[fid] = max(heads.get(fid, 0), head + 1)`` — also den
HOECHSTEN Kopf-Index plus eins. Das ist nur dann die Zahl der Zellen, wenn die
Koepfe luecken los ab 0 im Raster liegen, und genau das tun nur die frisch
erzeugten Streifen (`create_head_matrix_group`, `place_fixture_heads`).

Zwei Raster, die es nicht tun, entstehen im Betrieb durch Rechtsklick →
„Zelle entfernen":

* **Ring-Raster (Robin Spiider, FM-14b):** aus der 20-zelligen Auto-Kopf-Matrix
  wird die Zelle des Kopfes 0 entfernt — Kopf 0 ist die GRUNDFARBE des Geraets
  und gehoert nicht in den Ring. Uebrig bleiben die 19 Pixel als Koepfe 1..19;
  gemeldet wurde „20 Koepfe".
* **Raster mit Luecke:** wer einen Kopf aus der MITTE nimmt, behaelt den
  hoechsten Index — die Legende zaehlte den entfernten Kopf weiter mit.

★ „19 statt 20" bekaeme man auch, indem man einfach 1 abzieht. Deshalb pruefen
die Tests hier Raster mit VERSCHIEDENEM Abstand zwischen `max(head)+1` und der
Zellzahl: der Ring (20 → 19, Abstand 1), die Luecke (4 → 2, Abstand 2), die
einzelne Kopf-Zelle (4 → 1, Abstand 3) und die unberuehrten Streifen (20 → 20
bzw. 4 → 4, Abstand 0, Positivkontrollen). Eine „-1"-Loesung faellt an der
Luecke UND an den Positivkontrollen durch.

Gemessen wird auf dem Weg, den der Nutzer nimmt — **kein Raster von Hand ins
`positions_json` geschrieben**:

  Patchen (legt die Auto-Kopf-Matrizen an) → „Matrizen zusammenlegen"
  (`merge_head_matrix_groups`) → Gruppen-Combo (`currentIndexChanged`) →
  `_load_group` → Rechtsklick ins Raster (`cell_context_menu` → `_on_cell_menu`
  → das WIRKLICH GEZEIGTE Menue) → Legende.

Auch die zwei Knoepfe, die das Raster sonst noch aendern, werden echt gedrueckt:
„Köpfe einzeln → Raster" im Gruppen-Editor und „Aus Auswahl" im Matrix-Editor.

Headless (QT_QPA_PLATFORM=offscreen).
"""
from __future__ import annotations
import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state, color_head_count
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import FixtureGroup, FixtureProfile, PatchedFixture
from src.core.show.show_file import reset_show
from src.ui.views.fixture_group_view import FixtureGroupView, _split_cell

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


def _kopfzahl(text: str, name: str) -> int | None:
    """Die in der Legende genannte Kopfzahl dieses Geraets (None = kein Zusatz)."""
    m = re.search(re.escape(name) + r"\s*\((\d+) (?:Kopf|Köpfe)\)", text)
    return int(m.group(1)) if m else None


class _RigBasis(unittest.TestCase):
    """Zwei Mehrkopf-Geraete patchen — das legt je eine Auto-Kopf-Matrix an."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        # Robin Spiider im 91-Kanal-Pixelmodus: 19 Pixel + Grundfarbe = 20 Baenke.
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

    # ── die echten Wege ins Raster ───────────────────────────────────────────

    def _auto_gid(self, fid: int) -> int:
        """Die beim Patchen automatisch angelegte Kopf-Matrix dieses Geraets."""
        with Session(self.state._show_engine) as s:
            for g in s.execute(select(FixtureGroup)).scalars():
                pos = g.positions_json or ""
                if f'"{fid}:0"' in pos:
                    return int(g.id)
        self.fail(f"keine Auto-Kopf-Matrix fuer Geraet {fid} gefunden")

    def _rig_gid(self) -> int:
        """„Matrizen zusammenlegen": beide Auto-Kopf-Matrizen zu EINEM Raster.
        Genau das macht der Knopf im Gruppen-Editor (`_merge_groups`)."""
        gid = self.state.merge_head_matrix_groups(
            [self._auto_gid(1), self._auto_gid(2)], "Rig")
        self.assertIsNotNone(gid, "Zusammenlegen hat keine Gruppe geliefert")
        return int(gid)

    def _gruppe_waehlen(self, gid: int):
        """Wie der Nutzer: Gruppenliste nachziehen (das macht GROUP_CHANGED) und
        die Gruppe in der Combo auswaehlen → currentIndexChanged → _load_group."""
        self.view._reload_group_list()
        combo = self.view._combo_group
        idx = combo.findData(gid)
        self.assertGreaterEqual(idx, 0, "Gruppe steht nicht in der Auswahlliste")
        if combo.currentIndex() == idx:      # sonst kaeme kein Wechsel-Signal
            combo.setCurrentIndex((idx + 1) % combo.count())
        combo.setCurrentIndex(idx)

    def _zelle_von(self, wert: str) -> tuple[int, int]:
        gw = self.view._grid_widget
        treffer = [c for c, v in gw.positions.items() if str(v) == str(wert)]
        self.assertEqual(len(treffer), 1, f"Zelle {wert!r} nicht eindeutig im Raster")
        return treffer[0]

    def _rechtsklick(self, wert: str, eintrag: str):
        """Rechtsklick auf die Zelle mit diesem Wert und Klick auf ``eintrag``.

        ★ Geht durch den ECHTEN Menue-Eingang: `cell_context_menu` →
        `_on_cell_menu` → `menu.exec(...)`. Geprueft wird das Menue, das dabei
        wirklich AUFGEHT (`QApplication.activePopupWidget()`), nicht das von
        `_build_cell_menu` zurueckgegebene — sonst bliebe ungemessen, ob der
        Nutzer den Eintrag ueberhaupt zu sehen bekommt."""
        col, row = self._zelle_von(wert)
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
        self.view._grid_widget.cell_context_menu.emit(col, row, QPoint(0, 0))
        self.assertIsNotNone(gesehen.get("menu"),
                             "Rechtsklick hat kein Menue gezeigt")
        self.assertIsNotNone(gesehen.get("aktion"),
                             f"„{eintrag}“ fehlt im GEZEIGTEN Menue an {wert!r}")

    def _tree_waehlen(self, fid: int):
        tree = self.view._fixture_list
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole) == fid:
                    tree.setCurrentItem(child)
                    return
        self.fail(f"Geraet {fid} steht nicht im Baum")

    # ── Ablesen ──────────────────────────────────────────────────────────────

    def _kopfzellen(self, fid: int) -> list[int]:
        return sorted(h for f, h in
                      (_split_cell(v) for v in self.view._grid_widget.positions.values())
                      if f == fid and h is not None)

    def _zellen_mit_farbe_von(self, fid: int) -> int:
        """Wie viele Zellen die Legende in der Farbe dieses Geraets einfaerbt."""
        return sum(1 for v in self.view._grid_widget.positions.values()
                   if _split_cell(v)[0] == fid)

    def _legende(self) -> str:
        return self.view._legend.text()


class LegendeZaehltZellenTest(_RigBasis):

    # ── 1) Ring-Raster: 19 Pixel → „19 Köpfe" ────────────────────────────────

    def test_ring_raster_meldet_die_zahl_der_pixel(self):
        """Der Fall aus dem Item — auf dem Weg, auf dem er im Betrieb entsteht:
        die Grundfarben-Zelle (Kopf 0) aus der Auto-Kopf-Matrix entfernen."""
        self._gruppe_waehlen(self._rig_gid())
        self.assertEqual(len(self._kopfzellen(1)), 20,
                         "Vorbedingung: Auto-Kopf-Matrix mit 20 Zellen")

        self._rechtsklick("1:0", "Zelle entfernen")

        koepfe = self._kopfzellen(1)
        self.assertEqual(koepfe, list(range(1, 20)), "Ring 1..19 nicht entstanden")
        self.assertEqual(max(koepfe) + 1, 20,
                         "ohne Abstand zwischen max(head)+1 und Zellzahl misst "
                         "der Test nichts")
        txt = self._legende()
        # `isVisible()` bliebe hier immer False (das Fenster wird nie gezeigt) —
        # `isHidden()` trennt „ausdruecklich versteckt" von „Elternfenster zu".
        self.assertFalse(self.view._legend.isHidden(), "Legende versteckt")
        self.assertEqual(_kopfzahl(txt, "Spiider"), 19,
                         f"Legende meldet die falsche Pixelzahl: {txt!r}")
        self.assertNotIn("20 Köpfe", txt)
        # Das zweite Geraet wird getrennt gezaehlt und bleibt unberuehrt.
        self.assertEqual(_kopfzahl(txt, "Bar"), 4, txt)

    # ── 2) Luecke in der Mitte → die entfernten Koepfe zaehlen nicht mit ─────

    def test_luecke_meldet_die_belegten_zellen(self):
        self._gruppe_waehlen(self._rig_gid())
        for kopf in (1, 2):
            self._rechtsklick(f"2:{kopf}", "Zelle entfernen")

        self.assertEqual(self._kopfzellen(2), [0, 3])
        txt = self._legende()
        self.assertEqual(_kopfzahl(txt, "Bar"), 2,
                         f"Legende zaehlt die entfernten Koepfe mit: {txt!r}")
        self.assertNotIn("4 Köpfe", txt)     # max(head)+1
        self.assertNotIn("3 Köpfe", txt)     # „einfach 1 abziehen"
        self.assertEqual(_kopfzahl(txt, "Spiider"), 20, txt)

    # ── 3) Positivkontrolle: unberuehrte Streifen melden wie vorher ──────────

    def test_zusammengelegte_streifen_melden_dieselbe_zahl_wie_vorher(self):
        """Der haeufige Fall: zwei Auto-Kopf-Matrizen, luecken los ab Kopf 0.
        Dort ist `max(head)+1` richtig — der Waechter darf hier NICHT anschlagen."""
        self._gruppe_waehlen(self._rig_gid())
        txt = self._legende()
        for fid, name in ((1, "Spiider"), (2, "Bar")):
            koepfe = self._kopfzellen(fid)
            self.assertEqual(koepfe, list(range(len(koepfe))), "Streifen hat Luecken")
            alt = max(koepfe) + 1        # das, was die Legende VORHER meldete
            self.assertEqual(_kopfzahl(txt, name), alt,
                             f"der gesunde Fall hat sich geaendert: {txt!r}")
        self.assertEqual(_kopfzahl(txt, "Spiider"), 20)
        self.assertEqual(_kopfzahl(txt, "Bar"), 4)
        self.assertNotIn("19 Köpfe", txt)    # „einfach 1 abziehen" waere falsch
        self.assertNotIn("3 Köpfe", txt)

    # ── 4) Positivkontrolle am ECHTEN Knopf „Köpfe einzeln → Raster" ─────────

    def test_knopf_koepfe_einzeln_ins_raster_zieht_die_legende_nach(self):
        """Der Knopf wird wirklich gedrueckt (Menue-Eintrag am `_btn_heads`),
        die Legende NICHT von Hand nachgezogen: gemessen wird auch die
        Meldekette `positions_changed → _highlight_group_members`."""
        self._gruppe_waehlen(self._rig_gid())
        self._rechtsklick("2:0", 'Alle Zellen von „Bar“ entfernen')
        self.assertEqual(self._kopfzellen(2), [], "Bar nicht aus dem Raster")

        self._tree_waehlen(2)
        eintrag = next(a for a in self.view._btn_heads.menu().actions()
                       if a.text() == "als Zeile (waagerecht)")
        with patch("src.ui.views.fixture_group_view.QMessageBox.information") as info:
            eintrag.trigger()
        info.assert_not_called()

        n = int(color_head_count(next(f for f in self.state.get_patched_fixtures()
                                      if f.fid == 2)))
        self.assertEqual(n, 4)
        self.assertEqual(self._kopfzellen(2), [0, 1, 2, 3])
        txt = self._legende()
        self.assertEqual(_kopfzahl(txt, "Bar"), n,
                         f"Legende folgt dem Knopf nicht: {txt!r}")

    # ── 5) EINE Kopf-Zelle bleibt als Kopf-Zelle erkennbar ───────────────────

    def test_einzelne_kopf_zelle_ist_von_der_ganz_zelle_unterscheidbar(self):
        """Bleibt von einem Geraet nur EIN Kopf im Raster, nennt die Legende ihn
        („1 Kopf"). Mit der alten Schwelle `n > 1` sah der Eintrag genau aus wie
        der eines Geraets, das als GANZES im Raster liegt — und die Legende gibt
        es, um genau das zu unterscheiden."""
        self._gruppe_waehlen(self._rig_gid())
        for kopf in (0, 1, 2):
            self._rechtsklick(f"2:{kopf}", "Zelle entfernen")
        self.assertEqual(self._kopfzellen(2), [3])
        # Das andere Geraet als GANZE Zelle (echter Menuepunkt „zusammenfassen").
        self._rechtsklick("1:0", '„Spiider“ zu einer Zelle zusammenfassen')
        self.assertEqual(self._kopfzellen(1), [])

        txt = self._legende()
        self.assertEqual(_kopfzahl(txt, "Bar"), 1, f"Kopf-Zelle verschwiegen: {txt!r}")
        self.assertIn("Bar (1 Kopf)", txt)          # Einzahl, nicht „1 Köpfe"
        self.assertIsNone(_kopfzahl(txt, "Spiider"),
                          f"die GANZ-Zelle darf keinen Kopf-Zusatz tragen: {txt!r}")

    # ── 6) Gezaehlt werden Kopf-Zellen, nicht eingefaerbte Zellen ────────────

    def test_ganz_zelle_zaehlt_nicht_als_kopf(self):
        """Ueber „Matrizen zusammenlegen" kann ein Geraet zugleich als GANZ-Zelle
        und kopfweise im selben Raster stehen (FM-30). Die Legende faerbt dann 5
        Zellen und nennt 4 — sie zaehlt KOPF-Zellen, nicht Farbfelder. Der Test
        haelt genau diese Lesart fest, damit die Begruendung im Code stimmt."""
        rig = self._rig_gid()
        self._gruppe_waehlen(rig)
        self._rechtsklick("2:0", '„Bar“ zu einer Zelle zusammenfassen')
        with patch("src.ui.views.fixture_group_view.QMessageBox"):
            self.view._save_group()          # Ganz-Zelle in die Show-DB
        gemischt = self.state.merge_head_matrix_groups([rig, self._auto_gid(2)],
                                                       "Rig + Bar-Köpfe")
        self.assertIsNotNone(gemischt)
        self._gruppe_waehlen(int(gemischt))

        self.assertEqual(self._zellen_mit_farbe_von(2), 5,
                         "Vorbedingung: Bar liegt als Ganz-Zelle UND kopfweise")
        self.assertEqual(self._kopfzellen(2), [0, 1, 2, 3])
        txt = self._legende()
        self.assertEqual(_kopfzahl(txt, "Bar"), 4,
                         f"die Ganz-Zelle wird als Kopf mitgezaehlt: {txt!r}")
        self.assertNotIn("5 Köpfe", txt)


class MatrixEditorLegendeTest(_RigBasis):
    """★ Dieselbe Formel stand ein zweites Mal im Matrix-Editor. Beide Ansichten
    zeigen DASSELBE Raster — sie duerfen nicht zwei verschiedene Zahlen nennen."""

    def _ring_gruppe_speichern(self) -> int:
        gid = self._rig_gid()
        self._gruppe_waehlen(gid)
        self._rechtsklick("1:0", "Zelle entfernen")
        with patch("src.ui.views.fixture_group_view.QMessageBox"):
            self.view._save_group()
        return gid

    def test_matrix_editor_nennt_dieselbe_zahl_wie_der_gruppen_editor(self):
        gid = self._ring_gruppe_speichern()
        gruppen_txt = self._legende()
        self.assertEqual(_kopfzahl(gruppen_txt, "Spiider"), 19, gruppen_txt)

        from src.core.engine.function_manager import get_function_manager
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        fm = get_function_manager()
        vorher = {f.id for f in fm.all()}

        def _aufraeumen():
            fm.stop_all()
            for f in list(fm.all()):
                if f.id not in vorher:
                    fm.remove(f.id)
        self.addCleanup(_aufraeumen)

        self.state.set_selected_group_id(gid)
        mv = RgbMatrixView()
        self.addCleanup(mv.deleteLater)
        mv._add()                                  # eine Matrix anlegen
        self.assertIsNotNone(mv._current)
        mv._btn_from_sel.click()                   # echter Knopf „Aus Auswahl"
        mv._chk_assignment.setChecked(True)        # echte Kasten „Zuordnung zeigen"

        ring = sorted(h for f, h in zip(mv._current.fixture_grid or [],
                                        mv._current.head_grid or [])
                      if f == 1 and h is not None)
        self.assertEqual(ring, list(range(1, 20)),
                         "Ring-Raster nicht im Matrix-Editor angekommen")
        txt = mv._legend.text()
        self.assertEqual(_kopfzahl(txt, "Spiider"), 19,
                         f"Matrix-Legende widerspricht der Gruppen-Legende: {txt!r}")
        self.assertNotIn("20 Köpfe", txt)
        self.assertEqual(_kopfzahl(txt, "Bar"), 4, txt)


if __name__ == "__main__":
    unittest.main()
