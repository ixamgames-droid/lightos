"""XPLAT-44: Nutzerdaten im App-Datenordner + einmalige Uebernahme aus ``data/``.

Vorher lagen ``current_show.db``, ``universes.json``, ``midi_mappings.json``,
``channel_groups.json`` und ``channel_modifiers.json`` relativ zum
ARBEITSVERZEICHNIS. Ein Start aus einem fremden Ordner schrieb ein zweites
``data/`` neben den Aufrufer. Hier festgehalten:

* jede dieser Dateien loest in den App-Datenordner auf — auch aus einem
  fremden Arbeitsverzeichnis (Subprozess, Ende zu Ende);
* die Uebernahme kopiert genau einmal, verschiebt nichts, ueberschreibt nichts,
  meldet Konflikte, vertraegt fehlende Quellen/Rechte, nimmt die SQLite-WAL mit
  und laesst eine offene DB in Ruhe;
* die Kanal-Modifier werden beim Start wieder geladen (Nebenbefund #863).

Alle Proben laufen in ``tempfile``-Ordnern; der echte Datenordner und das
echte ``data/`` werden nie beruehrt.
"""
from __future__ import annotations

import json
import ntpath
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from src.core import datenumzug as dz
from src.core import paths

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NAMEN = list(paths.USER_DATA_FILES)


def _stand(ordner: str) -> dict:
    """Inhalt + mtime aller Dateien eines Ordners (fuer "unangetastet")."""
    aus = {}
    for wurzel, _d, dateien in os.walk(ordner):
        for n in dateien:
            p = os.path.join(wurzel, n)
            with open(p, "rb") as f:
                aus[os.path.relpath(p, ordner)] = (f.read(), os.stat(p).st_mtime_ns)
    return aus


class _TmpFall(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="xplat44_")
        self.basis = self._td.name
        self.ziel = os.path.join(self.basis, "app", "LightOS")
        self.alt = os.path.join(self.basis, "repo", "data")
        os.makedirs(self.alt)
        self.log: list[str] = []
        self.addCleanup(self._td.cleanup)
        # Ein von aussen gesetzter Abschalter darf die Tests nicht leerlaufen lassen.
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop(dz.ENV_AUS, None)
        for var in paths.USER_DATA_FILES.values():
            if var:
                os.environ.pop(var, None)

    def schreibe(self, ordner, name, inhalt):
        os.makedirs(ordner, exist_ok=True)
        with open(os.path.join(ordner, name), "w", encoding="utf-8") as f:
            f.write(inhalt)

    def lauf(self, quellen=None, **kw):
        kw.setdefault("in_benutzung", lambda p: False)
        return dz.uebernehme_alte_daten(
            self.ziel, [self.alt] if quellen is None else quellen,
            log=self.log.append, **kw)


# ── (1) zentrale Pfade ─────────────────────────────────────────────────────────

