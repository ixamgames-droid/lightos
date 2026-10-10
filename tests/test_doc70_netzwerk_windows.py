"""DOC-70: die Anleitung „Netzwerk vorbereiten (Windows)" stimmt mit dem Code.

Eine Netzwerk-Anleitung altert an zwei Stellen: an den **Ports** und an den
**Beschriftungen** der Schalter, die sie nennt. Beides wird hier gegen den
Quelltext gehalten — eine falsche Portnummer in der Firewall-Regel faellt sonst
erst am Veranstaltungsort auf, als Stille.

Geprueft wird ausserdem die Aussage, auf der die Tabelle „Freigabe noetig?"
steht: WAS in der Voreinstellung auf allen Schnittstellen lauscht (Web-Remote)
und was nur lokal (OSC).

MIDI Show Control ueber Netzwerk (UDP 6004) kam mit MIDI-5; solange das Modul
fehlt, prueft der Test nur, dass die Anleitung den Vorbehalt nennt.
"""
import importlib.util
import inspect
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANLEITUNG = os.path.join(REPO, "docs", "anleitung_netzwerk_windows", "ANLEITUNG.md")
MSC_MODUL = os.path.join(REPO, "src", "core", "midi", "msc.py")


def _lies(*teile: str) -> str:
    with open(os.path.join(REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _regel_zeilen(text: str) -> dict[int, str]:
    """{Port: Protokoll} aus den ``New-NetFirewallRule``-Zeilen der Anleitung."""
    regeln = {}
    for zeile in text.splitlines():
        if not zeile.startswith("New-NetFirewallRule"):
            continue
        m = re.search(r"-Protocol (TCP|UDP)\s+-LocalPort (\d+)", zeile)
        assert m, f"Regel ohne Protokoll/Port: {zeile}"
        regeln[int(m.group(2))] = m.group(1)
    return regeln


class Doc70NetzwerkWindowsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = _lies("docs", "anleitung_netzwerk_windows", "ANLEITUNG.md")

    # ── Auffindbar ───────────────────────────────────────────────────────────

    def test_steht_im_anleitungs_index(self):
        index = _lies("docs", "ANLEITUNGEN.md")
        self.assertIn("(anleitung_netzwerk_windows/ANLEITUNG.md)", index)

    # ── Ports gegen den Code ─────────────────────────────────────────────────

    def test_ports_der_firewall_regeln_stimmen_mit_dem_code(self):
        from src.core.audio.os2l import OS2LServer
        from src.core.dmx import artnet_input, sacn_input
        from src.web import app as web_app

        web_port = inspect.signature(web_app.start_server).parameters["port"].default
        os2l_port = inspect.signature(OS2LServer.__init__).parameters["port"].default
        soll = {
            web_port: "TCP",
            artnet_input.ARTNET_PORT: "UDP",
            sacn_input.SACN_PORT: "UDP",
            # Codex-Befund zu #1002: die Tabelle verlangt die Freigabe, wenn die
            # DJ-Software auf einem anderen Rechner laeuft — dann muss sie auch
            # im Regel-Block stehen.
            os2l_port: "TCP",
        }
        regeln = _regel_zeilen(self.text)
        for port, proto in soll.items():
            with self.subTest(port=port):
                self.assertEqual(regeln.get(port), proto,
                                 f"Regel fuer {proto} {port} fehlt oder nennt das "
                                 f"falsche Protokoll: {regeln}")

    def test_msc_port_stimmt_sobald_es_das_modul_gibt(self):
        regeln = _regel_zeilen(self.text)
        if os.path.exists(MSC_MODUL):
            spec = importlib.util.spec_from_file_location("_doc70_msc", MSC_MODUL)
            msc = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(msc)
            self.assertEqual(regeln.get(msc.GMA_PORT), "UDP", regeln)
        else:
            # Der Schalter fehlt in dieser Version — die Anleitung muss das sagen.
            self.assertIn(6004, regeln)
            self.assertRegex(self.text, r"erst in Versionen mit MIDI Show Control")

    def test_sendeports_und_nebenports_stimmen(self):
        from src.core.audio.os2l import OS2LServer
        from src.core.dmx import artnet, sacn
        from src.core.osc.osc_server import OscServer

        self.assertIn(f"sendet an UDP {artnet.ARTNET_PORT}", self.text)
        self.assertIn(f"sendet an UDP {sacn.SACN_PORT}", self.text)
        os2l = inspect.signature(OS2LServer.__init__).parameters["port"].default
        osc = inspect.signature(OscServer.__init__).parameters["port"].default
        self.assertIn(f"lauscht auf TCP {os2l}", self.text)
        self.assertIn(f"lauscht auf UDP {osc}", self.text)

    # ── Die Aussagen hinter „Freigabe noetig?" ───────────────────────────────

    def test_osc_lauscht_in_der_voreinstellung_nur_lokal(self):
        from src.core.osc.osc_server import OscServer
        from src.web import remote_settings

        ip = inspect.signature(OscServer.__init__).parameters["ip"].default
        self.assertEqual(ip, "127.0.0.1")
        self.assertIs(remote_settings.DEFAULTS["osc_network_enabled"], False)

    def test_web_remote_lauscht_in_der_voreinstellung_im_ganzen_netz(self):
        from src.web import remote_settings

        self.assertIs(remote_settings.DEFAULTS["lan_remote_enabled"], True)
        quelle = _lies("src", "web", "app.py")
        self.assertIn('host = "0.0.0.0"', quelle)
        self.assertIn('host = "127.0.0.1"', quelle)
        # ... und die Anleitung nennt beide Bilder, an denen man es erkennt.
        self.assertIn("0.0.0.0:5000", self.text)
        self.assertIn("127.0.0.1:5000", self.text)

    # ── Beschriftungen gegen den Code ────────────────────────────────────────

    def test_genannte_schalter_gibt_es_im_code(self):
        fundorte = {
            "Art-Net Input aktivieren": ("src", "ui", "widgets", "output_config.py"),
            "sACN Input aktivieren": ("src", "ui", "widgets", "output_config.py"),
            "DMX Input": ("src", "ui", "widgets", "output_config.py"),
            "Merge in Universe:": ("src", "ui", "widgets", "output_config.py"),
            "Netzwerkkarte:": ("src", "ui", "widgets", "output_config.py"),
            "Web-Interface (Port 5000)": ("src", "ui", "main_window.py"),
            "OS2L-Server (Port 1234)": ("src", "ui", "main_window.py"),
            "OSC-Server (Port 7770)": ("src", "ui", "main_window.py"),
            "LAN-/Handy-Remote": ("src", "ui", "main_window.py"),
        }
        for beschriftung, pfad in fundorte.items():
            with self.subTest(beschriftung):
                self.assertIn(beschriftung, self.text,
                              "die Anleitung nennt den Schalter nicht mehr")
                self.assertIn(f'"{beschriftung}', _lies(*pfad),
                              f"{'/'.join(pfad)} kennt die Beschriftung nicht mehr")

    def test_msc_schalter_gibt_es_sobald_es_das_modul_gibt(self):
        self.assertIn("**GMA-MSC über Netzwerk**", self.text)
        if os.path.exists(MSC_MODUL):
            self.assertIn('"GMA-MSC über Netzwerk"',
                          _lies("src", "ui", "views", "midi_view.py"))

    # ── Die Regeln sind eng und wieder entfernbar ────────────────────────────

    def test_regeln_sind_auf_privat_und_das_eigene_netz_begrenzt(self):
        m = re.search(r"^\$lightos = @\{(.+)\}$", self.text, re.M)
        self.assertTrue(m, "der gemeinsame Parameter-Block fehlt")
        block = m.group(1)
        for teil in ("Direction = 'Inbound'", "Action = 'Allow'",
                     "Profile = 'Private'", "RemoteAddress = 'LocalSubnet'",
                     "Group = 'LightOS'"):
            with self.subTest(teil):
                self.assertIn(teil, block)
        for zeile in self.text.splitlines():
            if zeile.startswith("New-NetFirewallRule"):
                self.assertIn("@lightos", zeile, zeile)

    def test_aufraeumen_steht_dabei(self):
        self.assertIn("Remove-NetFirewallRule -Group 'LightOS'", self.text)
        self.assertIn("Get-NetFirewallRule -Group 'LightOS'", self.text)
        self.assertIn("-WhatIf", self.text)

    def test_jede_funktion_mit_freigabe_hat_eine_regel(self):
        """Tabelle (Schritt 1) und Regel-Block (Schritt 4) duerfen nicht
        auseinanderlaufen: jede Zeile, die „lauscht auf <Proto> <Port>" sagt
        und eine Freigabe verlangt, hat eine Regel mit demselben Port."""
        regeln = _regel_zeilen(self.text)
        zeilen = [z for z in self.text.splitlines()
                  if z.startswith("|") and "lauscht auf" in z]
        self.assertGreaterEqual(len(zeilen), 5)
        for z in zeilen:
            spalten = [s.strip() for s in z.strip("|").split("|")]
            m = re.search(r"lauscht auf (TCP|UDP) (\d+)", spalten[2])
            self.assertTrue(m, z)
            proto, port = m.group(1), int(m.group(2))
            if spalten[3].startswith("nein"):
                self.assertNotIn(port, regeln, f"Regel ohne Bedarf: {z}")
            else:
                with self.subTest(port=port):
                    self.assertEqual(regeln.get(port), proto, z)

    def test_blockier_regeln_werden_einzeln_und_gezielt_entfernt(self):
        """Codex-Befund zu #1002: das fruehere Rezept haengte
        ``| Remove-NetFirewallRule`` an eine Suche nach 'python|LightOS' im
        Namen — das loeschte JEDE solche Blockier-Regel, auch die anderer
        Python-Programme. Entfernt wird jetzt eine Regel ueber ihre Kennung."""
        self.assertNotRegex(self.text, r"\|\s*Remove-NetFirewallRule")
        self.assertIn("Remove-NetFirewallRule -Name '<Name aus der Liste>'", self.text)
        # Die Liste davor zeigt Kennung UND Programm — sonst waere „die
        # richtige Regel" nicht zu erkennen.
        i = self.text.index("**Blockier-Regeln finden.**")
        j = self.text.index("Remove-NetFirewallRule -Name")
        liste = self.text[i:j]
        self.assertIn("Get-NetFirewallApplicationFilter", liste)
        self.assertIn("Name = $_.Name", liste)
        # Sammel-Loeschen gibt es nur fuer die eigene Gruppe.
        for zeile in self.text.splitlines():
            if "Remove-NetFirewallRule" in zeile and "-Name" not in zeile:
                self.assertIn("-Group 'LightOS'", zeile, zeile)

    # ── Pruefen heisst lesen ─────────────────────────────────────────────────

    def test_der_pruefschritt_nennt_nur_lesende_befehle(self):
        """Regel vom 10.10.: am Rechner wird LESEND geprueft. Schritt 5 darf
        deshalb keinen Befehl enthalten, der Netzwerk oder Firewall aendert."""
        i = self.text.index("## 5. Prüfen, ob es wirkt")
        j = self.text.index("## 6. Typische Fehlerbilder")
        schritt = self.text[i:j]
        for befehl in ("Get-NetConnectionProfile", "Get-NetFirewallRule -Group 'LightOS'",
                       "netsh advfirewall show currentprofile", "ipconfig",
                       "netstat -ano", "Test-NetConnection"):
            with self.subTest(befehl):
                self.assertIn(befehl, schritt)
        for aendernd in ("New-Net", "Set-Net", "Remove-Net", "Enable-Net", "Disable-Net",
                         "netsh advfirewall firewall", "netsh advfirewall set",
                         "netsh interface"):
            with self.subTest(aendernd):
                self.assertNotIn(aendernd, schritt)

    def test_profilwechsel_warnt_vor_den_regeln_anderer_programme(self):
        """Der Wechsel auf „Privat" macht auch fremde Regeln wirksam — die
        Anleitung sagt das und nennt die lesende Abfrage dazu."""
        i = self.text.index("## 2. Netzwerkprofil prüfen")
        j = self.text.index("## 3. Feste Adresse")
        schritt = self.text[i:j]
        self.assertIn("**alle** Firewall-Regeln", schritt)
        self.assertIn("Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow", schritt)
        self.assertIn("-notmatch 'Public'", schritt)
        self.assertNotIn("Set-NetConnectionProfile", self.text,
                         "das Profil stellt der Nutzer in den Einstellungen um, bewusst")

    # ── Oeffentliches Repo ───────────────────────────────────────────────────

    def test_keine_privaten_pfade(self):
        self.assertNotRegex(self.text, r"(?i)C:\\Users\\")
        self.assertNotRegex(self.text, r"192\.168\.178\.")


if __name__ == "__main__":
    unittest.main()
