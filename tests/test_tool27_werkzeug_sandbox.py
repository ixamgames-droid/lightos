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
* **am echten Weg** — die beiden Werkzeuge werden NACKT gestartet
  (``python tools/<name>.py`` aus einem fremden Arbeitsordner), mit eigenem Home,
  in dem eine „echte" ``current_show.db``, ``universes.json`` (Enttec) und
  ``ui_prefs.json`` liegen. Danach ist der Datenordner unveraendert.
  Gegenprobe: mit ausgehebelter Sandbox wird er angefasst.

In keinem Fall wird ein Port geoeffnet: ``serial.Serial``, die Port-Suche, der
Start von Kindprozessen, ``usb.core.find``, MIDI-Ports und jedes Netz-Socket,
das den Rechner verliesse, sind im Kind durch Mitschreiber ersetzt (als
``sitecustomize`` ueber ``PYTHONPATH`` — das Werkzeug selbst bleibt unberuehrt).
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

#: Werkzeuge, die ``src`` laden, die App aber NICHT bauen und mit Absicht am
#: Bestand bzw. an der Hardware des Rechners arbeiten. Jedes braucht einen Grund
#: — und darf nichts laden, womit die Show-Datenbank ins Spiel kaeme
#: (:data:`BESTAND_VERBOTEN`).
AM_BESTAND = {
    "tools/library_testreste.py": (
        "QA-68: zeigt bzw. entfernt Testreste in der Geraete-Bibliothek des Rechners."),
    "tools/bibliothek_profil.py": (
        "Pflegewerkzeug der Geraete-Bibliothek (Profile aus- und einlesen)."),
    "tools/fixture_herkunft.py": (
        "Liest die Herkunft der Profile aus der Geraete-Bibliothek des Rechners."),
    "tools/_profil.py": (
        "Helfer: sucht ein Profil in der Geraete-Bibliothek; die Generatoren laden "
        "ihn erst nach _gen_env, dann ist es die Kopie."),
    "tools/collect_crash_report.py": (
        "Wertet das Absturzprotokoll des Rechners aus — das ist sein Zweck."),
    "tools/import_qlc_input_profile.py": (
        "Legt ein Controller-Profil fuer den Bediener ab — das ist sein Zweck."),
    "tools/hw5_longrun.py": (
        "HW-5: Langzeitmessung am Enttec — sendet mit Absicht an den echten Port."),
    "tools/mh_einmessen.py": (
        "Einmessen der Moving Heads am Rig — sendet mit Absicht an den genannten Port."),
}
#: Damit kaeme der AppState (Show-DB, Ausgaenge) oder die Oberflaeche ins Spiel.
BESTAND_VERBOTEN = ("src.core.app_state", "src.ui", "src.web", "src.core.show", "main")

ALT = 1_577_880_000          # 01.01.2020 — der „alte" Zeitstempel der echten Dateien


def _skripte():
    for pfad in sorted(TOOLS.rglob("*.py")):
        teile = pfad.relative_to(TOOLS).parts
        if "__pycache__" in teile or teile[0] == "_archiv":
            continue
        yield pfad, teile


