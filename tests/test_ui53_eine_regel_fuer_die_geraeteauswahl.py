"""UI-53 — EIN Einstieg fuer "wen darf dieses Widget anfassen", und die
RESET-Reihe stand auf der falschen Fassung.

Bis 2026-09-07 beantworteten VIER Fassungen dieselbe Frage
(``_fixtures_with_attr``, ``_fixtures_with_any_attr``,
``_range_compatible_fixtures`` und eine vierte, INLINE in
``_build_orientation_bar``), und jede der SIEBEN Schnellwahl-Reihen suchte sich
ihre Fassung selbst aus. Das war kein Lesbarkeitsproblem:

★★ **Gemessen am laufenden Code** (``ProgrammerView``, echter Bauweg, echter
Klick): der ``ResetActionButton`` backt den Mittelwert des VORLAGEN-Bereichs
``kind='reset'`` ein und schreibt ihn LITERAL auf jedes Geraet
(``_set_on_fixtures``) — gefiltert wurde aber nur nach Kanal-Existenz.

* ``SHARPY [16-Kanal]`` (Vorlage, Reset-Mittelwert **51** = "Effekt-Reset")
  neben ``ZQ02001 [11-Kanal]``: dort liegt 51 im Bereich 0–149
  **"Keine Funktion"** (``kind=''``). Der Knopf verspricht eine
  Rekalibrierung; das zweite Geraet bekam einen Kanalwert, der nichts tut.
* Bibliotheksweit (448 Modi mit ``reset``-Kanal, 100128 Paare): an **91918**
  Paaren (91,8 %) landete der Vorlagenwert am Partner in einem Bereich mit
  ANDEREN Grenzen oder anderer ``kind``-Bedeutung. Nach der Umstellung: **0**.

Die Nutzlast entscheidet ueber die Regel, nicht die Filter-Technik
(:class:`src.core.fixture_filter.Nutzlast`):

* (i)   LITERALWERT AUS EINEM VORLAGEN-BEREICH — Shutter, Farbrad, Gobo, Reset
* (ii)  ABSOLUTER Wert auf EINEM Kanal — Pan/Tilt-Speed, Farb-Synchronregler
* (iii) ABSOLUTE Werte auf einer KANALMENGE — RGB-Kacheln, Orientierungsleiste

★ Gemessen wird am DMX-Ausgang UND am Programmer-Dict (ein stiller Dict-Eintrag
wandert in Szenen/Snaps mit), ueber den echten Bauweg: echte Builtin-Profile
patchen, ``ProgrammerView`` bauen, ueber ``set_selected_cells`` auswaehlen, das
gebaute Widget aus dem Baum holen und mit ``QTest.mouseClick`` wirklich klicken.

★ Nur MITGELIEFERTE Profile (``source='builtin'``): ein Test auf ein Profil aus
einer lokal importierten Bibliothek haette in der CI nichts zu messen (QA-61).

Gegenproben — wichtiger als der Kern, denn ein Einstieg, der irgendwo strenger
wird, nimmt dem Bediener Geraete weg:

* die SECHS uebrigen Reihen behalten an einer gemischten Auswahl ihre HEUTIGE
  Geraeteliste (jede Reihe mit mindestens einem Treffer UND einem Ausschluss),
* die Orientierungsleiste behaelt das Tilt-ohne-Pan-Geraet (``SPIDER14``;
  101 solche Modi in der Bibliothek DIESES Rechners) — gemessen ueber deren
  5125 Modi antwortet der gemeinsame Einstieg 1608 mal "ja", genau wie die alte
  Inline-Fassung, 0 Abweichungen,
* zwei BAUGLEICHE Geraete bleiben an der Reset-Reihe BEIDE erhalten (ein Fix,
  der nur die Vorlage stehen liesse, bestuende sonst jeden Kern-Test),
* der Alltagszustand (vier Geraete, Programmer schon gefuellt, Reihe schon
  einmal benutzt) wird ausdruecklich mitgemessen — eine Regel, die nur am
  frischen, leeren Objekt geprueft wird, ist nur dort festgenagelt.
"""
from __future__ import annotations

import ast
import inspect
import os
import textwrap
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QGroupBox,  # noqa: E402
                               QLabel, QMessageBox)
from PySide6.QtTest import QTest                                    # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_channels_for_patched, get_state  # noqa: E402
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import (FixtureMode, FixtureProfile,  # noqa: E402
                                      PatchedFixture)
from src.core.fixture_filter import (Nutzlast, attr_head_count,     # noqa: E402
                                     fixtures_fuer_nutzlast, hat_kanal,
                                     range_signature)
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.views import programmer_view as pv_mod                  # noqa: E402
from src.ui.views.programmer_view import (AttributeSlider,          # noqa: E402
                                          ProgrammerView)
from src.ui.widgets.preset_tile import (ColorQuickBar,              # noqa: E402
                                        GoboQuickBar,
                                        ResetActionButton,
                                        ShutterQuickBar)

def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    """Profil-ID ueber den KURZnamen eines Builtins (nie ueber den Anzeigenamen —
    der existiert je nach Rechner nur lokal, Fallenklasse QA-23)."""
    with Session(fdb_engine()) as s:
        got = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()
    assert got is not None, f"Builtin-Profil {short} fehlt in der Bibliothek"
    return int(got)


