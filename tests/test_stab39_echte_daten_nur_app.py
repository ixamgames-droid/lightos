"""STAB-39: echter Datenordner und echte DMX-Ausgabe NUR fuer die echte App.

Vorfaelle 13.10. (TOOL-27), 29.10. und 31.10.2026: Probeskripte und
``python -c``-Zeilen, die ``src`` importierten, oeffneten den echten
Datenordner und stiessen den DMX-Sendeprozess fuer das echte Interface an.

Jeder Fall laeuft als KINDPROZESS mit sauberer Umgebung: ``HOME``,
``XDG_DATA_HOME``, ``APPDATA`` zeigen in ``tmp_path``, alle ``LIGHTOS_*``
der Suite sind entfernt (sonst saehe das Kind den Sandkasten der Suite statt
des nackten Zustands eines Probeskripts). Nie mit echtem HOME. Serielle Ports,
Port-Liste und Sockets sind im Kind durch Attrappen ersetzt — auch in den
Positivkontrollen und auch in per ``spawn`` gestarteten Enkeln (die Attrappen
stehen auf Modulebene des Kindskripts, das ``spawn`` neu laedt).
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WARN = "STAB-39"


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LIGHTOS_")}
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    env.pop("PYTHONPATH", None)
    env.update(extra)
    return env


def _regulaer(tmp_path: Path) -> Path:
    """Der Datenordner, den die echte App unter diesem (tmp-)HOME benutzte."""
    home = tmp_path / "home"
    if sys.platform == "win32":
        return home / "AppData" / "Roaming" / "LightOS"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "LightOS"
    return home / ".local" / "share" / "LightOS"


def _lauf(tmp_path: Path, code: str, **extra: str):
    skript = tmp_path / "kind.py"
    skript.write_text(textwrap.dedent(code).replace("@REPO@", repr(str(REPO))),
                      encoding="utf-8")
    r = subprocess.run([sys.executable, str(skript)], cwd=str(tmp_path),
                       env=_env(tmp_path, **extra), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=180)
    assert r.returncode == 0, f"Kind rot:\n{r.stdout}\n{r.stderr}"
    zeile = [z for z in r.stdout.splitlines() if z.startswith("ERGEBNIS ")][-1]
    return json.loads(zeile[len("ERGEBNIS "):]), r.stderr


_PFADE = """
import json, sys
sys.path.insert(0, @REPO@)
from src.core import paths
from src.core import app_state
print("ERGEBNIS " + json.dumps({"dir": paths.app_data_dir(),
                                "show_db": app_state.SHOW_DB_PATH}))
"""


def _unter(pfad: str, wurzel: Path) -> bool:
    p = os.path.normcase(os.path.realpath(pfad))
    w = os.path.normcase(os.path.realpath(str(wurzel)))
    return p == w or p.startswith(w + os.sep)


# ── (a)–(c) Datenordner ────────────────────────────────────────────────────

def test_a_probeskript_bekommt_wegwerf_ordner_mit_warnung(tmp_path):
    erg, err = _lauf(tmp_path, _PFADE)
    home = tmp_path / "home"
    assert not _unter(erg["dir"], home), erg
    assert not _unter(erg["show_db"], home), erg
    assert not _regulaer(tmp_path).exists(), "regulaerer Datenordner wurde angelegt"
    assert WARN in err and "WEGWERF" in err, err
    assert err.count("WEGWERF-Datenordner") == 1, "Warnzeile soll EINMAL erscheinen"


def test_a2_daten_ordner_vorgabe_wird_benutzt(tmp_path):
    ziel = tmp_path / "vorgabe" / "LightOS"
    erg, _ = _lauf(tmp_path, _PFADE, LIGHTOS_DATEN_ORDNER=str(ziel))
    assert os.path.normcase(erg["dir"]) == os.path.normcase(str(ziel))


def test_a3_einzel_override_hat_vorrang(tmp_path):
    db = tmp_path / "eigen" / "show.db"
    erg, _ = _lauf(tmp_path, _PFADE, LIGHTOS_SHOW_DB=str(db))
    assert erg["show_db"] == str(db)


def test_b_echte_app_markierung_loest_regulaer_auf(tmp_path):
    erg, err = _lauf(tmp_path, _PFADE, LIGHTOS_ECHTE_APP="1")
    assert os.path.normcase(erg["dir"]) == os.path.normcase(str(_regulaer(tmp_path)))
    assert WARN not in err, err


def test_c_echte_daten_freigabe_loest_regulaer_auf(tmp_path):
    erg, err = _lauf(tmp_path, _PFADE, LIGHTOS_ECHTE_DATEN="1")
    assert os.path.normcase(erg["dir"]) == os.path.normcase(str(_regulaer(tmp_path)))
    assert "WEGWERF" not in err, err


# ── (d) DMX-Ausgabe ────────────────────────────────────────────────────────

_DMX = """
import json, os, socket, sys
sys.path.insert(0, @REPO@)