def _src_importe(baum: ast.AST) -> set[str]:
    """Alle ``src``-/``main``-Module, die ein Skript irgendwo importiert."""
    aus = set()
    for node in ast.walk(baum):
        namen = []
        if isinstance(node, ast.Import):
            namen = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            namen = [node.module or ""] + [f"{node.module or ''}.{a.name}" for a in node.names]
        aus |= {n for n in namen if n == "src" or n.startswith("src.") or n == "main"}
    return aus


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

    def test_jedes_werkzeug_das_src_laedt_ist_eingeordnet(self):
        """Die Suche oben erkennt ein bauendes Werkzeug an ``QApplication``,
        ``AppState``, ``get_state`` … Das ist eine Stichwortliste. Dieser Test
        ist das Netz darunter: WER ``src`` LAEDT, ist geschuetzt, eine
        begruendete Ausnahme oder ein begruendetes Bestands-Werkzeug. Ein neues
        Skript, das z. B. nur ``src.core.show.show_file.load_show`` ruft (und
        damit die Show-Datenbank oeffnet), faellt sonst durch."""
        offen, falsch = [], []
        gesehen = set()
        for pfad, teile in _skripte():
            rel = pfad.relative_to(REPO).as_posix()
            if pfad.name in ("_werkzeug_sandbox.py", "_gen_env.py"):
                continue
            if teile[0] == "anleitungsbilder":
                continue        # eigene Sandbox (DOC-16)
            quelle = pfad.read_text(encoding="utf-8", errors="replace")
            baum = ast.parse(quelle)
            geladen = _src_importe(baum)
            dynamisch = "import_module" in quelle and '"src.' in quelle
            if not (geladen or dynamisch):
                continue
            b = _befund(baum)
            geschuetzt = b["schutz"] is not None and (
                b["src"] is None or b["schutz"] < b["src"])
            if geschuetzt or rel in AUSNAHMEN:
                continue
            if rel not in AM_BESTAND:
                offen.append(rel)
                continue
            gesehen.add(rel)
            boese = sorted(n for n in geladen
                           if any(n == v or n.startswith(v + ".") for v in BESTAND_VERBOTEN))
            if boese or b["rufe"]:
                falsch.append(f"{rel}: {boese or sorted(b['rufe'])}")
        self.assertEqual(
            offen, [],
            "Diese Werkzeuge laden src ohne Sandbox und stehen auf keiner Liste. "
            "Als ERSTE Import-Zeile:\n    import _werkzeug_sandbox  # noqa: F401\n"
            "oder — wenn der Bestand des Rechners ihr Zweck ist — mit Grund in "
            "AM_BESTAND:\n  " + "\n  ".join(offen))
        self.assertEqual(falsch, [],
                         "Ein Bestands-Werkzeug laedt den AppState, die Show oder die "
                         "Oberflaeche — damit gehoert es in die Sandbox.")
        self.assertEqual(sorted(gesehen), sorted(AM_BESTAND),
                         "AM_BESTAND nennt ein Werkzeug, das es nicht (mehr) gibt, "
                         "das kein src mehr laedt oder das inzwischen geschuetzt ist.")
        for grund in AM_BESTAND.values():
            self.assertGreater(len(grund), 30)

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
    p = os.path.normcase(os.path.realpath(pfad))
    o = os.path.normcase(os.path.realpath(ordner))
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
            self.assertEqual(u.get("LIGHTOS_NO_MIDI_AUTOCONNECT"), "1")

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

