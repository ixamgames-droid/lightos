"""DOC-13 — die Anleitung „Gruppen und Matrizen anlegen" gegen die ECHTE Oberflaeche.

Die Anleitung existiert, weil ein Feature, das niemand findet, praktisch nicht
vorhanden ist: Aufteilen, Zusammenfassen und Zusammenlegen von Kopf-Matrizen
gibt es seit Monaten, sie stecken nur im Rechtsklick-Menue und in einem
Knopf-Menue. Eine Anleitung, die dorthin fuehrt, ist aber nur so lange etwas
wert, wie ihre Beschriftungen und Zahlen stimmen — eine falsche Beschriftung ist
schlimmer als gar keine: der Leser sucht dann einen Knopf, den es nicht gibt,
und haelt sich selbst fuer den Fehler.

**Deshalb prueft diese Datei die Anleitung gegen die laufende Oberflaeche**, nicht
gegen eine Kopie ihrer Texte. Gebaut wird die echte ``FixtureGroupView`` mit
einem echt gepatchten Mehrkopf-Geraet; die Menuepunkte kommen aus
``_build_cell_menu``, die Dialogtexte aus den echten Dialog-Aufrufen. Zieht
jemand einen Knopf um, wird diese Datei rot und nennt die Anleitung, die
nachgezogen werden muss.

Drei Aussagen der Anleitung haengen an dieser Pruefung:

1. **Beschriftungen** — jedes „…"-Zitat muss in der Oberflaeche vorkommen.
2. **Zahlen** — „48 einzeln färbbare Zonen", „1 Zeile × 48 Zellen" und
   „12 Spalten × 4 Zeilen" werden am realen Ergebnis nachgemessen.
3. **Namen** — Ordner der Auto-Gruppe und der zusammengelegten Gruppe, sowie der
   Namenszusatz der Auto-Gruppe, kommen aus der DB und muessen im Text stehen.

★ Zur Konvention: Anleitungen dieses Repos schreiben Beschriftungen als
``„Text"`` — oeffnendes U+201E, schliessendes ASCII-Anfuehrungszeichen. Genau das
liest ``_ZITAT``; enthaelt ein Menuepunkt den Geraetenamen, zitiert die Anleitung
nur den festen Teil, deshalb wird auf TEILSTRING geprueft und nicht auf
Gleichheit.
"""
from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QComboBox, QDialog,   # noqa: E402
                               QListWidget, QWidget)
from PySide6.QtWidgets import QAbstractButton                      # noqa: E402
from sqlalchemy import select                                      # noqa: E402
from sqlalchemy.orm import Session                                 # noqa: E402

import pytest as _pytest_xplat15                                   # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets            # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANLEITUNG = os.path.join(REPO, "docs", "anleitung_gruppen_matrizen",
                         "ANLEITUNG_GRUPPEN_MATRIZEN.md")
INDEX = os.path.join(REPO, "docs", "ANLEITUNGEN.md")
INDEX_PFAD = "anleitung_gruppen_matrizen/ANLEITUNG_GRUPPEN_MATRIZEN.md"

_ZITAT = re.compile("„([^„\"\n]+)\"")

# Die Stellen der Anleitung, an denen eine ZAHL eine Behauptung ueber die Software
# ist. Als Konstanten, damit Pruefung und Parser-Test dasselbe Muster benutzen —
# baut ein Test seine eigene Kopie, misst er am Ende nur sich selbst (QA-52).
MUSTER_ZONEN = r"\*\*(\d+) einzeln färbbare Zonen\*\*"
MUSTER_AUTO_RASTER = r"\*\*(\d+) Zeile × (\d+) Zellen\*\*"
MUSTER_PHYSISCH = r"\*\*(\d+) Spalten × (\d+) Reihen\*\*"
MUSTER_EINGABE = r"Für den Balken \*\*(\d+)\*\* eintragen"
MUSTER_BLOCK = r"Ergebnis: \*\*(\d+) Spalten × (\d+) Zeilen\*\*"

# Das Geraet der Anleitung — ein echtes Profil aus der Bibliothek, kein Attrappen-
# Fixture: die Kopfzahl 48 ist die Aussage, die geprueft wird.
MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
KANAELE = 154
LABEL = "LED-Balken"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def anleitung_text() -> str:
    with open(ANLEITUNG, encoding="utf-8") as fh:
        return fh.read()


