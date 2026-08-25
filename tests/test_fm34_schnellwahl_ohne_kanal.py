"""FM-34 — Schnellwahl-Farbkacheln und der Reset-Knopf fassten Geraete an, die
den Kanal gar nicht haben.

Dieselbe stille Klasse wie FM-9/A5: der Wert landet im Programmer-Dict und
**nirgends** auf DMX. In #663 sind der Pan/Tilt-Speed-Regler und die
Grundfarben-Regler auf ``ProgrammerView._fixtures_with_attr`` umgestellt worden
— zwei Schnellwahl-Widgets bekamen ihre Fixture-Liste weiter ungefiltert:

* ``ColorQuickBar`` traegt ZWEI Kachelfamilien, die verschiedene Kanaele
  schreiben: die RGB-Presets (``color_r/g/b/w``) und die Farbrad-Slots
  (``color_wheel``). Beide bekamen dieselbe, ungefilterte Liste. In der
  Auswahl ``Robin Spiider [91-Kanal Pixel]`` + ``Sharpy (Beam 16ch)`` hat der
  Spiider RGB und kein Farbrad, der SHARPY ein Farbrad und kein RGB — jede
  Kachel traf also genau EIN Geraet richtig und eines gar nicht.
* ``ResetActionButton`` bekam ebenfalls beide, obwohl nur der SHARPY einen
  ``reset``-Kanal hat. Der Knopf verspricht eine Rekalibrierung; am Spiider
  fuehrt sie kein Kanal aus.

★ **Gemessen wird am DMX-Ausgang**, nicht am Programmer-Dict: genau das Fehlen
einer DMX-Wirkung ist der Befund, ein fehlender Dict-Eintrag waere kein
Nachweis. Der Dict-Eintrag wird zusaetzlich geprueft, weil die Zusage aus dem
BACKLOG „weder DMX noch Programmer-Eintrag" lautet — ein stiller Eintrag
laesst sich spaeter in Szenen/Snaps mitspeichern.

★ **Gemessen ueber den echten Bauweg**: echte Builtin-Profile patchen,
``ProgrammerView`` bauen, ueber ``set_selected_cells`` auswaehlen, das gebaute
Widget aus dem Baum holen und die Kachel per ``QTest.mouseClick`` wirklich
anklicken. Kein direkter Aufruf von ``_apply_payload``.

Positivkontrollen (ein Waechter, der alles beanstandet, wird abgeschaltet):

* ``Robin Spiider`` + ``LED Moving Bar 4×`` — BEIDE haben RGB. Nach demselben
  Klick muessen BEIDE ihre Rot-Kanaele auf DMX geaendert haben, und die Bar
  traegt unveraendert beide Geraete.
* Zwei ``SHARPY`` — BEIDE haben Farbrad und Reset. Farbrad-Kachel und
  Reset-Knopf muessen unveraendert beide treiben.
* Der SHARPY behaelt seine Farbrad-Kacheln, der Spiider seine RGB-Kacheln —
  der Filter darf keine gueltigen Ziele wegwerfen.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox            # noqa: E402
from PySide6.QtTest import QTest                                    # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_channels_for_patched, get_state  # noqa: E402
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import (FixtureMode, FixtureProfile,  # noqa: E402
                                      PatchedFixture)
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.views.programmer_view import ProgrammerView             # noqa: E402
from src.ui.widgets.preset_tile import (ColorQuickBar, PresetTile,  # noqa: E402
                                        ResetActionButton)

RGB_ATTRS = ("color_r", "color_g", "color_b", "color_w")


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
    """Echte Profile patchen, echte View bauen, DMX lesen — wie
    ``test_fm27_fm28_fm29_kopf_zaehlung`` es fuer die Regler vormacht."""

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

    def _attrs(self, fid: int) -> set:
        return {(c.attribute or "") for c in get_channels_for_patched(self._fx(fid))}

    # ── Bestands-Wache: das Profil muss den Kanal wirklich (nicht) haben ───
    def _hat(self, fid: int, *attrs: str):
        vorhanden = self._attrs(fid)
        for a in attrs:
            self.assertIn(a, vorhanden,
                          f"fid {fid} muss {a} haben, sonst misst der Test nichts")

    def _hat_nicht(self, fid: int, *attrs: str):
        vorhanden = self._attrs(fid)
        for a in attrs:
            self.assertNotIn(a, vorhanden,
                             f"fid {fid} darf {a} NICHT haben — sonst gibt es "
                             f"den Befund an diesem Geraet gar nicht")

    # ── Widgets ueber den echten Bauweg ────────────────────────────────────
    def _view(self, cells):
        """Frische View je Messung, sonst liefert ``findChildren`` auch die
        Widgets frueherer Auswahlen."""
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        self.state.set_selected_cells(list(cells))
        _app().processEvents()
        return v

    def _color_bars(self, cells) -> list:
        return self._view(cells).findChildren(ColorQuickBar)

    def _eine_bar(self, cells) -> ColorQuickBar:
        bars = self._color_bars(cells)
        self.assertEqual(len(bars), 1,
                         f"genau eine ColorQuickBar erwartet, gebaut: {len(bars)}")
        return bars[0]

    @staticmethod
    def _fids(widget) -> tuple:
        return tuple(f.fid for f in widget._fixtures)

    @staticmethod
    def _kacheln(bar: ColorQuickBar, attrs) -> list:
        """Kacheln, deren Nutzlast eines dieser Attribute schreibt."""
        return [t for t in bar.findChildren(PresetTile)
                if isinstance(t._payload, dict)
                and any(a in t._payload for a in attrs)]

    # ── DMX ───────────────────────────────────────────────────────────────
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

    def _klick(self, widget, fids) -> dict:
        """Wirklich klicken (``QTest.mouseClick`` -> ``mousePressEvent``) und
        zurueckgeben, welche DMX-Kanaele und welche Programmer-Eintraege sich je
        Geraet dadurch geaendert haben."""
        fids = tuple(fids)
        self._grundstellung(*fids)
        vor_dmx = {fid: self._dmx(fid) for fid in fids}
        vor_prog = {fid: self._prog(fid) for fid in fids}
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


class ProfileTragenDenBefundTest(_Basis):
    """Wache gegen Leerlauf: ohne diese Kanal-Verteilung misst der Rest nichts."""

    def test_spiider_hat_rgb_ohne_farbrad_und_ohne_reset(self):
        self._patch(2, "SPIIDER", 91)
        self._hat(2, "color_r", "color_g", "color_b")
        self._hat_nicht(2, "color_wheel", "reset")

    def test_sharpy_hat_farbrad_und_reset_ohne_rgb(self):
        self._patch(3, "SHARPY", 16)
        self._hat(3, "color_wheel", "reset")
        self._hat_nicht(3, *RGB_ATTRS)

    def test_movbar_hat_rgb(self):
        self._patch(4, "MOVBAR4", 22)
        self._hat(4, "color_r", "color_g", "color_b")


class FarbkachelTrifftNurRgbGeraeteTest(_Basis):
    """Der gemeldete Befund: ``DMX-Diff SHARPY: {}``."""

    def _auswahl(self):
        self._patch(2, "SPIIDER", 91)
        self._patch(3, "SHARPY", 16)
        return self._eine_bar(["2", "3"])

    def test_bar_traegt_den_sharpy_nicht_mehr(self):
        bar = self._auswahl()
        self.assertEqual(self._fids(bar), (2,),
                         "der SHARPY hat kein RGB und gehoert nicht an die "
                         "Farbkacheln")

    def test_klick_laesst_den_sharpy_unberuehrt(self):
        """★★ Der Kern: weder ein DMX-Kanal noch ein Programmer-Eintrag."""
        bar = self._auswahl()
        kacheln = self._kacheln(bar, RGB_ATTRS)
        self.assertTrue(kacheln, "keine RGB-Kachel gebaut — nichts zu messen")
        dmx, prog = self._klick(kacheln[1], (2, 3))[3]
        self.assertEqual(dmx, {}, "der SHARPY hat keinen RGB-Kanal — ein Klick "
                                  "darf dort nichts bewegen")
        self.assertEqual(prog, {}, "…und auch keinen stillen Dict-Eintrag "
                                   "hinterlassen (landet sonst in Szenen/Snaps)")

    def test_klick_trifft_den_spiider_weiterhin(self):
        """Positivkontrolle im selben Klick: das Geraet MIT dem Kanal wird
        getroffen."""
        bar = self._auswahl()
        kacheln = self._kacheln(bar, RGB_ATTRS)
        dmx, _prog = self._klick(kacheln[1], (2, 3))[2]
        self.assertTrue(dmx, "der Spiider bewegt gar keinen Kanal mehr")
        self.assertTrue(
            any("Rot" in name for name in dmx),
            f"kein Rot-Kanal des Spiiders geaendert, geaendert: {sorted(dmx)}")


class FarbradKachelTrifftNurRadGeraeteTest(_Basis):
    """Die zweite Kachelfamilie derselben Bar — sie schreibt einen ANDEREN
    Kanal und braucht deshalb eine eigene Liste."""

    def _auswahl(self):
        self._patch(2, "SPIIDER", 91)
        self._patch(3, "SHARPY", 16)
        return self._eine_bar(["2", "3"])

    def test_farbrad_kacheln_gehen_an_den_sharpy(self):
        bar = self._auswahl()
        self.assertEqual(tuple(f.fid for f in bar._wheel_fixtures), (3,))

    def test_klick_aufs_farbrad_laesst_den_spiider_unberuehrt(self):
        bar = self._auswahl()
        kacheln = self._kacheln(bar, ("color_wheel",))
        self.assertTrue(kacheln, "keine Farbrad-Kachel gebaut — nichts zu messen")
        erg = self._klick(kacheln[0], (2, 3))
        self.assertEqual(erg[2], ({}, {}),
                         "der Spiider hat kein Farbrad")
        dmx, _prog = erg[3]
        self.assertTrue(dmx, "der SHARPY muss sein Farbrad weiterhin drehen")


class FarbradNurRangeKompatibleTest(_Basis):
    """★ Die Farbrad-Kacheln sind RANGE-basiert wie Shutter und Gobo: die Kachel
    traegt den Mittelwert eines Bereichs der VORLAGE, nicht eine absolute Farbe.
    „Hat den Kanal" ist deshalb die falsche Frage — zwei Farbraeder mit
    verschiedenem Slot-Layout bekaemen denselben Literal-Wert und zeigten
    VERSCHIEDENE Farben. Gefiltert wird darum wie bei Shutter/Gobo ueber
    ``_range_compatible_fixtures`` (UI-07), das den fehlenden Kanal mit
    erschlaegt (``ch is None``).

    Gemessen an ``SHARPY`` (16ch, 16 Slots, Rot 7–14) neben ``MH8`` (8ch,
    9 Slots, 0–15 = Weiss/Offen): DMX 10 heisst am einen Rot, am anderen Offen.
    """

    def _auswahl(self):
        self._patch(3, "SHARPY", 16)
        self._patch(5, "MH8", 8)
        return self._eine_bar(["3", "5"])

    def _wheel_channel(self, fid):
        return next(c for c in get_channels_for_patched(self._fx(fid))
                    if c.attribute == "color_wheel")

    def test_beide_haben_ein_farbrad_mit_VERSCHIEDENEM_layout(self):
        """Wache gegen Leerlauf: ohne diesen Unterschied misst der Rest nichts."""
        self._patch(3, "SHARPY", 16)
        self._patch(5, "MH8", 8)
        self._hat(3, "color_wheel")
        self._hat(5, "color_wheel")
        sig = ProgrammerView._range_signature
        self.assertNotEqual(sig(self._wheel_channel(3)),
                            sig(self._wheel_channel(5)),
                            "gleiche Slot-Layouts — dann gibt es den Befund "
                            "an diesem Paar gar nicht")

    def test_bar_traegt_das_fremde_farbrad_nicht(self):
        bar = self._auswahl()
        self.assertEqual(tuple(f.fid for f in bar._wheel_fixtures), (3,),
                         "der MH8 hat ein ANDERES Slot-Layout und darf nicht "
                         "an die Kacheln der SHARPY-Vorlage")

    def test_klick_laesst_das_fremde_farbrad_unberuehrt(self):
        """★★ Der Kern: der Nutzer klickt „Rot" — am MH8 laege derselbe
        DMX-Wert im Bereich „Weiss / Offen"."""
        bar = self._auswahl()
        kacheln = self._kacheln(bar, ("color_wheel",))
        self.assertTrue(kacheln, "keine Farbrad-Kachel gebaut — nichts zu messen")
        ziel = kacheln[1]
        wert = ziel._payload["color_wheel"]
        erg = self._klick(ziel, (3, 5))
        self.assertEqual(erg[5], ({}, {}),
                         "der MH8 wuerde bei diesem Wert eine andere Farbe "
                         "zeigen als die Kachel verspricht")
        dmx, _prog = erg[3]
        self.assertEqual(sorted(dmx.values()), [wert],
                         f"der SHARPY (die Vorlage) muss {wert} bekommen, "
                         f"geaendert: {dmx}")