class ZentralePfade(unittest.TestCase):

    def test_jede_nutzerdatei_liegt_im_app_ordner(self):
        with mock.patch.dict(os.environ):
            for var in ("LIGHTOS_SHOW_DB", "LIGHTOS_UNIVERSES_JSON"):
                os.environ.pop(var, None)
            for n in _NAMEN:
                with self.subTest(datei=n):
                    self.assertEqual(paths.user_data_file(n),
                                     os.path.join(paths.app_data_dir(), n))

    def test_override_hat_vorrang(self):
        with mock.patch.dict(os.environ, LIGHTOS_SHOW_DB="/x/show.db",
                             LIGHTOS_UNIVERSES_JSON="/x/u.json"):
            self.assertEqual(paths.user_data_file("current_show.db"), "/x/show.db")
            self.assertEqual(paths.user_data_file("universes.json"), "/x/u.json")

    def test_unbekannter_name_ist_ein_fehler(self):
        with self.assertRaises(ValueError):
            paths.user_data_file("snapshots.json")

    def test_mitgelieferte_repo_daten_sind_keine_nutzerdaten(self):
        """Controller-Vorlagen bleiben im Repo (keine Uebernahme, kein Umzug)."""
        from src.core.controllers import controller_library as cl
        self.assertEqual(os.path.normcase(cl._BUILTIN_DIR),
                         os.path.normcase(os.path.join(_REPO, "data", "controller_library")))
        self.assertNotIn("controller_library", " ".join(_NAMEN))

    def test_kein_cwd_relativer_data_pfad_mehr_in_src(self):
        """Waechter: keine der fuenf Dateien darf wieder an ``data/`` ab CWD haengen."""
        muster = re.compile(
            r"""["']data[/\\]|join\(\s*["']data["']\s*,\s*["'](%s)""" %
            "|".join(re.escape(n) for n in _NAMEN))
        funde = []
        for wurzel, _d, dateien in os.walk(os.path.join(_REPO, "src")):
            for n in dateien:
                if not n.endswith(".py"):
                    continue
                p = os.path.join(wurzel, n)
                with open(p, encoding="utf-8") as f:
                    for i, zeile in enumerate(f, 1):
                        code = zeile.split("#", 1)[0]
                        if muster.search(code) and "``" not in zeile:
                            funde.append(f"{os.path.relpath(p, _REPO)}:{i}: {zeile.strip()}")
        self.assertEqual(funde, [])


_PROBE = r"""
import json, os, sys
sys.path.insert(0, sys.argv[1])
from src.core import app_state, paths
from src.ui.widgets import output_config
from src.ui.views import channel_groups_view
from src.core.engine.channel_modifier import ChannelModifierManager
from src.core.midi.midi_mapper import MidiMapper
ChannelModifierManager().save(paths.user_data_file("channel_modifiers.json"))
mm = MidiMapper(None)
ok = mm.save(paths.user_data_file("midi_mappings.json"))
print(json.dumps({
    "show_db": os.path.abspath(app_state.SHOW_DB_PATH),
    "universes": os.path.abspath(output_config._UNIV_CONFIG_PATH),
    "gruppen": os.path.abspath(channel_groups_view._PERSIST_PATH),
    "midi_ok": ok,
}))
"""


class StartAusFremdemOrdner(unittest.TestCase):
    """Ende zu Ende: ein Prozess mit fremdem CWD loest alles in den App-Ordner
    auf und legt im CWD kein ``data/`` an (vorher: rot, ``data/`` im CWD)."""

    def test_fremdes_cwd_schreibt_in_den_app_ordner(self):
        with tempfile.TemporaryDirectory(prefix="xplat44_cwd_") as td:
            fremd = os.path.join(td, "irgendwo anders")
            xdg = os.path.join(td, "xdg")
            os.makedirs(fremd)
            env = dict(os.environ, XDG_DATA_HOME=xdg, APPDATA=xdg,
                       HOME=os.path.join(td, "home"),
                       QT_QPA_PLATFORM="offscreen")
            for var in ("LIGHTOS_SHOW_DB", "LIGHTOS_UNIVERSES_JSON"):
                env.pop(var, None)
            r = subprocess.run([sys.executable, "-c", _PROBE, _REPO], cwd=fremd,
                               env=env, capture_output=True, text=True, timeout=180)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            erg = json.loads(r.stdout.strip().splitlines()[-1])
            app = os.path.join(xdg, "LightOS")
            for schluessel, name in (("show_db", "current_show.db"),
                                     ("universes", "universes.json"),
                                     ("gruppen", "channel_groups.json")):
                self.assertEqual(os.path.realpath(erg[schluessel]),
                                 os.path.realpath(os.path.join(app, name)), schluessel)
            self.assertTrue(erg["midi_ok"])
            self.assertTrue(os.path.isfile(os.path.join(app, "midi_mappings.json")))
            self.assertTrue(os.path.isfile(os.path.join(app, "channel_modifiers.json")))
            self.assertFalse(os.path.exists(os.path.join(fremd, "data")),
                             "im fremden Arbeitsverzeichnis entstand ein data/")


