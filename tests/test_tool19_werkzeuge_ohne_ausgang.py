"""TOOL-19: kein Werkzeug oeffnet ueber ``get_state()`` einen echten DMX-Ausgang.

Befund (Codex-Review #929–#954, Sammelbefund Werkzeuge): rund 30 Skripte unter
``tools/`` rufen ``get_state()``. Das ruft IMMER ``apply_output_config()`` auf —
und richtete damit ein, was in der ECHTEN ``universes.json`` steht: bei einem
Enttec-Eintrag oeffnete ein Generator- oder Messlauf den echten seriellen Port,
bei Art-Net/sACN die Sende-Sockets. ``LIGHTOS_NO_OUTPUT_THREAD`` verhindert nur
den Sende-Thread, nicht das Oeffnen.

Jetzt lenkt ``tools/_gen_env.py`` die Ausgabe-Konfiguration auf eine Datei um,
die es nicht gibt (``LIGHTOS_UNIVERSES_JSON``); die drei Werkzeuge ohne
``_gen_env`` setzen dieselbe Umlenkung selbst.

Geprueft wird am echten Weg: ein Kindprozess mit eigenem Datenordner, in dem
eine ``universes.json`` mit Enttec, Art-Net und sACN liegt, ruft ``get_state()``.
Die drei ``add_*``-Methoden des Ausgabe-Managers sind dabei durch Mitschreiber
ersetzt — es wird also in KEINEM Fall wirklich ein Port oder Socket geoeffnet.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"

#: Die „echte" Konfiguration des Rechners, wie sie im Datenordner laege.
ECHTE_KONFIG = [
    {"num": 1, "name": "Rig", "output": "Enttec", "patch": "COM_TOOL19"},
    {"num": 2, "name": "Netz", "output": "ArtNet", "patch": "10.255.255.254"},
    {"num": 3, "name": "Netz 2", "output": "sACN", "patch": "10.255.255.253"},
]

_KIND = r'''
import json, os, sys
sys.path.insert(0, sys.argv[1])                    # Repo
sys.path.insert(0, os.path.join(sys.argv[1], "tools"))
VORSPANN
from src.core.dmx import output_manager as om
aufrufe = []
for name in ("add_enttec", "add_artnet", "add_sacn"):
    def mitschreiber(self, universe, *a, _n=name, **k):
        aufrufe.append([_n, universe, [str(x) for x in a]])
    setattr(om.OutputManager, name, mitschreiber)
from src.core.app_state import get_state
st = get_state()
pfad = os.environ.get("LIGHTOS_UNIVERSES_JSON", "")
print("ERGEBNIS " + json.dumps({
    "aufrufe": aufrufe,
    "universes_json": pfad,
    "datei_existiert": bool(pfad) and os.path.exists(pfad),
    "ausgaenge": len(st.output_manager.ausgabe_status()),
    "kein_sende_thread": bool(os.environ.get("LIGHTOS_NO_OUTPUT_THREAD")),
}))
'''


def _lauf(vorspann: str, extra_env: dict | None = None) -> dict:
    """Kindprozess mit eigenem Datenordner samt „echter" ``universes.json``."""
    with tempfile.TemporaryDirectory(prefix="lightos_tool19_") as tmp:
        daten = os.path.join(tmp, "LightOS")
        os.makedirs(daten)
        with open(os.path.join(daten, "universes.json"), "w", encoding="utf-8") as f:
            json.dump(ECHTE_KONFIG, f)
        skript = os.path.join(tmp, "kind.py")
        with open(skript, "w", encoding="utf-8") as f:
            f.write(_KIND.replace("VORSPANN", vorspann))
        env = dict(os.environ)
        # Der Testlauf pinnt die Variable selbst (conftest) — fuer diese
        # Pruefung muss das Kind in der Lage eines Bedieners sein: nichts gesetzt.
        for var in ("LIGHTOS_UNIVERSES_JSON", "LIGHTOS_SHOW_DB", "LIGHTOS_VC_ASSETS_DIR",
                    "LIGHTOS_NO_OUTPUT_THREAD", "LIGHTOS_SERIAL_INPROC"):
            env.pop(var, None)
        env.update({
            "APPDATA": tmp, "XDG_DATA_HOME": tmp, "HOME": tmp, "USERPROFILE": tmp,
            "LIGHTOS_NO_DATENUMZUG": "1", "QT_QPA_PLATFORM": "offscreen",
            "LIGHTOS_NO_AUDIO_AUTOSTART": "1", "PYTHONIOENCODING": "utf-8",
        })
        env.update(extra_env or {})
        lauf = subprocess.run([sys.executable, skript, str(REPO)], env=env, cwd=tmp,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300)
        zeilen = [z for z in (lauf.stdout or "").splitlines() if z.startswith("ERGEBNIS ")]
        assert zeilen, (lauf.returncode, (lauf.stdout or "")[-1500:], (lauf.stderr or "")[-1500:])
        return json.loads(zeilen[-1][len("ERGEBNIS "):])


