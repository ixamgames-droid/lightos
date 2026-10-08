"""ENG-31: Die Bewegungen der Mega-Arena-Demo laufen ruhig, nicht als Zittern.

Beobachtung am Rig: In der Demo-Show aus ``tools/build_mega_arena_2026.py``
drehten die Moving Heads „ganz schnell links-rechts-links auf der Stelle", die
Spider schwenkten sehr schnell.

Ursache (gemessen, headless): Alle Bewegungs-EFX hingen am Master-Bus „Global"
mit ``tempo_multiplier`` 1.0 (Spider Wackeln 2.0). Am laufenden Tempo-Bus gilt
„1 Beat = 1 volle Figur" (``EfxInstance._sync_from_bus``, Semantik in
``test_tempo_sync_matrix.py`` festgehalten) — das im Generator gesetzte
``speed_hz`` wird dann nicht gelesen. Der Generator seedet 150 BPM, die Musik
liefert 128–175 BPM. Ergebnis: 2,45 Figuren/s bei 150 BPM (Kreis mit 130 DMX
Pan-Hub), Spider Wackeln 4,95 Hz. Ein Motor kann das nicht fahren und
schuettelt um die Mitte. Zeitbasis/Windows-Takt ist es nicht: der Render-Takt
uebergibt ein festes ``FRAME_INTERVAL`` — ein groberer Windows-Schlaf macht die
Bewegung langsamer, nie schneller.

Jetzt: eine Figur ueber 16 Beats (0,16 Hz bei 150 BPM), Random ueber 8 Beats,
Spider Wackeln 1/4 mit kleinem Hub. Die Bewegungs-Speed-Dials bieten nur noch
1/16, 1/8 und 1/4 an — der Dial setzt den Multiplikator absolut.

Geprueft wird zweifach:
  * statisch an der gespeicherten Show: Figurfrequenz = BPM/60 × Multiplikator
    fuer jeden Bewegungs-EFX und jeden Faktor der Bewegungs-Dials;
  * gerendert: der Generator laeuft im Unterprozess, danach wird jeder
    Bewegungs-EFX einzeln bei 175 BPM gestartet und die hoechste Pan/Tilt-
    Geschwindigkeit (DMX-Stufen je Sekunde) im Ausgabe-Frame gemessen.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_mega_arena_2026.py")

#: Schnellster Track, den die Show realistisch sieht (Frenchcore/Uptempo-Rand).
SCHNELL_BPM = 175.0
SEED_BPM = 150.0
#: Grosse Figuren (Hub >= 100 DMX): hoechstens 0,3 Figuren je Sekunde.
GROSS_MAX_HZ = 0.3
#: Alles andere (kleiner Hub) und die schnellste Dial-Stufe: hoechstens 0,75 Hz.
KLEIN_MAX_HZ = 0.75
#: Hoechste Pan/Tilt-Geschwindigkeit im Ausgabe-Frame (8-Bit-DMX-Stufen je s).
#: Vorher 390–600/s bei 175 BPM, jetzt 50–200/s.
MAX_DMX_PRO_S = 250.0

_TREIBER = r'''
import contextlib, io, json, os, runpy, sys
repo, bpm = sys.argv[1], float(sys.argv[2])
sys.path.insert(0, repo); sys.path.insert(0, os.path.join(repo, "tools"))
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path(os.path.join(repo, "tools", "build_mega_arena_2026.py"),
                       run_name="__main__")
from src.core.engine.bpm_manager import get_bpm_manager
state, fm = g["state"], g["fm"]
get_bpm_manager().request_bpm(bpm, "test")
FPS = 44.0
for _ in range(5):
    state._render_frame(1 / FPS)
assert abs(g["tbm"].get(g["BUS"]).snapshot()[0] - bpm) < 0.5, "Bus folgt der BPM nicht"
efx = g["MH_SHAPES"] + [g["crowd_sweep"], g["sp_scissor"], g["sp_wave"], g["sp_wiggle"]]
erg = {}
for fn in efx:
    fid = fn.fixtures[0].fid
    fx = g["fx_of"][fid]
    kanaele = [fx.address + rel - 1 for a in ("pan", "tilt") for rel in g["attr_chs"](fid, a)[:1]]
    fm.stop_all()
    for _ in range(3):
        state._render_frame(1 / FPS)
    fm.start(fn.id)
    verlauf = []
    for _ in range(int(8 * FPS)):
        state._render_frame(1 / FPS)
        verlauf.append([g["d1"](c) for c in kanaele])
    fm.stop_all()
    fen = int(FPS / 4)        # 0,25-s-Fenster gegen DMX-Rundungsrauschen
    spitze = 0.0
    for k in range(len(kanaele)):
        werte = [v[k] for v in verlauf]
        for i in range(len(werte) - fen):
            spitze = max(spitze, abs(werte[i + fen] - werte[i]) * FPS / fen)
    hub = max(max(v[k] for v in verlauf) - min(v[k] for v in verlauf)
              for k in range(len(kanaele)))
    erg[fn.name] = {"dmx_pro_s": round(spitze, 1), "hub": hub}
print("ENG31=" + json.dumps(erg))
'''


def _env(tmp):
    env = dict(os.environ)
    musik = os.path.join(tmp, "musik")
    os.makedirs(musik, exist_ok=True)
    env.update({
        "LIGHTOS_GEN_OUT": os.path.join(tmp, "Mega_Arena_2026.lshow"),
        "LIGHTOS_SHOW_DB": os.path.join(tmp, "show.db"),
        "LIGHTOS_MEGA_MUSIC_DIR": musik,      # leer -> Platzhalter-Playlist
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONIOENCODING": "utf-8",
    })
    return env


class MegaArenaBewegtRuhig(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="lightos_eng31_")
        tmp = cls._tmp.name
        lauf = subprocess.run([sys.executable, "-c", _TREIBER, REPO, str(SCHNELL_BPM)],
                              cwd=REPO, env=_env(tmp), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=600)
        cls.ausgabe = lauf.stdout + lauf.stderr
        cls.rc = lauf.returncode
        zeile = next((z for z in lauf.stdout.splitlines() if z.startswith("ENG31=")), None)
        cls.messung = json.loads(zeile[len("ENG31="):]) if zeile else None
        ziel = os.path.join(tmp, "Mega_Arena_2026.lshow")
        cls.show = None
        if os.path.isfile(ziel):
            with zipfile.ZipFile(ziel) as z:
                cls.show = json.loads(z.read("show.json"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _bereit(self):
        self.assertEqual(self.rc, 0, f"Treiber endete mit rc={self.rc}:\n{self.ausgabe[-3000:]}")
        self.assertIsNotNone(self.show, "Generator hat keine Show geschrieben")

    def _efx(self):
        fns = []
        for liste in self.show["functions"].values():
            fns.extend(f for f in liste if f.get("type") == "EFX")
        return {f["id"]: f for f in fns}

    def _dials(self):
        out = []

        def walk(o):
            if isinstance(o, dict):
                if o.get("type") == "VCSpeedDial" and o.get("target_mode") == "TempoBusMult":
                    out.append(o)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(self.show.get("virtual_console"))
        return out

    def test_jede_bewegung_hat_ein_ruhiges_figurtempo(self):
        self._bereit()
        efx = self._efx()
        self.assertGreaterEqual(len(efx), 10)
        zu_schnell = []
        for f in efx.values():
            self.assertEqual(f.get("tempo_bus_id"), "Global", f["name"])
            hub = max(float(f.get("width", 0)), float(f.get("height", 0)))
            grenze = GROSS_MAX_HZ if hub >= 100 else KLEIN_MAX_HZ
            if f.get("algorithm") == "Random":
                # Random zaehlt Wegpunkte je Sekunde, keine geschlossenen Figuren;
                # zwischen zwei Wegpunkten liegt hoechstens ein halber Schwenk.
                grenze = KLEIN_MAX_HZ
            for bpm in (SEED_BPM, SCHNELL_BPM):
                hz = bpm / 60.0 * float(f["tempo_multiplier"])
                if hz > grenze + 1e-9:
                    zu_schnell.append(f"{f['name']}: {hz:.2f} Hz bei {bpm:.0f} BPM (Grenze {grenze})")
            # Free-Run (Bus noch ohne BPM) laeuft wie am Bus beim Seed-Tempo.
            self.assertAlmostEqual(float(f["speed_hz"]),
                                   SEED_BPM / 60.0 * float(f["tempo_multiplier"]), places=3,
                                   msg=f["name"])
        self.assertEqual(zu_schnell, [], "\n".join(zu_schnell))

    def test_bewegungs_dials_bieten_nur_ruhige_stufen(self):
        self._bereit()
        efx = self._efx()
        bewegung = [d for d in self._dials() if any(i in efx for i in d.get("function_ids", []))]
        self.assertEqual(sorted(d["caption"] for d in bewegung),
                         ["Bewegung ×", "MH ×", "Spider ×"])
        for d in bewegung:
            self.assertTrue(all(i in efx for i in d["function_ids"]), d["caption"])
            schnellste = max(d["factor_buttons"]) * SCHNELL_BPM / 60.0
            self.assertLessEqual(schnellste, KLEIN_MAX_HZ, d["caption"])
            # Die Anzeige des Dials zeigt den Faktor, mit dem die Effekte gebaut sind.
            mults = {round(efx[i]["tempo_multiplier"], 6) for i in d["function_ids"]
                     if efx[i]["algorithm"] != "Random"}
            self.assertEqual(mults, {round(d["active_factor"], 6)}, d["caption"])
            self.assertAlmostEqual(d["mult"], d["active_factor"], msg=d["caption"])
        # "Spider Wackeln" hat ein eigenes Tempo und haengt an keinem Dial.
        wackeln = [i for i, f in efx.items() if f["name"] == "Spider Wackeln"]
        self.assertEqual(len(wackeln), 1)
        self.assertFalse(any(wackeln[0] in d["function_ids"] for d in bewegung))

    def test_gerenderte_bewegung_ist_langsam_genug(self):
        self._bereit()
        self.assertIsNotNone(self.messung, self.ausgabe[-3000:])
        self.assertEqual(len(self.messung), 10)
        zu_schnell = {n: m for n, m in self.messung.items() if m["dmx_pro_s"] > MAX_DMX_PRO_S}
        self.assertEqual(zu_schnell, {}, f"zu schnell bei {SCHNELL_BPM:.0f} BPM: {zu_schnell}")
        # ... und es bewegt sich trotzdem etwas (kein „ruhig, weil steht").
        stehend = {n: m for n, m in self.messung.items() if m["hub"] < 20}
        self.assertEqual(stehend, {}, f"bewegt sich nicht: {stehend}")


if __name__ == "__main__":
    unittest.main()
