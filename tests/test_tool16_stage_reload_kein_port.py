"""TOOL-16: ``tools/verify_stage_reload.py`` darf keinen echten DMX-Port oeffnen.

Das Werkzeug pruefte die noch leere ``universes.json`` des Sandkastens — danach
uebernahm ``get_state()`` (XPLAT-44-Datenumzug) ein altes ``data/universes.json``
aus dem Arbeitsverzeichnis und rief ``apply_output_config()`` auf. Mit einem
Enttec-Eintrag oeffnete das den echten seriellen Port.

Jetzt: ``LIGHTOS_NO_DATENUMZUG`` ist gesetzt, und die Ausgabe wird NACH
``get_state()`` erneut geprueft. Getestet in einem eigenen Prozess (frischer
State-Singleton, Arbeitsverzeichnis mit Alt-``data/``), der Port-Oeffner ist
ein Spion.
"""
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tools", "verify_stage_reload.py")

_KIND = r'''
import importlib.util, json, os, sys
repo, tool, sandbox, ergebnis = sys.argv[1:5]
sys.path.insert(0, repo)
spec = importlib.util.spec_from_file_location("vsr", tool)
vsr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vsr)
vsr.sandbox_einrichten(sandbox, fixture_db=os.path.join(sandbox, "fx.db"),
                       stages_quelle=os.path.join(sandbox, "keine_stages"))
geoeffnet = []
import src.core.dmx.output_manager as om_mod

class _Dummy:
    def __init__(self, port):
        self.port = port
    def send_dmx(self, data):
        pass
    def close(self):
        pass

def _spion(port):
    geoeffnet.append(port)
    return _Dummy(port)

om_mod._make_enttec_device = _spion
vsr.ausgabe_datei_pruefen()
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from src.core.app_state import get_state
abbruch = ""
try:
    vsr.ausgabe_nach_state_pruefen(get_state())
except SystemExit as e:
    abbruch = str(e)
with open(ergebnis, "w", encoding="utf-8") as fh:
    json.dump({"geoeffnet": geoeffnet, "abbruch": abbruch}, fh)
os._exit(0)
'''


