"""TOOL-3: zwei Generatoren mit bruechigen Annahmen (Befund PROC-07).

**(a) CWD-relativ statt repo-relativ.** ``build_full_show.py`` schrieb als
einziger Generator ``os.path.join("shows", "APC_Demo_Show.lshow")`` (und
genauso ``data/midi_mappings.json``) — aus einem anderen Verzeichnis
gestartet landete die Show woanders. Der Waechter unten prueft ALLE
Werkzeuge, nicht nur dieses.

**(b) Rohe Profil-ID.** ``build_spot90_testshow.py`` trug
``PROFIL = 1698``. Eine Profil-ID ist eine SQLite-Auto-ID; auf jedem Rechner
mit einer anders gewachsenen Bibliothek zeigt sie auf ein anderes Geraet oder
ins Leere — und das Werkzeug merkte es nicht. Jetzt loest
``tools/_profil.profil_id`` ueber Hersteller + Modell auf und scheitert laut.

**TOOL-6 (Folgepunkt aus dem Review von #841):** der Waechter zu (a) kannte
nur ``os.path.join("shows", ...)``. ``Path("shows")``, ``open("data/...")``,
f-Strings und ein relativer Pfad, der ueber eine Modul-Konstante an einen
Dateisystem-Aufruf ging, rutschten durch — und genau so schrieben drei
Generatoren (``build_dimmer_farbe_combo``, ``build_neuheiten_demo``,
``build_zq06121_demo``) ihre Show ueber ``build_and_verify(b, "shows/...")``
ab dem Arbeitsverzeichnis. Jetzt prueft er alle Dateisystem-Aufrufe aus
``_PFAD_AUFRUFE``, auch in Unterordnern von ``tools/``.
"""
import ast
import os
import subprocess
import sys
import tempfile
import unittest

from sqlalchemy.orm import Session

from _fixture_quelle import frische_library     # FIXTEST-FRESH

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
SPOT90 = os.path.join(TOOLS, "build_spot90_testshow.py")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

#: Ordner, deren Pfad ein Werkzeug nie relativ zum Arbeitsverzeichnis bauen darf.
REPO_ORDNER = ("shows", "data", "docs", "fixtures", "assets")

#: TOOL-6: Aufrufe, die ihren Pfad direkt im Dateisystem benutzen —
#: ``{Aufruf: Positionen der Pfad-Argumente}``. Bis TOOL-6 kannte der Waechter
#: nur ``os.path.join``; ``Path("shows")``, ``open("data/...")`` und ein
#: relativer Pfad, der ueber eine Konstante an ``build_and_verify`` ging,
#: rutschten durch. Bei Quelle -> Ziel (umbenennen, kopieren, verschieben)
#: zaehlen BEIDE Pfade — das Ziel ist der, der woanders landet (Review #849).
_EIN = (0,)
_ZWEI = (0, 1)
_PFAD_AUFRUFE = {
    "os.path.join": _EIN, "open": _EIN, "io.open": _EIN,
    "Path": _EIN, "pathlib.Path": _EIN, "PurePath": _EIN, "pathlib.PurePath": _EIN,
    "os.listdir": _EIN, "os.scandir": _EIN, "os.makedirs": _EIN, "os.mkdir": _EIN,
    "os.remove": _EIN, "os.unlink": _EIN, "os.rename": _ZWEI, "os.replace": _ZWEI,
    "os.path.exists": _EIN, "os.path.isfile": _EIN, "os.path.isdir": _EIN,
    "os.path.getsize": _EIN, "os.path.getmtime": _EIN,
    "os.path.abspath": _EIN, "os.path.realpath": _EIN,
    "shutil.copy": _ZWEI, "shutil.copy2": _ZWEI, "shutil.copyfile": _ZWEI,
    "shutil.copytree": _ZWEI, "shutil.move": _ZWEI, "shutil.rmtree": _EIN,
    "glob.glob": _EIN, "glob.iglob": _EIN, "sqlite3.connect": _EIN,
    "save_show": _EIN, "load_show": _EIN, "build_and_verify": (1,),
}

