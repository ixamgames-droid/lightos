"""FM-23 — die Geometrie wird ueber die BEDIENELEMENTE gesetzt, nicht ueber die API.

**Warum es diese Datei gibt.** ``tests/test_fm23_editor_panel_geometrie.py``
misst den ganzen Weg von der Eingabe bis zum Renderer — aber die Eingabe selbst
setzt jeder dortige Test ueber ``tab.set_geometry(...)`` bzw.
``_add_mode(grid=..., weiss=...)`` und liest sie ueber ``get_geometry()``. Das
ist die Programmierschnittstelle, nicht das, was ein Mensch bedient.

★ **Gemessen, nicht vermutet.** Streicht man in ``_ModeTab.__init__`` die eine
Zeile ``layout.addLayout(geo_row)`` — die Spinboxen existieren dann noch als
Attribute, liegen aber in keinem Layout und damit in keinem Dialog —, bleiben
alle 10 Tests der Nachbardatei gruen. Der Nutzer haette kein einziges Feld mehr
vor sich, und keine Messung haette es bemerkt.

**Was diese Datei anders macht.** Sie kennt die Attributnamen der Spinboxen
nicht. Sie geht das **Layout** des aufgebauten Dialogs durch, ordnet die
Eingabefelder ueber die **Beschriftungen** zu, unter denen ein Mensch sie sucht
("Pixel-Raster:", "Weiß-Leiste:"), **tippt** die Zahlen dort hinein
(``QTest``-Tastendruecke auf die Zeileneditoren der Spinboxen) und **klickt**
den Speichern-Knopf des Dialogs. Geprueft wird danach die Datenbank — nicht der
Ruecklesewert eines Widgets.

Damit wird rot, was vorher gruen blieb:

* die Felder liegen in keinem Layout / keinem Dialog,
* die Felder sind unsichtbar,
* eine Beschriftung fehlt (dann ist das Feld fuer den Nutzer nicht zuordenbar),
* Zeilen und Spalten sind vertauscht,
* die Farb- und die Weiss-Eingabe sind vertauscht,
* ``_save`` liest eines der Felder nicht mit,
* der Ladeweg traegt die gespeicherte Form nicht in die sichtbaren Felder.

★ **Warum ``dlg._tabs`` trotzdem vorkommt.** Der Mode-Tab wird ueber das
Tab-Register des Dialogs angesteuert — das ist Navigation, keine Messung. Dass
die Felder wirklich IM Dialog haengen, sagt nicht dieser Zugriff, sondern
``spin.isVisible()`` am gezeigten Dialog: sichtbar ist ein Widget in Qt nur,
wenn die ganze Kette bis zum gezeigten Fenster steht. Ein Register, das nicht
im Dialog laege, koennte keine sichtbaren Felder tragen.

**Positivkontrollen** stehen unten: wer nichts eintippt, bekommt auch nichts
hinterlegt (der Editor darf keine Form erfinden — sonst haette jedes
selbstgebaute Panel das Weiss-Band zurueck, das CDX-52 abgeschafft hat), und
das Zuordnen ueber die Beschriftungen darf nicht nur im ersten Tab gelingen,
sondern muss auch fuer einen ueber den "+ Mode"-Knopf angelegten Modus klappen.

⚠️ **Was diese Datei NICHT behauptet.** Die Kanaele werden ueber den echten
"+ Channel"-Knopf angelegt, ihre Zahl aber nicht geprueft: ``_save`` legt pro
Modus nur den LETZTEN Kanal an (``s.add(fc)`` steht eine Ebene zu weit links,
also hinter der Kanalschleife statt darin). Das ist der schon gemeldete
Nebenbefund aus der Nachbardatei, unabhaengig von FM-23 — die Geometrie sitzt
am Modus, nicht am Kanal.
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

from src.core.database.fixture_db import get_engine            # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureProfile, create_all_idempotent)
from src.ui.widgets import fixture_editor as editor_module     # noqa: E402


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
# ════════════════════════════════════════════════════════════════════════════

def _in_layout_reihenfolge(w: QWidget) -> list[QWidget]:
    """Alle Widgets aus dem Layout von ``w`` — in der Reihenfolge auf dem Schirm.

    Bewusst ueber das **Layout** und nicht ueber ``findChildren``: gefragt ist
    nicht, ob es ein Objekt gibt, sondern ob es einen PLATZ im Dialog hat. Und
    die Reihenfolge ist keine Nebensache — sie ist es, woran ein Mensch
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