def zitate(text: str) -> list[tuple[int, str]]:
    """(Zeilennummer, Beschriftung) je „…"-Zitat — zeilenweise, damit ein
    fehlendes schliessendes Zeichen nicht den halben Text verschluckt."""
    out: list[tuple[int, str]] = []
    for nr, zeile in enumerate(text.splitlines(), 1):
        for m in _ZITAT.finditer(zeile):
            out.append((nr, m.group(1).strip()))
    return out


def fehlende(zitate_: list[tuple[int, str]], lebend: set[str]) -> list[tuple[int, str]]:
    """Zitate, die in KEINER lebenden Beschriftung vorkommen."""
    return [(nr, z) for nr, z in zitate_
            if not any(z in t for t in lebend)]


def _zahl(text: str, muster: str) -> tuple[int, ...]:
    """Genau EIN Vorkommen des Musters — sonst Fehler.

    Mehrere Vorkommen waeren die stille Variante des Driftens: eine Stelle wird
    korrigiert, die andere bleibt stehen, und die Pruefung findet zufaellig die
    richtige. Deshalb ist Mehrdeutigkeit hier ein Fehler.
    """
    treffer = re.findall(muster, text)
    if len(treffer) != 1:
        raise AssertionError(
            f"Marker {muster!r} kommt {len(treffer)}× vor (erwartet: genau 1) — "
            "die Anleitung wurde umformuliert, die Pruefung greift ins Leere")
    roh = treffer[0]
    if isinstance(roh, tuple):
        return tuple(int(x) for x in roh)
    return (int(roh),)


def menue_texte(menu) -> set[str]:
    """Alle Eintraege eines Menues samt Untermenues."""
    out: set[str] = set()
    if menu is None:
        return out
    for a in menu.actions():
        if a.isSeparator():
            continue
        out.add(a.text())
        out |= menue_texte(a.menu())
    return out


def widget_texte(root: QWidget) -> set[str]:
    """Jede sichtbare Beschriftung unter ``root`` — Knoepfe, Labels, Combo-
    Eintraege, Menues, Fenstertitel."""
    texte: set[str] = {root.windowTitle()}
    for w in [root] + root.findChildren(QWidget):
        holen = getattr(w, "text", None)
        if callable(holen):
            try:
                texte.add(str(holen()))
            except Exception:
                pass
        if isinstance(w, QComboBox):
            texte.update(w.itemText(i) for i in range(w.count()))
        if isinstance(w, QAbstractButton):
            # Nur QPushButton/QToolButton tragen ein Menue — `getattr`, weil
            # QCheckBox & Co. die Methode gar nicht haben.
            hol_menue = getattr(w, "menu", None)
            if callable(hol_menue):
                texte |= menue_texte(hol_menue())
    return {t for t in texte if t}


class _StummeMeldung:
    """Ersatz fuer ``QMessageBox`` waehrend der Text-Ernte.

    ★ Keine Attrappe im gemessenen Pfad: geprueft werden Menues, Dialogtexte und
    Rasterergebnisse. Ein modaler Hinweis waere hier nur eine Falle — er
    BLOCKIERT headless bis zum Timeout, und ein haengendes Segment sieht im
    Runner aus wie ein Absturz, nicht wie ein Testfehler.
    """
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


