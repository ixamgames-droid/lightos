"""FM-46 (Etappe 1): die Spalte „Weiß-Segment“ in BEIDEN Profil-Dialogen.

Zwei Dialoge, zwei getrennte Modelle (FM-23/FM-26): der einfache
Fixture-Editor haelt Kanal-Dicts und baut beim Speichern alle Modi NEU (was
``_load_existing`` nicht mitliest, ist danach weg); der Generator hat
``GenChannel`` und speichert ueber ``build_profile_payload`` ->
``create_user_profile``. Die Zuordnung muss durch beide Wege — sonst haengt
sie daran, welchen Dialog der Nutzer erwischt hat.

Geprueft: Roundtrip (setzen, speichern, laden, Wert da — beim Editor auch ein
zweites Speichern), Spalte nur an Dimmern, Vorschlagsknopf, Hinweis
erscheint/verschwindet, ``validate_model`` meldet den Hinweis.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox             # noqa: E402
from sqlalchemy import select                                     # noqa: E402
from sqlalchemy.orm import Session                                # noqa: E402

from src.core.database.fixture_db import get_engine               # noqa: E402
from src.core.database.models import (FixtureChannel, FixtureMode,  # noqa: E402
                                      create_all_idempotent)
from src.ui.widgets import fixture_editor as editor_module        # noqa: E402
from src.ui.widgets import fixture_generator as gen_module        # noqa: E402
from src.ui.widgets.fixture_generator import (GenChannel, GenMode,  # noqa: E402
                                              GeneratorModel,
                                              build_profile_payload,
                                              validate_model)

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# Eigene Weiss-Achse: 2x Weiss, 1 Farbkopf, zwei Dimmer — direkt vor ihrem
# Weiss, damit der Vorschlag eindeutig ist.
_KANAELE = [("Dimmer 1", "intensity"), ("Weiss 1", "color_w"),
            ("Dimmer 2", "intensity"), ("Weiss 2", "color_w"),
            ("Rot", "color_r"), ("Gruen", "color_g"), ("Blau", "color_b")]


def _dicts():
    return [{"name": n, "attribute": a, "default": 0, "highlight": 255}
            for n, a in _KANAELE]


class _DbFall(unittest.TestCase):

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        p = mock.patch.object(editor_module, "engine", lambda: self.engine)
        p.start()
        self.addCleanup(p.stop)
        for modul in (editor_module, gen_module):
            pm = mock.patch.object(modul.QMessageBox, "information")
            self.info = pm.start()
            self.addCleanup(pm.stop)

    def _segmente_in_db(self, profil_id):
        with Session(self.engine) as s:
            mode = s.execute(select(FixtureMode).where(
                FixtureMode.fixture_id == profil_id)).scalars().one()
            chans = s.execute(select(FixtureChannel)
                              .where(FixtureChannel.mode_id == mode.id)
                              .order_by(FixtureChannel.channel_number)
                              ).scalars().all()
            return [c.segment for c in chans]


class EditorTest(_DbFall):

    def _dialog(self, fixture_id=None):
        dlg = editor_module.FixtureEditorDialog(fixture_id=fixture_id)
        self.addCleanup(dlg.deleteLater)
        return dlg, dlg._tabs.widget(0)

    def _neu(self):
        dlg, tab = self._dialog()
        dlg._cb_manufacturer.setCurrentText("FM46 Hersteller")
        dlg._edit_name.setText("FM46 Panel")
        tab.load_mode_data("Default", _dicts())
        return dlg, tab

    def test_spalte_nur_an_dimmern(self):
        _dlg, tab = self._neu()
        col = editor_module.SEGMENT_COL
        self.assertIsInstance(tab._tbl.cellWidget(0, col), QComboBox)
        self.assertIsNone(tab._tbl.cellWidget(1, col))
        cb = tab._tbl.cellWidget(0, col)
        self.assertEqual([cb.itemText(i) for i in range(cb.count())],
                         ["—", "1", "2"])

    def test_roundtrip_setzen_speichern_laden(self):
        dlg, tab = self._neu()
        col = editor_module.SEGMENT_COL
        # Ueber Kreuz: Dimmer 1 -> Segment 2, Dimmer 2 -> Segment 1.
        tab._tbl.cellWidget(0, col).setCurrentIndex(2)
        tab._tbl.cellWidget(2, col).setCurrentIndex(1)
        dlg._save()
        pid = dlg.saved_id
        self.assertIsNotNone(pid)
        self.assertEqual(self._segmente_in_db(pid),
                         [1, None, 0, None, None, None, None])
        # Laden: der Wert steht wieder in der Spalte ...
        dlg2, tab2 = self._dialog(pid)
        self.assertEqual(tab2._tbl.cellWidget(0, col).currentText(), "2")
        self.assertEqual(tab2._tbl.cellWidget(2, col).currentText(), "1")
        # ... und ueberlebt ein zweites Speichern (`_save` baut Modi neu).
        dlg2._save()
        self.assertEqual(self._segmente_in_db(pid),
                         [1, None, 0, None, None, None, None])

    def test_attributwechsel_verwirft_zuordnung(self):
        _dlg, tab = self._neu()
        tab._tbl.cellWidget(0, editor_module.SEGMENT_COL).setCurrentIndex(1)
        self.assertEqual(tab.channels[0]["segment"], 0)
        tab._set_attr(0, "shutter")
        self.assertIsNone(tab.channels[0]["segment"])
        self.assertIsNone(tab._tbl.cellWidget(0, editor_module.SEGMENT_COL))

    def test_hinweis_erscheint_und_verschwindet(self):
        from src.core.dimmer_segmente import HINWEIS_TEXT
        _dlg, tab = self._neu()
        col = editor_module.SEGMENT_COL
        self.assertEqual(tab.segment_hinweis_text(), HINWEIS_TEXT)
        # Eine Zuordnung: der Fehlt-Hinweis geht, die Teil-Zuordnung wird
        # benannt (Review-Befund 3).
        tab._tbl.cellWidget(0, col).setCurrentIndex(1)
        self.assertIn("Kanal 3 hat kein", tab.segment_hinweis_text())
        tab._tbl.cellWidget(2, col).setCurrentIndex(2)
        self.assertFalse(tab.segment_hinweis_sichtbar())
        tab._tbl.cellWidget(0, col).setCurrentIndex(0)
        tab._tbl.cellWidget(2, col).setCurrentIndex(0)
        self.assertEqual(tab.segment_hinweis_text(), HINWEIS_TEXT)

    def test_kein_hinweis_ohne_eigene_weiss_achse(self):
        _dlg, tab = self._neu()
        tab.load_mode_data("Default", [
            {"name": "D", "attribute": "intensity"},
            {"name": "R", "attribute": "color_r"},
            {"name": "W", "attribute": "color_w"},
            {"name": "D", "attribute": "intensity"},
            {"name": "R", "attribute": "color_r"},
            {"name": "W", "attribute": "color_w"}])
        self.assertFalse(tab.segment_hinweis_sichtbar())

    def test_vorschlag(self):
        _dlg, tab = self._neu()
        self.assertTrue(tab.vorschlag_uebernehmen())
        self.assertEqual([c.get("segment") for c in tab.channels][:4],
                         [0, None, 1, None])
        self.assertEqual(tab._tbl.cellWidget(2, editor_module.SEGMENT_COL)
                         .currentText(), "2")
        self.assertFalse(tab.segment_hinweis_sichtbar())

    def test_kein_eindeutiger_vorschlag_meldet_sich(self):
        _dlg, tab = self._neu()
        tab.load_mode_data("Default", [
            {"name": "D", "attribute": "intensity"},
            {"name": "D", "attribute": "intensity"},
            {"name": "R", "attribute": "color_r"},
            {"name": "W", "attribute": "color_w"},
            {"name": "W", "attribute": "color_w"}])
        self.info.reset_mock()
        tab._on_vorschlag()
        self.assertEqual(self.info.call_count, 1)
        self.assertEqual([c.get("segment") for c in tab.channels],
                         [None] * 5)


def _gen_modell(segmente=(None, None)):
    chans = []
    it = iter(segmente)
    for n, a in _KANAELE:
        chans.append(GenChannel(n, a, segment=next(it) if a == "intensity" else None))
    return GeneratorModel(manufacturer="FM46 Hersteller", model="FM46 Panel",
                          modes=[GenMode("Default", chans)])


class GeneratorTest(_DbFall):

    def test_payload_und_roundtrip(self):
        model = _gen_modell((1, 0))
        payload = build_profile_payload(model)
        self.assertEqual([c["segment"] for c in payload["modes"][0]["channels"]],
                         [1, None, 0, None, None, None, None])
        pid = gen_module.save_generated_profile(payload, engine=self.engine)
        self.assertEqual(self._segmente_in_db(pid),
                         [1, None, 0, None, None, None, None])

    def test_nicht_dimmer_verliert_den_wert(self):
        model = _gen_modell()
        model.modes[0].channels[1].segment = 0       # an einem Weiss-Kanal
        payload = build_profile_payload(model)
        self.assertIsNone(payload["modes"][0]["channels"][1]["segment"])

    def test_alte_payloads_ohne_schluessel(self):
        payload = build_profile_payload(_gen_modell((0, 1)))
        for c in payload["modes"][0]["channels"]:
            c.pop("segment")
        pid = gen_module.save_generated_profile(payload, engine=self.engine)
        self.assertEqual(self._segmente_in_db(pid), [None] * 7)

    def test_validate_meldet_hinweis_mit_vorschlag(self):
        texte = [t for _s, t in validate_model(_gen_modell())]
        treffer = [t for t in texte if "Weiß-Segment" in t]
        self.assertEqual(len(treffer), 1, texte)
        self.assertIn("Kanal 1 → Segment 1", treffer[0])
        self.assertIn("Kanal 3 → Segment 2", treffer[0])
        texte = [t for _s, t in validate_model(_gen_modell((0, 1)))]
        self.assertFalse([t for t in texte if "Weiß-Segment" in t], texte)

    def test_validate_segment_gibt_es_nicht(self):
        texte = [t for _s, t in validate_model(_gen_modell((0, 5)))]
        self.assertTrue([t for t in texte if "Segment 6 gibt es" in t], texte)

    def test_dialog_spalte_hinweis_vorschlag(self):
        dlg = gen_module.FixtureGeneratorDialog(model=_gen_modell())
        self.addCleanup(dlg.deleteLater)
        tab = dlg._tabs.widget(0)
        col = gen_module.SEGMENT_COL
        self.assertIsInstance(tab._tbl.cellWidget(0, col), QComboBox)
        self.assertIsNone(tab._tbl.cellWidget(1, col))
        self.assertTrue(tab.segment_hinweis_sichtbar())
        self.assertTrue(tab.vorschlag_uebernehmen())
        self.assertEqual([c.segment for c in tab.mode.channels][:4],
                         [0, None, 1, None])
        self.assertFalse(tab.segment_hinweis_sichtbar())
        tab._tbl.cellWidget(2, col).setCurrentIndex(0)
        self.assertIsNone(tab.mode.channels[2].segment)
        self.assertIn("Kanal 3 hat kein", tab.segment_hinweis_text())
        tab._tbl.cellWidget(0, col).setCurrentIndex(0)
        self.assertTrue(tab.segment_hinweis_sichtbar())


# ════════════════════════════════════════════════════════════════════════════
# Review-Befunde (2)-(5): Umnummerieren, Probleme melden, Vorschlag fragt
# nach, Generator-Combo loescht nicht beim Tippen.
# ════════════════════════════════════════════════════════════════════════════

def _segs(tab):
    """Segmente beider Dimmer (Editor: Dicts, Generator: GenChannel)."""
    chans = tab.channels if hasattr(tab, "channels") else tab.mode.channels
    get = (lambda c: c.get("segment")) if hasattr(tab, "channels") \
        else (lambda c: c.segment)
    attr = (lambda c: c.get("attribute")) if hasattr(tab, "channels") \
        else (lambda c: c.attribute)
    return [get(c) for c in chans if attr(c) in ("intensity", "intens")]


class _BeideEditoren(_DbFall):
    """Jeder Test laeuft im einfachen Editor UND im Generator."""

    def _tabs(self):
        dlg = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        etab = dlg._tabs.widget(0)
        etab.load_mode_data("Default", _dicts())
        gdlg = gen_module.FixtureGeneratorDialog(model=_gen_modell())
        self.addCleanup(gdlg.deleteLater)
        gtab = gdlg._tabs.widget(0)
        return (("Editor", etab, editor_module.SEGMENT_COL),
                ("Generator", gtab, gen_module.SEGMENT_COL))

    @staticmethod
    def _zuordnen(tab, col, d1, d2):
        """Dimmer 1 (Zeile 0) und Dimmer 2 (Zeile 2) per Spalte setzen."""
        tab._tbl.cellWidget(0, col).setCurrentIndex(0 if d1 is None else d1 + 1)
        tab._tbl.cellWidget(2, col).setCurrentIndex(0 if d2 is None else d2 + 1)

    @staticmethod
    def _zeile_waehlen(tab, row):
        tab._tbl.clearSelection()
        tab._tbl.selectRow(row)

    @staticmethod
    def _bewegen(tab, richtung):
        return tab._move(richtung)


class UmnummerierenTest(_BeideEditoren):
    """(2) Segment ist ein Index ins ``color_w``-Vorkommen. Ohne Nachziehen
    zeigte nach Loeschen/Verschieben eines Weiss-Kanals derselbe Index stumm
    auf ein anderes Segment."""

    def test_weiss_loeschen(self):
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, 0, 1)
                self._zeile_waehlen(tab, 1)              # Weiss 1
                (tab._del_channel if name == "Editor" else tab._del)()
                self.assertEqual(_segs(tab), [None, 0],
                                 "Dimmer 1 verliert sein Segment, Dimmer 2 "
                                 "zeigt weiter auf DASSELBE Weiss (jetzt Nr. 1)")

    def test_weiss_hoch(self):
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, 0, 1)
                self._zeile_waehlen(tab, 3)              # Weiss 2 nach oben
                self._bewegen(tab, -1)
                self._zeile_waehlen(tab, 2)
                self._bewegen(tab, -1)                   # jetzt vor Weiss 1
                self.assertEqual(_segs(tab), [1, 0])

    def test_weiss_runter(self):
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, 0, 1)
                self._zeile_waehlen(tab, 1)              # Weiss 1 nach unten
                self._bewegen(tab, 1)
                self._zeile_waehlen(tab, 2)
                self._bewegen(tab, 1)                    # jetzt hinter Weiss 2
                self.assertEqual(_segs(tab), [1, 0])

    def test_attributwechsel_eines_weiss_kanals(self):
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, 0, 1)
                tab._set_attr(1, "color_a")              # Weiss 1 ist keins mehr
                self.assertEqual(_segs(tab), [None, 0])
                tab._set_attr(1, "color_w")              # ... und wieder Weiss
                self.assertEqual(_segs(tab), [0, 1])

    def test_gespeichert_wird_die_nachgezogene_nummer(self):
        _n, tab, col = self._tabs()[0]
        dlg = tab.window()
        dlg._cb_manufacturer.setCurrentText("FM46 Hersteller")
        dlg._edit_name.setText("FM46 Panel")
        self._zuordnen(tab, col, 0, 1)
        self._zeile_waehlen(tab, 1)
        tab._del_channel()
        dlg._save()
        self.assertEqual(self._segmente_in_db(dlg.saved_id),
                         [None, 0, None, None, None, None])


class ProblemeTest(_BeideEditoren):
    """(3) Widerspruechliche oder unvollstaendige Zuordnung wird gemeldet."""

    def test_doppelt_vergeben(self):
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, 0, 0)
                text = tab.segment_hinweis_text()
                self.assertIn("Weiß-Segment 1 ist mehrfach vergeben", text)
                self._zuordnen(tab, col, 0, 1)
                self.assertEqual(tab.segment_hinweis_text(), "")

    def test_dimmer_ohne_segment(self):
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, None, 1)
                self.assertIn("Dimmer auf Kanal 1 hat kein Weiß-Segment",
                              tab.segment_hinweis_text())

    def test_validate_model(self):
        texte = [t for _s, t in validate_model(_gen_modell((1, 1)))]
        self.assertTrue([t for t in texte if "mehrfach vergeben" in t], texte)
        texte = [t for _s, t in validate_model(_gen_modell((None, 0)))]
        self.assertTrue([t for t in texte if "Kanal 1 hat kein" in t], texte)
        texte = [t for _s, t in validate_model(_gen_modell((0, 1)))]
        self.assertFalse([t for t in texte if "Weiß-Segment" in t], texte)


class VorschlagFragtNachTest(_BeideEditoren):
    """(4) Der Vorschlag ueberschreibt Handzuordnungen nicht ungefragt."""

    def _frage(self, antwort):
        from PySide6.QtWidgets import QMessageBox
        pm = mock.patch.object(QMessageBox, "question", return_value=antwort)
        frage = pm.start()
        self.addCleanup(pm.stop)
        return frage

    def test_nein_fuellt_nur_leere(self):
        from PySide6.QtWidgets import QMessageBox
        frage = self._frage(QMessageBox.StandardButton.No)
        for name, tab, col in self._tabs():
            with self.subTest(name):
                frage.reset_mock()
                self._zuordnen(tab, col, None, 0)        # Hand: D2 -> 1
                self.assertTrue(tab.vorschlag_uebernehmen())
                self.assertEqual(frage.call_count, 1)
                self.assertEqual(_segs(tab), [0, 0], "Handwert bleibt")

    def test_ja_ueberschreibt(self):
        from PySide6.QtWidgets import QMessageBox
        self._frage(QMessageBox.StandardButton.Yes)
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, None, 0)
                self.assertTrue(tab.vorschlag_uebernehmen())
                self.assertEqual(_segs(tab), [0, 1])

    def test_abbrechen_aendert_nichts(self):
        from PySide6.QtWidgets import QMessageBox
        self._frage(QMessageBox.StandardButton.Cancel)
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, None, 0)
                self.info.reset_mock()
                self.assertIsNone(tab.vorschlag_uebernehmen())
                tab._on_vorschlag()
                self.assertEqual(self.info.call_count, 0,
                                 "Abbruch ist kein „kein Vorschlag“")
                self.assertEqual(_segs(tab), [None, 0])

    def test_keine_frage_ohne_abweichung(self):
        frage = self._frage(None)
        for name, tab, col in self._tabs():
            with self.subTest(name):
                self._zuordnen(tab, col, 0, None)        # passt zum Vorschlag
                self.assertTrue(tab.vorschlag_uebernehmen())
                self.assertEqual(_segs(tab), [0, 1])
        self.assertEqual(frage.call_count, 0)


class GeneratorTippenTest(_DbFall):
    """(5) Die Attribut-Combo des Generators ist editierbar und meldet jeden
    Tipp-Zwischenstand — die Zuordnung darf dabei nicht verloren gehen."""

    def test_zwischenstand_loescht_nicht(self):
        dlg = gen_module.FixtureGeneratorDialog(model=_gen_modell((1, 0)))
        self.addCleanup(dlg.deleteLater)
        tab = dlg._tabs.widget(0)
        tab._set_attr(0, "intens")
        self.assertEqual(tab.mode.channels[0].segment, 1)
        zelle = tab._tbl.item(0, gen_module.SEGMENT_COL)
        self.assertIsNone(tab._tbl.cellWidget(0, gen_module.SEGMENT_COL))
        self.assertEqual(zelle.text(), "2", "grau, aber sichtbar")
        tab._set_attr(0, "intensity")
        self.assertEqual(tab.mode.channels[0].segment, 1)
        self.assertEqual(tab._tbl.cellWidget(0, gen_module.SEGMENT_COL)
                         .currentText(), "2")

    def test_an_nicht_dimmern_beim_speichern_verworfen(self):
        model = _gen_modell((1, 0))
        model.modes[0].channels[0].attribute = "shutter"
        payload = build_profile_payload(model)
        self.assertIsNone(payload["modes"][0]["channels"][0]["segment"])


if __name__ == "__main__":
    unittest.main()
