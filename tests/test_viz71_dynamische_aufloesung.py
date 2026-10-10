"""VIZ-71 (S6): dynamische Aufloesung bei Kamerabewegung — der Zustandsautomat.

``scene/dynamic_resolution.js`` ist rein (Uhr, Zeitgeber und Wirkungen werden
hereingereicht). Dieser Test faehrt ihn unter Node mit einer Fake-Uhr — ohne
GPU, ohne WebEngine, ohne Warten. Die Verdrahtung in der echten Seite (eine
Quelle fuer die Pixeldichte, Deckel je Stufe) prueft
``test_viz71_qualitaetsstufen.py``.

Regeln laut Entwurf + Qualitaetsstufen:
  * ein einzelnes Update (Preset/Reset-Sprung) senkt nicht ab, eine Serie schon;
  * 200 ms Ruhe -> volle Aufloesung PLUS ``requestRender`` (scharfes Endbild);
  * ``always`` (Niedrig) immer, ``slow`` (Hoch) nur, wenn regelmaessig Frames
    gegen den Bildschirmtakt verpasst werden (mit Hysterese, verfaellt nach
    30 s), ``never`` (Maximal) nie.
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
  else if (s[0] === 'hz') d.setDisplayHz(s[1]);
  else if (s[0] === 'messen') aus.push({scale: d.scale(), renders, wechsel: log.slice()});
  else if (s[0] === 'info') aus.push(d.info());
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
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
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

    # Review B1: realistische Frame-Abstaende. rAF-Abstaende fallen bei Vsync
    # nie unter das Bildschirmintervall (60 Hz: 16,7 ms) — 10-ms-Frames, wie
    # sie der erste Entwurf dieses Tests fuetterte, gibt es nicht.
    def test_hoch_60hz_ein_ausreisser_bleibt_schnell(self):
        schritte = [["frame", 16.7]] * 10 + [["frame", 33.4]] + [["frame", 16.7]] * 10
        (m,) = _fahre(schritte + _serie() + [["messen"]], modus="slow")
        self.assertEqual(m["scale"], 1, "ein verpasster Frame macht keine langsame GPU")

    def test_hoch_60hz_ausreisser_als_erster_messwert(self):
        schritte = [["frame", 25]] + [["frame", 16.7]] * 50
        (m,) = _fahre(schritte + _serie() + [["messen"]], modus="slow")
        self.assertEqual(m["scale"], 1, "der erste Messwert darf nicht ungedaempft zaehlen")

    def test_hoch_50hz_und_fernzugriff_sind_nicht_langsam(self):
        for ms in (20, 33.3):
            (m,) = _fahre([["frame", ms]] * 30 + _serie() + [["messen"]], modus="slow")
            self.assertEqual(m["scale"], 1, f"gleichmaessige {ms}-ms-Frames sind Bildschirmtakt")

    def test_hoch_regelmaessig_verpasste_frames_senken_ab(self):
        schritte = [["frame", 16.7], ["frame", 33.4]] * 15
        (m,) = _fahre(schritte + _serie() + [["messen"]], modus="slow")
        self.assertLess(m["scale"], 1, "jeder zweite Frame verpasst: Hoch senkt ab")

    def test_hoch_60hz_erholt_sich_wieder(self):
        schritte = ([["frame", 16.7], ["frame", 33.4]] * 15
                    + [["frame", 16.7]] * 30)
        (m,) = _fahre(schritte + _serie() + [["messen"]], modus="slow")
        self.assertEqual(m["scale"], 1, "wieder ruhige 60 Hz: die GPU gilt als schnell")

    def test_hoch_langsam_verfaellt_ohne_bestaetigung(self):
        langsam = [["frame", 16.7], ["frame", 33.4]] * 15
        (m,) = _fahre(langsam + [["warte", 31000]] + _serie() + [["messen"]], modus="slow")
        self.assertEqual(m["scale"], 1, "nach 30 s ohne Messung: Probe mit voller Aufloesung")
        (m,) = _fahre(langsam + [["warte", 31000]] + langsam + _serie() + [["messen"]],
                      modus="slow")
        self.assertLess(m["scale"], 1, "Probe bestaetigt langsam: wieder absenken")

    # VIZ-85 (Testbericht Windows, 4K-Fernseher 29,97 Hz): das Minimum der
    # rAF-Abstaende fiel durch gelegentliche Doppel-rAF auf 8-17 ms, normale
    # 33-ms-Frames galten als verpasst, eine schnelle GPU wurde "langsam".
    def test_hoch_2997hz_mit_doppel_raf_bleibt_schnell(self):
        v = 1000 / 29.97
        schritte = []
        for i in range(200):
            if i % 9 == 4:                    # ~11 %: rAF zweimal je Vsync
                kurz = (8, 12.5, 17)[i % 3]
                schritte += [["frame", kurz], ["frame", v - kurz]]
            else:
                schritte.append(["frame", v + (0.6 if i % 2 else -0.6)])
        info, m = _fahre(schritte + [["info"]] + _serie() + [["messen"]], modus="slow")
        self.assertAlmostEqual(info["vsyncMs"], v, delta=1.5,
                               msg="Bildschirmintervall muss ~33,4 ms bleiben")
        self.assertFalse(info["slow"])
        self.assertLess(info["missed"], 0.1)
        self.assertEqual(m["scale"], 1, "GPU schafft jeden Vsync: nie absenken")

    # VIZ-85 Nachmessung D (Windows, RX 580, 29,97-Hz-Fernseher): rAF tickt
    # mit ~60 Hz, angezeigt wird mit 29,97 Hz — 16,7/16,7/33,4 gemischt sah wie
    # "jeder dritte verpasst" aus (missed 0,32-0,36, slow=true, Skala 0,65).
    @staticmethod
    def _raf60_auf_30hz():
        v60 = 1000 / 59.94
        return [["frame", v60 if i % 3 else 2 * v60] for i in range(240)]

    def test_hoch_2997hz_tv_mit_60hz_raf_bleibt_schnell(self):
        schritte = [["hz", 29.97]] + self._raf60_auf_30hz()
        info, m = _fahre(schritte + [["info"]] + _serie() + [["messen"]], modus="slow")
        self.assertFalse(info["slow"], "Bildschirm zeigt nur 29,97 Hz: nichts verpasst")
        self.assertGreater(info["vsyncMs"], 32.0)
        self.assertEqual(m["scale"], 1)

    def test_ohne_hz_bleibt_bisherige_schaetzung(self):
        (info,) = _fahre(self._raf60_auf_30hz() + [["info"]], modus="slow")
        self.assertTrue(info["slow"], "ohne echte Rate ist das Muster nicht unterscheidbar")
        self.assertEqual(info["displayMs"], 0)

    def test_ungueltige_hz_werden_ignoriert(self):
        for hz in (0, None, "x", 5, 1000):
            (info,) = _fahre([["hz", hz], ["info"]], modus="slow")
            self.assertEqual(info["displayMs"], 0, hz)

    def test_echte_langsamkeit_wird_mit_hz_weiter_erkannt(self):
        v = 1000 / 60
        schritte = [["hz", 60]] + [["frame", v if i % 3 else 3 * v] for i in range(240)]
        (info,) = _fahre(schritte + [["info"]], modus="slow")
        self.assertTrue(info["slow"])

    def test_hoch_doppel_raf_kurz_lang_reihenfolge_egal(self):
        v = 1000 / 29.97
        schritte = []
        for i in range(120):
            if i % 8 == 3:
                schritte += [["frame", v - 8], ["frame", 8]]   # erst lang, dann kurz
            else:
                schritte.append(["frame", v])
        (info,) = _fahre(schritte + [["info"]], modus="slow")
        self.assertFalse(info["slow"])
        self.assertAlmostEqual(info["vsyncMs"], v, delta=1.5)

    def test_hoch_jede_bildwiederholrate_mit_jitter_ist_schnell(self):
        for hz in (30, 50, 60, 144):
            v = 1000 / hz
            schritte = []
            for i in range(150):
                ms = v * (1 + 0.08 * ((i * 7) % 5 - 2) / 2)   # +-8 % Jitter
                if i % 13 == 6:
                    schritte += [["frame", v * 0.3], ["frame", ms - v * 0.3]]
                else:
                    schritte.append(["frame", ms])
            info, m = _fahre(schritte + [["info"]] + _serie() + [["messen"]], modus="slow")
            self.assertFalse(info["slow"], f"{hz} Hz")
            self.assertAlmostEqual(info["vsyncMs"], v, delta=v * 0.15, msg=f"{hz} Hz")
            self.assertEqual(m["scale"], 1, f"{hz} Hz")

    def test_hoch_144hz_wechselnde_last_wird_erkannt(self):
        v = 1000 / 144
        schritte = [["frame", v], ["frame", 2 * v], ["frame", v], ["frame", 2 * v],
                    ["frame", v]] * 20
        info, m = _fahre(schritte + [["info"]] + _serie() + [["messen"]], modus="slow")
        self.assertAlmostEqual(info["vsyncMs"], v, delta=0.5)
        self.assertTrue(info["slow"], "zwei von fuenf Frames verpasst")
        self.assertLess(m["scale"], 1)

    def test_hoch_monitorwechsel_60_auf_144hz(self):
        schritte = [["frame", 16.7]] * 60 + [["frame", 1000 / 144]] * 80
        info, m = _fahre(schritte + [["info"]] + _serie() + [["messen"]], modus="slow")
        self.assertAlmostEqual(info["vsyncMs"], 1000 / 144, delta=0.7)
        self.assertFalse(info["slow"])
        self.assertEqual(m["scale"], 1)

    def test_maximal_senkt_nie_ab(self):
        (m,) = _fahre([["frame", 40]] * 10 + _serie(n=20) + [["messen"]], modus="never")
        self.assertEqual(m["scale"], 1)
        self.assertEqual(m["wechsel"], [])


if __name__ == "__main__":
    unittest.main()
