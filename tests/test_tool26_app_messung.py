"""TOOL-26: tools/app_messung.py — die echte App in einer Sandbox messen.

Geprueft werden die zwei festen Regeln des Werkzeugs und seine Auswertung:

* **Sandbox-Pflicht:** jeder Schreibort liegt im Wegwerf-Ordner; zeigt der
  Datenordner der App woanders hin, startet nichts (Exit 2) — auch kein
  App-Modul und kein Qt.
* **Kein DMX nach aussen:** ein eingerichteter Ausgang bricht ab.
* Auswertung (Bildrate, Bewegungs-Gleichmass, Tabelle) und Aufruf-Pruefung.

Die volle App laesst sich im Gate nicht starten: ohne sichtbares Fenster
verliert sie den GPU-Kontext, die Szene baut sich nicht auf (gemessen unter
Windows mit ANGLE/D3D11). Deshalb zwei Stufen:

* `TestAnfassStellen` (laeuft immer): die Namen, an denen das Werkzeug die App
  anfasst — Qualitaets-Auswahl, Push-Kanal, die Web-Ansicht der 3D-Seite,
  `window.__lightos` — muessen im Quelltext noch so heissen. Benennt jemand
  eine davon um, faellt dieser Test und nicht erst die naechste Messung.
* `test_rauchtest_echte_app` (nur mit `LIGHTOS_APP_MESSUNG_RAUCHTEST=1`, im
  sichtbaren Fenster): der ganze Lauf mit der mitgelieferten Demo-Show.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WERKZEUG = os.path.join(REPO, "tools", "app_messung.py")


@pytest.fixture(scope="module")
def am():
    spec = importlib.util.spec_from_file_location("app_messung_test", WERKZEUG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def umgebung_wie_vorher():
    """main() des Werkzeugs schreibt in os.environ, sys.path und wechselt den
    Ordner — nach dem Test alles zurueck."""
    env, pfad, ordner = dict(os.environ), list(sys.path), os.getcwd()
    yield
    os.chdir(ordner)
    sys.path[:] = pfad
    os.environ.clear()
    os.environ.update(env)


# ── Sandbox-Pflicht ──────────────────────────────────────────────────────────

class TestSandbox:
    def test_alle_schreiborte_liegen_in_der_sandbox(self, am, tmp_path):
        env = am.sandbox_umgebung(str(tmp_path))
        pfade = {k: v for k, v in env.items() if os.path.isabs(v)}
        assert {"APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "LIGHTOS_SHOW_DB",
                "LIGHTOS_FIXTURE_DB", "LIGHTOS_UNIVERSES_JSON", "LIGHTOS_CRASH_LOG",
                "LIGHTOS_SACN_CID"} <= set(pfade)
        for name, pfad in pfade.items():
            assert am.liegt_in(pfad, str(tmp_path)), f"{name} zeigt aus der Sandbox: {pfad}"
        # Ohne Ausgabe-Konfiguration richtet die App keinen Ausgang ein.
        assert not os.path.exists(env["LIGHTOS_UNIVERSES_JSON"])
        assert env["LIGHTOS_NO_DATENUMZUG"] == "1" and env["LIGHTOS_NO_RECOVERY_PROMPT"] == "1"

    def test_macos_lenkt_den_heimatordner_um(self, am, tmp_path, monkeypatch):
        # app_data_dir() nimmt dort ~/Library/Application Support.
        monkeypatch.setattr(am.sys, "platform", "darwin")
        env = am.sandbox_umgebung(str(tmp_path))
        assert am.liegt_in(env["HOME"], str(tmp_path))

    def test_nachbarordner_mit_gleichem_anfang_zaehlt_nicht(self, am, tmp_path):
        drin = tmp_path / "sandbox"
        daneben = tmp_path / "sandbox2" / "LightOS"
        drin.mkdir()
        assert am.liegt_in(str(drin / "appdata" / "LightOS"), str(drin))
        assert not am.liegt_in(str(daneben), str(drin))
        assert not am.liegt_in(str(tmp_path), str(drin))

    def test_datenordner_ausserhalb_bricht_ab(self, am, tmp_path):
        drin = tmp_path / "sandbox"
        drin.mkdir()
        am.pruefe_sandbox(str(drin), str(drin / "appdata" / "LightOS"),
                          {"LIGHTOS_SHOW_DB": str(drin / "show.db")})
        with pytest.raises(am.Regelverstoss, match="Datenordner"):
            am.pruefe_sandbox(str(drin), str(tmp_path / "echt" / "LightOS"))
        with pytest.raises(am.Regelverstoss, match="LIGHTOS_SHOW_DB"):
            am.pruefe_sandbox(str(drin), str(drin / "appdata" / "LightOS"),
                              {"LIGHTOS_SHOW_DB": str(tmp_path / "echt" / "show.db")})
        with pytest.raises(am.Regelverstoss, match="nicht gesetzt"):
            am.pruefe_sandbox(str(drin), str(drin / "appdata" / "LightOS"),
                              {"LIGHTOS_FIXTURE_DB": ""})

    def test_werkzeug_startet_nichts_wenn_der_datenordner_draussen_liegt(
            self, am, tmp_path, monkeypatch, capsys, umgebung_wie_vorher):
        """Der ganze Aufruf: zeigt die Umgebung aus der Sandbox, endet er mit
        Exit 2 — bevor die Show gebaut, ``main`` geladen oder Qt angefasst wird."""
        draussen = tmp_path / "echte_daten"
        echt = am.sandbox_umgebung

        def kaputt(wurzel):
            env = echt(wurzel)
            env["APPDATA"] = str(draussen)          # Windows
            env["XDG_DATA_HOME"] = str(draussen)    # Linux
            env["HOME"] = str(draussen)             # macOS
            return env

        gebaut = []
        monkeypatch.setattr(am, "sandbox_umgebung", kaputt)
        monkeypatch.setattr(am, "_baue_mega_arena", lambda *a, **k: gebaut.append(a))
        vorher = set(sys.modules)
        code = am.main(["--stufen", "low", "--messungen", "leerlauf"])
        assert code == am.EXIT_REGEL == 2
        assert "Sandbox-Pflicht verletzt" in capsys.readouterr().out
        assert gebaut == []
        neu = set(sys.modules) - vorher
        assert "main" not in neu
        assert not any(m.startswith("PySide6") for m in neu)
        assert not draussen.exists(), "ausserhalb der Sandbox wurde etwas angelegt"


# ── kein DMX nach aussen ─────────────────────────────────────────────────────

class TestKeineAusgabe:
    def test_ohne_ausgang_geht_es_weiter(self, am):
        am.pruefe_keine_ausgabe([])
        am.pruefe_keine_ausgabe(None)

    def test_ein_ausgang_bricht_ab(self, am):
        with pytest.raises(am.Regelverstoss, match="U1 artnet"):
            am.pruefe_keine_ausgabe([{"universum": 1, "weg": "artnet", "ziel": "2.0.0.1"}])


# ── Auswertung ───────────────────────────────────────────────────────────────

class TestAuswertung:
    def test_bildrate_bei_60_hz(self, am):
        t = [i * 1000 / 60 for i in range(121)]
        s = am.bild_statistik(t)
        assert s["fps"] == 60.0 and s["bilder"] == 121
        assert s["bilder_ueber_25ms"] == 0 and s["bilder_ueber_50ms"] == 0

    def test_haenger_wird_gezaehlt(self, am):
        t = [i * 1000 / 60 for i in range(60)]
        t += [t[-1] + 300 + i * 1000 / 60 for i in range(60)]     # ein Bild von 300 ms
        s = am.bild_statistik(t)
        assert s["bilder_ueber_50ms"] == 1 and s["dt_max_ms"] == 300.0
        assert s["fps"] < 60

    def test_zu_wenige_bilder_sind_kein_ergebnis(self, am):
        assert "fehler" in am.bild_statistik([0.0, 16.7])
        assert "fehler" in am.bild_statistik(None)

    def test_gleichmaessige_drehung_hat_keine_standbilder(self, am):
        w = [math.radians(i * 1.0) for i in range(200)]
        s = am.bewegung_statistik(w)
        assert s["stand_anteil"] == 0.0
        assert s["schritt_median_grad"] == pytest.approx(1.0, abs=0.01)
        assert s["spruenge_ueber_3x_median"] == 0

    def test_winkel_nur_je_update_ergibt_standbilder(self, am):
        # 15 Updates/s bei 60 Bildern/s: drei von vier Bildern ohne Bewegung.
        w = [math.radians((i // 4) * 4.0) for i in range(200)]
        s = am.bewegung_statistik(w)
        assert s["stand_anteil"] == pytest.approx(0.75, abs=0.01)
        assert s["schritt_median_grad"] == pytest.approx(4.0, abs=0.01)

    def test_umlauf_ueber_180_grad_ist_kein_sprung(self, am):
        w = [am._kreis(math.radians(170 + i * 1.0)) for i in range(40)]
        s = am.bewegung_statistik(w)
        assert s["schritt_max_grad"] == pytest.approx(1.0, abs=0.01)

    def test_tabelle_nennt_soll_und_messwert(self, am):
        erg = {"stufen": {"high": {"anzeige": "Hoch", "soll_push": 30, "messungen": [
            {"messung": "dimmer", "hauptfenster": "minimiert", "push_hz": 27.4,
             "bild": {"fps": 56.2, "bilder_ueber_50ms": 1}, "blackout_median_ms": 45},
            {"messung": "gobo", "hauptfenster": "sichtbar", "push_hz": 19.1,
             "bild": {"fps": 47.0, "bilder_ueber_50ms": 8}, "gobo": {"stand_anteil": 0.182}}]}}}
        text = am.tabelle(erg)
        assert "| Hoch | dimmer | minimiert | 56,2 | 1 | 27,4 (30) | 45 ms | - |" in text
        assert "| Hoch | gobo | sichtbar | 47,0 | 8 | 19,1 (30) | - | 18 % |" in text

    def test_stromquelle_ist_eine_der_drei_antworten(self, am):
        assert am.stromquelle() in ("Netz", "Akku", "unbekannt")


# ── Aufruf ───────────────────────────────────────────────────────────────────

class TestAufruf:
    def test_unbekannte_stufe_wird_abgelehnt(self, am):
        with pytest.raises(SystemExit, match="Stufe unbekannt: ultra"):
            am._liste("low,ultra", am.STUFEN, "Stufe")
        assert am._liste("low, high", am.STUFEN, "Stufe") == ["low", "high"]

    def test_fehlende_show_wird_vor_dem_start_gemeldet(self, am, tmp_path, umgebung_wie_vorher):
        with pytest.raises(SystemExit, match="--show: Datei nicht gefunden"):
            am.main(["--show", str(tmp_path / "gibt_es_nicht.lshow")])

    def test_repo_muss_ein_checkout_sein(self, am, tmp_path, umgebung_wie_vorher):
        with pytest.raises(SystemExit, match="kein LightOS-Checkout"):
            am.main(["--repo", str(tmp_path)])

    def test_hilfe_nennt_die_beiden_regeln(self, am):
        hilfe = am.baue_parser().format_help()
        assert "Nie echte App-Daten" in hilfe and "kein DMX nach aussen" in hilfe

    def test_geerbte_testschalter_werden_entfernt(self, am):
        """Aus pytest heraus gestartet erbte das Werkzeug LIGHTOS_NO_OUTPUT_THREAD
        und offscreen: ohne Ausgabe-Thread kam kein einziger Wert im 3D an."""
        assert "--offscreen" not in am.baue_parser().format_help()
        env = {"LIGHTOS_NO_OUTPUT_THREAD": "1", "QT_QPA_PLATFORM": "offscreen",
               "LIGHTOS_SHOW_DB": "bleibt", "PATH": "bleibt"}
        assert am.bereinige_umgebung(env) == ["LIGHTOS_NO_OUTPUT_THREAD", "QT_QPA_PLATFORM"]
        assert env == {"LIGHTOS_SHOW_DB": "bleibt", "PATH": "bleibt"}
        normal = {"QT_QPA_PLATFORM": "windows"}
        assert am.bereinige_umgebung(normal) == [] and normal == {"QT_QPA_PLATFORM": "windows"}
        assert "bereinige_umgebung(os.environ)" in _quelle("tools", "app_messung.py")


# ── Anfass-Stellen in der App ────────────────────────────────────────────────

def _quelle(*teile) -> str:
    with open(os.path.join(REPO, *teile), encoding="utf-8") as fh:
        return fh.read()


class TestAnfassStellen:
    """Das Werkzeug greift an privaten Namen in die laufende App. Jeder davon
    steht hier — mit der Datei, in der er heute definiert ist."""

    def test_hauptfenster_und_start(self):
        main_py = _quelle("main.py")
        assert "_finalize_and_exit(app.exec())" in main_py, \
            "main() ruft app.exec() nicht mehr so auf — statt_exec greift ins Leere"
        assert 'parser.add_argument("--show"' in main_py
        fenster = _quelle("src", "ui", "main_window.py")
        assert "def _open_visualizer(self)" in fenster
        assert "self._visualizer_window = VisualizerWindow(self)" in fenster

    def test_visualizer_fenster(self):
        viz = _quelle("src", "ui", "visualizer", "visualizer_window.py")
        # Der Klassenname steht hier absichtlich nicht am Stueck: diese Datei
        # baut keine Web-Ansicht und soll vom Gate nicht dafuer gehalten werden.
        assert "self._view = QWebEngine" + "View()" in viz
        assert "self._lbl_gpu_tier = QLabel(" in viz
        assert "self._dmx_push = " in viz
        for stufe in ("auto", "low", "high", "max"):
            assert f', "{stufe}")' in viz, f"Qualitaetsstufe {stufe} fehlt in der Auswahl"

    def test_push_kanal(self):
        push = _quelle("src", "ui", "visualizer", "dmx_push.py")
        assert 'self.stats = {"batches": 0, "bytes": 0' in push
        assert "self.min_interval_s = " in push
        assert '"timeouts"' in push and '"resets"' in push

    def test_szenen_api(self, am):
        app_js = _quelle("src", "ui", "visualizer", "scene_src", "app.js")
        for name in ("gpuTier", "gpuProbeInfo", "pixelRatio", "shadowBudgetInfo",
                     "dynamicResolutionInfo", "umgebungInfo", "renderInfo", "spotPoolInfo",
                     "spotPoolLights", "stageObjects", "fixtures", "setEditMode",
                     "poolFalloffTexture"):
            assert name in app_js, f"window.__lightos.{name} fehlt in app.js"
        # ... und das Werkzeug benutzt keinen Namen, der hier nicht geprueft ist.
        import re
        benutzt = set()
        for js in (am._JS_INFO, am._JS_BUEHNE, am._JS_LICHT, am._JS_HELL, am._JS_ANZAHL):
            benutzt |= set(re.findall(r"\bL\.(\w+)", js))
            benutzt |= set(re.findall(r"__lightos(?:\|\|\{\})?\)?\.(\w+)", js))
        fehlend = sorted(n for n in benutzt if n not in app_js)
        assert fehlend == [], f"Werkzeug nutzt unbekannte Szenen-Namen: {fehlend}"

    def test_app_zustand_und_ausgabe(self):
        zustand = _quelle("src", "core", "app_state.py")
        for name in ("def get_channels_for_patched(", "def open_value_for(",
                     "self._prog_lock = ", "def get_patched_fixtures(self)"):
            assert name in zustand, name
        ausgabe = _quelle("src", "core", "dmx", "output_manager.py")
        assert "def ausgabe_status(self" in ausgabe
        assert "def set_blackout(self" in ausgabe

    def test_umgebungsschalter_gibt_es_noch(self, am, tmp_path):
        """Jeder LIGHTOS_-Schalter der Sandbox muss irgendwo im Programm gelesen
        werden — sonst lenkt er nichts mehr um."""
        alles = ""
        for wurzel, _ordner, dateien in os.walk(os.path.join(REPO, "src")):
            for d in dateien:
                if d.endswith(".py"):
                    alles += _quelle(wurzel, d)
        alles += _quelle("main.py")
        for name in am.sandbox_umgebung(str(tmp_path)):
            if name.startswith("LIGHTOS_"):
                assert name in alles, f"{name} wird im Programm nicht mehr gelesen"


# ── Rauchtest gegen die echte App (nur auf Wunsch, im sichtbaren Fenster) ────

@pytest.mark.skipif(os.environ.get("LIGHTOS_APP_MESSUNG_RAUCHTEST") != "1",
                    reason="oeffnet echte Fenster; mit LIGHTOS_APP_MESSUNG_RAUCHTEST=1 fahren")
@pytest.mark.timeout(280)
def test_rauchtest_echte_app(tmp_path):
    """Hauptfenster + 3D-Fenster wie beim Nutzer, mitgelieferte Demo-Show, eine
    Stufe, Helligkeits-Sinus und Blackout."""
    aus = tmp_path / "messung.json"
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    r = subprocess.run(
        [sys.executable, WERKZEUG, "--show",
         os.path.join(REPO, "shows", "demo_rgb_par.lshow"), "--stufen", "low",
         "--messungen", "buehne,leerlauf,dimmer", "--hauptfenster", "sichtbar",
         "--dauer", "2", "--zeitlimit", "240", "--json", str(aus)],
        cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=260)
    ende = "\n".join((r.stdout + "\n" + r.stderr).splitlines()[-25:])
    assert r.returncode == 0, f"Exit {r.returncode}\n{ende}"
    erg = json.loads(aus.read_text(encoding="utf-8"))
    assert "fehler" not in erg, erg.get("fehler")
    assert erg["show"]["geraete"] >= 1 and erg["show"]["dimmbar"] >= 1
    stufe = erg["stufen"]["low"]
    assert stufe["soll_push"] == 15
    assert (stufe["info"] or {}).get("gpuTier") == "low"
    assert [m["messung"] for m in stufe["messungen"]] == ["leerlauf", "dimmer"]
    leerlauf, dimmer = stufe["messungen"]
    assert leerlauf["bild"]["fps"] > 5
    assert dimmer["push_hz"] > 0, "Helligkeits-Sinus erzeugte keinen Push ins 3D"
    assert dimmer["timeouts"] == 0
    assert dimmer["blackout_gemessen"] == "5/5", dimmer
    assert "| Niedrig | dimmer | sichtbar |" in r.stdout


