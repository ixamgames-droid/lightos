"""FM-37: „Matrizen zusammenlegen" setzt kein Geraet mehr DOPPELT ins Raster.

FM-32 entschied nur das Zusammentreffen zweier FORMEN (Ganz-Zelle weicht den
Kopf-Zellen). Kommt dasselbe Geraet aus beiden Quellgruppen in DERSELBEN Form,
stapelte ``AppState._stack_group_grids`` es weiterhin roh. Gemessen ueber
Produktionswege (Patchen -> „Matrizen zusammenlegen" -> Combo -> Rechtsklick
„zu einer Zelle zusammenfassen" -> Speichern -> nochmal zusammenlegen):

    Fall                                    vorher              nachher
    (a) Bar je als GANZ-Zelle               Bar an '0,1'+'0,2'  nur '0,1'
        DMX color_r je Bar-Kopf             41 41 41 41         21 21 21 21
    (b) kopfweise Bar + Auto-Kopf-Matrix    28 Zellen, '2:0'    24 Zellen,
                                            an '0,1' UND '0,2'  '2:0' nur '0,1'
        DMX color_r je Bar-Kopf             41 42 43 44         21 22 23 24

★★ **Die Tie-Break-Regel, ausgesprochen: DAS ERSTE RASTER GEWINNT.** Sie ist
hier festgehalten, nicht als Nebenwirkung der Schleifenreihenfolge
stehengelassen — „frueher" heisst in der ``gids``-Reihenfolge, und die ist die,
die die Oberflaeche zusagt („Gruppen wählen (von oben nach unten gestapelt)").
``test_tie_break_folgt_der_stapelreihenfolge`` misst beide Reihenfolgen und
haelt fest, dass jeweils die Zelle des ERSTEN Rasters am DMX ankommt.

⚠️ In Fall (a) ist ein UNIFORMER Wert das RICHTIGE Ergebnis — eine Ganz-Zelle
faerbt alle Koepfe gleich. Geprueft wird deshalb, WELCHE der beiden Zellen
gewinnt (21 statt 41), nicht die Verschiedenheit der vier Werte. Wer hier den
FM-32-Test kopiert und „vier VERSCHIEDENE Werte" fordert, misst das Falsche.

Bewusst NICHT verlangt: „das Ergebnis haengt nicht mehr von der
Stapelreihenfolge ab". Das ist mit KEINER Tie-Break-Regel erreichbar (gemessen)
und widerspricht der zugesagten Bedienung.

Gemessen wird der Rasterzustand (``positions_json`` der neuen Gruppe) UND der
DMX-Ausgang. Headless (QT_QPA_PLATFORM=offscreen).
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

from src.core.app_state import (AppState, get_state, color_head_count,
                                channels_for_head, get_channels_for_patched)
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import FixtureGroup, FixtureProfile, PatchedFixture
from src.core.dmx.universe import Universe
from src.core.engine.rgb_matrix import (RgbAlgorithm, MatrixStyle, RgbMatrixInstance,
                                        grids_from_positions)
from src.core.group_cells import parse_zelle
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


def _doppelte(positions: dict) -> dict:
    """Zellwerte, die MEHR ALS EINMAL im Raster stehen -> ``{wert: [zellen]}``.

    Normiert ueber ``parse_zelle`` (``2`` und ``"2"`` sind dieselbe Zelle).
    Zellwerte, die kein Geraet nennen, zaehlen NICHT mit — sie werden bewusst
    nicht dedupliziert (kein stiller Datenverlust) und wuerden die Messung
    sonst mit einem Nicht-Befund fuellen."""
    nach_wert: dict = {}
    for schluessel, wert in (positions or {}).items():
        zelle = parse_zelle(wert)
        if zelle[0] is None:
            continue
        nach_wert.setdefault(zelle, []).append(schluessel)
    return {w: sorted(k) for w, k in nach_wert.items() if len(k) > 1}


# ── Rein: die Tie-Break-Regel selbst ─────────────────────────────────────────

class TieBreakRegelTest(unittest.TestCase):
    """``AppState._stack_group_grids`` — die ausgesprochene Regel, ohne Show-DB."""

    def _stapeln(self, *grids):
        return AppState._stack_group_grids(list(grids))

    def test_erstes_raster_gewinnt(self):
        """Der Kern: derselbe Zellwert aus zwei Rastern -> die Zelle des ZUERST
        gestapelten bleibt, die des spaeteren faellt weg."""
        g1 = (2, 1, {(0, 0): "5:0", (1, 0): "5:1"})
        g2 = (2, 1, {(0, 0): "5:0", (1, 0): "9:0"})
        _c, rows, merged = self._stapeln(g1, g2)
        self.assertEqual(rows, 2, "die Rastergroesse aendert die Regel nicht")
        self.assertEqual(merged.get((0, 0)), "5:0", "das erste Raster behaelt „5:0“")
        self.assertNotIn((0, 1), merged, "die spaetere „5:0“-Zelle steht noch da")
        self.assertEqual(merged.get((1, 1)), "9:0", "unbeteiligte Zelle verloren")
        self.assertEqual(_doppelte(merged), {})

    def test_letztes_raster_gewinnt_ausdruecklich_NICHT(self):
        """Gegenprobe zur angesagten Regel: die verworfene Alternative („letztes
        gewinnt") haette die Zelle des ZWEITEN Rasters behalten und die des
        ersten geraeumt. Ohne diese Probe waere „erstes gewinnt" nur behauptet."""
        g1 = (2, 1, {(0, 0): "5:0"})
        g2 = (2, 1, {(0, 0): "5:0", (1, 0): "9:0"})
        _c, _r, merged = self._stapeln(g1, g2)
        self.assertEqual(merged.get((0, 0)), "5:0",
                         f"das ERSTE Raster hat seine Zelle verloren: {merged}")
        self.assertNotIn((0, 1), merged,
                         f"nicht das erste, sondern das letzte Raster gewinnt: {merged}")

    def test_innerhalb_eines_rasters_gewinnt_die_zeilenweise_erste_zelle(self):
        """Auch WITHIN eines Rasters ist die Regel angesagt und nicht der Zufall
        der Dict-Reihenfolge: zeilenweise (Zeile, dann Spalte) — die Reihenfolge,
        in der ``RgbMatrixInstance.write`` schreibt.

        ``(1,0)`` steht zeilenweise VOR ``(0,1)``; spaltenweise waere es
        umgekehrt. Genau daran haengt, welche der beiden Zellen bleibt."""
        g = (2, 2, {(0, 1): "5:0", (1, 0): "5:0"})
        _c, _r, merged = self._stapeln(g, (1, 1, {(0, 0): "9:0"}))
        self.assertIn((1, 0), merged, "die zeilenweise ERSTE Zelle fehlt")
        self.assertNotIn((0, 1), merged,
                         "die zeilenweise SPAETERE Zelle steht noch da")

    def test_dasselbe_raster_zweimal_erzeugt_KEINE_doppelte_zelle(self):
        """★★★ Hier stand vorher die Gegenthese — und sie war falsch.

        Die erste Fassung nahm ein Raster, dessen Zellwerte schon einmal
        vollstaendig gestapelt worden waren, von der Entdopplung AUS
        („dasselbe Raster absichtlich mehrfach stapeln ist keine Kollision").
        Diese Ausnahme hing aber am RASTERINHALT und nicht an der Quelle, und
        feuerte deshalb auch bei zwei VERSCHIEDENEN Gruppen mit gleichem
        Raster. Gemessen ueber den Produktionsweg: die Bar landete an '0,0'
        UND '0,8', am DMX [65, 65, 65, 65] statt der angesagten [1, 1, 1, 1].

        ★ Und die Gegenthese widerspricht dem Abnahmekriterium dieses Items:
        „kein Zellwert kommt zweimal vor". Ein Geraet aus zwei Zellen zu fahren
        ist keine gewollte Vervielfachung, sondern sind zwei konkurrierende
        Werte auf denselben Kanaelen — welcher gewinnt, entscheidet die
        Schreibreihenfolge. Die zweite Kopie kann nichts beitragen, was die
        erste nicht schon tut.

        Die Reihen wachsen weiter (der Versatz ist eine Eigenschaft des
        Stapelns, nicht der Belegung) — die Zellen werden nur nicht doppelt
        vergeben.
        """
        g = (1, 2, {(0, 0): "1:0", (0, 1): "1:1"})
        _c, rows, merged = self._stapeln(g, g, g)
        self.assertEqual(rows, 6, "der Versatz addiert sich weiterhin")
        self.assertEqual(_doppelte(merged), {},
                         f"dasselbe Geraet liegt mehrfach im Raster: {merged}")
        self.assertEqual(sorted(merged.values()), ["1:0", "1:1"],
                         "jedes Geraet genau einmal")

    def test_zwei_VERSCHIEDENE_gruppen_mit_gleichem_raster(self):
        """★★ Der Fall, den die alte Ausnahme durchgewinkt hat, und der erste,
        den das Item nennt: zwei Gruppen, die BEIDE dieselbe Bar als Ganz-Zelle
        fuehren. Am Rasterinhalt sind sie nicht zu unterscheiden — genau
        deshalb darf die Regel nicht daran haengen."""
        a = (8, 8, {(0, 0): "2"})
        b = (8, 8, {(0, 0): "2"})
        _c, _r, merged = self._stapeln(a, b)
        self.assertEqual(_doppelte(merged), {},
                         f"die Bar liegt in beiden Rastern: {merged}")
        self.assertEqual(sorted(merged), [(0, 0)],
                         "das ERSTE Raster behaelt die Zelle")

    def test_gleiche_werte_an_anderen_stellen_sind_keine_wiederholung(self):
        """Die Ausnahme haengt am ganzen Raster, nicht bloss an seinen Werten:
        dieselben Zellwerte an ANDEREN Stellen sind zwei verschiedene Raster —
        die Regel greift."""
        g1 = (2, 1, {(0, 0): "5:0"})
        g2 = (2, 1, {(1, 0): "5:0"})
        _c, _r, merged = self._stapeln(g1, g2)
        self.assertEqual(sorted(merged), [(0, 0)],
                         f"versetzte Kopie als Wiederholung durchgewinkt: {merged}")

    def test_eine_gekuerzte_kopie_ist_kein_vorbild_fuer_die_ausnahme(self):
        """„Wiederholt" heisst: das Vorbild steht selbst VOLLSTAENDIG im
        Ergebnis. Sonst duerfte ausgerechnet die halbierte Kopie eines Rasters
        das Doppel wieder hereinholen — gemessen an ``[Rig, Bar, Bar]``."""
        rig = (2, 1, {(0, 0): "5:0", (1, 0): "9:0"})
        bar = (1, 1, {(0, 0): "5:0"})
        _c, _r, merged = self._stapeln(rig, bar, bar)
        self.assertEqual(_doppelte(merged), {},
                         f"die zweite Bar-Kopie hat das Doppel zurueckgeholt: {merged}")
        self.assertEqual(sorted(merged.values()), ["5:0", "9:0"])

    def test_int_und_string_meinen_dieselbe_zelle(self):
        """Der Gruppen-Editor schreibt den ganzen fid als int, eine geladene
        Alt-Show als str. Ein roher Wertvergleich haette das Doppel je nach
        Schreibweise mal erkannt und mal nicht."""
        g1 = (2, 1, {(0, 0): 5, (1, 0): "9:0"})
        g2 = (2, 1, {(0, 0): "5"})
        _c, _r, merged = self._stapeln(g1, g2)
        self.assertEqual(sorted(merged), [(0, 0), (1, 0)],
                         f"str und int gelten nicht als dieselbe Zelle: {merged}")

    def test_ganz_zelle_und_kopf_zelle_bleiben_zwei_verschiedene_werte(self):
        """Abgrenzung zu FM-32: „5" und „5:0" sind fuer DIESE Regel NICHT
        derselbe Zellwert. Dass am Ende trotzdem nur die Kopf-Zelle steht,
        entscheidet ``drop_whole_cells_with_heads`` — die Zustaendigkeiten
        bleiben getrennt."""
        _c, _r, merged = self._stapeln((1, 1, {(0, 0): 5}), (1, 1, {(0, 0): "5:0"}))
        self.assertEqual(list(merged.values()), ["5:0"],
                         "FM-32 laesst nach dem Stapeln nicht mehr die Kopf-Zelle stehen")

    def test_farb_kopf_und_weiss_segment_raeumen_einander_nicht_weg(self):
        """FM-41-Asymmetrie: die beiden Achsen sind verschiedene Zellen. Sonst
        loeschte das Zusammenlegen genau die Kombination weg, fuer die die
        Weiss-Achse gebaut wurde."""
        _c, _r, merged = self._stapeln((1, 1, {(0, 0): "5:0"}),
                                       (1, 1, {(0, 0): "5:w0"}))
        self.assertEqual(sorted(merged.values()), ["5:0", "5:w0"], merged)

    def test_doppeltes_weiss_segment_faellt_ebenso_weg(self):
        """… und auf der Weiss-Achse gilt die Regel genauso. Mit dem
        verlustbehafteten ``parse_group_cell`` als Schluessel bliebe FM-37 dort
        vollstaendig stehen (Weiss-Zellen gaelten als „kein Geraet")."""
        g1 = (2, 1, {(0, 0): "5:w0"})
        g2 = (2, 1, {(0, 0): "5:w0", (1, 0): "9:0"})
        _c, _r, merged = self._stapeln(g1, g2)
        self.assertNotIn((0, 1), merged,
                         f"das doppelte Weiss-Segment steht noch im Raster: {merged}")
        self.assertEqual(merged.get((1, 1)), "9:0")

    def test_dieselbe_zelle_anders_geschrieben_zaehlt_trotzdem_als_dieselbe(self):
        """``2`` und ``"2"`` sind dasselbe Geraet — die Schreibweise darf die
        Entdopplung nicht aushebeln. (Frueher pruefte dieser Test, dass eine
        so geschriebene Wiederholung von der Regel AUSGENOMMEN bleibt; die
        Ausnahme ist mit ihrem Loch entfallen, s. o.)"""
        a = (2, 1, {(0, 0): 2})
        b = (2, 1, {(0, 0): "2"})
        _c, _r, merged = self._stapeln(a, b)
        self.assertEqual(_doppelte(merged), {},
                         f"unterschiedliche Schreibweise umgeht die Regel: {merged}")
        self.assertEqual(sorted(merged), [(0, 0)])

    def test_unparsbare_zellwerte_bleiben_stehen(self):
        """Was kein Geraet nennt, wird nicht angefasst — auch doppelt nicht
        (kein stiller Datenverlust, dieselbe Linie wie
        ``drop_whole_cells_with_heads``)."""
        g1 = (2, 1, {(0, 0): "kaputt"})
        g2 = (2, 1, {(0, 0): "kaputt", (1, 0): "9:0"})
        _c, _r, merged = self._stapeln(g1, g2)
        self.assertEqual(sorted(merged), [(0, 0), (0, 1), (1, 1)],
                         f"ein unparsbarer Zellwert wurde stillschweigend "
                         f"wegdedupliziert: {merged}")

    def test_unparsbare_zellwerte_unterscheiden_zwei_raster(self):
        """Auch was kein Geraet nennt, macht zwei Raster verschieden. Sonst
        schluepfte ein FREMDES Raster als „Wiederholung" durch die Ausnahme —
        und braechte sein Doppel mit."""
        g1 = (2, 1, {(0, 0): "kaputt A", (1, 0): "5:0"})
        g2 = (2, 1, {(0, 0): "kaputt B", (1, 0): "5:0"})
        _c, _r, merged = self._stapeln(g1, g2)
        self.assertNotIn((1, 1), merged,
                         f"zwei verschiedene Raster galten als Wiederholung: {merged}")
        self.assertEqual(sorted(merged), [(0, 0), (0, 1), (1, 0)], merged)

    def test_zwei_raster_ohne_ueberschneidung_unveraendert(self):
        """Positivkontrolle: verschiedene Geraete werden weiterhin roh
        gestapelt (Zellwerte UND Zellen unveraendert)."""
        g1 = (4, 1, {(0, 0): "5:0", (1, 0): "5:1", (2, 0): "5:2", (3, 0): "5:3"})
        g2 = (4, 1, {(0, 0): "9:0", (1, 0): "9:1", (2, 0): "9:2", (3, 0): "9:3"})
        cols, rows, merged = self._stapeln(g1, g2)
        self.assertEqual((cols, rows), (4, 2))
        self.assertEqual(merged, {(0, 0): "5:0", (1, 0): "5:1", (2, 0): "5:2",
                                  (3, 0): "5:3", (0, 1): "9:0", (1, 1): "9:1",
                                  (2, 1): "9:2", (3, 1): "9:3"})


# ── Der echte Fall: Produktionswege ──────────────────────────────────────────

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
        """Kopfzahl AUS DEM PROFIL — keine Zahl von Hand."""
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
        durch den ECHTEN Menue-Eingang (das wirklich aufgehende Popup)."""
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

    def _speichern(self):
        with patch("src.ui.views.fixture_group_view.QMessageBox"):
            self.view._save_group()

    def _rig_kopfweise(self) -> int:
        """Das ALLTAGS-Rig: beide Auto-Kopf-Matrizen zusammengelegt — 20
        Spiider-Pixel in Reihe 0, die vier Bar-Koepfe in Reihe 1."""
        rig = self._merge([self._auto_gid(1), self._auto_gid(2)], "Rig")
        _c, _r, pos = self._lade(rig)
        self.assertEqual(len(pos), self._koepfe(1) + self._koepfe(2),
                         "Vorbedingung: das Rig fuehrt beide Geraete kopfweise")
        return rig

    def _rig_mit_ganzer_bar(self) -> int:
        """Fall (a): dasselbe Rig, aber die Bar per Rechtsklick zu EINER Zelle
        zusammengefasst und gespeichert."""
        rig = self._rig_kopfweise()
        self._gruppe_waehlen(rig)
        self._rechtsklick("2:0", '„Bar“ zu einer Zelle zusammenfassen')
        self._speichern()
        _c, _r, pos = self._lade(rig)
        self.assertEqual(self._formen(pos, 2), {"ganz"},
                         "Vorbedingung: die Bar liegt im Rig als GANZ-Zelle")
        return rig

    def _nur_die_ganze_bar(self) -> int:
        """Die zweite Quelle aus Fall (a): eine frisch angelegte Gruppe, in die
        der Nutzer nur die Bar als ganzes Geraet legt (Drop -> place_fixture)."""
        with patch("src.ui.views.fixture_group_view.QInputDialog.getText",
                   return_value=("Nur Bar", True)):
            self.view._new_group()
        gid = int(self.view._current_group.id)
        self.assertIsNotNone(self.view._grid_widget.place_fixture(2, 0, 0),
                             "die Bar liess sich nicht ins Raster legen")
        self._speichern()
        _c, _r, pos = self._lade(gid)
        self.assertEqual([parse_zelle(v) for v in pos.values()], [(2, None, None)],
                         f"Vorbedingung: die Gruppe haelt NUR die ganze Bar: {pos}")
        return gid

    # ── Ablesen ──────────────────────────────────────────────────────────────

    @staticmethod
    def _formen(positions: dict, fid: int) -> set:
        formen = set()
        for v in positions.values():
            f, _achse, index = parse_zelle(v)
            if f == fid:
                formen.add("ganz" if index is None else "kopf")
        return formen

    @staticmethod
    def _zellen_von(positions: dict, fid: int) -> list:
        return sorted((k, v) for k, v in positions.items()
                      if parse_zelle(v)[0] == fid)

    def _rot_je_kopf(self, positions: dict, cols: int, rows: int, fid: int) -> list:
        """DMX-Rotwert JEDES Kopfes dieses Geraets, nachdem eine Matrix ueber
        genau dieses Raster geschrieben hat. Jede Rasterzelle bekommt einen
        anderen Rotwert (Zellindex+1) — so ist am Ausgang ablesbar, WELCHE Zelle
        den Kopf gefahren hat."""
        fid_grid, head_grid = grids_from_positions(positions, cols, rows)
        m = RgbMatrixInstance(name="fm37", cols=cols, rows=rows,
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


class MergeOhneDoppelteZellenTest(_RigBasis):

    # ── Fall (a): die Bar je als GANZ-Zelle ──────────────────────────────────

    def test_fall_a_die_ganze_bar_steht_nur_noch_in_EINER_zelle(self):
        """Rig mit ganzer Bar + Gruppe, die nur die ganze Bar haelt. Vorher lag
        die Bar an '0,1' UND '0,2'."""
        rig = self._rig_mit_ganzer_bar()
        cols, rows, pos = self._lade(self._merge([rig, self._nur_die_ganze_bar()],
                                                 "Fall a"))
        self.assertEqual(self._doppelte_zellwerte(pos), {},
                         f"Zellwerte stehen doppelt im Raster: {pos}")
        self.assertEqual(len(self._zellen_von(pos, 2)), 1,
                         f"die Bar hat nicht genau EINE Zelle: "
                         f"{self._zellen_von(pos, 2)}")
        # Wache gegen Leerlauf: das Raster traegt beide Geraete vollstaendig.
        self.assertEqual(len(self._zellen_von(pos, 1)), self._koepfe(1))
        self.assertEqual(len(pos), self._koepfe(1) + 1)

    def test_fall_a_am_dmx_gewinnt_die_zelle_des_ERSTEN_rasters(self):
        """⚠️ UNIFORM ist hier das RICHTIGE Ergebnis — eine Ganz-Zelle faerbt
        alle Koepfe gleich. Gemessen wird, WELCHE der beiden Zellen den Wert
        stellt: 21 (Rig, Reihe 1) statt 41 (angehaengte Gruppe, Reihe 2)."""
        rig = self._rig_mit_ganzer_bar()
        rig_zelle = self._zellen_von(self._lade(rig)[2], 2)[0][0]
        cols, rows, pos = self._lade(self._merge([rig, self._nur_die_ganze_bar()],
                                                 "Fall a"))
        # Vorbedingung: die ueberlebende Zelle ist die aus dem Rig.
        self.assertEqual([k for k, _v in self._zellen_von(pos, 2)], [rig_zelle],
                         "es ueberlebt nicht die Zelle des ersten Rasters")
        c, r = (int(x) for x in str(rig_zelle).split(","))
        erwartet = r * cols + c + 1
        rot = self._rot_je_kopf(pos, cols, rows, 2)
        self.assertEqual(rot, [erwartet] * self._koepfe(2),
                         f"nicht die Zelle des ersten Rasters faehrt die Bar: {rot}")
        self.assertEqual(erwartet, 21, "die Messgroesse hat sich verschoben")

    # ── Fall (b): kopfweise Bar + deren Auto-Kopf-Matrix ─────────────────────

    def test_fall_b_kein_kopf_liegt_mehr_in_zwei_zellen(self):
        """Vorher: 28 statt 24 Zellen, '2:0' an '0,1' UND '0,2'."""
        rig = self._rig_kopfweise()
        cols, rows, pos = self._lade(self._merge([rig, self._auto_gid(2)], "Fall b"))
        self.assertEqual(self._doppelte_zellwerte(pos), {},
                         f"Zellwerte stehen doppelt im Raster: {pos}")
        self.assertEqual(len(pos), self._koepfe(1) + self._koepfe(2),
                         f"nicht {self._koepfe(1) + self._koepfe(2)} Zellen: {len(pos)}")
        self.assertEqual(sorted(parse_zelle(v)[2]
                                for _k, v in self._zellen_von(pos, 2)),
                         list(range(self._koepfe(2))),
                         "die Bar-Koepfe sind nicht mehr vollstaendig im Raster")
        # Die Rastergroesse bleibt, wie gestapelt — die frei gewordenen Zellen
        # sind Luecken, keine Verschiebung (wie nach „Zelle entfernen").
        self.assertEqual((cols, rows), (self._koepfe(1), 3))

    def test_fall_b_am_dmx_faehrt_jeden_kopf_die_zelle_des_ERSTEN_rasters(self):
        """Vorher 41,42,43,44 (die spaeter geschriebene Zelle), jetzt 21,22,23,24
        — die Bar-Koepfe des Rigs in Reihe 1."""
        rig = self._rig_kopfweise()
        cols, rows, pos = self._lade(self._merge([rig, self._auto_gid(2)], "Fall b"))
        rot = self._rot_je_kopf(pos, cols, rows, 2)
        self.assertEqual(rot, [21, 22, 23, 24],
                         f"nicht die Zellen des ersten Rasters fahren die Bar: {rot}")

    # ── Die Regel selbst, am DMX ─────────────────────────────────────────────

    def test_tie_break_folgt_der_stapelreihenfolge(self):
        """★ Die angesagte Regel, nicht bloss ein zufaellig stabiles Ergebnis:
        dreht man die Stapelreihenfolge um, gewinnen die Zellen der ANDEREN
        Gruppe — weil sie dann das erste Raster ist. Bewusst NICHT verlangt,
        dass das Ergebnis reihenfolge-UNABHAENGIG ist (das ist mit keiner
        Tie-Break-Regel erreichbar und widerspricht der zugesagten Bedienung
        „von oben nach unten gestapelt")."""
        rig = self._rig_kopfweise()
        auto2 = self._auto_gid(2)
        gemessen = {}
        for reihenfolge in ([rig, auto2], [auto2, rig]):
            with self.subTest(reihenfolge=reihenfolge):
                cols, rows, pos = self._lade(self._merge(reihenfolge, "Fall"))
                self.assertEqual(self._doppelte_zellwerte(pos), {},
                                 f"Doppel in Reihenfolge {reihenfolge}: {pos}")
                self.assertEqual(len(pos), self._koepfe(1) + self._koepfe(2))
                gemessen[tuple(reihenfolge)] = self._rot_je_kopf(pos, cols, rows, 2)
        # Rig zuerst: die Bar-Koepfe liegen in Reihe 1 (Index 20..23) -> 21..24.
        self.assertEqual(gemessen[(rig, auto2)], [21, 22, 23, 24])
        # Auto-Kopf-Matrix zuerst: sie ist jetzt Reihe 0 (Index 0..3) -> 1..4.
        self.assertEqual(gemessen[(auto2, rig)], [1, 2, 3, 4])
        self.assertNotEqual(gemessen[(rig, auto2)], gemessen[(auto2, rig)],
                            "die Messung unterscheidet die beiden Reihenfolgen nicht")

    # ── Alltagszustand: eine Show, die das Doppel schon mitbringt ────────────

    def test_nochmal_zusammenlegen_laesst_das_raster_nicht_weiter_wachsen(self):
        """Der Alltag: der Nutzer legt zusammen, legt spaeter nochmal zusammen.
        Vorher wuchs das Raster bei jedem Mal (24 -> 28 -> 32)."""
        rig = self._rig_kopfweise()
        auto2 = self._auto_gid(2)
        gid = self._merge([rig, auto2], "Runde 1")
        for runde in range(2, 5):
            with self.subTest(runde=runde):
                gid = self._merge([gid, auto2], f"Runde {runde}")
                _c, _r, pos = self._lade(gid)
                self.assertEqual(self._doppelte_zellwerte(pos), {}, pos)
                self.assertEqual(len(pos), self._koepfe(1) + self._koepfe(2),
                                 f"Runde {runde} hat das Raster wachsen lassen")

    def test_eine_alt_show_mit_doppelzellen_wird_beim_zusammenlegen_geraeumt(self):
        """Alltagszustand aus dem Bestand: Shows, die VOR diesem Fix
        zusammengelegt wurden, tragen das Doppel im ``positions_json`` — der
        Editor-Rundlauf raeumt es nicht weg (28 rein, 28 raus). Beim naechsten
        Zusammenlegen muss es fallen, sonst waechst es weiter mit.

        Das Alt-Raster wird aus den ECHTEN Zellen zweier Produktionsgruppen
        gebaut (genau so, wie der alte Code sie gestapelt hat), nicht von Hand
        getippt."""
        rig = self._rig_kopfweise()
        cols, rows, rig_pos = self._lade(rig)
        _c2, r2, auto_pos = self._lade(self._auto_gid(2))
        alt = dict(rig_pos)                      # das rohe Stapeln von damals
        for k, v in auto_pos.items():
            c, r = (int(x) for x in k.split(","))
            alt[f"{c},{r + rows}"] = v
        self.assertEqual(len(self._doppelte_zellwerte(alt)), self._koepfe(2),
                         "Vorbedingung: das Alt-Raster traegt das Doppel wirklich")
        with Session(self.state._show_engine) as s:
            g = FixtureGroup(name="Alt-Show", cols=cols, rows=rows + r2,
                             positions_json=json.dumps(alt), folder="Matrizen")
            s.add(g)
            s.commit()
            alt_gid = int(g.id)

        _c, _r, pos = self._lade(self._merge([alt_gid, self._auto_gid(1)], "Aufraeumen"))
        self.assertEqual(self._doppelte_zellwerte(pos), {},
                         f"das Alt-Doppel steht immer noch im Raster: {pos}")
        self.assertEqual(len(pos), self._koepfe(1) + self._koepfe(2))

    # ── Gegenproben: was sich NICHT aendern darf ─────────────────────────────

    def test_zwei_kopf_matrizen_verschiedener_geraete_unveraendert_gestapelt(self):
        """Positivkontrolle aus dem Item: 24 Zellen (Spiider 20 + Bar 4).
        Verglichen wird gegen das rohe Stapeln — die Regel darf hier nichts
        anfassen."""
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

    def test_fm32_bleibt_die_ganz_zelle_weicht_den_kopf_zellen(self):
        """Gegenprobe an der Nachbarregel: FM-37 darf FM-32 nicht abschalten.
        Rig mit ganzer Bar + deren KOPF-Matrix -> die Bar steht danach nur noch
        kopfweise, mit allen vier Koepfen."""
        rig = self._rig_mit_ganzer_bar()
        _c, _r, pos = self._lade(self._merge([rig, self._auto_gid(2)], "FM-32"))
        self.assertEqual(self._formen(pos, 2), {"kopf"},
                         f"Bar-Zellen: {self._zellen_von(pos, 2)}")
        self.assertEqual(len(self._zellen_von(pos, 2)), self._koepfe(2))
        self.assertEqual(self._doppelte_zellwerte(pos), {}, pos)

    def test_die_quell_gruppen_bleiben_unangetastet(self):
        """Nicht-destruktiv: geraeumt wird NUR im Ergebnis."""
        rig = self._rig_kopfweise()
        auto2 = self._auto_gid(2)
        vorher = (self._lade(rig), self._lade(auto2))
        self._merge([rig, auto2], "Fall")
        self.assertEqual((self._lade(rig), self._lade(auto2)), vorher)

    def test_zusammenlegen_liefert_weiterhin_eine_gruppe(self):
        """Gegenprobe gegen den billigen „Fix": wer das Zusammenlegen
        abschaltet, besteht jede Doppel-Pruefung."""
        gid = self._merge([self._auto_gid(1), self._auto_gid(2)], "Rig")
        _c, _r, pos = self._lade(gid)
        self.assertEqual(len(pos), self._koepfe(1) + self._koepfe(2))
        self.assertIsNone(self.state.merge_head_matrix_groups([gid]),
                          "unter zwei Gruppen darf nichts entstehen")

    @staticmethod
    def _doppelte_zellwerte(positions: dict) -> dict:
        return _doppelte(positions)


if __name__ == "__main__":
    unittest.main()
