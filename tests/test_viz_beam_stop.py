"""VIZ-BEAM-OCCLUSION Teil 2 — der Strahl endet am ersten Körper, nicht am Boden.

**Was schon da war (nachgesehen, nicht angenommen):** Teil 1 lässt den Kegel an
der **Bodenebene** enden — `applyFloorAim` schneidet die Strahlrichtung mit
`y=0` und gibt den Abstand an `setBeamLength`. Das Backlog behauptete noch „er
endet NICHT an einer getroffenen Fläche (feste Länge)"; das stimmte zum
Zeitpunkt dieser Runde nicht mehr und ist dort richtiggestellt.

**Was fehlte:** alles zwischen Linse und Boden. Steht ein Podest, ein DJ-Pult,
ein Boxenstapel oder eine Traverse im Weg, schoss der sichtbare Kegel hindurch
und endete erst am Boden dahinter. Am Rig ist das der häufige Fall — Scheinwerfer
stehen über Bühnenelementen, nicht über leerem Boden.

**Warum die Entscheidung ein eigenes, importfreies Modul ist:** die
fehleranfällige Stelle ist nicht die Strahlenverfolgung (die macht three.js),
sondern die Frage, *welcher* Abstand gilt — und dabei die Unterscheidung
`Infinity` („nichts getroffen", Grundlänge behalten) von `0` („Länge null",
unsichtbarer Punkt). Genau diese Verwechslung lässt einen nach oben gerichteten
Kopf seinen Kegel verlieren. Dieselbe Bauart wie `optics.js`: ohne Importe
direkt prüfbar, ohne eine 3D-Szene hochzuziehen.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODUL = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src",
                      "fixtures", "beam_stop.js")


def _node_verfuegbar() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:                       # pragma: no cover
        return False


def _rechne(aufrufe: list) -> list:
    """Führt die JS-Funktionen mit gestellten Zahlen aus und gibt die Ergebnisse.

    Der Quelltext wird als ES-Modul in einen Temp-Ordner kopiert; `Infinity`
    überlebt JSON nicht, deshalb wandert es als `null` durch und wird beidseitig
    übersetzt.
    """
    import tempfile
    with open(_MODUL, encoding="utf-8") as fh:
        quelle = fh.read()
    treiber = """
