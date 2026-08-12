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
      -> Gruppen-Raster: das Kontextmenue der Zelle wird GEBAUT und sein
         Menuepunkt „als Block…" AUSGELOEST (kein direkter Aufruf mit fest
         verdrahtetem Modus), echter Spalten-Dialog
      -> Gruppe gespeichert (positions_json)
      -> Matrix-Effekt bindet die Gruppe (RgbMatrixView._assign_from_selection)
      -> RgbMatrixInstance.write -> DMX-Kanaele eines Universums

Am Ende steht ein DMX-Kanalwert im Universum — kein Zwischenobjekt. **Der
Rueckweg Kanal -> Kopf benutzt aber dieselbe Produktionsfunktion
(`channels_for_head`) wie `RgbMatrixInstance.write` selbst; ein Fehler IN
dieser Abbildung bliebe deshalb beidseitig unsichtbar.** Was diese Datei
misst, ist die Kette DAVOR: Dialogwahl -> Patch -> Menuepunkt -> Raster ->
Effekt. Die ERWARTUNG ist von Hand aus der Geraete-Nummerierung abgeleitet und
steht als Zahl im Test: bei 12 Spalten in Schlangenlinien zaehlt die zweite
Zeile rueckwaerts, links aussen sitzt also Kopf 23 (Zeile 0: 0..11, Zeile 1:
23..12). Zeilenweise sitzt dort Kopf 12. Waere die Erwartung mit `pixel_cell`
nachgerechnet, pruefte der Test nur, dass die Formel sich selbst gleicht.

Die weiteren Aussagen:

* **Positivkontrolle** — „zeilenweise" (Default, Bestands-Shows) fuehrt zu Kopf
  12. Ohne sie wuerde auch ein Fehler durchgehen, der die Reihenfolge IMMER
  umdreht.