# Attrappen auf MODULEBENE: ``spawn`` laedt dieses Skript im Enkel neu, die
# Attrappen gelten also auch dort — kein Prozess fasst je ein echtes Geraet an.
import serial
import serial.tools.list_ports as _lp
GEOEFFNET = []
class _FakeSerial:
    def __init__(self, port=None, *a, **k):
        GEOEFFNET.append(port)
        self.port = port
        self.is_open = True
    def write(self, b):
        return len(b)
    def __getattr__(self, name):
        return lambda *a, **k: None
serial.Serial = _FakeSerial
_lp.comports = lambda *a, **k: []
GESENDET = []
class _FakeSock(socket.socket):
    def sendto(self, data, *a):
        GESENDET.append(len(data))
        return len(data)
socket.socket = _FakeSock
# Kein rohes USB, auch nicht im Enkel: pyusb laesst sich nicht importieren.
for _m in ("usb", "usb.core", "usb.util", "libusb_package"):
    sys.modules[_m] = None

if __name__ == "__main__":
    import multiprocessing
    from src.core.dmx.output_manager import OutputManager
    from src.core.dmx.artnet import ArtNetSender
    from src.core.dmx.sacn import SACNSender
    from src.core.dmx import enttec_pro
    om = OutputManager()
    om.add_enttec(1, "/dev/ttyLIGHTOSFAKE0")
    om.add_udmx(2, "")
    try:
        enttec_pro.EnttecPro("/dev/ttyLIGHTOSFAKE1").send_dmx(bytes(512))
        direkt = "offen"
    except Exception as e:
        direkt = type(e).__name__
    a = ArtNetSender("127.0.0.1"); a.send_dmx(0, bytes(512)); a.close()
    s = SACNSender("127.0.0.1"); s.send_dmx(1, bytes(512)); s.close()
    kinder = len(multiprocessing.active_children())
    for u in (1, 2):
        try:
            om.remove_output(u)
        except Exception:
            pass
    print("ERGEBNIS " + json.dumps({"serial": GEOEFFNET, "sendto": GESENDET,
                                    "kinder": kinder, "direkt": direkt}), flush=True)
    os._exit(0)
"""


def test_d_ohne_markierung_oeffnet_nichts_und_sendet_nichts(tmp_path):
    erg, err = _lauf(tmp_path, _DMX)
    assert erg["serial"] == [], erg
    assert erg["sendto"] == [], erg
    assert erg["kinder"] == 0, f"Sendeprozess gestartet: {erg}"
    assert erg["direkt"] != "offen", erg
    assert WARN in err and "Ausgabe" in err, err


def test_d2_positivkontrolle_mit_freigabe_wird_geoeffnet_und_gesendet(tmp_path):
    """Gegenprobe: dieselbe Attrappe sieht das Oeffnen/Senden, sobald die
    Ausgabe freigegeben ist — sonst bewiese (d) nur eine taube Attrappe."""
    erg, err = _lauf(tmp_path, _DMX, LIGHTOS_ECHTE_AUSGABE="1",
                     LIGHTOS_SERIAL_INPROC="1", LIGHTOS_KEIN_USB="1")
    assert "/dev/ttyLIGHTOSFAKE1" in erg["serial"], erg
    assert erg["sendto"], erg
    assert erg["direkt"] == "offen", erg


# ── (d3) Netzwerk-Laser (Gegenpruefung 31.10.) ─────────────────────────────

_LASER = """
import json, os, socket, sys
sys.path.insert(0, @REPO@)
VERBUNDEN, GESENDET = [], []
def _fake_connect(addr, *a, **k):
    VERBUNDEN.append(addr[1])
    raise OSError("Attrappe: kein DAC")