_PROBE_STATE = r"""
import os, sys
sys.path.insert(0, sys.argv[1])
from src.core import datenumzug as dz
if len(sys.argv) > 2:
    dz._REPO_ROOT = sys.argv[2]          # Quelle = Wegwerf-"Repo", nie das echte
from src.core.app_state import get_state
get_state()
sys.stdout.flush()
os._exit(0)
"""


class GetStateZuerst(unittest.TestCase):
    """Befund 1 Ende zu Ende mit der ECHTEN Show-DB-Anlage von ``get_state()``."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="xplat44_gs_")
        self.addCleanup(self._td.cleanup)
        td = self._td.name
        self.repo = os.path.join(td, "repo")
        self.alt = os.path.join(self.repo, "data")
        self.cwd = os.path.join(td, "cwd")
        self.xdg = os.path.join(td, "xdg")
        self.app = os.path.join(self.xdg, "LightOS")
        os.makedirs(self.alt)
        os.makedirs(self.cwd)
        self.env = dict(os.environ, XDG_DATA_HOME=self.xdg, APPDATA=self.xdg,
                        HOME=os.path.join(td, "home"), QT_QPA_PLATFORM="offscreen",
                        LIGHTOS_NO_OUTPUT_THREAD="1", LIGHTOS_NO_AUDIO_AUTOSTART="1")
        for var in ("LIGHTOS_SHOW_DB", "LIGHTOS_UNIVERSES_JSON"):
            self.env.pop(var, None)
        # Quelle: eine von der App angelegte Show-DB mit einer Gruppe.
        self._probe(dict(self.env, LIGHTOS_NO_DATENUMZUG="1",
                         LIGHTOS_SHOW_DB=os.path.join(self.alt, "current_show.db")))
        con = sqlite3.connect(os.path.join(self.alt, "current_show.db"))
        con.execute("insert into fixture_groups(name, cols, rows, positions_json, "
                    "folder) values ('Alt', 1, 1, '{}', '')")
        con.commit()
        con.close()

    def _probe(self, env, *extra):
        r = subprocess.run([sys.executable, "-c", _PROBE_STATE, _REPO, *extra],
                           cwd=self.cwd, env=env, capture_output=True, text=True,
                           timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])

    def _gruppen(self):
        con = sqlite3.connect(os.path.join(self.app, "current_show.db"))
        try:
            return [n for (n,) in con.execute("select name from fixture_groups")]
        finally:
            con.close()

    def test_werkzeug_mit_get_state_uebernimmt_zuerst(self):
        env = dict(self.env)
        env.pop(dz.ENV_AUS, None)
        self._probe(env, self.repo)
        self.assertEqual(self._gruppen(), ["Alt"])

    def test_erst_get_state_ohne_uebernahme_dann_uebernahme(self):
        """Der Review-Fall: ein Start ohne Uebernahme (z. B. aus einem
        Worktree) legt die leere DB an; die spaetere Uebernahme holt die Show
        trotzdem."""
        self._probe(dict(self.env, LIGHTOS_NO_DATENUMZUG="1"))
        self.assertEqual(self._gruppen(), [])
        with mock.patch.dict(os.environ):
            os.environ.pop(dz.ENV_AUS, None)
            os.environ.pop("LIGHTOS_SHOW_DB", None)
            erg = dz.uebernehme_alte_daten(self.app, [self.alt],
                                           dateien=["current_show.db"],
                                           log=lambda m: None,
                                           in_benutzung=lambda p: False)
        self.assertEqual(erg.konflikte, [])
        self.assertEqual([n for n, _ in erg.kopiert], ["current_show.db"])
        self.assertEqual(self._gruppen(), ["Alt"])
        self.assertTrue(os.path.exists(
            os.path.join(self.app, "current_show.db" + dz.SICHERUNG)))


# ── (2) Uebernahme ────────────────────────────────────────────────────────────

class Uebernahme(_TmpFall):

    def _alles_anlegen(self):
        for n in _NAMEN:
            if n.endswith(".json"):
                self.schreibe(self.alt, n, json.dumps({"alt": n}))
        con = sqlite3.connect(os.path.join(self.alt, "current_show.db"))
        con.execute("create table t(x)")
        con.execute("insert into t values (42)")
        con.commit()
        con.close()

    def test_kopiert_genau_einmal_und_verschiebt_nichts(self):
        self._alles_anlegen()
        vorher = _stand(self.alt)
        erg = self.lauf()
        self.assertEqual(sorted(n for n, _ in erg.kopiert), sorted(_NAMEN))
        for n in _NAMEN:
            with open(os.path.join(self.alt, n), "rb") as a, \
                    open(os.path.join(self.ziel, n), "rb") as z:
                self.assertEqual(a.read(), z.read(), n)
        self.assertEqual(_stand(self.alt), vorher, "der alte Stand wurde veraendert")
        self.assertTrue(os.path.isfile(os.path.join(self.ziel, dz.MARKER_NAME)))
        self.assertFalse([n for n in os.listdir(self.ziel) if n.endswith("-tmp")])

        # Zweiter Lauf: nichts mehr.
        erg2 = self.lauf()
        self.assertEqual(erg2.kopiert, [])
        self.assertEqual(erg2.uebersprungen, "bereits erledigt")

    def test_bewusst_geloeschte_datei_kommt_nicht_zurueck(self):
        self._alles_anlegen()
        self.lauf()
        os.remove(os.path.join(self.ziel, "midi_mappings.json"))
        self.lauf()
        self.assertFalse(os.path.exists(os.path.join(self.ziel, "midi_mappings.json")),
                         "Marker greift nicht — die geloeschte Datei ist wieder da")

    def test_konflikt_app_ordner_gewinnt(self):
        self._alles_anlegen()
        self.schreibe(self.ziel, "universes.json", '["neu"]')
        vorher = _stand(self.alt)
        erg = self.lauf()
        with open(os.path.join(self.ziel, "universes.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), '["neu"]')
        self.assertIn("universes.json", [n for n, _ in erg.konflikte])
        self.assertNotIn("universes.json", [n for n, _ in erg.kopiert])
        self.assertEqual(_stand(self.alt), vorher)
        self.assertTrue(any("universes.json" in z and "unangetastet" in z
                            for z in self.log), self.log)

    def test_leeres_json_ziel_wird_ersetzt(self):
        self.schreibe(self.alt, "midi_mappings.json", '[{"cc": 1}]')
        self.schreibe(self.ziel, "midi_mappings.json", "[]")
        erg = self.lauf()
        self.assertEqual([n for n, _ in erg.kopiert], ["midi_mappings.json"])
        with open(os.path.join(self.ziel, "midi_mappings.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), '[{"cc": 1}]')
        with open(os.path.join(self.ziel, "midi_mappings.json" + dz.SICHERUNG),
                  encoding="utf-8") as f:
            self.assertEqual(f.read(), "[]")

    def test_konflikt_bleibt_offen_bis_er_gemeldet_ist(self):
        """Befund 1: ein Konflikt wird nicht stillschweigend erledigt — erst
        die sichtbare Meldung (main.py) quittiert ihn."""
        self._alles_anlegen()
        self.schreibe(self.ziel, "universes.json", '["neu"]')
        erg = self.lauf()
        self.assertEqual([n for n, _ in erg.konflikte], ["universes.json"])
        erg2 = self.lauf()
        self.assertEqual([n for n, _ in erg2.konflikte], ["universes.json"])
        self.assertEqual(erg2.kopiert, [], "schon Kopiertes kam doppelt")
        dz.quittiere_konflikte(erg2, log=self.log.append)
        erg3 = self.lauf()
        self.assertEqual(erg3.uebersprungen, "bereits erledigt")

    def test_override_kopiert_nicht_in_den_ungelesenen_app_ordner(self):
        """Befund 5: bei gesetztem LIGHTOS_UNIVERSES_JSON nicht kopieren, aber
        fuer einen Start ohne Override offen lassen."""
        self.schreibe(self.alt, "universes.json", '["alt"]')
        os.environ["LIGHTOS_UNIVERSES_JSON"] = os.path.join(self.basis, "x.json")
        erg = self.lauf()
        self.assertEqual(erg.kopiert, [])
        self.assertFalse(os.path.exists(os.path.join(self.ziel, "universes.json")))
        del os.environ["LIGHTOS_UNIVERSES_JSON"]
        erg2 = self.lauf()
        self.assertEqual([n for n, _ in erg2.kopiert], ["universes.json"])

    def test_fehlende_quelle(self):
        erg = self.lauf([os.path.join(self.basis, "gibt", "es", "nicht")])
        self.assertEqual((erg.kopiert, erg.konflikte, erg.offen), ([], [], []))
        self.assertTrue(os.path.isfile(os.path.join(self.ziel, dz.MARKER_NAME)))

    def test_leere_quelle_schaltet_spaetere_echte_quelle_nicht_ab(self):
        """Erster Start aus einem fremden Ordner (leeres data/) darf die
        Uebernahme aus dem Programmordner nicht fuer immer erledigen."""
        leer = os.path.join(self.basis, "leer", "data")
        os.makedirs(leer)
        self.lauf([leer])
        self._alles_anlegen()
        erg = self.lauf([leer, self.alt])
        self.assertEqual(sorted(n for n, _ in erg.kopiert), sorted(_NAMEN))

    def test_repo_vor_cwd_und_keine_dubletten(self):
        cwd = os.path.join(self.basis, "cwd")
        q = dz.alte_quellen(cwd=cwd, repo_root=os.path.join(self.basis, "repo"))
        self.assertEqual(q, [self.alt, os.path.join(cwd, "data")])
        q2 = dz.alte_quellen(cwd=os.path.join(self.basis, "repo"),
                             repo_root=os.path.join(self.basis, "repo"))
        self.assertEqual(q2, [self.alt])

    def test_windows_pfade_gleich_trotz_schreibweise(self):
        """``C:\\LightOS`` und ``c:\\lightos`` sind auf Windows derselbe Ordner."""
        with mock.patch.object(dz.os, "path", ntpath), \
                mock.patch.object(ntpath, "realpath", lambda p: p):
            q = dz.alte_quellen(cwd="C:\\Programme\\LightOS",
                                repo_root="c:\\programme\\lightos")
        self.assertEqual(len(q), 1, q)
        self.assertEqual(q[0], "c:\\programme\\lightos\\data")

    def test_sonderzeichen_im_pfad(self):
        self.alt = os.path.join(self.basis, "Lichtö Show (alt) & #1", "data")
        self.ziel = os.path.join(self.basis, "App Daten ü", "LightOS")
        self.schreibe(self.alt, "channel_groups.json", "[]")
        erg = self.lauf()
        self.assertEqual([n for n, _ in erg.kopiert], ["channel_groups.json"])
        self.assertTrue(os.path.isfile(os.path.join(self.ziel, "channel_groups.json")))

    def test_marker_kaputt_ueberschreibt_trotzdem_nichts(self):
        self._alles_anlegen()
        self.lauf()
        self.schreibe(self.ziel, "midi_mappings.json", "[1]")
        self.schreibe(self.ziel, dz.MARKER_NAME, "{kaputt")
        erg = self.lauf()
        self.assertEqual(erg.kopiert, [])
        with open(os.path.join(self.ziel, "midi_mappings.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "[1]")

    def test_abschalter(self):
        self._alles_anlegen()
        os.environ[dz.ENV_AUS] = "1"
        erg = self.lauf()
        self.assertEqual(erg.kopiert, [])
        self.assertFalse(os.path.exists(self.ziel))

    @unittest.skipIf(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
                     "Schreibschutz per chmod nur als Nicht-root auf POSIX")
    def test_fehlende_rechte_brechen_nicht_ab_und_werden_wiederholt(self):
        self._alles_anlegen()
        os.makedirs(self.ziel)
        os.chmod(self.ziel, 0o500)
        try:
            erg = self.lauf()
        finally:
            os.chmod(self.ziel, 0o700)
        self.assertEqual(erg.kopiert, [])
        self.assertTrue(erg.offen)
        self.assertFalse(os.path.exists(os.path.join(self.ziel, dz.MARKER_NAME)))
        erg2 = self.lauf()          # Rechte wieder da -> jetzt klappt es
        self.assertEqual(sorted(n for n, _ in erg2.kopiert), sorted(_NAMEN))


class SqliteUebernahme(_TmpFall):

    def test_wal_wird_mitgenommen(self):
        """Stand mit noch nicht eingecheckpointeter WAL (z. B. nach Absturz):
        ohne die -wal fehlten die letzten Zeilen in der Kopie."""
        arbeit = os.path.join(self.basis, "arbeit")
        os.makedirs(arbeit)
        db = os.path.join(arbeit, "current_show.db")
        con = sqlite3.connect(db)
        con.execute("pragma journal_mode=wal")
        con.execute("pragma wal_autocheckpoint=0")
        con.execute("create table t(x)")
        con.execute("insert into t values (7)")
        con.commit()
        # Abbild WAEHREND die Verbindung offen ist -> Zeilen nur in der -wal.
        import shutil
        for endung in ("", "-wal"):
            shutil.copy2(db + endung, os.path.join(self.alt, "current_show.db" + endung))
        con.close()
        self.assertTrue(os.path.getsize(os.path.join(self.alt, "current_show.db-wal")) > 0)

        erg = self.lauf()
        self.assertEqual([n for n, _ in erg.kopiert], ["current_show.db"])
        self.assertTrue(os.path.exists(os.path.join(self.ziel, "current_show.db-wal")))
        self.assertFalse(os.path.exists(os.path.join(self.ziel, "current_show.db-shm")))
        con2 = sqlite3.connect(os.path.join(self.ziel, "current_show.db"))
        self.assertEqual(con2.execute("select x from t").fetchall(), [(7,)])
        con2.close()
        # Quelle unangetastet: die -wal liegt dort weiter.
        self.assertTrue(os.path.exists(os.path.join(self.alt, "current_show.db-wal")))

    def test_offene_db_wird_nicht_kopiert_und_spaeter_nachgeholt(self):
        self.schreibe(self.alt, "universes.json", "[]")
        sqlite3.connect(os.path.join(self.alt, "current_show.db")).close()
        erg = self.lauf(in_benutzung=lambda p: True)
        self.assertEqual([n for n, _ in erg.kopiert], ["universes.json"])
        self.assertEqual([o[0] for o in erg.offen], ["current_show.db"])
        self.assertFalse(os.path.exists(os.path.join(self.ziel, "current_show.db")))
        erg2 = self.lauf()
        self.assertEqual([n for n, _ in erg2.kopiert], ["current_show.db"])
        # Im ersten Lauf schon Uebernommenes ist kein Konflikt (Teil-Marker).
        self.assertEqual(erg2.konflikte, [])
        self.assertEqual(self.lauf().uebersprungen, "bereits erledigt")

    def _quelle_mit_show(self):
        con = sqlite3.connect(os.path.join(self.alt, "current_show.db"))
        con.execute("create table fixture_groups(name)")
        con.execute("insert into fixture_groups values ('G')")
        con.commit()
        con.close()

    def _gruppen_am_ziel(self):
        con = sqlite3.connect(os.path.join(self.ziel, "current_show.db"))
        try:
            return con.execute("select name from fixture_groups").fetchall()
        finally:
            con.close()

    def test_verwaiste_wal_am_ziel_wird_gesichert_und_uebernommen(self):
        """Befund 2: eine -wal ohne Hauptdatei ist kein Nutzerstand. Vorher:
        Konflikt, Quelle erledigt, die Show nie uebernommen."""
        self._quelle_mit_show()
        self.schreibe(self.ziel, "current_show.db-wal", "fremd")
        erg = self.lauf()
        self.assertEqual([n for n, _ in erg.kopiert], ["current_show.db"])
        self.assertEqual(erg.konflikte, [])
        self.assertFalse(os.path.exists(os.path.join(self.ziel, "current_show.db-wal")))
        self.assertTrue(os.path.exists(
            os.path.join(self.ziel, "current_show.db-wal" + dz.SICHERUNG)))
        self.assertEqual(self._gruppen_am_ziel(), [("G",)])

    def test_abbruch_beim_letzten_umbenennen_hinterlaesst_keine_wal(self):
        """Befund 2: -wal schon umbenannt, Hauptdatei scheitert (Virenscanner)
        -> Rollback; der naechste Start uebernimmt."""
        self._quelle_mit_show()
        self.schreibe(self.alt, "current_show.db-wal", "")
        echt = os.replace

        def zickig(a, b):
            if b.endswith("current_show.db"):
                raise PermissionError("gesperrt")
            return echt(a, b)

        with mock.patch.object(dz.os, "replace", zickig):
            erg = self.lauf(dateien=["current_show.db"])
        self.assertEqual(erg.kopiert, [])
        self.assertEqual([o[0] for o in erg.offen], ["current_show.db"])
        self.assertEqual(
            sorted(n for n in os.listdir(self.ziel) if n.startswith("current_show")),
            [], "Reste am Ziel")
        erg2 = self.lauf(dateien=["current_show.db"])
        self.assertEqual([n for n, _ in erg2.kopiert], ["current_show.db"])
        self.assertEqual(self._gruppen_am_ziel(), [("G",)])

    def test_leere_ziel_db_wird_gesichert_und_ersetzt(self):
        """Befund 1 (Kern): eine LEERE Show-DB im App-Ordner (App/Werkzeug lief
        einmal ohne Uebernahme) verdraengt den alten Stand nicht mehr."""
        self._quelle_mit_show()
        os.makedirs(self.ziel)
        con = sqlite3.connect(os.path.join(self.ziel, "current_show.db"))
        con.execute("pragma journal_mode=wal")
        con.execute("create table fixture_groups(name)")
        con.execute("create table patched_fixtures(id)")
        con.commit()
        con.close()
        erg = self.lauf()
        self.assertEqual(erg.konflikte, [])
        self.assertEqual([n for n, _ in erg.kopiert], ["current_show.db"])
        self.assertEqual([n for n, _ in erg.ersetzt], ["current_show.db"])
        self.assertTrue(os.path.exists(
            os.path.join(self.ziel, "current_show.db" + dz.SICHERUNG)))
        self.assertEqual(self._gruppen_am_ziel(), [("G",)])

    def test_ziel_db_mit_inhalt_bleibt_konflikt(self):
        self._quelle_mit_show()
        os.makedirs(self.ziel)
        con = sqlite3.connect(os.path.join(self.ziel, "current_show.db"))
        con.execute("create table fixture_groups(name)")
        con.execute("insert into fixture_groups values ('NEU')")
        con.commit()
        con.close()
        erg = self.lauf()
        self.assertEqual([n for n, _ in erg.konflikte], ["current_show.db"])
        self.assertEqual(erg.kopiert, [])
        self.assertEqual(self._gruppen_am_ziel(), [("NEU",)])

    def test_offen_dann_leere_db_angelegt_wird_beim_naechsten_start_nachgeholt(self):
        """Befund 1 (c): "offen, naechster Start" griff nie — im selben Lauf
        legte die App die Ziel-DB frisch an, der naechste sah einen Konflikt."""
        self._quelle_mit_show()
        erg = self.lauf(in_benutzung=lambda p: True)
        self.assertTrue(erg.show_db_in_benutzung())
        sqlite3.connect(os.path.join(self.ziel, "current_show.db")).close()
        erg2 = self.lauf()
        self.assertEqual([n for n, _ in erg2.kopiert], ["current_show.db"])
        self.assertEqual(self._gruppen_am_ziel(), [("G",)])

    @unittest.skipUnless(os.path.exists("/proc/locks"), "nur mit /proc/locks")
    def test_echte_offene_wal_verbindung_wird_erkannt(self):
        db = os.path.join(self.alt, "current_show.db")
        con = sqlite3.connect(db)
        con.execute("pragma journal_mode=wal")
        con.execute("create table t(x)")
        con.commit()
        con.execute("select * from t").fetchall()
        try:
            self.assertTrue(dz.sqlite_in_benutzung(db))
        finally:
            con.close()
        self.assertFalse(dz.sqlite_in_benutzung(db))

    def test_linux_lockliste_parsen(self):
        p = os.path.join(self.basis, "locks")
        self.schreibe(self.basis, "locks",
                      "1: POSIX  ADVISORY  READ 1234 08:02:5678 128 128\n"
                      "2: -> POSIX  ADVISORY  WRITE 99 fd:01:42 0 EOF\n")
        self.assertEqual(dz._linux_gesperrte_inodes(p), {5678, 42})


# ── main.py / Start ───────────────────────────────────────────────────────────

class StartVerdrahtung(unittest.TestCase):

    def test_main_ruft_die_uebernahme_nach_der_sperre_und_vor_dem_fenster(self):
        with open(os.path.join(_REPO, "main.py"), encoding="utf-8") as f:
            quelle = f.read()
        rumpf = quelle[quelle.index("def main():"):]
        i_sperre = rumpf.index("acquire_instance_lock(")
        i_umzug = rumpf.index("einmal_je_prozess()")
        i_fenster = rumpf.index("MainWindow(")
        self.assertLess(i_sperre, i_umzug)
        self.assertLess(i_umzug, i_fenster)

    def test_main_meldet_vor_dem_fenster(self):
        with open(os.path.join(_REPO, "main.py"), encoding="utf-8") as f:
            quelle = f.read()
        rumpf = quelle[quelle.index("def main():"):]
        self.assertLess(rumpf.index("_datenumzug_melden(_umzug)"),
                        rumpf.index("MainWindow("))

    def test_meldung_gesperrte_show_db_und_konflikte(self):
        """Befund 1: gesperrte Show-DB -> Rueckfrage (Nein = beenden);
        Konflikte -> Hinweis + Quittung, nicht nur eine Log-Zeile."""
        import main as M
        from PySide6.QtWidgets import QMessageBox
        erg = dz.Ergebnis(offen=[("current_show.db", "/alt/current_show.db",
                                  "in Benutzung")])
        with mock.patch.object(QMessageBox, "warning",
                               return_value=QMessageBox.StandardButton.No) as w:
            self.assertFalse(M._datenumzug_melden(erg))
        w.assert_called_once()
        erg2 = dz.Ergebnis(konflikte=[("universes.json", "/alt/universes.json")],
                           ziel_dir="/app")
        with mock.patch.object(QMessageBox, "information") as i, \
                mock.patch.object(dz, "quittiere_konflikte") as q:
            self.assertTrue(M._datenumzug_melden(erg2))
        i.assert_called_once()
        q.assert_called_once_with(erg2)

    def test_get_state_uebernimmt_vor_dem_oeffnen_der_show_db(self):
        """Befund 1 (b): Werkzeuge ohne main.py rufen get_state() — die
        Uebernahme muss dort laufen, bevor open_show() eine leere DB anlegt."""
        with open(os.path.join(_REPO, "src", "core", "app_state.py"),
                  encoding="utf-8") as f:
            quelle = f.read()
        rumpf = quelle[quelle.index("def get_state()"):]
        self.assertLess(rumpf.index("einmal_je_prozess()"),
                        rumpf.index("AppState()"))

    def test_kanal_modifier_werden_beim_start_geladen(self):
        """Nebenbefund Review #863: gespeichert wurde, geladen nie."""
        from src.core import app_state as A
        from src.core.engine import channel_modifier as cm
        pfad = paths.user_data_file("channel_modifiers.json")
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        # Sicherung: conftest hat den Datenordner in den Temp-Bereich gelenkt.
        self.assertTrue(os.path.realpath(pfad).startswith(
            os.path.realpath(tempfile.gettempdir()) + os.sep), pfad)
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump([{"universe": 1, "address": 5, "curve": "Linear"}], f)
        alt = cm._mgr
        cm._mgr = None
        try:
            A.AppState()
            self.assertIsNotNone(cm.get_modifier_manager().get(1, 5))
        finally:
            cm._mgr = alt
            os.remove(pfad)


if __name__ == "__main__":
    unittest.main()
