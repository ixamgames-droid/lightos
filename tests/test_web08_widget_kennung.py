"""WEB-08: feste Kennung je VC-Widget.

Die Handy-Konsole (WEB-07, Konzept A) legt Widgets der grossen Konsole als
VERKNUEPFUNG ab. Eine Verknuepfung braucht etwas, das Umsortieren, Verschieben
und Speichern/Laden ueberlebt — Typ, Lage und Beschriftung tun das nicht.

Geprueft wird die Kennung an allen Wegen, auf denen ein Widget entsteht oder
wiederkommt: neu, aus einer Alt-Show ohne Kennung, als Kopie, per Undo/Redo,
im Typ-Tausch und aus einer Datei mit doppelten Kennungen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_frame import VCFrame
from src.ui.virtualconsole.vc_widget import VCWidget

_app = QApplication.instance() or QApplication([])


def _alle_kennungen(canvas) -> list[str]:
    return [w.widget_id for w in canvas.findChildren(VCWidget)]


def _alt_show() -> dict:
    """Layout im Format VOR WEB-08: kein Feld ``id``, ein Frame mit Kindern."""
    return {"widgets": [
        {"type": "VCButton", "caption": "Strobe", "x": 8, "y": 8, "w": 72, "h": 72},
        {"type": "VCSlider", "caption": "Master", "x": 96, "y": 8, "w": 60, "h": 200},
        {"type": "VCFrame", "caption": "Farben", "x": 200, "y": 8, "w": 300, "h": 200,
         "children": [
             {"type": "VCButton", "caption": "Rot", "x": 8, "y": 30, "w": 72, "h": 72},
             {"type": "VCButton", "caption": "Blau", "x": 90, "y": 30, "w": 72, "h": 72},
         ]},
    ]}


class KennungGrundlagenTest(unittest.TestCase):
    def setUp(self):
        self.canvas = VCCanvas()

    def tearDown(self):
        self.canvas.close()
        self.canvas.deleteLater()

    def test_neues_widget_hat_kennung(self):
        a = self.canvas._add_widget("VCButton", QPoint(10, 10))
        b = self.canvas._add_widget("VCButton", QPoint(100, 10))
        self.assertIsInstance(a.widget_id, str)
        self.assertTrue(a.widget_id)
        self.assertNotEqual(a.widget_id, b.widget_id)

    def test_kennung_ist_nie_eine_reine_ziffernfolge(self):
        # patch_dedup._als_ints liest Ziffern-Strings im VC-Layout als Zahlen
        # ("kommt diese Geraete-ID in der Konsole vor?"). Eine Kennung, die nur
        # aus Ziffern besteht, wuerde dort als Geraete-ID gezaehlt.
        from src.ui.virtualconsole.vc_widget import neue_kennung
        for _ in range(500):
            self.assertFalse(neue_kennung().lstrip("-").isdigit())

    def test_kennung_steht_in_to_dict_und_kommt_zurueck(self):
        a = self.canvas._add_widget("VCButton", QPoint(10, 10))
        kennung = a.widget_id
        d = self.canvas.to_dict()
        self.assertEqual(d["widgets"][0]["id"], kennung)
        self.canvas.from_dict(d)
        self.assertEqual(_alle_kennungen(self.canvas), [kennung])

    def test_frame_kinder_tragen_eigene_kennungen(self):
        self.canvas.from_dict(_alt_show())
        frame = self.canvas.findChildren(VCFrame)[0]
        d = frame.to_dict()
        kinder = [c["id"] for c in d["children"]]
        self.assertEqual(len(set(kinder + [d["id"]])), 3)


class AltShowTest(unittest.TestCase):
    def setUp(self):
        self.canvas = VCCanvas()

    def tearDown(self):
        self.canvas.close()
        self.canvas.deleteLater()

    def test_alt_show_bekommt_beim_laden_kennungen(self):
        self.canvas.from_dict(_alt_show())
        kennungen = _alle_kennungen(self.canvas)
        self.assertEqual(len(kennungen), 5)
        self.assertTrue(all(kennungen))
        self.assertEqual(len(set(kennungen)), 5)

    def test_kennungen_bleiben_nach_speichern_und_laden(self):
        self.canvas.from_dict(_alt_show())
        vorher = {w.caption: w.widget_id for w in self.canvas.findChildren(VCWidget)}
        gespeichert = self.canvas.to_dict()
        zweite = VCCanvas()
        try:
            zweite.from_dict(gespeichert)
            nachher = {w.caption: w.widget_id for w in zweite.findChildren(VCWidget)}
            self.assertEqual(nachher, vorher)
            # und ein zweites Mal — die Kennung darf nicht bei jedem Durchgang kippen
            dritte_runde = zweite.to_dict()
            zweite.from_dict(dritte_runde)
            self.assertEqual(
                {w.caption: w.widget_id for w in zweite.findChildren(VCWidget)}, vorher)
        finally:
            zweite.close()
            zweite.deleteLater()

    def test_ungueltige_kennung_wird_ersetzt(self):
        layout = {"widgets": [
            {"type": "VCButton", "caption": "a", "id": ""},
            {"type": "VCButton", "caption": "b", "id": 17},
            {"type": "VCButton", "caption": "c", "id": None},
            {"type": "VCButton", "caption": "d", "id": "../../etc"},
            {"type": "VCButton", "caption": "e", "id": "x" * 300},
            {"type": "VCButton", "caption": "f", "id": "123456"},
        ]}
        self.canvas.from_dict(layout)
        from src.ui.virtualconsole.vc_widget import kennung_gueltig
        kennungen = _alle_kennungen(self.canvas)
        self.assertEqual(len(set(kennungen)), 6)
        for k in kennungen:
            self.assertTrue(kennung_gueltig(k), k)
        self.assertNotIn("../../etc", kennungen)
        self.assertNotIn("123456", kennungen)


class DoppelteKennungTest(unittest.TestCase):
    """'VC Layout laden' darf keine zwei Widgets mit derselben Kennung ergeben —
    eine Verknuepfung haette dann zwei Ziele."""

    def setUp(self):
        self.canvas = VCCanvas()

    def tearDown(self):
        self.canvas.close()
        self.canvas.deleteLater()

    def test_doppelte_kennung_wird_beim_laden_repariert(self):
        layout = {"widgets": [
            {"type": "VCButton", "caption": "erste", "id": "wdoppelt0001"},
            {"type": "VCButton", "caption": "zweite", "id": "wdoppelt0001"},
            {"type": "VCFrame", "caption": "kasten", "id": "wkasten00001", "children": [
                {"type": "VCButton", "caption": "dritte", "id": "wdoppelt0001"},
                {"type": "VCButton", "caption": "vierte", "id": "wkasten00001"},
            ]},
        ]}
        self.canvas.from_dict(layout)
        nach = {w.caption: w.widget_id for w in self.canvas.findChildren(VCWidget)}
        self.assertEqual(len(set(nach.values())), 5)
        # das ERSTE Vorkommen behaelt die Kennung — eine bestehende Verknuepfung
        # zeigt weiter auf dasselbe Widget wie vor dem Laden
        self.assertEqual(nach["erste"], "wdoppelt0001")
        self.assertEqual(nach["kasten"], "wkasten00001")

    def test_reparatur_ist_nach_speichern_stabil(self):
        layout = {"widgets": [
            {"type": "VCButton", "caption": "erste", "id": "wdoppelt0001"},
            {"type": "VCButton", "caption": "zweite", "id": "wdoppelt0001"},
        ]}
        self.canvas.from_dict(layout)
        einmal = self.canvas.to_dict()
        self.canvas.from_dict(einmal)
        self.assertEqual(self.canvas.to_dict(), einmal)

    def test_widget_mit_kennung_findet_auch_frame_kinder(self):
        self.canvas.from_dict(_alt_show())
        for w in self.canvas.findChildren(VCWidget):
            self.assertIs(self.canvas.widget_mit_kennung(w.widget_id), w)
        self.assertIsNone(self.canvas.widget_mit_kennung("wgibtesnicht"))
        self.assertIsNone(self.canvas.widget_mit_kennung(None))


class KopieTest(unittest.TestCase):
    """Eine Kopie ist ein ZWEITES Widget: es bekommt eine neue Kennung, das
    Original behaelt seine."""

    def setUp(self):
        self.canvas = VCCanvas()

    def tearDown(self):
        self.canvas.close()
        self.canvas.deleteLater()

    def test_kopie_aus_dict_bekommt_neue_kennung(self):
        original = self.canvas._add_widget("VCButton", QPoint(10, 10))
        original.caption = "Original"
        kennung = original.widget_id
        kopie = self.canvas._add_widget("VCButton", QPoint(100, 10),
                                        dict(original.to_dict(), caption="Kopie"))
        self.assertEqual(original.widget_id, kennung)
        self.assertNotEqual(kopie.widget_id, kennung)
        self.assertEqual(kopie.caption, "Kopie")

    def test_kopie_eines_frames_gibt_auch_den_kindern_neue_kennungen(self):
        self.canvas.from_dict(_alt_show())
        frame = self.canvas.findChildren(VCFrame)[0]
        vorher = set(_alle_kennungen(self.canvas))
        self.canvas._add_widget("VCFrame", QPoint(600, 10), frame.to_dict())
        nachher = _alle_kennungen(self.canvas)
        self.assertEqual(len(nachher), 8)
        self.assertEqual(len(set(nachher)), 8)
        # die alten Widgets haben ihre Kennungen behalten
        self.assertTrue(vorher.issubset(set(nachher)))

    def test_kopie_dict_traegt_keine_kennung(self):
        from src.ui.virtualconsole.vc_widget import ohne_kennung
        self.canvas.from_dict(_alt_show())
        frame = self.canvas.findChildren(VCFrame)[0]
        original = frame.to_dict()
        kopie = ohne_kennung(original)
        self.assertNotIn("id", kopie)
        self.assertTrue(all("id" not in c for c in kopie["children"]))
        # das Original-Dict bleibt unveraendert (kein Seiteneffekt auf den Undo-Stand)
        self.assertIn("id", original)
        self.assertTrue(all("id" in c for c in original["children"]))


class UndoRedoTest(unittest.TestCase):
    def setUp(self):
        self.canvas = VCCanvas()

    def tearDown(self):
        self.canvas.close()
        self.canvas.deleteLater()

    def test_loeschen_und_undo_bringt_dieselbe_kennung_zurueck(self):
        a = self.canvas._add_widget("VCButton", QPoint(10, 10))
        b = self.canvas._add_widget("VCSlider", QPoint(100, 10))
        ka, kb = a.widget_id, b.widget_id
        self.canvas._remove_widget(a)
        _app.processEvents()
        self.assertEqual(_alle_kennungen(self.canvas), [kb])
        self.canvas.undo()
        self.assertEqual(sorted(_alle_kennungen(self.canvas)), sorted([ka, kb]))
        self.canvas.redo()
        self.assertEqual(_alle_kennungen(self.canvas), [kb])
        self.canvas.undo()
        self.assertEqual(sorted(_alle_kennungen(self.canvas)), sorted([ka, kb]))

    def test_undo_eines_neuen_widgets_und_redo_erhaelt_die_kennung(self):
        a = self.canvas._add_widget("VCButton", QPoint(10, 10))
        ka = a.widget_id
        self.canvas.undo()
        self.assertEqual(_alle_kennungen(self.canvas), [])
        self.canvas.redo()
        self.assertEqual(_alle_kennungen(self.canvas), [ka])

    def test_undo_im_frame_erhaelt_die_kennungen(self):
        self.canvas.from_dict(_alt_show())
        vorher = {w.caption: w.widget_id for w in self.canvas.findChildren(VCWidget)}
        frame = self.canvas.findChildren(VCFrame)[0]
        kind = [w for w in frame.findChildren(VCWidget) if w.caption == "Rot"][0]
        frame._remove_child(kind)
        _app.processEvents()
        self.canvas.undo()
        nachher = {w.caption: w.widget_id for w in self.canvas.findChildren(VCWidget)}
        self.assertEqual(nachher, vorher)

    def test_typ_tausch_behaelt_die_kennung(self):
        # "Widget aendern" ersetzt das Objekt, gemeint ist aber dasselbe
        # Bedienelement an derselben Stelle — eine Verknuepfung soll halten.
        a = self.canvas._add_widget("VCButton", QPoint(10, 10))
        ka = a.widget_id
        neu = self.canvas.replace_widget_type(a, "VCSlider")
        _app.processEvents()
        self.assertIsNot(neu, a)
        self.assertEqual(neu.widget_id, ka)
        self.assertEqual(_alle_kennungen(self.canvas), [ka])


class UngespeichertTest(unittest.TestCase):
    """Eine Alt-Show, die beim Laden nur Kennungen bekommen hat, ist NICHT
    'geaendert' — sonst fragte LightOS bei jeder alten Show nach dem Speichern."""

    def test_kennung_zaehlt_nicht_als_aenderung(self):
        from src.core.show.show_file import _vc_ohne_live_werte
        alt = _alt_show()
        canvas = VCCanvas()
        try:
            canvas.from_dict(alt)
            mit = canvas.to_dict()
            self.assertNotEqual(mit, alt)

            def _kern(layout):
                # nur die Felder, die schon die Alt-Show hatte
                def _w(d, vorlage):
                    out = {k: d[k] for k in vorlage if k != "children"}
                    if "children" in vorlage:
                        out["children"] = [_w(c, v) for c, v
                                           in zip(d["children"], vorlage["children"])]
                    return out
                return [_w(d, v) for d, v in zip(layout["widgets"], alt["widgets"])]

            ohne = _vc_ohne_live_werte(mit)
            self.assertTrue(all("id" not in w for w in ohne["widgets"]))
            self.assertTrue(all("id" not in c for c in ohne["widgets"][2]["children"]))
            self.assertEqual(_kern(ohne), _kern(_vc_ohne_live_werte(alt)))
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_fremde_id_felder_bleiben_im_vergleich(self):
        # Nur die Kennung des WIDGETS faellt heraus — ein gleichnamiges Feld
        # tiefer in den Widget-Daten ist Inhalt und bleibt eine Aenderung.
        from src.core.show.show_file import _vc_ohne_live_werte
        layout = {"widgets": [{"type": "VCButton", "id": "wabc",
                               "actions": [{"type": "function", "id": 5}]}]}
        ohne = _vc_ohne_live_werte(layout)
        self.assertNotIn("id", ohne["widgets"][0])
        self.assertEqual(ohne["widgets"][0]["actions"][0]["id"], 5)


if __name__ == "__main__":
    unittest.main()