socket.create_connection = _fake_connect
class _FakeSock(socket.socket):
    def sendto(self, data, *a):
        GESENDET.append(len(data))
        return len(data)
socket.socket = _FakeSock
from src.core.laser.etherdream import EtherDreamConnection
from src.core.laser.idn import IDNConnection
erg = {}
for name, conn in (("etherdream", EtherDreamConnection("127.0.0.1")),
                   ("idn", IDNConnection("127.0.0.1"))):
    try:
        conn.connect()
        if name == "idn":
            conn._send(b"\\x00" * 8)
        erg[name] = "offen"
    except Exception as e:
        erg[name] = type(e).__name__
erg.update(verbunden=VERBUNDEN, gesendet=GESENDET)
print("ERGEBNIS " + json.dumps(erg), flush=True)
"""


def test_d3_laser_ohne_markierung_verbindet_und_sendet_nicht(tmp_path):
    erg, err = _lauf(tmp_path, _LASER)
    assert erg["etherdream"] == "EtherDreamError", erg
    assert erg["idn"] == "IDNError", erg
    assert erg["verbunden"] == [] and erg["gesendet"] == [], erg
    assert WARN in err and "Laser" in err, err


def test_d4_laser_positivkontrolle_mit_freigabe(tmp_path):
    erg, _ = _lauf(tmp_path, _LASER, LIGHTOS_ECHTE_AUSGABE="1")
    assert erg["verbunden"], erg            # die Attrappe sah den Verbindungsversuch
    assert erg["idn"] == "offen" and erg["gesendet"], erg


# ── (a5) Datenumzug und Diagnose-Ziel bleiben im Wegwerf-Bereich ──────────

_UMZUG = """
import json, os, sys
sys.path.insert(0, @REPO@)
from src.core import datenumzug, diagnose_log, paths
erg = datenumzug.uebernehme_alte_daten(log=lambda m: None)
print("ERGEBNIS " + json.dumps({"umzug": erg.uebersprungen,
                                "diagnose": diagnose_log.standard_ziel(),
                                "dir": paths.app_data_dir()}), flush=True)