import { naechsterAuftreffpunkt, auftreffFlaeche } from './beam_stop.mjs';
const auf = (v) => (v === null ? Infinity : v);
const ab  = (v) => (isFinite(v) ? v : null);
const ergebnis = AUFRUFE.map(a => {
  if (a.fn === 'naechster') {
    return ab(naechsterAuftreffpunkt(auf(a.boden), auf(a.objekt)));
  }
  const r = auftreffFlaeche(auf(a.boden), a.treffer);
  return { abstand: ab(r.abstand), y: r.y };
});
console.log(JSON.stringify(ergebnis));
"""
    with tempfile.TemporaryDirectory() as verz:
        with open(os.path.join(verz, "beam_stop.mjs"), "w", encoding="utf-8") as fh:
            fh.write(quelle)
        with open(os.path.join(verz, "treiber.mjs"), "w", encoding="utf-8") as fh:
            fh.write(treiber.replace("AUFRUFE", json.dumps(aufrufe)))
        p = subprocess.run(["node", os.path.join(verz, "treiber.mjs")],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:               # pragma: no cover
            raise AssertionError(p.stderr)
        return json.loads(p.stdout.strip())


@unittest.skipUnless(_node_verfuegbar(), "node fehlt")
class BeamStopTest(unittest.TestCase):

    def test_der_naehere_treffer_gewinnt(self):
        """Der Kern: steht ein Podest über dem Boden, endet der Strahl dort."""
        self.assertEqual(_rechne([{"fn": "naechster", "boden": 6.0,
                                   "objekt": 2.5}]), [2.5])

    def test_ohne_koerper_bleibt_der_boden(self):
        self.assertEqual(_rechne([{"fn": "naechster", "boden": 6.0,
                                   "objekt": None}]), [6.0])

    def test_ein_koerper_HINTER_dem_boden_zaehlt_nicht(self):
        """Gegenprobe: sonst würde ein Objekt unter der Bühne den Strahl
        verlängern statt ihn zu stoppen."""
        self.assertEqual(_rechne([{"fn": "naechster", "boden": 3.0,
                                   "objekt": 9.0}]), [3.0])

    def test_kein_treffer_heisst_unendlich_und_nicht_null(self):
        """★ Die eigentliche Falle. `Infinity` bedeutet „behalte die
        Grundlänge"; würde daraus eine 0, verlöre ein nach oben gerichteter
        Kopf seinen Kegel vollständig."""
        self.assertEqual(_rechne([{"fn": "naechster", "boden": None,
                                   "objekt": None}]), [None])

    def test_unbrauchbare_werte_gelten_als_kein_treffer(self):
        """Ein einzelnes NaN oder ein negativer Abstand (Treffer HINTER der
        Linse) darf den Kegel nicht verschwinden lassen."""
        self.assertEqual(
            _rechne([{"fn": "naechster", "boden": -2.0, "objekt": None},
                     {"fn": "naechster", "boden": 0.0, "objekt": 4.0}]),
            [None, 4.0])

    # ── Der Lichtfleck gehört auf die getroffene Fläche ──────────────────────

    def test_fleck_liegt_auf_dem_koerper_nicht_auf_dem_boden(self):
        """Ein Podest bekommt den Fleck auf seine Oberkante. Läge er weiter auf
        dem Boden, zeigte die Ansicht Licht an einer Stelle, die in Wahrheit im
        Schatten des Podests liegt."""
        self.assertEqual(
            _rechne([{"fn": "flaeche", "boden": 6.0,
                      "treffer": {"abstand": 2.5, "y": 1.2}}]),
            [{"abstand": 2.5, "y": 1.2}])

    def test_ohne_koerper_liegt_der_fleck_am_boden(self):
        self.assertEqual(
            _rechne([{"fn": "flaeche", "boden": 6.0, "treffer": None}]),
            [{"abstand": 6.0, "y": 0}])

    def test_treffer_hinter_dem_boden_verschiebt_den_fleck_nicht(self):
        self.assertEqual(
            _rechne([{"fn": "flaeche", "boden": 3.0,
                      "treffer": {"abstand": 9.0, "y": 4.0}}]),
            [{"abstand": 3.0, "y": 0}])

    def test_treffer_ohne_brauchbare_hoehe_faellt_auf_null_zurueck(self):
        """Lieber der Boden als eine erfundene Höhe — ein Fleck auf `NaN` wäre
        gar nicht sichtbar."""
        self.assertEqual(
            _rechne([{"fn": "flaeche", "boden": 6.0,
                      "treffer": {"abstand": 2.0, "y": None}}]),
            [{"abstand": 2.0, "y": 0}])


class VerdrahtungTest(unittest.TestCase):
    """Die Rechnung nützt nichts, wenn der Aufrufer sie nicht benutzt.

    Geprüft am Quelltext statt in der Szene: eine 3D-Szene hochzuziehen kostet
    einen WebGL-Kontext, und das ist auf diesem Rechner ein knappes Gut
    (XPLAT-17). Für „ist es überhaupt verdrahtet?" reicht der Quelltext.
    """

    def setUp(self):
        with open(os.path.join(_REPO, "src", "ui", "visualizer", "scene_src",
                               "fixtures", "builders.js"), encoding="utf-8") as fh:
            self.quelle = fh.read()

    def test_die_koerperpruefung_wird_aufgerufen(self):
        self.assertIn("auftreffFlaeche(", self.quelle)
        self.assertIn("koerperTreffer(f, origin, dir)", self.quelle)

    def test_der_raycaster_wird_gehalten_statt_pro_frame_gebaut(self):
        """Ein `new THREE.Raycaster()` pro Fixture und Frame wäre bei 44 Hz
        und 30 Geräten reine Allokationslast — dieselbe Regel wie beim
        Andocken."""
        self.assertIn("const _strahl = new THREE.Raycaster()", self.quelle)
        rechnen = re.search(r"function _koerperTrefferRechnen\([^)]*\)\s*\{.*?\n\}",
                            self.quelle, re.S)
        self.assertIsNotNone(rechnen)
        self.assertNotIn("new THREE.Raycaster()", rechnen.group(0))

    def test_leere_buehne_kostet_keinen_strahl(self):
        """Der häufigste Fall ist „keine Bühnenobjekte". Er muss abbiegen,
        BEVOR überhaupt gerechnet wird."""
        wahl = re.search(r"function koerperTreffer\([^)]*\)\s*\{.*?\n\}",
                         self.quelle, re.S).group(0)
        frueh = wahl.index("if (anzahl === 0)")
        rechnen = wahl.index("_koerperTrefferRechnen(")
        self.assertLess(frueh, rechnen,
                        "die leere Bühne biegt erst nach der Rechnung ab")

    def test_kein_strahl_solange_sich_nichts_bewegt(self):
        """★ Die Zusage, die `test_viz_beam_laenge.py` seit VIZ-15 festhält:
        **kein Raycast je Fixture und Frame.** DMX-Batches kommen mit 44 Hz,
        auch wenn nichts fährt.

        Aufgelöst nicht durch Verzicht auf die Prüfung, sondern durch einen
        Änderungs-Schlüssel: Strahl (Ursprung + Richtung) und Bühne (Anzahl,
        Lage, Größe). Bleibt er gleich, wird das letzte Ergebnis
        wiederverwendet — ein fahrender Moving Head zahlt die Strahlenverfolgung
        nur, *während* er fährt.
        """
        wahl = re.search(r"function koerperTreffer\([^)]*\)\s*\{.*?\n\}",
                         self.quelle, re.S).group(0)
        self.assertIn("f._koerperSchluessel === schluessel", wahl,
                      "kein Änderungs-Schlüssel — es würde jeden Frame gerechnet")
        treffer = wahl.index("f._koerperSchluessel === schluessel")
        rechnen = wahl.index("_koerperTrefferRechnen(")
        self.assertLess(treffer, rechnen,
                        "der Schlüssel wird erst NACH der Rechnung geprüft")
        # Der Schlüssel muss beide Seiten enthalten: Strahl UND Bühne.
        for teil in ("origin.x", "dir.y", "signatur", "anzahl"):
            self.assertIn(teil, wahl, f"Schlüssel ignoriert {teil}")

    def test_fixtures_selbst_sind_keine_hindernisse(self):
        """Sonst schnitte ein Kegel, der knapp am Gehäuse eines anderen
        Scheinwerfers vorbeigeht, reihenweise ab."""
        koerper = re.search(r"function koerperTreffer\([^)]*\)\s*\{.*?\n\}",
                            self.quelle, re.S).group(0)
        self.assertIn("stageObjects", koerper)
        self.assertNotIn("fixtureMeshes", koerper)


if __name__ == "__main__":
    unittest.main()
