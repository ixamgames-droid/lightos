"""PROC-07: zwei Werkzeug-Befunde, beide gemessen.

**XPLAT-25 — vier Werkzeuge waren auf Linux tot.** `capture_*_tempo_guide.py`,
`render_apc_pages.py` und `render_neue_demo_pages.py` erzwangen die Qt-Plattform
`"windows"`. Das ist auf Windows richtig (ein Capture braucht ein ECHT
gerendertes Fenster — offscreen liefert bei QtWebEngine schwarze Bilder), auf
Linux heisst dieselbe Plattform aber `xcb`. Gemessen: `rc=134`,
`qt.qpa.plugin: Could not find the Qt platform plugin "windows"`.

**PROC-07 — `session_claim.py list` druckte die ganze Blocker-Historie.**
Der Aufruf steht als Schritt 2 im Ablauf JEDES Items (`AGENTS.md`,
`COORDINATION.md`); 99 % seiner Ausgabe waren Blockertext (gemessen 11.516 von
11.637 Bytes). Wer ihn je Runde ganz liest, zahlt ihn je Runde.
"""
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"


class QtPlattformIstPortabelTest(unittest.TestCase):
    """Kein Werkzeug darf eine FREMDE Qt-Plattform fest verdrahten.

    Der Waechter ist bewusst breit: er verbietet nicht das Erzwingen (das ist
    fuer Captures noetig), sondern nur das Erzwingen eines Namens, den es auf
    dem laufenden System gar nicht gibt.
    """

    # Plattform-Plugins, die jeweils NUR auf einem Betriebssystem existieren.
    FREMD = {"windows": "nt", "cocoa": "posix-darwin", "xcb": "posix-linux",
             "wayland": "posix-linux"}
    ZUWEISUNG = re.compile(
        r"""QT_QPA_PLATFORM["']\s*\]?\s*(?:=|,)\s*["'](\w+)["']""")

    def test_keine_fest_verdrahtete_fremdplattform(self):
        treffer = []
        for pfad in sorted(TOOLS.glob("*.py")):
            text = pfad.read_text(encoding="utf-8", errors="replace")
            for zeile_nr, zeile in enumerate(text.splitlines(), start=1):
                if "QT_QPA_PLATFORM" not in zeile or zeile.lstrip().startswith("#"):
                    continue
                m = self.ZUWEISUNG.search(zeile)
                if not m:
                    continue
                plattform = m.group(1)
                if plattform not in self.FREMD:
                    continue          # offscreen o. Ae. — plattformneutral, ok
                # Erzwungen ist in Ordnung, WENN es von os.name/sys.platform abhaengt.
                if "os.name" in zeile or "sys.platform" in zeile:
                    continue
                treffer.append(f"{pfad.name}:{zeile_nr}  {zeile.strip()}")

        self.assertEqual(
            treffer, [],
            "Fest verdrahtete Qt-Plattform — das Werkzeug stirbt auf jedem "
            "anderen Betriebssystem mit rc=134:\n  " + "\n  ".join(treffer))

    def test_die_vier_reparierten_waehlen_nach_betriebssystem(self):
        """Positivkontrolle: sie erzwingen weiterhin eine NATIVE Plattform —
        ein blosses ``setdefault("offscreen")`` waere die falsche Reparatur
        (schwarze Bilder statt Absturz ist keine Verbesserung)."""
        for name in ("capture_test123_tempo_guide.py",
                     "capture_hochzeit_tempo_guide.py",
                     "render_apc_pages.py",
                     "render_neue_demo_pages.py"):
            with self.subTest(werkzeug=name):
                text = (TOOLS / name).read_text(encoding="utf-8")
                self.assertIn("QT_QPA_PLATFORM", text)
                self.assertRegex(
                    text,
                    r'QT_QPA_PLATFORM"\]\s*=\s*"windows"\s+if\s+os\.name\s*==\s*"nt"\s+else\s+"xcb"',
                    f"{name} waehlt die Plattform nicht mehr nach Betriebssystem")


class BlockerlisteIstBegrenztTest(unittest.TestCase):
    """``session_claim.py list`` zeigt nur die juengsten Blocker — sagt aber,
    dass es kuerzt, und bleibt ueber ``--blocker -1`` verlustfrei erreichbar."""

    def _ausgabe(self, n, anzahl_blocker=22):
        import io
        import contextlib
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_sc", TOOLS / "session_claim.py")
        sc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sc)

        blocker = [f"2026-09-{i:02d}T10:00Z (A) Blockertext Nummer {i} " + "x" * 300
                   for i in range(1, anzahl_blocker + 1)]
        sc.lade_tafel = lambda repo: ({"claims": [], "blocker": blocker}, None)

        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            sc.cmd_list(SimpleNamespace(blocker=n), str(REPO))
        return puffer.getvalue(), blocker

    def test_vorgabe_zeigt_nur_die_juengsten_und_sagt_es(self):
        aus, blocker = self._ausgabe(5)
        self.assertIn("letzte 5 von 22", aus,
                      "Die Kuerzung wird verschwiegen — dann haelt eine Sitzung "
                      "die Kurzfassung fuer die ganze Tafel")
        self.assertIn("--blocker -1", aus, "Der Weg zur Vollansicht fehlt")
        self.assertIn(blocker[-1], aus, "Der juengste Blocker fehlt")
        self.assertNotIn(blocker[0], aus, "Es wird gar nicht gekuerzt")

    def test_gezeigte_blocker_werden_nicht_angeschnitten(self):
        """Bewusste Entscheidung: lieber WENIGER Blocker als angeschnittene.

        Gerade der juengste ist meist die Uebergabe der anderen Sitzung — ihn
        auf 240 Zeichen zu kappen spart 1,6 kB und kostet genau die Information,
        fuer die man ihn liest.
        """
        aus, blocker = self._ausgabe(5)
        for b in blocker[-5:]:
            self.assertIn(b, aus, "Ein gezeigter Blocker ist gekuerzt")

    def test_minus_eins_ist_verlustfrei(self):
        aus, blocker = self._ausgabe(-1)
        for b in blocker:
            self.assertIn(b, aus)
        self.assertNotIn("letzte", aus, "Bei -1 darf keine Kuerzungs-Zeile stehen")

    def test_null_blendet_aus_nennt_aber_die_zahl(self):
        aus, _ = self._ausgabe(0)
        self.assertIn("22 Blocker ausgeblendet", aus)
        self.assertIn("--blocker -1", aus)

    def test_kuerzung_spart_wirklich(self):
        """Die Ersparnis ist der ganze Zweck — also wird sie gemessen."""
        kurz, _ = self._ausgabe(5)
        voll, _ = self._ausgabe(-1)
        self.assertLess(len(kurz) * 2, len(voll),
                        f"Kaum Ersparnis: {len(kurz)} B statt {len(voll)} B")


if __name__ == "__main__":
    unittest.main()
