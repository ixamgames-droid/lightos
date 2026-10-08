"""ENG-31: Die Bewegungen der Demo-Generatoren laufen ruhig, nicht als Zittern.

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

Dasselbe Muster stand in drei weiteren Generatoren: ``build_demo_show_full.py``
und ``build_farb_fx_vc_show.py`` (alle Bewegungs-EFX an „Global" mit 1.0 bzw.
2.0) und ``build_event_demo_2026.py`` („Sync MH-Kreis >Bus A" mit 1.0; die
uebrigen EFX dort sind als Free-Run gemeint, hingen aber per Default an
„Global" mit 1.0).

Jetzt, nach der Regel des Projektinhabers vom Rig: Bewegungen bleiben am Bus
(taktsynchron), aber mit kleinem Faktor — Moving Heads 1/4 (eine Figur je
Takt), Spider 1/4 bis 1/2 davon (1/8), auch „Spider Wackeln"; Spider sind nie
schneller als die Moving Heads. Die Bewegungs-Dials bieten genau diese Stufen
(MH 1/8 und 1/4, Spider 1/16 und 1/8) und zeigen den Baufaktor an; kein Dial
mischt Spider und MH, denn der Dial setzt den Multiplikator absolut.

Geprueft wird zweifach:
  * statisch, fuer ALLE vier Generatoren an der gebauten Show:
    Figurfrequenz = BPM/60 × Multiplikator (× Bus-Faktor) fuer jeden
    bus-gebundenen Bewegungs-EFX und jede Dial-Stufe, bei 150 und 175 BPM,
    hoechstens 0,75 Hz; Spider-Faktor <= MH-Faktor;
  * gerendert (Mega Arena): der Generator laeuft im Unterprozess, danach wird
    jeder Bewegungs-EFX einzeln bei 175 BPM gestartet und das Figurtempo aus
    den Mittendurchgaengen von Pan/Tilt im Ausgabe-Frame gemessen (vorher
    2,9 Hz, jetzt MH 0,7 Hz, Spider 0,35 Hz).

Die Generatoren schreiben ueber ``LIGHTOS_GEN_OUT`` in einen Wegwerf-Ordner —
die mitgelieferten ``shows/*.lshow`` fasst der Test nicht an.
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
#: Regel vom Rig (Projektinhaber): Moving Heads laufen mit Grundfaktor 1/4 am Bus,
#: Spider mit 1/4 bis 1/2 davon. Hoechstens 0,75 Figuren je Sekunde = Faktor 1/4
#: bis 180 BPM — vorher Faktor 1 (2,9 Hz bei 175 BPM), Spider Wackeln Faktor 2.
MAX_HZ = 0.75
#: Messtoleranz der gerenderten Frequenz (Nulldurchgaenge in 10 s, +-1 Durchgang).
TOLERANZ_HZ = 0.08

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
FPS, DAUER = 44.0, 10.0
for _ in range(5):
    state._render_frame(1 / FPS)
assert abs(g["tbm"].get(g["BUS"]).snapshot()[0] - bpm) < 0.5, "Bus folgt der BPM nicht"
efx = g["MH_SHAPES"] + [g["crowd_sweep"], g["sp_scissor"], g["sp_wave"], g["sp_wiggle"]]


def durchgaenge(werte):
    # Mittendurchgaenge mit Hysterese (15 % des Hubs) — zwei je Figur und Achse.
    lo, hi = min(werte), max(werte)
    mitte, band = (lo + hi) / 2.0, 0.15 * (hi - lo)
    zustand, n = None, 0
    for w in werte:
        z = 1 if w > mitte + band else (-1 if w < mitte - band else zustand)
        if zustand is not None and z != zustand:
            n += 1
        zustand = z
    return n


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
    for _ in range(int(DAUER * FPS)):
        state._render_frame(1 / FPS)
        verlauf.append([g["d1"](c) for c in kanaele])
    fm.stop_all()
    hz, hub = [], 0
    for k in range(len(kanaele)):
        werte = [v[k] for v in verlauf]
        h = max(werte) - min(werte)
        hub = max(hub, h)
        if h >= 20:
            hz.append(durchgaenge(werte) / (2.0 * DAUER))
    # Eine Acht faehrt Tilt doppelt so schnell wie Pan: die langsamere Achse ist
    # das Figurtempo.
    erg[fn.name] = {"hz": round(min(hz), 3) if hz else 0.0, "hub": hub}
print("ENG31=" + json.dumps(erg))
'''


def _env(tmp, ziel):
    env = dict(os.environ)
    musik = os.path.join(tmp, "musik")
    os.makedirs(musik, exist_ok=True)
    env.update({
        "LIGHTOS_GEN_OUT": ziel,
        "LIGHTOS_SHOW_DB": os.path.join(tmp, "show.db"),
        "LIGHTOS_MEGA_MUSIC_DIR": musik,      # leer -> Platzhalter-Playlist
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def _lies_show(ziel):
    if not os.path.isfile(ziel):
        return None
    with zipfile.ZipFile(ziel) as z:
        return json.loads(z.read("show.json"))


class _FigurtempoPruefung:
    """Gemeinsame statische Pruefung — je Generator eine Unterklasse."""

    #: Dateiname unter ``tools/``.
    GENERATOR = ""
    #: Erwartete Bewegungs-Dials (Caption), sortiert.
    BEWEGUNGS_DIALS = []
    #: Mindestzahl bus-gebundener Bewegungs-EFX (gegen einen leer gruenen Test).
    MIN_BUS_EFX = 1

    @classmethod
    def _baue(cls, tmp, ziel):
        """Generator im Unterprozess; liefert ``(rc, ausgabe)``."""
        lauf = subprocess.run([sys.executable, os.path.join(REPO, "tools", cls.GENERATOR)],
                              cwd=REPO, env=_env(tmp, ziel), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=600)
        return lauf.returncode, lauf.stdout + lauf.stderr

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="lightos_eng31_")
        ziel = os.path.join(cls._tmp.name, "show.lshow")
        cls.rc, cls.ausgabe = cls._baue(cls._tmp.name, ziel)
        cls.show = _lies_show(ziel)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _bereit(self):
        self.assertEqual(self.rc, 0, f"{self.GENERATOR} endete mit rc={self.rc}:\n"
                                     f"{self.ausgabe[-3000:]}")
        self.assertIsNotNone(self.show, f"{self.GENERATOR} hat keine Show geschrieben")

    def _efx(self):
        fns = []
        for liste in self.show["functions"].values():
            fns.extend(f for f in liste if f.get("type") == "EFX")
        return {f["id"]: f for f in fns}

    def _bus_faktor(self, bus_id):
        """Sub-Bus (z. B. Event-Demo B = 1/2, C = ×2) laeuft mit seinem Faktor."""
        for b in self.show.get("tempo_buses") or []:
            if b.get("bus_id") == bus_id and b.get("role") == "sub":
                return float(b.get("bus_multiplier", 1.0) or 1.0)
        return 1.0

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

    @staticmethod
    def _ist_spider(f):
        return f["name"].startswith("Spider")

    def test_jede_bewegung_hat_ein_ruhiges_figurtempo(self):
        self._bereit()
        efx = self._efx()
        am_bus = [f for f in efx.values() if f.get("tempo_bus_id")]
        self.assertGreaterEqual(len(am_bus), self.MIN_BUS_EFX, self.GENERATOR)
        zu_schnell = []
        for f in am_bus:
            mult = float(f["tempo_multiplier"]) * self._bus_faktor(f["tempo_bus_id"])
            for bpm in (SEED_BPM, SCHNELL_BPM):
                hz = bpm / 60.0 * mult
                if hz > MAX_HZ + 1e-9:
                    zu_schnell.append(f"{f['name']}: {hz:.2f} Hz bei {bpm:.0f} BPM "
                                      f"(Grenze {MAX_HZ})")
            # Free-Run (Bus noch ohne BPM) laeuft wie am Bus beim Seed-Tempo.
            self.assertAlmostEqual(float(f["speed_hz"]), SEED_BPM / 60.0 * mult, places=3,
                                   msg=f"{self.GENERATOR}: {f['name']}")
        self.assertEqual(zu_schnell, [], f"{self.GENERATOR}:\n" + "\n".join(zu_schnell))

    def test_spider_laufen_langsamer_als_die_moving_heads(self):
        """Regel vom Rig: Spider mit 1/4 bis 1/2 des MH-Faktors — auch „Wackeln"."""
        self._bereit()
        am_bus = [f for f in self._efx().values() if f.get("tempo_bus_id")]

        def mult(f):
            return float(f["tempo_multiplier"]) * self._bus_faktor(f["tempo_bus_id"])
        mh = [mult(f) for f in am_bus if not self._ist_spider(f)]
        spider = {f["name"]: mult(f) for f in am_bus if self._ist_spider(f)}
        self.assertTrue(mh, self.GENERATOR)
        if not spider:
            return
        langsamstes_mh, mh_grund = min(mh), max(mh)
        zu_schnell = {n: m for n, m in spider.items() if m > langsamstes_mh + 1e-9}
        self.assertEqual(zu_schnell, {}, f"{self.GENERATOR}: Spider schneller als MH "
                                         f"(MH ab {langsamstes_mh})")
        for n, m in spider.items():
            self.assertGreaterEqual(m, mh_grund / 4.0 - 1e-9, n)
            self.assertLessEqual(m, mh_grund / 2.0 + 1e-9, n)

    def test_bewegungs_dials_bieten_nur_ruhige_stufen(self):
        self._bereit()
        efx = self._efx()
        bewegung = [d for d in self._dials() if any(i in efx for i in d.get("function_ids", []))]
        self.assertEqual(sorted(d["caption"] for d in bewegung), self.BEWEGUNGS_DIALS)
        mh_stufen, sp_stufen = [], []
        for d in bewegung:
            self.assertTrue(all(i in efx for i in d["function_ids"]), d["caption"])
            schnellste = max(d["factor_buttons"]) * SCHNELL_BPM / 60.0
            self.assertLessEqual(schnellste, MAX_HZ, d["caption"])
            # Die Anzeige des Dials zeigt den Faktor, mit dem die Effekte gebaut
            # sind — fuer ALLE Effekte am Dial, auch Random.
            mults = {round(efx[i]["tempo_multiplier"], 6) for i in d["function_ids"]}
            self.assertEqual(mults, {round(d["active_factor"], 6)}, d["caption"])
            self.assertAlmostEqual(d["mult"], d["active_factor"], msg=d["caption"])
            # Der Dial setzt den Faktor ABSOLUT: Spider und MH an einem Dial
            # liefen danach gleich schnell.
            arten = {self._ist_spider(efx[i]) for i in d["function_ids"]}
            self.assertEqual(len(arten), 1, f"{d['caption']} mischt Spider und MH")
            (sp_stufen if arten == {True} else mh_stufen).extend(d["factor_buttons"])
        if mh_stufen and sp_stufen:
            self.assertLessEqual(max(sp_stufen), min(mh_stufen),
                                 "eine Spider-Stufe ist schneller als eine MH-Stufe")


