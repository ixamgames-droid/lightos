"""DEMO-02 — ``tools/build_*.py``-Generatoren bauen headless den VOLLSTAENDIGEN Patch.

Ursache des Bugs (nur Windows):
    Importiert ein Generator ``app_state``/``output_manager`` und ist ein Enttec-Port
    konfiguriert, erzeugt ``get_state()`` einen
    :class:`~src.core.dmx.serial_process.EnttecProcessProxy`, der einen Kindprozess
    per ``multiprocessing`` im ``spawn``-Modus startet. ``spawn`` RE-IMPORTIERT auf
    Windows das Hauptmodul als ``__mp_main__`` — bei einem Generator OHNE
    ``if __name__ == "__main__":``-Guard laeuft der Build-Code ein ZWEITES MAL im
    Kind. Zwei Prozesse bauen die Show auf derselben SQLite-Show-DB; der FLD-FID-
    Guard in ``add_fixture`` vergibt fids neu -> nur ein Teil der Fixtures landet im
    Patch.

Fix (Single-Point): ``tools/_gen_env.py`` setzt beim Import — vor app_state/
    output_manager — ``LIGHTOS_SERIAL_INPROC=1`` + ``LIGHTOS_NO_OUTPUT_THREAD=1``.
    Dann nimmt ``_make_enttec_device`` den In-Prozess-``EnttecPro`` (kein Spawn) und
    der Output-Thread startet nicht -> kein ``__mp_main__``-Re-Import -> kein
    Doppel-Build.

Die Tests sind schnell + deterministisch: KEIN echtes multiprocessing-spawn. Der
End-to-End-Test laeuft den Generator als eigene Datei (genau der Bug-Pfad) in einem
Subprozess, der die Schutzschicht aber bereits aktiv hat.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    # _gen_env / _builder liegen in tools/ (wird beim Datei-Aufruf automatisch
    # vorne in sys.path gelegt; im Test explizit ergaenzen).
    sys.path.insert(0, str(TOOLS))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class GenEnvBootstrapTest(unittest.TestCase):
    """Die Bootstrap-Schicht setzt die spawn-sicheren Schalter beim Import."""

    def test_import_sets_safe_switches(self):
        import _gen_env  # noqa: F401  (Seiteneffekt: setzt os.environ)
        self.assertEqual(os.environ.get("LIGHTOS_SERIAL_INPROC"), "1")
        self.assertEqual(os.environ.get("LIGHTOS_NO_OUTPUT_THREAD"), "1")

    def test_builder_imports_gen_env(self):
        # _builder ist die gemeinsame Boilerplate; ihr Import muss die Schalter
        # ebenfalls (ueber _gen_env) gesetzt lassen -> alle _builder-Generatoren
        # sind ohne Zutun geschuetzt.
        import _builder  # noqa: F401
        self.assertEqual(os.environ.get("LIGHTOS_SERIAL_INPROC"), "1")
        self.assertEqual(os.environ.get("LIGHTOS_NO_OUTPUT_THREAD"), "1")


class NoSpawnPathTest(unittest.TestCase):
    """Mit gesetztem LIGHTOS_SERIAL_INPROC nimmt _make_enttec_device den
    In-Prozess-Pfad und beruehrt den (spawnenden) EnttecProcessProxy NIE."""

    def test_inproc_env_means_no_process_proxy(self):
        import _gen_env  # noqa: F401  (garantiert LIGHTOS_SERIAL_INPROC=1)
        self.assertEqual(os.environ.get("LIGHTOS_SERIAL_INPROC"), "1")

        from src.core.dmx import output_manager as om

        # EnttecPro durch einen Stub ersetzen (kein echter COM-Port noetig) und
        # serial_process.EnttecProcessProxy scharf stellen: WIRD er instanziiert,
        # faellt der Test. So beweisen wir, dass KEIN Spawn-Pfad betreten wird.
        sentinel = object()

        class _StubEnttec:
            def __init__(self, port):
                self.port = port
                self.tag = sentinel

        orig_enttec = om.EnttecPro
        om.EnttecPro = _StubEnttec
        try:
            from src.core.dmx import serial_process as sp

            class _ProxyMustNotBeUsed:
                def __init__(self, *a, **k):  # pragma: no cover - darf nie laufen
                    raise AssertionError(
                        "EnttecProcessProxy wurde im Generator-/Headless-Kontext "
                        "instanziiert -> multiprocessing-spawn waere moeglich "
                        "(DEMO-02 Regression).")

            orig_proxy = sp.EnttecProcessProxy
            sp.EnttecProcessProxy = _ProxyMustNotBeUsed
            try:
                dev = om._make_enttec_device("COM_BOGUS")
            finally:
                sp.EnttecProcessProxy = orig_proxy
        finally:
            om.EnttecPro = orig_enttec

        # In-Prozess-Geraet (Stub), NICHT der Prozess-Proxy.
        self.assertIs(getattr(dev, "tag", None), sentinel)
        self.assertEqual(dev.port, "COM_BOGUS")


class HeadlessGeneratorFullPatchTest(unittest.TestCase):
    """End-to-End: einen guardlosen Generator ALS DATEI (Bug-Pfad) headless bauen
    und die Fixture-Zahl pruefen. Laeuft in einem Subprozess mit aktiver
    Schutzschicht; die erzeugte Show wird frisch geladen und gezaehlt.

    Generator: ``tools/build_test_show.py`` -> 10 Fixtures (6 PARs + 4 Heads).
    """

    GENERATOR = "build_test_show.py"
    SHOW = ROOT / "shows" / "Test_Show_Komplett.lshow"
    EXPECTED_FIXTURES = 10

    def tearDown(self):
        # Den generierten Test-Show-Artefakt NICHT in shows/ liegen lassen. Sonst
        # lintet ihn test_show_lint spaeter mit (Hard-Gate glob-t shows/*.lshow) und
        # koppelt den Lint-Gate an DIESEN Build — der die Fixture-DEFINITIONEN aus der
        # geteilten, NICHT umgelenkten fixtures.db zieht (nur die Show-DB ist pro
        # Prozess isoliert). Baut eine parallele Session zeitgleich an fixtures.db
        # (Reseed/Migration), faengt der Build inkonsistente Profil-Referenzen ein →
        # der geleakte Artefakt lintet rot → spurious rotes Gate (beobachtet
        # 2026-07-18, s. SecondBrain project_test_isolation_show_db_2026_06_21).
        # Aufraeumen macht den Test in sich geschlossen (wie schon die Build-Show-DB);
        # die eigentliche DEMO-02-Zusicherung prueft der Test selbst per Load+Count.
        for p in (ROOT / "shows").glob("Test_Show_Komplett.lshow*"):
            try:
                p.unlink()
            except OSError:
                pass

    def test_file_build_yields_full_patch(self):
        py = sys.executable
        # Pro-Prozess-eindeutige Show-DB (wie conftest) -> keine Kollision mit
        # parallelen Laeufen / der echten App.
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        # Eine eigene, eindeutige Show-DB fuer den Build-Subprozess erzwingen, damit
        # er garantiert leer startet und nichts Fremdes anfasst.
        import tempfile
        dbp = os.path.join(tempfile.gettempdir(),
                           f"lightos_demo02_build_{os.getpid()}.db")
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suffix)
            except OSError:
                pass
        env["LIGHTOS_SHOW_DB"] = dbp
        # Die sicheren Schalter NICHT vorab in env setzen — der Generator selbst
        # (ueber _gen_env) muss sie setzen. So testen wir die Schutzschicht echt.
        env.pop("LIGHTOS_SERIAL_INPROC", None)
        env.pop("LIGHTOS_NO_OUTPUT_THREAD", None)

        proc = subprocess.run(
            [py, str(TOOLS / self.GENERATOR)],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"Generator-Build fehlgeschlagen:\nSTDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}")
        self.assertTrue(self.SHOW.exists(), f"Show nicht erzeugt: {self.SHOW}")

        # Die erzeugte Show in EINEM weiteren, isolierten Subprozess laden und die
        # Fixture-Zahl ausgeben (eigener app_state, eigene DB) -> robust gegen ein
        # evtl. schon initialisiertes Singleton im Test-Interpreter.
        loader = (
            "import os, sys;"
            f"sys.path.insert(0, {str(ROOT)!r});"
            "os.environ['QT_QPA_PLATFORM']='offscreen';"
            "from PySide6.QtWidgets import QApplication;"
            "QApplication.instance() or QApplication([]);"
            "from src.core.show.show_file import load_show;"
            "from src.core.app_state import get_state;"
            f"ok,msg=load_show({str(self.SHOW)!r});"
            "assert ok, msg;"
            "print('FIXTURES', len(get_state().get_patched_fixtures()))"
        )
        load_proc = subprocess.run(
            [py, "-c", loader], cwd=str(ROOT), env=env,
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(
            load_proc.returncode, 0,
            f"Laden der Show fehlgeschlagen:\nSTDOUT:\n{load_proc.stdout}\n"
            f"STDERR:\n{load_proc.stderr}")
        line = [l for l in load_proc.stdout.splitlines() if l.startswith("FIXTURES")]
        self.assertTrue(line, f"Keine Fixture-Zahl ausgegeben:\n{load_proc.stdout}")
        count = int(line[-1].split()[1])
        self.assertEqual(
            count, self.EXPECTED_FIXTURES,
            f"VOLLSTAENDIGER Patch erwartet ({self.EXPECTED_FIXTURES}), "
            f"aber nur {count} Fixtures gebaut (DEMO-02: halber Patch?).")

        # Aufraeumen: die Build-eigene Show-DB.
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suffix)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
