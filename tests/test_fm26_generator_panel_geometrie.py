"""FM-26 — auch der Fixture-GENERATOR kann die Panel-Geometrie hinterlegen.

**Der Rest von FM-23.** Der einfache Fixture-Editor hat die vier Rasterfelder
seit FM-23. Der **Generator** (Patch-View → „Generator") ist ein zweiter,
reicherer Dialog mit EIGENEM Modell (:class:`GenMode`) und eigenem Speicherweg
(``build_profile_payload`` → ``fixture_db.create_user_profile``) — dort fehlte
die Angabe an drei Stellen hintereinander: das Modell kannte sie nicht, das
Payload gab sie folglich nicht aus, und ``create_user_profile`` setzte
``FixtureMode`` ohne diese vier Spalten. Jede einzelne Stelle genuegt, damit
beim Renderer vier Nullen ankommen.

★ **Warum das der teurere der beiden Wege war.** Wer ein selbstgebautes Panel
anlegt, nimmt den Generator: er hat den **Live-Test am echten Geraet**, mit dem
man ueberhaupt erst herausfindet, welcher Kanal welche Zone schaltet. Genau
dieser Nutzer stand nach FM-23 weiter vor dem FM-23-Befund — sein Panel wurde
im 3D als geratenes Quadrat gezeichnet (aus 4x12 ein 7x7) und bekam seit CDX-52
auch kein Weiss-Band mehr.

**Wo gemessen wird.** Am Ende steht ``panel_grid_for``/``white_grid_for``
(``src/core/app_state.py``) — der Weg, den der 3D-Renderer geht (DB → Modus →
Wert). Das Payload ist ausdruecklich NICHT das Mass: es ist die Seitentuer, an
der die Kette schon zweimal weitergerissen ist (ein Payload mit den vier
Zahlen und ein ``create_user_profile``, das sie fallen laesst, sehen im
Payload-Test gleich aus). Die wenigen Payload-Tests unten stehen deshalb
bewusst als Nebenmessung am Schluss und nicht als Beweis.

**Wie eingegeben wird.** Nicht ueber ``set_geometry(...)`` — das waere wieder
die Programmierschnittstelle, und FM-23 hat gemessen, dass eine ganze
Testdatei gruen bleibt, wenn die Felder in keinem Layout haengen. Diese Datei
kennt die Attributnamen der Spinboxen nicht: sie geht das **Layout** des
gezeigten Dialogs durch, ordnet die Felder ueber ihre **Aufschriften** zu
("Pixel-Raster:", "Weiß-Leiste:"), **tippt** die Zahlen hinein und **klickt**
den Speichern-Knopf.

★★ **Die Abschlussmessung des Items** steht in
:class:`GeneratorUndEditorErgebenDasselbeTest`: dasselbe Panel wird EINMAL ueber
den Generator und EINMAL ueber den Editor angelegt — beide Male getippt, beide
Male ueber denselben Helfer, der die Felder nur an ihrer Aufschrift findet.
Danach muessen ``panel_grid_for``/``white_grid_for`` fuer beide Profile
dasselbe liefern. Dass der Helfer in BEIDEN Dialogen faendig wird, ist Teil der
Aussage: die Angabe heisst in beiden gleich, sonst findet der Nutzer sie im
zweiten Dialog nicht wieder.

**Positivkontrollen** in jedem Abschnitt: wer nichts eintippt, bekommt nichts
hinterlegt (der Generator darf keine Form ERFINDEN — sonst haette jedes
selbstgebaute Panel das Weiss-Band zurueck, das CDX-52 abgeschafft hat), eine
einzelne Zahl genuegt, und jeder Modus behaelt seine EIGENE Form.

⚠️ **Was diese Datei NICHT behauptet.** Sie prueft keine Kanalzahlen und keine
Bereiche des Generators — das tut ``tests/test_fixture_generator.py``. Und sie
sagt nichts ueber den QXF-Import des Generators (``model_from_qxf``), der die
Rasterform aus ``<Physical><Layout/>`` weiterhin nicht uebernimmt, obwohl der
QXF-Import der Bibliothek (``qxf_import``) es seit FM-23 tut; das ist ein
gemeldeter Nebenbefund und kein Gegenstand dieses Items.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                  # noqa: E402
from PySide6.QtTest import QTest                               # noqa: E402
from PySide6.QtWidgets import (                                # noqa: E402
    QApplication, QDialogButtonBox, QLabel, QLayout, QPushButton, QSpinBox,
    QWidget)
from sqlalchemy import select                                  # noqa: E402
from sqlalchemy.orm import Session, selectinload               # noqa: E402

from src.core.database import fixture_db as FDB                # noqa: E402
from src.core.database.fixture_db import get_engine            # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureProfile, PatchedFixture, create_all_idempotent)
from src.ui.widgets import fixture_editor as editor_module     # noqa: E402
from src.ui.widgets import fixture_generator as gen_module     # noqa: E402


_app = QApplication.instance() or QApplication([])

# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets wirklich
# abbauen (Muster + Begruendung: tests/_qt_lifecycle.py).
import pytest as _pytest_xplat15                               # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets        # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# ════════════════════════════════════════════════════════════════════════════
# Den Dialog so lesen, wie ein Mensch ihn sieht
#
# Bewusst hier ausgeschrieben und nicht aus der FM-23-Datei importiert: ein
# Test, der einen anderen Test importiert, macht dessen Innenleben zur
# Schnittstelle — und diese Helfer sind genau das, was NICHT stillschweigend
# mitwandern darf, wenn dort jemand etwas umbaut.
# ════════════════════════════════════════════════════════════════════════════

def _in_layout_reihenfolge(w: QWidget) -> list[QWidget]:
    """Alle Widgets aus dem Layout von ``w`` — in der Reihenfolge auf dem Schirm.

    Ueber das **Layout** und nicht ueber ``findChildren``: gefragt ist nicht,
    ob es ein Objekt gibt, sondern ob es einen PLATZ im Dialog hat. Und die
    Reihenfolge ist keine Nebensache — sie ist es, woran ein Mensch
    "Zeilen x Spalten" auseinanderhaelt.
    """
    out: list[QWidget] = []

    def rein(layout: QLayout):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            kind = item.widget()
            if kind is not None:
                out.append(kind)
                if kind.layout() is not None:
                    rein(kind.layout())
            elif item.layout() is not None:
                rein(item.layout())

    if w.layout() is not None:
        rein(w.layout())
    return out


#: Aufschrift -> die beiden Felder, die darunter fallen. Ein Mensch sucht das
#: Feld unter seiner Aufschrift; genau so wird hier zugeordnet. Die Stichworte
#: sind absichtlich kurz und gelten fuer BEIDE Dialoge — dass sie in beiden
#: passen, ist eine Aussage dieser Datei und kein Zufall.
_UEBERSCHRIFTEN = (("raster", ("grid_rows", "grid_cols")),
                   ("wei", ("white_rows", "white_cols")))


def _geo_eingaben(tab: QWidget) -> dict[str, QSpinBox]:
    """Die vier Rasterfelder eines Mode-Tabs, zugeordnet ueber ihre Aufschrift.

    Kennt KEINEN Attributnamen des Produktionscodes. Findet die Felder nur,
    wenn sie im Layout des Tabs liegen und ihre Aufschrift dort steht.
    """
    felder: dict[str, QSpinBox] = {}
    rollen: tuple[str, ...] = ()
    gefunden = 0
    for w in _in_layout_reihenfolge(tab):
        if isinstance(w, QLabel):
            text = w.text().casefold()
            for stichwort, neue_rollen in _UEBERSCHRIFTEN:
                if stichwort in text:
                    rollen, gefunden = neue_rollen, 0
                    break
        elif isinstance(w, QSpinBox) and gefunden < len(rollen):
            felder[rollen[gefunden]] = w
            gefunden += 1
    return felder


def _tippe(spin: QSpinBox, wert) -> None:
    """Traegt ``wert`` so ein, wie ein Mensch es tut: markieren, tippen.

    Kein ``setValue`` — das waere wieder die Programmierschnittstelle. Und kein
    abschliessendes Return: in einem ``QDialog`` mit Standardknopf loest Return
    das Speichern des GANZEN Profils aus (siehe den gemeldeten Nebenbefund),
    hier waere es ein zweiter Klick.
    """
    zeile = spin.lineEdit()
    zeile.setFocus()
    QTest.keyClick(zeile, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(zeile, str(wert))


def _knopf(wurzel: QWidget, aufschrift: str) -> QPushButton:
    """Der Knopf mit dieser Aufschrift — aus dem Layout, nicht per Attributname."""
    for w in _in_layout_reihenfolge(wurzel):
        if isinstance(w, QPushButton) and w.text() == aufschrift:
            return w
    raise AssertionError(f"Kein Knopf '{aufschrift}' im Dialog "
                         f"({[type(w).__name__ for w in _in_layout_reihenfolge(wurzel)]})")


def _patched(profile_id: int, mode_name: str, channel_count: int):
    """Ein gepatchtes Geraet, wie es der Renderer sieht (VIZ-50a-Weg)."""
    return PatchedFixture(fid=1, label="Panel", fixture_profile_id=profile_id,
                          mode_name=mode_name, universe=1, address=1,
                          channel_count=channel_count, fixture_type="matrix")


# ════════════════════════════════════════════════════════════════════════════
# Gemeinsame Testbasis: eigene Fixture-DB, beide Dialoge, app_state
# ════════════════════════════════════════════════════════════════════════════

class _GeneratorFall(unittest.TestCase):

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)

        # Der Generator speichert ueber `create_user_profile` OHNE `engine`-
        # Argument — er nimmt also die globale Bibliothek. Dieselbe Engine
        # liest `app_state` (panel_grid_for/white_grid_for).
        p = mock.patch.object(FDB, "_engine", self.engine)
        p.start()
        self.addCleanup(p.stop)
        # ... der einfache Editor ueber den importierten Namen.
        p2 = mock.patch.object(editor_module, "engine", lambda: self.engine)
        p2.start()
        self.addCleanup(p2.stop)

        # Meldungswege beider Dialoge abfangen. `warning` MIT Zaehler, weil ein
        # Abbruch sonst als "nichts gespeichert" durchginge; `question` beantwortet
        # die Rueckfrage bei Validierungsfehlern mit Ja.
        self.warnung = {}
        for modul in (gen_module, editor_module):
            for methode in ("information", "warning", "question"):
                if not hasattr(modul.QMessageBox, methode):
                    continue
                pm = mock.patch.object(modul.QMessageBox, methode)
                attrappe = pm.start()
                self.addCleanup(pm.stop)
                if methode == "warning":
                    self.warnung[modul.__name__] = attrappe
                if methode == "question":
                    attrappe.return_value = \
                        modul.QMessageBox.StandardButton.Yes

        from src.core.app_state import clear_channel_cache
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)

    # ── Bedienung: Generator ────────────────────────────────────────────────

    def _generator(self):
        dlg = gen_module.FixtureGeneratorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg.show()
        _app.processEvents()
        return dlg

    def _gen_kopf(self, dlg, *, name: str, kurz: str, hersteller="Eigenbau"):
        for feld, text in ((dlg._edit_mfr, hersteller), (dlg._edit_model, name),
                           (dlg._edit_short, kurz)):
            feld.setFocus()
            QTest.keyClick(feld, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClicks(feld, text)
        dlg._cb_type.setCurrentText("matrix")

    def _speichern_klicken(self, dlg, modulname: str):
        box = dlg.findChild(QDialogButtonBox)
        self.assertIsNotNone(box, "Kein QDialogButtonBox im Dialog")
        btn = box.button(QDialogButtonBox.StandardButton.Save)
        self.assertIsNotNone(btn, "Kein Speichern-Knopf im Dialog")
        self.assertTrue(btn.isVisible(), "Speichern-Knopf ist unsichtbar")
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        _app.processEvents()
        warnung = self.warnung[modulname]
        self.assertEqual(warnung.call_args_list, [],
                         f"Das Speichern wurde abgebrochen: "
                         f"{warnung.call_args_list}")

    def _panel_ueber_generator(self, *, grid=(4, 12), weiss=(1, 3),
                               name="Getipptes Panel", kurz="GEN48"):
        """Der ganze Weg eines Menschen durch den Generator: Dialog auf, Kopf
        ausfuellen, Rasterfelder ueber ihre Aufschrift finden, tippen,
        Speichern klicken."""
        dlg = self._generator()
        self._gen_kopf(dlg, name=name, kurz=kurz)
        tab = dlg._tabs.currentWidget()
        felder = _geo_eingaben(tab)
        self.assertEqual(sorted(felder), ["grid_cols", "grid_rows",
                                          "white_cols", "white_rows"],
                         "Die Rastereingaben sind im Generator nicht auffindbar")
        for rolle, wert in (("grid_rows", grid[0]), ("grid_cols", grid[1]),
                            ("white_rows", weiss[0]), ("white_cols", weiss[1])):
            _tippe(felder[rolle], wert)
        self._speichern_klicken(dlg, gen_module.__name__)
        return dlg

    # ── Bedienung: der einfache Editor (fuer den Vergleich) ─────────────────

    def _panel_ueber_editor(self, *, grid=(4, 12), weiss=(1, 3),
                            name="Getipptes Panel", kurz="EDI48"):
        dlg = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg.show()
        _app.processEvents()
        QTest.keyClicks(dlg._cb_manufacturer.lineEdit(), "Eigenbau")
        for feld, text in ((dlg._edit_name, name), (dlg._edit_short, kurz)):
            feld.setFocus()
            QTest.keyClick(feld, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClicks(feld, text)
        dlg._cb_type.setCurrentText("matrix")
        tab = dlg._tabs.currentWidget()
        knopf = _knopf(tab, "+ Channel")
        for _ in range(4):
            QTest.mouseClick(knopf, Qt.MouseButton.LeftButton)
        felder = _geo_eingaben(tab)
        self.assertEqual(sorted(felder), ["grid_cols", "grid_rows",
                                          "white_cols", "white_rows"],
                         "Die Rastereingaben sind im Editor nicht auffindbar")
        for rolle, wert in (("grid_rows", grid[0]), ("grid_cols", grid[1]),
                            ("white_rows", weiss[0]), ("white_cols", weiss[1])):
            _tippe(felder[rolle], wert)
        self._speichern_klicken(dlg, editor_module.__name__)
        return dlg

    # ── Ablesen ─────────────────────────────────────────────────────────────

    def _profil(self, kurzname: str):
        """``(id, {modusname: ((grid), (weiss))})`` — ueber den Kurznamen
        gesucht, nicht ueber ``dlg.saved_id``: gemessen wird, was in der DB
        steht."""
        with Session(self.engine) as s:
            treffer = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes))
                .where(FixtureProfile.short_name == kurzname)
            ).scalars().all()
            self.assertEqual(len(treffer), 1,
                             f"Genau ein Profil '{kurzname}' erwartet, "
                             f"{len(treffer)} gefunden")
            prof = treffer[0]
            return prof.id, {m.name: ((m.grid_rows, m.grid_cols),
                                      (m.white_rows, m.white_cols))
                             for m in prof.modes}

    def _beim_renderer(self, kurzname: str, modus: str, kanaele: int):
        """Was ``panel_grid_for``/``white_grid_for`` fuer dieses Profil
        liefern — der Weg des 3D-Renderers, nicht das Payload."""
        from src.core.app_state import panel_grid_for, white_grid_for
        pid, _ = self._profil(kurzname)
        f = _patched(pid, modus, kanaele)
        return panel_grid_for(f), white_grid_for(f)


# ════════════════════════════════════════════════════════════════════════════
# 1. Die Felder liegen wirklich im Generator-Dialog
# ════════════════════════════════════════════════════════════════════════════

class EingabefelderImGeneratorTest(_GeneratorFall):

    def test_vier_rasterfelder_liegen_sichtbar_im_modustab(self):
        """★ Die Lehre aus FM-23: dass es die Felder gibt, muss gemessen
        werden. Haengen sie in keinem Layout, existieren sie als Attribute
        weiter — und jede Messung, die ueber ``set_geometry`` eingibt, bleibt
        gruen, waehrend der Nutzer kein Feld vor sich hat."""
        dlg = self._generator()
        tab = dlg._tabs.currentWidget()
        felder = _geo_eingaben(tab)
        self.assertEqual(sorted(felder), ["grid_cols", "grid_rows",
                                          "white_cols", "white_rows"])
        for rolle, spin in felder.items():
            with self.subTest(rolle=rolle):
                self.assertTrue(dlg.isAncestorOf(spin),
                                f"{rolle} haengt nicht im Dialog")
                self.assertTrue(spin.isVisible(), f"{rolle} ist unsichtbar")
                self.assertFalse(spin.visibleRegion().isEmpty(),
                                 f"{rolle} belegt keine Flaeche")
                self.assertTrue(spin.isEnabled(), f"{rolle} ist gesperrt")

    def test_kein_zahlenfeld_steht_ohne_aufschrift_im_modustab(self):
        """Zwei Aussagen in einer: die vier Rollen zeigen auf vier
        VERSCHIEDENE Felder, und im Mode-Tab steht kein weiteres Zahlenfeld
        ohne zugehoerige Aufschrift (ein solches waere nicht deutbar)."""
        dlg = self._generator()
        tab = dlg._tabs.currentWidget()
        zugeordnet = _geo_eingaben(tab)
        self.assertEqual(len({id(s) for s in zugeordnet.values()}), 4,
                         "Zwei Rollen zeigen auf dasselbe Feld")
        ohne = [w for w in _in_layout_reihenfolge(tab)
                if isinstance(w, QSpinBox)
                and id(w) not in {id(s) for s in zugeordnet.values()}]
        self.assertEqual(ohne, [],
                         "Zahlenfeld im Mode-Tab ohne zugehoerige Aufschrift")

    def test_jedes_rasterfeld_erklaert_sich_beim_hinsehen(self):
        """Die Zeile zeigt nur "Pixel-Raster: [0] x [0]". Was die 0 bedeutet —
        RATEN beim Farbraster, KEINE LEISTE beim Weiss — steht nirgends sonst
        als im Tooltip."""
        dlg = self._generator()
        felder = _geo_eingaben(dlg._tabs.currentWidget())
        # Ohne diese Zeile waere der Test bei FEHLENDEN Feldern gruen: eine
        # Schleife ueber ein leeres dict prueft nichts. Gemessen — auf dem
        # Stand vor FM-26 blieb genau dieser Test als einziger der Klasse
        # gruen, bis die Zusicherung hier stand.
        self.assertEqual(sorted(felder), ["grid_cols", "grid_rows",
                                          "white_cols", "white_rows"])
        for rolle, spin in felder.items():
            with self.subTest(rolle=rolle):
                self.assertTrue(spin.toolTip().strip(),
                                f"{rolle} hat keinen Tooltip")

    def test_getippte_zahl_wird_vom_feld_auch_angezeigt(self):
        """Positivkontrolle fuer das Tippen selbst: bliebe ``_tippe``
        wirkungslos, wuerden alle Messungen unten nur Nullen vergleichen und
        trotzdem bestehen."""
        dlg = self._generator()
        felder = _geo_eingaben(dlg._tabs.currentWidget())
        _tippe(felder["grid_cols"], 12)
        self.assertEqual(felder["grid_cols"].lineEdit().text(), "12")


# ════════════════════════════════════════════════════════════════════════════
# 2. ★★ Getippt -> geklickt -> beim Renderer angekommen
# ════════════════════════════════════════════════════════════════════════════

class VomGeneratorBisZumRendererTest(_GeneratorFall):

    def test_vier_verschiedene_zahlen_kommen_beim_renderer_an(self):
        """★ Der Kern des Items — und bewusst an ``panel_grid_for``/
        ``white_grid_for`` gemessen, nicht am Payload. Vier UNTERSCHIEDLICHE
        Werte (4/12/1/3), damit jede Verwechslung auffaellt: Zeile gegen
        Spalte, Farbraster gegen Weiss-Leiste."""
        self._panel_ueber_generator(grid=(4, 12), weiss=(1, 3))
        self.assertEqual(self._beim_renderer("GEN48", "Default", 4),
                         ((4, 12), (1, 3)))

    def test_dieselbe_form_steht_auch_in_der_datenbank(self):
        """Die Zwischenstation — hilft beim Eingrenzen, wenn oben etwas reisst
        (Dialog/Payload vs. Speicherweg)."""
        self._panel_ueber_generator(grid=(4, 12), weiss=(1, 3))
        _, modi = self._profil("GEN48")
        self.assertEqual(modi["Default"], ((4, 12), (1, 3)))

    def test_positivkontrolle_ohne_eingabe_raet_der_renderer_weiter(self):
        """``(0, 0)`` heisst bei der Rasterform WEITERRATEN und beim Weiss-Band
        NEIN — genau die CDX-52-Aussage. Der Generator darf keine Form
        ERFINDEN, sonst haette jedes selbstgebaute Panel sein Band zurueck."""
        dlg = self._generator()
        self._gen_kopf(dlg, name="Panel ohne Angabe", kurz="GEN00")
        # Kein einziger Tastendruck in die Rasterfelder.
        self._speichern_klicken(dlg, gen_module.__name__)
        self.assertEqual(self._beim_renderer("GEN00", "Default", 4),
                         ((0, 0), (0, 0)))

    def test_nur_eine_zahl_eintippen_genuegt(self):
        """Der Alltagsfall: wer die Spaltenzahl kennt, tippt nur sie. Die
        uebrigen Felder duerfen dadurch nichts bekommen — ``panelGrid`` zieht
        die fehlende Zahl aus der Pixelzahl."""
        dlg = self._generator()
        self._gen_kopf(dlg, name="Nur Spalten", kurz="GEN0C")
        _tippe(_geo_eingaben(dlg._tabs.currentWidget())["grid_cols"], 12)
        self._speichern_klicken(dlg, gen_module.__name__)
        self.assertEqual(self._beim_renderer("GEN0C", "Default", 4),
                         ((0, 12), (0, 0)))

    def test_ein_ueber_den_knopf_angelegter_modus_hat_seine_eigene_form(self):
        """★ Die Form gehoert zum MODUS: ein Panel mit 1-Zonen- und
        48-Pixel-Modus hat zwei Raster. '+ Modus' ist der einzige Weg, einen
        zweiten anzulegen — und der neue Tab braucht die Felder auch."""
        dlg = self._generator()
        self._gen_kopf(dlg, name="Zwei Modi", kurz="GEN2M")
        erster = dlg._tabs.currentWidget()
        _tippe(_geo_eingaben(erster)["grid_rows"], 1)
        _tippe(_geo_eingaben(erster)["grid_cols"], 1)

        QTest.mouseClick(_knopf(dlg, "+ Modus"), Qt.MouseButton.LeftButton)
        _app.processEvents()
        zweiter = dlg._tabs.currentWidget()
        self.assertIsNot(zweiter, erster, "'+ Modus' hat keinen Tab angelegt")
        felder = _geo_eingaben(zweiter)
        self.assertEqual(sorted(felder), ["grid_cols", "grid_rows",
                                          "white_cols", "white_rows"],
                         "Der zweite Modus hat keine Rastereingaben")
        _tippe(felder["grid_rows"], 4)
        _tippe(felder["grid_cols"], 12)
        _tippe(felder["white_rows"], 1)
        self._speichern_klicken(dlg, gen_module.__name__)

        _, modi = self._profil("GEN2M")
        self.assertEqual(modi["Default"], ((1, 1), (0, 0)))
        self.assertEqual(modi["Modus 1"], ((4, 12), (1, 0)))
        # Und beide auch auf dem Renderer-Weg, ueber den Modusnamen aufgeloest.
        self.assertEqual(self._beim_renderer("GEN2M", "Modus 1", 1),
                         ((4, 12), (1, 0)))


# ════════════════════════════════════════════════════════════════════════════
# 3. ★★ Die Abschlussmessung: Generator == Editor
# ════════════════════════════════════════════════════════════════════════════

class GeneratorUndEditorErgebenDasselbeTest(_GeneratorFall):

    def test_beide_dialoge_ergeben_dieselbe_form_beim_renderer(self):
        """Das „Fertig, wenn" des Items. Beide Profile werden getippt
        angelegt; verglichen wird, was der 3D-Renderer bekommt.

        ★ Verglichen wird NICHT nur "gleich": vier Nullen waeren auch gleich.
        Deshalb steht der erwartete Wert daneben."""
        self._panel_ueber_generator(grid=(4, 12), weiss=(1, 3), kurz="GEN48")
        self._panel_ueber_editor(grid=(4, 12), weiss=(1, 3), kurz="EDI48")

        aus_generator = self._beim_renderer("GEN48", "Default", 4)
        aus_editor = self._beim_renderer("EDI48", "Default", 4)
        self.assertEqual(aus_generator, aus_editor,
                         "Generator und Editor legen dasselbe Panel mit "
                         "verschiedener Form an")
        self.assertEqual(aus_generator, ((4, 12), (1, 3)),
                         "Beide Wege liefern uebereinstimmend das FALSCHE")

    def test_positivkontrolle_beide_erfinden_nichts(self):
        """Die andere Richtung: ohne Eingabe muessen BEIDE bei (0,0) bleiben.
        Ein Dialog, der eine Form erfaende, waere hier rot — und die
        Gleichheit oben waere sonst auch mit zwei erfundenen Formen zu haben."""
        dlg = self._generator()
        self._gen_kopf(dlg, name="Leer Generator", kurz="GEN0X")
        self._speichern_klicken(dlg, gen_module.__name__)

        dlg2 = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg2.deleteLater)
        dlg2.show()
        _app.processEvents()
        QTest.keyClicks(dlg2._cb_manufacturer.lineEdit(), "Eigenbau")
        dlg2._edit_name.setText("Leer Editor")
        dlg2._edit_short.setText("EDI0X")
        tab = dlg2._tabs.currentWidget()
        QTest.mouseClick(_knopf(tab, "+ Channel"), Qt.MouseButton.LeftButton)
        self._speichern_klicken(dlg2, editor_module.__name__)

        self.assertEqual(self._beim_renderer("GEN0X", "Default", 4),
                         ((0, 0), (0, 0)))
        self.assertEqual(self._beim_renderer("EDI0X", "Default", 1),
                         ((0, 0), (0, 0)))


# ════════════════════════════════════════════════════════════════════════════
# 4. Nebenmessung: Modell und Speicherweg ohne Dialog
#
# ⚠️ Bewusst NACH der Messung am echten Weg und bewusst klein gehalten. Ein
#    Payload mit den vier Zahlen beweist nichts ueber das, was in der
#    Bibliothek landet — genau diese Luecke war der Befund. Hier stehen nur
#    die Faelle, die ein Dialog gar nicht erzeugen KANN (die Spinbox klemmt
#    schon), die ``build_profile_payload``/``create_user_profile`` aber sehen:
#    Handbau, Import, aeltere Payloads.
# ════════════════════════════════════════════════════════════════════════════

class ModellUndSpeicherwegTest(unittest.TestCase):

    def _engine(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        eng = get_engine(path)
        self.addCleanup(eng.dispose)
        create_all_idempotent(eng)
        return eng

    def _modell(self, **geo):
        return gen_module.GeneratorModel(
            manufacturer="Eigenbau", model="Panel", short_name="PAY48",
            fixture_type="matrix",
            modes=[gen_module.GenMode(
                "Default", [gen_module.GenChannel("Rot", "color_r", 0, 255)],
                **geo)])

    def _gespeicherte_form(self, payload) -> tuple:
        from src.core.database.models import FixtureMode
        eng = self._engine()
        pid = gen_module.save_generated_profile(payload, engine=eng)
        with Session(eng) as s:
            m = s.execute(select(FixtureMode).where(
                FixtureMode.fixture_id == pid)).scalars().one()
            return ((m.grid_rows, m.grid_cols), (m.white_rows, m.white_cols))

    def test_das_modell_traegt_die_form_bis_in_die_bibliothek(self):
        payload = gen_module.build_profile_payload(
            self._modell(grid_rows=4, grid_cols=12, white_rows=1, white_cols=3))
        self.assertEqual(self._gespeicherte_form(payload), ((4, 12), (1, 3)))

    def test_ein_payload_ohne_die_schluessel_bleibt_bei_null(self):
        """Rueckwaertsvertraeglichkeit: ein von Hand gebautes oder aelteres
        Payload kennt die vier Schluessel nicht — das muss "nicht hinterlegt"
        heissen und darf nicht krachen."""
        payload = gen_module.build_profile_payload(self._modell())
        for schluessel in ("grid_rows", "grid_cols", "white_rows", "white_cols"):
            payload["modes"][0].pop(schluessel, None)
        self.assertEqual(self._gespeicherte_form(payload), ((0, 0), (0, 0)))

    def test_negative_zahlen_kommen_gar_nicht_erst_ins_payload(self):
        """★ Der Fall, den FM-23 im QXF-Weg gefunden hat: ``rows * cols <= 1``
        faengt zwei negative Zahlen nicht (minus mal minus ist positiv). Ueber
        den Dialog unerreichbar (die Spinbox klemmt), ueber Modell und Import
        nicht.

        Gemessen wird hier absichtlich das PAYLOAD und nicht die DB: es gibt
        zwei Waechter hintereinander (``_clamp_geo`` beim Bauen,
        ``_geo_wert`` beim Schreiben), und einer verdeckt den anderen. Faellt
        nur EINER aus, muss genau EIN Test rot werden — sonst wandert die
        Sicherung unbemerkt von der einen Stelle zur anderen."""
        payload = gen_module.build_profile_payload(
            self._modell(grid_rows=-4, grid_cols=-3))
        modus = payload["modes"][0]
        self.assertEqual((modus["grid_rows"], modus["grid_cols"]), (0, 0))

    def test_ein_fremdes_payload_mit_negativen_zahlen_wird_keine_form(self):
        """Der zweite Waechter, allein gemessen: ``create_user_profile`` sieht
        auch Payloads, die nie durch ``build_profile_payload`` gelaufen sind
        (Handbau, andere Aufrufer). Deshalb ist dieses Payload hier von Hand
        gebaut und NICHT ueber den Generator erzeugt."""
        payload = {
            "manufacturer": "Eigenbau", "short_mfr": "EIGEN",
            "name": "Handgebautes Panel", "short_name": "HAND48",
            "fixture_type": "matrix", "source": "user",
            "modes": [{"name": "Default", "channel_count": 1,
                       "grid_rows": -4, "grid_cols": -3,
                       "white_rows": -1, "white_cols": -1,
                       "channels": [{"name": "Rot", "attribute": "color_r"}]}],
        }
        self.assertEqual(self._gespeicherte_form(payload), ((0, 0), (0, 0)))

    def test_unsinnig_grosse_zahl_wird_auf_die_obergrenze_gekappt(self):
        """``GEO_MAX`` ist die Stelle, an der ``panelGrid`` die Pixelzahl
        kappt — darueber koennte nie ein Pixel mehr erscheinen."""
        payload = gen_module.build_profile_payload(
            self._modell(grid_rows=1, grid_cols=99999))
        self.assertEqual(self._gespeicherte_form(payload),
                         ((1, editor_module.GEO_MAX), (0, 0)))


if __name__ == "__main__":
    unittest.main()
