"""FM-36 — das Ergebnisfeld des Fixture-Editors existiert ab dem Konstruktor.

**Der Befund.** ``FixtureEditorDialog._saved_id`` wurde ausschliesslich am Ende
von ``_save()`` angelegt (``self._saved_id = profile.id``); ``__init__``
belegte den Namen nirgends vor. Wer das Feld nach einem ABGEBROCHENEN Dialog
las, bekam einen ``AttributeError`` statt ``None``. Gemessen am laufenden Code:
frisch konstruiert, nach ``reject()`` und nach einem an der Pflichtfeldpruefung
abgebrochenen ``_save()`` warf jeder Zugriff
``'FixtureEditorDialog' object has no attribute '_saved_id'``.

★ **Zwei Namen, eine Frage.** Der Schwesterdialog ``FixtureGeneratorDialog``
fuehrt dieselbe Auskunft oeffentlich (``saved_id``, im ``__init__``
vorbelegt) — und ``patch_view._open_generator`` liest sie so. Der Editor kannte
nur den privaten Namen. Damit beide Dialoge auf dieselbe Frage dieselbe
Auskunft geben, fuehrt der Editor jetzt BEIDE Namen; sie werden gemeinsam
belegt und gemeinsam gesetzt. Der private Name durfte nicht ersatzlos
entfallen: 16 bestehende Tests lesen ``dlg._saved_id``.

⚠️ **Warum hier ueberall DIREKT gelesen wird.** Ein ``getattr(dlg, "saved_id",
None)`` macht aus dem fehlenden Attribut selbst ein ``None`` — ein so
geschriebener Test waere schon VOR dem Fix gruen gewesen und haette nichts
gemessen. Darum steht in jedem Zugriff hier woertlich ``dlg._saved_id`` bzw.
``dlg.saved_id``; :meth:`LesehelferTest.test_lesehelfer_meldet_ein_fehlendes_feld`
weist nach, dass der gemeinsame Helfer ein fehlendes Feld wirklich anzeigt.

★ **Die Positivkontrolle traegt den halben Wert dieser Datei.** Ein Fix, der
beide Felder schlicht immer auf ``None`` liesse, bestuende jede
Abbruch-Pruefung. Deshalb misst :class:`NachEchtemSpeichernTest`, dass nach
einem Speichern ueber den ECHTEN Dialog in BEIDEN Namen dieselbe, in der
Datenbank tatsaechlich vorhandene Profil-ID steht.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402
from sqlalchemy.orm import Session                             # noqa: E402

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


# Zwei Kanaele, damit ein Modus die Pflichtpruefung „Mode hat keine Channels"
# passiert — der Inhalt spielt fuer FM-36 keine Rolle.
_KANAELE = [
    {"name": "Dimmer", "attribute": "dimmer", "default": 0},
    {"name": "Rot", "attribute": "color_r", "default": 0},
]

# Die beiden Namen, die dieselbe Auskunft geben muessen.
_BEIDE_NAMEN = ("_saved_id", "saved_id")


class _EditorFall(unittest.TestCase):
    """Gemeinsame Umgebung: eigene Datenbank, echter Dialog, stumme Dialoge."""

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)

        # Der Editor holt seine Engine ueber den importierten Namen.
        p1 = mock.patch.object(editor_module, "engine", lambda: self.engine)
        p1.start()
        self.addCleanup(p1.stop)
        # Die Meldungsfenster wuerden headless blockieren; die Zaehler der
        # Attrappen sind gleichzeitig der Nachweis, welcher Zweig gelaufen ist.
        p2 = mock.patch.object(editor_module.QMessageBox, "information")
        self.info = p2.start()
        self.addCleanup(p2.stop)
        p3 = mock.patch.object(editor_module.QMessageBox, "warning")
        self.warnung = p3.start()
        self.addCleanup(p3.stop)

    # ── Hilfen ──────────────────────────────────────────────────────────────

    def _dialog(self, fixture_id: int | None = None):
        """Ein echter ``FixtureEditorDialog`` — kein Nachbau, keine Attrappe."""
        dlg = editor_module.FixtureEditorDialog(fixture_id=fixture_id)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def _feld(self, dlg, name: str):
        """Liest ``name`` DIREKT als Attribut und meldet ein Fehlen als Fehler.

        Bewusst KEIN ``getattr(dlg, name, None)``: ein Default machte aus dem
        fehlenden Attribut ein ``None`` und der Test waere blind. Der Zugriff
        steht deshalb woertlich als ``dlg._saved_id`` / ``dlg.saved_id`` da,
        der ``except``-Zweig uebersetzt den Befund nur in eine lesbare
        Meldung — er schluckt ihn nicht."""
        try:
            if name == "_saved_id":
                return dlg._saved_id
            return dlg.saved_id
        except AttributeError as fehler:
            self.fail(f"Zugriff auf {name} warf statt zu antworten: {fehler}")

    def _profil_anlegen(self, *, name="Sondengeraet", short="FM36") -> int:
        """Legt ueber den ECHTEN Dialog ein Profil an und gibt dessen ID."""
        dlg = self._dialog()
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText(name)
        dlg._edit_short.setText(short)
        while dlg._tabs.count():
            dlg._tabs.removeTab(0)
        dlg._add_mode(name="Standard", channels=[dict(c) for c in _KANAELE])
        dlg._save()
        self.assertEqual(1, dlg.result(),
                         "Vorbedingung: der Dialog hat nicht mit accept() "
                         "geschlossen — es wurde gar nicht gespeichert.")
        return self._ids_in_der_db()[-1]

    def _ids_in_der_db(self) -> list[int]:
        """Die tatsaechlich vorhandenen Profil-IDs — die Wahrheit zum Vergleich."""
        with Session(self.engine) as s:
            return sorted(p.id for p in s.query(FixtureProfile).all())

    def _beide_sind_None(self, dlg, wo: str):
        """Beide Namen antworten ``None`` — geprueft, nicht vorausgesetzt."""
        for name in _BEIDE_NAMEN:
            self.assertIsNone(
                self._feld(dlg, name),
                f"{name} ist {wo} nicht None, sondern "
                f"{self._feld(dlg, name)!r}.")


class FrischKonstruiertTest(_EditorFall):
    """Der Konstruktor allein muss beide Namen belegen."""

    def test_neues_profil_beide_felder_sind_None(self):
        dlg = self._dialog()
        # Vorbedingung: der Dialog steht wirklich im Neu-Fall.
        self.assertIsNone(dlg._fixture_id,
                          "Vorbedingung: kein Neu-Fall gemessen.")
        self._beide_sind_None(dlg, "direkt nach dem Konstruieren (neu)")

    def test_vorhandenes_profil_geladen_beide_felder_sind_None(self):
        """Der Ladeweg (``fixture_id=<Profil>``) ist ein ZWEITER Weg durch
        ``__init__`` — er darf die Vorbelegung nicht ueberspringen."""
        pid = self._profil_anlegen()
        dlg = self._dialog(fixture_id=pid)
        # Vorbedingung: das Profil ist wirklich geladen worden.
        self.assertEqual(pid, dlg._fixture_id)
        self.assertGreater(dlg._tabs.count(), 0,
                           "Vorbedingung: nichts geladen, der Ladeweg lief nicht.")
        self.assertEqual("Sondengeraet", dlg._edit_name.text(),
                         "Vorbedingung: die Profildaten kamen nicht an.")
        self._beide_sind_None(dlg, "nach dem Laden eines vorhandenen Profils")


class NachAbbruchTest(_EditorFall):
    """Jeder Abbruchweg endet mit ``None`` — nicht mit einem AttributeError."""

    def test_nach_reject_beide_felder_sind_None(self):
        dlg = self._dialog()
        dlg.reject()
        # Vorbedingung: der Dialog wurde wirklich abgewiesen.
        self.assertEqual(0, dlg.result(), "Vorbedingung: kein reject() gemessen.")
        self._beide_sind_None(dlg, "nach reject()")

    def _abgebrochenes_save(self, dlg, wo: str):
        """Ruft das ECHTE ``_save`` und belegt, dass es abgebrochen hat:
        eine Warnung mehr, kein Profil in der Datenbank, Dialog nicht
        akzeptiert."""
        vorher = self.warnung.call_count
        dlg._save()
        self.assertEqual(vorher + 1, self.warnung.call_count,
                         f"Vorbedingung: {wo} hat keine Warnung ausgeloest — "
                         "der Abbruchzweig wurde nie betreten.")
        self.assertEqual([], self._ids_in_der_db(),
                         f"Vorbedingung: {wo} hat trotzdem gespeichert.")
        self.assertNotEqual(1, dlg.result(),
                            f"Vorbedingung: {wo} hat den Dialog akzeptiert.")

    def test_save_ohne_hersteller_laesst_beide_felder_None(self):
        dlg = self._dialog()
        dlg._cb_manufacturer.setCurrentText("")
        dlg._edit_name.setText("Egal")
        self._abgebrochenes_save(dlg, "_save ohne Hersteller")
        self._beide_sind_None(dlg, "nach dem Abbruch an der Herstellerpruefung")

    def test_save_ohne_modellnamen_laesst_beide_felder_None(self):
        """Der zweite fruehe ``return`` in ``_save`` — ein anderer Weg zum
        selben Zustand (Hausregel 8)."""
        dlg = self._dialog()
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText("")
        self._abgebrochenes_save(dlg, "_save ohne Modell-Namen")
        self._beide_sind_None(dlg, "nach dem Abbruch an der Namenspruefung")

    def test_save_mit_leerem_mode_laesst_beide_felder_None(self):
        """Der spaeteste Abbruch: erst in der Modus-Schleife, nachdem ``_save``
        schon Daten eingesammelt hat."""
        dlg = self._dialog()
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText("Ohne Kanaele")
        self.assertEqual(1, dlg._tabs.count(),
                         "Vorbedingung: erwartet wird genau der leere Default-Mode.")
        self._abgebrochenes_save(dlg, "_save mit kanallosem Mode")
        self._beide_sind_None(dlg, "nach dem Abbruch an der Kanalpruefung")


class NachEchtemSpeichernTest(_EditorFall):
    """POSITIVKONTROLLE — ohne sie bestuende alles oben auch ein Fix, der die
    Felder fuer immer auf ``None`` liesse."""

    def test_beide_felder_tragen_die_echte_profil_id(self):
        pid = self._profil_anlegen(name="Echtes Profil", short="ECHT")
        dlg = self._dialog()
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText("Zweites Profil")
        dlg._edit_short.setText("ZWEI")
        while dlg._tabs.count():
            dlg._tabs.removeTab(0)
        dlg._add_mode(name="Standard", channels=[dict(c) for c in _KANAELE])
        dlg._save()
        # Vorbedingung: es wurde wirklich gespeichert.
        self.assertEqual(1, dlg.result(), "Vorbedingung: kein accept() gemessen.")
        ids = self._ids_in_der_db()
        self.assertEqual(2, len(ids),
                         f"Vorbedingung: erwartet zwei Profile, gefunden {ids}.")
        neu = [i for i in ids if i != pid]
        self.assertEqual(1, len(neu), f"Kein eindeutiges neues Profil: {ids}.")

        for name in _BEIDE_NAMEN:
            wert = self._feld(dlg, name)
            self.assertIsNotNone(
                wert, f"{name} ist nach erfolgreichem Speichern leer geblieben.")
            self.assertEqual(
                neu[0], wert,
                f"{name} nennt {wert!r}, angelegt wurde aber Profil {neu[0]}.")

    def test_auch_das_BEARBEITEN_eines_vorhandenen_profils_setzt_beide(self):
        """★★★ Vom Skeptiker gefunden: eine Mutation, die die Zuweisung auf den
        NEU-Fall einschraenkt (``if self._fixture_id is None: ...``), bestand
        saemtliche Tests — obwohl sie beim BEARBEITEN eines vorhandenen Profils
        nach erfolgreichem Speichern in BEIDEN Namen ``None`` zuruecklaesst.

        Genau dieser Zustand ist der, den das Kriterium ausschliessen soll: ein
        Aufrufer im ueblichen Idiom (``if dlg.exec() and dlg.saved_id is not
        None``) liest ihn als *nichts gespeichert* — und speichert womoeglich
        ein zweites Mal.

        Alle Tests oben legen ein NEUES Profil an. Der Bearbeiten-Fall war
        unbeobachtet."""
        pid = self._profil_anlegen(name="Zu Bearbeiten", short="BEARB")
        dlg = self._dialog(fixture_id=pid)
        self.assertEqual(self._feld(dlg, "_saved_id"), None,
                         "Vorbedingung: vor dem Speichern leer")
        dlg._edit_name.setText("Bearbeitet")
        dlg._save()
        self.assertEqual(1, dlg.result(),
                         "Vorbedingung: das Speichern hat gar nicht stattgefunden")
        for name in _BEIDE_NAMEN:
            self.assertEqual(
                pid, self._feld(dlg, name),
                f"{name} bleibt beim BEARBEITEN leer — ein Aufrufer liest das "
                f"als 'nichts gespeichert'")

    def test_ein_gescheitertes_speichern_meldet_KEINE_id(self):
        """★★ Zweiter Skeptiker-Fund: zieht man die Zuweisung VOR ``s.commit()``,
        bestehen alle Tests — aber das Feld meldete dann eine ID, die in der
        Datenbank nie angekommen ist. Die Auskunft ``saved_id`` heisst
        *gespeichert*, nicht *versucht*."""
        from unittest import mock
        from sqlalchemy.orm import Session as _Session
        dlg = self._dialog()
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText("Faellt Um")
        dlg._edit_short.setText("FALL")
        while dlg._tabs.count():
            dlg._tabs.removeTab(0)
        dlg._add_mode(name="Standard", channels=[dict(c) for c in _KANAELE])
        with mock.patch.object(_Session, "commit",
                               side_effect=RuntimeError("commit faellt um")):
            try:
                dlg._save()
            except RuntimeError:
                pass          # der Dialog darf werfen — er darf nur nichts behaupten
        for name in _BEIDE_NAMEN:
            self.assertIsNone(
                self._feld(dlg, name),
                f"{name} nennt eine ID, obwohl das Speichern gescheitert ist")

    def test_beide_namen_geben_dieselbe_auskunft(self):
        """Hausregel 6 — eine Frage, eine Stelle: die beiden Namen duerfen in
        KEINEM Zustand auseinanderlaufen."""
        dlg = self._dialog()
        self.assertEqual(self._feld(dlg, "_saved_id"), self._feld(dlg, "saved_id"),
                         "Die Namen laufen schon frisch konstruiert auseinander.")
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText("Gleichlauf")
        dlg._edit_short.setText("GLEICH")
        while dlg._tabs.count():
            dlg._tabs.removeTab(0)
        dlg._add_mode(name="Standard", channels=[dict(c) for c in _KANAELE])
        dlg._save()
        self.assertEqual(1, dlg.result(), "Vorbedingung: kein accept() gemessen.")
        self.assertEqual(self._feld(dlg, "_saved_id"), self._feld(dlg, "saved_id"),
                         "Nach dem Speichern nennen die beiden Namen "
                         "verschiedene IDs.")

    def test_ein_zweiter_dialog_erbt_die_id_nicht(self):
        """GEGENPROBE: die Vorbelegung gehoert in ``__init__``, nicht in die
        Klasse. Ein Klassenattribut bestuende alle Pruefungen oben — aber der
        naechste Dialog saehe die ID des vorigen."""
        pid = self._profil_anlegen(name="Erstes", short="ERST")
        zweiter = self._dialog()
        for name in _BEIDE_NAMEN:
            self.assertIsNone(
                self._feld(zweiter, name),
                f"{name} eines frischen Dialogs traegt noch {pid} aus dem "
                "vorigen Dialog — der Wert haengt an der Klasse statt am "
                "Objekt.")


class KonstruktorBelegtAmObjektTest(_EditorFall):
    """Die Vorbelegung gehoert in ``__init__`` — nicht an die Klasse.

    ⚠️ Gefunden von der Mutationsprobe: ersetzt man die beiden Zeilen im
    ``__init__`` durch Klassen-Attribute (``_saved_id = None`` direkt unter dem
    Klassen-Docstring), bleiben ALLE uebrigen Pruefungen dieser Datei gruen —
    die gelesenen Werte sind identisch. Der Unterschied ist trotzdem echt: bei
    einem Klassen-Attribut besitzt kein Dialog seine eigene Antwort, bis er
    einmal gespeichert hat; sie haengt bis dahin an einem einzigen, von allen
    Dialogen geteilten Wert an der Klasse."""

    def test_konstruktor_legt_beide_felder_am_objekt_selbst_an(self):
        dlg = self._dialog()
        for name in _BEIDE_NAMEN:
            self.assertIn(
                name, vars(dlg),
                f"{name} steht nicht am Dialog-Objekt, sondern nur an der "
                "Klasse — der Konstruktor belegt es nicht vor.")

    def test_ein_wert_an_der_klasse_veraendert_die_antwort_nicht(self):
        """Die spuerbare Folge: ein Schreibzugriff auf die KLASSE darf die
        Auskunft eines bereits gebauten, noch nicht gespeicherten Dialogs nicht
        umschreiben."""
        dlg = self._dialog()
        for name in _BEIDE_NAMEN:
            with mock.patch.object(editor_module.FixtureEditorDialog,
                                   name, 99, create=True):
                # Vorbedingung: der Schreibzugriff ist wirklich passiert.
                self.assertEqual(
                    99, getattr(editor_module.FixtureEditorDialog, name),
                    f"Vorbedingung: {name} liess sich an der Klasse nicht "
                    "setzen — die Probe misst nichts.")
                self.assertIsNone(
                    self._feld(dlg, name),
                    f"{name} des Dialogs folgt der Klasse (99 statt None) — "
                    "die Vorbelegung liegt an der Klasse statt am Objekt.")


class LesehelferTest(_EditorFall):
    """Selbstpruefung: sieht der Lesehelfer ein fehlendes Feld ueberhaupt?"""

    def test_lesehelfer_meldet_ein_fehlendes_feld(self):
        class OhneFelder:
            pass

        for name in _BEIDE_NAMEN:
            with self.assertRaises(self.failureException, msg=(
                    f"Der Helfer haelt ein fehlendes {name} fuer None — "
                    "dann waere diese ganze Datei blind.")):
                self._feld(OhneFelder(), name)