_MITSCHREIBER = r'''
# sitecustomize des Kindprozesses (liegt per PYTHONPATH vor allem anderen):
# so startet der Test das Werkzeug wirklich NACKT — ``python tools/<name>.py``,
# kein Huellskript — und schreibt trotzdem mit. Nichts hier laedt ein src-Modul.
import atexit, json, os, sys, types
_ziel = os.environ.get("TOOL27_ERGEBNIS")
if _ziel:
    geoeffnet = []
    # In KEINEM Fall wird ein Port, ein USB-/MIDI-Geraet, ein Netz-Socket oder
    # ein Kindprozess wirklich geoeffnet.
    try:
        import serial, serial.tools.list_ports
        class _KeinPort:
            def __init__(self, *a, **k):
                geoeffnet.append(["serial", [str(x) for x in a]])
                raise serial.SerialException("TOOL-27: der Test oeffnet keinen Port")
        serial.Serial = _KeinPort
        serial.tools.list_ports.comports = lambda *a, **k: []
    except ImportError:
        pass
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
    # Netz: jedes bind/connect/sendto, das nicht auf dem eigenen Rechner bleibt
    # (Art-Net, sACN, OSC, OS2L, Web-Fernbedienung), wird notiert und abgelehnt.
    import socket
    def _lokal(sock, adresse):
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            return True
        host = adresse[0] if isinstance(adresse, tuple) and adresse else ""
        return str(host).startswith("127.") or host in ("::1", "localhost")
    def _wache(name):
        echt = getattr(socket.socket, name)
        def ersatz(self, *a, **k):
            adresse = a[-1] if a else None
            if not _lokal(self, adresse):
                geoeffnet.append(["netz", [name, repr(adresse)]])
                raise OSError("TOOL-27: der Test oeffnet kein Netz")
            return echt(self, *a, **k)
        setattr(socket.socket, name, ersatz)
    for _n in ("bind", "connect", "connect_ex", "sendto"):
        _wache(_n)
    # MIDI: Ports AUFZAEHLEN ist erlaubt, OEFFNEN nicht.
    try:
        import rtmidi
        def _kein_midi(basis, art):
            class _Zu(basis):
                def open_port(self, *a, **k):
                    geoeffnet.append(["midi", [art] + [str(x) for x in a]])
                    raise RuntimeError("TOOL-27: der Test oeffnet kein MIDI-Geraet")
                def open_virtual_port(self, *a, **k):
                    geoeffnet.append(["midi", [art, "virtuell"]])
                    raise RuntimeError("TOOL-27: der Test oeffnet kein MIDI-Geraet")
            return _Zu
        rtmidi.MidiIn = _kein_midi(rtmidi.MidiIn, "ein")
        rtmidi.MidiOut = _kein_midi(rtmidi.MidiOut, "aus")
    except Exception:
        pass

    if os.environ.get("TOOL27_MODUS") == "ohne":
        # Gegenprobe: die gemeinsame Stelle ist ausgehebelt — das Werkzeug laeuft
        # so, wie es vor TOOL-27 lief.
        attrappe = types.ModuleType("_werkzeug_sandbox")
        attrappe.SCHALTER_ECHTE_DATEN = "--echte-daten"
        attrappe.ECHTE_DATEN = False
        sys.modules["_werkzeug_sandbox"] = sys.modules["tools._werkzeug_sandbox"] = attrappe

    def _bericht():
        ausgaenge = show_db = datenordner = None
        zustand = sys.modules.get("src.core.app_state")
        gebaut = False
        if zustand is not None:
            show_db = getattr(zustand, "SHOW_DB_PATH", None)
            st = getattr(zustand, "_state", None)     # NICHT get_state(): nichts neu bauen
            gebaut = st is not None
            try:
                ausgaenge = len(st.output_manager.ausgabe_status()) if gebaut else None
            except Exception as e:
                ausgaenge = "Fehler: %r" % (e,)
        pfade = sys.modules.get("src.core.paths")
        if pfade is not None:
            datenordner = pfade.app_data_dir()
        sandbox = sys.modules.get("_werkzeug_sandbox")
        haupt = sys.modules.get("__main__")
        with open("%s.%d" % (_ziel, os.getpid()), "w", encoding="utf-8") as f:
            json.dump({
                "geoeffnet": geoeffnet, "ausgaenge": ausgaenge,
                "app_state_geladen": gebaut,
                "show_db": show_db, "datenordner": datenordner,
                "wurzel": getattr(sandbox, "WURZEL", None),
                "hauptmodul": getattr(haupt, "__file__", None),
                "umgebung": {k: v for k, v in os.environ.items()
                             if k.startswith("LIGHTOS_")},
            }, f)
    atexit.register(_bericht)
'''