class KachelSchreibtNurVorhandeneKanaeleTest(_Basis):
    """★ Der Geraete-Filter fragt „hat EINEN der Farbkanaele" — die Nutzlast
    schreibt aber MEHRERE auf einmal. Deshalb wird beim Anwenden jeder
    Schluessel noch einmal gegen die Kanaele DIESES Geraets geprueft
    (``_apply_payload_on``), sonst bleibt die Klasse FM-9/A5 im Kleinen stehen.

    Gemessen an der Kachel „Aus": sie traegt zusaetzlich ``color_a`` und
    ``color_uv``; der Spiider hat beide nicht.

    ★ Warum nicht an einem Teil-RGB-Geraet gemessen: unter den mitgelieferten
    Profilen gibt es KEINS (0 von 94) — nur in einer importierten Bibliothek
    (dort 43 Modi). Ein Test darauf haette in der CI nichts zu messen (QA-61).
    Die Kachel „Aus" ist derselbe Mechanismus an einem Builtin-Geraet.
    """

    def _bar_und_kachel(self):
        self._patch(2, "SPIIDER", 91)
        self._hat(2, "color_r", "color_g", "color_b", "color_w")
        self._hat_nicht(2, "color_a", "color_uv")
        bar = self._eine_bar(["2"])
        kacheln = self._kacheln(bar, ("color_a",))
        self.assertEqual(len(kacheln), 1,
                         "genau eine Kachel traegt color_a ('Aus')")
        return bar, kacheln[0]

    def test_aus_kachel_hinterlaesst_keine_toten_eintraege(self):
        bar, aus = self._bar_und_kachel()
        self.assertIn("color_uv", aus._payload,
                      "die Kachel muss die fehlenden Kanaele wirklich tragen")
        _dmx, prog = self._klick(aus, (2,))[2]
        ohne_kanal = sorted(k for k in prog if k not in self._attrs(2))
        self.assertEqual(ohne_kanal, [],
                         "Wert im Programmer-Dict, nichts auf DMX — genau die "
                         "Klasse, die FM-34 beseitigen soll (wandert in "
                         "Szenen/Snaps mit)")

    def test_die_vorhandenen_kanaele_kommen_weiterhin_an(self):
        """Positivkontrolle: der Filter darf nicht die ganze Nutzlast fressen.
        Erst faerben, dann „Aus" — so ist die Ruecknahme auf DMX sichtbar."""
        bar, aus = self._bar_und_kachel()
        farbe = self._kacheln(bar, RGB_ATTRS)[5]      # 'Cyan' — g/b auf 255
        self._klick(farbe, (2,))
        dmx, _prog = self._klick(aus, (2,))[2]
        self.assertTrue(dmx, "der Spiider bewegt gar keinen Kanal mehr")
        self.assertEqual({v for v in dmx.values()}, {0},
                         f"'Aus' muss die Farbkanaele auf 0 ziehen: {dmx}")
        stand = self._prog(2)
        for attr in ("color_r", "color_g", "color_b", "color_w"):
            self.assertEqual(stand.get(attr), 0,
                             f"{attr} hat einen Kanal und muss ankommen, "
                             f"Stand: {stand}")


