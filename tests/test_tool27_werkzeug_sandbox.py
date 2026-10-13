"""TOOL-27: Pruef- und Inventar-Werkzeuge isolieren sich selbst.

Vorfall (13.10.2026): ``tools/audit_tooltip_coverage.py`` und
``tools/ui_verification_checklist.py`` wurden direkt gestartet. Beide bauen
``AppState`` und Ansichten und oeffneten dabei die ECHTE ``current_show.db``
des Bedieners (``-wal``/``-shm`` neu gestempelt) und den Sende-Prozess des
angeschlossenen DMX-Interface. TOOL-19 deckte nur ``get_state()``-Rufer und nur
die Ausgabe-Konfiguration ab.

Jetzt gibt es EINE Stelle, ``tools/_werkzeug_sandbox.py``: sie lenkt beim Import
den Datenordner, die Show-DB, die Ausgabe-Konfiguration, das Absturzprotokoll
und die Geraete-Bibliothek (als Kopie) in einen Wegwerf-Ordner und schaltet
Ausgabe-Thread, seriellen Kindprozess und rohes USB ab.

Drei Lagen:

* **statisch** — jedes Skript unter ``tools/``, das die App oder Teile davon
  baut, laedt die Sandbox (direkt oder ueber ``_gen_env``/``_builder``) vor dem
  ersten ``src``-Import, oder steht mit Begruendung auf der Ausnahmeliste.
* **das Modul selbst** — Kindprozesse, die NUR die Sandbox laden (kein ``src``,
  kein Qt): was wird umgelenkt, was bleibt stehen, wer darf ``--echte-daten``.
* **am echten Weg** — ein Kindprozess mit eigenem Home, in dem eine „echte"
  ``current_show.db``, ``universes.json`` (Enttec) und ``ui_prefs.json`` liegen,
  laesst die beiden Werkzeuge wirklich laufen. Danach ist der Datenordner
  unveraendert. Gegenprobe: mit ausgehebelter Sandbox wird er angefasst.

In keinem Fall wird ein Port geoeffnet: ``serial.Serial``, die Port-Suche, der
Start von Kindprozessen und ``usb.core.find`` sind im Kind durch Mitschreiber
ersetzt.
"""
from __future__ import annotations

import ast
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"

#: Module, ueber die ein Werkzeug die Sandbox bekommt.
SCHUTZ = {"_werkzeug_sandbox", "_gen_env", "_builder", "_showcase"}

#: Aufrufe, an denen man ein Werkzeug erkennt, das die App (oder Teile) baut.
BAUT = {"QApplication", "QGuiApplication", "AppState", "MainWindow", "get_state"}

#: Werkzeuge mit EIGENER, harter Sandbox — mit Grund. Kurz halten.
AUSNAHMEN = {
    "tools/app_messung.py": (
        "TOOL-26: misst die App wie der Nutzer sie startet und nimmt dafuer die "
        "Schutzschalter (kein Ausgabe-Thread, offscreen) bewusst wieder heraus; "
        "eigene Sandbox-Pflicht mit Pruefung vor dem ersten App-Import (Exit 2)."),
    "tools/verify_stage_reload.py": (
        "Sichtprobe im echten Fenster mit eigener Sandbox (sandbox_einrichten), "
        "die hart setzt statt setdefault."),
}
#: Was eine Ausnahme mindestens selbst umlenken muss.
AUSNAHME_MUSS_SETZEN = ("XDG_DATA_HOME", "LIGHTOS_SHOW_DB", "LIGHTOS_FIXTURE_DB",
                        "LIGHTOS_UNIVERSES_JSON")

ALT = 1_577_880_000          # 01.01.2020 — der „alte" Zeitstempel der echten Dateien


def _skripte():
    for pfad in sorted(TOOLS.rglob("*.py")):
        teile = pfad.relative_to(TOOLS).parts
        if "__pycache__" in teile or teile[0] == "_archiv":
            continue
        yield pfad, teile