#: Beschriftung -> die beiden Felder, die darunter fallen. Ein Mensch sucht das
#: Feld unter seiner Aufschrift; genau so wird hier zugeordnet.
_UEBERSCHRIFTEN = (("raster", ("grid_rows", "grid_cols")),
                   ("wei", ("white_rows", "white_cols")))


def _geo_eingaben(tab: QWidget) -> dict[str, QSpinBox]:
    """Die vier Rasterfelder eines Mode-Tabs, zugeordnet ueber ihre Aufschrift.

    Kennt KEINEN Attributnamen des Produktionscodes. Findet die Felder nur,
    wenn sie im Layout des Tabs liegen und ihre Beschriftung dort steht.
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


def _tippe(spin: QSpinBox, wert: int) -> None:
    """Traegt ``wert`` so ein, wie ein Mensch es tut: markieren, tippen.

    Kein ``setValue`` — das waere wieder die Programmierschnittstelle. Und kein
    abschliessendes Return: in einem ``QDialog`` mit Standardknopf loest Return
    das Speichern aus (im Betrieb korrekt, hier waere es ein zweiter Klick).
    """
    zeile = spin.lineEdit()
    zeile.setFocus()
    QTest.keyClick(zeile, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(zeile, str(wert))


def _knopf(wurzel: QWidget, aufschrift: str) -> QPushButton:
    """Der sichtbare Knopf mit dieser Aufschrift — aus dem Layout, nicht per Name."""
    for w in _in_layout_reihenfolge(wurzel):
        if isinstance(w, QPushButton) and w.text() == aufschrift:
            return w
    raise AssertionError(f"Kein Knopf '{aufschrift}' im Dialog "
                         f"({[type(w).__name__ for w in _in_layout_reihenfolge(wurzel)]})")


class _EditorFall(unittest.TestCase):
    """Eigene Fixture-DB; der Dialog wird gezeigt und bedient."""

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)

        for ziel, name in ((editor_module, "engine"),):
            p = mock.patch.object(ziel, name, lambda: self.engine)
            p.start()
            self.addCleanup(p.stop)
        # Beide Meldungswege abfangen: `information` beendet das Speichern,
        # `warning` wuerde einen ABBRUCH modal anzeigen und den Lauf haengen
        # lassen. Deshalb als Attrappe MIT Zaehler — ein unbemerkter Abbruch
        # wuerde sonst als "nichts gespeichert" durchgehen.
        for feld, methode in (("info", "information"), ("warnung", "warning")):
            p = mock.patch.object(editor_module.QMessageBox, methode)
            setattr(self, feld, p.start())
            self.addCleanup(p.stop)

    # ── Bedienung ───────────────────────────────────────────────────────────

    def _dialog(self, fixture_id: int | None = None):
        dlg = editor_module.FixtureEditorDialog(fixture_id=fixture_id)
        self.addCleanup(dlg.deleteLater)
        dlg.show()
        _app.processEvents()
        return dlg

    def _kopf_ausfuellen(self, dlg, *, name: str, kurz: str, hersteller="Eigenbau"):
        """Hersteller/Modell/Kurzname eintippen, Typ auswaehlen."""
        QTest.keyClicks(dlg._cb_manufacturer.lineEdit(), hersteller)
        for feld, text in ((dlg._edit_name, name), (dlg._edit_short, kurz)):
            feld.setFocus()
            QTest.keyClick(feld, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClicks(feld, text)
        dlg._cb_type.setCurrentIndex(dlg._cb_type.findText("matrix"))

    def _kanaele_anlegen(self, tab, anzahl: int = 3):
        """Ueber den echten '+ Channel'-Knopf — ``_save`` verlangt Kanaele."""
        knopf = _knopf(tab, "+ Channel")
        for _ in range(anzahl):
            QTest.mouseClick(knopf, Qt.MouseButton.LeftButton)

    def _speichern_klicken(self, dlg):
        box = dlg.findChild(QDialogButtonBox)
        self.assertIsNotNone(box, "Kein QDialogButtonBox im Fixture-Editor")
        btn = box.button(QDialogButtonBox.StandardButton.Save)
        self.assertIsNotNone(btn, "Kein Speichern-Knopf im Fixture-Editor")
        self.assertTrue(btn.isVisible(), "Speichern-Knopf ist unsichtbar")
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        _app.processEvents()
        self.assertEqual(
            self.warnung.call_args_list, [],
            f"Das Speichern wurde abgebrochen: {self.warnung.call_args_list}")

    # ── Ablesen (Datenbank, nicht Widget) ───────────────────────────────────

    def _modi_aus_db(self, kurzname: str) -> dict:
        """Die gespeicherte Form — ueber den Kurznamen gesucht, nicht ueber
        ``dlg._saved_id``: gemessen wird, was in der DB steht."""
        with Session(self.engine) as s:
            treffer = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes))
                .where(FixtureProfile.short_name == kurzname)
            ).scalars().all()
            self.assertEqual(len(treffer), 1,
                             f"Genau ein Profil '{kurzname}' erwartet, "
                             f"{len(treffer)} gefunden")
            return {m.name: ((m.grid_rows, m.grid_cols),
                             (m.white_rows, m.white_cols))
                    for m in treffer[0].modes}

    def _panel_eintippen(self, *, grid=(4, 12), weiss=(1, 3),
                         name="Getipptes Panel", kurz="TIPP48"):
        """Der ganze Weg eines Menschen: Dialog auf, Felder finden, tippen,
        Speichern klicken. Gibt die vier gefundenen Eingabefelder zurueck."""
        dlg = self._dialog()
        self._kopf_ausfuellen(dlg, name=name, kurz=kurz)
        tab = dlg._tabs.currentWidget()
        self._kanaele_anlegen(tab)
        felder = _geo_eingaben(tab)
        self.assertEqual(sorted(felder), ["grid_cols", "grid_rows",
                                          "white_cols", "white_rows"],
                         "Die Rastereingaben sind im Dialog nicht auffindbar")
        for rolle, wert in (("grid_rows", grid[0]), ("grid_cols", grid[1]),
                            ("white_rows", weiss[0]), ("white_cols", weiss[1])):
            _tippe(felder[rolle], wert)
        self._speichern_klicken(dlg)
        return dlg, felder


# ════════════════════════════════════════════════════════════════════════════
# 1. Die Felder liegen wirklich im Dialog und sind bedienbar
# ════════════════════════════════════════════════════════════════════════════

class EingabefelderImDialogTest(_EditorFall):

    def test_vier_rasterfelder_liegen_sichtbar_im_dialog(self):
        """★ Der eigentliche Befund der Gegenpruefung: dass es die Felder gibt,
        hatte niemand gemessen. Gestrichenes ``layout.addLayout(geo_row)``
        liess die Nachbardatei komplett gruen."""
        dlg = self._dialog()
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
        VERSCHIEDENE Felder (keine wird doppelt vergeben), und im Tab steht
        kein weiteres Zahlenfeld, das unter keiner Aufschrift liegt — ein
        solches waere fuer den Nutzer nicht deutbar."""
        dlg = self._dialog()
        tab = dlg._tabs.currentWidget()
        zugeordnet = _geo_eingaben(tab)
        self.assertEqual(len({id(s) for s in zugeordnet.values()}), 4,
                         "Zwei Rollen zeigen auf dasselbe Feld")
        ohne_aufschrift = [w for w in _in_layout_reihenfolge(tab)
                           if isinstance(w, QSpinBox)
                           and id(w) not in {id(s) for s in zugeordnet.values()}]
        self.assertEqual(ohne_aufschrift, [],
                         "Zahlenfeld im Mode-Tab ohne zugehoerige Aufschrift")

    def test_jedes_rasterfeld_erklaert_sich_beim_hinsehen(self):
        """Die Zeile zeigt nur "Pixel-Raster: [0] x [0]". Was die 0 bedeutet —
        RATEN beim Farbraster, KEINE LEISTE beim Weiss — steht nirgends sonst
        als im Tooltip; ohne ihn ist das Feld stumm."""
        dlg = self._dialog()
        for rolle, spin in _geo_eingaben(dlg._tabs.currentWidget()).items():
            with self.subTest(rolle=rolle):
                self.assertTrue(spin.toolTip().strip(),
                                f"{rolle} hat keinen Tooltip")

    def test_getippte_zahl_wird_vom_feld_auch_angezeigt(self):
        """Positivkontrolle fuer das Tippen selbst: bliebe ``_tippe`` wirkungslos,
        wuerden alle Messungen unten nur Nullen vergleichen und trotzdem
        bestehen."""
        dlg = self._dialog()
        felder = _geo_eingaben(dlg._tabs.currentWidget())
        _tippe(felder["grid_cols"], 12)
        self.assertEqual(felder["grid_cols"].lineEdit().text(), "12")


