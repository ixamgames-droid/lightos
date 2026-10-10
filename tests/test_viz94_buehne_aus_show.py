"""VIZ-94: eine Show von einem anderen Rechner zeigt ihre Traversen und Buehnen-Elemente.

Befund (Windows-ARM-PC, Sitzung B, 08.10.2026): der 3D-Viewer zeigte alle
Fixtures, aber keine Traversen. Gemessen im echten Fenster mit der frisch
gebauten Mega Arena: ``window.__lightos.stageObjects`` blieb in JEDER Stufe
(Niedrig/Hoch/Maximal) und in beiden Modi (Ansehen/Bauen) leer — das
Zusammenfassen aus VIZ-72 war also nicht schuld. Mit der Buehnen-Datei im
App-Ordner kamen dieselben 9 Elemente an (Ansehen: 2 Sammelkoerper, +7600
Dreiecke).

Ursache: der Visualizer holt die Buehne NUR per Namen aus
``stages_dir()/<Name>.json`` (``resolve_active_stage`` -> ``load_stage``).
Die Datei entsteht dort, wo die Show gebaut wurde (TOOL-13: Generatoren
schreiben in den App-Ordner des bauenden Rechners) und reist nicht mit. Die
``.lshow`` traegt die Elemente aber vollstaendig im ``scene_graph`` (Art,
Lage, Drehung, Groesse, Farbe, Name, dieselben IDs).

Fix: ``load_show`` legt die Buehnen-Datei aus dem Szenengraph an, wenn sie im
App-Ordner fehlt. Eine vorhandene Datei gewinnt (Nutzer-Bearbeitung).
"""
import json
import math
import os
import shutil
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.show import show_file as SF
from src.core.stage import stage_definition as SD


def _knoten(nid, kind, pos, size, rot_y=0.0, color="#2a2a3a", name=""):
    return {"id": nid, "kind": kind,
            "transform": {"pos_m": list(pos), "rot_deg": [0.0, rot_y, 0.0],
                          "scale": [1.0, 1.0, 1.0]},
            "parent_id": None, "mount_type": "floor",
            "size_m": list(size), "color": color, "name": name}


class BuehneAusShowTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="viz94_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(SF.reset_show)
        self._entfernen = []
        self.addCleanup(lambda: [SD.delete_stage(n) for n in self._entfernen])

    def _fremde_show(self, stage_name, knoten):
        """Show wie von einem anderen Rechner: Buehnen-Name + Szenengraph, aber
        keine Buehnen-Datei in diesem App-Ordner."""
        SF.reset_show()
        pfad = os.path.join(self.tmp, f"{stage_name}.lshow")
        SF.save_show(pfad)
        with zipfile.ZipFile(pfad) as z:
            inhalt = {n: z.read(n) for n in z.namelist()}
        show = json.loads(inhalt["show.json"])
        show.setdefault("visualizer", {})["active_stage"] = stage_name
        show["scene_graph"] = {"nodes": knoten,
                               "stage_snapshot": {"name": stage_name, "source": "user"}}
        inhalt["show.json"] = json.dumps(show).encode("utf-8")
        with zipfile.ZipFile(pfad, "w") as z:
            for n, b in inhalt.items():
                z.writestr(n, b)
        self._entfernen.append(stage_name)
        return pfad

    def test_fehlende_buehnen_datei_entsteht_aus_dem_szenengraph(self):
        name = "VIZ94 Fremde Buehne"
        SD.delete_stage(name)
        self.assertIsNone(SD.load_stage(name), "Testaufbau: Datei darf nicht da sein")
        pfad = self._fremde_show(name, [
            _knoten("el_a", "truss_h", (0.0, 5.5, 2.6), (16.0, 0.3, 0.3), name="Front-Traverse"),
            _knoten("el_b", "platform", (1.0, 0.3, -0.5), (18.0, 0.6, 6.0), rot_y=90.0,
                    color="#112233", name="Buehne"),
            # Geister-Platzhalter (Dock auf unbekannte ID): keine Geometrie -> kein Element
            {"id": "el_geist", "kind": "platform", "transform": {}, "parent_id": None},
        ])
        ok, msg = SF.load_show(pfad)
        self.assertTrue(ok, msg)
        stage = SD.load_stage(name)
        self.assertIsNotNone(stage, "Buehne der Show fehlt nach dem Laden (VIZ-94)")
        els = {e.id: e for e in stage.elements}
        self.assertEqual({"el_a", "el_b"}, set(els))
        a, b = els["el_a"], els["el_b"]
        self.assertEqual(("truss_h", 0.0, 5.5, 2.6, 16.0, 0.3, 0.3, "Front-Traverse"),
                         (a.type, a.x, a.y, a.z, a.w, a.h, a.d, a.name))
        self.assertEqual(("platform", "#112233"), (b.type, b.color))
        self.assertAlmostEqual(math.radians(90.0), b.rotation, places=6)

    def test_der_visualizer_findet_sie_als_nutzer_buehne(self):
        name = "VIZ94 Visualizer"
        SD.delete_stage(name)
        pfad = self._fremde_show(name, [
            _knoten("el_v", "truss_v", (-8.0, 2.75, 2.6), (0.3, 5.5, 0.3))])
        ok, msg = SF.load_show(pfad)
        self.assertTrue(ok, msg)
        stage, art, combo = SD.resolve_active_stage(name)
        self.assertEqual(("user", name), (art, combo),
                         "Visualizer faellt auf die leere Standardbuehne zurueck")
        self.assertEqual(["el_v"], [e.id for e in stage.elements])

    def test_vorhandene_buehnen_datei_gewinnt(self):
        name = "VIZ94 Eigene Buehne"
        eigen = SD.StageDefinition(name=name)
        eigen.add("wall", id="el_eigen", x=1.0, y=2.0, z=3.0)
        SD.save_stage(eigen)
        self._entfernen.append(name)
        pfad = self._fremde_show(name, [
            _knoten("el_x", "truss_h", (0.0, 5.0, 0.0), (10.0, 0.3, 0.3)),
            _knoten("el_y", "truss_h", (0.0, 5.0, 4.0), (10.0, 0.3, 0.3))])
        ok, msg = SF.load_show(pfad)
        self.assertTrue(ok, msg)
        self.assertEqual(["el_eigen"], [e.id for e in SD.load_stage(name).elements],
                         "die Nutzer-Buehne im App-Ordner darf nicht ueberschrieben werden")

    def test_preset_bleibt_preset(self):
        pfad = self._fremde_show("simple", [
            _knoten("el_p", "truss_h", (0.0, 5.0, 0.0), (10.0, 0.3, 0.3))])
        self._entfernen.remove("simple")
        ok, msg = SF.load_show(pfad)
        self.assertTrue(ok, msg)
        self.assertIsNone(SD.load_stage("simple"),
                          "fuer einen Preset-Namen darf keine Nutzer-Datei entstehen")


if __name__ == "__main__":
    unittest.main()
