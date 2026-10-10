"""VIZ-92 (3/4): Pan, Tilt und Gobo-Drehung zwischen zwei DMX-Updates glaetten.

Befund (Gobo-Demo, Stufe Hoch, generischer MH16): rotierende Gobos ruckelten,
und beim Schwenken hing der Gobo-Fleck stufenweise hinter dem Kopf her. Die
Lichtdaten kommen mit 15/30/44 Hz (Push-Takt der Stufe), gerendert wird im
Bildschirmtakt — zwischen zwei Updates stand alles still und sprang dann.

``scene_src/fixtures/bewegung_glatt.js`` ist rein (Zeit wird hereingereicht);
dieser Test faehrt es unter Node mit einer Fake-Uhr und MISST den angezeigten
Winkel je Renderbild:

* ein gleichmaessiger Fade (30 Hz Updates, 60 Hz Bilder) ergibt gleich grosse
  Schritte je Bild — ohne Glaettung waere jedes zweite Bild ein Stillstand;
* der Gobo-Winkel laeuft ueber 0/2*pi auf dem kurzen Weg (kein Rueckwaerts-
  Umlauf beim Wraparound 255 -> 0);
* ein einzelner Sprung (Preset/Cue, grosser Schritt oder nach einer Pause)
  bleibt ein Sprung — das naechste Bild steht sofort am Ziel;
* das Ende einer Bewegung liegt exakt auf dem Ziel (kein Rundungsrest).

Die Verdrahtung in der echten Seite (Kegel, Bodenmuster und Pool-Ziel folgen
dem angezeigten Kopf je Bild) prueft ``test_viz92_gobo_feinschliff_scene.py``.
"""
import json
import math
import os
import subprocess
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODUL = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src",
                      "fixtures", "bewegung_glatt.js")


def _node_verfuegbar() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:                       # pragma: no cover
        return False


# Schritte: ['ziel', t_ms, wert] meldet ein neues Ziel, ['bild', t_ms] liest
# den angezeigten Wert.
_TREIBER = """
import { glattKanal, glattZiel, glattWert, kreisDelta, SPRUNG_RAD, GLATT_MAX_MS } from './glatt.mjs';
const SCHRITTE = %s;
const k = glattKanal(%s);
const aus = [];
for (const s of SCHRITTE) {
  if (s[0] === 'ziel') glattZiel(k, s[2], s[1]);
  else aus.push(glattWert(k, s[1]));
}
console.log(JSON.stringify({werte: aus, sprung: SPRUNG_RAD, maxMs: GLATT_MAX_MS}));
"""


