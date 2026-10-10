"""DEMO-8: Demo-Shows sind Teil des Produkts — im Setup mitgeliefert, per Menue
zu oeffnen.

1. **Bau-Skript** (``packaging/demo_shows.py``): erzeugt die Auswahl in einem
   Temp-Ordner, jede Show ist ``lint_show.py --strict``-sauber, traegt ihre
   Buehne im ``scene_graph`` und laedt headless in einem LEEREN Datenordner
   vollstaendig (die Buehnen-Datei entsteht dort aus der Show, VIZ-94). Der
   Bau laeuft in einer Sandbox: im Datenordner des aufrufenden Prozesses
   entsteht keine Buehne (TOOL-13). Die Laufzeit steht in der Testausgabe.
2. **App** (Datei -> „Demo-Show öffnen"): das Untermenue listet die Demos mit
   Kurzbeschreibung; Oeffnen laesst die Quelldatei unveraendert, die Show hat
   keinen Pfad und gilt als ungespeichert, „Speichern" fuehrt zu „Speichern
   unter" im Show-Ordner. Ohne Demo-Ordner: ausgegrauter Hinweis.
3. **Paketierung**: Bundle-Liste, Selbsttest, Spec-Daten, Workflow und
   ``.gitignore`` kennen den Ordner.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _modul(name: str, *teile: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_REPO, *teile))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod            # dataclasses brauchen das Modul per Name
    spec.loader.exec_module(mod)
    return mod


def _bau():
    return _modul("demo8_bauskript", "packaging", "demo_shows.py")


def _bundle_inhalt():
    return _modul("demo8_bundle_inhalt", "packaging", "windows", "bundle_inhalt.py")


def _lies(*teile: str) -> str:
    with open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _sha(pfad: str) -> str:
    with open(pfad, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _demo_ordner(ziel: str, shows: dict[str, tuple[str, str]], *,
                 inhalt: bytes | None = None) -> None:
    """Ein Demo-Ordner wie nach dem Bau: ``{datei: (titel, beschreibung)}``.
    ``inhalt`` = Bytes einer echten ``.lshow`` (sonst eine Minimal-ZIP)."""
    os.makedirs(ziel, exist_ok=True)
    for datei in shows:
        pfad = os.path.join(ziel, datei)
        if inhalt is not None:
            with open(pfad, "wb") as f:
                f.write(inhalt)
        else:
            with zipfile.ZipFile(pfad, "w") as z:
                z.writestr("show.json", json.dumps({"version": "1.2"}))
    with open(os.path.join(ziel, "demos.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "demos": [
            {"schluessel": d[:-6].lower(), "datei": d, "titel": t, "beschreibung": b}
            for d, (t, b) in shows.items()]}, f)


# ── 1. Bau-Skript ────────────────────────────────────────────────────────────

# Laedt jede Show in EINEM Prozess nacheinander — mit leerem Datenordner (die
# Umgebung baut der Test aus ``sandbox_umgebung``): keine Buehnen-Datei, keine
# Geraete-Bibliothek. So wie auf einem frisch installierten Rechner.
_LADE_TREIBER = r'''
import contextlib, io, json, os, sys
repo, pfade = sys.argv[1], sys.argv[2:]
sys.path.insert(0, repo); sys.path.insert(0, os.path.join(repo, "tools"))
import _gen_env  # noqa
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])
from src.core.show.show_file import load_show, letzte_ladeprobleme
from src.core.app_state import get_state
from src.core.stage.stage_definition import load_stage, stages_dir
from src.core.paths import app_data_dir
erg = {"app_data_dir": app_data_dir(), "shows": {}}
for pfad in pfade:
    with contextlib.redirect_stdout(io.StringIO()):
        ok, msg = load_show(pfad)
    st = get_state()
    name = st.active_stage_name if hasattr(st, "active_stage_name") else None
    with open(pfad, "rb") as f:
        import zipfile
        show = json.loads(zipfile.ZipFile(f).read("show.json"))
    name = (show.get("visualizer") or {}).get("active_stage")
    buehne = load_stage(name)
    erg["shows"][os.path.basename(pfad)] = {
        "ok": bool(ok), "msg": str(msg),
        "probleme": list(letzte_ladeprobleme() or []),
        "geraete": len(st.get_patched_fixtures()),
        "buehne": name,
        "buehnen_elemente": len(buehne.elements) if buehne is not None else -1,
    }
print("ERG=" + json.dumps(erg))
'''


class BauSkriptTest(unittest.TestCase):
    """Ein echter Bau aller Demos (rund eine halbe Minute) fuer die ganze Klasse."""

    @classmethod
    def setUpClass(cls):
        from src.core.paths import app_data_dir
        cls.bau = _bau()
        cls._tmp = tempfile.TemporaryDirectory(prefix="lightos_demo8_")
        cls.ziel = os.path.join(cls._tmp.name, "demo_shows")
        cls.eigene_stages = os.path.join(app_data_dir(), "stages")
        cls.stages_vorher = (sorted(os.listdir(cls.eigene_stages))
                             if os.path.isdir(cls.eigene_stages) else [])
        cls.meldungen: list[str] = []
        cls.fehler = None
        try:
            cls.ergebnis = cls.bau.baue(cls.ziel, melde=cls.meldungen.append)
        except Exception as e:                       # jeder Test meldet ihn
            cls.ergebnis, cls.fehler = None, e
        if cls.ergebnis:
            d = cls.ergebnis["dauer"]
            print("\n[DEMO-8] Bau-Laufzeit: " + ", ".join(
                f"{k} {v:.1f} s" for k, v in d.items()))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _bereit(self):
        self.assertIsNone(self.fehler, f"{self.fehler}\n" + "\n".join(self.meldungen))

    def _pfade(self):
        return [os.path.join(self.ziel, d.datei) for d in self.bau.DEMOS]

    def test_auswahl_vier_bis_sechs_mit_generator(self):
        self.assertGreaterEqual(len(self.bau.DEMOS), 4)
        self.assertLessEqual(len(self.bau.DEMOS), 6)
        for d in self.bau.DEMOS:
            with self.subTest(demo=d.schluessel):
                self.assertTrue(os.path.isfile(os.path.join(_REPO, "tools", d.generator)))
                self.assertTrue(d.datei.endswith(".lshow"))
                self.assertTrue(d.titel and d.beschreibung)
        self.assertEqual(len({d.datei for d in self.bau.DEMOS}), len(self.bau.DEMOS))

    def test_alle_shows_und_das_verzeichnis_entstehen(self):
        self._bereit()
        self.assertEqual(sorted(os.listdir(self.ziel)),
                         sorted([d.datei for d in self.bau.DEMOS] + ["demos.json"]))
        index = json.loads(_lies_abs(os.path.join(self.ziel, "demos.json")))
        self.assertEqual([e["datei"] for e in index["demos"]],
                         [d.datei for d in self.bau.DEMOS])
        for e in index["demos"]:
            self.assertTrue(e["titel"] and e["beschreibung"])

    def test_lint_strict_ist_sauber(self):
        """Der Bau lintet selbst — hier unabhaengig noch einmal, mit frischem
        Datenordner (so wie beim Bauen des Setups und auf einem neu
        installierten Rechner). Bewusst NICHT gegen die Geraete-Bibliothek der
        Suite: die ist eine Kopie der gewachsenen Bibliothek des Rechners, und
        deren Profile koennen vom mitgelieferten Stand abweichen (FM-69)."""
        self._bereit()
        self.assertIn("lint", self.ergebnis["dauer"])
        with tempfile.TemporaryDirectory(prefix="lightos_demo8_lint_") as basis:
            r = subprocess.run([sys.executable, os.path.join(_REPO, "tools", "lint_show.py"),
                                "--strict", *self._pfade()], cwd=_REPO,
                               env=self.bau.sandbox_umgebung(basis),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("== Gesamt: 0 Fehler, 0 Warnungen", r.stdout)

    def test_jede_show_traegt_ihre_buehne(self):
        self._bereit()
        for pfad in self._pfade():
            with self.subTest(show=os.path.basename(pfad)):
                show = self.bau.lies_show(pfad)
                self.assertTrue((show.get("visualizer") or {}).get("active_stage"))
                self.assertGreater(len(self.bau.buehnen_knoten(show)), 0,
                                   "keine Bühnen-Elemente im scene_graph")

    def test_laedt_headless_in_leerem_datenordner_vollstaendig(self):
        self._bereit()
        with tempfile.TemporaryDirectory(prefix="lightos_demo8_leer_") as basis:
            env = self.bau.sandbox_umgebung(basis)
            stages = os.path.join(self.bau.app_datenordner(env), "stages")
            self.assertFalse(os.path.isdir(stages) and os.listdir(stages))
            vorher = {p: _sha(p) for p in self._pfade()}
            r = subprocess.run([sys.executable, "-c", _LADE_TREIBER, _REPO, *self._pfade()],
                               cwd=basis, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-3000:])
            zeile = [z for z in r.stdout.splitlines() if z.startswith("ERG=")][-1]
            erg = json.loads(zeile[4:])
            self.assertTrue(os.path.realpath(erg["app_data_dir"]).startswith(
                os.path.realpath(basis)), erg["app_data_dir"])
            for pfad in self._pfade():
                name = os.path.basename(pfad)
                with self.subTest(show=name):
                    e = erg["shows"][name]
                    self.assertTrue(e["ok"], e["msg"])
                    self.assertEqual(e["probleme"], [])
                    self.assertGreater(e["geraete"], 0)
                    knoten = len(self.bau.buehnen_knoten(self.bau.lies_show(pfad)))
                    self.assertEqual(e["buehnen_elemente"], knoten,
                                     "Bühne nicht vollständig aus der Show entstanden")
                    self.assertEqual(_sha(pfad), vorher[pfad], "Laden hat die Datei verändert")

    def test_bau_schreibt_keine_buehne_in_den_datenordner_des_aufrufers(self):
        """TOOL-13: ohne Sandbox landeten die Buehnen der Generatoren im
        App-Datenordner des bauenden Prozesses (hier: dem der Suite)."""
        self._bereit()
        nachher = (sorted(os.listdir(self.eigene_stages))
                   if os.path.isdir(self.eigene_stages) else [])
        self.assertEqual(nachher, self.stages_vorher)

    def test_keine_pfade_des_baurechners_in_den_shows(self):
        self._bereit()
        for pfad in self._pfade():
            with self.subTest(show=os.path.basename(pfad)):
                self.assertEqual(self.bau.spuren_befund(
                    pfad, (os.path.expanduser("~"), _REPO, tempfile.gettempdir())), [])
                roh = zipfile.ZipFile(pfad).read("show.json").decode("utf-8")
                self.assertNotIn("Users/", roh.replace("\\", "/"))


def _lies_abs(pfad: str) -> str:
    with open(pfad, encoding="utf-8") as f:
        return f.read()


class BauPruefungenTest(unittest.TestCase):
    """Die Pruefungen des Bau-Skripts schlagen an, wenn etwas fehlt (ohne Bau)."""

    def setUp(self):
        self.bau = _bau()
        self.tmp = tempfile.mkdtemp(prefix="lightos_demo8_p_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _show(self, knoten):
        return {"visualizer": {"active_stage": "Probe-Bühne"},
                "scene_graph": {"nodes": knoten}}

    def _buehnen_datei(self, ids):
        stages = os.path.join(self.tmp, "stages")
        os.makedirs(stages, exist_ok=True)
        with open(os.path.join(stages, "Probe-B_hne.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "Probe-Bühne", "elements": [{"id": i} for i in ids]}, f)
        return stages

    def test_fehlendes_buehnen_element_wird_gemeldet(self):
        knoten = [{"id": "t1", "kind": "truss", "size_m": [1, 1, 1]},
                  {"id": "f1", "kind": "fixture", "size_m": [1, 1, 1]}]
        stages = self._buehnen_datei(["t1", "t2"])
        self.assertEqual(len(self.bau.buehnen_knoten(self._show(knoten))), 1)
        maengel = self.bau.buehnen_befund(self._show(knoten), stages)
        self.assertEqual(len(maengel), 1)
        self.assertIn("t2", maengel[0])
        knoten.append({"id": "t2", "kind": "truss", "size_m": [1, 1, 1]})
        self.assertEqual(self.bau.buehnen_befund(self._show(knoten), stages), [])

    def test_pfad_des_baurechners_wird_gemeldet(self):
        pfad = os.path.join(self.tmp, "x.lshow")
        with zipfile.ZipFile(pfad, "w") as z:
            z.writestr("show.json", json.dumps({"bild": os.path.join(self.tmp, "a.png")}))
        self.assertTrue(self.bau.spuren_befund(pfad, (self.tmp,)))
        self.assertEqual(self.bau.spuren_befund(pfad, (os.path.join(self.tmp, "nie"),)), [])

    def test_sandbox_lenkt_alle_datenorte_um_und_laesst_nichts_geerbtes_gelten(self):
        geerbt = {"PATH": os.environ.get("PATH", ""),
                  "LIGHTOS_SHOW_DB": "/echt/current_show.db",
                  "LIGHTOS_FIXTURE_DB": "/echt/fixtures.db",
                  "LIGHTOS_GEN_OUT": "/echt/x.lshow",
                  "LIGHTOS_OUTPUT_IFACE": "eth0",
                  "XDG_DATA_HOME": "/echt/share", "APPDATA": "/echt/appdata",
                  "HOME": "/echt/home", "DISPLAY": ":0"}
        env = self.bau.sandbox_umgebung(self.tmp, vorlage=geerbt)
        basis = os.path.realpath(self.tmp)
        for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME",
                     "XDG_CONFIG_HOME", "TMPDIR", "TEMP", "TMP", "LIGHTOS_FIXTURE_DB",
                     "LIGHTOS_PREFS_DIR", "LIGHTOS_CRASH_LOG", "LIGHTOS_SACN_CID",
                     "LIGHTOS_UNIVERSES_JSON"):
            with self.subTest(name=name):
                self.assertTrue(env[name].startswith(basis + os.sep), env[name])
        for name in ("LIGHTOS_SHOW_DB", "LIGHTOS_GEN_OUT", "LIGHTOS_OUTPUT_IFACE", "DISPLAY"):
            self.assertNotIn(name, env)
        self.assertEqual(env["QT_QPA_PLATFORM"], "offscreen")
        for name in ("LIGHTOS_NO_OUTPUT_THREAD", "LIGHTOS_SERIAL_INPROC",
                     "LIGHTOS_NO_AUDIO_AUTOSTART", "LIGHTOS_NO_DATENUMZUG"):
            self.assertEqual(env[name], "1")
        self.assertTrue(self.bau.app_datenordner(env).startswith(basis + os.sep))

    def test_gescheiterter_bau_hinterlaesst_kein_verzeichnis(self):
        ziel = os.path.join(self.tmp, "ziel")
        os.makedirs(ziel)
        with open(os.path.join(ziel, "demos.json"), "w") as f:
            f.write("{}")
        with mock.patch.object(self.bau, "baue_eine",
                               side_effect=self.bau.DemoBauFehler("kaputt")):
            with self.assertRaises(self.bau.DemoBauFehler):
                self.bau.baue(ziel, melde=lambda *_: None)
        self.assertFalse(os.path.exists(os.path.join(ziel, "demos.json")))
        with self.assertRaises(self.bau.DemoBauFehler):
            self.bau.waehle("gibt_es_nicht")


# ── 2. App ───────────────────────────────────────────────────────────────────

class DemoListeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lightos_demo8_l_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_ordner_liegt_bei_den_programmdateien(self):
        from src.core import demo_shows, paths
        self.assertEqual(demo_shows.ordner(), paths.programm_datei("demo_shows"))
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "_MEIPASS", self.tmp, create=True):
            self.assertEqual(demo_shows.ordner(),
                             os.path.join(os.path.abspath(self.tmp), "demo_shows"))

    def test_namen_stimmen_mit_dem_bauskript_ueberein(self):
        from src.core import demo_shows
        bau = _bau()
        self.assertEqual((demo_shows.ORDNER, demo_shows.INDEX), (bau.ORDNER, bau.INDEX))

    def test_liste_in_reihenfolge_ohne_fehlende_und_fremde_dateien(self):
        from src.core import demo_shows
        _demo_ordner(self.tmp, {"B.lshow": ("Zweite", "b"), "A.lshow": ("Erste", "a"),
                                "Weg.lshow": ("Fehlt", "")})
        os.remove(os.path.join(self.tmp, "Weg.lshow"))
        index = os.path.join(self.tmp, "demos.json")
        daten = json.loads(_lies_abs(index))
        daten["demos"] += [{"datei": "../draussen.lshow", "titel": "x"},
                           {"datei": "kein.txt", "titel": "y"}, "muell"]
        with open(index, "w", encoding="utf-8") as f:
            json.dump(daten, f)
        demos = demo_shows.liste(self.tmp)
        self.assertEqual([(d.titel, d.beschreibung, d.dateiname) for d in demos],
                         [("Zweite", "b", "B.lshow"), ("Erste", "a", "A.lshow")])

    def test_fehlender_oder_kaputter_ordner_ist_eine_leere_liste(self):
        from src.core import demo_shows
        self.assertEqual(demo_shows.liste(os.path.join(self.tmp, "nie")), [])
        with open(os.path.join(self.tmp, "demos.json"), "w") as f:
            f.write("{kaputt")
        self.assertEqual(demo_shows.liste(self.tmp), [])
        self.assertTrue(demo_shows.pruefe(self.tmp))

    def test_pruefe_meldet_fehlende_und_kaputte_shows(self):
        from src.core import demo_shows
        self.assertEqual(len(demo_shows.pruefe(os.path.join(self.tmp, "nie"))), 1)
        _demo_ordner(self.tmp, {"A.lshow": ("A", ""), "B.lshow": ("B", ""),
                                "C.lshow": ("C", "")})
        self.assertEqual(demo_shows.pruefe(self.tmp), [])
        os.remove(os.path.join(self.tmp, "A.lshow"))
        with open(os.path.join(self.tmp, "B.lshow"), "w") as f:
            f.write("keine zip")
        fehler = demo_shows.pruefe(self.tmp)
        self.assertEqual(len(fehler), 2)
        self.assertTrue(any("A.lshow" in f for f in fehler))
        self.assertTrue(any("B.lshow" in f for f in fehler))


import pytest as _pytest_xplat15                         # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True, scope="module")
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    if _QApp.instance() is not None:
        destroy_all_top_level_widgets(_QApp.instance())


class MenueTest(unittest.TestCase):
    """Datei -> „Demo-Show öffnen" im echten Hauptfenster."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        from src.core.app_state import get_state
        from src.core.show import show_file as SF
        from src.core import demo_shows
        from src.ui import main_window as mw
        cls.SF, cls.mw, cls.demo_shows = SF, mw, demo_shows
        cls.state = get_state()
        cls.tmp = tempfile.mkdtemp(prefix="lightos_demo8_m_")
        # Eine echte kleine Show (ein Geraet) als Demo-Inhalt.
        SF.reset_show()
        cls.state.add_fixture(_dimmer(1, 1), undoable=False)
        quelle = os.path.join(cls.tmp, "quelle.lshow")
        SF.save_show(quelle)
        with open(quelle, "rb") as f:
            inhalt = f.read()
        os.remove(quelle)
        SF.reset_show()
        cls.ordner = os.path.join(cls.tmp, "demo_shows")
        _demo_ordner(cls.ordner, {"Erste_Demo.lshow": ("Erste Demo", "Kurz erklärt."),
                                  "Zweite_Demo.lshow": ("Zweite Demo", "Auch kurz.")},
                     inhalt=inhalt)
        cls._patch = mock.patch.object(demo_shows, "ordner", lambda: cls.ordner)
        cls._patch.start()
        cls.win = mw.MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        cls.SF.reset_show()
        cls.app.processEvents()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _datei_menue(self):
        # Ueber die Kinder der Menueleiste, NICHT ueber ``QAction.menu()``:
        # dessen PySide-Wrapper nimmt das Menue beim Freigeben mit.
        from PySide6.QtWidgets import QMenu
        for m in self.win.menuBar().findChildren(QMenu):
            if m.title().replace("&", "") == "Datei":
                return m
        self.fail("kein Datei-Menue")

    def _demo_menue(self):
        menue = self.win._demo_menu
        self.assertEqual(menue.title(), "Demo-Show öffnen")
        self.assertIn(menue.menuAction(), self._datei_menue().actions(),
                      "Datei-Menue ohne „Demo-Show öffnen“")
        menue.aboutToShow.emit()
        return menue

    def _oeffne(self, titel="Erste Demo"):
        akt = [a for a in self._demo_menue().actions() if a.text() == titel][0]
        with mock.patch.object(self.mw.QMessageBox, "warning", lambda *a, **k: None):
            akt.trigger()
        self.app.processEvents()

    def test_menue_listet_die_demos_mit_kurzbeschreibung(self):
        menue = self._demo_menue()
        eintraege = [(a.text(), a.toolTip(), a.isEnabled()) for a in menue.actions()
                     if not a.isSeparator()]
        self.assertEqual(eintraege, [("Erste Demo", "Kurz erklärt.", True),
                                     ("Zweite Demo", "Auch kurz.", True)])
        self.assertTrue(menue.toolTipsVisible())
        # direkt unter „Öffnen..."
        texte = [a.text().replace("&", "") for a in self._datei_menue().actions()]
        self.assertEqual(texte.index("Demo-Show öffnen"), texte.index("Öffnen...") + 1)

    def test_ohne_demo_ordner_ausgegrauter_hinweis(self):
        with mock.patch.object(self.demo_shows, "ordner",
                               lambda: os.path.join(self.tmp, "nie")):
            menue = self._demo_menue()
            aktionen = [a for a in menue.actions() if not a.isSeparator()]
            self.assertEqual(len(aktionen), 1)
            self.assertFalse(aktionen[0].isEnabled())
            self.assertIn("packaging/demo_shows.py", aktionen[0].toolTip())
        self.assertEqual(len(self._demo_menue().actions()), 2)   # wieder da

    def test_oeffnen_laesst_die_quelle_unveraendert_und_ist_ungespeichert(self):
        quelle = os.path.join(self.ordner, "Erste_Demo.lshow")
        vorher = (_sha(quelle), os.stat(quelle).st_mtime_ns, sorted(os.listdir(self.ordner)))
        recents_vorher = self.mw._load_recent_files()
        self._oeffne()
        self.assertEqual(len(self.state.get_patched_fixtures()), 1)
        self.assertIsNone(self.win._current_show_path)
        self.assertTrue(self.win._has_unsaved_changes())
        self.assertIn("Erste Demo", self.win.windowTitle())
        self.assertIn("nicht gespeichert", self.win.windowTitle())
        self.assertEqual(self.mw._load_recent_files(), recents_vorher,
                         "die Demo gehört nicht in „Zuletzt verwendet“")
        self.assertEqual((_sha(quelle), os.stat(quelle).st_mtime_ns,
                          sorted(os.listdir(self.ordner))), vorher)

    def test_speichern_fuehrt_zu_speichern_unter_im_show_ordner(self):
        from src.core.paths import app_data_dir
        quelle = os.path.join(self.ordner, "Erste_Demo.lshow")
        vorher = _sha(quelle)
        self._oeffne()
        ziel = os.path.join(self.tmp, "meine_kopie.lshow")
        gefragt = []

        def dialog(_eltern, _titel, start, _filter):
            gefragt.append(start)
            return ziel, ""
        with mock.patch.object(self.mw.QFileDialog, "getSaveFileName", dialog):
            self.assertTrue(self.win._save_show())
        self.assertEqual(len(gefragt), 1, "Speichern muss „Speichern unter“ öffnen")
        self.assertEqual(os.path.normpath(gefragt[0]),
                         os.path.normpath(os.path.join(app_data_dir(), "shows",
                                                       "Erste_Demo.lshow")))
        self.assertTrue(os.path.isfile(ziel))
        self.assertEqual(self.win._current_show_path, ziel)
        self.assertEqual(_sha(quelle), vorher)
        self.assertEqual(sorted(os.listdir(self.ordner)),
                         ["Erste_Demo.lshow", "Zweite_Demo.lshow", "demos.json"])
        # Danach ist es eine normale Show: der Namensvorschlag ist verbraucht.
        with mock.patch.object(self.mw.QFileDialog, "getSaveFileName", dialog):
            self.win._save_show_as()
        self.assertEqual(os.path.normpath(gefragt[1]), os.path.normpath(self.tmp))

    def test_normales_oeffnen_bleibt_wie_es_war(self):
        quelle = os.path.join(self.ordner, "Zweite_Demo.lshow")
        with mock.patch.object(self.mw.QMessageBox, "warning", lambda *a, **k: None):
            self.win._open_show_path(quelle)
        self.app.processEvents()
        self.assertEqual(self.win._current_show_path, quelle)


