"""UI-106: „Universum“ auch im Patch-Dialog, im Output- und DMX-Monitor und in
den Statusmeldungen der Ausgabe (Rest aus UI-100, #1134).

Befund: UI-100 hatte den Ausgabe-Dialog eingedeutscht, die Statuszeilen aber
bewusst ausgeklammert. Danach sagte die Oberflaeche noch „Universe:“ im
Patch-Dialog, im Output-Monitor und im DMX-Monitor, die Statuszeilen meldeten
„Verbunden: COM3 → Universe 1“, „war Universe 2 — jetzt Universe 1“,
„⚠ Universe 1 hat keinen Ausgang“, „Enttec: … erkannt, kein Universe“; der
Dialog „Show prüfen“ meldete „Ungültige Universe-Nummer“ und „Universe N“.

Festgehalten wird:
  * die neuen Begriffe stehen in den Dialogen und Meldungen (am Widget bzw. am
    Rueckgabewert gemessen),
  * kein angezeigter Text in den betroffenen Modulen enthaelt das Wort
    „Universe“ — gemessen an ALLEN String-Literalen der Module (ohne
    Docstrings und ``print``-Logzeilen), mit Gegenprobe am alten Quelltext,
  * die gespeicherten Namen bleiben: eine neue Zeile heisst weiter
    „Universe N“ (Feld ``name`` in ``universes.json``) — das ist Nutzerdatum,
    kein Anzeigetext.

„Merge-Modus“ (HTP/LTP) bleibt Fachbegriff. Nicht Teil dieses Items: Simple
Desk, Geraete-Baum der Buehne/Gruppen, Kanalgruppen, VC-Regler und
Fixture-Generator — sie sagen weiter „Universe“ (eigener Punkt).
"""
from __future__ import annotations

import ast
import os
import pathlib
import re
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

from PySide6.QtWidgets import QApplication  # noqa: E402

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

# Dieselbe Sammel-Hilfe wie UI-100 — als Modul, damit pytest dessen Klassen
# hier nicht ein zweites Mal einsammelt.
import test_ui100_einheitliche_begriffe as ui100  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Wortgrenzen: „Universum“/„Universen“ schlagen nicht an, „Universe-Manager“ schon.
VERBOTEN = re.compile(r"\bUniverse\b")

#: Module, deren angezeigte Texte UI-106 eindeutscht.
MODULE = (
    "src/ui/views/patch_view.py",
    "src/ui/widgets/fixture_browser.py",
    "src/ui/views/output_view.py",
    "src/ui/views/dmx_monitor_view.py",
    "src/ui/monitor_ausgang.py",
    "src/core/dmx/adapter_zeilen.py",
    "src/core/dmx/enttec_pro.py",
    "src/ui/widgets/output_config.py",
    "src/ui/main_window.py",
    "src/core/app_state.py",
    "src/core/sync.py",
)

#: Gespeicherte Namen neuer Zeilen (``universes.json``, Feld ``name``) — bleiben.
ERLAUBT = {
    ("src/ui/widgets/output_config.py", 'f"Universe {num}"'),
    ("src/ui/widgets/output_config.py", 'f"Universe {row + 1}"'),
    ("src/ui/widgets/output_config.py", '"Universe"'),
}


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


def literal_funde(quelltext: str) -> list[tuple[int, str]]:
    """String-Literale mit „Universe“ — ohne Docstrings und ohne ``print``-Logs.

    Ergebnis: ``(zeile, Quelltext des Literals)``; f-Strings zaehlen als Ganzes.
    """
    baum = ast.parse(quelltext)
    zeilen = quelltext.splitlines()
    ausgenommen = set()
    for n in ast.walk(baum):
        if (isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                           ast.AsyncFunctionDef))
                and n.body and isinstance(n.body[0], ast.Expr)
                and isinstance(n.body[0].value, ast.Constant)):
            ausgenommen.add(id(n.body[0].value))
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "print"):
            ausgenommen.update(id(k) for k in ast.walk(n))
    funde = []
    for n in ast.walk(baum):
        if isinstance(n, ast.JoinedStr) and id(n) not in ausgenommen:
            teile = [k.value for k in n.values
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if any(VERBOTEN.search(t) for t in teile):
                ausgenommen.update(id(k) for k in n.values)
                funde.append((n.lineno, ast.get_source_segment(quelltext, n)
                              or zeilen[n.lineno - 1].strip()))
    for n in ast.walk(baum):
        if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in ausgenommen and VERBOTEN.search(n.value)):
            funde.append((n.lineno, ast.get_source_segment(quelltext, n)
                          or zeilen[n.lineno - 1].strip()))
    return sorted(funde)


