"""DOC-69 — Sammel-Korrektur eindeutig falscher/veralteter Doku-Stellen.

Jeder Test hier haelt EINE Stelle fest, die nachweislich nicht (mehr) zum
Programm passte. Die Tests pruefen bewusst nur kurze, eindeutige Textmarken —
kein allgemeines "Doku gegen Code"-Gate (das hat in DOC-10 fast nur
Falschmeldungen geliefert, s. ``test_doc_removed_ui.py``).

Wo es billig geht, wird die Marke gegen den Quelltext gegengeprueft (z. B. die
Beschriftung "Tempo ×"), damit der Test nicht eine Doku festschreibt, die der
Code laengst wieder ueberholt hat.
"""
from __future__ import annotations

import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(*teile: str) -> str:
    with open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _flach(text: str) -> str:
    """Zeilenumbrueche/Mehrfach-Leerzeichen einebnen — Fliesstext bricht um."""
    return re.sub(r"\s+", " ", text)


class TestTempoSync(unittest.TestCase):
    DOC = ("docs", "ANLEITUNG_TEMPO_SYNC.md")

    def test_ui_begriffe_stehen_im_code(self):
        for datei in ("efx_view.py", "rgb_matrix_view.py"):
            src = _lies("src", "ui", "views", datei)
            self.assertIn('"Tempo ×:"', src, datei)
            self.assertIn('"Tempo-Versatz:"', src, datei)

    def test_anleitung_nennt_die_ui_begriffe(self):
        text = _lies(*self.DOC)
        self.assertIn("Tempo ×", text)
        self.assertIn("Tempo-Versatz", text)

    def test_keine_alten_feldnamen_als_bedienelement(self):
        # "Multiplikator"/"Phase" duerfen als ERKLAERUNG vorkommen, aber nicht
        # mehr fett als Name eines Feldes, das es so nicht gibt.
        text = _lies(*self.DOC)
        self.assertNotIn("**Multiplikator**", text)
        self.assertNotIn("**Phase**", text)
        self.assertNotIn("Multiplikator / Phase", _flach(text))
        self.assertNotIn("Multiplikator =", text)

    def test_freeze_absatz_ist_ganz(self):
        text = _flach(_lies(*self.DOC))
        self.assertNotIn("enthalten: friert alle Buses", text)
        self.assertNotIn("BUG-FBW", text)


class TestMusikSync(unittest.TestCase):
    DOC = ("docs", "anleitung_musik_sync", "ANLEITUNG_MUSIK_SYNC.md")

    def test_keine_entfernte_bpm_bedienung(self):
        text = _flach(_lies(*self.DOC))
        self.assertNotIn("±10", text)
        self.assertNotIn("**MANUAL**", text)
        self.assertNotIn("BPM-Quelle", text)
        self.assertNotIn("unter **Einstellungen**", text)

    def test_verweist_auf_bpm_manager_anleitung(self):
        self.assertIn("anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md",
                      _lies(*self.DOC))


class TestApcTestShow(unittest.TestCase):
    DOC = ("docs", "APC_TEST_SHOW.md")

    def test_seitenzahl_einheitlich(self):
        text = _lies(*self.DOC)
        self.assertNotIn("5 umschaltbare Seiten", text)
        self.assertIn("6 umschaltbare Seiten", text)
        # Review: der Generator-Absatz nannte weiter "5 VC-Seiten" (mit
        # geschuetztem Bindestrich) — jede Seitenzahl im Text muss 6 sein.
        zahlen = re.findall(r"(\d+)\s+(?:umschaltbare\s+|VC[\u2011-])?Seiten\b", text)
        self.assertTrue(zahlen)
        self.assertEqual(set(zahlen), {"6"}, zahlen)

    def test_menuenamen_wie_im_programm(self):
        text = _lies(*self.DOC)
        mw = _lies("src", "ui", "main_window.py")
        self.assertIn('"Öffnen..."', mw)
        self.assertIn('"Konfigurieren..."', mw)
        self.assertNotIn("Show öffnen", text)
        self.assertNotIn("Ausgabe → Konfiguration**", text)
        self.assertIn("Datei → Öffnen", text)
        self.assertIn("Ausgabe → Konfigurieren", text)

    def test_hardware_ist_mk2(self):
        kopf = "\n".join(_lies(*self.DOC).splitlines()[:14])
        self.assertNotIn("(Original)", kopf)
        self.assertIn("mk2", kopf)


