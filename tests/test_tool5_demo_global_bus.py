"""TOOL-5 (mit TOOL-4): zwei Werkzeug-Befunde aus DOC-17, beide gemessen.

**(a) ``tools/build_demo_show_full.py`` brach in der Selbstpruefung ab** —
nachdem die Show schon gespeichert war, mit
``AssertionError: Global-Bus fehlt: []``. Ursache: seit ENG-26 ist ``"Global"``
ein ALIAS des Default-Bus (``TempoBusManager.kanonische_bus_id``).
``ensure_bus("Global")`` legt deshalb keinen eigenen Bus an, und
``named_buses()`` listet den Default-Bus per Konstruktion nie. Die Pruefung
fragte nach etwas, das es nicht geben kann — der Generator meldete nie
„FERTIG", obwohl die Show richtig war.

**(b) ``capture_hochzeit_tempo_guide.py`` zielte auf geloeschte Bilder.**
DOC-17 hat ``docs/anleitung_hochzeit_tempo/img`` entfernt (die Anleitung nutzt
Tempo-Controller und ist bildlos); das Werkzeug schrieb trotzdem weiter dorthin
und erwartete die alten Multiplikator-Dials. Es liegt jetzt in
``tools/_archiv/``, schreibt nicht mehr nach ``docs/`` und sagt bei fehlenden
Dials, WELCHE Show es erwartet und was fehlt (TOOL-4) — statt eines nackten
``RuntimeError: Speed-Dial fehlt: Farb Wechsel``.
"""
import ast
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
GENERATOR = os.path.join(TOOLS, "build_demo_show_full.py")
MITGELIEFERT = os.path.join(REPO, "shows", "Demo_Show_Full.lshow")
CAPTURE_ALT = os.path.join(TOOLS, "capture_hochzeit_tempo_guide.py")
CAPTURE = os.path.join(TOOLS, "_archiv", "capture_hochzeit_tempo_guide.py")


