"""FM-21 — die Pixel-Reihenfolge: wo sie wirkt, wo nicht, und was der Dialog sagt.

Die Falle, um die es geht: wer im Patch-Dialog auf „Schlangenlinien" stellt,
sieht die 3D-Vorschau umspringen und schliesst daraus, die Sache sei erledigt.
Am Rig lief das Lauflicht aber unveraendert im Zickzack — **eine Einstellung,
die sichtbar reagiert, ohne zu wirken, ist irrefuehrender als eine, die gar
nichts tut.**

Der Weg ans Geraet existiert seit FM-20 Teil 1: die Matrix-Effekte holen ihr
Raster aus einer Fixture-Gruppe, und „als Block…" baut dieses Raster mit
`place_element` — also mit Nummerierung UND Montage-Drehung. Was fehlte, war der
Beleg, dass die Kette wirklich durchgeht, und ein ehrlicher Hinweis im Dialog.

★ Diese Datei faehrt die ganze Kette am ECHTEN Pfad:

    Patch-Dialog (Wahl „Schlangenlinien")
      -> PatchView speichert (update_fixture)
      -> Gruppen-Raster: Rechtsklick „als Block…" (echtes Menue, echter Dialog)
      -> Gruppe gespeichert (positions_json)
      -> Matrix-Effekt bindet die Gruppe (RgbMatrixView._assign_from_selection)
      -> RgbMatrixInstance.write -> DMX-Kanaele eines Universums

Gemessen wird am Ende ein DMX-Kanal, nicht ein Zwischenobjekt. Welcher Kanal zu
welchem Kopf gehoert, sagt die Produktion (`channels_for_head`) — die
ERWARTUNG dagegen ist von Hand aus der Geraete-Nummerierung abgeleitet und
steht als Zahl im Test: bei 12 Spalten in Schlangenlinien zaehlt die zweite
Zeile rueckwaerts, links aussen sitzt also Kopf 23 (Zeile 0: 0..11, Zeile 1:
23..12). Zeilenweise sitzt dort Kopf 12. Waere die Erwartung mit `pixel_cell`
nachgerechnet, pruefte der Test nur, dass die Formel sich selbst gleicht.

Die beiden anderen Aussagen:

* **Positivkontrolle** — „zeilenweise" (Default, Bestands-Shows) fuehrt zu Kopf
  12. Ohne sie wuerde auch ein Fehler durchgehen, der die Reihenfolge IMMER
  umdreht.
* **Die ehrliche Grenze** — die beim Patchen automatisch angelegte Gruppe
  („… · Köpfe") ist eine 1×N-Reihe in DMX-Reihenfolge und ignoriert die Wahl.
  Genau das behauptet der neue Hinweis im Dialog, und genau das wird hier
  nachgemessen, statt es zu glauben.
"""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QDialog, QLabel,   # noqa: E402
                               QWidget)
from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

import pytest as _pytest_xplat15                                 # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets          # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


# Davids Geraet, ein echtes Profil aus der Bibliothek: 48 einzeln faerbbare
# Zonen, physisch 12 Spalten x 4 Reihen.
MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
KANAELE = 154
SPALTEN = 12

# Die Zelle, an der sich die Reihenfolgen unterscheiden: Zeile 1, Spalte 0.
ZEILE, SPALTE = 1, 0
# Von Hand aus der Geraete-Nummerierung abgeleitet (NICHT aus `pixel_cell`):
KOPF_ZEILENWEISE = 12       # Zeile 1 beginnt links mit Kopf 12
KOPF_SCHLANGE = 23          # Zeile 1 laeuft rueckwaerts, links steht Kopf 23


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _StummeMeldung:
    """Ersatz fuer ``QMessageBox`` — ein modaler Hinweis blockiert headless bis
    zum Timeout, und ein haengendes Segment sieht im Runner aus wie ein Absturz.
    Keine Attrappe im gemessenen Pfad: gemessen werden Raster und DMX."""

    class StandardButton:
        Yes = 1
        No = 0

    @staticmethod
    def information(*_a, **_kw):
        return 0

    @staticmethod
    def warning(*_a, **_kw):
        return 0

    @staticmethod
    def question(*_a, **_kw):
        return 1


