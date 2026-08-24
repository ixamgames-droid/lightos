"""UI-52: Die Gruppen-Legende zaehlt die belegten Zellen, nicht `max(head)+1`.

`fixture_group_view._refresh_legend` schrieb je Geraet
``heads[fid] = max(heads.get(fid, 0), head + 1)`` — also den HOECHSTEN Kopf-Index
plus eins. Das ist nur dann die Zahl der Zellen, wenn die Koepfe luecken los ab 0
im Raster liegen, und genau das tut nur der Streifen aus `place_fixture_heads`.

Zwei Raster, die es nicht tun, kommen im Betrieb vor:

* **Ring-Raster (Robin Spiider, FM-14b):** die 19 Pixel liegen als Koepfe 1..19
  im Raster — Kopf 0 ist die GRUNDFARBE des Geraets und gehoert nicht in den
  Ring. Gemeldet wurde „20 Koepfe" bei 19 Zellen.
* **Raster mit Luecke:** wer per Rechtsklick „Zelle entfernen" einen Kopf aus der
  Mitte nimmt, behaelt den hoechsten Index — die Legende zaehlt den entfernten
  Kopf weiter mit.

★ „19 statt 20" bekaeme man auch, indem man einfach 1 abzieht. Deshalb pruefen
die Tests hier drei Raster mit VERSCHIEDENEM Abstand zwischen `max(head)+1` und
der Zellzahl: der Ring (20 -> 19, Abstand 1), die Luecke 0/2/5 (6 -> 3, Abstand
3) und die luecken lose Reihe (4 -> 4, Abstand 0, Positivkontrolle). Eine
„-1"-Loesung faellt an der Luecke UND an der Positivkontrolle durch.

Gemessen wird auf dem Weg, den der Nutzer nimmt: Gruppe in der Show-DB ->
Auswahl in der Gruppen-Combo (`currentIndexChanged`) -> `_load_group` ->
`_highlight_group_members` -> Legende. Fuer die Luecke zusaetzlich ueber die
ECHTE Menue-Aktion „Zelle entfernen" aus `_build_cell_menu`.

Headless (QT_QPA_PLATFORM=offscreen).
"""
from __future__ import annotations
import json
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state, color_head_count
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import (
    FixtureGroup, FixtureProfile, PatchedFixture,
)
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


# ── Ring-Raster wie beim Robin Spiider ────────────────────────────────────────
# 19 Pixel als Wabe (3-4-5-4-3) in einem 5x5-Raster. Die Kopf-Indizes sind
# 1..19: Kopf 0 ist die Grundfarbe des Geraets (FM-14: „Bank 0 ist die
# Geraetefarbe") und liegt NICHT im Ring — daher beginnt der Ring bei 1 und
# `max(head)+1` ist um genau eins zu gross.
def _wabe_zellen() -> list[tuple[int, int]]:
    zeilen = {0: (1, 2, 3), 1: (0, 1, 2, 3), 2: (0, 1, 2, 3, 4),
              3: (0, 1, 2, 3), 4: (1, 2, 3)}
    return [(c, r) for r in sorted(zeilen) for c in zeilen[r]]


def _ring_positions(fid_ring: int, fid_extra: int) -> dict:
    zellen = _wabe_zellen()
    pos = {f"{c},{r}": f"{fid_ring}:{i}" for i, (c, r) in enumerate(zellen, start=1)}
    pos["4,0"] = fid_extra          # zweites Geraet (Legende zeigt erst ab zwei)
    return pos


def _kopfzahl(text: str, name: str) -> int | None:
    """Die in der Legende genannte Kopfzahl dieses Geraets (None = kein Zusatz)."""
    m = re.search(re.escape(name) + r"\s*\((\d+) Köpfe\)", text)
    return int(m.group(1)) if m else None