def _dimmer(fid: int, addr: int = 1):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine as fdb_engine
    from src.core.database.models import FixtureProfile, PatchedFixture
    with Session(fdb_engine()) as s:
        pid = int(s.execute(select(FixtureProfile.id)).scalars().first())
    return PatchedFixture(
        fid=fid, label=f"Fix {fid}", fixture_profile_id=pid, mode_name="", universe=1,
        address=addr, channel_count=1, manufacturer_name="Test", fixture_name="Test",
        fixture_type="dimmer")


# ── 3. Paketierung ───────────────────────────────────────────────────────────

class PaketierungTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lightos_demo8_b_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bi = _bundle_inhalt()

    def test_bundle_nimmt_genau_die_verzeichneten_demos(self):
        ordner = os.path.join(self.tmp, "demo_shows")
        _demo_ordner(ordner, {"A.lshow": ("A", ""), "B.lshow": ("B", "")})
        # Was nicht im Verzeichnis steht, kommt nicht mit — auch keine Show.
        with open(os.path.join(ordner, "privat.lshow"), "w") as f:
            f.write("x")
        os.makedirs(os.path.join(ordner, "unter"))
        self.assertIn("demo_shows", self.bi.ERZEUGTE_ORDNER)
        self.assertEqual(self.bi.erzeugte_dateien(self.tmp),
                         ["demo_shows/A.lshow", "demo_shows/B.lshow",
                          "demo_shows/demos.json"])
        ziele = {(os.path.relpath(q, self.tmp).replace(os.sep, "/"), z)
                 for q, z in self.bi.datas(self.tmp)}
        for rel in ("demo_shows/A.lshow", "demo_shows/B.lshow", "demo_shows/demos.json"):
            self.assertIn((rel, "demo_shows"), ziele)
        self.assertNotIn(("demo_shows/privat.lshow", "demo_shows"), ziele)

    def test_bundle_ohne_demo_ordner_bleibt_baubar(self):
        self.assertEqual(self.bi.erzeugte_dateien(self.tmp), [])

    def test_selbsttest_kennt_den_ordner(self):
        from src.core import selbsttest
        # Quellbetrieb ohne Demos: Hinweis, kein Fehler.
        fehler, zeile = selbsttest.pruefe_demo_shows(self.tmp, pflicht=False)
        self.assertEqual(fehler, [])
        self.assertIn("demo_shows", zeile)
        # Gepackt ohne Demos: Fehler.
        fehler, _ = selbsttest.pruefe_demo_shows(self.tmp, pflicht=True)
        self.assertTrue(fehler)
        _demo_ordner(os.path.join(self.tmp, "demo_shows"), {"A.lshow": ("A", "")})
        fehler, zeile = selbsttest.pruefe_demo_shows(self.tmp, pflicht=True)
        self.assertEqual(fehler, [])
        self.assertIn("1", zeile)
        # kaputte Show faellt auch im Quellbetrieb auf
        with open(os.path.join(self.tmp, "demo_shows", "A.lshow"), "w") as f:
            f.write("keine zip")
        fehler, _ = selbsttest.pruefe_demo_shows(self.tmp, pflicht=False)
        self.assertTrue(fehler)

    def test_selbsttest_pflicht_haengt_am_gepackten_build(self):
        from src.core import selbsttest
        with mock.patch.object(selbsttest, "ist_gefroren", lambda: True), \
                mock.patch.object(selbsttest, "programm_dir", lambda: self.tmp), \
                mock.patch.object(selbsttest, "pruefe_module", lambda *a, **k: []), \
                mock.patch.object(selbsttest, "pruefe_ressourcen", lambda *a, **k: []):
            code, zeilen = selbsttest.bericht()
        self.assertEqual(code, 1)
        self.assertTrue(any("demo_shows" in z and z.startswith("FEHLER") for z in zeilen))

    def test_workflow_baut_die_demos_vor_pyinstaller(self):
        w = _lies(".github", "workflows", "windows-setup.yml")
        self.assertIn("python packaging/demo_shows.py", w)
        self.assertLess(w.index("python packaging/demo_shows.py"),
                        w.index("python -m PyInstaller"))
        self.assertIn('"packaging/**"', w)

    def test_demo_ordner_ist_nicht_eingecheckt(self):
        self.assertIn("/demo_shows/", _lies(".gitignore").splitlines())
        try:
            aus = subprocess.run(["git", "ls-files", "--", "demo_shows"], cwd=_REPO,
                                 capture_output=True, check=True, text=True)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("kein Git")
        self.assertEqual(aus.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
