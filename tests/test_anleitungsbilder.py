"""DOC-16 — Das Bild-Werkzeug ``tools/anleitungsbilder.py`` bleibt in seiner Sandbox.

Das Werkzeug baut ein VOLLES ``MainWindow``. Ohne Umlenkung griffe das auf die
echte Fixture-Bibliothek, ``recent.json``, ``auto_save.lshow``, die sACN-CID und
— relativ zum Arbeitsverzeichnis — auf ``data/`` im Repo zu. Diese Tests halten
fest:

* alle Pfade, die die geladenen Module tatsaechlich benutzen, liegen im
  Temp-Ordner der Sandbox (das Werkzeug meldet sie als ``SANDBOX {...}``);
* ein Mini-Lauf mit EINER Szene erzeugt eine PNG in einem Temp-Ausgabeordner,
  das Manifest enthaelt keine absoluten Pfade;
* der echte Datenordner und ``data/``/``shows/`` im Repo sind danach
  unveraendert (mtime/Groesse/Existenz);
* die Sandbox verweigert sich, wenn ``src`` schon importiert ist (dann waeren
  die Pfade der Module bereits eingefroren);
* ein nicht gefundenes Marken-Widget ist ein Fehler, keine stille Luecke;
* DOC-20: Frames -> GIF (Endlosschleife, Dauern, eine Palette), Zuschnitt und
  Verkleinern, Groessenlimit (Fehler mit Groesse), Stabilitaet (gleiche
  Eingabe -> byte-gleich, unmerkliche Abweichung -> „unveraendert"), und
  jedes GIF unter ``docs/`` bleibt unter 2 MB.

Der Mini-Lauf ist ein eigener Prozess (die Sandbox biegt ``os.environ`` und das
cwd um — das darf die Testsuite nicht erben). Laufzeit ca. 10 s.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from anleitungsbilder import sandbox  # noqa: E402


def _echte_orte():
    home = sandbox.echter_home()
    return [os.path.join(home, ".local", "share", "LightOS"),
            os.path.join(home, ".config", "LightOS"),
            os.path.join(REPO, "data"),
            os.path.join(REPO, "shows")]


def _stand(orte):
    """Unabhaengig vom Werkzeug: {pfad: (mtime_ns, groesse)} bis Tiefe 2."""
    st = {}
    for ort in orte:
        if not os.path.isdir(ort):
            st[ort] = None
            continue
        tiefe0 = ort.rstrip(os.sep).count(os.sep)
        for wurzel, dirs, dateien in os.walk(ort):
            if wurzel.count(os.sep) - tiefe0 >= 2:
                dirs[:] = []
            for d in dateien:
                p = os.path.join(wurzel, d)
                try:
                    s = os.stat(p)
                    st[p] = (s.st_mtime_ns, s.st_size)
                except OSError:
                    pass
    return st


class MiniLaufTest(unittest.TestCase):
    """Ein echter Lauf mit einer Szene — einmal fuer alle Pruefungen."""

    @classmethod
    def setUpClass(cls):
        cls.ausgabe = tempfile.mkdtemp(prefix="lightos_abtest_")
        cls.orte = _echte_orte()
        cls.vorher = _stand(cls.orte)
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cls.lauf = subprocess.run(
            [sys.executable, os.path.join(TOOLS, "anleitungsbilder.py"),
             "projektseite", "--nur", "02_patch", "--ausgabe", cls.ausgabe],
            cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        cls.nachher = _stand(cls.orte)
        cls.app_laeuft = sandbox.laufende_instanz()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.ausgabe, ignore_errors=True)

    def _log(self):
        return (self.lauf.stdout[-3000:] + "\n--- stderr ---\n"
                + self.lauf.stderr[-3000:])

    def test_lauf_gruen(self):
        self.assertEqual(self.lauf.returncode, 0, self._log())

    def test_sandbox_pfade_liegen_alle_im_temp_ordner(self):
        zeilen = [z for z in self.lauf.stdout.splitlines() if z.startswith("SANDBOX ")]
        self.assertEqual(len(zeilen), 1, self._log())
        pfade = json.loads(zeilen[0][len("SANDBOX "):])
        # Die Liste muss die kritischen Stellen wirklich enthalten.
        for pflicht in ("app_data_dir", "fixture_db", "show_db", "universes_json",
                        "crash_log", "sacn_cid", "ui_prefs", "recent_json",
                        "midi_mappings", "channel_groups", "home", "cwd"):
            self.assertIn(pflicht, pfade)
        tmp = os.path.realpath(tempfile.gettempdir())
        basis = os.path.dirname(os.path.realpath(pfade["cwd"]))   # <basis>/arbeit
        self.assertTrue(os.path.basename(basis).startswith("lightos_doku_"), basis)
        self.assertTrue(basis.startswith(tmp + os.sep), f"{basis} nicht unter {tmp}")
        for name, p in pfade.items():
            self.assertTrue(os.path.realpath(p).startswith(basis + os.sep),
                            f"{name} liegt ausserhalb der Sandbox {basis}: {p}")
        # ... und die Sandbox ist nach dem Lauf wieder weg.
        self.assertFalse(os.path.exists(pfade["cwd"]), "Sandbox wurde nicht aufgeraeumt")

    def test_png_und_manifest_im_ausgabeordner(self):
        from PIL import Image
        ziel = os.path.join(self.ausgabe, "projektseite")
        png = os.path.join(ziel, "02_patch.png")
        self.assertTrue(os.path.isfile(png), self._log())
        with Image.open(png) as bild:
            self.assertEqual(bild.size, (1600, 900))
            self.assertEqual(bild.mode, "P", "Bild ist nicht palettiert verkleinert")
        self.assertLess(os.path.getsize(png), 150 * 1024)
        # Nur die eine Szene wurde gebaut.
        self.assertEqual(sorted(f for f in os.listdir(ziel) if f.endswith(".png")),
                         ["02_patch.png"])
        with open(os.path.join(ziel, "bilder.json"), encoding="utf-8") as f:
            text = f.read()
        manifest = json.loads(text)
        self.assertEqual([b["datei"] for b in manifest["bilder"]], ["02_patch.png"])
        self.assertEqual(manifest["bilder"][0]["groesse"], [1600, 900])
        self.assertTrue(manifest["schrift"])
        self.assertNotIn(os.path.realpath(tempfile.gettempdir()), text)
        self.assertNotIn(sandbox.echter_home(), text)
        self.assertNotIn("/home/", text)
        self.assertNotIn(REPO, text)

    def test_echter_datenordner_unveraendert(self):
        diff = sandbox.vergleiche(self.vorher, self.nachher, app_laeuft=self.app_laeuft)
        self.assertEqual(diff, [], "Das Werkzeug hat echte Datenorte veraendert")


class SandboxRiegelTest(unittest.TestCase):

    def test_sandbox_verweigert_sich_nach_src_import(self):
        import src.core.paths  # noqa: F401  (friert die Modulpfade ein)
        vorher = dict(os.environ)
        cwd = os.getcwd()
        with self.assertRaises(RuntimeError):
            sandbox.einrichten()
        self.assertEqual(dict(os.environ), vorher)
        self.assertEqual(os.getcwd(), cwd)


class WindowsHomeTest(unittest.TestCase):
    """XPLAT-39: auf Windows liest expanduser("~") USERPROFILE. Die Sandbox muss
    es (und LOCALAPPDATA) wie HOME umlenken — gemessen in einem frischen
    Prozess, weil einrichten() sich nach einem src-Import verweigert."""

    def test_userprofile_und_localappdata_liegen_in_der_sandbox(self):
        code = (
            "import os, sys; sys.path.insert(0, %r)\n"
            "from anleitungsbilder import sandbox\n"
            "sb = sandbox.einrichten()\n"
            "b = os.path.realpath(sb.basis)\n"
            "for k in ('USERPROFILE', 'LOCALAPPDATA', 'HOME'):\n"
            "    v = os.path.realpath(os.environ[k])\n"
            "    print(k, v.startswith(b + os.sep))\n"
            "import shutil; os.chdir(%r); shutil.rmtree(b, ignore_errors=True)\n"
        ) % (TOOLS, REPO)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60, cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        for k in ("USERPROFILE", "LOCALAPPDATA", "HOME"):
            self.assertIn(f"{k} True", r.stdout)


class MarkenFinderTest(unittest.TestCase):

    def test_fehlendes_widget_ist_ein_fehler(self):
        from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
        from anleitungsbilder import runner
        app = QApplication.instance() or QApplication([])
        fenster = QWidget()
        lay = QVBoxLayout(fenster)
        knopf = QPushButton("Farb-Werkzeug…")
        lay.addWidget(knopf)
        fenster.show()
        app.processEvents()
        try:
            ui = runner.UI(app, fenster, None, {})
            # „…" im Code und „..." in der Szene gelten als gleich.
            self.assertIs(ui.finde("Farb-Werkzeug..."), knopf)
            with self.assertRaises(runner.SzenenFehler):
                ui.finde("Gibt es nicht")
        finally:
            fenster.close()
            fenster.deleteLater()


class PlatzierungTest(unittest.TestCase):
    """Reine Geometrie der Kreis-Lage (``marker.platzieren``) — ohne App."""

    def setUp(self):
        from PySide6.QtCore import QRect
        from anleitungsbilder import marker
        self.marker, self.QRect = marker, QRect
        self.ziel = QRect(300, 200, 80, 30)

    def _feld(self, c):
        return self.marker._kreisfeld(c)

    def test_vorzug_wird_genommen_wenn_frei(self):
        (c, linie, gefunden), = self.marker.platzieren(
            [self.ziel], 800, 600, [], ["links"])
        self.assertTrue(gefunden)
        self.assertFalse(linie)
        self.assertLess(c.x(), self.ziel.left())               # links daneben
        self.assertTrue(self.ziel.top() <= c.y() <= self.ziel.bottom())

    def test_kandidat_mit_kollision_wird_verworfen(self):
        # Ein beschrifteter Nachbar-Knopf direkt links: der Vorzug „links"
        # kollidiert und muss verworfen werden.
        nachbar = self.QRect(230, 195, 64, 40)
        (c, _linie, gefunden), = self.marker.platzieren(
            [self.ziel], 800, 600, [nachbar], ["links"])
        self.assertTrue(gefunden)
        self.assertFalse(self._feld(c).intersects(nachbar))
        self.assertGreaterEqual(c.x(), self.ziel.left())       # nicht mehr links

    def test_kein_kreis_auf_fremdem_rahmen_oder_kreis(self):
        a = self.ziel
        b = self.QRect(300, 250, 80, 30)                       # direkt darunter
        (ca, _l1, g1), (cb, _l2, g2) = self.marker.platzieren(
            [a, b], 800, 600, [], ["unten", "oben"])
        self.assertTrue(g1 and g2)
        rahmen_b = self.marker.rahmen_von(b, 800, 600)
        rahmen_a = self.marker.rahmen_von(a, 800, 600)
        self.assertFalse(self._feld(ca).intersects(rahmen_b))
        self.assertFalse(self._feld(cb).intersects(rahmen_a))
        self.assertFalse(self._feld(ca).intersects(self._feld(cb)))

    def test_kreis_haengt_eindeutig_am_eigenen_rahmen(self):
        # Zwei Menuezeilen uebereinander, rechts neben der oberen ein
        # beschrifteter Knopf: der Kreis der oberen Zeile darf nicht so
        # ausweichen, dass er naeher an der unteren Zeile sitzt.
        oben = self.QRect(0, 100, 270, 27)
        unten = self.QRect(0, 127, 270, 27)
        knopf = self.QRect(276, 90, 80, 40)
        (c, _l, gefunden), _zweite = self.marker.platzieren(
            [oben, unten], 800, 600, [knopf], ["rechts", "rechts"])
        ra = self.marker.rahmen_von(oben, 800, 600)
        rb = self.marker.rahmen_von(unten, 800, 600)
        self.assertLess(self.marker._abstand(ra, c), self.marker._abstand(rb, c))
        self.assertFalse(self._feld(c).intersects(knopf))

    def test_kreis_bleibt_im_bild(self):
        am_rand = self.QRect(0, 0, 120, 30)
        (c, _linie, gefunden), = self.marker.platzieren(
            [am_rand], 800, 600, [], ["links"])
        self.assertTrue(gefunden)
        self.assertTrue(self.QRect(0, 0, 800, 600).contains(self._feld(c)))

    def test_eingekesselt_weiter_weg_mit_linie(self):
        # Rundum eine schmale beschriftete Zeile (8 px) dicht am Rahmen: der
        # Kreis muss dahinter, haengt dann per Verbindungslinie am Rahmen.
        z = self.ziel
        ring = [self.QRect(z.left() - 60, z.top() - 14, z.width() + 120, 8),
                self.QRect(z.left() - 60, z.bottom() + 7, z.width() + 120, 8),
                self.QRect(z.left() - 14, z.top() - 6, 8, z.height() + 12),
                self.QRect(z.right() + 7, z.top() - 6, 8, z.height() + 12)]
        (c, linie, gefunden), = self.marker.platzieren([z], 800, 600, ring)
        self.assertTrue(gefunden)
        self.assertTrue(all(not self._feld(c).intersects(h) for h in ring))
        self.assertTrue(linie)


def _bilder(n=3, groesse=(800, 450)):
    """UI-artige Testbilder: dunkle Flaeche, Text, ein Feld, das je Frame
    die Farbe wechselt."""
    from PIL import Image, ImageDraw
    aus = []
    for i in range(n):
        b = Image.new("RGB", groesse, (30, 33, 40))
        d = ImageDraw.Draw(b)
        for k in range(12):
            d.text((10 + k * 40, 20 + k * 12), f"Kanal {k}", fill=(210, 210, 210))
        d.rectangle((300, 200, 420, 260), fill=((255, 0, 0), (0, 0, 0), (0, 0, 255))[i % 3])
        aus.append(b)
    return aus


class GifTest(unittest.TestCase):
    """DOC-20: GIF-Erzeugung ohne App (reines Pillow)."""

    def setUp(self):
        from anleitungsbilder import runner
        self.runner = runner

    def test_frames_werden_gif_mit_endlosschleife(self):
        import io
        from PIL import Image
        daten = self.runner.gif_bytes(_bilder(), [1000, 1500, 1200])
        self.assertTrue(daten.startswith(b"GIF89a"))
        with Image.open(io.BytesIO(daten)) as im:
            self.assertEqual(im.info.get("loop"), 0, "keine Endlosschleife")
            self.assertEqual(im.n_frames, 3)
            self.assertEqual(im.size, (800, 450))
        frames = self.runner.gif_frames(daten)
        self.assertEqual([d for _f, d in frames], [1000, 1500, 1200])
        # Frame 2 ist wirklich anders (Feld schwarz statt rot), voll zusammengesetzt.
        self.assertEqual(frames[0][0].getpixel((350, 230)), (255, 0, 0))
        self.assertEqual(frames[1][0].getpixel((350, 230)), (0, 0, 0))
        self.assertEqual(frames[2][0].getpixel((350, 230)), (0, 0, 255))
        self.assertEqual(frames[1][0].getpixel((5, 5)), (30, 33, 40))

    def test_zuschnitt_und_verkleinern(self):
        daten = self.runner.gif_bytes(_bilder(2), [500, 500],
                                      zuschnitt=(100, 50, 600, 300), breite=300)
        frames = self.runner.gif_frames(daten)
        self.assertEqual(frames[0][0].size, (300, 150))
        # Nie vergroessern.
        daten = self.runner.gif_bytes(_bilder(2), [500, 500], breite=2000)
        self.assertEqual(self.runner.gif_frames(daten)[0][0].size, (800, 450))

    def test_groessenlimit_ist_fehler_mit_groesse(self):
        self.assertEqual(self.runner.GIF_LIMIT, 2 * 1024 * 1024)
        with self.assertRaises(self.runner.GifZuGross) as ctx:
            self.runner.gif_bytes(_bilder(), [1000] * 3, limit=1000)
        self.assertIn("MB", str(ctx.exception))
        self.assertTrue(issubclass(self.runner.GifZuGross, self.runner.SzenenFehler))

    def test_ungleiche_eingaben_sind_fehler(self):
        with self.assertRaises(self.runner.SzenenFehler):
            self.runner.gif_bytes([], [])
        with self.assertRaises(self.runner.SzenenFehler):
            self.runner.gif_bytes(_bilder(2), [1000])
        a, b = _bilder(2)
        with self.assertRaises(self.runner.SzenenFehler):
            self.runner.gif_bytes([a, b.resize((400, 225))], [1000, 1000])

    def test_stabil_bytegleich_und_unveraendert_erkannt(self):
        import tempfile as tf
        eingabe = _bilder()
        eins = self.runner.gif_bytes(eingabe, [1000, 1500, 1200])
        zwei = self.runner.gif_bytes(_bilder(), [1000, 1500, 1200])
        self.assertEqual(eins, zwei, "gleiche Eingabe muss byte-gleich sein")
        with tf.TemporaryDirectory() as d:
            pfad = os.path.join(d, "a.gif")
            with open(pfad, "wb") as f:
                f.write(eins)
            self.assertTrue(self.runner.ist_gleich(pfad, zwei))
            # Ein einzelner anders glimmender Pixel -> gilt als unveraendert.
            leicht = _bilder()
            leicht[1].putpixel((700, 400), (255, 255, 255))
            self.assertTrue(self.runner.gif_fast_gleich(
                pfad, self.runner.gif_bytes(leicht, [1000, 1500, 1200])))
            # Andere Dauer, anderer Inhalt, andere Frame-Zahl -> geaendert.
            self.assertFalse(self.runner.gif_fast_gleich(
                pfad, self.runner.gif_bytes(_bilder(), [1000, 1500, 900])))
            anders = _bilder()
            anders[0].paste((0, 255, 0), (0, 0, 800, 200))
            self.assertFalse(self.runner.gif_fast_gleich(
                pfad, self.runner.gif_bytes(anders, [1000, 1500, 1200])))
            self.assertFalse(self.runner.gif_fast_gleich(
                pfad, self.runner.gif_bytes(_bilder(2), [1000, 1500])))
            self.assertFalse(self.runner.gif_fast_gleich(
                os.path.join(d, "fehlt.gif"), eins))

    def test_szene_mit_frames_wird_gif(self):
        sz = self.runner.Szene("05_ablauf", frames=[self.runner.Frame(dauer_s=1.0)])
        self.assertTrue(sz.ist_gif)
        self.assertEqual(sz.datei, "05_ablauf.gif")
        self.assertEqual(self.runner.Szene("05_bild").datei, "05_bild.png")

    def test_gifs_in_docs_unter_der_grenze_und_in_schleife(self):
        """Jedes GIF unter docs/ <= 2 MB; die vom Werkzeug erzeugten (im
        Manifest ``bilder.json`` gefuehrten) laufen in Endlosschleife."""
        from PIL import Image
        gefunden = 0
        for wurzel, _dirs, dateien in os.walk(os.path.join(REPO, "docs")):
            werkzeug = set()
            if "bilder.json" in dateien:
                with open(os.path.join(wurzel, "bilder.json"), encoding="utf-8") as f:
                    werkzeug = {b["datei"] for b in json.load(f).get("bilder", [])}
            for name in dateien:
                if not name.lower().endswith(".gif"):
                    continue
                pfad = os.path.join(wurzel, name)
                groesse = os.path.getsize(pfad)
                self.assertLessEqual(groesse, 2 * 1024 * 1024,
                                     f"{name}: {groesse / 1024 / 1024:.2f} MB > 2 MB")
                if name not in werkzeug:
                    continue
                gefunden += 1
                with Image.open(pfad) as im:
                    self.assertEqual(im.info.get("loop"), 0, f"{name}: keine Endlosschleife")
                    self.assertGreater(im.n_frames, 1, f"{name}: nur ein Frame")
        self.assertGreater(gefunden, 0)
# ── TOOL-8: jede Anleitung startet frisch ─────────────────────────────────────

_SZENE_HINTERLASSEN = """
from anleitungsbilder.runner import Szene


