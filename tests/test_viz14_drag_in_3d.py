"""VIZ-14 Drag-Haelfte — das GEZOGENE Geraet landet dort, wo man es fallen laesst.

Platzieren ging bisher nur per Rechtsklick, und der setzte „das naechste noch
unplatzierte Geraet". Welches das ist, stand nirgends — man platzierte blind und
sortierte hinterher. Der Plan verlangt ausdruecklich: „Klick-Platzierung nur fuer
das in der Liste selektierte Geraet (nie blind das naechste)".

**Die Machbarkeit wurde VOR dem Bauen gemessen:** ein Qt-Drag auf die
QWebEngineView kommt in der Seite als echtes ``dragenter``/``dragover``/``drop``
an, samt ``text/plain``-Nutzlast. Deshalb folgt der Geist im vollen
Ereignistakt des Zeigers statt im Poll-Intervall der Bruecke — und deshalb ist
die Nutzlast ``text/plain`` und nicht Qts eigenes
``application/x-qabstractitemmodeldatalist``, das in der Seite gar nicht ankaeme.

Drei Ebenen, absichtlich getrennt:

* die **Nutzlast** (reine Funktion, kein Qt),
* die **Qt-Seite** (Liste erzeugt den Drag, ``placeFixture`` versteht die fid),
* der **echte Weg** durch eine laufende QWebEngine.
"""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace                                   # noqa: E402
from unittest.mock import MagicMock                                 # noqa: E402

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidgetItem         # noqa: E402

import src.ui.visualizer.visualizer_window as VW                    # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class NutzlastTest(unittest.TestCase):
    """Das Format, auf das sich Qt-Seite und Seite einigen."""

    def test_liste_verpackt_die_fid_als_text(self):
        _app()
        liste = VW.FixtureDragList()
        self.addCleanup(liste.deleteLater)
        it = QListWidgetItem("[ ] [023] Hydra")
        it.setData(Qt.ItemDataRole.UserRole, 23)
        liste.addItem(it)

        md = liste.mimeData([it])

        self.assertEqual(md.text(), "lightos-fixture:23")
        self.assertTrue(md.hasText(),
                        "text/plain ist der Typ, den die WebEngine durchreicht")

    def test_mehrfachauswahl_zieht_genau_eines(self):
        """Der Geist zeigt EINE Pose und ein Drop setzt EINE Position — mehrere
        gleichzeitig haetten keine sichtbare Entsprechung."""
        _app()
        liste = VW.FixtureDragList()
        self.addCleanup(liste.deleteLater)
        items = []
        for fid in (7, 8):
            it = QListWidgetItem(f"[{fid}]")
            it.setData(Qt.ItemDataRole.UserRole, fid)
            liste.addItem(it)
            items.append(it)

        self.assertEqual(liste.mimeData(items).text(), "lightos-fixture:7")

    def test_eintrag_ohne_fid_erzeugt_keine_nutzlast(self):
        _app()
        liste = VW.FixtureDragList()
        self.addCleanup(liste.deleteLater)
        it = QListWidgetItem("Kopfzeile")
        liste.addItem(it)

        self.assertEqual(liste.mimeData([it]).text(), "")


class PlaceFixtureTest(unittest.TestCase):
    """``placeFixture`` muss die fid ernst nehmen — sonst landet das falsche
    Geraet dort, wo man gezielt eines fallengelassen hat."""

    def _bruecke(self, platziert=()):
        fixtures = [SimpleNamespace(fid=1), SimpleNamespace(fid=2),
                    SimpleNamespace(fid=3)]
        state = SimpleNamespace(
            get_patched_fixtures=lambda: fixtures,
            visualizer_positions={f: (0.0, 0.0, 0.0) for f in platziert},
            visualizer_docks={},
        )
        b = SimpleNamespace(
            _state=state,
            _write_back_to_live_view=MagicMock(),
            _fixture_to_dict=lambda f: {"fid": f.fid},
            fixtureAdded=MagicMock(),
            _sync_placeable=MagicMock(),
        )
        return b, state

    def _place(self, b, **payload):
        VW.VisualizerBridge.placeFixture.__wrapped__(b, json.dumps(payload)) \
            if hasattr(VW.VisualizerBridge.placeFixture, "__wrapped__") \
            else VW.VisualizerBridge.placeFixture(b, json.dumps(payload))

    def test_mit_fid_landet_genau_dieses_geraet(self):
        b, state = self._bruecke()
        self._place(b, x=2.0, y=6.5, z=-3.0, fid=3)

        self.assertIn(3, state.visualizer_positions)
        self.assertNotIn(1, state.visualizer_positions,
                         "das erste unplatzierte darf NICHT genommen werden")
        self.assertEqual(state.visualizer_positions[3], (2.0, 6.5, -3.0))

    def test_mit_fid_verschiebt_auch_ein_schon_platziertes(self):
        """Ein Drop auf ein bereits platziertes Geraet ist ein Verschieben —
        sonst passierte beim Ziehen sichtbar nichts."""
        b, state = self._bruecke(platziert=(2,))
        self._place(b, x=5.0, y=4.0, z=1.0, fid=2)

        self.assertEqual(state.visualizer_positions[2], (5.0, 4.0, 1.0))

    def test_ohne_fid_bleibt_das_bestandsverhalten(self):
        """Der Rechtsklick-Weg schickt keine fid und nimmt weiter das naechste
        unplatzierte Geraet."""
        b, state = self._bruecke(platziert=(1,))
        self._place(b, x=0.0, y=6.5, z=0.0)

        self.assertIn(2, state.visualizer_positions)
        self.assertNotIn(3, state.visualizer_positions)

    def test_unbrauchbare_fid_faellt_auf_das_bestandsverhalten_zurueck(self):
        b, state = self._bruecke()
        self._place(b, x=0.0, y=6.5, z=0.0, fid="quatsch")

        self.assertIn(1, state.visualizer_positions,
                      "lieber das Bestandsverhalten als gar nichts zu tun")

    def test_dock_wird_uebernommen(self):
        b, state = self._bruecke()
        self._place(b, x=1.0, y=3.0, z=2.0, fid=2, dock="truss-1")

        self.assertEqual(state.visualizer_docks[2], "truss-1")


if __name__ == "__main__":
    unittest.main()