class ResetKnopfTrifftNurResetGeraeteTest(_Basis):
    """Der Reset-Knopf verspricht eine Rekalibrierung — an einem Geraet ohne
    ``reset``-Kanal fuehrt sie niemand aus."""

    def _knoepfe(self, cells) -> list:
        return self._view(cells).findChildren(ResetActionButton)

    def test_knopf_traegt_den_spiider_nicht_mehr(self):
        self._patch(2, "SPIIDER", 91)
        self._patch(3, "SHARPY", 16)
        knoepfe = self._knoepfe(["2", "3"])
        self.assertEqual(len(knoepfe), 1, "genau ein Reset-Knopf erwartet")
        self.assertEqual(self._fids(knoepfe[0]), (3,))

    def test_klick_bewegt_nur_den_sharpy(self):
        self._patch(2, "SPIIDER", 91)
        self._patch(3, "SHARPY", 16)
        knopf = self._knoepfe(["2", "3"])[0]
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            erg = self._klick(knopf, (2, 3))
        self.assertEqual(erg[2], ({}, {}), "der Spiider hat keinen reset-Kanal")
        dmx, _prog = erg[3]
        self.assertIn("Reset", dmx, "der SHARPY muss seinen Reset-Kanal sehen")

    def test_ohne_reset_geraet_gibt_es_gar_keinen_knopf(self):
        """Bestand, nicht Fix: ein Geraet ohne ``reset`` bekam auch vorher
        schon keinen Knopf — die Vorlage ist die UNION der Auswahl, also fehlt
        dort ``reset`` ganz.

        ★ Ehrlich dazugesagt: der Waechter ``if rs_fixtures:`` im Produktivcode
        ist deshalb heute ueber die Oberflaeche NICHT ausloesbar (er kann nur
        greifen, wenn ein Geraet den Kanal laut Vorlage hat und laut
        Kopfzaehlung nicht). Er steht dort in derselben Form wie in #663
        („bleibt kein Geraet uebrig, entsteht der Regler gar nicht") — dieser
        Test macht ihn nicht rot, er haelt nur fest, dass der Filter keinen
        Knopf ERFINDET, wo vorher keiner war."""
        self._patch(2, "SPIIDER", 91)
        self.assertEqual(self._knoepfe(["2"]), [])

    def test_positivkontrolle_zwei_sharpys(self):
        """Eine Auswahl, in der ALLE den Kanal haben, verhaelt sich
        unveraendert."""
        self._patch(3, "SHARPY", 16)
        self._patch(4, "SHARPY", 16)
        knoepfe = self._knoepfe(["3", "4"])
        self.assertEqual(len(knoepfe), 1)
        self.assertEqual(self._fids(knoepfe[0]), (3, 4))
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            erg = self._klick(knoepfe[0], (3, 4))
        for fid in (3, 4):
            self.assertIn("Reset", erg[fid][0], f"fid {fid} ohne Reset-Wirkung")


