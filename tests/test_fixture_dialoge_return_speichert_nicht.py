"""FM-30: `Return` in einem Eingabefeld darf kein Fixture-Profil speichern.

Beide Profil-Dialoge — der einfache Fixture-Editor
(``src/ui/widgets/fixture_editor.py``) und der Generator
(``src/ui/widgets/fixture_generator.py``) — haengen ihren Speichern-Knopf in eine
``QDialogButtonBox``. Die macht den ersten Knopf mit AcceptRole automatisch zum
Standardknopf; ein `Return` in IRGENDEINEM Feld loeste damit das Speichern des
GANZEN Profils aus. Gemessen im Generator: eine getippte Rasterzahl plus Return
legte ein halb eingegebenes Profil in der Bibliothek an und schloss den Dialog —
ohne Warnung. Im Generator wiegt es schwerer, weil er ein bestehendes Profil
nicht wieder OEFFNEN kann: die Fehlangabe ist mit ihm nicht mehr zu berichtigen.

★ Gemessen wird ueber den ECHTEN Weg: ``QTest.keyClick`` an das echte Widget,
  danach ein Blick in die DB. Ein direkter Aufruf von ``dlg._save()`` oder
  ``dlg.accept()`` haette den Befund gar nicht sichtbar gemacht — er liegt
  ausschliesslich in der Tastenzustellung von Qt.

★ Gemessen werden alle Tastenvarianten, die ``QDialog::keyPressEvent`` auf den
  Standardknopf leitet — ``Key_Return``, ``Key_Enter`` und der ECHTE
  Ziffernblock-Enter (``Key_Enter`` MIT ``KeypadModifier``). Nachbesserung nach
  Gegenpruefung zu PR #669: vorher stand hier nur ``Key_Enter`` ohne Modifier,
  und das ist NICHT die Ziffernblock-Taste. Belegt: streicht man
  ``Qt.KeyboardModifier.KeypadModifier`` aus der Bedingung beider Dialoge,
  blieben alle acht damaligen Tests gruen, waehrend ein Ziffernblock-Nutzer
  wieder ein halbes Profil in die Bibliothek schrieb. ``RETURN_TASTEN`` haelt
  die drei Varianten an EINER Stelle; geprueft wird nach JEDER Taste einzeln,
  damit die Fehlermeldung die schuldige Taste nennt.

★ Gemessen werden beide im BACKLOG genannten Felder: das RASTERFELD (Spinbox)
  und das KANALFELD (die Kanaltabelle des Modus-Tabs). Das Kanalfeld war die
  Abnahmebedingung des Items und fehlte bis zur Gegenpruefung — auf ``main``
  speicherte ein Return mit Fokus auf der Kanaltabelle in BEIDEN Dialogen.

★ Die Positivkontrollen sind hier die eigentliche Gefahr, nicht der Befund: ein
  abgeschalteter Speichern-Knopf waere schlimmer als das Problem. Gemessen sind
  je Dialog GENAU die vier Bedienwege, die der Kommentar ueber ``keyPressEvent``
  als "absichtlich unveraendert" zusagt: der MAUSKLICK auf "Speichern", `Escape`,
  `Return` im offenen Zellen-Editor der Kanaltabelle (der Editor verbraucht die
  Taste selbst und committet nur die Zelle) und `Return` auf dem FOKUSSIERTEN
  Speichern-Knopf — Letzteres ist der einzige verbliebene Speicherweg fuer
  Tastatur-Bedienung und war ebenfalls ungewacht.

★ Falle aus #659: headless (``QT_QPA_PLATFORM=offscreen``) bekommt ein Dialog
  ohne ausdrueckliche Groesse Zeilen der Hoehe 0. Ein Knopf ist dann
  ``isVisible() == True``, hat aber ``QSize(x, 0)`` und eine leere
  ``visibleRegion()`` — ein ``QTest.mouseClick`` landet still daneben, ohne
  Fehler und ohne Wirkung. Darum ``resize(1000, 900)`` in ``_dialog_zeigen``
  UND eine ausdrueckliche Probe, dass der Knopf eine sichtbare Flaeche hat.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database import fixture_db as fdb
from src.core.database.models import FixtureProfile
from src.ui.widgets import fixture_editor as editor_module
from src.ui.widgets import fixture_generator as generator_module


_app = QApplication.instance() or QApplication([])


#: Die Tastenvarianten, die ``QDialog::keyPressEvent`` auf den Standardknopf
#: leitet — und die der Fix darum allesamt abfangen muss. Seine Bedingung
#: lautet dort woertlich::
#:
#:     !e->modifiers() || (e->modifiers() & Qt::KeypadModifier
#:                         && e->key() == Qt::Key_Enter)
#: Die dritte ist die entscheidende: ``QTest.keyClick(w, Qt.Key_Enter)`` sendet
#: NoModifier und ist damit NICHT die Taste des Ziffernblocks; ein echter
#: Numpad-Enter traegt ``KeypadModifier``, und genau diesen Fall behandelt
#: ``QDialog::keyPressEvent`` mit einem eigenen Zweig.
RETURN_TASTEN = (
    ("Return", Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
    ("Enter", Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier),
    ("Ziffernblock-Enter", Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier),
    # ★ Die vierte ist der Fall, an dem die erste Fassung des Fixes zerbrach:
    # sie verglich `e.modifiers()` per GLEICHHEIT gegen `KeypadModifier`, und
    # ein Ziffernblock-Enter, bei dem Qt noch ein weiteres Flag meldet, fiel
    # durch — landete in `super()` und klickte den Standardknopf. Qts eigene
    # Bedingung fragt `modifiers() & KeypadModifier`, nicht `==`.
    ("Ziffernblock-Enter mit Zusatzflag", Qt.Key.Key_Enter,
     Qt.KeyboardModifier.KeypadModifier | Qt.KeyboardModifier.GroupSwitchModifier),
)


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets wirklich
# abbauen — `deleteLater()` allein stellt `DeferredDelete` nie zu.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class _DialogBasis(unittest.TestCase):
    """Gemeinsame Test-DB + Dialog-Helfer fuer beide Profil-Dialoge."""

    def setUp(self):
        fd, pfad = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(pfad) and os.remove(pfad))
        self.engine = fdb.get_engine(pfad)
        self.addCleanup(self.engine.dispose)

        # Beide Dialoge speichern ueber `fixture_db.engine()` — der Editor
        # direkt, der Generator ueber `create_user_profile`. Ein Patch am
        # gecachten Modul-Engine trifft deshalb BEIDE echten Speicherwege,
        # ohne eine einzige Speicherfunktion durch eine Attrappe zu ersetzen.
        self.engine_patch = mock.patch.object(fdb, "_engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.assertEqual(self._profile_in_db(), [],
                         "Test-DB startet nicht leer — die Messung waere wertlos.")

        for modul in (editor_module, generator_module):
            for name in ("information", "warning", "question"):
                p = mock.patch.object(modul.QMessageBox, name)
                p.start()
                self.addCleanup(p.stop)

    def _profile_in_db(self) -> list[str]:
        with Session(self.engine) as s:
            return [p.name for p in
                    s.execute(select(FixtureProfile)).scalars().all()]

    def _dialog_zeigen(self, dlg):
        # ★ #659: ohne ausdrueckliche Groesse bekommt der Dialog headless Zeilen
        #   der Hoehe 0; ein QTest.mouseClick landet dann still daneben.
        dlg.resize(1000, 900)
        dlg.show()
        _app.processEvents()
        self.addCleanup(_app.processEvents)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def _speichern_knopf(self, dlg) -> QPushButton:
        box = dlg.findChild(QDialogButtonBox)
        self.assertIsNotNone(box, "Kein QDialogButtonBox im Dialog gefunden.")
        btn = box.button(QDialogButtonBox.StandardButton.Save)
        self.assertIsNotNone(btn, "Kein Speichern-Knopf im ButtonBox gefunden.")
        return btn

    def _knopf_ist_wirklich_klickbar(self, btn: QPushButton):
        """#659-Wache: `isVisible()` allein genuegt nicht."""
        self.assertTrue(btn.isVisible(), "Speichern-Knopf ist nicht sichtbar.")
        self.assertTrue(btn.isEnabled(), "Speichern-Knopf ist nicht aktiv.")
        self.assertGreater(btn.height(), 0,
                           f"Speichern-Knopf hat Hoehe 0 ({btn.size()}) — ein "
                           f"Klick landet still daneben.")
        self.assertFalse(btn.visibleRegion().isEmpty(),
                         "Speichern-Knopf hat keine sichtbare Flaeche — ein "
                         "Klick landet still daneben.")

    def _rasterzahl_tippen(self, feld, ziffer: str = "4"):
        """Tippt eine Rasterzahl in eine Spinbox — ueber die Tastatur, nicht
        ueber ``setValue``.

        ``selectAll`` vorweg, damit die Ziffer die vorhandene 0 ERSETZT statt
        sich daneben zu setzen (sonst haengt der Endwert an der Cursorposition:
        gemessen 40 statt 4)."""
        feld.setFocus()
        _app.processEvents()
        feld.lineEdit().selectAll()
        QTest.keyClicks(feld, ziffer)
        _app.processEvents()

    def _saved_id_von(self, dlg):
        """``saved_id`` gibt es nur am Generator; der Editor fuehrt kein
        oeffentliches Gegenstueck. ``getattr`` statt Fallunterscheidung, damit
        beide Dialoge durch denselben Helfer laufen."""
        return getattr(dlg, "saved_id", None)

    def _jede_return_taste_speichert_nicht(self, dlg, ziel, wo: str):
        """Schickt Return, Enter und den ECHTEN Ziffernblock-Enter an ``ziel``
        und prueft NACH JEDER EINZELNEN Taste, dass nichts gespeichert wurde und
        der Dialog noch offen ist.

        Einzeln geprueft, nicht am Ende gesammelt: sonst nennt die Fehlermeldung
        die schuldige Taste nicht — und genau daran ist die erste Fassung dieses
        Waechters gescheitert, die den Ziffernblock gar nicht erst gedrueckt
        hat."""
        for name, taste, mod in RETURN_TASTEN:
            QTest.keyClick(ziel, taste, mod)
            _app.processEvents()
            self.assertEqual(
                self._profile_in_db(), [],
                f"{name} in {wo} hat ein Profil in der Bibliothek angelegt.")
            self.assertIsNone(
                self._saved_id_von(dlg),
                f"{name} in {wo} hat gespeichert (saved_id gesetzt).")
            self.assertTrue(
                dlg.isVisible(), f"{name} in {wo} hat den Dialog geschlossen.")

    def _kanaltabelle(self, dlg):
        """Die Kanaltabelle des aktiven Modus-Tabs — das im BACKLOG genannte
        KANALFELD. Beide Dialoge fuehren sie als ``_tbl`` am Modus-Tab."""
        tab = dlg._tabs.currentWidget()
        tbl = getattr(tab, "_tbl", None)
        self.assertIsNotNone(tbl, "Kein Kanaltabelle (_tbl) im Modus-Tab.")
        self.assertGreater(tbl.rowCount(), 0,
                           "Die Kanaltabelle ist leer — dann misst der "
                           "Kanalfeld-Test gar nichts.")
        tbl.setFocus()
        tbl.setCurrentCell(0, 1)
        _app.processEvents()
        self.assertTrue(tbl.hasFocus(),
                        "Die Kanaltabelle hat den Fokus nicht bekommen.")
        return tbl

    # ── Die vier Bedienwege, die der Kommentar ueber `keyPressEvent` als
    #    "absichtlich unveraendert" zusagt. Zwei davon (Zellen-Editor,
    #    fokussierter Knopf) waren bis zur Gegenpruefung zu #669 ungewacht.
    def _pruefe_zellen_editor_committet_nur_die_zelle(self, dlg):
        tbl = self._kanaltabelle(dlg)
        alt = tbl.item(0, 1).text()
        tbl.editItem(tbl.item(0, 1))
        _app.processEvents()
        zellen_editor = _app.focusWidget()
        self.assertIsNotNone(zellen_editor,
                             "Der Zellen-Editor hat sich nicht geoeffnet.")
        self.assertIsNot(zellen_editor, tbl,
                         "Der Fokus liegt noch auf der Tabelle — es ist gar "
                         "kein Zellen-Editor offen.")
        zellen_editor.selectAll()
        QTest.keyClicks(zellen_editor, "FM30 Kanalname")
        QTest.keyClick(zellen_editor, Qt.Key.Key_Return)
        _app.processEvents()

        self.assertNotEqual(alt, "FM30 Kanalname",
                            "Die Probe schreibt denselben Text, der schon "
                            "dastand — sie kann nichts zeigen.")
        self.assertEqual(tbl.item(0, 1).text(), "FM30 Kanalname",
                         "Return im Zellen-Editor committet den getippten "
                         "Kanalnamen nicht mehr.")
        self.assertEqual(tbl.state(), tbl.State.NoState,
                         "Der Zellen-Editor ist nach Return noch offen.")
        self.assertEqual(self._profile_in_db(), [],
                         "Return im Zellen-Editor hat ein Profil angelegt.")
        self.assertTrue(dlg.isVisible(),
                        "Return im Zellen-Editor hat den Dialog geschlossen.")

    def _pruefe_return_auf_fokussiertem_knopf_speichert(self, dlg, erwartet: str):
        btn = self._speichern_knopf(dlg)
        self._knopf_ist_wirklich_klickbar(btn)
        btn.setFocus()
        _app.processEvents()
        self.assertTrue(btn.hasFocus(),
                        "Der Speichern-Knopf hat den Fokus nicht bekommen — "
                        "die Probe misst dann nicht den Tastaturweg.")

        QTest.keyClick(btn, Qt.Key.Key_Return)
        _app.processEvents()

        self.assertEqual(self._profile_in_db(), [erwartet],
                         "Return auf dem FOKUSSIERTEN Speichern-Knopf speichert "
                         "nicht mehr — das ist der einzige Speicherweg fuer "
                         "Tastatur-Bedienung.")
        self.assertFalse(dlg.isVisible(),
                         "Der Dialog blieb nach dem Speichern offen.")