class _Basis(unittest.TestCase):
    def setUp(self):
        from src.core.app_state import get_state
        from src.core.database.fixture_db import (engine as fdb_engine,
                                                  ensure_builtins)
        from src.core.database.models import FixtureProfile
        from src.core.show.show_file import reset_show
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        with Session(fdb_engine()) as s:
            self.pid_panel = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "ZQ06121")).scalar_one())
            self.pid_par = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "ZQ01424")).scalar_one())

    def _patch_panel(self, fid: int = 1):
        """Das Panel patchen wie die Oberflaeche: OHNE Sonderwuensche. Die
        Pixel-Reihenfolge kommt spaeter aus dem Dialog — genau so, wie ein
        Benutzer sie nachtraeglich umstellt."""
        from src.core.database.models import PatchedFixture
        self.state.add_fixture(PatchedFixture(
            fid=fid, label="Balken", fixture_profile_id=self.pid_panel,
            mode_name=MODUS, universe=1, address=1, channel_count=KANAELE,
            manufacturer_name="U King",
            fixture_name="ZQ06121 LED-Balken 768 (stage light)",
            fixture_type="matrix"), undoable=False)
        return self._frisch(fid)

    def _frisch(self, fid: int = 1):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _kopfzahl(self, fx) -> int:
        from src.core.app_state import color_head_count
        return int(color_head_count(fx))

    def _im_dialog_waehlen(self, fid: int, order: str) -> None:
        """Die Wahl ueber den ECHTEN Dialog treffen und ueber den ECHTEN
        Aufrufer speichern (``PatchView._on_double_click`` -> ``update_fixture``).

        Nur ``exec`` wird ersetzt — sonst blieben wir headless im modalen Dialog
        stehen. Alles andere (Combo-Aufbau, ``_on_accept``, die Nutzlast und wer
        sie schreibt) ist Produktionscode; genau dort sass FM-13 zwei Runden
        lang tot (PIXELORDER-TOT), weil Tests die Nutzlast von Hand abschrieben.
        """
        import src.ui.views.patch_view as PV

        class _DialogMitWahl(PV.PatchFixtureEditDialog):
            def exec(self_inner):
                combo = self_inner._combo_pixel_order
                assert combo is not None, "Panel ohne Pixel-Reihenfolge-Feld"
                i = combo.findData(order)
                assert i >= 0, f"Reihenfolge {order!r} fehlt im Auswahlfeld"
                combo.setCurrentIndex(i)
                self_inner._on_accept()
                return QDialog.DialogCode.Accepted

        pv = PV.PatchView()
        self.addCleanup(pv.deleteLater)
        echt = PV.PatchFixtureEditDialog
        PV.PatchFixtureEditDialog = _DialogMitWahl
        try:
            zeile = next(r for r in range(pv._table.rowCount())
                         if pv._fid_at_row(r) == fid)
            pv._on_double_click(pv._table.model().index(zeile, 0))
        finally:
            PV.PatchFixtureEditDialog = echt

    def _block_gruppe(self, fx) -> int:
        """„als Block…" ueber die echte Ansicht — Kontextmenue-Aktion, echter
        Spalten-Dialog, echtes Speichern. Rueckgabe: Gruppen-id."""
        from src.ui.views import fixture_group_view as fgv
        from src.ui.views.fixture_group_view import FixtureGroupView
        view = FixtureGroupView()
        self.addCleanup(view.deleteLater)
        echt_dlg, echt_box = fgv.QInputDialog, fgv.QMessageBox
        fgv.QInputDialog = type("_Stub", (), {
            "getInt": staticmethod(lambda *a, **kw: (SPALTEN, True)),
            "getText": staticmethod(lambda *a, **kw: ("Balken-Raster", True))})
        fgv.QMessageBox = _StummeMeldung
        try:
            view._new_group()
            gw = view._grid_widget
            gw.positions.clear()
            gw.positions[(0, 0)] = fx.fid       # Panel als GANZES Geraet
            view._cell_menu_split(fx, self._kopfzahl(fx), "block", 0, 0)
            view._save_group()
        finally:
            fgv.QInputDialog, fgv.QMessageBox = echt_dlg, echt_box
        gid = next((g["id"] for g in self.state.list_fixture_groups()
                    if g.get("name") == "Balken-Raster"), None)
        self.assertIsNotNone(gid, "die aufgeteilte Gruppe wurde nicht gespeichert")
        return int(gid)

    def _dmx_kopf(self, gid: int, fx, zeile: int = ZEILE,
                  spalte: int = SPALTE) -> int:
        """Eine Zelle des Gruppen-Rasters faerben und messen, WELCHER Kopf am
        DMX leuchtet — ueber den Matrix-Effekt, nicht daneben.

        Rueckgabe: Kopf-Index (aus der Kanalnummer zurueckgerechnet, mit der
        Produktionsabbildung ``channels_for_head``).
        """
        from src.core.app_state import get_channels_for_patched, channels_for_head
        from src.core.dmx.universe import Universe
        from src.core.engine.rgb_matrix import MatrixStyle, RgbAlgorithm
        from src.ui.views.rgb_matrix_view import RgbMatrixView

        self.state.set_selected_group_id(gid)
        mv = RgbMatrixView()
        self.addCleanup(mv.deleteLater)
        mv._add()                      # der Knopf „+ Neu" im Matrix-Tab
        mv._assign_from_selection()    # Gruppen-Pfad: Raster aus positions_json
        inst = mv._current
        self.assertIsNotNone(inst, "keine Matrix angelegt")

        zellen = [(0, 0, 0)] * (inst.cols * inst.rows)
        zellen[zeile * inst.cols + spalte] = (255, 0, 0)
        inst.algorithm = RgbAlgorithm.PLAIN
        inst.style = MatrixStyle.RGB
        inst.start()
        inst._render = lambda _step: zellen
        u = Universe(fx.universe)
        inst.write({fx.universe: u}, self.state.get_patched_fixtures(), 0.0)

        an = [c for c in range(1, KANAELE + 1) if u.get_channel(c)]
        self.assertEqual(len(an), 1,
                         f"genau ein Rot-Kanal erwartet, an sind {an}")
        kanaele = get_channels_for_patched(fx)
        for kopf in range(self._kopfzahl(fx)):
            rot = channels_for_head(kanaele, kopf).get("color_r")
            if rot is not None and int(rot.channel_number) == an[0]:
                return kopf
        self.fail(f"Kanal {an[0]} gehoert zu keinem Kopf")