class GeneratorOeffnetKeinenAusgangTest(unittest.TestCase):

    def test_gegenprobe_ohne_schutz_wird_die_echte_konfiguration_eingerichtet(self):
        """Der Aufbau misst richtig: OHNE ``_gen_env`` greift ``get_state()``
        nach allen drei Ausgaengen der echten Datei."""
        erg = _lauf('os.environ["LIGHTOS_NO_OUTPUT_THREAD"] = "1"\n'
                    'os.environ["LIGHTOS_SERIAL_INPROC"] = "1"\n'
                    'import tempfile\n'
                    'os.environ["LIGHTOS_SHOW_DB"] = os.path.join(tempfile.gettempdir(), '
                    'f"lightos_tool19_gegenprobe_{os.getpid()}.db")')
        self.assertEqual(sorted(a[0] for a in erg["aufrufe"]),
                         ["add_artnet", "add_enttec", "add_sacn"], erg)
        enttec = [a for a in erg["aufrufe"] if a[0] == "add_enttec"][0]
        self.assertEqual(enttec[2], ["COM_TOOL19"])

    def test_mit_gen_env_wird_kein_ausgang_eingerichtet(self):
        erg = _lauf("import _gen_env  # noqa: F401")
        self.assertEqual(erg["aufrufe"], [],
                         "ein Generator hat die echte Ausgabe-Konfiguration eingerichtet")
        self.assertEqual(erg["ausgaenge"], 0)
        self.assertTrue(erg["universes_json"], "LIGHTOS_UNIVERSES_JSON ist nicht gesetzt")
        self.assertFalse(erg["datei_existiert"], "die Wegwerfdatei wurde angelegt")
        self.assertTrue(erg["kein_sende_thread"])

    def test_ueber_den_builder_ebenso(self):
        """``_builder`` ist der Weg der meisten Generatoren."""
        erg = _lauf("import _builder  # noqa: F401")
        self.assertEqual(erg["aufrufe"], [])

    def test_eine_bewusste_umlenkung_bleibt_stehen(self):
        """``setdefault``: Testlauf, Bild-Sandbox und ``verify_stage_reload``
        pinnen selbst — ihr Wert darf nicht ueberschrieben werden."""
        with tempfile.TemporaryDirectory(prefix="lightos_tool19_pin_") as d:
            eigen = os.path.join(d, "eigene.json")
            with open(eigen, "w", encoding="utf-8") as f:
                json.dump([{"num": 1, "output": "ArtNet", "patch": "127.0.0.1"}], f)
            erg = _lauf("import _gen_env  # noqa: F401", {"LIGHTOS_UNIVERSES_JSON": eigen})
            self.assertEqual(os.path.normcase(erg["universes_json"]), os.path.normcase(eigen))
            self.assertEqual([a[:2] for a in erg["aufrufe"]], [["add_artnet", 1]])