class MegaArenaBewegtRuhig(_FigurtempoPruefung, unittest.TestCase):
    GENERATOR = "build_mega_arena_2026.py"
    BEWEGUNGS_DIALS = ["Bewegung ×", "MH ×", "Spider ×"]
    MIN_BUS_EFX = 10

    @classmethod
    def _baue(cls, tmp, ziel):
        # Mega Arena: der Treiber baut die Show UND misst danach gerendert.
        lauf = subprocess.run([sys.executable, "-c", _TREIBER, REPO, str(SCHNELL_BPM)],
                              cwd=REPO, env=_env(tmp, ziel), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=600)
        zeile = next((z for z in lauf.stdout.splitlines() if z.startswith("ENG31=")), None)
        cls.messung = json.loads(zeile[len("ENG31="):]) if zeile else None
        return lauf.returncode, lauf.stdout + lauf.stderr

    def test_alle_bewegungen_haengen_am_master(self):
        self._bereit()
        for f in self._efx().values():
            self.assertEqual(f.get("tempo_bus_id"), "Global", f["name"])

    def test_gerenderte_bewegung_ist_langsam_genug(self):
        self._bereit()
        self.assertIsNotNone(self.messung, self.ausgabe[-3000:])
        self.assertEqual(len(self.messung), 10)
        zu_schnell = {n: m for n, m in self.messung.items() if m["hz"] > MAX_HZ + TOLERANZ_HZ}
        self.assertEqual(zu_schnell, {}, f"zu schnell bei {SCHNELL_BPM:.0f} BPM: {zu_schnell}")
        # ... und es bewegt sich trotzdem etwas (kein „ruhig, weil steht").
        stehend = {n: m for n, m in self.messung.items() if m["hub"] < 20 or m["hz"] <= 0}
        self.assertEqual(stehend, {}, f"bewegt sich nicht: {stehend}")
        # Spider gerendert langsamer als die Moving Heads (Random zaehlt Wegpunkte).
        mh = [m["hz"] for n, m in self.messung.items()
              if not n.startswith("Spider") and n != "MH Random"]
        spider = {n: m["hz"] for n, m in self.messung.items() if n.startswith("Spider")}
        self.assertEqual({n: h for n, h in spider.items() if h > min(mh) + TOLERANZ_HZ}, {},
                         f"Spider schneller als MH ({min(mh)} Hz)")