# ════════════════════════════════════════════════════════════════════════════
# 2. ★★ Getippt -> geklickt -> in der Datenbank
# ════════════════════════════════════════════════════════════════════════════

class GetipptLandetInDerDatenbankTest(_EditorFall):

    def test_vier_verschiedene_zahlen_landen_an_ihrem_platz(self):
        """★ Vier UNTERSCHIEDLICHE Werte (4/12/1/3), damit jede Verwechslung
        auffaellt: Zeile gegen Spalte, Farbraster gegen Weiss-Leiste."""
        self._panel_eintippen(grid=(4, 12), weiss=(1, 3))
        self.assertEqual(self._modi_aus_db("TIPP48")["Default"],
                         ((4, 12), (1, 3)))

    def test_positivkontrolle_wer_nichts_eintippt_bekommt_nichts(self):
        """Der Editor darf keine Form ERFINDEN — sonst haette jedes
        selbstgebaute Panel wieder ein Weiss-Band (CDX-52)."""
        dlg = self._dialog()
        self._kopf_ausfuellen(dlg, name="Unberuehrt", kurz="TIPP00")
        self._kanaele_anlegen(dlg._tabs.currentWidget())
        # Kein einziger Tastendruck in die Rasterfelder.
        self._speichern_klicken(dlg)
        self.assertEqual(self._modi_aus_db("TIPP00")["Default"],
                         ((0, 0), (0, 0)))

    def test_nur_eine_zahl_eintippen_genuegt(self):
        """Der Alltagsfall: wer die Spaltenzahl kennt, tippt nur sie. Die
        uebrigen Felder duerfen dadurch nichts bekommen."""
        dlg = self._dialog()
        self._kopf_ausfuellen(dlg, name="Nur Spalten", kurz="TIPP0C")
        self._kanaele_anlegen(dlg._tabs.currentWidget())
        _tippe(_geo_eingaben(dlg._tabs.currentWidget())["grid_cols"], 12)
        self._speichern_klicken(dlg)
        self.assertEqual(self._modi_aus_db("TIPP0C")["Default"],
                         ((0, 12), (0, 0)))

    def test_ein_ueber_den_knopf_angelegter_modus_hat_die_felder_auch(self):
        """Positivkontrolle fuer die Zuordnung: sie darf nicht am ersten Tab
        haengen. '+ Mode' ist der einzige Weg, einen zweiten Modus anzulegen —
        und die Form gehoert zum MODUS, nicht zum Profil."""
        dlg = self._dialog()
        self._kopf_ausfuellen(dlg, name="Zwei Modi", kurz="TIPP2M")
        erster = dlg._tabs.currentWidget()
        self._kanaele_anlegen(erster)
        _tippe(_geo_eingaben(erster)["grid_rows"], 1)
        _tippe(_geo_eingaben(erster)["grid_cols"], 1)

        QTest.mouseClick(_knopf(dlg, "+ Mode"), Qt.MouseButton.LeftButton)
        _app.processEvents()
        zweiter = dlg._tabs.currentWidget()
        self.assertIsNot(zweiter, erster, "'+ Mode' hat keinen Tab angelegt")
        self._kanaele_anlegen(zweiter)
        felder = _geo_eingaben(zweiter)
        self.assertEqual(sorted(felder), ["grid_cols", "grid_rows",
                                          "white_cols", "white_rows"],
                         "Der zweite Modus hat keine Rastereingaben")
        _tippe(felder["grid_rows"], 4)
        _tippe(felder["grid_cols"], 12)
        _tippe(felder["white_rows"], 1)

        self._speichern_klicken(dlg)
        modi = self._modi_aus_db("TIPP2M")
        self.assertEqual(modi["Default"], ((1, 1), (0, 0)))
        self.assertEqual(modi["Mode 1"], ((4, 12), (1, 0)))