class KetteVomDialogBisZumDmxTest(_Basis):
    """Die Kette, die FM-21 als fehlend notiert hatte."""

    def _kette(self, order: str) -> int:
        fx = self._patch_panel()
        self._im_dialog_waehlen(fx.fid, order)
        fx = self._frisch()
        self.assertEqual(getattr(fx, "pixel_order", None), order,
                         "die Wahl aus dem Dialog kam nicht im Patch an")
        return self._dmx_kopf(self._block_gruppe(fx), fx)

    def test_schlangenlinie_erreicht_das_geraet(self):
        """★ Der Kern: „Schlangenlinien" im Dialog -> in der zweiten Rasterzeile
        leuchtet links Kopf 23, nicht Kopf 12. Gemessen am DMX-Kanal."""
        self.assertEqual(
            self._kette("serpentine"), KOPF_SCHLANGE,
            "die Pixel-Reihenfolge erreicht das Geraet nicht — im Raster liegt "
            "links in Zeile 1 der zeilenweise gezaehlte Kopf, obwohl das Panel "
            "in Schlangenlinien nummeriert")

    def test_zeilenweise_bleibt_wie_bisher(self):
        """POSITIVKONTROLLE: der Default darf sich NICHT aendern — sonst waere
        jede Bestands-Show still umsortiert, und der Test oben wuerde auch bei
        einem Fehler gruen, der die Reihenfolge grundsaetzlich umdreht."""
        self.assertEqual(
            self._kette("rowwise"), KOPF_ZEILENWEISE,
            "zeilenweise gepatcht, aber im Raster steht ein anderer Kopf — "
            "Bestands-Shows wuerden dadurch still umsortiert")

    def test_gespiegelt_dreht_schon_die_erste_zeile(self):
        """Gegenprobe: „Gespiegelt" dreht JEDE Zeile, die Schlangenlinie nur
        jede zweite. In Zeile 1 liefern beide dieselbe Zelle — der Unterschied
        steht in Zeile 0, also wird hier DIE gemessen: links aussen sitzt dann
        der letzte Kopf der Zeile (11), zeilenweise waere es Kopf 0."""
        fx = self._patch_panel()
        self._im_dialog_waehlen(fx.fid, "mirrored")
        fx = self._frisch()
        kopf = self._dmx_kopf(self._block_gruppe(fx), fx, zeile=0, spalte=0)
        self.assertEqual(kopf, SPALTEN - 1,
                         "Gespiegelt muss schon die erste Zeile umdrehen — "
                         "links aussen sitzt der letzte Kopf der Zeile")


