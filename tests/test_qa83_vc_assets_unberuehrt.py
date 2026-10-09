"""QA-83: Wer schreibt ohne Sandbox nach ``vc_assets/``?

Befund (DOC-59, Nebenfund c): waehrend eines Bildlaufs aenderten sich zwoelf
Dateien in ``vc_assets/`` des echten Datenordners mit derselben mtime; Verdacht:
ein Test ruft ``vc_gallery.import_to_cache`` ohne umgelenkten Datenordner.

Gemessen 2026-10-08 auf dem Windows-PC (Sitzung B):

* Im echten ``%APPDATA%/LightOS/vc_assets`` liegen genau zwoelf Dateien, alle
  mit derselben mtime (04.10. 19:52:42) — und es sind genau die zwoelf in
  ``shows/Mega_Arena_2026.lshow`` eingebetteten Bilder. ``recent.json`` nennt
  eine Kopie der Mega Arena, die App lief (Lebenszeichen 20:18): die ECHTE App
  hat sie beim Laden entpackt. Das ist ihr Cache, kein Leck.
* Ein voller Gate-Lauf (839 Dateien) hat den Ordner nicht angefasst — die
  Suite ist ueber ``conftest.py`` (APPDATA + XDG_DATA_HOME, QA-60) dicht.
* Undicht sind dagegen die GENERATOREN (``tools/build_*.py``):
  ``tools/_gen_env.py`` lenkt fuer sie die Show-DB um (STAB-CURSHOW: Generator-
  Laeufe duerfen den echten Show-Zustand nicht anfassen), den Asset-Cache aber
  nicht. ``build_mega_arena_2026.py`` importiert Galerie-Bilder per
  ``import_to_cache`` — ein Lauf von Hand schrieb sie in den echten Cache.

Dieser Waechter haelt beides fest: die Suite (Laden einer Show mit
eingebetteten Bildern, Galerie-Import) laesst den echten Ordner unveraendert,
und ein Generator schreibt seinen Cache in einen Wegwerf-Ordner.
"""
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _echter_cache() -> str:
    """Wie tests/test_qa60_datenordner_unberuehrt.py: aus HOME NACHGEBAUT, nicht
    aus ``app_data_dir()`` (das zeigt in der Suite absichtlich in den Sandkasten)."""
    plat = sys.platform
    if plat == "win32":
        basis = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    else:
        basis = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(basis, "LightOS", "vc_assets")


def _stand(ordner: str) -> dict:
    if not os.path.isdir(ordner):
        return {}
    out = {}
    for name in os.listdir(ordner):
        st = os.stat(os.path.join(ordner, name))
        out[name] = (st.st_mtime_ns, st.st_size)
    return out


def _real(p: str) -> str:
    return os.path.normcase(os.path.realpath(p))


class SuiteLaesstDenEchtenCacheInRuheTest(unittest.TestCase):

    def test_cache_der_suite_liegt_nicht_im_echten_ordner(self):
        from src.core.show import vc_assets
        benutzt = _real(vc_assets.cache_dir())
        echt = _real(_echter_cache())
        self.assertFalse(benutzt == echt or benutzt.startswith(echt + os.sep),
                         f"vc_assets.cache_dir() zeigt in den echten Ordner: {benutzt}")

    def test_show_mit_bildern_laden_und_galerie_import(self):
        """Die beiden Wege, die Dateien in den Cache legen: Galerie-Bild
        importieren und eingebettete Bilder beim Laden entpacken. Die Show mit
        eingebettetem Bild entsteht hier (die Mega Arena ist nicht eingecheckt)."""
        import shutil
        import tempfile
        echt = _echter_cache()
        vorher = _stand(echt)
        from src.core.app_state import get_state
        from src.core.show import vc_assets, vc_gallery
        from src.core.show.show_file import load_show, reset_show, save_show
        tmp = tempfile.mkdtemp(prefix="qa83_show_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pfad = os.path.join(tmp, "bild.lshow")
        try:
            reset_show()
            key = vc_gallery.import_to_cache(vc_gallery.names()[0])
            get_state()._vc_layout = {"widgets": [
                {"type": "VCButton", "caption": "Bild", "x": 0, "y": 0,
                 "w": 80, "h": 40, "bg_image": key}]}
            save_show(pfad)
            os.remove(os.path.join(vc_assets.cache_dir(), key))   # Laden muss entpacken
            ok, msg = load_show(pfad)
            self.assertTrue(ok, msg)
            self.assertTrue(os.path.isfile(os.path.join(vc_assets.cache_dir(), key)),
                            "Testaufbau: das eingebettete Bild wurde nicht entpackt")
        finally:
            reset_show()
        self.assertEqual(vorher, _stand(echt),
                         "die Suite hat den echten vc_assets-Ordner veraendert")


_GENERATOR_PROBE = r"""
import os, sys
sys.path.insert(0, sys.argv[1])          # tools/  -> _gen_env
sys.path.insert(0, sys.argv[2])          # Repo    -> src
import _gen_env  # noqa: F401
from src.core.show import vc_assets
print("CACHE", vc_assets.cache_dir())
"""


class GeneratorCacheTest(unittest.TestCase):
    """Ein Generator, gestartet wie von Hand: APPDATA/XDG zeigen auf den
    „echten“ Datenordner (hier ein Stellvertreter)."""

    def test_generator_schreibt_nicht_in_den_datenordner(self):
        import shutil
        import tempfile
        echt = tempfile.mkdtemp(prefix="qa83_echter_datenordner_")
        self.addCleanup(shutil.rmtree, echt, ignore_errors=True)
        env = dict(os.environ, APPDATA=echt, XDG_DATA_HOME=echt)
        env.pop("LIGHTOS_VC_ASSETS_DIR", None)
        r = subprocess.run(
            [sys.executable, "-c", _GENERATOR_PROBE, os.path.join(REPO, "tools"), REPO],
            capture_output=True, text=True, timeout=60, cwd=REPO, env=env)
        self.assertEqual(0, r.returncode, r.stderr[-2000:])
        zeile = next(z for z in r.stdout.splitlines() if z.startswith("CACHE "))
        cache = _real(zeile[len("CACHE "):])
        self.assertFalse(cache.startswith(_real(echt) + os.sep),
                         f"Generator-Lauf schreibt in den Datenordner des Nutzers: {cache}")
        # Ausdruecklich gesetzt gewinnt (wie bei LIGHTOS_SHOW_DB).
        eigen = os.path.join(echt, "eigener_cache")
        r = subprocess.run(
            [sys.executable, "-c", _GENERATOR_PROBE, os.path.join(REPO, "tools"), REPO],
            capture_output=True, text=True, timeout=60, cwd=REPO,
            env=dict(env, LIGHTOS_VC_ASSETS_DIR=eigen))
        self.assertEqual(0, r.returncode, r.stderr[-2000:])
        self.assertIn(f"CACHE {eigen}", r.stdout)


if __name__ == "__main__":
    unittest.main()