class TestEnttecStatus(unittest.TestCase):
    def test_statusmeldung_wie_im_programm(self):
        text = _lies("docs", "anleitung_enttec_artnet",
                     "ANLEITUNG_ENTTEC_ARTNET.md")
        self.assertNotIn("COM3 OK", text)
        self.assertNotIn("… OK", text)
        self.assertIn("aktiv (", text)
        self.assertIn("aktiv ({anzahl})", _lies("src", "ui", "main_window.py"))


class TestContributing(unittest.TestCase):
    def setUp(self):
        self.text = _lies("CONTRIBUTING.md")

    def test_kein_dev_zweig(self):
        for zeile in self.text.splitlines():
            ohne = zeile.replace("requirements-dev.txt", "").replace("--dev", "")
            self.assertIsNone(
                re.search(r"(?<![\w-])dev(?![\w-])", ohne),
                f"CONTRIBUTING.md nennt einen dev-Zweig, den es nicht gibt: {zeile!r}")

    def test_keine_erfundene_teststruktur(self):
        self.assertNotIn("93 Tests", self.text)
        self.assertNotIn("test_views.py", self.text)

    def test_commit_form_mit_bereich_und_id(self):
        self.assertIn("<typ>(<bereich>):", self.text)
        self.assertNotIn("feat: add MIDI learn to VC fader", self.text)

    def test_ci_verspricht_kein_ruff(self):
        self.assertNotIn("pytest + ruff", self.text)
        self.assertNotIn("ruff", _lies(".github", "workflows", "ci.yml"))


class TestGateAngaben(unittest.TestCase):
    def test_requirements_dev_nennt_kein_sammel_pytest(self):
        self.assertNotIn("pytest tests/", _lies("requirements-dev.txt"))

    def test_workflow_tests_vor_commit_nennt_das_gate(self):
        text = _lies("WORKFLOW.md")
        m = re.search(r"## Tests vor jedem Commit\n(.*?)\n## ", text, re.S)
        self.assertIsNotNone(m)
        abschnitt = m.group(1)
        self.assertIn("verify_loop.sh", abschnitt)
        self.assertIn("verify_segmented.ps1", abschnitt)


class TestStandAngaben(unittest.TestCase):
    def test_install_ci_nicht_nur_windows(self):
        text = _flach(_lies("INSTALL.md"))
        self.assertNotIn("bisher nur `windows-latest`", text)
        self.assertIn("ubuntu-latest", _lies(".github", "workflows", "ci.yml"))

    def test_architecture_ohne_feste_testzahl(self):
        text = _lies("ARCHITECTURE.md")
        self.assertNotIn("517", text)
        self.assertNotIn("8 Sektionen", text)

    def test_roadmap_als_historischer_stand_markiert(self):
        kopf = "\n".join(_lies("ROADMAP.md").splitlines()[:8])
        self.assertIn("istorischer Stand", kopf)
        self.assertIn("BACKLOG.md", kopf)


class TestDatenorte(unittest.TestCase):
    def test_install_md_shows_im_app_datenordner(self):
        text = _lies("INSTALL.md")
        self.assertNotIn("(deine .lshow Dateien)", text)
        m = re.search(r"\nApp-Datenordner.*?```", text, re.S)
        self.assertIsNotNone(m)
        self.assertIn("shows/", m.group(0))
        # Gegenprobe: dort legt das Programm sie wirklich ab.
        self.assertIn('os.path.join(app_data_dir(), "shows")',
                      _lies("src", "ui", "main_window.py"))

    def test_install_py_data_ist_nicht_die_show_db(self):
        self.assertNotIn("(lokale Show-DB, MIDI-Mappings, Modifier)",
                         _lies("install.py"))


class TestNichtVorhandenes(unittest.TestCase):
    def test_dmx_protocol(self):
        text = _flach(_lies("docs", "DMX_PROTOCOL.md"))
        self.assertNotIn("Fallback-Implementierung unterstützt", text)
        self.assertNotIn("| Enttec Pro Mk2 | Dual-Universe Version |", text)
        self.assertIn("unterstützt Open DMX USB", text)
        self.assertNotIn("open_dmx", " ".join(os.listdir(
            os.path.join(_REPO, "src", "core", "dmx"))))
        self.assertNotIn("| 0x03 | DMX Output senden", text)
        self.assertIn("LABEL_DMX_OUTPUT = 6",
                      _lies("src", "core", "dmx", "enttec_pro.py"))

    def test_features(self):
        text = _lies("docs", "FEATURES.md")
        self.assertNotIn("| Enttec Open DMX USB | DMX512 (Serial) | USB |", text)
        self.assertNotIn("konfigurierbar 1–44 Hz", text)
        self.assertNotIn("Sprache (DE/EN)", text)
        self.assertNotIn("Dark / Light / Custom", text)