class GeneratorReturnTest(_DialogBasis):
    """Der Generator — hier wurde der Befund gemessen."""

    def _dialog(self):
        return self._dialog_zeigen(generator_module.FixtureGeneratorDialog())

    def test_return_im_rasterfeld_speichert_nicht(self):
        dlg = self._dialog()
        tab = dlg._tabs.currentWidget()
        feld = tab._spin_grid_rows
        self._rasterzahl_tippen(feld)

        # Wache gegen Leerlauf: die Tasten muessen das echte Widget erreicht
        # haben — sonst misst der Test nur eine verschluckte Eingabe.
        self.assertEqual(feld.value(), 4,
                         "Die getippte Rasterzahl kam nicht im Feld an — der "
                         "Return-Test misst dann gar nichts.")
        self._jede_return_taste_speichert_nicht(dlg, feld, "einem Rasterfeld")

    def test_return_im_kanalfeld_speichert_nicht(self):
        """Die zweite Haelfte der Abnahmebedingung aus dem BACKLOG.

        Auf ``main`` gemessen: ein Return mit Fokus auf der Kanaltabelle legte
        hier ein Profil an und schloss den Dialog."""
        dlg = self._dialog()
        tbl = self._kanaltabelle(dlg)
        self._jede_return_taste_speichert_nicht(dlg, tbl, "einem Kanalfeld")

    def test_return_im_kurznamen_speichert_nicht(self):
        dlg = self._dialog()
        feld = dlg._edit_short
        feld.clear()
        feld.setFocus()
        _app.processEvents()
        QTest.keyClicks(feld, "HALB")
        _app.processEvents()

        self.assertEqual(feld.text(), "HALB",
                         "Der getippte Kurzname kam nicht im Feld an.")
        self._jede_return_taste_speichert_nicht(dlg, feld, "dem Kurznamen-Feld")

    def test_klick_auf_speichern_speichert_weiterhin(self):
        """Positivkontrolle — ein abgeschalteter Knopf waere schlimmer."""
        dlg = self._dialog()
        dlg._edit_mfr.setText("FM30 Hersteller")
        dlg._edit_model.setText("FM30 Klickprobe")
        dlg._edit_short.setText("FM30KLICK")
        btn = self._speichern_knopf(dlg)
        self._knopf_ist_wirklich_klickbar(btn)

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        _app.processEvents()

        self.assertIsNotNone(dlg.saved_id,
                             "Der Klick auf Speichern hat nichts gespeichert.")
        self.assertEqual(self._profile_in_db(), ["FM30 Klickprobe"])
        self.assertFalse(dlg.isVisible(),
                         "Der Dialog blieb nach dem Speichern offen.")

    def test_escape_schliesst_den_dialog_weiterhin(self):
        """Positivkontrolle — ein nicht mehr schliessbarer Dialog waere schlimmer."""
        dlg = self._dialog()
        dlg._edit_short.setFocus()
        _app.processEvents()
        QTest.keyClick(dlg._edit_short, Qt.Key.Key_Escape)
        _app.processEvents()

        self.assertFalse(dlg.isVisible(), "Escape schliesst den Dialog nicht mehr.")
        self.assertIsNone(dlg.saved_id, "Escape hat gespeichert.")
        self.assertEqual(self._profile_in_db(), [])

    def test_return_im_zellen_editor_committet_weiterhin(self):
        """Positivkontrolle 3 von 4 — der Zellen-Editor der Kanaltabelle."""
        dlg = self._dialog()
        self._pruefe_zellen_editor_committet_nur_die_zelle(dlg)

    def test_return_auf_fokussiertem_speichern_knopf_speichert_weiterhin(self):
        """Positivkontrolle 4 von 4 — der einzige Tastaturweg zum Speichern."""
        dlg = self._dialog()
        dlg._edit_mfr.setText("FM30 Hersteller")
        dlg._edit_model.setText("FM30 Tastaturprobe")
        dlg._edit_short.setText("FM30TAST")
        self._pruefe_return_auf_fokussiertem_knopf_speichert(
            dlg, "FM30 Tastaturprobe")
        self.assertIsNotNone(dlg.saved_id,
                             "Return auf dem Speichern-Knopf hat kein Profil "
                             "angelegt (saved_id leer).")


