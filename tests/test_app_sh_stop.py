"""TOOL-APPSTOP: ``tools/app.sh stop`` darf keinen Erfolg melden, solange noch
etwas laeuft.

Zweimal belegt (2026-08-03 und 2026-08-05): ``stop`` gab ``[app] beendet`` aus,
die App lief weiter. Am 05.08. half auch ein zweiter Aufruf nicht mehr — erst
``pkill``. Das ist teuer, und zwar auf Umwegen: eine laufende LightOS-Instanz
haelt ALSA-MIDI-Clients und macht View-bauende Testdateien messbar instabiler
(XPLAT-14: 2/6 Ausfaelle ohne, 8/8 mit). Am 03.08. wurde das Gate deswegen rot,
und es kostete Zeit, die Ursache als Ursache zu erkennen — **weil ``stop`` ja
Erfolg gemeldet hatte**.

★ Getestet wird gegen eine **Mini-Repo-Attrappe**, nicht gegen eine Nachbildung
der Logik: ein Wegwerf-Verzeichnis mit ``tools/app.sh`` (der echten Datei),
einem ``start.sh`` und einem ``venv/bin/python``, das ein ``main.py`` startet.
Damit laeuft der echte Kontrollfluss des Skripts — Nachbauen wuerde genau die
Loecher nachbauen, die gefixt werden sollen.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_SH = ROOT / "tools" / "app.sh"


def _lebt(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    return True


class AppShStopTest(unittest.TestCase):
    """Jeder Test baut sich seine eigene Attrappe und raeumt sie wieder ab."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lightos-appstop-"))
        self.repo = self.tmp / "repo"
        (self.repo / "tools").mkdir(parents=True)
        (self.repo / "venv" / "bin").mkdir(parents=True)
        (self.tmp / "logs").mkdir(exist_ok=True)
        shutil.copy(APP_SH, self.repo / "tools" / "app.sh")
        os.chmod(self.repo / "tools" / "app.sh", 0o755)

        # Das „venv-Python" ist der echte Interpreter — app.sh sucht nach
        # `venv/bin/python.*main\.py` in der Kommandozeile, mehr braucht es nicht.
        os.symlink(sys.executable, self.repo / "venv" / "bin" / "python")

        self.pidfile = self.tmp / "run" / "lightos-app.pid"
        self.pidfile.parent.mkdir(exist_ok=True)
        self.gestartet: list[int] = []

    def tearDown(self):
        for pid in self.gestartet:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── Helfer ───────────────────────────────────────────────────────────────

    def _fake_app(self, ignoriert_sigterm: bool = False,
                  mit_kind: bool = False) -> int:
        """Startet `venv/bin/python main.py` im Attrappen-Repo — losgeloest.

        ★ Der Zwischenschritt ueber eine sofort endende Shell ist kein Zierrat:
        bliebe die Attrappe ein direktes KIND des Testprozesses, wuerde sie nach
        dem Kill zum ZOMBIE, und `kill -0` meldet Zombies als lebend — der Test
        saehe einen Fehlschlag, wo keiner ist. Die echte App haengt aus genau
        demselben Grund an init: `cmd_start` startet sie ueber `nohup ... &` in
        einer Subshell, die sofort endet. (Erst beim Bauen dieses Tests
        aufgefallen — die erste Fassung war deshalb rot.)"""
        quelle = ["import signal, sys, time, subprocess, os"]
        if ignoriert_sigterm:
            quelle.append("signal.signal(signal.SIGTERM, signal.SIG_IGN)")
        if mit_kind:
            quelle.append(
                "subprocess.Popen([sys.executable, '-c',"
                " 'import time; time.sleep(300)'])")
        quelle.append("sys.stdout.write('bereit\\n'); sys.stdout.flush()")
        quelle.append("time.sleep(300)")
        (self.repo / "main.py").write_text("\n".join(quelle), encoding="utf-8")
        e = subprocess.run(
            ["bash", "-c", "venv/bin/python main.py >/dev/null 2>&1 & echo $!"],
            cwd=self.repo, capture_output=True, text=True, timeout=30)
        pid = int(e.stdout.strip())
        self.gestartet.append(pid)
        for _ in range(100):         # warten, bis der Prozess wirklich steht
            if _lebt(pid):
                break
            time.sleep(0.05)
        time.sleep(0.6)              # SIGTERM-Handler/Kind sind dann gesetzt
        return pid

    def _stop(self):
        umg = dict(os.environ, XDG_RUNTIME_DIR=str(self.pidfile.parent))
        return subprocess.run(
            ["bash", str(self.repo / "tools" / "app.sh"), "stop"],
            capture_output=True, text=True, env=umg, timeout=90)

    # ── Die Tests ────────────────────────────────────────────────────────────

    def test_beendet_die_app_auch_ohne_pid_file(self):
        """Der Normalfall: das PID-File ist weg (die start.sh dahinter endet
        sofort), gefunden wird ueber den Prozess-Scan."""
        app = self._fake_app()
        e = self._stop()
        self.assertEqual(e.returncode, 0, f"stop scheiterte: {e.stdout}{e.stderr}")
        self.assertIn("beendet", e.stdout)
        self.assertFalse(_lebt(app),
                         "stop meldete Erfolg, der Prozess lebt aber noch")

    def test_meldet_KEINEN_erfolg_wenn_noch_etwas_laeuft(self):
        """★ Der Kern des Fundes.

        Das PID-File zeigt auf einen Wegwerf-Prozess (so wie es auf die
        laengst beendete `start.sh` zeigt), waehrend die ECHTE App daneben
        laeuft. Die alte Fassung toetete die eine PID aus dem File, druckte
        „[app] beendet" und liess die App stehen — genau das am 03.08. und
        05.08. beobachtete Verhalten.
        """
        app = self._fake_app()
        e_k = subprocess.run(['bash', '-c', 'sleep 300 >/dev/null 2>&1 & echo $!'],
                             capture_output=True, text=True, timeout=30)
        koeder = int(e_k.stdout.strip())
        self.gestartet.append(koeder)
        self.pidfile.write_text(str(koeder), encoding='utf-8')

        e = self._stop()
        self.assertFalse(
            _lebt(app),
            f"die App lebt nach stop weiter (Ausgabe: {e.stdout!r}{e.stderr!r}) — "
            f"genau der Fall, in dem frueher trotzdem „beendet\" gemeldet wurde")
        # Und wenn doch etwas ueberlebt, muss es LAUT scheitern:
        if _lebt(app):
            self.assertNotEqual(e.returncode, 0)
            self.assertNotIn("beendet", e.stdout)

    def test_nimmt_die_kindprozesse_mit(self):
        """QtWebEngine haengt Hilfsprozesse unter die App. Bleiben die stehen,
        haelt die Instanz weiter ihre ALSA-Clients."""
        app = self._fake_app(mit_kind=True)
        time.sleep(0.5)
        kinder = subprocess.run(["pgrep", "-P", str(app)],
                                capture_output=True, text=True)
        kind_pids = [int(z) for z in kinder.stdout.split() if z.strip()]
        self.assertTrue(kind_pids, "Attrappe hat kein Kind erzeugt")

        e = self._stop()
        self.assertEqual(e.returncode, 0, f"{e.stdout}{e.stderr}")
        uebrig = [p for p in kind_pids if _lebt(p)]
        self.assertEqual(
            uebrig, [],
            f"Kindprozesse ueberlebten den stop: {uebrig} — die Instanz haelt "
            f"damit weiter ihre Ressourcen")

    def test_sigterm_verweigerer_wird_hart_beendet_und_das_wird_gesagt(self):
        """Reagiert die App nicht auf SIGTERM, muss SIGKILL folgen — und das
        Skript darf erst DANACH Erfolg melden."""
        app = self._fake_app(ignoriert_sigterm=True)
        e = self._stop()
        self.assertFalse(_lebt(app), "SIGTERM-Verweigerer ueberlebte")
        self.assertIn("SIGKILL", e.stdout,
                      "der harte Abbruch muss sichtbar sein, nicht stillschweigend")
        self.assertIn("beendet", e.stdout)
        self.assertEqual(e.returncode, 0)

    def test_ohne_laufende_app_ist_stop_ein_no_op(self):
        e = self._stop()
        self.assertEqual(e.returncode, 0)
        self.assertIn("laeuft nicht", e.stdout)


if __name__ == "__main__":
    unittest.main()