class PositivkontrolleAlleHabenDenKanalTest(_Basis):
    """Der Filter darf keine gueltigen Ziele wegwerfen."""

    def test_zwei_rgb_geraete_werden_beide_getroffen(self):
        """``Robin Spiider`` + ``LED Moving Bar 4×`` — beide mit RGB."""
        self._patch(2, "SPIIDER", 91)
        self._patch(4, "MOVBAR4", 22)
        bar = self._eine_bar(["2", "4"])
        self.assertEqual(self._fids(bar), (2, 4),
                         "beide haben RGB — die Bar muss beide tragen")
        kacheln = self._kacheln(bar, RGB_ATTRS)
        erg = self._klick(kacheln[1], (2, 4))
        for fid in (2, 4):
            dmx = erg[fid][0]
            self.assertTrue(dmx, f"fid {fid} bewegt keinen Kanal")
            self.assertTrue(
                any("Rot" in name for name in dmx),
                f"fid {fid} muss einen Rot-Kanal aendern, geaendert: "
                f"{sorted(dmx)}")

    def test_zwei_farbrad_geraete_werden_beide_getroffen(self):
        self._patch(3, "SHARPY", 16)
        self._patch(4, "SHARPY", 16)
        bar = self._eine_bar(["3", "4"])
        self.assertEqual(tuple(f.fid for f in bar._wheel_fixtures), (3, 4))
        kacheln = self._kacheln(bar, ("color_wheel",))
        wert = kacheln[0]._payload["color_wheel"]
        erg = self._klick(kacheln[0], (3, 4))
        for fid in (3, 4):
            self.assertTrue(erg[fid][0], f"fid {fid} dreht sein Farbrad nicht")
            # ★ Nicht nur DASS sich etwas bewegt, sondern WELCHER Wert ankommt:
            # bei gleichem Slot-Layout muss beiden derselbe Bereich zugehen.
            self.assertEqual(sorted(erg[fid][0].values()), [wert],
                             f"fid {fid} bekam nicht den Kachel-Wert {wert}, "
                             f"sondern {erg[fid][0]}")

    def test_reines_rgb_geraet_behaelt_seine_kacheln(self):
        self._patch(2, "SPIIDER", 91)
        bar = self._eine_bar(["2"])
        self.assertEqual(self._fids(bar), (2,))
        self.assertTrue(self._kacheln(bar, RGB_ATTRS),
                        "die RGB-Kacheln duerfen nicht verschwinden")

    def test_reines_farbrad_geraet_behaelt_seine_kacheln(self):
        self._patch(3, "SHARPY", 16)
        bar = self._eine_bar(["3"])
        self.assertEqual(self._fids(bar), (),
                         "kein RGB-Geraet in der Auswahl")
        self.assertEqual(self._kacheln(bar, RGB_ATTRS), [],
                         "ohne RGB-Geraet duerfen gar keine RGB-Kacheln "
                         "entstehen")
        self.assertTrue(self._kacheln(bar, ("color_wheel",)),
                        "die Farbrad-Kacheln duerfen nicht verschwinden")


