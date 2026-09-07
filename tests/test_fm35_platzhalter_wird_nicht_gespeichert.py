"""FM-35 — ein Klick auf "Speichern" darf kein Platzhalter-Profil anlegen.

**Der Befund, am laufenden Code gemessen (Sonde: echter ``QTest.mouseClick``
auf den Speichern-Knopf, danach Blick in eine Temp-DB).** Vor dem Fix legte
ein EINZIGER Mausklick unmittelbar nach dem Oeffnen des Generators die Zeile
``(1, 'Generic', 'Neues Fixture', 'NEUES FI', 'user')`` in der Bibliothek an,
``saved_id`` war ``1``, der Dialog war zu, und es erschien KEINE Warnung. Im
Fixture-Editor genuegten zwei Klicks ("+ Channel", "Speichern") fuer
``(1, 'ADB', 'Neues Fixture', 'NEUES FI', 'user')``. Nach dem Fix: 0 Zeilen,
``saved_id is None``, Dialog offen, genau eine ``QMessageBox.warning``.

⚠️ **Warum nicht der im Item genannte Hebel.** Das Item vermutete ein leeres
Pflichtfeld (Kurzname/Hersteller). Beide erreichen die DB nie leer bzw. sind
gueltig (``Generic`` ist ein echter Hersteller). Blockieren muss der
unveraenderte PLATZHALTER-Modellname — deshalb misst diese Datei genau den.

⚠️ **Warum die Test-DB Hersteller enthaelt.** Auf einer LEEREN DB faengt im
Editor zufaellig "Hersteller fehlt." den Klick ab (die Hersteller-Auswahl ist
dann leer) und der Test misst am Gegenstand vorbei. ``setUp`` legt darum
Hersteller an, und jede Messung belegt zusaetzlich, dass die gezeigte Warnung
NICHT die Hersteller-Warnung ist.

⚠️ **Warum jeder Klick seine Vorbedingung zusichert.** Ein
``QTest.mouseClick`` auf einen unsichtbaren, gesperrten, hoehenlosen oder
verdeckten Knopf landet still daneben — der Test waere dann gruen, ohne je
etwas ausgeloest zu haben. ``_klick`` prueft deshalb isVisible/isEnabled/
height/visibleRegion, bevor er klickt.

★ **Die Gegenproben tragen den halben Wert dieser Datei** (Hausregel 6). Ein
Fix, der das Speichern schlicht abschaltet, bestuende jede Sperr-Pruefung.
Deshalb wird gemessen, dass ein echter Name UNVERAENDERT speichert, dass ein
Name, der zufaellig mit dem Platzhalter BEGINNT ("Neues Fixture Mk II"),
durchgeht, und dass die bestehenden Leer-Pruefungen des Editors weiter
greifen.

★ **Alltagszustand statt Bequemzustand** (Hausregel 5): eine Sonde je Dialog
trifft ein weit ausgefuelltes Profil (zweiter Modus, Kanaele, Kurzname,
Leistung, Notizen) mit stehengebliebenem Platzhalter-Namen — genau der Fall,
den eine auf "frisch geoeffnet" verengte Wache durchliesse.

★ **Eine Frage, eine Stelle** (Hausregel 7): ``EineFunktionFuerBeideTest``
haelt fest, dass beide Dialoge ueber ``kopfformular.kopf_beanstandung``
antworten (nachgewiesen mit einer Attrappe, die BEIDE Dialoge sichtbar
umsteuert) und dass der Platzhalter-Text in keinem der beiden Dialog-Module
mehr woertlich steht.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtWidgets import (                                 # noqa: E402
    QApplication, QDialogButtonBox, QPushButton)
from sqlalchemy.orm import Session                              # noqa: E402

from src.core.database import fixture_db as fdb                 # noqa: E402
from src.core.database.fixture_db import get_engine             # noqa: E402
from src.core.database.models import (                          # noqa: E402
    Manufacturer, FixtureProfile, create_all_idempotent)
from src.core.kopfformular import (                             # noqa: E402
    PLATZHALTER_MODELL, ist_platzhalter_modell, kopf_beanstandung)
from src.ui.widgets import fixture_editor as ed_mod             # noqa: E402
from src.ui.widgets import fixture_generator as gen_mod         # noqa: E402


_app = QApplication.instance() or QApplication([])

# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets abbauen.
import pytest as _pytest_xplat15                                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets         # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# Ein Name, der mit dem Platzhalter BEGINNT und trotzdem echt ist.
NAME_MIT_PLATZHALTER_PRAEFIX = PLATZHALTER_MODELL + " Mk II"
ECHTER_NAME = "Sondengeraet 500"


class _FM35Fall(unittest.TestCase):
    """Gemeinsame Umgebung: eigene DB mit Herstellern, echte Dialoge,
    attrappierte (aber MITGESCHRIEBENE) Meldungsfenster."""

    def setUp(self):
        fd, pfad = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(pfad) and os.remove(pfad))
        self.engine = get_engine(pfad)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        # ⚠️ Ohne Hersteller faengt im Editor "Hersteller fehlt." den Klick ab.
        with Session(self.engine) as s:
            s.add(Manufacturer(name="ADB", short_name="ADB"))
            s.add(Manufacturer(name="Generic", short_name="GENERIC"))
            s.commit()

        # Der Generator speichert ueber die globale Engine von fixture_db,
        # der Editor ueber den in sein Modul importierten Namen.
        p = mock.patch.object(fdb, "_engine", self.engine)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(ed_mod, "engine", lambda: self.engine)
        p.start()
        self.addCleanup(p.stop)

        # Meldungsfenster wuerden headless blockieren. Sie werden attrappiert
        # UND mitgeschrieben — der Text ist das Messergebnis, nicht Beiwerk.
        self.warnungen: list[tuple[str, str]] = []
        self.infos: list[tuple[str, str]] = []
        for modul in (gen_mod, ed_mod):
            p = mock.patch.object(
                modul.QMessageBox, "warning",
                side_effect=lambda _p, titel, text, *a, **k:
                    self.warnungen.append((titel, text)))
            p.start()
            self.addCleanup(p.stop)
            p = mock.patch.object(
                modul.QMessageBox, "information",
                side_effect=lambda _p, titel, text, *a, **k:
                    self.infos.append((titel, text)))
            p.start()
            self.addCleanup(p.stop)
        # Die Fehler-Rueckfrage des Generators darf die Messung nicht
        # aufhalten; "Ja" ist der ungnaedigste Fall fuer den Fix.
        p = mock.patch.object(
            gen_mod.QMessageBox, "question",
            return_value=gen_mod.QMessageBox.StandardButton.Yes)
        p.start()
        self.addCleanup(p.stop)

    # ── Hilfen ──────────────────────────────────────────────────────────

    def _zeilen(self) -> list[tuple]:
        """Was wirklich in der Bibliothek steht — die Wahrheit zum Vergleich."""
        with Session(self.engine) as s:
            return [(p.id, p.manufacturer.name if p.manufacturer else None,
                     p.name, p.short_name, p.source)
                    for p in s.query(FixtureProfile).all()]

    def _klick(self, knopf, wo: str):
        """Klickt WIRKLICH — und belegt vorher, dass der Klick ankommt."""
        self.assertIsNotNone(knopf, f"Vorbedingung: Knopf '{wo}' nicht gefunden.")
        _app.processEvents()
        self.assertTrue(knopf.isVisible(), f"Vorbedingung: '{wo}' unsichtbar.")
        self.assertTrue(knopf.isEnabled(), f"Vorbedingung: '{wo}' gesperrt.")
        self.assertGreater(knopf.height(), 0, f"Vorbedingung: '{wo}' hat Hoehe 0.")
        self.assertFalse(knopf.visibleRegion().isEmpty(),
                         f"Vorbedingung: '{wo}' ist verdeckt, der Klick "
                         "wuerde still danebengehen.")
        QTest.mouseClick(knopf, Qt.MouseButton.LeftButton,
                         pos=knopf.rect().center())
        _app.processEvents()

    def _speicherknopf(self, dlg):
        for box in dlg.findChildren(QDialogButtonBox):
            knopf = box.button(QDialogButtonBox.StandardButton.Save)
            if knopf is not None:
                return knopf
        return None

    def _knopf_mit_text(self, dlg, text: str):
        for knopf in dlg.findChildren(QPushButton):
            if knopf.text() == text:
                return knopf
        return None

    def _generator(self):
        """Ein echter, sichtbarer Generator-Dialog — kein Nachbau."""
        dlg = gen_mod.FixtureGeneratorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg.show()
        _app.processEvents()
        return dlg

    def _editor(self, *, mit_kanal: bool = True):
        """Ein echter, sichtbarer Editor-Dialog; auf Wunsch mit dem Klick auf
        "+ Channel", ohne den der Modus-Check den Speichern-Klick abfaengt."""
        dlg = ed_mod.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg.show()
        _app.processEvents()
        if mit_kanal:
            self._klick(self._knopf_mit_text(dlg, "+ Channel"), "+ Channel")
        return dlg

    def _speichern_klicken(self, dlg):
        self._klick(self._speicherknopf(dlg), "Speichern")

    # ── zusammengesetzte Zusicherungen ──────────────────────────────────

    def _erwarte_blockiert(self, dlg, wo: str):
        """Nichts angelegt, genau eine Warnung, Dialog OFFEN."""
        self.assertEqual([], self._zeilen(),
                         f"{wo}: es wurde trotzdem ein Profil angelegt.")
        self.assertIsNone(getattr(dlg, "saved_id", "<fehlt>"),
                          f"{wo}: saved_id ist gesetzt.")
        self.assertEqual(1, len(self.warnungen),
                         f"{wo}: erwartet genau eine Warnung, bekommen "
                         f"{self.warnungen!r}.")
        self.assertEqual([], self.infos,
                         f"{wo}: es erschien eine Erfolgsmeldung.")
        self.assertTrue(dlg.isVisible(), f"{wo}: der Dialog wurde geschlossen.")
        self.assertNotEqual(1, dlg.result(), f"{wo}: der Dialog hat akzeptiert.")

    def _erwarte_platzhalter_warnung(self, wo: str):
        """Die Warnung ist die PLATZHALTER-Warnung — nicht zufaellig die
        Hersteller- oder Modus-Warnung, die am Gegenstand vorbeimisst."""
        titel, text = self.warnungen[-1]
        self.assertEqual(
            kopf_beanstandung("ADB", PLATZHALTER_MODELL), text,
            f"{wo}: es hat eine ANDERE Wache abgefangen: {text!r}")
        self.assertIn(PLATZHALTER_MODELL, text,
                      f"{wo}: die Warnung benennt den Platzhalter nicht.")

    def _erwarte_gespeichert(self, dlg, name: str, wo: str):
        zeilen = self._zeilen()
        self.assertEqual([], self.warnungen,
                         f"{wo}: unerwartet abgewiesen mit {self.warnungen!r}.")
        self.assertEqual(1, len(zeilen), f"{wo}: erwartet genau ein Profil, "
                                         f"bekommen {zeilen!r}.")
        self.assertEqual(name, zeilen[0][2], f"{wo}: falscher Name gespeichert.")
        self.assertEqual(1, dlg.result(), f"{wo}: der Dialog hat nicht "
                                          "akzeptiert.")


class GeneratorEinKlickTest(_FM35Fall):
    """(1) Generator: EIN Klick nach dem Oeffnen legt nichts an."""

    def test_ein_klick_direkt_nach_dem_oeffnen_legt_nichts_an(self):
        dlg = self._generator()
        # Vorbedingungen: der Platzhalter steht wirklich im Feld, die DB ist
        # leer, und der Modus-Check (die einzige alte Wache) wuerde NICHT
        # abfangen — sonst misst der Test an FM-35 vorbei.
        self.assertEqual(PLATZHALTER_MODELL, dlg._edit_model.text())
        self.assertEqual([], self._zeilen())
        dlg._sync_all()
        self.assertTrue(any(m.channels for m in dlg._model.modes),
                        "Vorbedingung: der Default-Modus hat keine Kanaele — "
                        "dann faengt der Modus-Check ab und nicht die "
                        "Kopf-Pruefung.")

        self._speichern_klicken(dlg)

        self._erwarte_blockiert(dlg, "Generator, ein Klick")
        self._erwarte_platzhalter_warnung("Generator, ein Klick")


class EditorZweiKlicksTest(_FM35Fall):
    """(2) Editor: "+ Channel", dann "Speichern" legt ebenfalls nichts an."""

    def test_channel_und_speichern_legt_nichts_an(self):
        dlg = self._editor()
        # Vorbedingungen: Platzhalter im Feld, ein echter Hersteller
        # vorgewaehlt (sonst faengt "Hersteller fehlt." ab), DB leer.
        self.assertEqual(PLATZHALTER_MODELL, dlg._edit_name.text())
        self.assertTrue(dlg._cb_manufacturer.currentText().strip(),
                        "Vorbedingung: kein Hersteller vorgewaehlt — dann "
                        "misst der Test die falsche Wache.")
        self.assertEqual([], self._zeilen())

        self._speichern_klicken(dlg)

        self._erwarte_blockiert(dlg, "Editor, zwei Klicks")
        self._erwarte_platzhalter_warnung("Editor, zwei Klicks")

    def test_ohne_kanal_faengt_weiter_der_modus_check_ab(self):
        """GEGENPROBE zur Reihenfolge: ohne "+ Channel" bleibt es beim
        bestehenden Modus-Hinweis — die neue Wache hat ihn nicht verdraengt.
        (Der Editor prueft den Kopf zuerst, also warnt er hier ueber den
        Platzhalter; entscheidend ist, dass NICHT gespeichert wird und der
        Dialog offen bleibt.)"""
        dlg = self._editor(mit_kanal=False)
        dlg._edit_name.setText(ECHTER_NAME)
        self._speichern_klicken(dlg)
        self.assertEqual([], self._zeilen())
        self.assertTrue(dlg.isVisible())
        self.assertEqual(1, len(self.warnungen))
        self.assertIn("Channels", self.warnungen[-1][1],
                      "Der Modus-Check meldet sich nicht mehr: "
                      f"{self.warnungen!r}")


class AlltagszustandTest(_FM35Fall):
    """⚠️ Hausregel 5: die Wache darf nicht auf "frisch geoeffnet" verengt
    sein. Beide Dialoge werden hier weit ausgefuellt — nur der Modellname
    bleibt der Platzhalter."""

    def test_generator_weit_ausgefuellt_mit_platzhalter_name_blockiert(self):
        dlg = self._generator()
        dlg._edit_mfr.setText("ADB")
        dlg._edit_short.setText("SONDE")
        dlg._spin_power.setValue(250)
        dlg._edit_notes.setText("Notiz aus dem Alltag")
        dlg._add_mode()
        _app.processEvents()
        # Vorbedingung: der Dialog ist wirklich NICHT mehr im Frischzustand.
        dlg._sync_all()
        self.assertGreater(len(dlg._model.modes), 1,
                           "Vorbedingung: kein zweiter Modus angelegt.")
        self.assertEqual("SONDE", dlg._model.short_name)
        self.assertEqual(PLATZHALTER_MODELL, dlg._edit_model.text())

        self._speichern_klicken(dlg)

        self._erwarte_blockiert(dlg, "Generator, Alltagszustand")
        self._erwarte_platzhalter_warnung("Generator, Alltagszustand")

    def test_editor_weit_ausgefuellt_mit_platzhalter_name_blockiert(self):
        dlg = self._editor()
        dlg._cb_manufacturer.setCurrentText("ADB")
        dlg._edit_short.setText("SONDE")
        dlg._spin_power.setValue(250)
        dlg._add_mode(name="Zweiter", channels=[
            {"name": "Dimmer", "attribute": "intensity", "default": 0}])
        _app.processEvents()
        # Vorbedingung: mehrere Modi, alle mit Kanaelen.
        self.assertGreater(dlg._tabs.count(), 1,
                           "Vorbedingung: kein zweiter Modus angelegt.")
        for i in range(dlg._tabs.count()):
            self.assertTrue(dlg._tabs.widget(i).get_data()[1],
                            f"Vorbedingung: Modus {i} hat keine Kanaele — "
                            "dann faengt der Modus-Check ab.")
        self.assertEqual(PLATZHALTER_MODELL, dlg._edit_name.text())

        self._speichern_klicken(dlg)

        self._erwarte_blockiert(dlg, "Editor, Alltagszustand")
        self._erwarte_platzhalter_warnung("Editor, Alltagszustand")


class DieWacheHAENGTANKEINEMNEBENZUSTANDTest(_FM35Fall):
    """★★★ Vom Skeptiker erzwungen — vier Verengungen ueberlebten die erste
    Fassung, und zwar nicht nur diese Datei, sondern die ganze
    Regressionsliste (12 Dateien, 175 Tests).

    Die Mutationen hatten alle dieselbe Form: die Wache an einen NEBENZUSTAND
    haengen, den kein Test variiert —

        if beanstandung and not self._model.viz_model:      # 3D-Modell gewaehlt
        if beanstandung and self._cb_type.currentText() == "par":   # Typ

    Beide sind Dinge, die ein Nutzer im Alltag als ERSTES anfasst. Ein Nutzer,
    der ein 3D-Modell auswaehlt oder den Geraetetyp umstellt, haette die Wache
    damit stillschweigend abgeschaltet.

    ⚠️ Die Klasse ist allgemein: ein Test, der nur den bequemen Zustand kennt,
    nagelt eine Regel nur fuer diesen Zustand fest. Hier werden die
    Nebenzustaende deshalb ausdruecklich VARIIERT.
    """

    def test_generator_mit_gewaehltem_3d_modell_blockiert_weiterhin(self):
        dlg = self._generator()
        # Ueber das WIDGET setzen: `_sync_all` schreibt Widget -> Modell und
        # wuerde eine direkte Zuweisung ans Modell sofort wieder ueberschreiben.
        for i in range(dlg._cb_vizmodel.count()):
            if dlg._cb_vizmodel.itemData(i):
                dlg._cb_vizmodel.setCurrentIndex(i)
                break
        _app.processEvents()
        dlg._sync_all()
        self.assertTrue(dlg._model.viz_model,
                        "Vorbedingung: es ist ein 3D-Modell gesetzt")
        self.assertEqual(PLATZHALTER_MODELL, dlg._edit_model.text())

        self._speichern_klicken(dlg)

        self._erwarte_blockiert(dlg, "Generator mit 3D-Modell")
        self._erwarte_platzhalter_warnung("Generator mit 3D-Modell")

    def test_generator_mit_umgestelltem_typ_blockiert_weiterhin(self):
        dlg = self._generator()
        vorher = dlg._cb_type.currentText()
        for i in range(dlg._cb_type.count()):
            if dlg._cb_type.itemText(i) != vorher:
                dlg._cb_type.setCurrentIndex(i)
                break
        _app.processEvents()
        self.assertNotEqual(vorher, dlg._cb_type.currentText(),
                            "Vorbedingung: der Typ wurde wirklich umgestellt")

        self._speichern_klicken(dlg)

        self._erwarte_blockiert(dlg, "Generator mit anderem Typ")
        self._erwarte_platzhalter_warnung("Generator mit anderem Typ")

    def test_editor_mit_umgestelltem_typ_blockiert_weiterhin(self):
        dlg = self._editor()
        vorher = dlg._cb_type.currentText()
        for i in range(dlg._cb_type.count()):
            if dlg._cb_type.itemText(i) != vorher:
                dlg._cb_type.setCurrentIndex(i)
                break
        _app.processEvents()
        self.assertNotEqual(vorher, dlg._cb_type.currentText(),
                            "Vorbedingung: der Typ wurde wirklich umgestellt")

        self._speichern_klicken(dlg)

        self._erwarte_blockiert(dlg, "Editor mit anderem Typ")
        self._erwarte_platzhalter_warnung("Editor mit anderem Typ")

    def test_und_der_echte_name_speichert_in_all_diesen_zustaenden(self):
        """★★ Gegenprobe, sonst bestuende alles oben auch eine Wache, die
        IMMER blockiert — und der Dialog waere unbenutzbar."""
        dlg = self._generator()
        for i in range(dlg._cb_vizmodel.count()):
            if dlg._cb_vizmodel.itemData(i):
                dlg._cb_vizmodel.setCurrentIndex(i)
                break
        for i in range(dlg._cb_type.count()):
            if dlg._cb_type.itemText(i) != dlg._cb_type.currentText():
                dlg._cb_type.setCurrentIndex(i)
                break
        dlg._edit_model.setText("Sondengeraet 500")
        dlg._edit_mfr.setText("ADB")
        dlg._sync_all()
        _app.processEvents()

        self._speichern_klicken(dlg)

        self.assertEqual(1, len(self._zeilen()),
                         "ein echter Name speichert in diesen Zustaenden nicht")


class SchreibweisenTest(_FM35Fall):
    """Der unveraenderte Vorgabewert bleibt derselbe, egal wie er im Feld
    steht — sonst bliebe ein zweiter Weg an der Regel vorbei (Hausregel 8)."""

    def test_generator_kleinschreibung_und_leerraum_zaehlen_als_platzhalter(self):
        for geschrieben in (PLATZHALTER_MODELL.lower(),
                            "  " + PLATZHALTER_MODELL + "  ",
                            PLATZHALTER_MODELL.replace(" ", "   ")):
            with self.subTest(geschrieben=geschrieben):
                self.warnungen.clear()
                self.infos.clear()
                dlg = self._generator()
                dlg._edit_model.setText(geschrieben)
                self.assertEqual(geschrieben, dlg._edit_model.text(),
                                 "Vorbedingung: die Eingabe kam nicht an.")
                self._speichern_klicken(dlg)
                self._erwarte_blockiert(dlg, f"Generator {geschrieben!r}")
                self._erwarte_platzhalter_warnung(f"Generator {geschrieben!r}")

    def test_leerer_modellname_wird_im_generator_zum_platzhalter(self):
        """Der Generator ersetzt ein leeres Feld selbst durch den
        Platzhalter — dieser zweite Weg muss an derselben Wache enden."""
        dlg = self._generator()
        dlg._edit_model.setText("")
        self.assertEqual("", dlg._edit_model.text(),
                         "Vorbedingung: das Feld ist nicht leer.")
        self._speichern_klicken(dlg)
        self._erwarte_blockiert(dlg, "Generator, leeres Modellfeld")


class GegenprobeTest(_FM35Fall):
    """(4) Was sich NICHT aendern darf. Ein Fix, der das Speichern abschaltet,
    bestuende alle Sperr-Pruefungen — hier faellt er durch."""

    def test_generator_echter_name_speichert_unveraendert(self):
        dlg = self._generator()
        dlg._edit_model.setText(ECHTER_NAME)
        self.assertEqual(ECHTER_NAME, dlg._edit_model.text(),
                         "Vorbedingung: die Eingabe kam nicht an.")
        self._speichern_klicken(dlg)
        self._erwarte_gespeichert(dlg, ECHTER_NAME, "Generator, echter Name")
        self.assertEqual("Generic", self._zeilen()[0][1],
                         "Der Vorgabe-HERSTELLER 'Generic' ist gueltig und "
                         "darf nicht mitblockiert werden.")

    def test_editor_echter_name_speichert_unveraendert(self):
        dlg = self._editor()
        dlg._edit_name.setText(ECHTER_NAME)
        self._speichern_klicken(dlg)
        self._erwarte_gespeichert(dlg, ECHTER_NAME, "Editor, echter Name")

    def test_generator_name_mit_platzhalter_praefix_speichert(self):
        """"Neues Fixture Mk II" ist ein echter Geraetename — ein
        Praefix-Vergleich statt Gleichheit wuerde ihn verschlucken."""
        dlg = self._generator()
        dlg._edit_model.setText(NAME_MIT_PLATZHALTER_PRAEFIX)
        self.assertTrue(
            NAME_MIT_PLATZHALTER_PRAEFIX.startswith(PLATZHALTER_MODELL),
            "Vorbedingung: der Name beginnt gar nicht mit dem Platzhalter.")
        self._speichern_klicken(dlg)
        self._erwarte_gespeichert(dlg, NAME_MIT_PLATZHALTER_PRAEFIX,
                                  "Generator, Praefix-Name")

    def test_editor_name_mit_platzhalter_praefix_speichert(self):
        dlg = self._editor()
        dlg._edit_name.setText(NAME_MIT_PLATZHALTER_PRAEFIX)
        self._speichern_klicken(dlg)
        self._erwarte_gespeichert(dlg, NAME_MIT_PLATZHALTER_PRAEFIX,
                                  "Editor, Praefix-Name")

    def test_editor_leerer_hersteller_wird_weiter_abgewiesen(self):
        """Die bestehende Leer-Pruefung darf die neue Wache ueberleben."""
        dlg = self._editor()
        dlg._cb_manufacturer.setCurrentText("")
        dlg._edit_name.setText(ECHTER_NAME)
        self.assertEqual("", dlg._cb_manufacturer.currentText(),
                         "Vorbedingung: das Herstellerfeld ist nicht leer.")
        self._speichern_klicken(dlg)
        self._erwarte_blockiert(dlg, "Editor, leerer Hersteller")
        self.assertEqual(kopf_beanstandung("", ECHTER_NAME),
                         self.warnungen[-1][1])

    def test_editor_leerer_modellname_wird_weiter_abgewiesen(self):
        dlg = self._editor()
        dlg._edit_name.setText("   ")
        self._speichern_klicken(dlg)
        self._erwarte_blockiert(dlg, "Editor, leerer Modellname")
        self.assertEqual(kopf_beanstandung("ADB", ""), self.warnungen[-1][1])


class EineFunktionFuerBeideTest(_FM35Fall):
    """(3) Die Frage steht in GENAU EINER Funktion, und der Platzhalter-Text
    an genau EINER Stelle."""

    def _kopf_setzen_generator(self, dlg, hersteller, modell):
        dlg._edit_mfr.setText(hersteller)
        dlg._edit_model.setText(modell)

    def _kopf_setzen_editor(self, dlg, hersteller, modell):
        dlg._cb_manufacturer.setCurrentText(hersteller)
        dlg._edit_name.setText(modell)

    def _antwort(self, bauen, setzen, hersteller, modell):
        """Fuehrt EINEN Dialog mit diesem Kopf bis zum Speichern-Klick und
        gibt (Warntext oder None, wurde gespeichert)."""
        self.warnungen.clear()
        self.infos.clear()
        with Session(self.engine) as s:
            for p in s.query(FixtureProfile).all():
                s.delete(p)
            s.commit()
        dlg = bauen()
        setzen(dlg, hersteller, modell)
        self._speichern_klicken(dlg)
        warntext = self.warnungen[-1][1] if self.warnungen else None
        return warntext, bool(self._zeilen())

    def test_beide_dialoge_geben_dieselbe_auskunft(self):
        """Dieselbe Kopfeingabe, zwei Dialoge, EINE Antwort — sonst haetten
        wir wieder zwei Massstaebe (der Ausgangsbefund von FM-35)."""
        faelle = [
            ("ADB", PLATZHALTER_MODELL),
            ("ADB", PLATZHALTER_MODELL.lower()),
            ("ADB", "  " + PLATZHALTER_MODELL + " "),
            ("ADB", NAME_MIT_PLATZHALTER_PRAEFIX),
            ("Generic", ECHTER_NAME),
        ]
        for hersteller, modell in faelle:
            with self.subTest(hersteller=hersteller, modell=modell):
                aus_gen = self._antwort(self._generator,
                                        self._kopf_setzen_generator,
                                        hersteller, modell)
                aus_ed = self._antwort(self._editor,
                                       self._kopf_setzen_editor,
                                       hersteller, modell)
                self.assertEqual(aus_gen, aus_ed,
                                 f"Generator sagt {aus_gen!r}, Editor sagt "
                                 f"{aus_ed!r} — zwei Massstaebe.")

    def test_beide_dialoge_fragen_dieselbe_funktion(self):
        """Nachgewiesen, nicht behauptet: eine Attrappe an ``kopf_beanstandung``
        steuert BEIDE Dialoge sichtbar um. Ein Dialog mit eigener Kopie der
        Regel bliebe hier unbeeindruckt."""
        marke = "ATTRAPPE: Kopf unvollstaendig"
        for modul, bauen, setzen, wo in (
                (gen_mod, self._generator, self._kopf_setzen_generator,
                 "Generator"),
                (ed_mod, self._editor, self._kopf_setzen_editor, "Editor")):
            with self.subTest(dialog=wo):
                self.warnungen.clear()
                attrappe = mock.Mock(return_value=marke)
                with mock.patch.object(modul, "kopf_beanstandung", attrappe):
                    dlg = bauen()
                    setzen(dlg, "ADB", ECHTER_NAME)
                    self._speichern_klicken(dlg)
                self.assertTrue(attrappe.called,
                                f"{wo} fragt die gemeinsame Funktion nicht.")
                self.assertEqual(
                    ("ADB", ECHTER_NAME),
                    tuple(attrappe.call_args.args),
                    f"{wo} uebergibt nicht die Kopfeingabe des Nutzers.")
                self.assertEqual([("Speichern", marke)], self.warnungen,
                                 f"{wo} zeigt die Antwort der gemeinsamen "
                                 "Funktion nicht an.")
                self.assertEqual([], self._zeilen(),
                                 f"{wo} speichert trotz Beanstandung.")
                self.assertTrue(dlg.isVisible(),
                                f"{wo} schliesst trotz Beanstandung.")

    def test_platzhalter_text_steht_in_keinem_dialogmodul_woertlich(self):
        """Der Vorgabewert stand vor dem Fix vier Mal im Code. Er gehoert an
        EINE Stelle — beide Dialoge beziehen ihn von dort."""
        for modul in (gen_mod, ed_mod):
            with self.subTest(modul=modul.__name__):
                quelle = open(modul.__file__, encoding="utf-8").read()
                self.assertNotIn(
                    PLATZHALTER_MODELL, quelle,
                    f"{modul.__name__} enthaelt den Platzhalter-Text noch "
                    "woertlich — dann gibt es wieder zwei Wahrheiten.")

    def test_beide_dialoge_zeigen_denselben_vorgabewert_an(self):
        """Gegenstueck zur Quelltextprobe: die Felder muessen den Wert aus der
        gemeinsamen Konstante wirklich anzeigen."""
        self.assertEqual(PLATZHALTER_MODELL,
                         self._generator()._edit_model.text())
        self.assertEqual(PLATZHALTER_MODELL,
                         self._editor(mit_kanal=False)._edit_name.text())
        self.assertEqual(PLATZHALTER_MODELL, gen_mod.GeneratorModel().model)


class KopfformularFunktionTest(unittest.TestCase):
    """Die gemeinsame Funktion allein — schnelle Randfaelle ohne Qt."""

    def test_platzhalter_wird_beanstandet(self):
        self.assertIsNotNone(kopf_beanstandung("ADB", PLATZHALTER_MODELL))

    def test_echter_name_wird_nicht_beanstandet(self):
        self.assertIsNone(kopf_beanstandung("ADB", ECHTER_NAME))
        self.assertIsNone(kopf_beanstandung("ADB",
                                            NAME_MIT_PLATZHALTER_PRAEFIX))

    def test_praefix_ist_kein_platzhalter(self):
        self.assertFalse(ist_platzhalter_modell(NAME_MIT_PLATZHALTER_PRAEFIX))
        self.assertTrue(ist_platzhalter_modell(PLATZHALTER_MODELL))
        self.assertTrue(ist_platzhalter_modell(PLATZHALTER_MODELL.upper()))
        self.assertTrue(ist_platzhalter_modell(
            "  " + PLATZHALTER_MODELL.replace(" ", "  ") + "  "))
        self.assertFalse(ist_platzhalter_modell(None))
        self.assertFalse(ist_platzhalter_modell(""))

    def test_leere_felder_werden_benannt(self):
        self.assertEqual("Hersteller fehlt.", kopf_beanstandung("", "X"))
        self.assertEqual("Hersteller fehlt.", kopf_beanstandung("  ", "X"))
        self.assertEqual("Modell-Name fehlt.", kopf_beanstandung("ADB", "  "))
        self.assertEqual("Modell-Name fehlt.", kopf_beanstandung("ADB", None))


if __name__ == "__main__":
    unittest.main()