* **Die ehrliche Grenze** — die beim Patchen automatisch angelegte Gruppe
  („… · Köpfe") ist eine 1×N-Reihe in DMX-Reihenfolge und ignoriert die Wahl.
  Genau das behauptet der Hinweis im Dialog, und genau das wird hier
  nachgemessen, statt es zu glauben.
* **Der Hinweis wird an der Stelle gemessen, an die er schickt** — in der
  Auto-Gruppe stehen KOPF-Zellen, dort bietet das Kontextmenue „als Block…"
  gar nicht an. Ein Hinweis, der einen Menuepunkt nennt, den es dort nicht
  gibt, ist so unbrauchbar wie gar keiner.
* **Er erscheint nur, wo der Weg existiert** — ein Matrix-Panel mit nur EINEM
  faerbbaren Kopf hat weder Kopf-Gruppe noch „als Block…".

Sichtbarkeit wird gemessen, nicht angenommen: der Dialog wird gezeigt
(``show()``) und nur ausgewertet, was Qt danach als sichtbar fuehrt.
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

# Ein Geraet, das fixture_type „matrix" ist und trotzdem nur EINEN faerbbaren
# Kopf hat: der Panel-Gesamtmodus der ADJ Dotz Matrix. Fuer die Abgrenzung in
# `EinKopfMatrixOhneHinweisTest` — „Matrix" heisst nicht „hat ein Raster".
MODUS_EINKOPF = "3-Kanal RGB"
KANAELE_EINKOPF = 3

# Die Zelle, an der sich die Reihenfolgen unterscheiden: Zeile 1, Spalte 0.
ZEILE, SPALTE = 1, 0
# Von Hand aus der Geraete-Nummerierung abgeleitet (NICHT aus `pixel_cell`):
KOPF_ZEILENWEISE = 12       # Zeile 1 beginnt links mit Kopf 12
KOPF_SCHLANGE = 23          # Zeile 1 laeuft rueckwaerts, links steht Kopf 23


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _menue_eintraege(menu) -> list:
    """Alle Menuepunkte samt Untermenues als Liste von ``(Text, QAction)``.

    Ausloesen laesst sich so ein Eintrag mit ``QAction.trigger()`` — dasselbe,
    was ein Mausklick tut, nur ohne das blockierende ``QMenu.exec``.

    ★ Aktionen UND Untermenues werden am uebergebenen Menue festgehalten.
    PySide6 haengt die Lebensdauer eines Untermenues an die Python-Referenz der
    Aktion, die es traegt: filtert der Aufrufer diese Aktion weg (sie heisst
    „… aufteilen (48 Elemente)", enthaelt also kein „Block"), raeumt der
    Garbage Collector Aktion, Untermenue und dessen Eintraege gemeinsam weg —
    ``trigger()`` scheitert dann an „Internal C++ object already deleted".
    Genau daran ist der erste Versuch gestorben (gemessen). Solange der
    Aufrufer `menu` haelt, leben sie.
    """
    halter = getattr(menu, "_fm21_halter", None)
    if halter is None:
        halter = []
        menu._fm21_halter = halter
    eintraege = []
    for a in menu.actions():
        if a.isSeparator():
            continue
        halter.append(a)
        eintraege.append((a.text(), a))
        sub = a.menu()
        if sub is not None:
            halter.append(sub)
            eintraege.extend(_menue_eintraege(sub))
    return eintraege


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
            self.pid_dotz = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "DOTZMATRIX")).scalar_one())

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

    def _patch_einkopf_matrix(self, fid: int = 3):
        """Ein Geraet vom Typ „matrix" mit nur EINEM faerbbaren Kopf: der
        Panel-Gesamtmodus der ADJ Dotz Matrix faerbt alle 16 Pixel zusammen,
        hat also genau eine RGB-Bank. Fuer dieses Geraet gibt es weder eine
        Kopf-Gruppe noch „als Block…"."""
        from src.core.database.models import PatchedFixture
        self.state.add_fixture(PatchedFixture(
            fid=fid, label="Dotz gesamt", fixture_profile_id=self.pid_dotz,
            mode_name=MODUS_EINKOPF, universe=1, address=300,
            channel_count=KANAELE_EINKOPF, manufacturer_name="ADJ",
            fixture_name="Dotz Matrix", fixture_type="matrix"), undoable=False)
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
        """„als Block…" ueber den ECHTEN Weg: Kontextmenue der Zelle bauen, den
        Menuepunkt ausloesen, echter Spalten-Dialog, echtes Speichern.
        Rueckgabe: Gruppen-id.

        ★ Der Modus („block") wird hier NICHT uebergeben — er haengt allein an
        dem Menuepunkt, den `_build_cell_menu` verdrahtet. Vorher rief diese
        Datei `_cell_menu_split(fx, n, "block", 0, 0)` direkt: bog man im
        Produktionscode „als Block…" auf „als Zeile" um, blieb jeder Test hier
        gruen — und der Benutzer bekaeme wieder den 1×48-Streifen, also exakt
        den Fehler, um den es in FM-21 geht.

        Ausgeloest wird mit `QAction.trigger()`. `QMenu.exec` zeigt das Menue
        und blockiert bis zum Klick — headless gibt es niemanden, der klickt;
        `_build_cell_menu` ist genau dafuer vom Anzeigen getrennt.
        """
        from src.ui.views import fixture_group_view as fgv
        from src.ui.views.fixture_group_view import FixtureGroupView
        view = FixtureGroupView()
        self.addCleanup(view.deleteLater)
        n = self._kopfzahl(fx)
        gesehen: dict = {}

        class _SpaltenDialog:
            """Kein Wegwerf-Stub: nimmt die Argumente des ECHTEN Aufrufs benannt
            entgegen und haelt sie fest, damit Titel/Frage/Vorschlag geprueft
            werden koennen (Vorbild: test_doc13_anleitung_gruppen_matrizen.py).
            Nur der modale Aufruf wird ersetzt — was gefragt wird, entscheidet
            weiter `_ask_block_cols`."""

            @staticmethod
            def getInt(_eltern, titel, frage, wert=0, mini=0, maxi=0, schritt=1,
                       **_kw):
                gesehen.update(titel=str(titel), frage=str(frage),
                               vorschlag=int(wert), maxi=int(maxi))
                return SPALTEN, True

            @staticmethod
            def getText(_eltern, _titel, _frage, *_a, **_kw):
                return ("Balken-Raster", True)

        echt_dlg, echt_box = fgv.QInputDialog, fgv.QMessageBox
        fgv.QInputDialog = _SpaltenDialog
        fgv.QMessageBox = _StummeMeldung
        try:
            view._new_group()
            gw = view._grid_widget
            gw.positions.clear()
            gw.positions[(0, 0)] = fx.fid       # Panel als GANZES Geraet
            menu = view._build_cell_menu(0, 0)
            self.assertIsNotNone(menu, "kein Kontextmenue an der Geraete-Zelle")
            treffer = [(t, a) for t, a in _menue_eintraege(menu) if "Block" in t]
            self.assertEqual(
                len(treffer), 1,
                f"genau ein Block-Menuepunkt erwartet, gefunden: "
                f"{[t for t, _ in treffer]}")
            treffer[0][1].trigger()
            view._save_group()
        finally:
            fgv.QInputDialog, fgv.QMessageBox = echt_dlg, echt_box

        # Der Spalten-Dialog wurde wirklich gefragt — und zwar mit dem Text und
        # dem Vorschlag, den `_ask_block_cols` verspricht. Ohne diese Pruefung
        # koennte der Menuepunkt auch einen ganz anderen Dialog oeffnen.
        self.assertEqual(gesehen.get("titel"), "Als Block aufteilen",
                         f"anderer Dialog als der Block-Dialog: {gesehen!r}")
        self.assertIn("Spalten", gesehen.get("frage", ""))
        self.assertIn(str(n), gesehen.get("frage", ""),
                      "die Frage nennt die Elementzahl des Geraets nicht")
        self.assertEqual(gesehen.get("maxi"), n)
        vorschlag = int(gesehen.get("vorschlag", 0))
        self.assertTrue(1 <= vorschlag <= n and n % vorschlag == 0,
                        f"der Vorschlag {vorschlag} ist kein Teiler von {n} — "
                        "dann geht der Block nicht auf")

        gid = next((g["id"] for g in self.state.list_fixture_groups()
                    if g.get("name") == "Balken-Raster"), None)
        self.assertIsNotNone(gid, "die aufgeteilte Gruppe wurde nicht gespeichert")
        return int(gid)

    def _dmx_kopf(self, gid: int, fx, zeile: int = ZEILE,
                  spalte: int = SPALTE) -> int:
        """Eine Zelle des Gruppen-Rasters faerben und messen, WELCHER Kopf am
        DMX leuchtet — ueber den Matrix-Effekt, nicht daneben.

        Rueckgabe: Kopf-Index, aus der Kanalnummer zurueckgerechnet.

        ⚠ Die Grenze dieser Messung, offen gesagt: zurueckgerechnet wird mit
        ``channels_for_head`` — derselben Funktion, die ``RgbMatrixInstance.
        write`` zum Schreiben benutzt. Ein Fehler IN dieser Abbildung bliebe
        also auf beiden Seiten unsichtbar. Gemessen ist damit die Kette davor
        (Dialogwahl -> Patch -> Menuepunkt -> Raster -> Effekt), nicht die
        Kopf-zu-Kanal-Abbildung selbst; die haengt an ihren eigenen Tests.
        """
        from src.core.app_state import get_channels_for_patched, channels_for_head
        from src.core.dmx.universe import Universe
        from src.core.engine.rgb_matrix import MatrixStyle
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
        # `style` liest `write` selbst (RGB-Zweig) — die Zeile wirkt. Der
        # frueher hier stehende `algorithm`-Aufbau nicht: `_render` wird zwei
        # Zeilen weiter ersetzt, der Algorithmus also nie ausgefuehrt.
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
        """Nur was der Benutzer WIRKLICH sieht.

        ★ Der Dialog wird GEZEIGT (``show()`` — ``exec()`` blockierte headless)
        und danach nur ausgewertet, was Qt als sichtbar fuehrt. Ohne diese
        Abfrage misst die Datei die Sichtbarkeit gar nicht: ein
        ``_hinweis.setVisible(False)`` im Produktionscode liess vorher alle
        Tests gruen, obwohl der Hinweis nie auf dem Schirm erscheint — und
        genau darum geht es hier, ein unsichtbarer Hinweis ist keiner.

        Tooltips zaehlen bewusst nicht: die Falle trifft genau den, der nicht
        hovert.
        """
        dlg.show()
        texte = set()
        for w in dlg.findChildren(QWidget):
            if not w.isVisible():
                continue
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

    def _menue_texte(self, positionen: dict) -> list[str]:
        """Die Beschriftungen des echten Rechtsklick-Menues an Zelle (0,0) —
        fuer ein Raster, das genau so belegt ist wie ``positionen``."""
        from src.ui.views.fixture_group_view import FixtureGroupView
        view = FixtureGroupView()
        self.addCleanup(view.deleteLater)
        gw = view._grid_widget
        gw.positions.clear()
        gw.positions.update(positionen)
        menu = view._build_cell_menu(0, 0)
        self.assertIsNotNone(menu, "kein Kontextmenue im Gruppen-Raster")
        return [t for t, _a in _menue_eintraege(menu)]

    def _menue_aktion_block(self, fx) -> str:
        """Die Beschriftung des Aufteilen-Menuepunkts — messbar erst, wenn das
        Geraet als GANZES in der Zelle steht. Genau diese Voraussetzung stellt
        der Test hier selbst her; dass sie nach dem Patchen NICHT gilt, misst
        `test_hinweis_nennt_den_noetigen_zwischenschritt`."""
        treffer = [t for t in self._menue_texte({(0, 0): fx.fid})
                   if "Block" in t]
        self.assertEqual(len(treffer), 1,
                         f"genau eine Block-Aktion erwartet, gefunden: {treffer}")
        return treffer[0]

    def _auto_gruppen_positionen(self, fx) -> dict:
        """Die Belegung, die beim Patchen WIRKLICH entsteht — aus der
        gespeicherten Kopf-Gruppe gelesen, nicht nachgebaut."""
        from src.core.database.models import FixtureGroup
        gid = self.state.find_head_matrix_group(fx.fid, dedicated=True)
        self.assertIsNotNone(gid, "beim Patchen entstand keine Kopf-Gruppe")
        with self.state._session() as s:
            pos = json.loads(s.get(FixtureGroup, gid).positions_json or "{}")
        out = {}
        for schluessel, wert in pos.items():
            c, r = schluessel.split(",")
            out[(int(c), int(r))] = wert
        return out

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

    def test_hinweis_nennt_den_noetigen_zwischenschritt(self):
        """★ Der Hinweis schickte den Benutzer an eine Stelle, an der es den
        genannten Menuepunkt NICHT gibt.

        Nach dem Patchen liegt genau EINE Gruppe fuer dieses Geraet vor, und in
        ihr traegt jede Zelle einen KOPF (``fid:head``). `_build_cell_menu`
        bietet „als Block…" aber nur an, wo das Geraet als GANZES steht — hier
        wird nachgemessen, dass es dort wirklich fehlt. Wer dem alten Hinweis
        („Rechtsklick auf das Gerät im Raster → „als Block…"") folgte, suchte
        einen Menuepunkt, der an der einzigen vorhandenen Stelle nicht da ist.

        Der Zwischenschritt steht in der Anleitung
        (docs/anleitung_gruppen_matrizen, Abschnitt 3 Schritt 1: Geraet als
        ganzes auf eine Rasterzelle ziehen; Abschnitt 5: Kopf-Zellen „zu einer
        Zelle zusammenfassen") — geprueft wird gegen die Beschriftung, die das
        echte Menue an dieser Stelle anbietet, nicht gegen die Anleitung.
        """
        fx = self._patch_panel()
        in_der_auto_gruppe = self._menue_texte(self._auto_gruppen_positionen(fx))
        self.assertEqual(
            [t for t in in_der_auto_gruppe if "Block" in t], [],
            "in der Auto-Gruppe gibt es „als Block…“ doch — dann darf der "
            "Hinweis wieder direkt dorthin schicken (und dieser Test weg)")
        heraus = [t for t in in_der_auto_gruppe if "zusammenfassen" in t]
        self.assertEqual(len(heraus), 1,
                         f"genau ein Zusammenfassen-Menuepunkt erwartet, "
                         f"gefunden: {in_der_auto_gruppe}")
        # Der Geraetename steckt in der Beschriftung („Balken" zu einer Zelle
        # …) — fuer den Hinweis zaehlt nur der geraeteunabhaengige Teil.
        zwischenschritt = heraus[0].split("“", 1)[1].strip()

        sichtbar = self._sichtbare_texte(self._dialog(fx))
        self.assertTrue(
            any(zwischenschritt in t for t in sichtbar),
            f"kein sichtbarer Hinweis nennt {zwischenschritt!r} — der Weg "
            f"beginnt aber genau dort: in der beim Patchen angelegten Gruppe "
            f"steht in jeder Zelle nur ein Kopf, und dort bietet das Menue nur "
            f"{in_der_auto_gruppe}")

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

    def test_einkopf_matrix_bekommt_den_hinweis_nicht(self):
        """★ Die schaerfere Positivkontrolle: „Matrix" heisst nicht „hat ein
        Raster". Der PAR oben faellt schon durch das fehlende
        Pixel-Reihenfolge-Feld heraus — dieses Geraet NICHT: es ist
        fixture_type „matrix", hat das Feld, und trotzdem gibt es den ganzen
        beschriebenen Weg nicht. Alle drei Voraussetzungen werden hier
        nachgemessen, damit der Test nicht bloss seine eigene Bedingung
        wiederholt:

        * nur EIN faerbbarer Kopf,
        * keine Kopf-Gruppe („… · Köpfe" entsteht ab zwei Koepfen),
        * kein „als Block…" im Kontextmenue (`_build_cell_menu`: ab n >= 2).

        Ein Hinweis dort waere die Anleitung zu einem Menuepunkt, den dieses
        Geraet nicht hat — und zu einer Gruppe, die es nicht gibt.
        """
        fx = self._patch_einkopf_matrix()
        self.assertEqual(self._kopfzahl(fx), 1,
                         "dieses Geraet hat mehrere Koepfe — dann ist es die "
                         "falsche Gegenprobe")
        self.assertIsNone(
            self.state.find_head_matrix_group(fx.fid, dedicated=True),
            "es gibt doch eine Kopf-Gruppe — dann darf der Hinweis erscheinen")
        self.assertEqual(
            [t for t in self._menue_texte({(0, 0): fx.fid}) if "Block" in t],
            [], "das Menue bietet „als Block…“ doch an — dann waere der "
                "Hinweis richtig")

        dlg = self._dialog(fx)
        self.assertIsNotNone(
            dlg._combo_pixel_order,
            "ohne Pixel-Reihenfolge-Feld waere die Gegenprobe stumpf — dann "
            "faellt dieses Geraet schon wie der PAR heraus")
        for t in self._sichtbare_texte(dlg):
            self.assertNotIn(
                "als Block", t,
                f"ein Ein-Kopf-Panel zeigt den Block-Hinweis: {t!r}")
        tip = dlg._combo_pixel_order.toolTip()
        self.assertNotIn("als Block", tip,
                         "auch der Tooltip verspricht hier einen Weg, den es "
                         "an diesem Geraet nicht gibt")


if __name__ == "__main__":
    unittest.main()