"""


def test_a5_ohne_freigabe_kein_datenumzug_und_kein_desktop(tmp_path):
    (tmp_path / "home" / "Desktop").mkdir(parents=True)
    erg, _ = _lauf(tmp_path, _UMZUG)
    assert erg["umzug"] and WARN in erg["umzug"], erg
    assert not _unter(erg["diagnose"], tmp_path / "home"), erg
    assert _unter(erg["diagnose"], Path(erg["dir"])), erg
    # Gegenprobe: mit Freigabe wie bisher (Desktop, Datenumzug laeuft an).
    mit, _ = _lauf(tmp_path, _UMZUG, LIGHTOS_ECHTE_DATEN="1", LIGHTOS_NO_DATENUMZUG="1")
    assert _unter(mit["diagnose"], tmp_path / "home" / "Desktop"), mit
    assert WARN not in (mit["umzug"] or ""), mit


# ── (a4) ein SANDKASTEN ausserhalb des Temp-Bereichs gilt nicht ────────────

def test_a4_sandkasten_ausserhalb_temp_gilt_nicht(tmp_path):
    """Gegenpruefung 31.10.: unter macOS lenkt die Suite nur XDG/APPDATA um, der
    Ordner kommt aber aus HOME — ``LIGHTOS_SANDKASTEN=1`` behauptete dann einen
    Sandkasten, den es nicht gibt. Nachgestellt ohne echten Pfad: der Temp-
    Bereich des Kindes (TMPDIR/TEMP) ist ein Unterordner von ``tmp_path``, der
    Datenordner liegt daneben, also AUSSERHALB davon."""
    temp = tmp_path / "temp"
    temp.mkdir()
    extra = {"LIGHTOS_SANDKASTEN": "1", "TMPDIR": str(temp), "TEMP": str(temp),
             "TMP": str(temp)}
    erg, err = _lauf(tmp_path, _PFADE, **extra)
    assert not _unter(erg["dir"], tmp_path / "home"), erg
    assert _unter(erg["dir"], temp), erg
    assert WARN in err, err
    # Gegenprobe: liegt der Datenordner IM Temp-Bereich, gilt der Sandkasten.
    erg2, err2 = _lauf(tmp_path, _PFADE, LIGHTOS_SANDKASTEN="1")
    assert os.path.normcase(erg2["dir"]) == os.path.normcase(str(_regulaer(tmp_path)))
    assert "WEGWERF" not in err2, err2


# ── (e) main.py setzt die Markierung vor dem ersten src-Import ─────────────

def test_e_main_setzt_markierung_vor_erstem_src_import():
    baum = ast.parse((REPO / "main.py").read_text(encoding="utf-8"))
    markierung = erster_src = None
    for i, knoten in enumerate(baum.body):
        if isinstance(knoten, (ast.Import, ast.ImportFrom)):
            namen = ([knoten.module or ""] if isinstance(knoten, ast.ImportFrom)
                     else [a.name for a in knoten.names])
            if erster_src is None and any(n == "src" or n.startswith("src.") for n in namen):
                erster_src = i
        if markierung is None and isinstance(knoten, ast.If):
            text = ast.unparse(knoten)
            if ("__name__ == '__main__'" in text
                    and "_echte_app_markieren()" in text):
                markierung = i
    assert markierung is not None, "main.py setzt LIGHTOS_ECHTE_APP nicht (als __main__)"
    assert erster_src is not None
    assert markierung < erster_src, "Markierung steht NACH dem ersten src-Import"


def test_e2_main_import_aus_test_setzt_keine_markierung(tmp_path):
    """Wer ``main`` nur importiert (Tests), ist nicht die echte App."""
    erg, _ = _lauf(tmp_path, """
    import json, os, sys
    sys.path.insert(0, @REPO@)
    import main  # noqa: F401
    print("ERGEBNIS " + json.dumps({"m": os.environ.get("LIGHTOS_ECHTE_APP")}), flush=True)
    os._exit(0)
    """)
    assert erg["m"] is None


def test_e3_agent_shell_bekommt_keine_markierung(tmp_path):
    """Gegenpruefung 31.10.: ein Agent (Claude Code setzt ``CLAUDECODE=1``),
    der ``main.py`` startet, darf nicht die echte App werden. Ohne die Variable
    markiert ``main`` wie bisher. Geprueft an einem Wegwerf-``env``-dict, die
    App startet nie."""
    erg, err = _lauf(tmp_path, """
    import json, os, sys
    sys.path.insert(0, @REPO@)
    import main
    agent, mensch = {"CLAUDECODE": "1"}, {}
    a, m = main._echte_app_markieren(agent), main._echte_app_markieren(mensch)
    print("ERGEBNIS " + json.dumps({"a": [a, agent.get("LIGHTOS_ECHTE_APP")],
                                    "m": [m, mensch.get("LIGHTOS_ECHTE_APP")],
                                    "prozess": os.environ.get("LIGHTOS_ECHTE_APP")}),
          flush=True)
    os._exit(0)
    """)
    assert erg["a"] == [False, None]
    assert erg["m"] == [True, "1"]
    assert erg["prozess"] is None
    assert WARN in err and "CLAUDECODE" in err


# ── (f) der DMX-Sendeprozess erbt die Markierung ───────────────────────────

def test_f_spawn_kind_erbt_markierung(tmp_path):
    """Die Markierung ist eine UMGEBUNGSvariable: ein per ``spawn`` gestarteter
    Prozess (so startet ``serial_process``/``udmx_process`` den Sender) sieht
    die Freigabe ebenfalls. Ohne Markierung sieht er sie nicht."""
    code = """
    import json, os, sys
    sys.path.insert(0, @REPO@)

    def _frage(q):
        from src.core import paths
        q.put(paths.echte_ausgabe_erlaubt())

    if __name__ == "__main__":
        import multiprocessing as mp
        if os.environ.get("NACHSTELLEN_WIE_MAIN"):
            os.environ["LIGHTOS_ECHTE_APP"] = "1"   # wie main.py
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        p = ctx.Process(target=_frage, args=(q,))
        p.start(); p.join(60)
        print("ERGEBNIS " + json.dumps({"kind": q.get(timeout=5)}))
    """
    mit, _ = _lauf(tmp_path, code, NACHSTELLEN_WIE_MAIN="1")
    ohne, _ = _lauf(tmp_path, code)
    assert mit["kind"] is True
    assert ohne["kind"] is False


def test_f2_main_nutzt_spawn_nach_der_markierung():
    """``serial_process`` startet den Sender per ``spawn`` — der erbt
    ``os.environ`` zum Startzeitpunkt. Haelt fest, dass es ``os.environ`` ist
    (keine Modul-Globale, die ein spawn-Kind nicht saehe)."""
    text = (REPO / "src" / "core" / "paths.py").read_text(encoding="utf-8")
    assert 'ECHTE_APP_VAR = "LIGHTOS_ECHTE_APP"' in text
    assert "os.environ.get(name)" in text


@pytest.mark.parametrize("datei", ["install.py", "uninstall.py",
                                   "tools/collect_crash_report.py"])
def test_g_bestands_skripte_geben_echte_daten_nur_als_skript_frei(datei):
    text = (REPO / datei).read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":\n    os.environ.setdefault("LIGHTOS_ECHTE_DATEN", "1")' in text


def test_h_coordination_nennt_die_freigaben():
    """Die Entwickler-Doku sagt, wie man bewusst echt arbeitet."""
    text = (REPO / "COORDINATION.md").read_text(encoding="utf-8")
    for wort in ("STAB-39", "LIGHTOS_ECHTE_APP", "LIGHTOS_ECHTE_DATEN",
                 "LIGHTOS_ECHTE_AUSGABE", "LIGHTOS_DATEN_ORDNER", "LIGHTOS_SANDKASTEN"):
        assert wort in text, wort


# ── (f) sichtbarer Hinweis: Fenstertitel im Probelauf ──────────────────────

_TITEL = """
import json, sys
sys.path.insert(0, @REPO@)
from src.core import paths
print("ERGEBNIS " + json.dumps({"zusatz": paths.probelauf_titelzusatz()}), flush=True)
"""

_PROBELAUF = "PROBELAUF (Wegwerf-Daten, keine Ausgabe)"


def test_f_titelzusatz_nur_ohne_echte_daten(tmp_path):
    """Startet ein Agent die App (CLAUDECODE=1 -> keine Markierung), arbeitet der
    Bediener sonst unbemerkt in einem leeren Wegwerf-Ordner ohne DMX — und
    verliert seine Aenderungen beim Beenden. Der Titel sagt es ihm."""
    erg, _ = _lauf(tmp_path, _TITEL)
    assert _PROBELAUF in erg["zusatz"], erg
    erg, _ = _lauf(tmp_path, _TITEL, LIGHTOS_ECHTE_AUSGABE="1")
    assert "PROBELAUF (Wegwerf-Daten)" in erg["zusatz"], erg
    # Echte App, bewusste Datenfreigabe, gueltiger Sandkasten: KEIN Hinweis.
    for extra in ({"LIGHTOS_ECHTE_APP": "1"}, {"LIGHTOS_ECHTE_DATEN": "1"},
                  {"LIGHTOS_SANDKASTEN": "1"}):
        erg, _ = _lauf(tmp_path, _TITEL, **extra)
        assert erg["zusatz"] == "", (extra, erg)


def test_f2_anleitungsbilder_sandkasten_ohne_hinweis(tmp_path):
    """Die Anleitungsbilder laufen im Sandkasten (``tools/anleitungsbilder``)
    — ihre Fensterbilder duerfen KEINEN Probelauf-Hinweis im Titel tragen."""
    erg, _ = _lauf(tmp_path, """
    import json, os, shutil, sys
    sys.path.insert(0, os.path.join(@REPO@, "tools"))
    from anleitungsbilder import sandbox
    sb = sandbox.einrichten()
    sys.path.insert(0, @REPO@)
    from src.core import paths
    erg = {"zusatz": paths.probelauf_titelzusatz(),
           "erlaubt": paths.echte_daten_erlaubt()}
    os.chdir(@REPO@)
    shutil.rmtree(sb.basis, ignore_errors=True)
    print("ERGEBNIS " + json.dumps(erg), flush=True)
    """)
    assert erg == {"zusatz": "", "erlaubt": True}, erg


def test_f3_hauptfenster_traegt_den_hinweis_in_jedem_titel(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from src.core import paths
    from src.ui import main_window as mw
    # Unter der Suite (gueltiger Sandkasten) bleibt der Titel unveraendert.
    assert paths.probelauf_titelzusatz() == ""
    app = QApplication.instance() or QApplication([])
    zusatz = " — " + _PROBELAUF
    monkeypatch.setattr(mw, "probelauf_titelzusatz", lambda: zusatz)
    win = mw.MainWindow()
    try:
        assert win.windowTitle() == "LightOS" + zusatz
        win.setWindowTitle("LightOS  -  meine.lshow")
        assert win.windowTitle() == "LightOS  -  meine.lshow" + zusatz
        win.setWindowTitle(win.windowTitle())          # kein doppelter Zusatz
        assert win.windowTitle().count("PROBELAUF") == 1
        # Echte App (leerer Zusatz): Titel genau wie bisher.
        win._probelauf_zusatz = ""
        win.setWindowTitle("LightOS  -  meine.lshow")
        assert win.windowTitle() == "LightOS  -  meine.lshow"
    finally:
        win.deleteLater()
        app.processEvents()


# ── (g) Generatoren nennen den TATSAECHLICHEN Zielort ──────────────────────

_ZIEL = """
import json, os, sys
sys.path.insert(0, @REPO@)
from src.core import paths
from src.core.stage.stage_definition import StageDefinition, save_stage
p = save_stage(StageDefinition(name="Probe"))
print("ERGEBNIS " + json.dumps({"pfad": p, "text": paths.ziel_hinweis(p)}), flush=True)
"""


def test_g_ziel_hinweis_nennt_wegwerf_ordner_und_freigabe(tmp_path):
    """build_grosses_rig.py meldete ``-> %APPDATA%/LightOS/stages`` — ohne
    Freigabe landet die Buehne aber im Wegwerf-Ordner (TOOL-13: bewusst)."""
    erg, _ = _lauf(tmp_path, _ZIEL)
    assert erg["text"].startswith(erg["pfad"]), erg
    assert "WEGWERF" in erg["text"] and "LIGHTOS_ECHTE_DATEN=1" in erg["text"], erg
    assert not _unter(erg["pfad"], tmp_path / "home"), erg
    erg, _ = _lauf(tmp_path, _ZIEL, LIGHTOS_ECHTE_DATEN="1")
    assert erg["text"] == erg["pfad"], erg
    assert _unter(erg["pfad"], _regulaer(tmp_path)), erg


def test_g2_kein_generator_behauptet_appdata_als_ziel():
    treffer = []
    for p in sorted((REPO / "tools").glob("*.py")):
        for nr, zeile in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "print(" in zeile and "%APPDATA%" in zeile:
                treffer.append(f"{p.name}:{nr}")
    assert treffer == [], treffer