def _zustand_hinterlassen(ui):
    from src.core.engine.bpm_manager import BpmMode, get_bpm_manager
    pars = ui.info["pars"]
    ui.wert(pars, "intensity", 255)
    ui.win._programmer_view._select_fids(pars[:4])
    mgr = get_bpm_manager()
    mgr.set_mode(BpmMode.MANUAL)
    mgr.set_manual_bpm(128.0)
    ui.pump(0.1)


SZENEN = [Szene("t8_hinterlassen", sektion="Programmer", unterreiter="Attribute",
                vorher=_zustand_hinterlassen, warte_s=0.1)]
"""

_SZENE_FRISCH = """
from anleitungsbilder.runner import Szene, SzenenFehler


def _frisch(ui):
    from src.core.engine.bpm_manager import BpmMode, get_bpm_manager
    pv = ui.win._programmer_view
    mgr = get_bpm_manager()
    reste = []
    if list(ui.state.selected_fids or []):
        reste.append("Auswahl %r" % list(ui.state.selected_fids))
    if any(ui.state.programmer.values()):
        reste.append("Programmer-Werte")
    if pv._editor_fids or pv._fixture_combo.count():
        reste.append("Programmer-Ansicht %r" % pv._editor_fids)
    if mgr.mode == BpmMode.MANUAL and abs(mgr.bpm - 128.0) < 0.01:
        reste.append("BPM 128 manuell")
    if reste:
        raise SzenenFehler("Zustand der vorigen Anleitung: " + ", ".join(reste))