class DemoShowFullBewegtRuhig(_FigurtempoPruefung, unittest.TestCase):
    GENERATOR = "build_demo_show_full.py"
    BEWEGUNGS_DIALS = ["Bewegung ×", "MH ×", "Spider ×"]
    MIN_BUS_EFX = 11


class FarbFxVcShowBewegtRuhig(_FigurtempoPruefung, unittest.TestCase):
    GENERATOR = "build_farb_fx_vc_show.py"
    BEWEGUNGS_DIALS = ["Bewegung ×", "MH ×", "Spider ×"]
    MIN_BUS_EFX = 10


class EventDemoBewegtRuhig(_FigurtempoPruefung, unittest.TestCase):
    GENERATOR = "build_event_demo_2026.py"
    BEWEGUNGS_DIALS = []          # Speed-Dials dort steuern Buses (SpeedNode), keine EFX

    def test_sync_kreis_haengt_an_bus_a_die_anderen_laufen_frei(self):
        self._bereit()
        efx = {f["name"]: f for f in self._efx().values()}
        self.assertEqual(efx["Sync MH-Kreis >Bus A"]["tempo_bus_id"], "A")
        frei = [n for n, f in efx.items() if n != "Sync MH-Kreis >Bus A"]
        self.assertGreaterEqual(len(frei), 8)
        # Free-Run ist dort gemeint (speed_hz). Haengen sie per Default an
        # "Global" mit Faktor 1, laeuft bei jeder Musik-BPM ein Beat je Figur.
        self.assertEqual({n: efx[n]["tempo_bus_id"] for n in frei if efx[n]["tempo_bus_id"]}, {})


if __name__ == "__main__":
    unittest.main()