# ════════════════════════════════════════════════════════════════════════════
# 3. Zurueck in die sichtbaren Felder — und wieder hinaus
# ════════════════════════════════════════════════════════════════════════════

class ObergrenzeDerEingabeTest(_EditorFall):
    """``GEO_MAX = 256`` ist keine gegriffene Zahl, sondern die Stelle, an der
    ``panelGrid`` (``scene_src/fixtures/pixel_order.js``) die Pixelzahl kappt.
    Geklemmt wird bewusst NICHT in Python, sondern vom Feld selbst — also muss
    auch am Feld gemessen werden."""

    def _mit_getippter_zahl(self, ziffern: str, kurz: str):
        dlg = self._dialog()
        self._kopf_ausfuellen(dlg, name=f"Grenze {ziffern}", kurz=kurz)
        tab = dlg._tabs.currentWidget()
        self._kanaele_anlegen(tab)
        feld = _geo_eingaben(tab)["grid_cols"]
        _tippe(feld, ziffern)
        angezeigt = feld.lineEdit().text()
        self._speichern_klicken(dlg)
        return angezeigt, self._modi_aus_db(kurz)["Default"][0][1]

    def test_die_groesste_sinnvolle_zahl_wird_angenommen(self):
        """256 Spalten muessen durchgehen — waere die Grenze niedriger, fraesse
        das Feld die letzte Ziffer und der Nutzer bekaeme klaglos 25."""
        angezeigt, gespeichert = self._mit_getippter_zahl("256", "TIPP256")
        self.assertEqual((angezeigt, gespeichert), ("256", 256))

    def test_darueber_nimmt_das_feld_die_ziffer_nicht_mehr_an(self):
        """★ Positivkontrolle in der anderen Richtung: die Grenze WIRKT. Beim
        Tippen von "300" verweigert das Feld die dritte Ziffer und behaelt 30 —
        eine hoehere Grenze liesse hier eine 300 in die Bibliothek, die im 3D
        nie ein Pixel mehr zeigen koennte."""
        angezeigt, gespeichert = self._mit_getippter_zahl("300", "TIPP300")
        self.assertEqual((angezeigt, gespeichert), ("30", 30))


