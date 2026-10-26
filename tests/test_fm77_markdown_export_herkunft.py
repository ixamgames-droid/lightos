"""FM-77: „Markdown exportieren…“ im Fixture Generator nimmt die Herkunft mit.

Befund: ``model_to_markdown`` schrieb Kopf, Typ, Leistung, Notizen und die
Modus-Tabellen, las ``GeneratorModel.herkunft`` (FM-76) aber nirgends. Eine
Kanaltabelle aus einer QLC+-Vorlage (Apache-2.0) ging so ohne Herkunfts-,
Urheber- und Lizenzangabe aus dem Programm.

Gemessen wird an der exportierten Datei (Dialog, Vorlage per Knopf geladen,
Datei-Dialog ersetzt) und an ``model_to_markdown`` direkt. Die Angaben
muessen dieselben sein, mit denen das Profil gespeichert wuerde
(``herkunft_zum_speichern``) — samt Generator-Vermerk.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.database import bibliothek_format as BF          # noqa: E402
from src.ui.widgets import fixture_generator as FG             # noqa: E402

from test_fm76_generator_herkunft import _AURO, _HANDBUCH, _Fall  # noqa: E402

import pytest                                                  # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets        # noqa: E402


@pytest.fixture(autouse=True)
def _keine_uebrigen_fenster():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


class MarkdownExportHerkunftTest(_Fall):

    def _exportieren(self, dlg) -> str:
        ziel = os.path.join(self.tmp, "export.md")
        with mock.patch.object(FG.QFileDialog, "getSaveFileName",
                               return_value=(ziel, "")):
            dlg._export_markdown()
        self.assertEqual(self.meldung["warning"].call_args_list, [])
        with open(ziel, encoding="utf-8") as fh:
            return fh.read()

    def test_qlcplus_vorlage_exportiert_lizenz_urheber_original(self):
        """Der Befund: Auro Spot (QLC+, Apache-2.0) laden, als Markdown
        exportieren — Herkunftsblock mit Lizenz, Urheber, Original, Quelle
        und dem Vermerk, dass im Generator bearbeitet wurde."""
        vorlage = BF.lade_datei(_AURO)
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM77")
        md = self._exportieren(dlg)
        self.assertIn("## Herkunft", md)
        self.assertIn("- Art: QLC+", md)
        self.assertIn("- Lizenz: Apache-2.0", md)
        self.assertIn(f"- Urheber: {vorlage['herkunft']['urheber']}", md)
        self.assertIn(f"- Original: {vorlage['herkunft']['original']}", md)
        self.assertIn(vorlage["quelle"]["titel"], md)
        self.assertIn(vorlage["quelle"]["url"], md)
        geaendert = [z for z in md.splitlines() if z.startswith("- Geändert:")]
        self.assertEqual(len(geaendert), 1)
        self.assertIn(BF.GENERATOR_VERMERK, geaendert[0])
        self.assertIn("im LightOS-Fixture-Generator bearbeitet", geaendert[0])
        # Der Block steht vor den Kanaltabellen, nicht irgendwo dahinter.
        self.assertLess(md.index("## Herkunft"), md.index("| # | Name"))

    def test_export_gleicht_der_gespeicherten_herkunft(self):
        """Was exportiert wird, ist genau das, was gespeichert wuerde."""
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM77")
        h = FG.herkunft_zum_speichern(dlg._model)
        md = FG.model_to_markdown(dlg._model)
        self.assertIn(f"- Geändert: {h['herkunft']['geaendert']}", md)
        self.assertIn(f"- Autor: {h['autor']}", md)

    def test_qxf_import_exportiert_apache_lizenz(self):
        dlg = self._dialog()
        self._qxf_laden(dlg)
        md = self._exportieren(dlg)
        self.assertIn("- Lizenz: Apache-2.0", md)
        self.assertIn("- Urheber:", md)
        self.assertIn("Testautorin", md)
        self.assertIn("- Original: FM76-Par.qxf", md)
        self.assertIn(BF.GENERATOR_VERMERK, md)

    def test_handbuch_vorlage_ohne_fremd_vermerk(self):
        """Nicht-fremde Herkunft (Herstellerhandbuch): Block ja, aber kein
        Apache-§4b-Vermerk erfunden — wie beim Speichern (``mit_vermerk``)."""
        vorlage = BF.lade_datei(_HANDBUCH)
        dlg = self._dialog()
        self._datei_laden(dlg, _HANDBUCH, modell="Pint FM77")
        md = self._exportieren(dlg)
        self.assertIn("- Art: Herstellerhandbuch", md)
        self.assertIn(f"- Lizenz: {vorlage['herkunft']['lizenz']}", md)
        self.assertEqual(BF.GENERATOR_VERMERK in md,
                         BF.GENERATOR_VERMERK in vorlage["herkunft"].get("geaendert", ""))

    def test_frei_gebaut_ist_eigen(self):
        dlg = self._dialog()
        md = self._exportieren(dlg)
        self.assertIn("**Herkunft:** eigen", md)
        self.assertNotIn("## Herkunft", md)
        self.assertNotIn("Lizenz", md)

    def test_nicht_belegbar_wird_nicht_still_eigen(self):
        m = FG.GeneratorModel(herkunft_fehlt="Grund XY")
        md = FG.model_to_markdown(m)
        self.assertIn("**Herkunft:** nicht belegbar — Grund XY", md)
        self.assertNotIn("eigen", md)


if __name__ == "__main__":
    unittest.main()