def _nackt(name: str, tmp: str, env: dict, modus: str, *argumente: str,
           timeout: int = 280):
    """Startet ``tools/<name>`` so, wie es jemand im Terminal tut — als
    eigenes Skript, aus einem FREMDEN Arbeitsordner. Der Mitschreiber kommt als
    ``sitecustomize`` ueber ``PYTHONPATH`` in den Prozess."""
    ort = os.path.join(tmp, "mitschreiber")
    os.makedirs(ort, exist_ok=True)
    with open(os.path.join(ort, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(_MITSCHREIBER)
    ziel = os.path.join(tmp, "ergebnis.json")
    env = dict(env, PYTHONPATH=ort, TOOL27_ERGEBNIS=ziel, TOOL27_MODUS=modus,
               PYTHONDONTWRITEBYTECODE="1")
    lauf = subprocess.run([sys.executable, str(TOOLS / name), *argumente], env=env,
                          cwd=tmp, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    berichte = sorted(n for n in os.listdir(tmp) if n.startswith("ergebnis.json."))
    erg = None
    if berichte:
        with open(os.path.join(tmp, berichte[0]), encoding="utf-8") as f:
            erg = json.load(f)
        erg["code"] = lauf.returncode
        erg["prozesse"] = len(berichte)
    return lauf, erg


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
        heim_vorher = set(_stand(os.path.join(tmp, "heim")))
        if modus == "ohne":
            # Die Gegenprobe soll die Show-Datenbank anfassen, nicht das Rig:
            # die Schalter, die sonst die Sandbox setzt, kommen hier von aussen.
            env.update({"LIGHTOS_SERIAL_INPROC": "1", "LIGHTOS_NO_OUTPUT_THREAD": "1",
                        "LIGHTOS_KEIN_USB": "1", "LIGHTOS_NO_AUDIO_AUTOSTART": "1",
                        "LIGHTOS_NO_DATENUMZUG": "1"})
        ziel = os.path.join(tmp, "bericht.txt")
        argumente = ["--ausgabe", ziel] if schreibend else ["--check"]
        lauf, erg = _nackt(name, tmp, env, modus, *argumente)
        assert erg is not None, (lauf.returncode, (lauf.stdout or "")[-2000:],
                                 (lauf.stderr or "")[-3000:])
        heim = os.path.join(tmp, "heim")
        return {"erg": erg, "name": name, "vorher": vorher, "nachher": _stand(daten), "daten": daten,
                "heim_neu": sorted(set(_stand(heim)) - heim_vorher),
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
        # Auch sonst nirgends im Home (~/LightOS, ~/.config/LightOS …). Fremde
        # Caches (fontconfig, Qt) sind nicht gemeint.
        self.assertEqual([n for n in r["heim_neu"] if "lightos" in n.lower()], [],
                         "im Home des Bedieners ist ausserhalb des Datenordners "
                         "etwas von LightOS entstanden")
        self.assertEqual(erg["geoeffnet"], [],
                         "ein Port/USB-/MIDI-Geraet/Netz-Socket/Kindprozess wurde angefasst")
        self.assertEqual(erg["prozesse"], 1, "das Werkzeug hat weitere Python-Prozesse gestartet")
        self.assertEqual(os.path.basename(erg["hauptmodul"] or ""), r["name"],
                         "das Werkzeug lief nicht als eigenes Skript")
        self.assertEqual(erg["umgebung"].get("LIGHTOS_NO_MIDI_AUTOCONNECT"), "1")
        self.assertEqual(erg["ausgaenge"], 0, "ein Ausgang ist eingerichtet")
        self.assertFalse(_innerhalb(erg["show_db"], r["daten"]), erg["show_db"])
        self.assertFalse(_innerhalb(erg["datenordner"], r["daten"]), erg["datenordner"])
        self.assertTrue(_innerhalb(erg["show_db"], r["temp"]), erg["show_db"])
        for var in ("LIGHTOS_NO_OUTPUT_THREAD", "LIGHTOS_SERIAL_INPROC", "LIGHTOS_KEIN_USB"):
            self.assertEqual(erg["umgebung"].get(var), "1", var)
        if sys.platform != "win32":
            # Unter Windows haelt eine noch offene SQLite-Datei das Loeschen auf;
            # den Rest nimmt dort ein spaeterer Lauf mit (_alte_reste_entfernen).
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


class MidiAutoconnectSchalterTest(unittest.TestCase):
    """Ein Werkzeug mit Hauptfenster (``_run_showcase_app``, die Capture-Skripte)
    oeffnete nach 800 ms alle MIDI-Eingaenge des Rechners. Die Sandbox setzt
    ``LIGHTOS_NO_MIDI_AUTOCONNECT``; das Hauptfenster haelt sich daran."""

    def _rufe(self, gesetzt: bool) -> list:
        from src.core.midi import midi_manager
        from src.ui.main_window import MainWindow
        gerufen = []

        class _Manager:
            _inputs: dict = {}

            def open_all_inputs(self):
                gerufen.append("open_all_inputs")

        alt_fn = midi_manager.get_midi_manager
        alt_env = os.environ.get("LIGHTOS_NO_MIDI_AUTOCONNECT")
        midi_manager.get_midi_manager = lambda: _Manager()
        try:
            if gesetzt:
                os.environ["LIGHTOS_NO_MIDI_AUTOCONNECT"] = "1"
            else:
                os.environ.pop("LIGHTOS_NO_MIDI_AUTOCONNECT", None)
            MainWindow._auto_connect_midi(object())
        finally:
            midi_manager.get_midi_manager = alt_fn
            if alt_env is None:
                os.environ.pop("LIGHTOS_NO_MIDI_AUTOCONNECT", None)
            else:
                os.environ["LIGHTOS_NO_MIDI_AUTOCONNECT"] = alt_env
        return gerufen

    def test_mit_schalter_oeffnet_das_hauptfenster_keinen_midi_eingang(self):
        self.assertEqual(self._rufe(True), [])

    def test_ohne_schalter_bleibt_der_autoconnect(self):
        self.assertEqual(self._rufe(False), ["open_all_inputs"])


class AusgabeZielTest(unittest.TestCase):
    """``--ausgabe``: der schreibende Modus laesst sich vom Repo weglenken."""

    def test_beide_werkzeuge_kennen_ausgabe(self):
        for name in ("audit_tooltip_coverage.py", "ui_verification_checklist.py"):
            with self.subTest(name):
                self.assertIn('"--ausgabe"', (TOOLS / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