class PrueferGegenprobeTest(unittest.TestCase):
    """Ohne diese Gegenprobe bewiese der gruene Quelltext-Lauf nichts."""

    ALT = '''
"""Docstring mit Universe darf bleiben."""
def f(univ, port, lbl):
    """auch hier: Universe."""
    print(f"[log] Universe {univ}")
    lbl.setText(f"Verbunden: {port} → Universe {univ} (gespeichert)")
    lbl.setText("Universe:")
    return f"war Universe {univ} — jetzt Universe 1"
'''
    NEU = ALT.replace('→ Universe', '→ Universum').replace(
        '"Universe:"', '"Universum:"').replace(
        'war Universe {univ} — jetzt Universe 1',
        'war Universum {univ} — jetzt Universum 1')

    def test_alte_texte_schlagen_an_docstrings_und_logs_nicht(self):
        funde = literal_funde(self.ALT)
        self.assertEqual([z for z, _ in funde], [6, 7, 8], funde)

    def test_neue_texte_schlagen_nicht_an(self):
        self.assertEqual(literal_funde(self.NEU), [])
        for t in ("Universum:", "Universen", "Universum 1 geht raus",
                  "Art-Net-Universum 3", "Merge-Modus:"):
            self.assertIsNone(VERBOTEN.search(t), t)
        self.assertIsNotNone(VERBOTEN.search("im Universe-Manager"))


class QuelltextTest(unittest.TestCase):

    def test_keine_angezeigten_englischen_universe_texte(self):
        rest = []
        for rel in MODULE:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for zeile, literal in literal_funde(text):
                if (rel, literal) not in ERLAUBT:
                    rest.append(f"{rel}:{zeile}: {literal}")
        self.assertEqual(rest, [])

    def test_ausnahmen_sind_noch_noetig(self):
        """Steht eine Ausnahme nicht mehr im Code, gehoert sie aus der Liste."""
        gefunden = set()
        for rel in {r for r, _ in ERLAUBT}:
            text = (ROOT / rel).read_text(encoding="utf-8")
            gefunden |= {(rel, lit) for _, lit in literal_funde(text)}
        self.assertEqual(ERLAUBT - gefunden, set())


class MeldungenTest(unittest.TestCase):

    def test_umzug_und_doppelter_adapter(self):
        from src.core.dmx import adapter_zeilen as az
        self.assertEqual(az.umzug_text([2], 1), "war Universum 2 — jetzt Universum 1")
        d = az.Doppelt("Enttec", "/dev/ttyUSB0", (1, 2))
        self.assertIn("steht auf Universum 1 und 2", d.text)
        self.assertIn("das richtige Universum", d.text)
        self.assertIsNone(VERBOTEN.search(d.text), d.text)
        st = az.stoerungen([d])[0]["problem"]
        self.assertIn("steht auf Universum", st)

    def test_monitor_aussagen(self):
        from src.ui import monitor_ausgang as ma
        faelle = [
            ma.aussage(3, [], False, angelegt=False),
            ma.aussage(1, [], False),
            ma.aussage(1, [{"universum": 1, "weg": "Enttec", "verbunden": False}], True),
            ma.aussage(1, [{"universum": 1, "weg": "Enttec", "zustand": "verbindet"}], True),
            ma.aussage(1, [{"universum": 1, "weg": "Enttec"}], False),
            ma.aussage(1, [{"universum": 1, "weg": "Enttec"}], True),
        ]
        texte = [a.text for a in faelle]
        self.assertEqual(texte[-1], "Universum 1 geht raus")
        self.assertTrue(texte[0].startswith("Universum 3 ist nicht angelegt"))
        self.assertTrue(texte[1].startswith("⚠ Universum 1 hat keinen Ausgang"))
        for t in texte:
            self.assertIsNone(VERBOTEN.search(t), t)

    def test_enttec_hinweise(self):
        from src.core.dmx import enttec_pro as ep
        with mock.patch.object(ep, "find_enttec_port", return_value="/dev/ttyUSB0"):
            leer = ep.diagnose_port("")
            fremd = ep.diagnose_port("COM_FAKE_UI106")
        self.assertIn("Fuer dieses Universum", leer)
        self.assertIn("Reiter „Universen“", fremd or "")
        for t in (leer, fremd or ""):
            self.assertIsNone(VERBOTEN.search(t), t)