class AnleitungGegenOberflaecheTest(unittest.TestCase):
    """Baut die echte Ansicht mit dem echten Geraeteprofil."""

    def setUp(self):
        from src.core.app_state import get_state
        from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
        from src.core.database.models import PatchedFixture, FixtureProfile
        from src.core.show.show_file import reset_show
        from src.ui.views.fixture_group_view import FixtureGroupView
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        with Session(fdb_engine()) as s:
            pid_panel = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "ZQ06121")).scalar_one())
            pid_par = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "ZQ01424")).scalar_one())
        self.state.add_fixture(PatchedFixture(
            fid=1, label=LABEL, fixture_profile_id=pid_panel,
            mode_name=MODUS, universe=3, address=1, channel_count=KANAELE,
            manufacturer_name="U King",
            fixture_name="ZQ06121 LED-Balken 768 (stage light)",
            fixture_type="matrix"), undoable=False)
        for fid, label, adresse in ((2, "PAR links", 1), (3, "PAR rechts", 9)):
            self.state.add_fixture(PatchedFixture(
                fid=fid, label=label, fixture_profile_id=pid_par,
                mode_name="8-Kanal RGBW", universe=1, address=adresse,
                channel_count=8, manufacturer_name="Generic",
                fixture_name="Stage Light ZQ01424",
                fixture_type="par"), undoable=False)
        self.panel = next(f for f in self.state.get_patched_fixtures() if f.fid == 1)
        self.view = FixtureGroupView()
        self.addCleanup(self.view.deleteLater)
        self.text = anleitung_text()

    # ── Bausteine ────────────────────────────────────────────────────────────

    def _kopfzahl(self) -> int:
        from src.core.app_state import color_head_count
        return int(color_head_count(self.panel))

    def _auto_gruppe(self):
        """Die Gruppe, die beim Patchen entsteht — ueber den echten Aufruf."""
        from src.core.database.models import FixtureGroup
        gid = self.state.create_head_matrix_group(self.panel)
        self.assertIsNotNone(gid, "keine Kopf-Matrix-Gruppe entstanden")
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            return gid, g.name, g.cols, g.rows, g.folder

    def _block_aufteilen(self, spalten: int) -> list[tuple[int, int]]:
        """„als Block…" ueber die echte View — inklusive Dialog und Raster-
        Wachstum. Der Dialog liefert die Spaltenzahl, die die Anleitung nennt."""
        from src.ui.views import fixture_group_view as fgv
        from src.ui.views.fixture_group_view import _split_cell
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = 1          # Panel steht als GANZES Geraet im Raster
        echt_dlg, echt_box = fgv.QInputDialog, fgv.QMessageBox
        fgv.QInputDialog = type("_Stub", (), {
            "getInt": staticmethod(lambda *a, **kw: (spalten, True))})
        fgv.QMessageBox = _StummeMeldung
        try:
            self.view._cell_menu_split(self.panel, self._kopfzahl(), "block", 0, 0)
        finally:
            fgv.QInputDialog, fgv.QMessageBox = echt_dlg, echt_box
        return [(c, r) for (c, r), v in gw.positions.items()
                if _split_cell(v)[0] == 1 and _split_cell(v)[1] is not None]

    def _par_gruppe(self):
        """Zweite Gruppe auf dem Weg, den die Anleitung beschreibt:
        „+ Neu" → Geraete ins Raster → „Speichern"."""
        from src.ui.views import fixture_group_view as fgv
        echt_dlg, echt_box = fgv.QInputDialog, fgv.QMessageBox
        fgv.QInputDialog = type("_Stub", (), {
            "getText": staticmethod(lambda *a, **kw: ("PAR-Reihe", True))})
        fgv.QMessageBox = _StummeMeldung
        try:
            self.view._new_group()
            gw = self.view._grid_widget
            gw.positions.clear()
            gw.positions[(0, 0)] = 2
            gw.positions[(1, 0)] = 3
            self.view._spin_cols.setValue(2)
            self.view._spin_rows.setValue(1)
            self.view._save_group()
        finally:
            fgv.QInputDialog, fgv.QMessageBox = echt_dlg, echt_box

    def _lebende_texte(self) -> set[str]:
        """Jede Beschriftung, die ein Benutzer auf diesem Weg zu sehen bekommt."""
        from src.ui.views import fixture_group_view as fgv
        from src.ui.views.patch_view import PatchFixtureEditDialog
        gw = self.view._grid_widget
        texte = widget_texte(self.view)

        # Kontextmenues: ganze Geraete-Zelle (48 Koepfe), Kopf-Zelle, PAR.
        gw.positions.clear()
        gw.positions[(0, 0)] = 1
        texte |= menue_texte(self.view._build_cell_menu(0, 0))
        gw.positions.clear()
        gw.positions[(0, 0)] = "1:0"
        gw.positions[(1, 0)] = "1:1"
        texte |= menue_texte(self.view._build_cell_menu(0, 0))
        gw.positions.clear()
        gw.positions[(0, 0)] = 2
        texte |= menue_texte(self.view._build_cell_menu(0, 0))
        gw.positions.clear()

        # Block-Dialog: Titel und Frage dem ECHTEN Aufruf abgegriffen.
        gesehen: set[str] = set()

        class _StubEingabe:
            @staticmethod
            def getInt(_parent, titel, frage, wert=0, mini=0, maxi=0, schritt=1,
                       **_kw):
                gesehen.update({str(titel), str(frage)})
                return wert, False

        echt_dlg = fgv.QInputDialog
        fgv.QInputDialog = _StubEingabe
        try:
            self.view._ask_block_cols(self._kopfzahl())
        finally:
            fgv.QInputDialog = echt_dlg
        texte |= gesehen

        # Zusammenlegen-Dialog: der echte Dialog wird gebaut, nur `exec` wird
        # ersetzt (headless kann niemand klicken). Braucht >= 2 Gruppen.
        self._auto_gruppe()
        self._par_gruppe()
        texte |= self._zusammenlegen_dialog()[1]

        # Patch-Dialog „Gerät bearbeiten" — dort stehen Mehrkopf-Programmierung,
        # Pixel-Reihenfolge und Montage-Drehung.
        dlg = PatchFixtureEditDialog(self.state, self.panel)
        self.addCleanup(dlg.deleteLater)
        texte |= widget_texte(dlg)
        return texte

    def _zusammenlegen_dialog(self, auswahl: int = 0):
        """``_merge_groups`` mit echtem Dialog fahren.

        ``auswahl`` = wie viele Listeneintraege vor dem OK markiert werden; 0
        heisst „Abbrechen". Rueckgabe: (neue Gruppen-id oder None, Dialogtexte).
        """
        from src.ui.views import fixture_group_view as fgv
        gesehen: set[str] = set()
        vorher = set(self._gruppen_ids())

        class _Rec(QDialog):
            def exec(self):
                gesehen.update(widget_texte(self))
                if auswahl < 2:
                    return QDialog.DialogCode.Rejected
                for lst in self.findChildren(QListWidget):
                    for i in range(min(auswahl, lst.count())):
                        lst.item(i).setSelected(True)
                return QDialog.DialogCode.Accepted

        echt_dlg, echt_box = fgv.QDialog, fgv.QMessageBox
        fgv.QDialog, fgv.QMessageBox = _Rec, _StummeMeldung
        try:
            self.view._merge_groups()
        finally:
            fgv.QDialog, fgv.QMessageBox = echt_dlg, echt_box
        neu = [g for g in self._gruppen_ids() if g not in vorher]
        return (neu[0] if neu else None), gesehen

    def _gruppen_ids(self) -> list[int]:
        from src.core.database.models import FixtureGroup
        with self.state._session() as s:
            return [int(g.id) for g in
                    s.execute(select(FixtureGroup)).scalars().all()]

    # ── 1. Beschriftungen ────────────────────────────────────────────────────

    def test_jede_zitierte_beschriftung_gibt_es_wirklich(self):
        lebend = self._lebende_texte()
        self.assertGreater(len(lebend), 30,
                           "zu wenige Beschriftungen eingesammelt — die Ernte "
                           "greift ins Leere und das Gate waere blind")
        zit = zitate(self.text)
        self.assertGreater(len(zit), 20,
                           "die Anleitung zitiert kaum Beschriftungen — dann "
                           "prueft dieses Gate nichts")
        fehlt = fehlende(zit, lebend)
        self.assertEqual(
            fehlt, [],
            "Diese Beschriftungen stehen in der Anleitung, aber in keiner "
            f"Stelle der Oberflaeche:\n{fehlt}")

    def test_gate_meldet_eine_erfundene_beschriftung(self):
        """★ Positivkontrolle. Ohne sie waere nicht zu unterscheiden, ob die
        Anleitung stimmt oder die Pruefung nichts mehr findet."""
        lebend = self._lebende_texte()
        probe = ('Klick „Köpfe zusammenfassen (eine Zelle)" und dann '
                 '„Köpfe zusammenlegen (eine Zelle)".')
        befund = fehlende(zitate(probe), lebend)
        self.assertEqual([z for _nr, z in befund],
                         ["Köpfe zusammenlegen (eine Zelle)"],
                         "das Gate muss die erfundene Beschriftung melden — "
                         "und die echte in Ruhe lassen")

    def test_zitat_erkennung_liest_die_konvention(self):
        """Der Parser selbst: „…" wird erkannt, `Code` und **fett** nicht."""
        probe = 'Nimm „+ Neu" und **Speichern**, nicht `Ordner…`.\n„Zeilen:"'
        self.assertEqual([z for _nr, z in zitate(probe)],
                         ["+ Neu", "Zeilen:"])

    # ── 2. Zahlen ────────────────────────────────────────────────────────────

    def test_die_genannte_zonenzahl_stimmt_mit_dem_geraet(self):
        (behauptet,) = _zahl(self.text, MUSTER_ZONEN)
        self.assertEqual(behauptet, self._kopfzahl(),
                         "die Anleitung nennt eine andere Kopfzahl, als das "
                         "Geraet in diesem Modus meldet")

    def test_das_genannte_auto_raster_stimmt(self):
        zeilen, zellen = _zahl(self.text, MUSTER_AUTO_RASTER)
        _gid, _name, cols, rows, _folder = self._auto_gruppe()
        self.assertEqual((rows, cols), (zeilen, zellen),
                         "die automatisch angelegte Kopf-Gruppe hat ein anderes "
                         "Raster als die Anleitung beschreibt")

    def test_das_genannte_blockergebnis_stimmt(self):
        """★ Diese Fassung ist von der Mutationsmessung erzwungen.

        Die erste Fassung las nur die Ergebniszeile und teilte mit GENAU dieser
        Spaltenzahl auf. Damit war sie gegen jede Aenderung der Zahl blind: aus
        „8 Spalten × 6 Zeilen" wurden brav 8×6 — die Software macht ja, was man
        ihr sagt. Gemessen: die Mutation blieb GRUEN.

        Geprueft wird deshalb die ganze Kette: die physische Angabe im
        Beispielaufbau, die Zahl, die der Leser eintippen soll, und das
        versprochene Ergebnis muessen zueinander passen UND das Ergebnis muss
        herauskommen, wenn man es wirklich tut.
        """
        phys_spalten, phys_reihen = _zahl(self.text, MUSTER_PHYSISCH)
        (eingabe,) = _zahl(self.text, MUSTER_EINGABE)
        spalten, zeilen = _zahl(self.text, MUSTER_BLOCK)
        self.assertEqual((eingabe, phys_spalten, phys_reihen),
                         (spalten, spalten, zeilen),
                         "die Anleitung widerspricht sich: physische Anordnung, "
                         "eingetippte Spaltenzahl und versprochenes Ergebnis "
                         "muessen dasselbe Raster meinen")
        self.assertEqual(spalten * zeilen, self._kopfzahl(),
                         "das versprochene Raster fasst nicht genau alle Zonen")

        zellen = self._block_aufteilen(eingabe)
        self.assertEqual(len(zellen), self._kopfzahl(),
                         "nicht alle Koepfe wurden platziert")
        self.assertEqual({c for c, _r in zellen}, set(range(spalten)))
        self.assertEqual({r for _c, r in zellen}, set(range(zeilen)))

    def test_das_textbild_zeigt_dasselbe_raster(self):
        """Das Textbild ist das, was ein Leser wirklich anschaut — es muss
        dasselbe sagen wie die Zahlen daneben."""
        spalten, zeilen = _zahl(self.text, MUSTER_BLOCK)
        bild = re.search(r"Nach „als Block…\".*?\n```", self.text, re.S)
        self.assertIsNotNone(bild, "das Textbild zum Blockaufteilen fehlt")
        reihen = [re.findall(r"K(\d+)", z) for z in bild.group(0).splitlines()]
        reihen = [r for r in reihen if len(r) > 1]
        self.assertEqual(len(reihen), zeilen, "andere Zeilenzahl im Bild")
        for r in reihen:
            self.assertEqual(len(r), spalten, f"Zeile mit {len(r)} Zellen")
        nummern = [int(n) for r in reihen for n in r]
        self.assertEqual(nummern, list(range(1, self._kopfzahl() + 1)),
                         "das Bild nummeriert die Koepfe anders als das Geraet "
                         "sie zaehlt (1 … N, zeilenweise)")

    def test_die_warnung_vor_dem_verkleinern_beschreibt_das_verhalten(self):
        """Die Anleitung warnt, dass Verkleinern Zellen ausserhalb wegwirft —
        ohne Nachfrage. Diese Warnung ist nur so lange richtig, wie das Raster
        sich wirklich so verhaelt; wuerde LightOS eines Tages fragen, muesste
        die Warnung weg."""
        warnung = ("**Verkleinern entfernt Zellen außerhalb des neuen Rasters**"
                   " — ohne Nachfrage.")
        self.assertIn(warnung, self.text, "die Warnung fehlt in der Anleitung")
        gw = self.view._grid_widget
        gw.set_grid(8, 2)
        gw.positions.clear()
        gw.positions[(0, 0)] = 2
        gw.positions[(7, 0)] = 3          # ausserhalb des kuenftigen Rasters
        gw.set_grid(3, 1)
        self.assertIn((0, 0), gw.positions, "die Zelle im Raster ist weg")
        self.assertNotIn((7, 0), gw.positions,
                         "die Zelle ausserhalb ueberlebt — dann warnt die "
                         "Anleitung vor etwas, das nicht passiert")

    # ── 3. Namen aus der Datenbank ───────────────────────────────────────────

    def test_namenszusatz_und_ordner_der_auto_gruppe_stehen_im_text(self):
        _gid, name, _cols, _rows, folder = self._auto_gruppe()
        zusatz = name[len(LABEL):].strip()
        self.assertTrue(zusatz, "Gruppenname ohne Zusatz — Test misst nichts")
        self.assertIn(zusatz, self.text,
                      f"die Auto-Gruppe heisst '{name}'; der Zusatz '{zusatz}' "
                      "fehlt in der Anleitung")
        # Als `Code` zitiert, nicht als blosses Wort: „Multi-Head" allein stuende
        # sonst zufaellig irgendwo im Fliesstext und die Pruefung waere erfuellt,
        # ohne dass der Ordner ueberhaupt genannt wird.
        self.assertIn(f"`{folder}`", self.text,
                      f"die Auto-Gruppe liegt im Ordner '{folder}' — der Ordner "
                      "muss als `Code` in der Anleitung stehen")

    def test_zusammenlegen_ordner_und_quellgruppen_stimmen(self):
        from src.core.database.models import FixtureGroup
        self._auto_gruppe()
        self._par_gruppe()
        quellen = set(self._gruppen_ids())
        neu_gid, _texte = self._zusammenlegen_dialog(auswahl=2)
        self.assertIsNotNone(neu_gid, "Zusammenlegen hat keine Gruppe erzeugt")
        with self.state._session() as s:
            neu = s.get(FixtureGroup, neu_gid)
            ordner = neu.folder
            rows = int(neu.rows)
        self.assertIn(f"`{ordner}`", self.text,
                      f"zusammengelegte Gruppen landen im Ordner '{ordner}' — "
                      "das muss als `Code` in der Anleitung stehen")
        self.assertTrue(quellen.issubset(set(self._gruppen_ids())),
                        "die Quellgruppen sind verschwunden — die Anleitung "
                        "sagt, sie bleiben erhalten")
        self.assertEqual(rows, 2, "gestapelt wird untereinander (1+1 Zeile)")

    def test_abgebrochener_dialog_legt_nichts_an(self):
        """Gegenprobe zum Test darueber: ohne Auswahl darf nichts entstehen —
        sonst belegt das Zusammenlegen oben gar nichts."""
        self._auto_gruppe()
        self._par_gruppe()
        neu_gid, _texte = self._zusammenlegen_dialog(auswahl=0)
        self.assertIsNone(neu_gid)

    # ── 4. Auffindbarkeit ────────────────────────────────────────────────────

    def test_die_anleitung_steht_im_index(self):
        """Eine Anleitung gegen „findet niemand", die selbst niemand findet,
        loest das Problem nicht."""
        with open(INDEX, encoding="utf-8") as fh:
            index = fh.read()
        self.assertIn(INDEX_PFAD, index,
                      "docs/ANLEITUNGEN.md verlinkt die Anleitung nicht")