class LegendeZaehltZellenTest(unittest.TestCase):

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

    # ── Helfer: der echte Bedienweg ──────────────────────────────────────────

    def _gruppe_anlegen(self, name: str, cols: int, rows: int,
                        positions: dict) -> int:
        with Session(self.state._show_engine) as s:
            g = FixtureGroup(name=name, cols=cols, rows=rows,
                             positions_json=json.dumps(positions), folder="")
            s.add(g)
            s.commit()
            return int(g.id)

    def _gruppe_waehlen(self, gid: int):
        """Wie der Nutzer: Gruppenliste nachziehen (das macht GROUP_CHANGED) und
        die Gruppe in der Combo auswaehlen -> currentIndexChanged -> _load_group."""
        self.view._reload_group_list()
        combo = self.view._combo_group
        idx = combo.findData(gid)
        self.assertGreaterEqual(idx, 0, "Gruppe steht nicht in der Auswahlliste")
        if combo.currentIndex() == idx:      # sonst kaeme kein Wechsel-Signal
            combo.setCurrentIndex((idx + 1) % combo.count())
        combo.setCurrentIndex(idx)

    def _kopfzellen(self, fid: int) -> list[int]:
        return [int(str(v).split(":")[1])
                for v in self.view._grid_widget.positions.values()
                if str(v).startswith(f"{fid}:")]

    # ── 1) Ring-Raster: 19 Pixel -> „19 Köpfe" ───────────────────────────────

    def test_ring_raster_meldet_die_zahl_der_pixel(self):
        gid = self._gruppe_anlegen("Spiider Ring", 5, 5, _ring_positions(1, 2))
        self._gruppe_waehlen(gid)

        # Das geladene Raster traegt wirklich den Fall, um den es geht:
        koepfe = self._kopfzellen(1)
        self.assertEqual(len(koepfe), 19, "Ring-Raster nicht wie erwartet geladen")
        self.assertEqual(max(koepfe) + 1, 20,
                         "ohne Abstand zwischen max(head)+1 und Zellzahl misst "
                         "der Test nichts")

        txt = self.view._legend.text()
        # `isVisible()` bliebe hier immer False (das Fenster wird nie gezeigt) —
        # `isHidden()` trennt „ausdruecklich versteckt" von „Elternfenster zu".
        self.assertFalse(self.view._legend.isHidden(), "Legende versteckt")
        self.assertEqual(_kopfzahl(txt, "Spiider"), 19,
                         f"Legende meldet die falsche Pixelzahl: {txt!r}")
        self.assertNotIn("20 Köpfe", txt)

    # ── 2) Luecke im Raster (Koepfe 0, 2, 5) -> „3 Köpfe" ────────────────────

    def test_luecke_meldet_die_belegten_zellen(self):
        gw = self.view._grid_widget
        gid = self._gruppe_anlegen(
            "Bar + Spiider", 8, 2,
            {**{f"{i},0": f"1:{i}" for i in range(6)}, "0,1": 2})
        self._gruppe_waehlen(gid)
        self.assertEqual(sorted(self._kopfzellen(1)), [0, 1, 2, 3, 4, 5])

        # Koepfe 1, 3 und 4 ueber die ECHTE Menue-Aktion entfernen (Rechtsklick
        # auf die Zelle -> „Zelle entfernen"), nicht ueber die Innerei.
        for kopf in (1, 3, 4):
            zelle = next(c for c, v in gw.positions.items() if v == f"1:{kopf}")
            menu = self.view._build_cell_menu(*zelle)
            self.assertIsNotNone(menu, f"kein Menue an Zelle {zelle}")
            act = next(a for a in menu.actions() if a.text() == "Zelle entfernen")
            act.trigger()
            menu.deleteLater()

        self.assertEqual(sorted(self._kopfzellen(1)), [0, 2, 5])
        txt = self.view._legend.text()
        self.assertEqual(_kopfzahl(txt, "Spiider"), 3,
                         f"Legende zaehlt die entfernten Koepfe mit: {txt!r}")
        self.assertNotIn("6 Köpfe", txt)     # max(head)+1
        self.assertNotIn("5 Köpfe", txt)     # max(head)+1-1 („einfach 1 abziehen")

    # ── 3) Positivkontrolle: luecken lose 1xN-Reihe bleibt unveraendert ──────

    def test_luecken_lose_reihe_meldet_dieselbe_zahl_wie_vorher(self):
        gid = self._gruppe_anlegen(
            "Bar-Reihe", 8, 2,
            {**{f"{i},0": f"2:{i}" for i in range(4)}, "0,1": 1})
        self._gruppe_waehlen(gid)

        koepfe = self._kopfzellen(2)
        self.assertEqual(sorted(koepfe), [0, 1, 2, 3])
        alt = max(koepfe) + 1            # das, was die Legende VOR dem Fix meldete
        txt = self.view._legend.text()
        self.assertEqual(_kopfzahl(txt, "Bar"), alt,
                         f"der haeufige Fall hat sich geaendert: {txt!r}")
        self.assertEqual(_kopfzahl(txt, "Bar"), 4)
        self.assertNotIn("3 Köpfe", txt)     # „einfach 1 abziehen" waere falsch

    # ── 4) Positivkontrolle: der Streifen aus der echten Platzierfunktion ────

    def test_frisch_platzierter_streifen_meldet_die_kopfzahl_des_geraets(self):
        """Der haeufigste Weg ueberhaupt: „Köpfe einzeln → Raster". Die Legende
        muss dort GENAU die Kopfzahl des Geraets nennen — der Waechter darf den
        gesunden Fall nicht beanstanden."""
        gw = self.view._grid_widget
        gw.positions.clear()
        gw.set_grid(8, 8)
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 2)
        n = int(color_head_count(fx))
        self.assertEqual(n, 4)
        gw.place_fixture_heads(2, n, 0, 0)      # genau das ruft `_place_heads`
        gw.place_fixture(1, 0, 4)
        self.view._highlight_group_members()

        txt = self.view._legend.text()
        self.assertEqual(_kopfzahl(txt, "Bar"), n, f"Legende: {txt!r}")
        # Das ganze Geraet (Nicht-Kopf-Zelle) bekommt weiterhin KEINEN Zusatz.
        self.assertIsNone(_kopfzahl(txt, "Spiider"))

    # ── 5) Zwei Geraete im selben Raster werden getrennt gezaehlt ────────────

    def test_zwei_geraete_werden_getrennt_gezaehlt(self):
        pos = _ring_positions(1, 2)
        pos.pop("4,0")
        pos.update({f"{i},5": f"2:{i}" for i in range(4)})
        gid = self._gruppe_anlegen("Ring + Bar", 5, 6, pos)
        self._gruppe_waehlen(gid)

        txt = self.view._legend.text()
        self.assertEqual(_kopfzahl(txt, "Spiider"), 19, txt)
        self.assertEqual(_kopfzahl(txt, "Bar"), 4, txt)


if __name__ == "__main__":
    unittest.main()