class AutoKopfgruppeIstDieEhrlicheGrenzeTest(_Basis):
    """Was der neue Hinweis im Dialog behauptet, wird hier nachgemessen."""

    def test_auto_gruppe_bleibt_eine_reihe_in_dmx_folge(self):
        from src.core.database.models import FixtureGroup
        fx = self._patch_panel()
        self._im_dialog_waehlen(fx.fid, "mirrored")
        fx = self._frisch()
        self.state.update_fixture(fx.fid, element_rotation=90)
        gid = self.state.find_head_matrix_group(fx.fid, dedicated=True)
        self.assertIsNotNone(gid, "beim Patchen entstand keine Kopf-Gruppe")
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            self.assertEqual((g.cols, g.rows), (self._kopfzahl(fx), 1),
                             "die Auto-Gruppe ist keine 1×N-Reihe mehr — dann "
                             "ist der Hinweis im Patch-Dialog falsch")
            pos = json.loads(g.positions_json or "{}")
        self.assertEqual(pos.get("0,0"), f"{fx.fid}:0",
                         "die Auto-Gruppe folgt nicht mehr der DMX-Reihenfolge "
                         "— dann ist der Hinweis im Patch-Dialog falsch")
        self.assertEqual(pos.get(f"{self._kopfzahl(fx) - 1},0"),
                         f"{fx.fid}:{self._kopfzahl(fx) - 1}")


