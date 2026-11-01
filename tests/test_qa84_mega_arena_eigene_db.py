"""QA-84: der Mega-Arena-Generator benutzt je Lauf eine EIGENE Show-DB.

Befund (DOC-60): ``tools/build_mega_arena_2026.py`` setzte ``LIGHTOS_SHOW_DB``
selbst auf die FESTE Datei ``<tmp>/lightos_mega_arena_build.db`` — zwei
gleichzeitige Laeufe (segmentiertes Gate, zwei Sitzungen) teilten sie sich
("database is locked"), und die Datei blieb nach dem Lauf liegen.

Seit der Werkzeug-Sandbox (TOOL-27) bekommt jeder Generator ueber ``_gen_env``
ohnehin einen eigenen Wegwerf-Ordner (``mkdtemp``) mit ``current_show.db``,
der am Prozessende geloescht wird. Die feste Vorgabe des Generators stand
davor und gewann (eine Vorgabe im Temp-Bereich gilt als bewusst).

Der Test startet den Generator ZWEIMAL GLEICHZEITIG ohne ``LIGHTOS_SHOW_DB``
(anders als ``test_tool7_global_bus_pruefungen.py``, der sie vorgibt) und mit
einem eigenen Temp-Bereich (``TMPDIR``/``TEMP``/``TMP``): beide Laeufe
muessen durchlaufen, und danach darf dort keine Show-DB liegen bleiben.
"""
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_mega_arena_2026.py")
FESTE_DB = "lightos_mega_arena_build.db"


def _db_reste(ordner: str) -> list:
    """Alle SQLite-Dateien (samt -wal/-shm/-journal) unter ``ordner``."""
    reste = []
    for wurzel, _ordner, dateien in os.walk(ordner):
        for name in dateien:
            if ".db" in name:
                reste.append(os.path.relpath(os.path.join(wurzel, name), ordner))
    return sorted(reste)


class MegaArenaEigeneShowDbJeLauf(unittest.TestCase):

    def test_zwei_gleichzeitige_laeufe_ohne_vorgabe(self):
        with tempfile.TemporaryDirectory(prefix="lightos_qa84_") as tmp:
            eigener_temp = os.path.join(tmp, "temp")
            os.mkdir(eigener_temp)
            laeufe = []
            for nr in (1, 2):
                ziel = os.path.join(tmp, f"lauf{nr}", "Mega_Arena_2026.lshow")
                musik = os.path.join(tmp, f"lauf{nr}", "musik")
                os.makedirs(musik)
                env = dict(os.environ)
                env.pop("LIGHTOS_SHOW_DB", None)   # der Generator sorgt selbst
                env.update({
                    "TMPDIR": eigener_temp, "TEMP": eigener_temp, "TMP": eigener_temp,
                    "LIGHTOS_GEN_OUT": ziel,
                    "LIGHTOS_MEGA_MUSIC_DIR": musik,   # leer -> Platzhalter-Playlist
                    "QT_QPA_PLATFORM": "offscreen",
                    "PYTHONIOENCODING": "utf-8",
                })
                proz = subprocess.Popen(
                    [sys.executable, GENERATOR], cwd=REPO, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace")
                laeufe.append((proz, ziel))
            for proz, ziel in laeufe:
                try:
                    ausgabe, _ = proz.communicate(timeout=300)
                except subprocess.TimeoutExpired:
                    proz.kill()
                    ausgabe, _ = proz.communicate()
                    self.fail(f"Generator haengt:\n{ausgabe[-3000:]}")
                self.assertNotIn("database is locked", ausgabe)
                self.assertEqual(proz.returncode, 0,
                                 f"Generator endete mit rc={proz.returncode}:\n"
                                 f"{ausgabe[-3000:]}")
                self.assertIn("FERTIG", ausgabe)
                self.assertTrue(os.path.isfile(ziel), "LIGHTOS_GEN_OUT nicht beachtet")
            self.assertFalse(os.path.exists(os.path.join(eigener_temp, FESTE_DB)),
                             "feste, geteilte Show-DB im Temp-Bereich angelegt")
            self.assertEqual(_db_reste(eigener_temp), [],
                             "Show-DB des Laufs blieb im Temp-Bereich liegen")


if __name__ == "__main__":
    unittest.main()