def _fahre(schritte, kreis=False):
    with open(_MODUL, encoding="utf-8") as fh:
        quelle = fh.read()
    with tempfile.TemporaryDirectory() as verz:
        with open(os.path.join(verz, "glatt.mjs"), "w", encoding="utf-8") as fh:
            fh.write(quelle)
        with open(os.path.join(verz, "treiber.mjs"), "w", encoding="utf-8") as fh:
            fh.write(_TREIBER % (json.dumps(schritte), "true" if kreis else "false"))
        out = subprocess.run(["node", os.path.join(verz, "treiber.mjs")],
                             capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


def _fade(start, schritt, n, update_ms=1000 / 30, bild_ms=1000 / 60):
    """n Updates im Abstand update_ms, dazwischen Bilder im Abstand bild_ms."""
    schritte = []
    t_ende = n * update_ms
    ereignisse = [(i * update_ms, 0, start + i * schritt) for i in range(n + 1)]
    t = bild_ms / 2
    while t < t_ende:
        ereignisse.append((t, 1, None))
        t += bild_ms
    for t, art, wert in sorted(ereignisse, key=lambda e: (e[0], e[1])):
        schritte.append(["ziel", t, wert] if art == 0 else ["bild", t])
    return schritte


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class GlaettungTest(unittest.TestCase):
    def test_gobo_fade_gleichmaessig_je_bild(self):
        # Gobo-Drehung 1 DMX-Schritt (1,41 Grad) je 30-Hz-Update.
        dmx = 2 * math.pi / 255
        r = _fahre(_fade(0.0, dmx, 40), kreis=True)
        w = r["werte"][4:]                   # Anlauf (erstes Stueck) abziehen
        schritte = [b - a for a, b in zip(w, w[1:])]
        self.assertGreater(len(schritte), 40)
        # Jedes Bild bewegt sich, und zwar gleich weit: halber DMX-Schritt.
        self.assertGreater(min(schritte), 0.4 * dmx, schritte)
        self.assertLess(max(schritte), 0.6 * dmx, schritte)

    def test_pan_fade_gleichmaessig(self):
        r = _fahre(_fade(0.0, 0.05, 30))
        w = r["werte"][4:]
        schritte = [b - a for a, b in zip(w, w[1:])]
        self.assertLess(max(schritte) - min(schritte), 0.2 * 0.025, schritte)

    def test_ohne_glaettung_waere_jedes_zweite_bild_stillstand(self):
        # Gegenprobe zum Messverfahren: mit Spruengen (Schritt > SPRUNG_RAD)
        # zeigt jedes zweite Bild denselben Wert wie das vorige.
        r = _fahre(_fade(0.0, 0.5, 10))
        w = r["werte"]
        stand = sum(1 for a, b in zip(w, w[1:]) if abs(b - a) < 1e-12)
        self.assertGreaterEqual(stand, len(w) // 2 - 1)

    def test_wraparound_kurzer_weg(self):
        dmx = 2 * math.pi / 255
        # 250 -> 254 -> 0 (= 2*pi) -> 4: Ziele als Winkel 0..2*pi.
        werte = [((250 + i) % 255) * dmx for i in range(0, 12, 2)]
        schritte = []
        for i, v in enumerate(werte):
            schritte.append(["ziel", i * 33.3, v])
            schritte.append(["bild", i * 33.3 + 16.6])
        r = _fahre(schritte, kreis=True)
        w = r["werte"]
        for a, b in zip(w, w[1:]):
            d = (b - a + math.pi) % (2 * math.pi) - math.pi
            self.assertGreater(d, 0, f"laeuft rueckwaerts: {w}")
            self.assertLess(d, 4 * dmx, f"Umlauf statt kurzer Weg: {w}")

    def test_einzelner_sprung_bleibt_sprung(self):
        # Grosser Schritt im Takt (Cue-Sprung): sofort am Ziel.
        r = _fahre([["ziel", 0, 0.0], ["ziel", 33, 1.5], ["bild", 34]])
        self.assertEqual(r["werte"], [1.5])
        # Kleiner Schritt nach einer Pause (> GLATT_MAX_MS): ebenfalls Sprung.
        r = _fahre([["ziel", 0, 0.0], ["ziel", 2000, 0.1], ["bild", 2001]])
        self.assertEqual(r["werte"], [0.1])
        # Zwei Ziele im selben Moment (ein Batch): kein Stueck.
        r = _fahre([["ziel", 0, 0.0], ["ziel", 1, 0.1], ["bild", 2]])
        self.assertEqual(r["werte"], [0.1])

    def test_ende_exakt_auf_dem_ziel(self):
        r = _fahre([["ziel", 0, 0.0], ["ziel", 33, 0.1], ["bild", 50],
                    ["bild", 66], ["bild", 500]])
        self.assertGreater(r["werte"][0], 0.0)
        self.assertLess(r["werte"][0], 0.1)
        self.assertEqual(r["werte"][-1], 0.1)



# Codex #965: Bild-Deckel unter laufenden DMX-Updates. rAF im Takt `bild_ms`,
# Updates (neues Ziel fuer Geraet 'a') im Takt `update_ms`, eine Sekunde lang.
_DECKEL_TREIBER = """
import { glattDeckel } from './glatt.mjs';
const [bildMs, updateMs, dauer, deckelMs] = %s;
const d = glattDeckel(deckelMs);
let voll = 0, extra = 0, verpasst = 0;
let naechstesUpdate = 0, offen = false;
for (let t = 0; t < dauer; t += bildMs) {
  while (naechstesUpdate <= t) { d.neuesZiel('a'); offen = true; naechstesUpdate += updateMs; }
  const s = d.tick(t);
  const traf = !!s && (s.alle || s.neu.includes('a'));
  if (offen && !traf) verpasst += 1;
  if (traf) offen = false;
  if (s && s.alle) voll += 1; else if (s) extra += 1;
}
console.log(JSON.stringify({voll, extra, verpasst}));
"""


def _deckel(bild_ms, update_ms, dauer=1000.0, deckel_ms=1000 / 60 - 2):
    with open(_MODUL, encoding="utf-8") as fh:
        quelle = fh.read()
    with tempfile.TemporaryDirectory() as verz:
        with open(os.path.join(verz, "glatt.mjs"), "w", encoding="utf-8") as fh:
            fh.write(quelle)
        with open(os.path.join(verz, "treiber.mjs"), "w", encoding="utf-8") as fh:
            fh.write(_DECKEL_TREIBER % json.dumps([bild_ms, update_ms, dauer, deckel_ms]))
        out = subprocess.run(["node", os.path.join(verz, "treiber.mjs")],
                             capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class DeckelUnterLaufendenUpdatesTest(unittest.TestCase):
    def test_44hz_updates_auf_240hz_schirm_halten_den_deckel(self):
        r = _deckel(1000 / 240, 1000 / 44)
        # Volle Glaett-Schritte (alle Geraete) hoechstens 60 je Sekunde —
        # vorher setzte jedes Update den Deckel zurueck (~88 je Sekunde).
        self.assertLessEqual(r["voll"], 61, r)
        self.assertGreaterEqual(r["voll"], 50, r)

    def test_erstes_bild_nach_jedem_update_zeigt_den_zwischenstand(self):
        for bild_ms in (1000 / 240, 1000 / 144, 1000 / 60):
            r = _deckel(bild_ms, 1000 / 44)
            self.assertEqual(r["verpasst"], 0, (bild_ms, r))

    def test_ohne_updates_nur_der_deckeltakt(self):
        r = _deckel(1000 / 240, 10 ** 9)
        self.assertLessEqual(r["voll"], 61, r)
        self.assertLessEqual(r["extra"], 1, r)


if __name__ == "__main__":
    unittest.main()