class StageReloadKeinPortTest(unittest.TestCase):
    def test_alt_universes_json_im_cwd_oeffnet_keinen_port(self):
        with tempfile.TemporaryDirectory() as cwd:
            os.makedirs(os.path.join(cwd, "data"))
            with open(os.path.join(cwd, "data", "universes.json"), "w",
                      encoding="utf-8") as fh:
                json.dump([{"num": 1, "output": "Enttec",
                            "patch": "/dev/ttyUSB0"}], fh)
            sandbox = os.path.join(cwd, "sandbox")
            os.makedirs(sandbox)
            ergebnis = os.path.join(cwd, "ergebnis.json")
            env = dict(os.environ)
            # Wie ein normaler Aufruf: keine Test-Umlenkungen aus conftest
            # (LIGHTOS_NO_DATENUMZUG, LIGHTOS_UNIVERSES_JSON …) erben.
            for k in [k for k in env if k.startswith("LIGHTOS_")] + ["XDG_DATA_HOME"]:
                env.pop(k, None)
            env["QT_QPA_PLATFORM"] = "offscreen"
            env["HOME"] = cwd              # nie das echte Konto beruehren
            r = subprocess.run(
                [sys.executable, "-c", _KIND, REPO, TOOL, sandbox, ergebnis],
                cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertTrue(os.path.exists(ergebnis), r.stdout + r.stderr)
            with open(ergebnis, encoding="utf-8") as fh:
                res = json.load(fh)
        self.assertEqual(res["geoeffnet"], [], res)
        self.assertEqual(res["abbruch"], "", res)


class GesetzteUniversesVariableTest(unittest.TestCase):
    """Codex #959: ``LIGHTOS_UNIVERSES_JSON`` des Bedieners zeigt auf die echte
    Konfiguration. Ein Enttec-Ziel, das ``_GEFAEHRLICH`` nicht kennt
    (``/dev/serial/by-id/...``), kam durch die Vorpruefung, und
    ``apply_output_config()`` oeffnete den Port. Der Sandkasten setzt die
    Variable jetzt hart auf eine eigene Datei."""

    def test_echte_konfiguration_per_variable_oeffnet_keinen_port(self):
        with tempfile.TemporaryDirectory() as cwd:
            echt = os.path.join(cwd, "echte_universes.json")
            with open(echt, "w", encoding="utf-8") as fh:
                json.dump([{"num": 1, "output": "Enttec",
                            "patch": "/dev/serial/by-id/usb-FTDI_Test-if00-port0"}], fh)
            sandbox = os.path.join(cwd, "sandbox")
            os.makedirs(sandbox)
            ergebnis = os.path.join(cwd, "ergebnis.json")
            env = dict(os.environ)
            for k in [k for k in env if k.startswith("LIGHTOS_")] + ["XDG_DATA_HOME"]:
                env.pop(k, None)
            env["LIGHTOS_UNIVERSES_JSON"] = echt
            env["QT_QPA_PLATFORM"] = "offscreen"
            env["HOME"] = cwd              # nie das echte Konto beruehren
            r = subprocess.run(
                [sys.executable, "-c", _KIND, REPO, TOOL, sandbox, ergebnis],
                cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertTrue(os.path.exists(ergebnis), r.stdout + r.stderr)
            with open(ergebnis, encoding="utf-8") as fh:
                res = json.load(fh)
        self.assertEqual(res["geoeffnet"], [], res)
        self.assertEqual(res["abbruch"], "", res)

    def test_schutz_verlangt_die_umgelenkte_datei(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("vsr_pin", TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        alt = {k: os.environ.get(k) for k in (
            "XDG_DATA_HOME", "LIGHTOS_SHOW_DB", "LIGHTOS_FIXTURE_DB",
            "LIGHTOS_NO_OUTPUT_THREAD", "LIGHTOS_NO_DATENUMZUG", "LIGHTOS_UNIVERSES_JSON")}

        def _zurueck():
            for k, v in alt.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(_zurueck)
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["LIGHTOS_UNIVERSES_JSON"] = os.path.join(tmp, "anderswo.json")
            mod.sandbox_einrichten(tmp, fixture_db=os.path.join(tmp, "fx.db"),
                                   stages_quelle=os.path.join(tmp, "keine"))
            self.assertEqual(os.environ["LIGHTOS_UNIVERSES_JSON"],
                             os.path.join(tmp, "universes.json"))
            self.assertTrue(mod.schutz_aktiv())
            os.environ["LIGHTOS_UNIVERSES_JSON"] = os.path.join(tmp, "anderswo.json")
            self.assertFalse(mod.schutz_aktiv())


class NachStatePruefungTest(unittest.TestCase):
    """Die zweite Pruefung erkennt einen trotzdem eingerichteten Adapter."""

    def _vsr(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("vsr_test", TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _state(self, **ausgaenge):
        entfernt = []
        om = types.SimpleNamespace(
            _enttec_outputs=ausgaenge.get("enttec", {}),
            _artnet_outputs=ausgaenge.get("artnet", {}),
            _sacn_outputs=ausgaenge.get("sacn", {}),
            universes={1: None}, remove_output=entfernt.append)
        return types.SimpleNamespace(output_manager=om), entfernt

    def test_enttec_nach_get_state_bricht_ab_und_schliesst(self):
        vsr = self._vsr()
        st, entfernt = self._state(enttec={1: object()})
        with self.assertRaises(SystemExit):
            vsr.ausgabe_nach_state_pruefen(st)
        self.assertEqual(entfernt, [1])

    def test_artnet_broadcast_und_sacn_multicast_brechen_ab(self):
        vsr = self._vsr()
        for kw in ({"artnet": {1: types.SimpleNamespace(target_ip="255.255.255.255")}},
                   {"sacn": {1: types.SimpleNamespace(_target_ip=None)}}):
            st, _ = self._state(**kw)
            with self.assertRaises(SystemExit):
                vsr.ausgabe_nach_state_pruefen(st)


_KIND_MAIN = r'''
import importlib.util, json, os, sys
repo, tool, show, modus, ergebnis = sys.argv[1:6]
sys.path.insert(0, repo)
spec = importlib.util.spec_from_file_location("vsr", tool)
vsr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vsr)          # nur Import — KEIN sandbox_einrichten()

class _Halt(Exception):
    pass

class _QApp:
    @staticmethod
    def instance():
        raise _Halt()

vsr.QApplication = _QApp               # hinter dem Schutz anhalten, kein Fenster
if modus == "state_schon_da":
    import src.core.app_state as A
    A._state = object()
res = {"erreicht": False, "abbruch": ""}
try:
    vsr.main([show])
except _Halt:
    res["erreicht"] = True
except SystemExit as e:
    res["abbruch"] = str(e)
res["xdg"] = os.environ.get("XDG_DATA_HOME", "")
res["datenumzug_aus"] = os.environ.get("LIGHTOS_NO_DATENUMZUG", "")
res["kein_thread"] = os.environ.get("LIGHTOS_NO_OUTPUT_THREAD", "")
res["show_db"] = os.environ.get("LIGHTOS_SHOW_DB", "")
with open(ergebnis, "w", encoding="utf-8") as fh:
    json.dump(res, fh)
os._exit(0)
'''


class MainOhneSandkastenTest(unittest.TestCase):
    """B4 (Review): ``import`` + ``main()`` ohne ``__main__``-Block."""

    def _lauf(self, modus):
        with tempfile.TemporaryDirectory() as cwd:
            show = os.path.join(cwd, "leer.lshow")
            open(show, "w").close()
            ergebnis = os.path.join(cwd, "ergebnis.json")
            env = dict(os.environ)
            for k in [k for k in env if k.startswith("LIGHTOS_")] + ["XDG_DATA_HOME"]:
                env.pop(k, None)
            env["QT_QPA_PLATFORM"] = "offscreen"
            env["HOME"] = cwd
            env["TMPDIR"] = cwd            # Wegwerf-Ordner mit aufraeumen
            r = subprocess.run(
                [sys.executable, "-c", _KIND_MAIN, REPO, TOOL, show, modus, ergebnis],
                cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertTrue(os.path.exists(ergebnis), r.stdout + r.stderr)
            with open(ergebnis, encoding="utf-8") as fh:
                return json.load(fh), cwd

    def test_main_richtet_sandkasten_selbst_ein(self):
        res, cwd = self._lauf("normal")
        self.assertTrue(res["erreicht"], res)
        self.assertTrue(res["datenumzug_aus"], res)
        self.assertTrue(res["kein_thread"], res)
        self.assertIn("vizverify_", res["xdg"])
        self.assertIn("vizverify_", res["show_db"])

    def test_main_bricht_ab_wenn_state_schon_existiert(self):
        res, _ = self._lauf("state_schon_da")
        self.assertFalse(res["erreicht"], res)
        self.assertIn("ABBRUCH", res["abbruch"])


if __name__ == "__main__":
    unittest.main()