SZENEN = [Szene("t8_frisch", sektion="Programmer", unterreiter="Attribute",
                vorher=_frisch, warte_s=0.1)]
"""


class AlleFrischTest(unittest.TestCase):
    """TOOL-8: ``--alle`` lief alle Anleitungen im SELBEN Fenster; die zweite
    sah Auswahl, Programmer-Werte und BPM 128 der ersten. Zwei Test-Anleitungen
    (ueber ``LIGHTOS_DOKU_SZENEN_ORDNER``, nicht im Paket): die erste
    hinterlaesst Zustand, die zweite bricht ab, wenn sie ihn sieht."""

    def test_zweite_anleitung_sieht_den_zustand_der_ersten_nicht(self):
        import shutil
        ordner = tempfile.mkdtemp(prefix="lightos_abtest_szenen_")
        ausgabe = tempfile.mkdtemp(prefix="lightos_abtest_")
        try:
            for name, text in (("t8a_hinterlassen", _SZENE_HINTERLASSEN),
                               ("t8b_frisch", _SZENE_FRISCH)):
                with open(os.path.join(ordner, f"szenen_{name}.py"), "w",
                          encoding="utf-8") as f:
                    f.write(text)
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["LIGHTOS_DOKU_SZENEN_ORDNER"] = ordner
            lauf = subprocess.run(
                [sys.executable, os.path.join(TOOLS, "anleitungsbilder.py"),
                 "--alle", "--nur", "t8_hinterlassen,t8_frisch",
                 "--ausgabe", ausgabe],
                cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            log = lauf.stdout[-4000:] + "\n--- stderr ---\n" + lauf.stderr[-3000:]
            self.assertNotIn("Zustand der vorigen Anleitung", lauf.stdout, log)
            self.assertEqual(lauf.returncode, 0, log)
            for name, szene in (("t8a_hinterlassen", "t8_hinterlassen"),
                                ("t8b_frisch", "t8_frisch")):
                self.assertTrue(os.path.isfile(
                    os.path.join(ausgabe, name, f"{szene}.png")), log)
            # Jede Anleitung hatte ihre eigene Sandbox (= eigenen Prozess).
            sandboxen = {json.loads(z[len("SANDBOX "):])["cwd"]
                         for z in lauf.stdout.splitlines() if z.startswith("SANDBOX ")}
            self.assertEqual(len(sandboxen), 2, log)
        finally:
            shutil.rmtree(ordner, ignore_errors=True)
            shutil.rmtree(ausgabe, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
