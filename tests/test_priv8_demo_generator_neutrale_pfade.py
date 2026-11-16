"""PRIV-8: der Generator der GETRACKTEN Demo-Show schreibt keine privaten Pfade.

``tools/build_demo_show_full.py`` las einen festen Musikordner und legte
dessen absolute Pfade in die Playlist der Show — so kamen Kontoname und
Ordnerstruktur ins oeffentliche Repo. Jetzt steht dort nur ``Musik/<datei>``,
auch wenn ein echter Ordner (``LIGHTOS_DEMO_MUSIC_DIR``) gelesen wird.

Laeuft im Unterprozess mit Wegwerf-Daten (``LIGHTOS_GEN_OUT``,
``LIGHTOS_SHOW_DB``, ``LIGHTOS_DATEN_ORDNER``); die mitgelieferte Show bleibt
unberuehrt.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_demo_show_full.py")
MITGELIEFERT = os.path.join(REPO, "shows", "Demo_Show_Full.lshow")


def _sha(pfad):
    with open(pfad, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class DemoGeneratorNeutralePfade(unittest.TestCase):

    def test_echter_musikordner_landet_nur_als_relativer_pfad(self):
        vorher = _sha(MITGELIEFERT)
        with tempfile.TemporaryDirectory(prefix="lightos_priv8_") as tmp:
            musik = os.path.join(tmp, "konto" + "ordner", "Desktop", "Musik")
            os.makedirs(musik)
            with open(os.path.join(musik, "Probe Track 150 BPM.mp3"), "wb") as f:
                f.write(b"\0")
            os.makedirs(os.path.join(tmp, "daten"))
            ziel = os.path.join(tmp, "Demo_Show_Full.lshow")
            env = {k: v for k, v in os.environ.items()
                   if k not in ("LIGHTOS_ECHTE_DATEN", "LIGHTOS_ECHTE_AUSGABE")}
            env.update({
                "LIGHTOS_GEN_OUT": ziel,
                "LIGHTOS_SHOW_DB": os.path.join(tmp, "show.db"),
                "LIGHTOS_DATEN_ORDNER": os.path.join(tmp, "daten"),
                "LIGHTOS_DEMO_MUSIC_DIR": musik,
                "QT_QPA_PLATFORM": "offscreen",
                "PYTHONIOENCODING": "utf-8",
            })
            lauf = subprocess.run([sys.executable, GENERATOR], cwd=REPO, env=env,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=300)
            self.assertEqual(lauf.returncode, 0,
                             (lauf.stdout + lauf.stderr)[-3000:])
            self.assertIn("FERTIG", lauf.stdout)
            with zipfile.ZipFile(ziel) as z:
                text = z.read("show.json").decode("utf-8")
            show = json.loads(text)
        pfade = [t["path"] for t in show["playlist"]]
        self.assertEqual(pfade, ["Musik/Probe Track 150 BPM.mp3"])
        self.assertNotIn(tmp, text)
        self.assertNotIn("konto" + "ordner", text)
        self.assertEqual(_sha(MITGELIEFERT), vorher,
                         "der Test hat die mitgelieferte Demo-Show veraendert")

    def test_mitgelieferte_show_hat_nur_relative_playlist(self):
        with zipfile.ZipFile(MITGELIEFERT) as z:
            show = json.loads(z.read("show.json").decode("utf-8"))
        for t in show.get("playlist") or []:
            p = str(t.get("path", ""))
            self.assertTrue(p.startswith("Musik/"), "Playlist-Pfad nicht neutral")
            self.assertNotIn(":", p)


if __name__ == "__main__":
    unittest.main()
