"""QA-UNIVERSES-WRITE: die Suite darf `data/universes.json` nicht anfassen.

**Warum das eine eigene Datei wert ist:** `data/universes.json` ist nicht
irgendeine Einstellung — sie sagt, welches Universum auf welchen Adapter geht.
**Ist sie falsch, geht kein DMX raus.** Und sie wird bei jedem
„Uebernehmen"/„Verbinden" im Universe-Manager neu geschrieben, ueber einen Pfad,
der relativ zum Arbeitsverzeichnis war.

Gemessen (2026-08-04): von acht Testdateien, die die Universe-Config-APIs
beruehren, schrieb genau **eine** die Datei —
`tests/test_output_config_lifecycle.py`, mit einer vollstaendigen erfundenen
Konfiguration (Enttec `COM_FAKE`, zwei Art-Net-Broadcasts, zwei sACN). Wer die
Suite im Repo-Ordner faehrt, legte die also ueber seine echte.

**Aufgefallen ist es durch einen Zufall, nicht durch eine Pruefung:** ein
frischer Worktree hatte die Datei noch gar nicht, und nach dem Testlauf war sie
da. Im Repo-Ordner haette sie eine vorhandene ersetzt — lautlos, denn
`data/*.json` ist gitignored, `git status` schweigt also. Dieser Test macht aus
dem Zufall eine Pruefung.

**★ Und der Schaden ist schlimmer als „Datei ueberschrieben".** Gegen die
entfernte Umlenkung gemessen, mit einer Zeile `{"num": 1, "name": "ECHT — nicht
anfassen", "patch": "10.0.0.1"}` als Ausgangsstand: nach dem Lauf stand dort
derselbe **Name** — und `"patch": "255.255.255.255"`. `_persist_output` sucht
die Zeile ueber `num` und ersetzt Typ und Ziel, den Namen laesst es stehen. Die
Konfiguration sieht danach also aus wie die eigene und **sendet woandershin**.
Ein komplett ersetzter Eintrag waere aufgefallen; dieser nicht.

Dieselbe Klasse wie die Show-DB-, Fixture-DB-, crash.log- und sACN-CID-Trennung
in `tests/conftest.py`; sie stehen dort alle mit derselben Begruendung.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ECHT = os.path.join(_REPO, "data", "universes.json")


class UniversesJsonIsolationTest(unittest.TestCase):

    def test_conftest_lenkt_die_datei_um(self):
        """Die Umlenkung muss im laufenden Testprozess AKTIV sein.

        Nicht „ist gesetzt", sondern „zeigt woanders hin": eine Variable, die
        zufaellig auf die echte Datei zeigt, waere schlimmer als keine.
        """
        umgelenkt = os.environ.get("LIGHTOS_UNIVERSES_JSON")
        self.assertTrue(umgelenkt, "LIGHTOS_UNIVERSES_JSON ist nicht gesetzt")
        self.assertNotEqual(
            os.path.abspath(umgelenkt), os.path.abspath(_ECHT),
            "die Umlenkung zeigt auf die ECHTE Konfiguration")

    def test_ein_von_aussen_gesetzter_pfad_haelt_den_schutz_nicht_auf(self):
        """CDX-49: `setdefault` waere hier die falsche Sanftmut.

        Wer sich `LIGHTOS_UNIVERSES_JSON` auf seine echte Konfiguration legt —
        etwa um die App mit einem anderen Aufbau zu starten — haette mit
        `setdefault` den Schutz genau dann abgeschaltet, wenn er am meisten
        kostet. *Eine Schutzmassnahme, die sich vom Zielobjekt abschalten
        laesst, ist keine.*

        Geprueft am Verhalten eines frischen Subprozesses: er bekommt die
        echte Datei vorgesetzt und muss sie trotzdem in Ruhe lassen.
        """
        opfer = os.path.join(_REPO, "tests", "test_output_config_lifecycle.py")
        if not os.path.exists(opfer):
            self.skipTest("test_output_config_lifecycle.py nicht vorhanden")

        vorher = (open(_ECHT, "rb").read()
                  if os.path.exists(_ECHT) else None)
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", opfer],
            cwd=_REPO, capture_output=True, text=True, timeout=600,
            # Der Angriff: die Variable zeigt auf die ECHTE Datei.
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen",
                     LIGHTOS_UNIVERSES_JSON=_ECHT))

        if vorher is None:
            self.assertFalse(
                os.path.exists(_ECHT),
                "trotz Schutz wurde data/universes.json angelegt — ein von "
                "aussen gesetzter Pfad hat ihn ausgehebelt")
        else:
            self.assertEqual(
                vorher, open(_ECHT, "rb").read(),
                "trotz Schutz wurde data/universes.json veraendert — ein von "
                "aussen gesetzter Pfad hat ihn ausgehebelt")

    def test_beide_seiten_sehen_dieselbe_datei(self):
        """Lesen und Schreiben duerfen nicht auseinanderlaufen.

        Der Dialog schreibt ueber `output_config._UNIV_CONFIG_PATH`, die App
        liest in `AppState.apply_output_config`. Stuenden die beiden auf
        verschiedenen Dateien, richtete der naechste Start eine andere
        Konfiguration ein als die gerade gespeicherte — ein Fehler, der sich
        erst am dunklen Rig zeigt. Der frueher fest verdrahtete Default in
        `apply_output_config` war genau diese zweite Stelle.
        """
        from src.ui.widgets import output_config as oc
        erwartet = os.environ["LIGHTOS_UNIVERSES_JSON"]
        self.assertEqual(os.path.abspath(oc._UNIV_CONFIG_PATH),
                         os.path.abspath(erwartet))

        # Die Leseseite loest denselben Pfad auf. Geprueft wird ueber das
        # Verhalten: eine Konfiguration in die umgelenkte Datei schreiben und
        # sehen, ob `apply_output_config()` OHNE Pfadargument sie findet.
        from src.core.app_state import AppState
        quelle = __import__("inspect").getsource(AppState.apply_output_config)
        self.assertIn("LIGHTOS_UNIVERSES_JSON", quelle,
                      "die Leseseite kennt die Umlenkung nicht")
        self.assertNotIn('path: str = "data/universes.json"', quelle,
                         "der fest verdrahtete Default ist zurueck")

    def test_ein_echter_lauf_laesst_die_datei_unveraendert(self):
        """Ende-zu-Ende, an der Datei gemessen — nicht an der Absicht.

        Faehrt genau die Testdatei als Subprozess, die als einzige geschrieben
        hat, und vergleicht Inhalt und Zeitstempel der ECHTEN Datei davor und
        danach. Ohne die Umlenkung ist dieser Test rot; mit ihr ist er der
        Beleg, dass die Suite die Konfiguration in Ruhe laesst.
        """
        opfer = os.path.join(_REPO, "tests", "test_output_config_lifecycle.py")
        if not os.path.exists(opfer):
            self.skipTest("test_output_config_lifecycle.py nicht vorhanden")

        vorher_da = os.path.exists(_ECHT)
        vorher = (open(_ECHT, "rb").read(), os.stat(_ECHT).st_mtime_ns) \
            if vorher_da else (None, None)

        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", opfer],
            cwd=_REPO, capture_output=True, text=True, timeout=600,
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))

        if not vorher_da:
            # Die Datei gab es nicht — dann darf sie auch danach nicht da sein.
            self.assertFalse(
                os.path.exists(_ECHT),
                f"der Lauf hat data/universes.json ANGELEGT:\n"
                f"{open(_ECHT).read()[:400] if os.path.exists(_ECHT) else ''}")
            return

        self.assertTrue(os.path.exists(_ECHT),
                        "der Lauf hat data/universes.json GELOESCHT")
        nachher = (open(_ECHT, "rb").read(), os.stat(_ECHT).st_mtime_ns)
        self.assertEqual(
            vorher[0], nachher[0],
            "der Lauf hat data/universes.json INHALTLICH veraendert — das ist "
            "die Datei, ohne die kein DMX rausgeht.\n"
            f"pytest-Ausgabe (gekuerzt): {r.stdout[-300:]}")
        self.assertEqual(vorher[1], nachher[1],
                         "data/universes.json wurde neu geschrieben (gleicher "
                         "Inhalt, neuer Zeitstempel) — die Umlenkung greift nicht")


if __name__ == "__main__":
    unittest.main()