def _mode_name(short: str, channels: int) -> str:
    """Modusname ueber die KANALZAHL — die Anzeigenamen der Modi sind Fliesstext."""
    with Session(fdb_engine()) as s:
        return s.execute(select(FixtureMode.name).where(
            FixtureMode.fixture_id == _pid(short),
            FixtureMode.channel_count == channels)).scalars().first()


class _Basis(unittest.TestCase):
    """Echte Profile patchen, echte View bauen, DMX lesen."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self._addr = 1

    # ── Patchen ───────────────────────────────────────────────────────────
    def _patch(self, fid: int, short: str, channels: int) -> PatchedFixture:
        mode = _mode_name(short, channels)
        self.assertIsNotNone(
            mode, f"Builtin {short} hat keinen {channels}-Kanal-Modus — der "
                  f"Test wuerde sonst ein anderes Geraet messen als er behauptet")
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"F{fid}", fixture_profile_id=_pid(short),
            mode_name=mode, universe=1, address=self._addr,
            channel_count=channels, fixture_type="moving_head"), undoable=False)
        self._addr += channels
        return self._fx(fid)

    def _fx(self, fid: int) -> PatchedFixture:
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _kanal(self, fid: int, attr: str):
        return next((c for c in get_channels_for_patched(self._fx(fid))
                     if c.attribute == attr), None)

    def _attrs(self, fid: int) -> set:
        return {(c.attribute or "") for c in get_channels_for_patched(self._fx(fid))}

    def _bereich_um(self, fid: int, attr: str, wert: int):
        """Der Bereich des Kanals, in den dieser DMX-Wert faellt (oder None)."""
        ch = self._kanal(fid, attr)
        self.assertIsNotNone(ch, f"fid {fid} hat keinen {attr}-Kanal")
        return next((r for r in (getattr(ch, "ranges", None) or [])
                     if int(r.range_from) <= wert <= int(r.range_to)), None)

    # ── Widgets ueber den echten Bauweg ────────────────────────────────────
    def _view(self, cells) -> ProgrammerView:
        """Frische View je Messung, sonst liefert ``findChildren`` auch die
        Widgets frueherer Auswahlen."""
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        self.state.set_selected_cells([str(c) for c in cells])
        _app().processEvents()
        return v

    @staticmethod
    def _fids(widget) -> tuple:
        return tuple(f.fid for f in widget._fixtures)

    def _widget_nach_label(self, view, text: str):
        """Das Widget, das die Schnellwahl DIREKT hinter dieser Beschriftung in
        die Tab-Spalte haengt.

        ★ Noetig, weil ``speed`` AUSSERDEM einen generischen Regler im
        Position-Tab hat: ``findChildren(AttributeSlider)`` liefert zwei, und
        ein Test, der einfach den ersten nimmt, misst womoeglich gar nicht die
        Schnellwahl-Reihe, die er zu pruefen behauptet."""
        lbl = next((l for l in view.findChildren(QLabel) if l.text() == text),
                   None)
        self.assertIsNotNone(lbl, f"Beschriftung {text!r} nicht gebaut")
        lay = lbl.parentWidget().layout()
        for i in range(lay.count() - 1):
            if lay.itemAt(i).widget() is lbl:
                return lay.itemAt(i + 1).widget()
        self.fail(f"hinter {text!r} steht kein Widget")

    # ── DMX / Programmer ──────────────────────────────────────────────────
    def _grundstellung(self, *fids: int):
        """Einmal spuelen, damit die ``default_value`` schon auf DMX stehen —
        sonst enthielte der erste gemessene Klick den Erst-Flush."""
        for fid in fids:
            self.state._flush_programmer_to_dmx(int(fid))

    def _dmx(self, fid: int) -> dict:
        fx = self._fx(fid)
        uni = self.state.universes[fx.universe]
        return {c.name: uni.get_channel(fx.address + c.channel_number - 1)
                for c in get_channels_for_patched(fx)}

    def _prog(self, fid: int) -> dict:
        return dict(self.state.programmer.get(fid, {}))

    def _klick(self, widget, fids, bestaetigen: bool = False) -> dict:
        """Wirklich klicken und zurueckgeben, welche DMX-Kanaele und welche
        Programmer-Eintraege sich je Geraet dadurch geaendert haben."""
        fids = tuple(fids)
        self._grundstellung(*fids)
        vor_dmx = {fid: self._dmx(fid) for fid in fids}
        vor_prog = {fid: self._prog(fid) for fid in fids}
        if bestaetigen:
            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Yes):
                QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        else:
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        _app().processEvents()
        self._grundstellung(*fids)
        out = {}
        for fid in fids:
            nach_dmx, nach_prog = self._dmx(fid), self._prog(fid)
            out[fid] = (
                {k: v for k, v in nach_dmx.items() if vor_dmx[fid].get(k) != v},
                {k: v for k, v in nach_prog.items() if vor_prog[fid].get(k) != v},
            )
        return out


# ══ 1. Wache gegen Leerlauf ═════════════════════════════════════════════════

class ProfileTragenDenBefundTest(_Basis):
    """Ohne diese Kanal-/Bereichsverteilung misst der ganze Rest nichts."""

    def setUp(self):
        super().setUp()
        self._patch(1, "SHARPY", 16)
        self._patch(2, "ZQ02001", 11)

    def test_beide_haben_reset_mit_VERSCHIEDENEM_bereichs_layout(self):
        for fid in (1, 2):
            self.assertIn("reset", self._attrs(fid),
                          f"fid {fid} muss einen reset-Kanal haben")
        self.assertNotEqual(
            range_signature(self._kanal(1, "reset")),
            range_signature(self._kanal(2, "reset")),
            "gleiche reset-Layouts — dann gibt es den Befund an diesem Paar "
            "gar nicht")

    def test_der_vorlagenwert_der_sharpy_ist_am_zq02001_KEIN_reset(self):
        """★ Der eigentliche Schaden: derselbe DMX-Wert, andere Bedeutung."""
        vorlage = next(r for r in self._kanal(1, "reset").ranges
                       if (r.kind or "") == "reset")
        wert = (int(vorlage.range_from) + int(vorlage.range_to)) // 2
        self.assertEqual(wert, 51, "Vorlagen-Reset-Mittelwert der SHARPY")
        fremd = self._bereich_um(2, "reset", wert)
        self.assertIsNotNone(fremd, "kein Bereich getroffen — anderer Befund")
        self.assertNotEqual(
            (fremd.kind or ""), "reset",
            f"am ZQ02001 bedeutet DMX {wert} {fremd.name!r} — waere das ein "
            f"reset-Bereich, gaebe es den Befund an diesem Paar nicht")


# ══ 2. Der Kern: die Reset-Reihe faehrt ueber die Vorlagen-Bereichs-Regel ═══

class ResetReiheFaehrtUeberDenVorlagenBereichTest(_Basis):
    """(b) des Kriteriums: die RESET-Reihe faehrt ueber Nutzlast (i)."""

    def _knopf(self):
        self._patch(1, "SHARPY", 16)
        self._patch(2, "ZQ02001", 11)
        knoepfe = self._view([1, 2]).findChildren(ResetActionButton)
        self.assertEqual(len(knoepfe), 1, "genau ein Reset-Knopf erwartet")
        return knoepfe[0]

    def test_knopf_traegt_das_fremde_reset_layout_nicht_mehr(self):
        knopf = self._knopf()
        self.assertEqual(knopf._reset_value, 51,
                         "die SHARPY muss die Vorlage sein — sonst misst der "
                         "Test ein anderes Paar als er beschreibt")
        self.assertEqual(self._fids(knopf), (1,),
                         "das ZQ02001 hat ein anderes reset-Layout und darf "
                         "den Vorlagenwert nicht bekommen")

    def test_klick_laesst_das_fremde_reset_layout_unberuehrt(self):
        """★★ Der Kern, am DMX-Ausgang gemessen."""
        knopf = self._knopf()
        dmx, prog = self._klick(knopf, (1, 2), bestaetigen=True)[2]
        self.assertEqual(dmx, {}, "DMX 51 bedeutet am ZQ02001 'Keine Funktion' "
                                  "— ein Klick darf dort nichts bewegen")
        self.assertEqual(prog, {}, "...und auch keinen stillen Dict-Eintrag "
                                   "hinterlassen (landet sonst in Szenen/Snaps)")

    def test_klick_trifft_die_vorlage_weiterhin(self):
        """Positivkontrolle im selben Klick: der Fix darf die Reihe nicht
        abschalten."""
        knopf = self._knopf()
        dmx, prog = self._klick(knopf, (1, 2), bestaetigen=True)[1]
        self.assertEqual(dmx.get("Reset"), 51,
                         f"die SHARPY muss ihren Reset-Kanal sehen: {dmx}")
        self.assertEqual(prog.get("reset"), 51)

    def test_die_alte_regel_haette_das_fremde_geraet_genommen(self):
        """★ Beleg, dass die Sonde ihren Gegenstand ERREICHT: nach der alten
        Regel (nur Kanal-Existenz, FM-34) waere das ZQ02001 dabei gewesen."""
        knopf = self._knopf()
        alle = [self._fx(1), self._fx(2)]
        alt = [f.fid for f in alle if hat_kanal(f, "reset")]
        self.assertEqual(alt, [1, 2],
                         "die alte Regel nahm beide — sonst zeigt dieser Test "
                         "keinen Unterschied und die Messung ist wertlos")
        self.assertEqual(self._fids(knopf), (1,),
                         "die neue Regel nimmt nur das gleiche Layout")


class ZweiBaugleicheGeraeteBleibenBeideTest(_Basis):
    """★ Gegenprobe zum Kern: ein Fix, der nur die VORLAGE stehen liesse,
    bestuende jeden Test oben — und haette die Reihe faktisch abgeschaltet."""

    def test_beide_sharpy_bekommen_den_reset(self):
        self._patch(1, "SHARPY", 16)
        self._patch(2, "SHARPY", 16)
        knopf = self._view([1, 2]).findChildren(ResetActionButton)[0]
        self.assertEqual(self._fids(knopf), (1, 2),
                         "zwei baugleiche Geraete haben dasselbe Layout und "
                         "muessen BEIDE am Knopf haengen")
        erg = self._klick(knopf, (1, 2), bestaetigen=True)
        for fid in (1, 2):
            self.assertEqual(erg[fid][0].get("Reset"), 51,
                             f"fid {fid} muss seinen Reset-Kanal sehen: "
                             f"{erg[fid][0]}")


class ResetReiheImAlltagszustandTest(_Basis):
    """⚠️ Regel 5 — der ALLTAGSZUSTAND, nicht das bequemste Objekt.

    Vier Geraete statt zwei, der Programmer schon gefuellt, eine andere
    Schnellwahl-Reihe vorher wirklich benutzt. Eine Regel, die nur am frischen,
    leeren Objekt geprueft wird, ist nur dort festgenagelt."""

    def _auswahl(self):
        self._patch(1, "SHARPY", 16)       # Vorlage
        self._patch(2, "SHARPY", 16)       # baugleich -> muss dabei bleiben
        self._patch(3, "ZQ02001", 11)      # fremdes reset-Layout -> raus
        self._patch(4, "PAR3", 3)          # gar kein reset -> raus
        return self._view([1, 2, 3, 4])

    def test_vorbedingung_der_alltagszustand_ist_wirklich_hergestellt(self):
        v = self._auswahl()
        # Vorbelegung wie nach ein paar Minuten Programmieren
        for fid in (1, 2, 3, 4):
            self.state.set_programmer_value(fid, "intensity", 200)
        shutter = v.findChildren(ShutterQuickBar)
        self.assertTrue(shutter, "keine Shutter-Reihe gebaut — nichts benutzt")
        QTest.mouseClick(shutter[0], Qt.MouseButton.LeftButton)
        _app().processEvents()
        self.assertTrue(any(self._prog(f) for f in (1, 2, 3, 4)),
                        "der Programmer ist leer — dann misst dieser Test "
                        "denselben bequemen Zustand wie die Tests oben")

    def test_reset_reihe_trennt_auch_im_gefuellten_zustand_richtig(self):
        v = self._auswahl()
        for fid in (1, 2, 3, 4):
            self.state.set_programmer_value(fid, "intensity", 200)
        self.state.set_programmer_value(3, "shutter", 30)
        knopf = v.findChildren(ResetActionButton)[0]
        self.assertEqual(self._fids(knopf), (1, 2),
                         "beide SHARPY dabei, ZQ02001 (fremdes Layout) und "
                         "PAR3 (kein reset-Kanal) draussen")
        erg = self._klick(knopf, (1, 2, 3, 4), bestaetigen=True)
        for fid in (1, 2):
            self.assertEqual(erg[fid][0].get("Reset"), 51,
                             f"fid {fid}: {erg[fid][0]}")
        for fid in (3, 4):
            self.assertEqual(erg[fid], ({}, {}),
                             f"fid {fid} darf vom Reset nichts abbekommen")

    def test_der_reset_klick_ruehrt_die_vorhandenen_werte_nicht_an(self):
        """Gegenprobe: was sich NICHT aendern darf, gehoert ebenso festgenagelt."""
        v = self._auswahl()
        for fid in (1, 2, 3, 4):
            self.state.set_programmer_value(fid, "intensity", 200)
        knopf = v.findChildren(ResetActionButton)[0]
        self._klick(knopf, (1, 2, 3, 4), bestaetigen=True)
        for fid in (1, 2, 3, 4):
            self.assertEqual(self._prog(fid).get("intensity"), 200,
                             f"fid {fid} hat seinen vorhandenen Wert verloren")


# ══ 3. Gegenprobe: die sechs uebrigen Reihen behalten ihre Auswahl ══════════

class SechsUebrigeReihenBehaltenIhreAuswahlTest(_Basis):
    """★ Wichtiger als der Kern: ein gemeinsamer Einstieg, der irgendwo
    STRENGER wird, nimmt dem Bediener Geraete weg.

    Eine gemischte Auswahl, an der JEDE Reihe sowohl einen Treffer als auch
    einen Ausschluss hat:

    * fid 1 ``MH8``      — Pan/Tilt, Speed, Shutter/Farbrad/Gobo (Layout A)
    * fid 2 ``MH16``     — dieselben drei Layouts wie MH8, Pan/Tilt, Speed
    * fid 3 ``SPIDER14`` — TILT OHNE PAN, Speed, RGB, Shutter (Layout B)
    * fid 4 ``PAR3``     — nur RGB, sonst nichts
    """

    def setUp(self):
        super().setUp()
        self._patch(1, "MH8", 8)
        self._patch(2, "MH16", 16)
        self._patch(3, "SPIDER14", 14)
        self._patch(4, "PAR3", 3)
        self.v = self._view([1, 2, 3, 4])

    # ── Wachen gegen Leerlauf ─────────────────────────────────────────────
    def test_vorbedingung_die_auswahl_unterscheidet_wirklich(self):
        self.assertEqual(range_signature(self._kanal(1, "shutter")),
                         range_signature(self._kanal(2, "shutter")),
                         "MH8 und MH16 muessen dasselbe Shutter-Layout haben")
        self.assertNotEqual(range_signature(self._kanal(1, "shutter")),
                            range_signature(self._kanal(3, "shutter")),
                            "SPIDER14 muss ein ANDERES Shutter-Layout haben")
        self.assertNotIn("pan", self._attrs(3),
                         "SPIDER14 muss Tilt OHNE Pan haben — sonst misst die "
                         "Gegenprobe zur Orientierungsleiste nichts")
        self.assertIn("tilt", self._attrs(3))
        self.assertEqual(self._attrs(4) & {"pan", "tilt", "speed", "shutter",
                                           "color_wheel", "gobo_wheel"}, set(),
                         "PAR3 darf nur RGB haben")
        self.assertIn("color_r", self._attrs(3))
        self.assertIn("color_r", self._attrs(4))

    # ── Reihe 1: Shutter — Nutzlast (i) ───────────────────────────────────
    def test_shutter_reihe_behaelt_gleiche_layouts_und_wirft_fremde_raus(self):
        bars = self.v.findChildren(ShutterQuickBar)
        self.assertEqual(len(bars), 1)
        self.assertEqual(self._fids(bars[0]), (1, 2),
                         "MH8/MH16 gleiches Layout -> dabei; SPIDER14 anderes "
                         "Layout und PAR3 ohne Shutter -> raus")

    # ── Reihe 2 + 3: RGB (iii) und Farbrad (i) ────────────────────────────
    def test_rgb_kacheln_behalten_jedes_geraet_mit_einem_farbkanal(self):
        bars = self.v.findChildren(ColorQuickBar)
        self.assertEqual(len(bars), 1)
        self.assertEqual(self._fids(bars[0]), (3, 4),
                         "SPIDER14 und PAR3 haben RGB; MH8/MH16 haben nur ein "
                         "Farbrad und gehoeren nicht an die RGB-Kacheln")

    def test_farbrad_kacheln_bleiben_bei_gleichem_slot_layout(self):
        bar = self.v.findChildren(ColorQuickBar)[0]
        self.assertEqual(tuple(f.fid for f in bar._wheel_fixtures), (1, 2),
                         "MH8/MH16 haben dasselbe Farbrad-Layout")

    # ── Reihe 4: Gobo — Nutzlast (i) ──────────────────────────────────────
    def test_gobo_reihe_behaelt_gleiche_slot_layouts(self):
        bars = self.v.findChildren(GoboQuickBar)
        self.assertEqual(len(bars), 1)
        self.assertEqual(self._fids(bars[0]), (1, 2))

    # ── Reihe 5: Orientierungsleiste — Nutzlast (iii) ─────────────────────
    def test_orientierungsleiste_behaelt_das_tilt_ohne_pan_geraet(self):
        """★ Die vierte, frueher INLINE ausgeschriebene Fassung. 101
        Builtin-Modi haben Tilt ohne Pan — wuerde der gemeinsame Einstieg hier
        'pan UND tilt' verlangen, verschwaenden sie aus der Leiste."""
        boxen = [b for b in self.v.findChildren(QGroupBox)
                 if b.title().startswith("Ausrichtung")]
        self.assertEqual(len(boxen), 1, "genau eine Orientierungsleiste")
        cb = boxen[0].findChildren(QCheckBox)[0]
        self.assertEqual(tuple(f.fid for f in cb._orient_fixtures), (1, 2, 3),
                         "MH8/MH16 (Pan+Tilt) und SPIDER14 (nur Tilt) gehoeren "
                         "hinein, PAR3 (weder noch) nicht")

    def test_orientierungs_klick_schreibt_nicht_auf_den_par(self):
        """Gegenprobe am Schreibweg: die Flags landen nur an Pan/Tilt-Geraeten."""
        boxen = [b for b in self.v.findChildren(QGroupBox)
                 if b.title().startswith("Ausrichtung")]
        cb = next(c for c in boxen[0].findChildren(QCheckBox)
                  if "Pan invert" in c.text())
        cb.click()
        _app().processEvents()
        self.assertTrue(getattr(self._fx(3), "invert_pan", False),
                        "SPIDER14 (Tilt ohne Pan) muss das Flag bekommen")
        self.assertFalse(getattr(self._fx(4), "invert_pan", False),
                         "der PAR3 hat keine Orientierung")

    # ── Reihe 6: Speed — Nutzlast (ii) ────────────────────────────────────
    def test_speed_regler_behaelt_jedes_geraet_mit_speed_kanal(self):
        regler = self._widget_nach_label(self.v, "Pan/Tilt-Speed:")
        self.assertIsInstance(regler, AttributeSlider)
        self.assertEqual(getattr(regler._channel, "attribute", ""), "speed",
                         "hinter der Beschriftung haengt nicht der Speed-Regler")
        self.assertEqual(self._fids(regler), (1, 2, 3),
                         "MH8/MH16/SPIDER14 haben speed, der PAR3 nicht — "
                         "absolute Werte brauchen NUR die Kanal-Existenz")


class FarbSynchronreglerFahrenUeberDenselbenEinstiegTest(_Basis):
    """Der Aufrufer AUSSERHALB von ``_add_quick_select``: ein Einstieg, der nur
    die Schnellwahl bedient, laesst genau die Aufrufer draussen, die spaeter
    falsch abbiegen (Nutzlast (ii) — absolute Farbwerte auf EINEM Kanal)."""

    def test_regler_traegt_nur_geraete_mit_dieser_farbe(self):
        self._patch(1, "SPIDER14", 14)     # RGBW
        self._patch(2, "MH8", 8)           # kein RGB
        v = self._view([1, 2])
        rot = [s for s in v.findChildren(AttributeSlider)
               if getattr(s._channel, "attribute", "") == "color_r"]
        self.assertTrue(rot, "kein Rot-Regler gebaut — nichts zu messen")
        self.assertEqual(self._fids(rot[0]), (1,),
                         "der MH8 hat keinen color_r-Kanal")


class GleicheGrenzenAberANDERESKindTest(_Basis):
    """★ Zur ueberlebenden Mutation "range_signature ignoriert ``kind``".

    Zwei Kanaele koennen DIESELBEN Bereichsgrenzen und trotzdem eine voellig
    andere Bedeutung haben — dann sagt allein ``kind``, dass sie unvertraeglich
    sind. Gemessen an mitgelieferten Profilen:

    * ``KLEINCONTI [7-Kanal]`` "Strobe": 0–0 ``open`` / 1–255 ``strobe``
    * ``L2600LASER [6-Kanal]`` "Laser An/Aus": 0–0 ``closed`` / 1–255 ``open``

    Gleiche Grenzen, gegenteilige Bedeutung: eine Strobe-Kachel der Vorlage
    wuerde am Laser die Ausgabe schalten. Unter den mitgelieferten Profilen
    gibt es 11 solche Shutter-Paare, in der Bibliothek dieses Rechners 53031
    (Shutter), 13530 (Farbrad), 2506 (Gobo) und 609 (Reset)."""

    def setUp(self):
        super().setUp()
        self._patch(1, "KLEINCONTI", 7)
        self._patch(2, "L2600LASER", 6)

    def test_vorbedingung_gleiche_grenzen_verschiedene_kinds(self):
        a, b = self._kanal(1, "shutter"), self._kanal(2, "shutter")
        grenzen = lambda ch: sorted(                            # noqa: E731
            (int(r.range_from), int(r.range_to)) for r in ch.ranges)
        self.assertEqual(grenzen(a), grenzen(b),
                         "verschiedene Grenzen — dann misst dieser Test nicht "
                         "die kind-Unterscheidung, sondern die Grenzen")
        self.assertNotEqual(range_signature(a), range_signature(b),
                            "nur das kind unterscheidet die beiden")

    def test_shutter_reihe_trennt_allein_am_kind(self):
        bars = self._view([1, 2]).findChildren(ShutterQuickBar)
        self.assertEqual(len(bars), 1)
        self.assertEqual(self._fids(bars[0]), (1,),
                         "am L2600LASER schaltet derselbe DMX-Wert die Ausgabe "
                         "statt einen Strobe — er gehoert nicht an die "
                         "Strobe-Kacheln der KLEINCONTI-Vorlage")


# ══ 4. Der Einstieg selbst: ohne Entscheidung geht nichts ═══════════════════

class _KanalStub:
    def __init__(self, attribute, ranges=()):
        self.attribute = attribute
        self.ranges = list(ranges)


class _BereichStub:
    def __init__(self, a, b, kind=""):
        self.range_from, self.range_to, self.kind = a, b, kind


class EinstiegVerlangtEineEntscheidungTest(unittest.TestCase):
    """"Eine neue Reihe kann ohne Entscheidung nicht gebaut werden": die
    Nutzlast ist positionell, und ein ``ziel``, das nicht zu ihr passt, ist ein
    Fehler statt eines stillen Sonderfalls."""

    def test_es_gibt_genau_drei_nutzlast_arten(self):
        self.assertEqual(
            [n.name for n in Nutzlast],
            ["LITERAL_AUS_VORLAGEN_BEREICH", "ABSOLUTWERT_EIN_KANAL",
             "ABSOLUTWERTE_KANALMENGE"])

    def test_ohne_nutzlast_gibt_es_keine_liste(self):
        with self.assertRaises(TypeError):
            fixtures_fuer_nutzlast([], "speed")      # noqa: E1120 (Absicht)

    def test_string_statt_nutzlast_ist_ein_fehler(self):
        """★ Das ``ziel`` ist hier absichtlich GUELTIG (ein Vorlagen-Kanal).

        Mit ``"speed"`` als ziel bestand dieser Test auch dann noch, wenn die
        Nutzlast-Pruefung ganz entfaellt — er waere dann an der ziel-Pruefung
        haengengeblieben und haette seinen Gegenstand nie erreicht. Genau diese
        Mutation hat in der ersten Mutationsprobe ueberlebt."""
        with self.assertRaises(ValueError):
            fixtures_fuer_nutzlast("literal_aus_vorlagen_bereich", [],
                                   _KanalStub("reset"))

    def test_vorlagen_bereich_ohne_vorlagen_kanal_ist_ein_fehler(self):
        with self.assertRaises(ValueError):
            fixtures_fuer_nutzlast(
                Nutzlast.LITERAL_AUS_VORLAGEN_BEREICH, [], "reset")

    def test_ein_kanal_mit_kanalmenge_ist_ein_fehler(self):
        with self.assertRaises(ValueError):
            fixtures_fuer_nutzlast(
                Nutzlast.ABSOLUTWERT_EIN_KANAL, [], ("color_r", "color_g"))

    def test_kanalmenge_mit_einzelnem_string_ist_ein_fehler(self):
        with self.assertRaises(ValueError):
            fixtures_fuer_nutzlast(
                Nutzlast.ABSOLUTWERTE_KANALMENGE, [], "color_r")

    def test_leere_kanalmenge_ist_ein_fehler(self):
        with self.assertRaises(ValueError):
            fixtures_fuer_nutzlast(Nutzlast.ABSOLUTWERTE_KANALMENGE, [], ())

    def test_ein_kanal_und_einelementige_menge_antworten_gleich(self):
        """Regel 'eine Frage, eine Stelle': (ii) ist (iii) mit einer
        einelementigen Menge und darf nie anders antworten."""
        a, b = object(), object()
        kan = {id(a): [_KanalStub("speed")], id(b): [_KanalStub("pan")]}
        hole = lambda f: kan[id(f)]                             # noqa: E731
        self.assertEqual(
            fixtures_fuer_nutzlast(Nutzlast.ABSOLUTWERT_EIN_KANAL,
                                   [a, b], "speed", hole),
            fixtures_fuer_nutzlast(Nutzlast.ABSOLUTWERTE_KANALMENGE,
                                   [a, b], ("speed",), hole))

    def test_unlesbare_kanaele_werfen_ein_geraet_NICHT_heraus(self):
        """⚠️ Der ``except``-Rueckfall auf 1 ist Absicht: 'nicht messbar' darf
        kein Geraet aus dem Bestandspfad werfen (sonst verschwaende ein Regler
        genau dann, wenn etwas schiefgeht)."""
        def kaputt(_f):
            raise RuntimeError("Kanaele nicht lesbar")
        self.assertEqual(attr_head_count(object(), "speed", kaputt), 1)
        self.assertEqual(
            len(fixtures_fuer_nutzlast(Nutzlast.ABSOLUTWERT_EIN_KANAL,
                                       [object()], "speed", kaputt)), 1)

    def test_vorlagen_bereich_ist_strikt_staerker_als_kanal_existenz(self):
        """Ohne den Kanal ist ``ch is None`` — die Range-Regel deckt FM-34 mit
        ab. Und mit gleichem Layout wirft sie NICHTS weg."""
        tpl = _KanalStub("reset", [_BereichStub(0, 149, ""),
                                   _BereichStub(150, 255, "reset")])
        gleich = object()
        fremd = object()
        ohne = object()
        kan = {id(gleich): [_KanalStub("reset", [_BereichStub(0, 149, ""),
                                                 _BereichStub(150, 255, "reset")])],
               id(fremd): [_KanalStub("reset", [_BereichStub(0, 255, "reset")])],
               id(ohne): [_KanalStub("intensity")]}
        hole = lambda f: kan[id(f)]                             # noqa: E731
        out = fixtures_fuer_nutzlast(Nutzlast.LITERAL_AUS_VORLAGEN_BEREICH,
                                     [gleich, fremd, ohne], tpl, hole)
        self.assertEqual(out, [gleich])


# ══ 5. Kein zweiter Weg an dem Einstieg vorbei ═════════════════════════════

def _nutzlast_aufrufe(func) -> list:
    """Die ``self._fixtures_fuer``-Aufrufe im Quelltext dieser Methode, in
    Quelltext-Reihenfolge, als Namen der uebergebenen Nutzlast."""
    baum = ast.parse(textwrap.dedent(inspect.getsource(func)))
    out = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        f = knoten.func
        if (isinstance(f, ast.Attribute) and f.attr == "_fixtures_fuer"
                and isinstance(f.value, ast.Name) and f.value.id == "self"):
            arg = knoten.args[0] if knoten.args else None
            out.append(arg.attr if (isinstance(arg, ast.Attribute)
                                    and isinstance(arg.value, ast.Name)
                                    and arg.value.id == "Nutzlast") else None)
    return out


class KeinZweiterWegTest(unittest.TestCase):
    """⚠️ Regel: 'gibt es einen ZWEITEN WEG, der die Regel umgeht?' — genau das
    war UI-53. Diese Tests halten die Zuordnung Reihe -> Nutzlast fest."""

    def test_alle_sechs_reihen_in_add_quick_select_nennen_ihre_nutzlast(self):
        got = _nutzlast_aufrufe(ProgrammerView._add_quick_select)
        self.assertEqual(
            got,
            ["LITERAL_AUS_VORLAGEN_BEREICH",     # Shutter
             "ABSOLUTWERTE_KANALMENGE",          # RGB-Kacheln
             "LITERAL_AUS_VORLAGEN_BEREICH",     # Farbrad
             "LITERAL_AUS_VORLAGEN_BEREICH",     # Gobo
             "ABSOLUTWERT_EIN_KANAL",            # Pan/Tilt-Speed
             "LITERAL_AUS_VORLAGEN_BEREICH"],    # Reset
            "jede Reihe muss ihre Geraeteliste ueber _fixtures_fuer mit einer "
            "ausdruecklich benannten Nutzlast bekommen")

    def test_die_siebte_reihe_die_orientierungsleiste_ebenso(self):
        self.assertEqual(_nutzlast_aufrufe(ProgrammerView._build_orientation_bar),
                         ["ABSOLUTWERTE_KANALMENGE"])

    def test_add_quick_select_filtert_nirgends_selbst(self):
        """Keine Reihe darf sich ihre Liste noch einmal selbst zusammensuchen."""
        quelle = inspect.getsource(ProgrammerView._add_quick_select)
        for verboten in ("get_channels_for_patched", "_attr_head_count",
                         "range_signature", "_range_compatible_fixtures"):
            self.assertNotIn(verboten, quelle,
                             f"{verboten} in _add_quick_select — das ist eine "
                             f"zweite Fassung derselben Frage")

    def test_die_alten_fassungen_gibt_es_nicht_mehr(self):
        for alt in ("_fixtures_with_attr", "_fixtures_with_any_attr"):
            self.assertFalse(hasattr(ProgrammerView, alt),
                             f"{alt} lebt noch — dann kann eine neue Reihe "
                             f"weiter an dem Einstieg vorbeigreifen")

    def test_der_bestandsname_antwortet_identisch(self):
        """``_range_compatible_fixtures`` bleibt als Name (UI-07-Tests), rechnet
        aber nichts mehr selbst — beide Namen muessen dieselbe Liste liefern."""
        tpl = _KanalStub("gobo_wheel", [_BereichStub(0, 15, "open"),
                                        _BereichStub(16, 255, "gobo")])
        gleich, fremd = object(), object()
        kan = {id(gleich): [_KanalStub("gobo_wheel", [_BereichStub(0, 15, "open"),
                                                      _BereichStub(16, 255, "gobo")])],
               id(fremd): [_KanalStub("gobo_wheel", [_BereichStub(0, 255, "gobo")])]}
        _app()
        v = ProgrammerView()
        try:
            orig = pv_mod.get_channels_for_patched
            pv_mod.get_channels_for_patched = lambda f: kan[id(f)]
            try:
                a = v._range_compatible_fixtures(tpl, [gleich, fremd])
                b = v._fixtures_fuer(Nutzlast.LITERAL_AUS_VORLAGEN_BEREICH,
                                     [gleich, fremd], tpl)
            finally:
                pv_mod.get_channels_for_patched = orig
            self.assertEqual(a, b)
            self.assertEqual(a, [gleich])
        finally:
            v.deleteLater()


if __name__ == "__main__":
    unittest.main()


class DerVerlustWirdBENANNTTest(unittest.TestCase):
    """★★★ Vom Bedien-Skeptiker erzwungen.

    Die Range-Regel ist richtig — ein fremdes Reset-Layout bekaeme den
    Vorlagenwert in einen semantisch anderen Bereich. Aber sie verkleinert die
    Auswahl, und der Bestaetigungsdialog versprach das Gegenteil: „die
    AUSGEWAEHLTEN Moving Heads fahren in ihre Home-Position", ohne Zahl und
    ohne Liste.

    Betriebsfolge, gemessen am Wortlaut: der Bediener waehlt acht Mover,
    bestaetigt einen Dialog, der ihm ALLE zusagt — und vier fahren nicht.
    Waehrend einer Show ist das nicht von einem haengenden Geraet oder einer
    toten DMX-Strecke zu unterscheiden. *Wer eine Auswahl verkleinert, muss es
    sagen.*
    """

    def _dialogtext(self, anzahl_traegt: int, uebergangen: int) -> str:
        from unittest import mock
        from types import SimpleNamespace
        from src.ui.widgets import preset_tile
        kanal = SimpleNamespace(
            attribute="reset", default_value=0,
            ranges=[SimpleNamespace(range_from=0, range_to=255,
                                    name="Reset", kind="reset")])
        gesehen = {}

        def _frage(_parent, _titel, text, *a, **k):
            gesehen["text"] = text
            return preset_tile.QMessageBox.StandardButton.No

        knopf = preset_tile.ResetActionButton(
            kanal, [object()] * anzahl_traegt, None,
            uebergangen=uebergangen)
        with mock.patch.object(preset_tile.QMessageBox, "question", _frage):
            knopf._on_clicked()
        self.assertIn("text", gesehen, "der Dialog wurde gar nicht gezeigt")
        return gesehen["text"]

    def test_der_dialog_nennt_die_zahl_wenn_geraete_wegfallen(self):
        text = self._dialogtext(anzahl_traegt=4, uebergangen=4)
        self.assertIn("4 von 8", text, f"keine Zahl im Dialog: {text!r}")
        self.assertIn("unberührt", text)

    def test_der_dialog_sagt_auch_WARUM(self):
        """Eine Zahl ohne Grund liest sich wie ein Fehler der Software."""
        text = self._dialogtext(anzahl_traegt=1, uebergangen=3)
        self.assertIn("bedeutet derselbe DMX-Wert etwas anderes", text)

    def test_einzahl_und_mehrzahl_stimmen(self):
        einer = self._dialogtext(anzahl_traegt=3, uebergangen=1)
        self.assertIn("1 Gerät bleibt unberührt", einer)
        mehrere = self._dialogtext(anzahl_traegt=3, uebergangen=2)
        self.assertIn("2 Geräte bleiben unberührt", mehrere)

    def test_ohne_verlust_bleibt_der_text_wie_bisher(self):
        """★★ Gegenprobe: eine Anzeige, die immer etwas meldet, meldet nichts.
        Faellt kein Geraet weg, darf auch keine Zahl erscheinen."""
        text = self._dialogtext(anzahl_traegt=5, uebergangen=0)
        self.assertIn("Die ausgewählten Moving Heads", text)
        self.assertNotIn("unberührt", text)
        self.assertNotIn("von", text.split("Home-Position")[0])