def _sha(pfad):
    if not os.path.isfile(pfad):
        return None
    with open(pfad, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class GlobalIstAliasDesDefaultBus(unittest.TestCase):
    """Der Mechanismus, an dem die alte Pruefung scheiterte — festgehalten,
    damit niemand ``named_buses()`` wieder fuer die Bus-Lage haelt."""

    def test_global_ist_der_default_bus_und_nicht_benannt(self):
        from src.core.engine.tempo_bus import TempoBusManager

        mgr = TempoBusManager()
        bus = mgr.ensure_bus("Global", source="bpm_global")
        self.assertIs(bus, mgr.get(mgr.DEFAULT_BUS),
                      "ensure_bus('Global') muss den Default-Bus liefern (ENG-26)")
        self.assertEqual(bus.source, "bpm_global")
        self.assertNotIn("Global", [b.bus_id for b in mgr.named_buses()])
        self.assertNotIn(mgr.DEFAULT_BUS, [b.bus_id for b in mgr.named_buses()],
                         "named_buses() listet den Default-Bus nie — deshalb "
                         "kann eine Pruefung darueber 'Global' nicht finden")
        self.assertIs(mgr.bus_for_effect("Global"), bus,
                      "ein Effekt auf 'Global' muss den Default-Bus lesen")


class DemoGeneratorLaeuftBisFertig(unittest.TestCase):
    """Der Generator selbst, im Unterprozess, bis zu seiner letzten Zeile.

    ``LIGHTOS_GEN_OUT`` lenkt die Show in einen Wegwerf-Ordner um — die
    mitgelieferte ``shows/Demo_Show_Full.lshow`` darf der Test nicht anfassen.
    """

    def test_selbstpruefung_laeuft_durch(self):
        vorher = _sha(MITGELIEFERT)
        with tempfile.TemporaryDirectory(prefix="lightos_tool5_") as tmp:
            ziel = os.path.join(tmp, "Demo_Show_Full.lshow")
            env = dict(os.environ)
            env.update({
                "LIGHTOS_GEN_OUT": ziel,
                "LIGHTOS_SHOW_DB": os.path.join(tmp, "show.db"),
                "QT_QPA_PLATFORM": "offscreen",
                "PYTHONIOENCODING": "utf-8",
            })
            lauf = subprocess.run([sys.executable, GENERATOR], cwd=REPO, env=env,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=300)
            ausgabe = lauf.stdout + lauf.stderr
            self.assertNotIn("Global-Bus fehlt", ausgabe)
            self.assertEqual(lauf.returncode, 0,
                             f"Generator endete mit rc={lauf.returncode}:\n{ausgabe[-3000:]}")
            self.assertIn("FERTIG", lauf.stdout)
            self.assertIn("Global=bpm_global", lauf.stdout)
            self.assertTrue(os.path.isfile(ziel), "LIGHTOS_GEN_OUT wurde nicht beachtet")
        self.assertEqual(_sha(MITGELIEFERT), vorher,
                         "der Test hat die mitgelieferte Demo-Show veraendert")


def _capture_baum():
    with open(CAPTURE, encoding="utf-8") as f:
        return ast.parse(f.read(), filename=CAPTURE)


def _zuweisung(baum, name):
    for knoten in baum.body:
        if isinstance(knoten, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in knoten.targets):
            return knoten
    return None


class HochzeitCaptureIstStillgelegt(unittest.TestCase):

    def test_liegt_im_archiv(self):
        self.assertFalse(os.path.exists(CAPTURE_ALT),
                         "capture_hochzeit_tempo_guide.py liegt noch in tools/")
        self.assertTrue(os.path.isfile(CAPTURE))

    def test_schreibt_nicht_mehr_nach_docs(self):
        out = _zuweisung(_capture_baum(), "OUT")
        self.assertIsNotNone(out, "OUT-Zuweisung nicht gefunden")
        quelle = ast.unparse(out.value)
        self.assertNotIn("docs", quelle,
                         "das Werkzeug zielt weiter auf docs/ — die Anleitung ist "
                         "seit DOC-17 bildlos")

    def _meldungs_funktion(self):
        """``fehlende_dials_meldung`` samt Konstanten aus dem Quelltext holen —
        das Modul selbst zu importieren startet Qt nativ und sucht die private
        Show (SystemExit), beides gehoert nicht in einen Testlauf."""
        baum = _capture_baum()
        teile = [_zuweisung(baum, "SHOW_NAME"), _zuweisung(baum, "ERWARTETE_DIALS")]
        teile += [k for k in baum.body if isinstance(k, ast.FunctionDef)
                  and k.name == "fehlende_dials_meldung"]
        self.assertEqual(len([t for t in teile if t is not None]), 3,
                         "SHOW_NAME / ERWARTETE_DIALS / fehlende_dials_meldung fehlen")
        ns = {}
        exec(compile(ast.Module(body=teile, type_ignores=[]), CAPTURE, "exec"), ns)
        return ns["fehlende_dials_meldung"]

    def test_tool4_meldung_nennt_show_und_fehlendes(self):
        meldung = self._meldungs_funktion()({"An Aus": object(), "Tempo": object()})
        self.assertIn("hochzeit.lshow", meldung)
        self.assertIn("'Farb Wechsel'", meldung)
        self.assertIn("Vorhanden:", meldung)
        self.assertIn("'Tempo'", meldung)
        self.assertNotIn("'An Aus'", meldung.split("Vorhanden:")[0],
                         "ein vorhandenes Dial wird als fehlend gemeldet")

    def test_tool4_alles_da_keine_meldung(self):
        meldung = self._meldungs_funktion()({"Farb Wechsel": 1, "An Aus": 2})
        self.assertEqual(meldung, "")

    def test_kein_nackter_runtimeerror_mehr(self):
        with open(CAPTURE, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn('RuntimeError(f"Speed-Dial fehlt', text)


if __name__ == "__main__":
    unittest.main()