def _befund(baum: ast.AST) -> dict:
    """Was ein Skript baut und wo es Schutz bzw. ``src`` importiert."""
    rufe, schutz_zeile, src_zeile, ui = set(), None, None, False
    for node in ast.walk(baum):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            if name in BAUT:
                rufe.add(name)
        namen = []
        if isinstance(node, ast.Import):
            namen = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            namen = [node.module or ""] + [f"{node.module or ''}.{a.name}" for a in node.names]
        for n in namen:
            if n == "src" or n.startswith("src.") or n == "main":
                src_zeile = min(src_zeile or node.lineno, node.lineno)
                if n.startswith("src.ui"):
                    ui = True
    for node in getattr(baum, "body", []):          # Schutz zaehlt nur auf Modulebene
        geladen = set()
        if isinstance(node, ast.Import):
            geladen = {a.name.split(".")[-1] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            geladen = {(node.module or "").split(".")[-1]} | {a.name for a in node.names}
        elif isinstance(node, ast.Try):             # try: import x / except: from tools import x
            for unter in ast.walk(node):
                if isinstance(unter, ast.Import):
                    geladen |= {a.name.split(".")[-1] for a in unter.names}
        if geladen & SCHUTZ and schutz_zeile is None:
            schutz_zeile = node.lineno
    return {"rufe": rufe, "ui": ui, "schutz": schutz_zeile, "src": src_zeile}


class JedesBauendeWerkzeugLaedtDieSandboxTest(unittest.TestCase):

    def _einordnen(self):
        geschuetzt, offen, zu_spaet, ausnahmen = [], [], [], []
        for pfad, teile in _skripte():
            rel = pfad.relative_to(REPO).as_posix()
            if pfad.name in ("_werkzeug_sandbox.py", "_gen_env.py"):
                continue                                    # eigene Tests unten
            baum = ast.parse(pfad.read_text(encoding="utf-8", errors="replace"))
            b = _befund(baum)
            if not (b["rufe"] or b["ui"]):
                continue
            if teile[0] == "anleitungsbilder":
                continue        # eigene Sandbox (DOC-16), s. test_die_bild_sandbox_...
            if rel in AUSNAHMEN:
                ausnahmen.append(rel)
            elif b["schutz"] is None:
                offen.append(rel)
            elif b["src"] is not None and b["src"] < b["schutz"]:
                zu_spaet.append(f"{rel}: src-Import in Zeile {b['src']}, "
                                f"Sandbox erst in Zeile {b['schutz']}")
            else:
                geschuetzt.append(rel)
        return geschuetzt, offen, zu_spaet, ausnahmen

    def test_kein_bauendes_werkzeug_ohne_sandbox(self):
        geschuetzt, offen, zu_spaet, _ = self._einordnen()
        self.assertEqual(
            offen, [],
            "Diese Werkzeuge bauen QApplication/AppState/MainWindow/Ansichten und laden "
            "die Sandbox nicht — direkt gestartet oeffnen sie die echte Show-Datenbank "
            "und das DMX-Interface des Rechners. Als ERSTE Import-Zeile:\n"
            "    import _werkzeug_sandbox  # noqa: F401\n  " + "\n  ".join(offen))
        self.assertEqual(zu_spaet, [],
                         "Die Sandbox muss VOR dem ersten src-Import geladen sein — "
                         "viele Module frieren ihre Pfade beim Import ein.")
        # Gegenprobe: die Suche laeuft nicht leer.
        self.assertGreater(len(geschuetzt), 40, geschuetzt)
        for name in ("tools/audit_tooltip_coverage.py",
                     "tools/ui_verification_checklist.py"):
            self.assertIn(name, geschuetzt)

    def test_die_beiden_vorfall_werkzeuge_laden_sie_als_erste_zeile(self):
        """Erste Import-Zeile nach dem (zwingend ersten) ``from __future__``."""
        for name in ("audit_tooltip_coverage.py", "ui_verification_checklist.py"):
            with self.subTest(name):
                baum = ast.parse((TOOLS / name).read_text(encoding="utf-8"))
                importe = [n for n in baum.body if isinstance(n, (ast.Import, ast.ImportFrom))
                           and not (isinstance(n, ast.ImportFrom) and n.module == "__future__")]
                self.assertIsInstance(importe[0], ast.Import)
                self.assertEqual([a.name for a in importe[0].names], ["_werkzeug_sandbox"])

    def test_die_ausnahmen_haben_ihre_eigene_sandbox(self):
        _, _, _, ausnahmen = self._einordnen()
        self.assertEqual(sorted(ausnahmen), sorted(AUSNAHMEN),
                         "Die Ausnahmeliste nennt ein Werkzeug, das es nicht (mehr) "
                         "gibt oder das nichts mehr baut.")
        for rel in AUSNAHMEN:
            quelle = (REPO / rel).read_text(encoding="utf-8")
            for var in AUSNAHME_MUSS_SETZEN:
                with self.subTest(rel=rel, var=var):
                    self.assertIn(f'"{var}"', quelle)

    def test_die_bild_sandbox_lenkt_dieselben_orte_um(self):
        quelle = (TOOLS / "anleitungsbilder" / "sandbox.py").read_text(encoding="utf-8")
        for var in AUSNAHME_MUSS_SETZEN + ("APPDATA", "LIGHTOS_CRASH_LOG",
                                           "LIGHTOS_PREFS_DIR"):
            with self.subTest(var):
                self.assertIn(f'"{var}"', quelle)

    def test_gen_env_und_builder_reichen_die_sandbox_weiter(self):
        """Der Schutz ueber ``_gen_env``/``_builder``/``_showcase`` gilt nur,
        solange die Kette haelt."""
        baum = ast.parse((TOOLS / "_gen_env.py").read_text(encoding="utf-8"))
        b = _befund(baum)
        self.assertIsNotNone(b["schutz"], "_gen_env laedt _werkzeug_sandbox nicht")
        erste_umgebung = min(
            n.lineno for n in ast.walk(baum)
            if isinstance(n, ast.Attribute) and n.attr == "environ")
        self.assertLess(b["schutz"], erste_umgebung,
                        "_gen_env setzt Variablen, bevor die Sandbox geladen ist — "
                        "ihre VORGABEN waeren dann schon verfaelscht")
        self.assertIsNone(b["src"], "_gen_env importiert src (die Bild-Sandbox "
                                    "verlangt: vor ihr kein src-Modul)")
        for name, traeger in (("_builder.py", "_gen_env"), ("_showcase.py", "_gen_env")):
            unter = ast.parse((TOOLS / name).read_text(encoding="utf-8"))
            geladen = {a.name for n in unter.body if isinstance(n, ast.Import)
                       for a in n.names}
            geladen |= {n.module for n in unter.body if isinstance(n, ast.ImportFrom)}
            self.assertTrue(geladen & {traeger, "_builder"}, f"{name} laedt {traeger} nicht")

    def test_die_sandbox_importiert_selbst_nichts_aus_src(self):
        baum = ast.parse((TOOLS / "_werkzeug_sandbox.py").read_text(encoding="utf-8"))
        self.assertIsNone(_befund(baum)["src"])


# ── Das Modul selbst: Kindprozesse ohne src und ohne Qt ──────────────────────

_NUR_SANDBOX = r'''
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "tools"))
sys.argv = [sys.argv[2]] + sys.argv[3:]
import _werkzeug_sandbox as w
print("ERGEBNIS " + json.dumps({
    "beschreibung": w.beschreibung(),
    "vorgaben": w.VORGABEN,
    "umgebung": {k: v for k, v in os.environ.items()
                 if k.startswith("LIGHTOS_") or k in ("XDG_DATA_HOME", "APPDATA", "HOME")},
    "src_geladen": sorted(m for m in sys.modules if m == "src" or m.startswith("src.")),
    "wurzel_inhalt": sorted(os.listdir(w.WURZEL)) if w.WURZEL else None,
}))
'''


def _datenordner(heim: str) -> str:
    """Der Datenordner, den die App in diesem Home OHNE Umlenkung benutzt."""
    if sys.platform == "win32":
        return os.path.join(heim, "AppData", "Roaming", "LightOS")
    if sys.platform == "darwin":
        return os.path.join(heim, "Library", "Application Support", "LightOS")
    return os.path.join(heim, ".local", "share", "LightOS")


def _bediener_umgebung(tmp: str) -> tuple[dict, str, str]:
    """Umgebung eines Bedieners: nichts von LightOS gesetzt, ein eigenes Home.

    ★ Der Temp-Bereich des Kindes ist ein EIGENER Ordner neben dem Home. Die
    Sandbox laesst einen Datenordner im Temp-Bereich als bewusste Umlenkung
    stehen — laege das Home des Kindes darin, pruefte der Test nichts."""
    heim = os.path.join(tmp, "heim")
    temp = os.path.join(tmp, "temp")
    daten = _datenordner(heim)
    os.makedirs(daten)
    os.makedirs(temp)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("LIGHTOS_") and not k.startswith("XDG_")}
    env.update({
        "HOME": heim, "USERPROFILE": heim,
        "APPDATA": os.path.join(heim, "AppData", "Roaming"),
        "LOCALAPPDATA": os.path.join(heim, "AppData", "Local"),
        "XDG_DATA_HOME": os.path.join(heim, ".local", "share"),
        "TMPDIR": temp, "TEMP": temp, "TMP": temp,
        "QT_QPA_PLATFORM": "offscreen", "PYTHONIOENCODING": "utf-8",
    })
    return env, daten, temp


