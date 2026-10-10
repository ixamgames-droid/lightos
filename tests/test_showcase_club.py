"""DEMO-07: Showcase „Club-Nacht" (``tools/build_showcase_club.py``).

Der Generator baut im Unterprozess (Datenpfade zeigt die Test-Umgebung in
Wegwerf-Ordner, s. ``conftest.py``) und schreibt die Show in ein tmp-Verzeichnis.
Geprueft wird:

* die Show baut und ``lint_show.py --strict`` ist sauber (0 Fehler, 0 Warnungen),
* die Cue-Liste „Club-Nacht" hat die Looks Intro … Outro, „Drop-Puls" ist
  taktgebunden, beide liegen auf Executor-Seite 1 und in der VC (GO/BACK-Liste,
  Playback-Fader),
* Bewegungen sind ruhig: jede Bewegung am Tempo-Bus faehrt hoechstens 0,75
  Figuren je Sekunde (auch bei 175 BPM), Spider 1/4 bis 1/2 des MH-Faktors,
  Dials bieten nur diese Stufen,
* das Playback wirkt: nach GO auf „Drop" stehen Front-PARs rot auf voll und
  die Moving Heads offen auf weiss; „Drop-Puls" ueberstimmt die Front im Takt,
* Farbe und Dimmer sind getrennt (Spider-Farbszenen schreiben nur Farbe).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_showcase_club.py")
SEED_BPM = 126.0
SCHNELL_BPM = 175.0
MAX_HZ = 0.75

_TREIBER = r'''
import contextlib, io, json, os, sys
repo, pfad = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo); sys.path.insert(0, os.path.join(repo, "tools"))
import _gen_env  # noqa
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])
from src.core.show.show_file import load_show
from src.core.app_state import get_state, get_channels_for_patched
from src.core.engine.function_manager import get_function_manager
with contextlib.redirect_stdout(io.StringIO()):
    ok, msg = load_show(pfad)
assert ok, msg
st = get_state(); fm = get_function_manager()
fx = {f.fid: f for f in st.get_patched_fixtures()}
def kanal(fid, attr):
    f = fx[fid]
    chs = sorted(get_channels_for_patched(f), key=lambda c: c.channel_number)
    return [f.address + c.channel_number - 1 for c in chs if c.attribute == attr]
def dmx(fid, attr):
    f = fx[fid]
    return int(st.universes.get(f.universe).get_channel(kanal(fid, attr)[0]))
def frames(n=6):
    import time
    time.sleep(0.2)          # Cue-Fades laufen auf der Wanduhr (0,05 s Puls-Fade)
    for _ in range(n):
        st._render_frame(1 / 44.0)
erg = {}
pe = st.playback_engine
club, puls = pe.get_executor(1, page=0).stack, pe.get_executor(2, page=0).stack
par_front = [f for f in fx if fx[f].label.startswith("PAR ")][:6]
mh = [f for f in fx if fx[f].label.startswith("MH")]
club.go_to(4.0)
frames()
erg["drop_front"] = [(dmx(f, "intensity"), dmx(f, "color_r"), dmx(f, "color_b")) for f in par_front]
erg["drop_mh"] = [(dmx(f, "intensity"), dmx(f, "color_wheel")) for f in mh]
puls.go_to(2.0)
frames()
erg["puls_front"] = [dmx(f, "intensity") for f in par_front]
puls.stop()
frames()
erg["nach_puls_front"] = [dmx(f, "intensity") for f in par_front]
# Farbe/Dimmer getrennt: Spider-Farbszenen und „Spider an"
def attrs_of(scene):
    aus = set()
    for sv in scene._values:
        f = fx[int(sv.fixture_id)]
        chs = {c.channel_number: c.attribute for c in get_channels_for_patched(f)}
        aus.add(chs[int(sv.channel)])
    return sorted(aus)
erg["szenen"] = {fn.name: attrs_of(fn) for fn in fm.all()
                 if hasattr(fn, "_values")
                 and (fn.name.startswith("Spider Farbe ") or fn.name == "Spider an")}
print("ERG=" + json.dumps(erg))
'''


def _lies_show(pfad):
    with zipfile.ZipFile(pfad) as z:
        return json.loads(z.read("show.json"))


def _widgets(show):
    aus = []

    def walk(o):
        if isinstance(o, dict):
            if "type" in o and str(o.get("type", "")).startswith("VC"):
                aus.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(show.get("virtual_console"))
    return aus


class ShowcaseClubTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="lightos_demo07_club_")
        cls.pfad = os.path.join(cls._tmp.name, "club.lshow")
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
        lauf = subprocess.run([sys.executable, GENERATOR, "--out", cls.pfad], cwd=REPO,
                              env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=900)
        cls.rc, cls.ausgabe = lauf.returncode, lauf.stdout + lauf.stderr
        cls.show = _lies_show(cls.pfad) if os.path.isfile(cls.pfad) else None
        cls.env = env

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _bereit(self):
        self.assertEqual(self.rc, 0, self.ausgabe[-3000:])
        self.assertIsNotNone(self.show)

    def test_lint_strict_sauber(self):
        self._bereit()
        lauf = subprocess.run([sys.executable, os.path.join(REPO, "tools", "lint_show.py"),
                               "--strict", self.pfad], cwd=REPO, env=self.env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=600)
        self.assertEqual(lauf.returncode, 0, lauf.stdout[-3000:] + lauf.stderr[-2000:])
        self.assertIn("0 Fehler, 0 Warnungen", lauf.stdout)

    def test_cue_listen_und_executor_seite(self):
        self._bereit()
        stacks = {s["name"]: s for s in self.show["cue_stacks"]}
        self.assertEqual([c["label"] for c in stacks["Club-Nacht"]["cues"]],
                         ["Intro", "Groove", "Build-up", "Drop", "Breakdown", "Outro"])
        puls = stacks["Drop-Puls"]
        self.assertTrue(puls["beat_sync"])
        self.assertEqual(puls["mode"], "loop")
        self.assertGreaterEqual(len(puls["cues"]), 4)
        ex = self.show["executors"]
        self.assertEqual(ex["page_names"][0], "Club-Nacht")
        belegt = {e["slot"]: e["stack_index"] for e in ex["pages"][0]}
        namen = [s["name"] for s in self.show["cue_stacks"]]
        self.assertEqual(namen[belegt[1]], "Club-Nacht")
        self.assertEqual(namen[belegt[2]], "Drop-Puls")

    def test_vc_hat_go_back_flash_und_tempo(self):
        self._bereit()
        w = _widgets(self.show)
        typen = [x["type"] for x in w]
        self.assertEqual(sorted(x["stack_slot"] for x in w if x["type"] == "VCCueList"), [0, 1])
        playback = [x for x in w if x["type"] == "VCSlider" and x.get("mode") == "Playback"]
        self.assertEqual(sorted(x["playback_slot"] for x in playback), [0, 1])
        flash = [x for x in w if x["type"] == "VCButton" and x.get("action") == "FunctionFlash"]
        self.assertGreaterEqual(len(flash), 3)
        self.assertIn("VCBpmDisplay", typen)
        aktionen = {x.get("action") for x in w if x["type"] == "VCButton"}
        self.assertTrue({"Tap", "AudioBpm", "SyncBus", "Blackout", "LaserEstop"} <= aktionen,
                        aktionen)

    def test_flash_teilt_keine_funktion_mit_einem_schalter(self):
        """Codex #962: Loslassen eines FLASH stoppt seine Funktion unbedingt
        (vc_button.py). Teilt er sie mit einem Schalter (FunctionToggle), geht
        ein eingerasteter Look beim Loslassen aus — FLASH „Laser" vs. „Laser an"."""
        self._bereit()
        def ids(x):
            return {i for i in [x.get("function_id"), *(x.get("function_ids") or [])]
                    if i is not None}
        knoepfe = [x for x in _widgets(self.show) if x["type"] == "VCButton"]
        flash = set().union(*(ids(x) for x in knoepfe if x.get("action") == "FunctionFlash"))
        schalter = set().union(*(ids(x) for x in knoepfe if x.get("action") == "FunctionToggle"))
        self.assertTrue(flash and schalter)
        self.assertEqual(flash & schalter, set())

    def _efx_am_bus(self):
        fns = [f for liste in self.show["functions"].values() for f in liste
               if f.get("type") == "EFX"]
        return [f for f in fns if f.get("tempo_bus_id")]

    def test_bewegungen_ruhig_am_bus(self):
        self._bereit()
        am_bus = self._efx_am_bus()
        self.assertGreaterEqual(len(am_bus), 6)
        for f in am_bus:
            self.assertEqual(f["tempo_bus_id"], "Global", f["name"])
            for bpm in (SEED_BPM, SCHNELL_BPM):
                hz = bpm / 60.0 * float(f["tempo_multiplier"])
                self.assertLessEqual(hz, MAX_HZ, f"{f['name']}: {hz:.2f} Hz bei {bpm} BPM")
            self.assertAlmostEqual(float(f["speed_hz"]),
                                   SEED_BPM / 60.0 * float(f["tempo_multiplier"]), places=3)
        mh = [float(f["tempo_multiplier"]) for f in am_bus if f["name"].startswith("MH")]
        sp = [float(f["tempo_multiplier"]) for f in am_bus if f["name"].startswith("Spider")]
        self.assertTrue(mh and sp)
        self.assertEqual(set(mh), {0.25})
        for m in sp:
            self.assertGreaterEqual(m, max(mh) / 4.0)
            self.assertLessEqual(m, min(mh) / 2.0)

    def test_dials_bieten_nur_ruhige_stufen(self):
        self._bereit()
        efx = {f["id"]: f for f in self._efx_am_bus()}
        dials = [x for x in _widgets(self.show)
                 if x["type"] == "VCSpeedDial" and x.get("target_mode") == "TempoBusMult"]
        bewegung = [d for d in dials if any(i in efx for i in d["function_ids"])]
        self.assertEqual(sorted(d["caption"] for d in bewegung), ["MH ×", "Spider ×"])
        for d in bewegung:
            self.assertLessEqual(max(d["factor_buttons"]) * SCHNELL_BPM / 60.0, MAX_HZ,
                                 d["caption"])

    def test_playback_wirkt_im_render(self):
        self._bereit()
        lauf = subprocess.run([sys.executable, "-c", _TREIBER, REPO, self.pfad], cwd=REPO,
                              env=self.env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=600)
        zeile = [z for z in lauf.stdout.splitlines() if z.startswith("ERG=")]
        self.assertTrue(zeile, lauf.stdout[-2000:] + lauf.stderr[-3000:])
        erg = json.loads(zeile[0][4:])
        self.assertEqual(erg["drop_front"], [[255, 255, 0]] * 6)
        self.assertEqual(erg["drop_mh"], [[255, 8]] * 8)
        self.assertEqual(erg["puls_front"], [64] * 6)        # „Rot 25 %" ueberstimmt Ex 1
        self.assertEqual(erg["nach_puls_front"], [255] * 6)  # nach Stop wieder Ex 1
        for name, attrs in erg["szenen"].items():
            if name == "Spider an":
                self.assertNotIn("color_r", attrs)
            else:
                self.assertTrue(all(a.startswith("color_") for a in attrs), (name, attrs))


if __name__ == "__main__":
    unittest.main()