class RundwegUeberDieFelderTest(_EditorFall):

    def test_gespeicherte_form_steht_beim_wiederoeffnen_in_den_feldern(self):
        """Abgelesen wird der ANGEZEIGTE Text, nicht ``get_geometry()``: der
        Nutzer, der sein Profil nachbessert, sieht genau diese Zeichen."""
        self._panel_eintippen(grid=(4, 12), weiss=(1, 3))
        pid = self._profil_id("TIPP48")
        felder = _geo_eingaben(self._dialog(fixture_id=pid)._tabs.currentWidget())
        self.assertEqual(
            {r: felder[r].lineEdit().text() for r in sorted(felder)},
            {"grid_cols": "12", "grid_rows": "4",
             "white_cols": "3", "white_rows": "1"})

    def test_im_geoeffneten_dialog_geaenderte_zahl_ueberschreibt_die_alte(self):
        """★★ Der Weg, auf dem ``_save`` alle Modi verwirft und neu baut: was
        der zweite Durchgang nicht aus den Feldern liest, ist danach weg."""
        self._panel_eintippen(grid=(4, 12), weiss=(1, 3))
        dlg = self._dialog(fixture_id=self._profil_id("TIPP48"))
        _tippe(_geo_eingaben(dlg._tabs.currentWidget())["grid_rows"], 6)
        self._speichern_klicken(dlg)
        self.assertEqual(self._modi_aus_db("TIPP48")["Default"],
                         ((6, 12), (1, 3)))

    def test_positivkontrolle_nichts_anfassen_aendert_nichts(self):
        """Wer nur den Namen korrigiert, darf die Form nicht verlieren — und
        auch keine geschenkt bekommen."""
        self._panel_eintippen(grid=(4, 12), weiss=(1, 3))
        dlg = self._dialog(fixture_id=self._profil_id("TIPP48"))
        self._speichern_klicken(dlg)
        self.assertEqual(self._modi_aus_db("TIPP48")["Default"],
                         ((4, 12), (1, 3)))

    def _profil_id(self, kurzname: str) -> int:
        with Session(self.engine) as s:
            return s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == kurzname)).scalars().one()


if __name__ == "__main__":
    unittest.main()