class TestInstallAktualisieren(unittest.TestCase):
    def test_abschnitt_vorhanden(self):
        text = _lies("INSTALL.md")
        m = re.search(r"\n## LightOS aktualisieren\n(.*?)\n## ", text, re.S)
        self.assertIsNotNone(m, "INSTALL.md braucht den Abschnitt "
                                "'## LightOS aktualisieren'")
        abschnitt = m.group(1)
        self.assertIn("git pull", abschnitt)
        self.assertIn("install.py", abschnitt)
        self.assertIn("LightOS-Setup.exe", abschnitt)
        self.assertIn("App-Datenordner", abschnitt)


class TestBugReportVorlage(unittest.TestCase):
    def test_fragt_installationsart_und_diagnosepaket(self):
        text = _lies(".github", "ISSUE_TEMPLATE", "bug_report.md")
        self.assertIn("Setup oder Quellcode", text)
        self.assertIn("Diagnosepaket speichern…", text)
        self.assertIn('"Diagnosepaket speichern…"',
                      _lies("src", "ui", "main_window.py"))


class TestZweiUniversen(unittest.TestCase):
    def test_veraltete_datenverlust_warnung_ist_weg(self):
        text = _flach(_lies("docs", "anleitung_zwei_universen", "ANLEITUNG.md"))
        self.assertNotIn("erst schließen und neu öffnen", text)
        self.assertNotIn("wieder weg", text)
        # Gegenprobe: der Dialog laedt die Tabelle nach beiden Wegen nach.
        src = _lies("src", "ui", "widgets", "output_config.py")
        self.assertGreaterEqual(src.count("self._univ_tabelle_nachladen()"), 2)


class TestBpmGenerator(unittest.TestCase):
    DOC = ("docs", "anleitung_bpm_generator", "ANLEITUNG_BPM_GENERATOR.md")

    def test_bild_wiederverwendet(self):
        text = _lies(*self.DOC)
        self.assertIn("](../anleitung_bpm_manager/img/generator.png)", text)
        self.assertTrue(os.path.isfile(os.path.join(
            _REPO, "docs", "anleitung_bpm_manager", "img", "generator.png")))

    def test_keine_interne_ticket_id(self):
        self.assertNotIn("BPM-17", _lies(*self.DOC))


class TestLaserGoboTest(unittest.TestCase):
    DOC = ("docs", "ANLEITUNG_LASER_GOBO_TEST_2026.md")

    def test_warnbox_am_anfang(self):
        zeilen = _lies(*self.DOC).splitlines()
        kopf = _flach("\n".join(zeilen[:30]))
        erste_ueberschrift = next(
            i for i, z in enumerate(zeilen) if z.startswith("## "))
        warn = next(i for i, z in enumerate(zeilen) if "Laser-Sicherheit" in z)
        self.assertLess(warn, erste_ueberschrift,
                        "Die Warnbox muss VOR dem ersten Abschnitt stehen")
        self.assertTrue(zeilen[warn].startswith(">"))
        for marke in ("Laserklasse", "Publikum", "NOT-AUS", "Strahl"):
            self.assertIn(marke, kopf)
        self.assertRegex(kopf, r"Anmelde|Abnahme")

    def test_tabelle_was_macht_den_laser_aus(self):
        text = _lies(*self.DOC)
        self.assertIn("Was macht den Laser sicher aus?", text)
        for zeile in ("| **Blackout**", "| **Grand Master 0", "| **Ziel-Blackout",
                      "| **Laser-NOT-AUS"):
            self.assertIn(zeile, text)
        self.assertIn(
            "anleitung_laser/ANLEITUNG_LASER.md#blackout-ziel-blackout-und-not-aus",
            text)
        self.assertIn('"Laser NOT-AUS"',
                      _lies("src", "ui", "virtualconsole", "vc_button.py"))


if __name__ == "__main__":
    unittest.main()