#: Bewusst CWD-relativ — ``(Datei relativ zu tools/, Aufruf)`` -> Grund.
# XPLAT-44: die einzige Ausnahme (Sandbox spiegelte den CWD-relativen
# ``data/midi_mappings.json`` der App) ist weg — die App benutzt den
# App-Datenordner, die Sandbox fragt ``paths.user_data_file`` ab.
_AUSNAHMEN: dict = {}


def _ist_repo_relativ(wert):
    if not isinstance(wert, str):
        return False
    w = wert.replace("\\", "/")
    return w in REPO_ORDNER or any(w.startswith(o + "/") for o in REPO_ORDNER)


def _relativer_anfang(knoten, konstanten):
    """Der Ausdruck beginnt mit einem nackten Repo-Ordner: Konstante,
    f-String, ``"shows/" + name`` oder ein Modul-Name, dem so etwas
    zugewiesen wurde (``OUT = "shows/X.lshow"``)."""
    if isinstance(knoten, ast.Constant):
        return _ist_repo_relativ(knoten.value)
    if isinstance(knoten, ast.JoinedStr) and knoten.values:
        return _relativer_anfang(knoten.values[0], konstanten)
    if isinstance(knoten, ast.BinOp) and isinstance(knoten.op, ast.Add):
        return _relativer_anfang(knoten.left, konstanten)
    if isinstance(knoten, ast.Name):
        return knoten.id in konstanten
    return False


#: Aufrufe, deren blosser Name (ohne Modul) schon eindeutig ist — sie werden
#: auch erkannt, wenn sie unter anderem Namen importiert sind.
_NACKTE_NAMEN = {n for n in _PFAD_AUFRUFE if "." not in n}

_BEREICHE = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
             ast.ClassDef)


def _import_aliase(baum):
    """``{lokaler Name: voller Name}`` aus ``import``/``from … import``.

    Review A zu #849: ``import os.path as osp`` / ``from shutil import copy``
    machten aus ``os.path.join`` ein ``osp.join``, aus ``shutil.copy`` ein
    ``copy`` — der Waechter kannte beide Schreibweisen nicht."""
    aliase = {}
    for k in ast.walk(baum):
        if isinstance(k, ast.Import):
            for a in k.names:
                if a.asname:
                    aliase[a.asname] = a.name
        elif isinstance(k, ast.ImportFrom) and k.module and not k.level:
            for a in k.names:
                aliase[a.asname or a.name] = f"{k.module}.{a.name}"
    return aliase


def _pfad_stellen(func, aliase):
    """Positionen der Pfad-Argumente dieses Aufrufs — ``()`` wenn er keiner
    aus ``_PFAD_AUFRUFE`` ist (auch unter einem Import-Alias)."""
    roh = ast.unparse(func)
    kopf, _, rest = roh.partition(".")
    voll = aliase.get(kopf)
    aufgeloest = (f"{voll}.{rest}" if rest else voll) if voll else roh
    for name in (aufgeloest, roh, aufgeloest.rsplit(".", 1)[-1]):
        if name in _PFAD_AUFRUFE and ("." in name or name in _NACKTE_NAMEN):
            return _PFAD_AUFRUFE[name]
    return ()


