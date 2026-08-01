"""Der Test-Runner darf WebEngine-Segmente nie gleichzeitig starten.

HINTERGRUND (2026-08-01): Zwei parallele Segmente, die je eine three.js-Szene
hochfahren, konkurrieren um WebGL-Kontexte. Eins scheitert dann mit
"THREE.WebGLRenderer: Error creating WebGL context" — isoliert sind dieselben
Dateien gruen. Das faerbte das Gate an wechselnden Dateien rot und drohte, die
Aussagekraft des Merge-Kriteriums zu zerstoeren: wer die Rotfaerbung als
Rauschen abtut, uebersieht den naechsten ECHTEN roten Viz-Test.

``verify_segmented.sh`` hat dafuer zwei Spuren. Dieser Test prueft das
**am laufenden Runner**, nicht am Skripttext: er laesst echte Mini-Testdateien
laufen, die ihre Start- und Endzeit protokollieren, und rechnet nach, ob sich
Intervalle ueberlappen. Ein Test, der nur nach ``QWebEngineView`` im Skript
grept, wuerde jede kaputte Umbau-Variante durchwinken.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "tools" / "verify_segmented.sh"

# Jede Mini-Testdatei schreibt "<name> <start> <ende>" in eine gemeinsame Datei.
# Das Anhaengen einer kurzen Zeile mit O_APPEND ist prozessuebergreifend atomar,
# deshalb braucht es hier kein Sperrfile.
VORLAGE = '''{marker}
import os, time

def test_spur():
    start = time.monotonic()
    time.sleep({schlaf})
    with open({protokoll!r}, "a") as fh:
        fh.write("%s %.4f %.4f\\n" % ({name!r}, start, time.monotonic()))
'''

# Der Marker steht bewusst in einem Docstring statt als echter Import: der
# Runner entscheidet per Textsuche, und ein echter WebEngine-Import wuerde
# diesen Test um Sekunden verlangsamen, ohne etwas zusaetzlich zu pruefen.
MARKER = '"""Diese Datei zaehlt als WebEngine-Segment: QWebEngineView."""'
HARMLOS = '"""Gewoehnliches Segment ohne Szene."""'


def _ueberlappt(a, b):
    """Ueberschneiden sich zwei (start, ende)-Intervalle?"""
    return a[0] < b[1] and b[0] < a[1]


class WebEngineSpurTest(unittest.TestCase):
    @unittest.skipUnless(RUNNER.exists(), "verify_segmented.sh fehlt")
    def test_webengine_segmente_laufen_nie_gleichzeitig(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            protokoll = tmp / "spuren.txt"
            protokoll.write_text("", encoding="utf-8")

            namen = []
            dateien = []
            for i in range(3):
                for art, marker in (("web", MARKER), ("rest", HARMLOS)):
                    name = f"{art}{i}"
                    p = tmp / f"test_{name}.py"
                    p.write_text(
                        VORLAGE.format(marker=marker, schlaf=0.5,
                                       protokoll=str(protokoll), name=name),
                        encoding="utf-8")
                    namen.append(name)
                    dateien.append(str(p))

            umgebung = dict(os.environ)
            umgebung["LIGHTOS_SEG_OUT"] = str(tmp / "out")
            erg = subprocess.run(
                ["bash", str(RUNNER), "-j", "3", *dateien],
                cwd=str(REPO), env=umgebung, capture_output=True,
                text=True, timeout=180)
            self.assertEqual(erg.returncode, 0,
                             f"Runner rot:\n{erg.stdout}\n{erg.stderr}")

            zeiten = {}
            for zeile in protokoll.read_text(encoding="utf-8").splitlines():
                name, start, ende = zeile.split()
                zeiten[name] = (float(start), float(ende))
            self.assertEqual(len(zeiten), len(namen),
                             f"nicht alle Segmente liefen: {sorted(zeiten)}")

            web = sorted(n for n in zeiten if n.startswith("web"))
            for i, a in enumerate(web):
                for b in web[i + 1:]:
                    self.assertFalse(
                        _ueberlappt(zeiten[a], zeiten[b]),
                        f"{a} und {b} liefen gleichzeitig — WebGL-Kontexte "
                        f"konkurrieren wieder: {zeiten[a]} / {zeiten[b]}")

    @unittest.skipUnless(RUNNER.exists(), "verify_segmented.sh fehlt")
    def test_gewoehnliche_segmente_bleiben_parallel(self):
        """Die Serialisierung darf nicht auf den Rest der Suite durchschlagen.

        Ohne diese Gegenprobe waere der Runner auch dann gruen, wenn jemand
        schlicht alles auf -j 1 stellt — die Ursache waere weg, das Gate aber
        um Minuten langsamer.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            protokoll = tmp / "spuren.txt"
            protokoll.write_text("", encoding="utf-8")

            dateien = []
            for i in range(3):
                p = tmp / f"test_rest{i}.py"
                p.write_text(
                    VORLAGE.format(marker=HARMLOS, schlaf=0.8,
                                   protokoll=str(protokoll), name=f"rest{i}"),
                    encoding="utf-8")
                dateien.append(str(p))

            umgebung = dict(os.environ)
            umgebung["LIGHTOS_SEG_OUT"] = str(tmp / "out")
            erg = subprocess.run(
                ["bash", str(RUNNER), "-j", "3", *dateien],
                cwd=str(REPO), env=umgebung, capture_output=True,
                text=True, timeout=180)
            self.assertEqual(erg.returncode, 0,
                             f"Runner rot:\n{erg.stdout}\n{erg.stderr}")

            zeiten = []
            for zeile in protokoll.read_text(encoding="utf-8").splitlines():
                _, start, ende = zeile.split()
                zeiten.append((float(start), float(ende)))
            self.assertEqual(len(zeiten), 3)

            paare = [(a, b) for i, a in enumerate(zeiten) for b in zeiten[i + 1:]
                     if _ueberlappt(a, b)]
            self.assertTrue(paare,
                            "kein Paar lief gleichzeitig — die schnelle Spur "
                            f"ist serialisiert worden: {zeiten}")


