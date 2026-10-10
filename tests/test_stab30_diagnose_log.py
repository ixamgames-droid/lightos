"""STAB-30: Sitzungs-Log (Tee) und Diagnosepaket fuer Fernhilfe.

Die Tee-Tests laufen in einem eigenen Python-Prozess: ``install_tee`` haengt
``sys.stdout``/``sys.stderr`` prozessweit um — im pytest-Prozess wuerde das die
Ausgabeerfassung aller folgenden Tests verbiegen.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
import zipfile

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(tmp_path) -> dict:
    """Isolierter Datenordner — nie die echten App-Daten."""
    env = dict(os.environ)
    daten = tmp_path / "daten"
    daten.mkdir(exist_ok=True)
    env["XDG_DATA_HOME"] = str(daten)
    env["APPDATA"] = str(daten)
    env.pop("LIGHTOS_LOG_DIR", None)
    env.pop("LIGHTOS_SESSION_LOG", None)
    env["LIGHTOS_CRASH_LOG"] = str(daten / "LightOS" / "crash.log")
    env["PYTHONPATH"] = _REPO
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(code: str, tmp_path, *args, timeout=120):
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code), *args],
                          capture_output=True, text=True, timeout=timeout,
                          cwd=_REPO, env=_env(tmp_path), encoding="utf-8", errors="replace")


# ── Tee ──────────────────────────────────────────────────────────────────────
def test_tee_schreibt_in_datei_und_terminal(tmp_path):
    log = tmp_path / "logs" / "lightos.log"
    r = _run(f"""
        import sys, threading
        from src.core import diagnose_log as d
        d.install_tee()
        print("[vorher] aus dem Startpuffer")
        assert d.oeffne_sitzungslog("9.9.9", path={str(log)!r})
        print("[test] hallo welt")
        sys.stderr.write("[test] fehlerzeile\\n")
        t = threading.Thread(target=lambda: print("[test] aus dem Faden"),
                             name="Werker")
        t.start(); t.join()
        d.melde_still("probe", ValueError("kaputt"))
        d.melde_still("probe", ValueError("kaputt"))   # gedrosselt
        sys.stdout.flush()
    """, tmp_path)
    assert r.returncode == 0, r.stderr
    # Terminal sieht unveraendert die Rohzeilen
    assert "[test] hallo welt" in r.stdout
    assert "[test] fehlerzeile" in r.stderr
    text = log.read_text(encoding="utf-8")
    assert "=== LightOS-Sitzung" in text and "LightOS: 9.9.9" in text
    assert "[vorher] aus dem Startpuffer" in text
    zeile = next(z for z in text.splitlines() if "[test] hallo welt" in z)
    # Zeitstempel HH:MM:SS.mmm am Zeilenanfang
    assert zeile[2] == ":" and zeile[5] == ":" and zeile[8] == "."
    assert any("!" in z and "[test] fehlerzeile" in z for z in text.splitlines())
    assert "<Werker> [test] aus dem Faden" in text
    assert text.count("[still:probe] ValueError: kaputt") == 1


def test_rotation_haelt_vorige_sitzungen_und_begrenzt_groesse(tmp_path):
    from src.core.diagnose_log import LogSink
    pfad = str(tmp_path / "lightos.log")
    for nr in range(4):                       # vier Sitzungen
        s = LogSink(max_bytes=10_000, backups=2)
        assert s.open(pfad, f"KOPF {nr}\n")
        s.write(f"sitzung {nr}\n")
        s.close()
    assert "sitzung 3" in open(pfad, encoding="utf-8").read()
    assert "sitzung 2" in open(pfad + ".1", encoding="utf-8").read()
    assert "sitzung 1" in open(pfad + ".2", encoding="utf-8").read()
    assert not os.path.exists(pfad + ".3")    # aelteste faellt weg
    # innerhalb einer Sitzung: Groessengrenze -> rotiert, Datei bleibt klein
    s = LogSink(max_bytes=2_000, backups=2)
    assert s.open(pfad)
    for i in range(400):
        s.write(f"zeile {i:04d} " + "x" * 40 + "\n")
    s.close()
    assert os.path.getsize(pfad) < 2_000 + 200
    assert "zeile 0399" in open(pfad, encoding="utf-8").read()
    assert "Fortsetzung" in open(pfad, encoding="utf-8").read()


def test_senke_ist_thread_sicher(tmp_path):
    from src.core.diagnose_log import LogSink, TeeStream
    pfad = str(tmp_path / "t.log")
    s = LogSink()
    assert s.open(pfad)
    tee = TeeStream(None, s)

    def schreibe(n):
        for i in range(200):
            tee.write(f"faden{n}-{i}\n")
    fs = [threading.Thread(target=schreibe, args=(n,)) for n in range(6)]
    for f in fs:
        f.start()
    for f in fs:
        f.join()
    s.close()
    zeilen = [z for z in open(pfad, encoding="utf-8").read().splitlines() if "faden" in z]
    assert len(zeilen) == 1200
    assert all(z.count("faden") == 1 for z in zeilen)


def test_logfehler_blockieren_den_start_nicht(tmp_path):
    from src.core.diagnose_log import LogSink, TeeStream
    blockiert = tmp_path / "ist_eine_datei"
    blockiert.write_text("x")
    s = LogSink()
    # Ziel-"Ordner" ist eine Datei -> open scheitert still, App laeuft weiter
    assert s.open(str(blockiert / "lightos.log"), "kopf\n") is False

    class Kaputt:
        def write(self, _s):
            raise UnicodeEncodeError("cp1252", "x", 0, 1, "kaputte Konsole")

        def flush(self):
            raise OSError("weg")

    tee = TeeStream(Kaputt(), s)
    assert tee.write("ä\n") == 2          # wirft nicht
    tee.flush()
    # Lock haengt (anderer Faden haelt es) -> write wartet nicht ewig
    s2 = LogSink()
    assert s2.open(str(tmp_path / "ok.log"))
    s2._lock.acquire()
    try:
        t = threading.Thread(target=lambda: s2.write("verloren\n"))
        t.start()
        t.join(timeout=3)
        assert not t.is_alive(), "Log-Schreiben hat blockiert"
    finally:
        s2._lock.release()


def test_main_startet_auch_wenn_logordner_unbrauchbar(tmp_path):
    """Ganz oben in main.py: ein kaputter Logordner darf den Import/Start nicht
    verhindern (Pruefung ueber die echten Funktionen in einem frischen Prozess)."""
    r = _run("""
        import os, sys
        os.environ["LIGHTOS_LOG_DIR"] = os.path.join(sys.argv[1], "datei", "logs")
        open(os.path.join(sys.argv[1], "datei"), "w").close()
        from src.core import diagnose_log as d
        d.install_tee()
        assert d.oeffne_sitzungslog("1") is None
        print("[test] laeuft weiter")
    """, tmp_path, str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "[test] laeuft weiter" in r.stdout


# ── Kopfblock ────────────────────────────────────────────────────────────────
def test_kopfblock_enthaelt_felder_und_keinen_benutzerpfad(monkeypatch, tmp_path):
    from src.core import diagnose_log as d
    home = os.path.expanduser("~")
    user = os.path.basename(home)
    # Datenordner unter das Home legen, damit die Anonymisierung greifen MUSS
    monkeypatch.setattr(d, "app_data_dir", lambda: os.path.join(home, ".local", "share", "LightOS"))
    kopf = d.kopfblock("1.2.3")
    for feld in ("LightOS: 1.2.3", "Commit:", "Gefroren", "Betriebssystem:",
                 "Maschine:", "Python:", "PySide6/Qt:", "Datenordner:"):
        assert feld in kopf, feld
    assert home not in kopf
    if len(user) >= 3:
        assert f"/{user}/" not in kopf and f"\\{user}\\" not in kopf
    assert "Datenordner: ~" in kopf


def test_anonymisiere_windows_und_linux_pfade():
    from src.core.diagnose_log import anonymisiere
    # Windows-Profilpfad (Laufwerk/Ordner hier bewusst fiktiv)
    t = anonymisiere(r"D:\Profile\Testerin\AppData\Roaming\LightOS und /srv/testerin/x",
                     home=r"D:\Profile\Testerin", user="Testerin")
    assert "Testerin" not in t
    assert r"~\AppData\Roaming\LightOS" in t
    t2 = anonymisiere("/Users/kim/Library/LightOS kim mag Licht",
                      home="/Users/kim", user="kim")
    assert t2 == "~/Library/LightOS kim mag Licht"


def test_windows_arm_emulation_wird_benannt(monkeypatch):
    from src.core import diagnose_log as d
    if sys.platform != "win32":
        pytest.skip("IsWow64Process2 gibt es nur unter Windows")
    assert "Maschine" in d._windows_architektur()


def test_melde_still_drosselt_je_stelle(capsys):
    from src.core import diagnose_log as d
    d._still_reset()
    for i in range(20):
        d.melde_still("drossel", RuntimeError(f"fehler {i}"))
    for _ in range(50):
        d.melde_still("einmal", OSError("gleich"))
    aus = capsys.readouterr().out
    assert aus.count("[still:drossel]") == d._STILL_MAX_JE_TAG + 1
    assert "nicht mehr gemeldet" in aus
    assert aus.count("[still:einmal]") == 1
    d._still_reset()


# ── Diagnosepaket ────────────────────────────────────────────────────────────
def test_diagnosepaket_enthaelt_logs_und_keine_privaten_dateien(monkeypatch, tmp_path):
    from src.core import diagnose_log as d
    daten = tmp_path / "LightOS"
    (daten / "logs").mkdir(parents=True)
    home = os.path.expanduser("~")
    (daten / "logs" / "lightos.log").write_text(
        f"12:00:00.000   [show_file] geladen {home}/shows/geheim.lshow\n", encoding="utf-8")
    (daten / "logs" / "lightos.log.1").write_text("vorige sitzung\n", encoding="utf-8")
    (daten / "crash.log").write_text("=== LightOS STARTED ===\n", encoding="utf-8")
    (daten / "current_show.db").write_bytes(b"SQLite format 3\0geheim")
    (daten / "current_show.db-wal").write_bytes(b"wal")
    (daten / "shows").mkdir()
    (daten / "shows" / "meine.lshow").write_bytes(b"PK geheim")
    (daten / "ui_prefs.json").write_text(
        '{"remote": {"token": "s3cr3t", "lan_remote_enabled": true},'
        ' "recent_shows": ["/x/a.lshow"], "zoom": 1.5, "letzte_show": "Hochzeit"}',
        encoding="utf-8")
    monkeypatch.setattr(d, "app_data_dir", lambda: str(daten))
    monkeypatch.setattr(d, "crash_log_path", lambda: str(daten / "crash.log"))
    monkeypatch.setenv("LIGHTOS_LOG_DIR", str(daten / "logs"))

    ziel = d.erstelle_diagnosepaket(str(tmp_path / "paket.zip"), "1.0.0")
    with zipfile.ZipFile(ziel) as zf:
        namen = zf.namelist()
        alles = "\n".join(zf.read(n).decode("utf-8") for n in namen)
        einst = zf.read("einstellungen.txt").decode("utf-8")
    assert "logs/lightos.log" in namen and "logs/lightos.log.1" in namen
    assert "crash/crash.log" in namen
    assert {"systeminfo.txt", "einstellungen.txt", "LIESMICH.txt"} <= set(namen)
    assert not [n for n in namen if n.endswith((".lshow", ".db", ".db-wal"))]
    assert "SQLite format" not in alles and "PK geheim" not in alles
    assert "s3cr3t" not in alles and "Hochzeit" not in alles
    assert "zoom = 1.5" in einst and "lan_remote_enabled = True" in einst
    assert home not in alles
    assert "~/shows/geheim.lshow" in alles     # Pfad bleibt lesbar, anonym


def test_cli_diagnose_laeuft_ohne_fenster(tmp_path):
    """``main.py --diagnose ZIEL`` schreibt das Paket und endet mit 0 — ohne
    QApplication/Fenster und ohne Sitzungs-Log/Einzelinstanz-Sperre."""
    ziel = tmp_path / "out" / "paket.zip"
    env = _env(tmp_path)
    env["QT_QPA_PLATFORM"] = "minimal-ungueltig"   # ein Fenster wuerde scheitern
    r = subprocess.run([sys.executable, "main.py", "--diagnose", str(ziel)],
                       capture_output=True, text=True, timeout=180, cwd=_REPO,
                       env=env, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    assert ziel.is_file()
    with zipfile.ZipFile(ziel) as zf:
        assert "systeminfo.txt" in zf.namelist()
    daten = tmp_path / "daten" / "LightOS"
    assert not (daten / "logs" / "lightos.log").exists()
    assert not (daten / "lightos.instance.lock").exists()


# ── Verdrahtung in main.py ───────────────────────────────────────────────────
def _main_quelle() -> str:
    with open(os.path.join(_REPO, "main.py"), encoding="utf-8") as f:
        return f.read()


def test_main_tee_nur_beim_echten_start_und_log_erst_nach_sperre():
    q = _main_quelle()
    assert 'if __name__ == "__main__" and _dl.soll_mitschreiben(sys.argv[1:]):' in q
    # Tee VOR dem PySide6-/MainWindow-Import (deren Startmeldungen gehoeren rein)
    assert q.index("_dl.install_tee()") < q.index("from src.ui.main_window import MainWindow")
    rumpf = q[q.index("def main():"):]
    assert rumpf.index("acquire_instance_lock(") < rumpf.index("_dl.oeffne_sitzungslog(")
    # --diagnose vor Sperre und Crash-Logging (keine Nebenwirkungen)
    assert rumpf.index("_dl.cli_diagnose(") < rumpf.index("acquire_instance_lock(")
    assert rumpf.index("_dl.cli_diagnose(") < rumpf.index("_setup_crash_logging()")


def test_soll_mitschreiben():
    from src.core.diagnose_log import soll_mitschreiben
    assert soll_mitschreiben([])
    assert soll_mitschreiben(["--kiosk"])
    for arg in (["--help"], ["--diagnose"], ["--diagnose=x.zip"], ["--selbsttest"]):
        assert not soll_mitschreiben(arg), arg


def test_hilfe_menue_hat_diagnosepaket():
    with open(os.path.join(_REPO, "src", "ui", "main_window.py"), encoding="utf-8") as f:
        q = f.read()
    assert '"Diagnosepaket speichern…"' in q
    assert "_diagnosepaket_speichern" in q


def test_menue_aktion_schreibt_paket_headless(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from src.ui.main_window import MainWindow
    ziel = tmp_path / "menue.zip"
    pfad = MainWindow._diagnosepaket_speichern(object(), str(ziel))
    assert pfad == str(ziel) and ziel.is_file()