def _kind(skript_text: str, tmp: str, env: dict, *args: str, timeout: int = 120):
    skript = os.path.join(tmp, "kind.py")
    with open(skript, "w", encoding="utf-8") as f:
        f.write(skript_text)
    lauf = subprocess.run([sys.executable, skript, str(REPO), *args], env=env, cwd=tmp,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    zeilen = [z for z in (lauf.stdout or "").splitlines() if z.startswith("ERGEBNIS ")]
    erg = json.loads(zeilen[-1][len("ERGEBNIS "):]) if zeilen else None
    return lauf, erg


def _innerhalb(pfad: str, ordner: str) -> bool:
    p, o = os.path.realpath(pfad), os.path.realpath(ordner)
    return p == o or p.startswith(o + os.sep)


class SandboxModulTest(unittest.TestCase):

    def test_ohne_vorgaben_wird_alles_umgelenkt_und_am_ende_aufgeraeumt(self):
        with tempfile.TemporaryDirectory(prefix="lightos_tool27_") as tmp:
            env, daten, temp = _bediener_umgebung(tmp)
            bibliothek = os.path.join(daten, "fixtures.db")
            with open(bibliothek, "wb") as f:
                f.write(b"TOOL-27 Bibliothek des Rechners")
            os.utime(bibliothek, (ALT, ALT))
            lauf, erg = _kind(_NUR_SANDBOX, tmp, env, "audit_tooltip_coverage.py")
            self.assertIsNotNone(erg, (lauf.returncode, lauf.stderr[-1500:]))
            wurzel = erg["beschreibung"]["wurzel"]
            self.assertTrue(wurzel and _innerhalb(wurzel, temp), erg)
            self.assertEqual(erg["src_geladen"], [])
            u = erg["umgebung"]
            for var in ("LIGHTOS_SHOW_DB", "LIGHTOS_UNIVERSES_JSON", "LIGHTOS_FIXTURE_DB",
                        "LIGHTOS_CRASH_LOG", "XDG_DATA_HOME", "APPDATA"):
                with self.subTest(var):
                    self.assertTrue(_innerhalb(u[var], wurzel), (var, u.get(var)))
            for var in ("LIGHTOS_NO_OUTPUT_THREAD", "LIGHTOS_SERIAL_INPROC",
                        "LIGHTOS_KEIN_USB", "LIGHTOS_NO_DATENUMZUG",
                        "LIGHTOS_NO_AUDIO_AUTOSTART"):
                with self.subTest(var):
                    self.assertEqual(u.get(var), "1")
            # Die Ausgabe-Konfiguration zeigt auf eine Datei, die es nicht gibt;
            # die Bibliothek ist eine Kopie.
            self.assertNotIn("universes.json", erg["wurzel_inhalt"])
            self.assertIn("fixtures.db", erg["wurzel_inhalt"])
            self.assertEqual(os.path.normcase(erg["beschreibung"]["echter_datenordner"]),
                             os.path.normcase(daten))
            # Das Original ist unberuehrt …
            with open(bibliothek, "rb") as f:
                self.assertEqual(f.read(), b"TOOL-27 Bibliothek des Rechners")
            self.assertEqual(int(os.stat(bibliothek).st_mtime), ALT)
            self.assertEqual(os.listdir(daten), ["fixtures.db"])
            # … und der Wegwerf-Ordner ist nach dem Lauf wieder weg.
            self.assertFalse(os.path.exists(wurzel))
            self.assertEqual(os.listdir(temp), [])

    def test_bewusste_vorgaben_bleiben_stehen(self):
        """Testlauf, Bild-Sandbox, Sichtproben-Sandkasten: wer selbst umlenkt,
        behaelt seine Orte — und es entsteht gar kein Wegwerf-Ordner."""
        with tempfile.TemporaryDirectory(prefix="lightos_tool27_") as tmp:
            env, _, temp = _bediener_umgebung(tmp)
            eigen = os.path.join(temp, "eigener_sandkasten")
            vorgaben = {
                "XDG_DATA_HOME": os.path.join(eigen, "xdg"),
                "APPDATA": os.path.join(eigen, "appdata"),
                "LIGHTOS_SHOW_DB": os.path.join(eigen, "show.db"),
                "LIGHTOS_UNIVERSES_JSON": os.path.join(eigen, "universes.json"),
                "LIGHTOS_FIXTURE_DB": os.path.join(eigen, "fixtures.db"),
                "LIGHTOS_CRASH_LOG": os.path.join(eigen, "crash.log"),
            }
            env.update(vorgaben)
            if sys.platform == "darwin":
                env["HOME"] = os.path.join(eigen, "home")
            lauf, erg = _kind(_NUR_SANDBOX, tmp, env, "audit_tooltip_coverage.py")
            self.assertIsNotNone(erg, (lauf.returncode, lauf.stderr[-1500:]))
            for var, wert in vorgaben.items():
                with self.subTest(var):
                    self.assertEqual(erg["umgebung"][var], wert)
                    self.assertEqual(erg["vorgaben"][var], wert)
            self.assertIsNone(erg["beschreibung"]["wurzel"])
            self.assertEqual(os.listdir(temp), [])

    def test_ein_echter_datenordner_wird_auch_dann_umgelenkt_wenn_er_gesetzt_ist(self):
        """``APPDATA`` ist unter Windows immer gesetzt — ein ``setdefault``
        schuetzte dort nichts. Nur eine Vorgabe im Temp-Bereich bleibt."""
        with tempfile.TemporaryDirectory(prefix="lightos_tool27_") as tmp:
            env, _, _ = _bediener_umgebung(tmp)
            echt = env["APPDATA"]
            lauf, erg = _kind(_NUR_SANDBOX, tmp, env, "audit_tooltip_coverage.py")
            self.assertIsNotNone(erg, (lauf.returncode, lauf.stderr[-1500:]))
            self.assertEqual(erg["vorgaben"]["APPDATA"], echt)
            self.assertNotEqual(erg["umgebung"]["APPDATA"], echt)

    def test_echte_daten_nur_fuer_die_erlaubten_werkzeuge(self):
        sys.path.insert(0, str(TOOLS))
        try:
            import _werkzeug_sandbox as w
        finally:
            sys.path.remove(str(TOOLS))
        # Im Testlauf ist alles schon umgelenkt (conftest) — die Sandbox legt
        # dann keinen eigenen Ordner an und verschiebt nichts ein zweites Mal.
        self.assertIsNone(w.WURZEL, w.UMGELENKT)
        self.assertEqual(sorted(w.ECHTE_DATEN_ERLAUBT),
                         ["build_full_show", "patch_quarantaene"],
                         "Ein weiteres Werkzeug darf an echte Daten — das gehoert "
                         "begruendet (Liste hier und Entwickler-Doku nachziehen).")
        for grund in w.ECHTE_DATEN_ERLAUBT.values():
            self.assertGreater(len(grund), 30)
        with tempfile.TemporaryDirectory(prefix="lightos_tool27_") as tmp:
            env, daten, temp = _bediener_umgebung(tmp)
            # (1) Ein Pruefwerkzeug bekommt den Schalter nicht.
            lauf, erg = _kind(_NUR_SANDBOX, tmp, env, "audit_tooltip_coverage.py",
                              "--echte-daten")
            self.assertIsNone(erg)
            self.assertNotEqual(lauf.returncode, 0)
            self.assertIn("ABBRUCH", lauf.stderr)
            # (2) Das Wartungswerkzeug bekommt ihn — mit Warnzeile, ohne Ausgang.
            lauf, erg = _kind(_NUR_SANDBOX, tmp, env, "patch_quarantaene.py",
                              "--echte-daten")
            self.assertIsNotNone(erg, (lauf.returncode, lauf.stderr[-1500:]))
            self.assertTrue(erg["beschreibung"]["echte_daten"])
            self.assertIn("ECHTEN Bestand", lauf.stderr)
            self.assertIn(daten, lauf.stderr)
            u = erg["umgebung"]
            self.assertEqual(u["XDG_DATA_HOME"], env["XDG_DATA_HOME"])
            self.assertEqual(u["APPDATA"], env["APPDATA"])
            self.assertNotIn("LIGHTOS_SHOW_DB", u)
            self.assertNotIn("LIGHTOS_FIXTURE_DB", u)
            self.assertTrue(_innerhalb(u["LIGHTOS_UNIVERSES_JSON"], temp))
            for var in ("LIGHTOS_NO_OUTPUT_THREAD", "LIGHTOS_SERIAL_INPROC",
                        "LIGHTOS_KEIN_USB"):
                self.assertEqual(u.get(var), "1", var)
            # (3) Ohne den Schalter laeuft auch das Wartungswerkzeug in der Sandbox.
            lauf, erg = _kind(_NUR_SANDBOX, tmp, env, "patch_quarantaene.py")
            self.assertFalse(erg["beschreibung"]["echte_daten"])
            self.assertTrue(_innerhalb(erg["umgebung"]["LIGHTOS_SHOW_DB"], temp))

    def test_die_wartungswerkzeuge_verlangen_den_schalter(self):
        quelle = (TOOLS / "patch_quarantaene.py").read_text(encoding="utf-8")
        self.assertIn("_werkzeug_sandbox.SCHALTER_ECHTE_DATEN", quelle)
        self.assertLess(quelle.index("if not args.echte_daten:"),
                        quelle.index("state = get_state()"),
                        "der Riegel steht hinter dem Aufbau des AppState")
        self.assertIn("--echte-daten", (TOOLS / "build_full_show.py").read_text(encoding="utf-8"))


# ── Am echten Weg: die beiden Werkzeuge laufen wirklich ──────────────────────

_WERKZEUG_LAUF = r'''
import json, os, runpy, sys, types
repo, name, modus = sys.argv[1], sys.argv[2], sys.argv[3]
argumente = sys.argv[4:]
tools = os.path.join(repo, "tools")
sys.path.insert(0, repo)
sys.path.insert(0, tools)            # wie beim Skript-Start: tools/ zuerst

# Mitschreiber: in KEINEM Fall wird ein Port, ein USB-Geraet oder ein
# Kindprozess wirklich geoeffnet. Nichts davon laedt ein src-Modul.
geoeffnet = []
import serial, serial.tools.list_ports
class _KeinPort:
    def __init__(self, *a, **k):
        geoeffnet.append(["serial", [str(x) for x in a]])
        raise serial.SerialException("TOOL-27: der Test oeffnet keinen Port")
serial.Serial = _KeinPort
serial.tools.list_ports.comports = lambda *a, **k: []
import multiprocessing.process
def _kein_kind(self, *a, **k):
    geoeffnet.append(["prozess", [str(getattr(self, "name", ""))]])
    raise RuntimeError("TOOL-27: der Test startet keinen Kindprozess")
multiprocessing.process.BaseProcess.start = _kein_kind
try:
    import usb.core
    def _kein_usb(*a, **k):
        geoeffnet.append(["usb", []])
        return iter(()) if k.get("find_all") else None
    usb.core.find = _kein_usb
except Exception:
    pass

if modus == "ohne":
    # Gegenprobe: die gemeinsame Stelle ist ausgehebelt — das Werkzeug laeuft
    # so, wie es vor TOOL-27 lief.
    attrappe = types.ModuleType("_werkzeug_sandbox")
    attrappe.SCHALTER_ECHTE_DATEN = "--echte-daten"
    attrappe.ECHTE_DATEN = False
    sys.modules["_werkzeug_sandbox"] = sys.modules["tools._werkzeug_sandbox"] = attrappe

pfad = os.path.join(tools, name)
sys.argv = [pfad] + argumente
code = 0
try:
    runpy.run_path(pfad, run_name="__main__")
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)

ausgaenge = show_db = datenordner = None
zustand = sys.modules.get("src.core.app_state")
if zustand is not None:
    show_db = getattr(zustand, "SHOW_DB_PATH", None)
    try:
        ausgaenge = len(zustand.get_state().output_manager.ausgabe_status())
    except Exception as e:
        ausgaenge = "Fehler: %r" % (e,)
pfade = sys.modules.get("src.core.paths")
if pfade is not None:
    datenordner = pfade.app_data_dir()
sandbox = sys.modules.get("_werkzeug_sandbox")
print("ERGEBNIS " + json.dumps({
    "code": code, "geoeffnet": geoeffnet, "ausgaenge": ausgaenge,
    "app_state_geladen": zustand is not None,
    "show_db": show_db, "datenordner": datenordner,
    "wurzel": getattr(sandbox, "WURZEL", None),
    "umgebung": {k: v for k, v in os.environ.items() if k.startswith("LIGHTOS_")},
}))
sys.stdout.flush()
'''


def _echte_dateien_anlegen(daten: str) -> dict:
    """Der Datenordner eines Bedieners: Show-DB, Ausgabe-Konfiguration mit
    Enttec, Einstellungen — bekannter Inhalt, alter Zeitstempel."""
    db = os.path.join(daten, "current_show.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE tool27_merker (wert TEXT)")
    con.execute("INSERT INTO tool27_merker VALUES ('die Show des Bedieners')")
    con.commit()
    con.close()
    with open(os.path.join(daten, "universes.json"), "w", encoding="utf-8") as f:
        json.dump([{"num": 1, "name": "Rig", "output": "Enttec", "patch": "COM_TOOL27"}], f)
    with open(os.path.join(daten, "ui_prefs.json"), "w", encoding="utf-8") as f:
        json.dump({"tool27": "Einstellungen des Bedieners"}, f)
    for name in os.listdir(daten):
        os.utime(os.path.join(daten, name), (ALT, ALT))
    return _stand(daten)


def _stand(daten: str) -> dict:
    """{relativer Pfad: (Inhalt, mtime)} fuer ALLES unter dem Datenordner —
    eine neue ``-wal``/``-shm``-Datei oder eine frische ``fixtures.db`` faellt
    damit genauso auf wie ein geaendertes Byte."""
    aus = {}
    for ordner, _, dateien in os.walk(daten):
        for d in dateien:
            p = os.path.join(ordner, d)
            with open(p, "rb") as f:
                aus[os.path.relpath(p, daten).replace(os.sep, "/")] = (
                    f.read(), os.stat(p).st_mtime_ns)
    return aus


def _werkzeug_lauf(name: str, modus: str, *, schreibend: bool = True):
    with tempfile.TemporaryDirectory(prefix="lightos_tool27_") as tmp:
        env, daten, temp = _bediener_umgebung(tmp)
        vorher = _echte_dateien_anlegen(daten)
        if modus == "ohne":
            # Die Gegenprobe soll die Show-Datenbank anfassen, nicht das Rig:
            # die Schalter, die sonst die Sandbox setzt, kommen hier von aussen.
            env.update({"LIGHTOS_SERIAL_INPROC": "1", "LIGHTOS_NO_OUTPUT_THREAD": "1",
                        "LIGHTOS_KEIN_USB": "1", "LIGHTOS_NO_AUDIO_AUTOSTART": "1",
                        "LIGHTOS_NO_DATENUMZUG": "1"})
        ziel = os.path.join(tmp, "bericht.txt")
        argumente = ["--ausgabe", ziel] if schreibend else ["--check"]
        lauf, erg = _kind(_WERKZEUG_LAUF, tmp, env, name, modus, *argumente, timeout=280)
        assert erg is not None, (lauf.returncode, (lauf.stdout or "")[-2000:],
                                 (lauf.stderr or "")[-3000:])
        return {"erg": erg, "vorher": vorher, "nachher": _stand(daten), "daten": daten,
                "temp": temp, "temp_inhalt": sorted(os.listdir(temp)),
                "bericht": os.path.isfile(ziel) and os.path.getsize(ziel),
                "stderr": (lauf.stderr or "")[-3000:]}


class WerkzeugeAmEchtenWegTest(unittest.TestCase):

    def _unberuehrt(self, r: dict):
        erg = r["erg"]
        self.assertTrue(erg["app_state_geladen"],
                        "das Werkzeug hat den AppState gar nicht gebaut — der Test "
                        "misst dann nichts")
        self.assertEqual(sorted(r["nachher"]), sorted(r["vorher"]),
                         "im Datenordner des Bedieners ist eine Datei entstanden "
                         "oder verschwunden (-wal/-shm? fixtures.db?)")
        for name, (inhalt, mtime) in r["vorher"].items():
            with self.subTest(name):
                self.assertEqual(r["nachher"][name][0], inhalt, "Inhalt geaendert")
                self.assertEqual(r["nachher"][name][1], mtime, "Zeitstempel geaendert")
        self.assertEqual(erg["geoeffnet"], [], "ein Port/Geraet/Kindprozess wurde angefasst")
        self.assertEqual(erg["ausgaenge"], 0, "ein Ausgang ist eingerichtet")
        self.assertFalse(_innerhalb(erg["show_db"], r["daten"]), erg["show_db"])
        self.assertFalse(_innerhalb(erg["datenordner"], r["daten"]), erg["datenordner"])
        self.assertTrue(_innerhalb(erg["show_db"], r["temp"]), erg["show_db"])
        for var in ("LIGHTOS_NO_OUTPUT_THREAD", "LIGHTOS_SERIAL_INPROC", "LIGHTOS_KEIN_USB"):
            self.assertEqual(erg["umgebung"].get(var), "1", var)
        self.assertEqual([n for n in r["temp_inhalt"] if n.startswith("lightos_")], [],
                         "der Wegwerf-Ordner wurde nicht aufgeraeumt")

    @pytest.mark.timeout(300)
    def test_audit_tooltip_coverage_schreibend(self):
        r = _werkzeug_lauf("audit_tooltip_coverage.py", "mit")
        self._unberuehrt(r)
        self.assertEqual(r["erg"]["code"], 0, r["stderr"])
        self.assertTrue(r["bericht"], "der Report wurde nicht geschrieben")

    @pytest.mark.timeout(300)
    def test_ui_verification_checklist_schreibend(self):
        r = _werkzeug_lauf("ui_verification_checklist.py", "mit")
        self._unberuehrt(r)
        self.assertEqual(r["erg"]["code"], 0, r["stderr"])
        self.assertTrue(r["bericht"], "der Report wurde nicht geschrieben")

    @pytest.mark.timeout(300)
    def test_gegenprobe_ohne_sandbox_wird_der_echte_datenordner_angefasst(self):
        """Der Aufbau misst richtig: mit ausgehebelter Sandbox arbeitet dasselbe
        Werkzeug auf der Show-Datenbank des Bedieners und greift nach dem
        Enttec-Port aus dessen ``universes.json`` (hier: dem Mitschreiber)."""
        r = _werkzeug_lauf("audit_tooltip_coverage.py", "ohne")
        erg = r["erg"]
        self.assertTrue(_innerhalb(erg["show_db"], r["daten"]), erg["show_db"])
        self.assertNotEqual(r["nachher"], r["vorher"],
                            "auch ohne Sandbox blieb der Datenordner unberuehrt — "
                            "der Test misst nichts")
        db_vorher = r["vorher"]["current_show.db"]
        db_nachher = r["nachher"].get("current_show.db")
        self.assertNotEqual(db_nachher, db_vorher,
                            "die echte Show-Datenbank wurde nicht angefasst")
        self.assertIn(["serial", ["COM_TOOL27"]],
                      [[a, b[:1]] for a, b in erg["geoeffnet"]], erg["geoeffnet"])


class AusgabeZielTest(unittest.TestCase):
    """``--ausgabe``: der schreibende Modus laesst sich vom Repo weglenken."""

    def test_beide_werkzeuge_kennen_ausgabe(self):
        for name in ("audit_tooltip_coverage.py", "ui_verification_checklist.py"):
            with self.subTest(name):
                self.assertIn('"--ausgabe"', (TOOLS / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