# Ein Segment, das den GPU-Kontextverlust nachstellt: es schreibt die beiden
# echten Zeilen aus dem Fehl-Log vom 2026-08-01 und faellt dann um. Bewusst als
# gestellte Ausgabe — den echten Kontextverlust kann kein Test herbeifuehren,
# und darum geht es hier auch nicht: geprueft wird, ob der Runner die Signatur
# ERKENNT und benennt.
KONTEXTVERLUST = '''"""Segment mit GPU-Kontextverlust: QWebEngineView."""

def test_stirbt_am_kontextverlust():
    print("[ERROR:raster_decoder.cc:1141] RasterDecoderImpl: "
          "Context lost during MakeCurrent.")
    print("js: THREE.WebGLRenderer: Error creating WebGL context.")
    assert False, "Szene kam nicht hoch"
'''

ECHTER_FEHLER = '''"""Segment mit einem gewoehnlichen Fehler: QWebEngineView."""

def test_faellt_ehrlich_um():
    assert 1 == 2, "echter Testfehler"
'''


class Xplat17SignaturTest(unittest.TestCase):
    """XPLAT-17: ein roter Viz-Test darf nicht wie Rauschen aussehen.

    Gemessen wurde 1 Ausfall in 6 vollen Laeufen — selten genug, dass niemand
    die Signatur im Kopf hat, haeufig genug, dass sie wiederkommt. Der Runner
    benennt sie deshalb; ROT bleibt sie trotzdem.
    """

    def _runner(self, tmp, dateien):
        umgebung = dict(os.environ)
        umgebung["LIGHTOS_SEG_OUT"] = str(tmp / "out")
        return subprocess.run(
            ["bash", str(RUNNER), "-j", "2", *dateien],
            cwd=str(REPO), env=umgebung, capture_output=True,
            text=True, timeout=180)

    @unittest.skipUnless(RUNNER.exists(), "verify_segmented.sh fehlt")
    def test_kontextverlust_wird_benannt_bleibt_aber_rot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            p = tmp / "test_kontextverlust.py"
            p.write_text(KONTEXTVERLUST, encoding="utf-8")
            erg = self._runner(tmp, [str(p)])

            self.assertNotEqual(
                erg.returncode, 0,
                "Die Signatur darf das Segment NICHT gruen rechnen — sonst "
                "waere sie genau die Wiederholungslogik, die hier nie "
                f"gebaut werden sollte.\n{erg.stdout}")
            self.assertIn("XPLAT-17-Signatur", erg.stdout,
                          f"Ursache nicht benannt:\n{erg.stdout}")
            self.assertIn("test_kontextverlust.py", erg.stdout)

    @unittest.skipUnless(RUNNER.exists(), "verify_segmented.sh fehlt")
    def test_gewoehnlicher_fehler_bekommt_die_signatur_NICHT(self):
        """Die Gegenprobe, an der sich alles entscheidet: waere das Etikett zu
        grosszuegig, haette es genau den Schaden angerichtet, den es verhindern
        soll — ein echter Fehler als bekannter Flake abgestempelt."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            p = tmp / "test_echter_fehler.py"
            p.write_text(ECHTER_FEHLER, encoding="utf-8")
            erg = self._runner(tmp, [str(p)])

            self.assertNotEqual(erg.returncode, 0)
            self.assertNotIn("XPLAT-17-Signatur", erg.stdout,
                             f"echter Fehler falsch etikettiert:\n{erg.stdout}")


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
