"""FM-25: Der Fixture-Editor speicherte pro Modus nur den LETZTEN Kanal.

In ``FixtureEditorDialog._save`` stand ``s.add(fc)`` eine Einrueckungsebene zu
weit links und lief damit erst NACH der Kanalschleife. Angelegt wurde genau ein
Kanal je Modus — waehrend ``channel_count`` aus ``len(chans)`` kam und stimmte.
**Die Datenbank widersprach sich selbst.**

★ Beim BEARBEITEN ist das zerstoerend: ``_save`` loescht die alten Modi vorher.
Wer ein 152-Kanal-Profil oeffnete und nur den Namen aenderte, hatte danach ein
Profil mit einem Kanal.

**Warum es niemandem aufgefallen ist:** ``test_fixture_editor_roundtrip.py``
arbeitet mit einem Profil, das genau EINEN Kanal hat — dort ist „alle" und „der
letzte" dasselbe. Diese Datei nimmt deshalb ausdruecklich mehrere.
"""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy.orm import Session

import src.ui.widgets.fixture_editor as editor_module
from src.core.database.fixture_db import get_engine
from src.core.database.models import (FixtureProfile, FixtureMode,
                                      create_all_idempotent)

_app = QApplication.instance() or QApplication([])

# Mehr als einer — das ist der ganze Punkt. Mit Ranges auf einem NICHT-letzten
# Kanal, damit auch die Range-Schleife gemessen wird: sie stand im selben
# falsch eingerueckten Block.
_KANAELE = [
    {"name": "Dimmer", "attribute": "dimmer", "default": 0},
    {"name": "Rot", "attribute": "color_r", "default": 0,
     "ranges": [{"range_from": 0, "range_to": 127, "name": "unten"},
                {"range_from": 128, "range_to": 255, "name": "oben"}]},
    {"name": "Gruen", "attribute": "color_g", "default": 0},
    {"name": "Blau", "attribute": "color_b", "default": 0},
    {"name": "Shutter", "attribute": "shutter", "default": 255},
]


class _EditorFall(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        p1 = mock.patch.object(editor_module, "engine", lambda: self.engine)
        p1.start(); self.addCleanup(p1.stop)
        p2 = mock.patch.object(editor_module.QMessageBox, "information")
        p2.start(); self.addCleanup(p2.stop)

    def _anlegen(self, short="MEHRKANAL") -> int:
        """Legt ueber den ECHTEN Dialog ein Profil mit mehreren Kanaelen an."""
        dlg = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText("Mehrkanal-Geraet")
        dlg._edit_short.setText(short)
        # Ueber den echten Weg, den auch der Ladepfad benutzt.
        while dlg._tabs.count():
            dlg._tabs.removeTab(0)
        dlg._add_mode(name="Standard", channels=[dict(c) for c in _KANAELE])
        dlg._save()
        return dlg._saved_id

    def _kanaele(self, pid: int, modus="Standard"):
        with Session(self.engine) as s:
            prof = s.get(FixtureProfile, pid)
            mode = next(m for m in prof.modes if m.name == modus)
            return ([(c.channel_number, c.name, c.attribute)
                     for c in sorted(mode.channels, key=lambda c: c.channel_number)],
                    mode.channel_count,
                    {c.name: len(c.ranges) for c in mode.channels})


class AlleKanaeleKommenAnTest(_EditorFall):

    def test_anlegen_speichert_JEDEN_kanal(self):
        pid = self._anlegen()
        kanaele, anzahl, _ = self._kanaele(pid)
        self.assertEqual(
            len(_KANAELE), len(kanaele),
            f"Es sind {len(kanaele)} von {len(_KANAELE)} Kanaelen angekommen. "
            f"Steht `s.add(fc)` wieder ausserhalb der Kanalschleife, ist es "
            f"genau einer — der letzte: {kanaele}")
        self.assertEqual([c["name"] for c in _KANAELE],
                         [k[1] for k in kanaele], "Reihenfolge oder Namen falsch")

    def test_die_datenbank_widerspricht_sich_nicht_mehr(self):
        """★ Der eigentliche Befund: `channel_count` kam aus `len(chans)` und
        stimmte, waehrend nur ein Kanal wirklich da war."""
        pid = self._anlegen()
        kanaele, anzahl, _ = self._kanaele(pid)
        self.assertEqual(
            anzahl, len(kanaele),
            f"`channel_count` sagt {anzahl}, tatsaechlich gespeichert sind "
            f"{len(kanaele)} — die Datenbank widerspricht sich selbst.")

    def test_die_ranges_eines_NICHT_letzten_kanals_kommen_mit(self):
        """Die Range-Schleife stand im selben falsch eingerueckten Block. Ranges
        auf dem LETZTEN Kanal waeren auch vorher angekommen — deshalb haengen
        sie hier am zweiten."""
        pid = self._anlegen()
        _, _, ranges = self._kanaele(pid)
        self.assertEqual(2, ranges.get("Rot", 0),
                         f"Die Ranges des zweiten Kanals fehlen: {ranges}")

    def test_bearbeiten_zerstoert_die_kanaele_nicht(self):
        """★ Der zerstoererische Fall. `_save` loescht die alten Modi vorher —
        wer ein Profil oeffnete und nur den Namen aenderte, hatte danach ein
        Geraet mit einem Kanal."""
        pid = self._anlegen()
        vorher, _, _ = self._kanaele(pid)
        dlg = editor_module.FixtureEditorDialog(fixture_id=pid)
        self.addCleanup(dlg.deleteLater)
        dlg._edit_name.setText("Mehrkanal-Geraet v2")
        dlg._save()
        nachher, anzahl, _ = self._kanaele(pid)
        self.assertEqual(
            vorher, nachher,
            f"Nach dem blossen Umbenennen sind aus {len(vorher)} Kanaelen "
            f"{len(nachher)} geworden.")
        self.assertEqual(anzahl, len(nachher))

    def test_positivkontrolle_ein_einkanal_profil_bleibt_richtig(self):
        """Genau der Fall, den `test_fixture_editor_roundtrip.py` prueft — dort
        ist „alle" und „der letzte" dasselbe, und deshalb ist der Fehler dort
        nie aufgefallen. Er muss weiterhin durchgehen."""
        dlg = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText("Einkanal")
        dlg._edit_short.setText("EINKANAL")
        while dlg._tabs.count():
            dlg._tabs.removeTab(0)
        dlg._add_mode(name="Standard",
                      channels=[{"name": "Dimmer", "attribute": "dimmer",
                                 "default": 0}])
        dlg._save()
        kanaele, anzahl, _ = self._kanaele(dlg._saved_id)
        self.assertEqual(1, len(kanaele))
        self.assertEqual(1, anzahl)


if __name__ == "__main__":
    unittest.main()