class JedesWerkzeugIstGeschuetztTest(unittest.TestCase):
    """Wer in ``tools/`` ``get_state()`` ruft, muss die Ausgabe-Konfiguration
    umlenken — ueber ``_gen_env``/``_builder``, einen eigenen Pin oder die
    Sandbox der Anleitungsbilder."""

    @staticmethod
    def _importe(baum: ast.AST) -> set[str]:
        namen = set()
        for node in ast.walk(baum):
            if isinstance(node, ast.Import):
                namen.update(a.name.split(".")[-1] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                namen.add((node.module or "").split(".")[-1])
                namen.update(a.name for a in node.names)
        return namen

    @staticmethod
    def _ruft_get_state(baum: ast.AST) -> bool:
        for node in ast.walk(baum):
            if isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Name) and f.id == "get_state") or \
                        (isinstance(f, ast.Attribute) and f.attr == "get_state"):
                    return True
        return False

    def _einordnen(self):
        geschuetzt, offen = {}, []
        for pfad in sorted(TOOLS.rglob("*.py")):
            teile = pfad.relative_to(TOOLS).parts
            if "__pycache__" in teile or teile[0] == "_archiv":
                continue
            quelle = pfad.read_text(encoding="utf-8", errors="replace")
            try:
                baum = ast.parse(quelle)
            except SyntaxError:
                continue
            if not self._ruft_get_state(baum):
                continue
            rel = pfad.relative_to(REPO).as_posix()
            importe = self._importe(baum)
            if importe & {"_gen_env", "_builder"}:
                geschuetzt[rel] = "_gen_env"
            elif "LIGHTOS_UNIVERSES_JSON" in quelle:
                geschuetzt[rel] = "eigener Pin"
            elif teile[0] == "anleitungsbilder":
                geschuetzt[rel] = "Sandbox"
            else:
                offen.append(rel)
        return geschuetzt, offen

    def test_kein_werkzeug_ohne_umlenkung(self):
        geschuetzt, offen = self._einordnen()
        self.assertEqual(
            offen, [],
            "Diese Werkzeuge rufen get_state() und lenken die Ausgabe-Konfiguration "
            "nicht um — am Rig oeffnen sie den echten Ausgang. Als erste Zeile "
            "`import _gen_env` (Generatoren) oder LIGHTOS_UNIVERSES_JSON selbst "
            "auf eine Wegwerfdatei setzen:\n  " + "\n  ".join(offen))
        # Gegenprobe: die Suche laeuft nicht leer.
        self.assertGreater(len(geschuetzt), 20, geschuetzt)

    def test_die_sandbox_der_anleitungsbilder_pinnt_wirklich(self):
        """Der dritte Weg oben gilt nur, weil die Sandbox die Variable setzt."""
        quelle = (TOOLS / "anleitungsbilder" / "sandbox.py").read_text(encoding="utf-8")
        self.assertIn('"LIGHTOS_UNIVERSES_JSON"', quelle)

    def test_gen_env_setzt_die_umlenkung_und_builder_laedt_es(self):
        gen = (TOOLS / "_gen_env.py").read_text(encoding="utf-8")
        self.assertRegex(gen, r'os\.environ\.setdefault\(\s*"LIGHTOS_UNIVERSES_JSON"')
        self.assertIn("tempfile.gettempdir()", gen)
        self.assertRegex((TOOLS / "_builder.py").read_text(encoding="utf-8"),
                         r"(?m)^import _gen_env")

    def test_die_drei_werkzeuge_ohne_gen_env_pinnen_selbst(self):
        for name in ("benchmark_universes.py", "patch_quarantaene.py",
                     "viz_dmx_latency_bench.py"):
            with self.subTest(name):
                quelle = (TOOLS / name).read_text(encoding="utf-8")
                self.assertRegex(
                    quelle, r'os\.environ\.setdefault\(\s*"LIGHTOS_UNIVERSES_JSON"')
        # Das Wartungswerkzeug arbeitet auf der echten Show — erst recht kein Senden.
        self.assertIn('os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")',
                      (TOOLS / "patch_quarantaene.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
