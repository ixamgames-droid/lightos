"""VIZ-71 (S6): dynamische Aufloesung bei Kamerabewegung — der Zustandsautomat.

``scene/dynamic_resolution.js`` ist rein (Uhr, Zeitgeber und Wirkungen werden
hereingereicht). Dieser Test faehrt ihn unter Node mit einer Fake-Uhr — ohne
GPU, ohne WebEngine, ohne Warten. Die Verdrahtung in der echten Seite (eine
Quelle fuer die Pixeldichte, Deckel je Stufe) prueft
``test_viz71_qualitaetsstufen.py``.

Regeln laut Entwurf + Qualitaetsstufen:
  * ein einzelnes Update (Preset/Reset-Sprung) senkt nicht ab, eine Serie schon;
  * 200 ms Ruhe -> volle Aufloesung PLUS ``requestRender`` (scharfes Endbild);
  * ``always`` (Niedrig) immer, ``slow`` (Hoch) nur bei Frames > 18 ms (mit
    Hysterese), ``never`` (Maximal) nie.
"""
import json
import os
import subprocess
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODUL = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src",
                      "scene", "dynamic_resolution.js")


def _node_verfuegbar() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:                       # pragma: no cover
        return False


_TREIBER = """
import { createDynamicResolution } from './dyn.mjs';
const SCHRITTE = %s;
const MODUS = %s;
let t = 0;
const timer = [];          // {at, fn, id}
let naechsteId = 1;
const log = [];
let renders = 0;
const d = createDynamicResolution({
  now: () => t,
  setTimer: (fn, ms) => { const id = naechsteId++; timer.push({at: t + ms, fn, id}); return id; },
  clearTimer: (id) => { const i = timer.findIndex(x => x.id === id); if (i >= 0) timer.splice(i, 1); },
  applyScale: (s) => log.push(s),
  requestRender: () => { renders += 1; },
  mode: MODUS,
});
function vor(ms) {
  const ziel = t + ms;
  for (;;) {
    timer.sort((a, b) => a.at - b.at);
    if (!timer.length || timer[0].at > ziel) break;
    const x = timer.shift(); t = x.at; x.fn();
  }
  t = ziel;
}
const aus = [];
for (const s of SCHRITTE) {
  if (s[0] === 'kamera') d.noteCameraMotion();
  else if (s[0] === 'warte') vor(s[1]);
  else if (s[0] === 'frame') d.noteFrameInterval(s[1]);
  else if (s[0] === 'modus') d.setMode(s[1]);
  else if (s[0] === 'messen') aus.push({scale: d.scale(), renders, wechsel: log.slice()});
}
console.log(JSON.stringify(aus));
"""


def _fahre(schritte, modus="always"):
    with open(_MODUL, encoding="utf-8") as fh:
        quelle = fh.read()
    with tempfile.TemporaryDirectory() as verz:
        with open(os.path.join(verz, "dyn.mjs"), "w", encoding="utf-8") as fh:
            fh.write(quelle)
        with open(os.path.join(verz, "treiber.mjs"), "w", encoding="utf-8") as fh:
            fh.write(_TREIBER % (json.dumps(schritte), json.dumps(modus)))
        p = subprocess.run(["node", os.path.join(verz, "treiber.mjs")],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:               # pragma: no cover
            raise AssertionError(p.stderr)
        return json.loads(p.stdout.strip())


def _serie(n=5, abstand=16):
    out = []
    for _ in range(n):
        out += [["kamera"], ["warte", abstand]]
    return out


@unittest.skipUnless(_node_verfuegbar(), "node fehlt")
class DynamischeAufloesungTest(unittest.TestCase):
    def test_einzelnes_update_senkt_nicht_ab(self):
        (m,) = _fahre([["kamera"], ["warte", 300], ["messen"]])
        self.assertEqual(m["scale"], 1)
        self.assertEqual(m["wechsel"], [])

    def test_reset_sprung_im_selben_task_senkt_nicht_ab(self):
        # resetCameraView ruft updateCamera UND resizeOrtho im selben Task.
        (m,) = _fahre([["kamera"], ["kamera"], ["warte", 2], ["kamera"], ["messen"]])
        self.assertEqual(m["scale"], 1)

    def test_serie_senkt_ab_ruhe_stellt_scharf(self):
        a, b, c = _fahre(_serie() + [["messen"], ["warte", 150], ["messen"],
                                     ["warte", 60], ["messen"]])
        self.assertLess(a["scale"], 1, "Kamerafahrt muss absenken")
        self.assertGreaterEqual(a["scale"], 0.6)
        self.assertLessEqual(a["scale"], 0.75)
        self.assertLess(b["scale"], 1, "nach 150 ms noch keine Ruhe")
        self.assertEqual(c["scale"], 1, "nach 200 ms Ruhe wieder voll")
        self.assertGreater(c["renders"], b["renders"],
                           "ohne requestRender bliebe das Standbild unscharf")

    def test_keine_wechsel_in_jedem_frame(self):
        (m,) = _fahre(_serie(n=40) + [["messen"]])
        self.assertEqual(len(m["wechsel"]), 1, "genau eine Absenkung, kein Flackern")

    def test_weiterfahren_haelt_die_absenkung(self):
        a, b = _fahre(_serie() + [["warte", 150]] + _serie() + [["messen"],
                                                               ["warte", 250], ["messen"]])
        self.assertLess(a["scale"], 1)
        self.assertEqual(b["scale"], 1)
        self.assertEqual(b["wechsel"], [a["wechsel"][0], 1])

    def test_hoch_nur_bei_langsamen_frames(self):
        schnell = [["frame", 10]] * 10
        (m,) = _fahre(schnell + _serie() + [["messen"]], modus="slow")
        self.assertEqual(m["scale"], 1, "schnelle GPU: Hoch senkt nicht ab")
        langsam = [["frame", 26]] * 10
        (m,) = _fahre(langsam + _serie() + [["messen"]], modus="slow")
        self.assertLess(m["scale"], 1, "Frames > 18 ms: Hoch senkt ab")

    def test_hoch_hysterese(self):
        # erst langsam, dann 16 ms (zwischen 14 und 18) -> bleibt "langsam"
        schritte = [["frame", 26]] * 10 + [["frame", 16]] * 20 + _serie() + [["messen"]]
        (m,) = _fahre(schritte, modus="slow")
        self.assertLess(m["scale"], 1)
        schritte = [["frame", 26]] * 10 + [["frame", 10]] * 20 + _serie() + [["messen"]]
        (m,) = _fahre(schritte, modus="slow")
        self.assertEqual(m["scale"], 1, "unter 14 ms gilt die GPU wieder als schnell")

    def test_maximal_senkt_nie_ab(self):
        (m,) = _fahre([["frame", 40]] * 10 + _serie(n=20) + [["messen"]], modus="never")
        self.assertEqual(m["scale"], 1)
        self.assertEqual(m["wechsel"], [])


if __name__ == "__main__":
    unittest.main()