class AnsichtenTest(unittest.TestCase):

    def setUp(self):
        _app()
        from src.core.show.show_file import reset_show
        reset_show()

    def _ohne_alt(self, w):
        texte = ui100.sichtbare_texte(w)
        self.assertEqual(ui100.treffer(texte, VERBOTEN), [])
        return texte

    def test_output_monitor(self):
        from src.ui.views.output_view import OutputView
        v = OutputView()
        self.addCleanup(v.deleteLater)
        self.assertIn("Universum:", self._ohne_alt(v))

    def test_dmx_monitor(self):
        from src.ui.views.dmx_monitor_view import DmxMonitorView
        v = DmxMonitorView()
        self.addCleanup(v.deleteLater)
        texte = self._ohne_alt(v)
        self.assertIn("Universum:", texte)
        self.assertTrue(any(t.startswith("Universum ") for t in texte), texte)

    def test_geraet_hinzufuegen(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.ui.widgets.fixture_browser import FixtureBrowserDialog
        ensure_builtins()
        d = FixtureBrowserDialog(1)
        self.addCleanup(d.deleteLater)
        self.assertIn("Universum:", self._ohne_alt(d))

    def test_patch_dialog(self):
        from src.core.app_state import get_state
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import PatchedFixture
        import src.ui.views.patch_view as PV
        ensure_builtins()
        st = get_state()
        st.add_fixture(PatchedFixture(fid=1, label="L", fixture_profile_id=1,
                                      mode_name="m", universe=1, address=1,
                                      channel_count=4, fixture_type="laser"))
        f = next(x for x in st.get_patched_fixtures() if x.fid == 1)
        import src.core.app_state as A
        ziele = [A] + ([PV] if hasattr(PV, "get_channels_for_patched") else [])
        for modul in ziele:
            p = mock.patch.object(modul, "get_channels_for_patched", lambda f: [])
            p.start()
            self.addCleanup(p.stop)
        d = PV.PatchFixtureEditDialog(st, f)
        self.addCleanup(d.deleteLater)
        texte = self._ohne_alt(d)
        self.assertIn("Universum:", texte)
        self.assertIn("DMX (Universum/Adresse)", texte)

    def test_neue_zeile_heisst_weiter_universe_n(self):
        """Gespeicherter Name bleibt englisch — er ist Nutzerdatum."""
        import json
        import tempfile
        import src.ui.widgets.output_config as oc
        fd, tmp = tempfile.mkstemp(suffix="_universes.json")
        os.close(fd)
        self.addCleanup(os.remove, tmp)
        with mock.patch.object(oc, "_UNIV_CONFIG_PATH", tmp):
            oc._save_universe_config([
                {"num": 1, "name": "Main", "output": "Disabled", "patch": ""}])
            from src.core.app_state import get_state
            st = get_state()
            with mock.patch.object(st, "apply_output_config", lambda *a, **k: None), \
                    mock.patch.object(oc, "QMessageBox"):
                dlg = oc.OutputConfigDialog()
                self.addCleanup(dlg.deleteLater)
                dlg._univ_add()
                dlg._univ_save()
            with open(tmp, encoding="utf-8") as fh:
                namen = [r["name"] for r in json.load(fh)]
        self.assertEqual(namen, ["Main", "Universe 2"])


if __name__ == "__main__":
    unittest.main()