class WidgetVertragTest(_Basis):
    """Der Vertrag der ``ColorQuickBar`` selbst — hier bewusst OHNE den
    ProgrammerView gemessen.

    ★ Warum eine Ausnahme vom „echten Weg": ueber die Oberflaeche kann eine der
    beiden Listen heute nicht leer sein, waehrend ihre Attribute in der Vorlage
    stehen — die Vorlage IST die Union der Auswahl. Die leere Liste ist damit
    kein erreichbarer Nutzerschaden, sondern die Zusage der neuen Schnittstelle
    an ihre Aufrufer: „leere Liste heisst keine Kacheln, nicht Kacheln ins
    Leere". Ohne diesen Test stuende sie ungemessen da."""

    def test_leere_rgb_liste_baut_keine_rgb_kacheln(self):
        self._patch(3, "SHARPY", 16)
        bar = ColorQuickBar([], self.state, {"color_r", "color_g", "color_b"})
        self.addCleanup(bar.deleteLater)
        self.assertEqual(self._kacheln(bar, RGB_ATTRS), [])

    def test_leere_farbrad_liste_baut_keine_farbrad_kacheln(self):
        fx = self._patch(3, "SHARPY", 16)
        cw = next(c for c in get_channels_for_patched(fx)
                  if c.attribute == "color_wheel")
        voll = ColorQuickBar([fx], self.state, set(), cw, wheel_fixtures=[fx])
        self.addCleanup(voll.deleteLater)
        self.assertTrue(self._kacheln(voll, ("color_wheel",)),
                        "mit Geraet muessen Farbrad-Kacheln entstehen — sonst "
                        "misst der Gegenfall nichts")
        leer = ColorQuickBar([fx], self.state, set(), cw, wheel_fixtures=[])
        self.addCleanup(leer.deleteLater)
        self.assertEqual(self._kacheln(leer, ("color_wheel",)), [])


if __name__ == "__main__":
    unittest.main()