class DialogNenntDenWegTest(_Basis):
    """★ Der Hinweis wird gegen die ECHTE Oberflaeche gehalten, nicht gegen
    seine eigene Kopie: die Aktion kommt aus dem gebauten Kontextmenue, der
    Gruppenname aus der DB. Wer eines von beiden umbenennt, macht diese Datei
    rot — und nicht erst der Benutzer, der den Knopf sucht."""

    def _sichtbare_texte(self, dlg) -> set[str]:
        """Nur WIRKLICH sichtbare Beschriftungen — Tooltips zaehlen bewusst
        nicht: die Falle trifft genau den, der nicht hovert."""
        texte = set()
        for w in [dlg] + dlg.findChildren(QWidget):
            holen = getattr(w, "text", None)
            if callable(holen):
                try:
                    texte.add(str(holen()))
                except Exception:
                    pass
        return {t for t in texte if t}

    def _dialog(self, fx):
        from src.ui.views.patch_view import PatchFixtureEditDialog
        dlg = PatchFixtureEditDialog(self.state, fx)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def _menue_aktion_block(self, fx) -> str:
        """Die Beschriftung, die im echten Rechtsklick-Menue steht."""
        from src.ui.views.fixture_group_view import FixtureGroupView
        view = FixtureGroupView()
        self.addCleanup(view.deleteLater)
        view._grid_widget.positions[(0, 0)] = fx.fid
        menu = view._build_cell_menu(0, 0)
        self.assertIsNotNone(menu, "kein Kontextmenue im Gruppen-Raster")

        def _alle(m):
            for a in m.actions():
                if a.isSeparator():
                    continue
                yield a.text()
                if a.menu() is not None:
                    yield from _alle(a.menu())

        treffer = [t for t in _alle(menu) if "Block" in t]
        self.assertEqual(len(treffer), 1,
                         f"genau eine Block-Aktion erwartet, gefunden: {treffer}")
        return treffer[0]

    def test_hinweis_nennt_die_echte_aktion_und_die_echte_gruppe(self):
        from src.core.database.models import FixtureGroup
        fx = self._patch_panel()
        aktion = self._menue_aktion_block(fx)
        gid = self.state.find_head_matrix_group(fx.fid, dedicated=True)
        with self.state._session() as s:
            gruppenname = s.get(FixtureGroup, gid).name
        zusatz = gruppenname[len(fx.label):].strip()     # „· Köpfe"

        sichtbar = self._sichtbare_texte(self._dialog(fx))
        self.assertTrue(
            any(aktion in t for t in sichtbar),
            f"kein sichtbarer Hinweis nennt {aktion!r} — die Wahl reagiert in "
            f"der 3D-Vorschau, und wo sie am Geraet wirkt, steht nirgends")
        self.assertTrue(
            any(zusatz in t for t in sichtbar),
            f"der Hinweis nennt die Auto-Gruppe ({zusatz!r}) nicht — dann weiss "
            f"niemand, welche Gruppe sich NICHT mit aendert")

    def test_tooltip_verspricht_nichts_ohne_den_weg(self):
        """Auch der Hover-Text darf nicht fuer sich allein Wirkung am Geraet
        versprechen — er war genau die Stelle, die es tat."""
        fx = self._patch_panel()
        aktion = self._menue_aktion_block(fx)
        tip = self._dialog(fx)._combo_pixel_order.toolTip()
        self.assertIn("GERAET", tip.upper().replace("Ä", "AE"),
                      "der Tooltip sagt gar nichts ueber die Wirkung am Geraet")
        self.assertIn(aktion, tip,
                      "der Tooltip spricht von der Wirkung am Geraet, ohne den "
                      "Weg dorthin zu nennen — genau die Falle aus FM-21")

    def test_par_bekommt_den_hinweis_nicht(self):
        """POSITIVKONTROLLE fuer den Hinweis: ein PAR hat keine Pixel-
        Reihenfolge — dort waere der Text eine Behauptung ueber ein Feld, das
        es nicht gibt. Ein Hinweis, der ueberall steht, hilft nirgends."""
        from src.core.database.models import PatchedFixture
        self.state.add_fixture(PatchedFixture(
            fid=2, label="PAR links", fixture_profile_id=self.pid_par,
            mode_name="8-Kanal RGBW", universe=1, address=200, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        par = self._frisch(2)
        dlg = self._dialog(par)
        self.assertIsNone(dlg._combo_pixel_order,
                          "ein PAR hat kein Pixel-Reihenfolge-Feld")
        for t in self._sichtbare_texte(dlg):
            self.assertNotIn("als Block", t,
                             f"der PAR-Dialog zeigt den Panel-Hinweis: {t!r}")


if __name__ == "__main__":
    unittest.main()