class EditorReturnTest(_DialogBasis):
    """Der einfache Fixture-Editor — derselbe Standardknopf, dieselbe Falle."""

    def _dialog(self):
        dlg = self._dialog_zeigen(editor_module.FixtureEditorDialog())
        # Ein speicherbarer Zustand: sonst faellt `_save` schon an der
        # Pflichtfeld-Pruefung heraus und der Test waere gruen, ohne dass der
        # Standardknopf etwas mit dem Ergebnis zu tun haette.
        dlg._cb_manufacturer.setCurrentText("FM30 Hersteller")
        dlg._edit_name.setText("FM30 Editorprobe")
        dlg._edit_short.setText("FM30ED")
        tab = dlg._tabs.currentWidget()
        knopf = [b for b in tab.findChildren(QPushButton) if b.text() == "+ Channel"]
        self.assertEqual(len(knopf), 1, "Kein '+ Channel'-Knopf im Mode-Tab.")
        QTest.mouseClick(knopf[0], Qt.MouseButton.LeftButton)
        _app.processEvents()
        self.assertEqual(len(tab.channels), 1,
                         "Der Mode-Tab hat keinen Channel — dann kann auch der "
                         "Klick-Test nichts speichern.")
        return dlg

    def test_return_im_rasterfeld_speichert_nicht(self):
        dlg = self._dialog()
        tab = dlg._tabs.currentWidget()
        feld = tab._spin_grid_rows
        self._rasterzahl_tippen(feld)

        self.assertEqual(feld.value(), 4,
                         "Die getippte Rasterzahl kam nicht im Feld an.")
        self._jede_return_taste_speichert_nicht(dlg, feld, "einem Rasterfeld")

    def test_return_im_kanalfeld_speichert_nicht(self):
        """Die zweite Haelfte der Abnahmebedingung aus dem BACKLOG."""
        dlg = self._dialog()
        tbl = self._kanaltabelle(dlg)
        self._jede_return_taste_speichert_nicht(dlg, tbl, "einem Kanalfeld")

    def test_return_im_modellnamen_speichert_nicht(self):
        dlg = self._dialog()
        feld = dlg._edit_name
        feld.setFocus()
        _app.processEvents()
        self._jede_return_taste_speichert_nicht(dlg, feld, "dem Modell-Feld")

    def test_klick_auf_speichern_speichert_weiterhin(self):
        """Positivkontrolle."""
        dlg = self._dialog()
        btn = self._speichern_knopf(dlg)
        self._knopf_ist_wirklich_klickbar(btn)

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        _app.processEvents()

        self.assertEqual(self._profile_in_db(), ["FM30 Editorprobe"],
                         "Der Klick auf Speichern hat nichts gespeichert.")
        self.assertFalse(dlg.isVisible(),
                         "Der Dialog blieb nach dem Speichern offen.")

    def test_escape_schliesst_den_dialog_weiterhin(self):
        """Positivkontrolle."""
        dlg = self._dialog()
        dlg._edit_name.setFocus()
        _app.processEvents()
        QTest.keyClick(dlg._edit_name, Qt.Key.Key_Escape)
        _app.processEvents()

        self.assertFalse(dlg.isVisible(), "Escape schliesst den Dialog nicht mehr.")
        self.assertEqual(self._profile_in_db(), [])

    def test_return_im_zellen_editor_committet_weiterhin(self):
        """Positivkontrolle 3 von 4 — der Zellen-Editor der Kanaltabelle."""
        dlg = self._dialog()
        self._pruefe_zellen_editor_committet_nur_die_zelle(dlg)

    def test_return_auf_fokussiertem_speichern_knopf_speichert_weiterhin(self):
        """Positivkontrolle 4 von 4 — der einzige Tastaturweg zum Speichern."""
        dlg = self._dialog()
        self._pruefe_return_auf_fokussiertem_knopf_speichert(
            dlg, "FM30 Editorprobe")


if __name__ == "__main__":
    unittest.main()
