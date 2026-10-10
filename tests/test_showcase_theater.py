"""DEMO-07: Showcase „Theater/Event" (``tools/build_showcase_theater.py``).

Der Generator baut im Unterprozess in ein tmp-Verzeichnis (Datenpfade der
Test-Umgebung, s. ``conftest.py``). Geprueft wird:

* die Show baut und ``lint_show.py --strict`` ist sauber,
* die Cue-Liste „Abendablauf" hat den Abend in der richtigen Reihenfolge,
  weiche Fades, Follow-Cues (2, 5, 8) und eine Wartezeit (6),
* die Spots zielen wirklich: aus Pan/Tilt der Cues zurueckgerechnet trifft der
  Strahl den Zielpunkt (Rednerpult, Podest, Buehnenmitte) auf 0,5 m genau —
  unabhaengig von der Rechnung des Generators, ueber das Strahlmodell des
  3D-Visualizers,
* beim Szenenwechsel fahren die Spots erst im Dunkeln (Pan/Tilt verzoegert),
* das Playback wirkt: GO auf „Rede-Spot" fadet die Spots auf voll, der
  Follow-Timer von „Saal dunkel" wird gestellt.
* Bewegungen gibt es hier keine (kein EFX) — die Show ist bewusst ruhig.
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_showcase_theater.py")

_TREIBER = r'''
import contextlib, io, json, os, sys, time
repo, pfad = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo); sys.path.insert(0, os.path.join(repo, "tools"))
import _gen_env  # noqa
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])
from src.core.show.show_file import load_show
from src.core.app_state import get_state, get_channels_for_patched
from src.core.stage.einmessen import aim_kw
with contextlib.redirect_stdout(io.StringIO()):
    ok, msg = load_show(pfad)
assert ok, msg
st = get_state()
fx = {f.fid: f for f in st.get_patched_fixtures()}
def dmx(fid, attr):
    f = fx[fid]
    chs = sorted(get_channels_for_patched(f), key=lambda c: c.channel_number)
    ch = [f.address + c.channel_number - 1 for c in chs if c.attribute == attr][0]
    return int(st.universes.get(f.universe).get_channel(ch))
spots = [f for f in fx if fx[f].label.startswith("Spot")]
erg = {"kw": {f: aim_kw(fx[f]) for f in spots},
       "pos": {f: list(st.visualizer_positions.get(f) or st.visualizer_positions.get(str(f)))
               for f in spots}}
stack = st.playback_engine.get_executor(1, page=0).stack
stack.go_to(4.0)
stack._fade.start_time -= 100.0          # Fade ueberspringen (Wanduhr)
for _ in range(4):
    st._render_frame(1 / 44.0)
erg["rede_spots"] = [dmx(f, "intensity") for f in spots]
stack.go_to(2.0)
erg["follow_gestellt"] = stack._follow_timer is not None
stack._cancel_follow()
print("ERG=" + json.dumps(erg))
'''

#: Zielpunkte wie im Generator (Kopfhoehe am Ort).
PUNKTE = {"Rednerpult": (-3.6, 2.55, -1.9), "Bühnenmitte": (0.0, 2.6, -2.5),
          "Podest": (1.5, 3.2, -4.9)}


def _lies_show(pfad):
    with zipfile.ZipFile(pfad) as z:
        return json.loads(z.read("show.json"))


def _abstand_strahl(pos, pan, tilt, kw, punkt):
    """Abstand des Punkts vom Strahl, den Pan/Tilt ergeben (Modell des
    3D-Visualizers: Ruhelage senkrecht nach unten, haengend ohne Drehung)."""
    half_p = kw.get("pan_range_deg", 360.0) / 2.0
    half_t = kw.get("tilt_range_deg", 180.0) / 2.0
    p = math.radians((pan - kw.get("pan_zero_dmx", 128.0)) / 128.0 * half_p)
    t = math.radians((tilt - kw.get("tilt_zero_dmx", 128.0)) / 128.0 * half_t)
    d = (-math.sin(t) * math.sin(p), -math.cos(t), -math.sin(t) * math.cos(p))
    v = [punkt[i] - pos[i] for i in range(3)]
    s = sum(v[i] * d[i] for i in range(3))
    if s <= 0:
        return 99.0
    q = [v[i] - s * d[i] for i in range(3)]
    return math.sqrt(sum(x * x for x in q))


class ShowcaseTheaterTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="lightos_demo07_theater_")
        cls.pfad = os.path.join(cls._tmp.name, "theater.lshow")
        cls.env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
        lauf = subprocess.run([sys.executable, GENERATOR, "--out", cls.pfad], cwd=REPO,
                              env=cls.env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=900)
        cls.rc, cls.ausgabe = lauf.returncode, lauf.stdout + lauf.stderr
        cls.show = _lies_show(cls.pfad) if os.path.isfile(cls.pfad) else None
        cls.erg = None
        if cls.show is not None:
            lauf = subprocess.run([sys.executable, "-c", _TREIBER, REPO, cls.pfad], cwd=REPO,
                                  env=cls.env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=600)
            zeile = [z for z in lauf.stdout.splitlines() if z.startswith("ERG=")]
            cls.erg = json.loads(zeile[0][4:]) if zeile else None
            cls.treiber_ausgabe = lauf.stdout[-2000:] + lauf.stderr[-3000:]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _bereit(self):
        self.assertEqual(self.rc, 0, self.ausgabe[-3000:])
        self.assertIsNotNone(self.show)

    def _cues(self):
        stack = [s for s in self.show["cue_stacks"] if s["name"] == "Abendablauf"][0]
        return stack["cues"]

    def test_lint_strict_sauber(self):
        self._bereit()
        lauf = subprocess.run([sys.executable, os.path.join(REPO, "tools", "lint_show.py"),
                               "--strict", self.pfad], cwd=REPO, env=self.env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=600)
        self.assertEqual(lauf.returncode, 0, lauf.stdout[-3000:] + lauf.stderr[-2000:])
        self.assertIn("0 Fehler, 0 Warnungen", lauf.stdout)

    def test_abendablauf_mit_follow_und_wartezeit(self):
        self._bereit()
        cues = self._cues()
        self.assertEqual([c["label"] for c in cues],
                         ["Einlass", "Saal dunkel", "Begrüßung", "Rede-Spot", "Szenenwechsel",
                          "Szene am Podest", "Applaus", "Ende", "Auslass"])
        folgen = {c["label"]: c.get("follow") for c in cues if c.get("follow") is not None}
        self.assertEqual(folgen, {"Saal dunkel": 2.0, "Szenenwechsel": 3.0, "Ende": 3.0})
        self.assertGreater([c for c in cues if c["label"] == "Szene am Podest"][0]["delay_in"], 0)
        self.assertTrue(all(c["fade_in"] >= 1.5 for c in cues), "weiche Fades")
        ex = self.show["executors"]
        self.assertEqual(ex["page_names"][0], "Abend")
        self.assertEqual(ex["pages"][0][0]["slot"], 1)

    def test_spots_fahren_im_dunkeln(self):
        self._bereit()
        wechsel = [c for c in self._cues() if c["label"] == "Szenenwechsel"][0]
        verz = wechsel["attr_delays"]
        self.assertEqual(len(verz), 2)
        for fid, d in verz.items():
            self.assertGreaterEqual(d["pan"], wechsel["fade_in"])
            self.assertEqual(wechsel["values"][fid]["intensity"], 0)

    def test_spots_treffen_ihre_ziele(self):
        self._bereit()
        self.assertIsNotNone(self.erg, getattr(self, "treiber_ausgabe", ""))
        ort_je_cue = {"Begrüßung": "Rednerpult", "Rede-Spot": "Rednerpult",
                      "Szene am Podest": "Podest", "Applaus": "Bühnenmitte"}
        geprueft = 0
        for c in self._cues():
            ort = ort_je_cue.get(c["label"])
            if not ort:
                continue
            for fid, kw in self.erg["kw"].items():
                v = c["values"][fid]
                if v["intensity"] == 0:
                    continue
                a = _abstand_strahl(self.erg["pos"][fid], v["pan"], v["tilt"], kw, PUNKTE[ort])
                self.assertLess(a, 0.5, f"{c['label']}: Spot {fid} verfehlt {ort} um {a:.2f} m")
                geprueft += 1
        self.assertGreaterEqual(geprueft, 6)
        paletten = {p["name"] for p in self.show["palettes"]["palettes"]}
        self.assertTrue({"Spot Rednerpult", "Spot Bühnenmitte", "Spot Podest"} <= paletten)

    def test_playback_wirkt_im_render(self):
        self._bereit()
        self.assertIsNotNone(self.erg, getattr(self, "treiber_ausgabe", ""))
        self.assertEqual(self.erg["rede_spots"], [255, 255])
        self.assertTrue(self.erg["follow_gestellt"])

    def test_keine_bewegungseffekte(self):
        self._bereit()
        efx = [f for liste in self.show["functions"].values() for f in liste
               if f.get("type") == "EFX"]
        self.assertEqual(efx, [])


if __name__ == "__main__":
    unittest.main()