class ZahlenLeserTest(unittest.TestCase):
    """Der Marker-Leser selbst — ohne Qt, ohne DB.

    ★ Positivkontrolle in beide Richtungen: er muss die richtige Zahl finden
    UND laut werden, wenn der Marker verschwunden oder doppelt ist. Ohne den
    zweiten Teil koennte eine Umformulierung der Anleitung alle Zahlen-Gates
    lautlos abschalten — dann waeren sie gruen, weil sie nichts mehr pruefen.
    """

    def test_findet_die_zahlen_des_markers(self):
        self.assertEqual(_zahl("Ergebnis: **12 Spalten × 4 Zeilen**.",
                               MUSTER_BLOCK), (12, 4))
        self.assertEqual(_zahl("… **48 einzeln färbbare Zonen** (= Köpfe)",
                               MUSTER_ZONEN), (48,))

    def test_fehlender_marker_ist_ein_fehler(self):
        with self.assertRaises(AssertionError):
            _zahl("Ergebnis: 12 Spalten und 4 Zeilen.", MUSTER_BLOCK)

    def test_doppelter_marker_ist_ein_fehler(self):
        doppelt = ("Ergebnis: **12 Spalten × 4 Zeilen**.\n"
                   "Ergebnis: **8 Spalten × 6 Zeilen**.")
        with self.assertRaises(AssertionError):
            _zahl(doppelt, MUSTER_BLOCK)


if __name__ == "__main__":
    unittest.main()
