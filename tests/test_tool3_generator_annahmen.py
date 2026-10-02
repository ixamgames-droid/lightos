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


def _cwd_relative_pfade(pfad):
    """``os.path.join("<repo-ordner>", ...)`` — der erste Teil ein nackter
    Ordnername statt eines Repo-Roots."""
    with open(pfad, encoding="utf-8", errors="replace") as f:
        try:
            baum = ast.parse(f.read(), filename=pfad)
        except SyntaxError:
            return []
    treffer = []
    for k in ast.walk(baum):
        if (isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
                and k.func.attr == "join" and ast.unparse(k.func.value) == "os.path"
                and k.args and isinstance(k.args[0], ast.Constant)
                and k.args[0].value in REPO_ORDNER):
            treffer.append(f"{os.path.basename(pfad)}:{k.lineno}  {ast.unparse(k)}")
    return treffer


class KeinWerkzeugBautCwdRelativePfade(unittest.TestCase):

    def test_alle_werkzeuge_repo_relativ(self):
        treffer = []
        for name in sorted(os.listdir(TOOLS)):
            if name.endswith(".py"):
                treffer += _cwd_relative_pfade(os.path.join(TOOLS, name))
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
        motor = frische_library(self)
        with tempfile.TemporaryDirectory(prefix="lightos_tool3_") as tmp:
            ziel = os.path.join(tmp, "Spot90_Testshow.lshow")
            env = dict(os.environ)
            env.update({
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
