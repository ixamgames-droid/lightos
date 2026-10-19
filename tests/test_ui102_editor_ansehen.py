"""UI-102: Fixture-Editor im Ansehen-Modus wirkt nicht mehr bearbeitbar.

Ein mitgeliefertes Profil oeffnet im Ansehen-Modus. Bisher stand nur im
Fenstertitel, dass nichts gespeichert wird; Felder, Auswahlen und
Tabellenzellen sahen bearbeitbar aus. Jetzt: Hinweiszeile im Dialog, Felder
schreibgeschuetzt und gekennzeichnet (``nurAnsehen``), Tabelle ohne
Bearbeiten-Ausloeser, „Abbrechen“ heisst „Schließen“. Die Kopie
(„Als eigenes Profil kopieren“) und eigene Profile bleiben voll bearbeitbar.

Alle DBs sind Temp-DBs — die echte fixtures.db bleibt unberuehrt.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                        # noqa: E402
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox,  # noqa: E402
                               QApplication, QComboBox, QLineEdit)
from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.database.fixture_db import get_engine                  # noqa: E402
from src.core.database.models import (FixtureChannel, FixtureMode,   # noqa: E402
                                      FixtureProfile, Manufacturer,
                                      create_all_idempotent)
from src.ui.widgets import fixture_editor as editor_module           # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _profil(s, mfr, name, source, herkunft=""):
    p = FixtureProfile(manufacturer=mfr, name=name, short_name=name[:8].upper(),
                       fixture_type="par", source=source, herkunft=herkunft)
    m = FixtureMode(fixture=p, name="8-Kanal", channel_count=6)
    for i, attr in enumerate(("intensity", "color_r", "color_g", "color_b",
                              "color_w", "intensity"), 1):
        m.channels.append(FixtureChannel(channel_number=i, name=f"K{i}",
                                         attribute=attr))
    s.add(p)
    s.flush()
    return p.id


class _TempDB(unittest.TestCase):

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        with Session(self.engine) as s:
            m = Manufacturer(name="ADJ", short_name="ADJ")
            self.pid_lightos = _profil(s, m, "5PX HEX", "lightos")
            self.pid_user = _profil(s, m, "Eigenbau HEX", "user")
            self.pid_qlc = _profil(s, m, "Import HEX", "qlcplus")
            s.commit()
        p = mock.patch.object(editor_module, "engine", lambda: self.engine)
        p.start()
        self.addCleanup(p.stop)
        for name in ("information", "warning"):
            p = mock.patch.object(editor_module.QMessageBox, name)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(editor_module, "_gepatchte_geraete", lambda: [])
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def _felder(dlg):
        tab = dlg._tabs.widget(0)
        kopf = [dlg._cb_manufacturer, dlg._edit_name, dlg._edit_short,
                dlg._cb_type, dlg._spin_power]
        modus = [tab._edit_name, tab._spin_grid_rows, tab._spin_grid_cols,
                 tab._spin_white_rows, tab._spin_white_cols]
        zellen = [tab._tbl.cellWidget(r, c)
                  for r in range(tab._tbl.rowCount())
                  for c in range(tab._tbl.columnCount())
                  if tab._tbl.cellWidget(r, c) is not None]
        return kopf + modus + zellen

    @staticmethod
    def _bearbeitbar(w) -> bool:
        if isinstance(w, (QLineEdit, QAbstractSpinBox)):
            return w.isEnabled() and not w.isReadOnly()
        return w.isEnabled()


class AnsehenTest(_TempDB):

    def _dlg(self, **kw):
        return editor_module.FixtureEditorDialog(fixture_id=self.pid_lightos, **kw)

    def test_hinweiszeile_im_dialog(self):
        dlg = self._dlg(nur_ansehen=True)
        self.assertFalse(dlg._lbl_nur_ansehen.isHidden())
        text = dlg._lbl_nur_ansehen.text()
        self.assertIn("Mitgeliefertes Profil", text)
        self.assertIn("nur ansehen", text)
        self.assertIn("Als eigenes Profil kopieren", text)
        # im Dialog, nicht nur im Titel
        self.assertIs(dlg._lbl_nur_ansehen.window(), dlg)

    def test_auch_ohne_flag_bei_mitgeliefertem_profil(self):
        dlg = self._dlg()          # Editor prueft die Quelle selbst (UI-74)
        self.assertFalse(dlg._lbl_nur_ansehen.isHidden())
        self.assertTrue(all(not self._bearbeitbar(w) for w in self._felder(dlg)))

    def test_felder_sichtbar_schreibgeschuetzt(self):
        dlg = self._dlg(nur_ansehen=True)
        felder = self._felder(dlg)
        # Kopf (5) + Modus (5) + Kombis: 6x Attribut, 2 Dimmer -> 2 Segment
        self.assertEqual(len(felder), 5 + 5 + 6 + 2)
        for w in felder:
            with self.subTest(feld=type(w).__name__, name=w.objectName()):
                self.assertFalse(self._bearbeitbar(w))
                self.assertTrue(w.property(editor_module.NUR_ANSEHEN_EIGENSCHAFT))
        for sp in felder:
            if isinstance(sp, QAbstractSpinBox):
                self.assertEqual(sp.buttonSymbols(),
                                 QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.assertIn("nurAnsehen", dlg.styleSheet())

    @staticmethod
    def _hintergrund(w):
        """Farbe am rechten Feldrand (innen, abseits von Text und Rahmen)."""
        w.ensurePolished()
        img = w.grab().toImage()
        return img.pixelColor(img.width() - 4, img.height() // 2).name()

    def test_optik_kommt_wirklich_an(self):
        """Gegenpruefung: Eigenschaft + Stylesheet-Text allein reichen nicht —
        ohne unpolish/polish bliebe das Feld hell. Darum Pixel vergleichen."""
        dlg = self._dlg(nur_ansehen=True)
        dlg.show()
        _app.processEvents()
        eigen = editor_module.FixtureEditorDialog(fixture_id=self.pid_user)
        eigen.show()
        _app.processEvents()
        tab_a, tab_e = dlg._tabs.widget(0), eigen._tabs.widget(0)
        paare = [(dlg._edit_short, eigen._edit_short, "Kurzname"),
                 (dlg._spin_power, eigen._spin_power, "Leistung"),
                 (tab_a._edit_name, tab_e._edit_name, "Mode-Name")]
        for a, e, name in paare:
            with self.subTest(feld=name):
                self.assertEqual(self._hintergrund(a), "#2e2e2e")
                self.assertNotEqual(self._hintergrund(e), "#2e2e2e")

    def test_tabelle_ohne_bearbeiten(self):
        dlg = self._dlg(nur_ansehen=True)
        tbl = dlg._tabs.widget(0)._tbl
        self.assertEqual(tbl.editTriggers(),
                         QAbstractItemView.EditTrigger.NoEditTriggers)
        for r in range(tbl.rowCount()):
            for c in range(tbl.columnCount()):
                it = tbl.item(r, c)
                if it is not None:
                    self.assertFalse(it.flags() & Qt.ItemFlag.ItemIsEditable,
                                     f"Zelle {r},{c} bearbeitbar")
        self.assertTrue(tbl.property(editor_module.NUR_ANSEHEN_EIGENSCHAFT))

    def test_neu_gebaute_zeilen_bleiben_gesperrt(self):
        dlg = self._dlg(nur_ansehen=True)
        tab = dlg._tabs.widget(0)
        tab._rebuild_rows()
        for w in self._felder(dlg)[10:]:
            self.assertFalse(w.isEnabled())

    def test_schliessen_statt_abbrechen_export_offen(self):
        dlg = self._dlg(nur_ansehen=True)
        self.assertEqual(dlg._btn_cancel.text(), "Schließen")
        self.assertTrue(dlg._btn_cancel.isEnabled())
        self.assertFalse(dlg._btn_save.isEnabled())


class KopierenUndEigenesTest(_TempDB):

    def _pruefe_offen(self, dlg):
        self.assertTrue(dlg._lbl_nur_ansehen.isHidden())
        self.assertEqual(dlg.styleSheet(), "")
        for w in self._felder(dlg):
            with self.subTest(feld=type(w).__name__):
                self.assertTrue(self._bearbeitbar(w))
                self.assertFalse(w.property(editor_module.NUR_ANSEHEN_EIGENSCHAFT))
        tbl = dlg._tabs.widget(0)._tbl
        self.assertNotEqual(tbl.editTriggers(),
                            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.assertTrue(dlg._btn_save.isEnabled())
        self.assertNotEqual(dlg._btn_cancel.text(), "Schließen")

    def test_kopie_bleibt_bedienbar_und_speichert(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_qlc,
                                                als_kopie=True)
        self._pruefe_offen(dlg)
        dlg._edit_short.setText("KOPIE")
        dlg._save()
        self.assertIsNotNone(dlg.saved_id)
        with Session(self.engine) as s:
            neu = s.get(FixtureProfile, dlg.saved_id)
            self.assertEqual((neu.source, neu.short_name), ("user", "KOPIE"))

    def test_kopie_eines_mitgelieferten_profils_bleibt_bedienbar(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_lightos,
                                                als_kopie=True)
        self._pruefe_offen(dlg)

    def test_eigenes_profil_bearbeitbar(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_user)
        self._pruefe_offen(dlg)

    def test_neues_profil_ohne_hinweis(self):
        dlg = editor_module.FixtureEditorDialog()
        self.assertTrue(dlg._lbl_nur_ansehen.isHidden())
        self.assertFalse(dlg._edit_name.isReadOnly())


if __name__ == "__main__":
    unittest.main()