def _namen_im_bereich(bereich):
    """``(relativ, alle)`` — Namen, die IN DIESEM Bereich (ohne verschachtelte
    Funktionen) zugewiesen werden, und welche davon einen nackten Repo-Pfad
    bekommen. Parameter zaehlen mit (ein Vorgabewert ``"shows/…"`` ist relativ)."""
    relativ, alle = set(), set()
    if isinstance(bereich, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = bereich.args
        params = a.posonlyargs + a.args + a.kwonlyargs
        alle.update(x.arg for x in params)
        vorgaben = list(zip(reversed(a.posonlyargs + a.args), reversed(a.defaults)))
        vorgaben += [(x, d) for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None]
        relativ.update(x.arg for x, d in vorgaben if _relativer_anfang(d, set()))
    stapel = list(ast.iter_child_nodes(bereich))
    while stapel:
        k = stapel.pop()
        if isinstance(k, _BEREICHE):
            continue                     # eigener Bereich, eigene Namen
        if isinstance(k, (ast.Assign, ast.AnnAssign)) and k.value is not None:
            ziele = k.targets if isinstance(k, ast.Assign) else [k.target]
            for z in ziele:
                if isinstance(z, ast.Name):
                    alle.add(z.id)
                    if _relativer_anfang(k.value, set()):
                        relativ.add(z.id)
        stapel.extend(ast.iter_child_nodes(k))
    return relativ, alle


def _cwd_relative_pfade(pfad, ausnahmen=None):
    """Pfade, die ein Werkzeug relativ zum Arbeitsverzeichnis baut: ein
    Dateisystem-Aufruf (``_PFAD_AUFRUFE``, auch unter Import-Alias), dessen
    Pfad mit einem nackten Repo-Ordner beginnt statt mit einem Repo-Root —
    direkt oder ueber eine Variable des eigenen oder eines umgebenden
    Bereichs (Modul, Funktion)."""
    with open(pfad, encoding="utf-8", errors="replace") as f:
        try:
            baum = ast.parse(f.read(), filename=pfad)
        except SyntaxError:
            return []
    rel = os.path.relpath(pfad, TOOLS).replace(os.sep, "/")
    ausnahmen = _AUSNAHMEN if ausnahmen is None else ausnahmen
    aliase = _import_aliase(baum)
    treffer = []

    def ist_relativ(name, kette):
        for relativ, alle in reversed(kette):
            if name in alle:             # innerster Bereich, der ihn setzt
                return name in relativ
        return False

    def besuche(knoten, kette):
        if isinstance(knoten, _BEREICHE):
            kette = kette + [_namen_im_bereich(knoten)]
        if isinstance(knoten, ast.Call):
            stellen = _pfad_stellen(knoten.func, aliase)
            sichtbar = {n.id for s in stellen if s < len(knoten.args)
                        for n in ast.walk(knoten.args[s])
                        if isinstance(n, ast.Name) and ist_relativ(n.id, kette)}
            if (any(s < len(knoten.args) and _relativer_anfang(knoten.args[s], sichtbar)
                    for s in stellen)
                    and (rel, ast.unparse(knoten)) not in ausnahmen):
                treffer.append(f"{rel}:{knoten.lineno}  {ast.unparse(knoten)}")
        for kind in ast.iter_child_nodes(knoten):
            besuche(kind, kette)

    besuche(baum, [])
    return sorted(treffer, key=lambda z: int(z.split(":")[1].split()[0]))


def _werkzeuge():
    """Alle lebenden Werkzeuge — auch in Unterordnern, ohne ``_archiv``."""
    for wurzel, ordner, dateien in os.walk(TOOLS):
        ordner[:] = sorted(o for o in ordner if o not in ("_archiv", "__pycache__"))
        for d in sorted(dateien):
            if d.endswith(".py"):
                yield os.path.join(wurzel, d)


class KeinWerkzeugBautCwdRelativePfade(unittest.TestCase):

    def test_alle_werkzeuge_repo_relativ(self):
        treffer = []
        for pfad in _werkzeuge():
            treffer += _cwd_relative_pfade(pfad)
        self.assertEqual(treffer, [], (
            "Pfad relativ zum Arbeitsverzeichnis — aus einem anderen Ordner "
            "gestartet landet die Datei woanders. Repo-Root voranstellen:\n  "
            + "\n  ".join(treffer)))

    def test_der_scanner_erkennt_das_muster(self):
        """Positivkontrolle — sonst waere der Waechter oben leer gruen."""
        with tempfile.TemporaryDirectory() as tmp:
            probe = os.path.join(tmp, "probe.py")
            with open(probe, "w", encoding="utf-8") as f:
                f.write('import os\nOUT = os.path.join("shows", "X.lshow")\n'
                        '_R = "/r"\nOK = os.path.join(_R, "shows", "X.lshow")\n')
            self.assertEqual(len(_cwd_relative_pfade(probe)), 1)

    def test_der_scanner_erkennt_die_weiteren_formen(self):
        """TOOL-6: die Formen, die der erste Waechter nicht sah — und ihre
        repo-relativen Gegenstuecke, die er nicht melden darf."""
        quelle = (
            'import os, json, pathlib, shutil\n'
            'from pathlib import Path\n'
            'OUT = "shows/X.lshow"\n'                          # 3  ueber Konstante
            'ROOT = Path(__file__).resolve().parent.parent\n'
            'a = Path("shows") / "X.lshow"\n'                  # 5
            'b = pathlib.Path("data/midi.json")\n'             # 6
            'c = open("data/midi.json", encoding="utf-8")\n'   # 7
            'd = json.load(open(f"shows/{OUT}"))\n'            # 8
            'build_and_verify(b, OUT, name="X")\n'             # 9
            'build_and_verify(b, "docs/a.lshow")\n'            # 10
            'e = os.path.exists("fixtures/" + "x")\n'          # 11
            'os.rename(tmp, "data/ergebnis.json")\n'           # 12 Ziel
            'shutil.copy(quelle, f"shows/{OUT}")\n'            # 13 Ziel
            'shutil.move("data/alt.json", ziel)\n'             # 14 Quelle
            'f = ROOT / "shows" / "X.lshow"\n'                 # ok
            'g = open(os.path.join(ROOT, "data", "m.json"))\n'  # ok
            'h = Path(ROOT, "shows")\n'                        # ok
            'i = print("shows/X.lshow")\n'                     # ok: kein Pfad-Aufruf
            'j = d.get("fixtures")\n')                         # ok
        with tempfile.TemporaryDirectory() as tmp:
            probe = os.path.join(tmp, "probe.py")
            with open(probe, "w", encoding="utf-8") as f:
                f.write(quelle)
            zeilen = sorted(int(t.split(":")[1].split()[0])
                            for t in _cwd_relative_pfade(probe, ausnahmen={}))
        self.assertEqual(zeilen, [5, 6, 7, 8, 9, 10, 11, 12, 13, 14])

    def test_lokale_variablen_und_import_aliase(self):
        """Review A zu #849: der Waechter las Variablen nur auf Modulebene und
        kannte keine Import-Aliase. Jetzt je Bereich (mit Verdeckung) und
        ueber ``import … as`` / ``from … import``."""
        quelle = (
            'import os.path as osp\n'                          # 1
            'from shutil import copy as kopiere\n'             # 2
            'from pathlib import Path as P\n'                  # 3
            'from os.path import join\n'                       # 4
            'OUT = "shows/a.lshow"\n'                          # 5
            'def bauen():\n'                                   # 6
            '    ziel = "shows/X.lshow"\n'                     # 7
            '    return open(ziel)\n'                          # 8  lokal
            'def mit_vorgabe(out="data/m.json"):\n'            # 9
            '    return open(out)\n'                           # 10 Parameter
            'def verdeckt():\n'                                # 11
            '    ziel = osp.join(ROOT, "shows")\n'             # 12 ok: gerootet
            '    OUT = osp.join(ROOT, "shows", "a.lshow")\n'   # 13 ok
            '    open(ziel); save_show(OUT)\n'                 # 14 ok: verdeckt
            'osp.join("shows", "x")\n'                         # 15 Alias
            'kopiere(quelle, "data/x")\n'                      # 16 Alias, Ziel
            'P("docs")\n'                                      # 17 Alias
            'join("fixtures", "y")\n'                          # 18 from-import
            'save_show(OUT)\n')                                # 19 Modul-Konstante
        with tempfile.TemporaryDirectory() as tmp:
            probe = os.path.join(tmp, "probe.py")
            with open(probe, "w", encoding="utf-8") as f:
                f.write(quelle)
            zeilen = [int(t.split(":")[1].split()[0])
                      for t in _cwd_relative_pfade(probe, ausnahmen={})]
        self.assertEqual(zeilen, [8, 10, 15, 16, 17, 18, 19])

    def test_ausnahmen_gibt_es_noch(self):
        """Eine Ausnahme, deren Aufruf verschwunden ist, gehoert gestrichen."""
        gesehen = set()
        for pfad in _werkzeuge():
            rel = os.path.relpath(pfad, TOOLS).replace(os.sep, "/")
            gefunden = _cwd_relative_pfade(pfad, ausnahmen={})
            for datei, aufruf in _AUSNAHMEN:
                if datei == rel and any(aufruf in t for t in gefunden):
                    gesehen.add((datei, aufruf))
        self.assertEqual(sorted(set(_AUSNAHMEN) - gesehen), [])


class KeineRoheProfilId(unittest.TestCase):

    def test_spot90_traegt_keine_profil_zahl(self):
        with open(SPOT90, encoding="utf-8") as f:
            baum = ast.parse(f.read(), filename=SPOT90)
        roh = []
        for k in ast.walk(baum):
            if isinstance(k, ast.keyword) and k.arg == "fixture_profile_id" \
                    and isinstance(k.value, ast.Constant):
                roh.append(f"Zeile {k.value.lineno}: fixture_profile_id={k.value.value}")
            if isinstance(k, ast.Assign):
                namen = [t for t in k.targets if isinstance(t, (ast.Name, ast.Tuple))]
                for t in namen:
                    elts = t.elts if isinstance(t, ast.Tuple) else [t]
                    werte = (k.value.elts if isinstance(k.value, ast.Tuple)
                             and isinstance(t, ast.Tuple) else [k.value])
                    for n, v in zip(elts, werte):
                        if (isinstance(n, ast.Name) and "PROFIL" in n.id.upper()
                                and isinstance(v, ast.Constant) and isinstance(v.value, int)):
                            roh.append(f"Zeile {k.lineno}: {n.id} = {v.value}")
        self.assertEqual(roh, [], "rohe, rechnerabhaengige Profil-ID im Generator")


class ProfilUeberDenNamen(unittest.TestCase):
    """``tools/_profil.profil_id`` gegen eine frisch geseedete Bibliothek —
    nicht gegen die gewachsene dieses Rechners (``tests/_fixture_quelle.py``)."""

    def setUp(self):
        from src.core.database.models import (FixtureMode, FixtureProfile,
                                              Manufacturer)
        self.motor = frische_library(self)
        with Session(self.motor) as s:
            herst = Manufacturer(name="TOOL3 Pruefhersteller")
            s.add(herst)
            s.flush()
            # Zwei Profile mit demselben Namen: der Import zuerst angelegt
            # (kleinere ID), das builtin danach — das builtin muss gewinnen.
            importiert = FixtureProfile(manufacturer_id=herst.id, name="Pruefspot",
                                        source="qlcplus")
            s.add(importiert)
            s.flush()
            eingebaut = FixtureProfile(manufacturer_id=herst.id, name="Pruefspot",
                                       source="builtin")
            s.add(eingebaut)
            s.flush()
            for prof in (importiert, eingebaut):
                s.add(FixtureMode(fixture_id=prof.id, name="16 Channel", channel_count=16))
                s.add(FixtureMode(fixture_id=prof.id, name="8 Channel", channel_count=8))
            s.commit()
            self.pid_import, self.pid_builtin = importiert.id, eingebaut.id

    def test_loest_ueber_namen_auf_builtin_gewinnt(self):
        from _profil import profil_id
        self.assertLess(self.pid_import, self.pid_builtin)
        self.assertEqual(profil_id("TOOL3 Pruefhersteller", "Pruefspot",
                                   modus="16 Channel", kanaele=16), self.pid_builtin)

    def test_fehlendes_geraet_scheitert_laut(self):
        from _profil import profil_id
        with self.assertRaises(SystemExit) as ctx:
            profil_id("TOOL3 Pruefhersteller", "Gibt es nicht")
        self.assertIn("Gibt es nicht", str(ctx.exception.code))
        self.assertIn("fehlt", str(ctx.exception.code))

    def test_fehlender_modus_nennt_die_vorhandenen(self):
        from _profil import profil_id
        with self.assertRaises(SystemExit) as ctx:
            profil_id("TOOL3 Pruefhersteller", "Pruefspot", modus="20 Channel")
        meldung = str(ctx.exception.code)
        self.assertIn("20 Channel", meldung)
        self.assertIn("16 Channel", meldung)
        self.assertIn("8 Channel", meldung)

    def test_falsche_kanalzahl_scheitert_laut(self):
        from _profil import profil_id
        with self.assertRaises(SystemExit) as ctx:
            profil_id("TOOL3 Pruefhersteller", "Pruefspot", modus="8 Channel", kanaele=16)
        self.assertIn("erwartet 16", str(ctx.exception.code))


class Spot90OhneGeraetBautNichts(unittest.TestCase):
    """Der Generator selbst, gegen eine Bibliothek OHNE das Geraet: er muss
    vor dem Patch stehen bleiben und sagen, was fehlt — statt eine Show mit
    einem falschen oder leeren Geraet zu speichern."""

    def test_bricht_laut_ab_und_schreibt_keine_show(self):
        """FM-57: der Hero Spot 90 ist seitdem mitgeliefert
        (``fixtures/bibliothek/varytec/hero-spot-90.json``) und wird beim Start
        des Generators eingespielt. Ihn nur aus der DB zu loeschen reichte nicht
        — der Start spielte die Datei sofort wieder ein. Deshalb laeuft der
        Generator gegen eine KOPIE der Bibliothek ohne genau diese Datei
        (``LIGHTOS_BIBLIOTHEK_DIR``); alle anderen Geraete bleiben da."""
        import shutil
        from src.core.database import bibliothek_format as BF
        datei = os.path.join("varytec", "hero-spot-90.json")
        self.assertTrue(os.path.isfile(os.path.join(BF.BIBLIOTHEK_DIR, datei)),
                        "Vorbedingung: die Bibliothek liefert den Hero Spot 90 — "
                        "sonst prueft der Test nichts mehr, was er nicht ohnehin saehe")
        motor = frische_library(self)
        with tempfile.TemporaryDirectory(prefix="lightos_tool3_") as tmp:
            bib = os.path.join(tmp, "bibliothek")
            shutil.copytree(BF.BIBLIOTHEK_DIR, bib)
            os.remove(os.path.join(bib, datei))
            ziel = os.path.join(tmp, "Spot90_Testshow.lshow")
            env = dict(os.environ)
            env.update({
                "LIGHTOS_BIBLIOTHEK_DIR": bib,
                "LIGHTOS_FIXTURE_DB": motor.url.database,
                "LIGHTOS_GEN_OUT": ziel,
                "LIGHTOS_SHOW_DB": os.path.join(tmp, "show.db"),
                "QT_QPA_PLATFORM": "offscreen",
                "PYTHONIOENCODING": "utf-8",
            })
            lauf = subprocess.run([sys.executable, SPOT90], cwd=REPO, env=env,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=300)
            ausgabe = lauf.stdout + lauf.stderr
            self.assertNotEqual(lauf.returncode, 0, ausgabe[-2000:])
            self.assertIn("Hero Spot 90", ausgabe)
            self.assertIn("fehlt", ausgabe)
            self.assertFalse(os.path.exists(ziel), "Show trotz fehlendem Geraet gespeichert")


if __name__ == "__main__":
    unittest.main()
