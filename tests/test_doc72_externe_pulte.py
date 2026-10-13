"""DOC-72: die Anleitung „Externe Pulte über Netzwerk und MIDI" stimmt mit dem Code.

Eine Anleitung fuer den Betrieb neben einem fremden Lichtpult altert an drei
Stellen: an den **Ports**, an den **Beschriftungen** der Bedienelemente und an
den **Vorgaben** (was ab Werk aus ist). Alle drei werden hier aus dem Quelltext
GELESEN und gegen den Text gehalten — niemand soll am Veranstaltungsort einen
Port freigeben, den es so nicht mehr gibt.

Dazu zwei Zusagen an den Projektinhaber:

* Titel, Dateiname, Ueberschriften und die Verweise in README und
  Anleitungsverzeichnis bleiben **herstellerneutral**. Herstellernamen stehen im
  Fliesstext hoechstens einmal, in EINEM Beispielsatz mit Markenhinweis.
  (Beschriftungen der Oberflaeche in Code-Schreibweise zaehlen nicht dazu — die
  Anleitung muss einen Listeneintrag so nennen koennen, wie er im Programm
  heisst.)
* Der Abschnitt „Was nicht geht" und der ehrliche „Stand der Erprobung" bleiben
  drin.
"""
import inspect
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = ("docs", "anleitung_externe_pulte", "ANLEITUNG_EXTERNE_PULTE.md")
LINK = "anleitung_externe_pulte/ANLEITUNG_EXTERNE_PULTE.md"
TITEL = "Externe Pulte über Netzwerk und MIDI"

# Schreibweisen, unter denen die grossen Pulte und ihre Hersteller auftauchen.
# Das Kuerzel "GMA" gehoert bewusst NICHT dazu: der Schalter heisst im Programm
# „GMA-MSC über Netzwerk", und die Anleitung muss ihn beim Namen nennen.
HERSTELLER = re.compile(
    r"grandMA\d?|MA\s?Lighting|ChamSys|MagicQ|\bHog\b|High End|"
    r"\bETC\b|\bEos\b|Avolites|\bTitan\b", re.I)


def _lies(*teile: str) -> str:
    with open(os.path.join(REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _ohne_code(text: str) -> str:
    """Text ohne Code-Bloecke und ohne `Code-Spannen` (= Fliesstext)."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", " ", text)


def _abschnitt(text: str, kopf: str) -> str:
    """Inhalt eines ``## ``-Abschnitts bis zur naechsten ``## ``-Ueberschrift."""
    i = text.index(kopf)
    j = text.find("\n## ", i + len(kopf))
    return text[i:j if j > 0 else len(text)]


class Doc72ExternePulteTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = _lies(*REL)
        cls.fliess = _ohne_code(cls.text)

    # ── Auffindbar ───────────────────────────────────────────────────────────

    def test_datei_existiert_mit_neutralem_titel(self):
        self.assertTrue(os.path.isfile(os.path.join(REPO, *REL)))
        self.assertEqual(self.text.splitlines()[0], f"# {TITEL}")

    def test_steht_im_anleitungsverzeichnis(self):
        index = _lies("docs", "ANLEITUNGEN.md")
        self.assertIn(f"[{TITEL}]({LINK})", index)

    def test_readme_verweist_im_abschnitt_ausgabe_und_eingaben(self):
        readme = _lies("README.md")
        i = readme.index("<summary><b>Ausgabe und Eingaben</b></summary>")
        j = readme.index("</details>", i)
        self.assertIn(f"[{TITEL}](docs/{LINK})", readme[i:j])

    # ── Herstellerneutral ────────────────────────────────────────────────────

    def test_dateiname_und_ueberschriften_ohne_herstellernamen(self):
        self.assertIsNone(HERSTELLER.search("/".join(REL)))
        for zeile in self.text.splitlines():
            if zeile.startswith("#"):
                with self.subTest(zeile):
                    self.assertIsNone(HERSTELLER.search(zeile))

    def test_verweise_ohne_herstellernamen(self):
        """Die Zeile im Anleitungsverzeichnis und der README-Halbsatz."""
        for datei in (("docs", "ANLEITUNGEN.md"), ("README.md",)):
            zeilen = _lies(*datei).splitlines()
            treffer = [k for k, z in enumerate(zeilen) if LINK in z]
            self.assertTrue(treffer, datei)
            for k in treffer:
                # README: der Halbsatz laeuft ueber die Zeilen davor.
                umfeld = " ".join(zeilen[max(0, k - 2):k + 1])
                with self.subTest(datei=datei[-1]):
                    self.assertIsNone(HERSTELLER.search(umfeld), umfeld)

    def test_herstellernamen_nur_einmal_als_beispiel_mit_markenhinweis(self):
        saetze = re.split(r"(?<=[.!?])\s+", " ".join(self.fliess.split()))
        mit_namen = [s for s in saetze if HERSTELLER.search(s)]
        self.assertEqual(len(mit_namen), 1,
                         f"Herstellernamen in mehr als einem Satz: {mit_namen}")
        satz = mit_namen[0]
        self.assertIn("zum Beispiel", satz)
        self.assertIn("Marken ihrer Hersteller", satz)
        self.assertRegex(satz, r"mit keinem davon verbunden")
        self.assertRegex(satz, r"von keinem\s+geprüft")
        # ... und jeder Name darin genau einmal.
        namen = [m.group(0).lower() for m in HERSTELLER.finditer(satz)]
        self.assertEqual(len(namen), len(set(namen)), namen)

    def test_code_spannen_nennen_hersteller_nur_als_echte_beschriftung(self):
        """Ausnahme vom Neutralitaets-Gebot ist allein ein Listeneintrag, der
        im Programm woertlich so heisst."""
        quelle = _lies("src", "ui", "views", "midi_view.py")
        for spanne in re.findall(r"`([^`\n]*)`", self.text):
            if HERSTELLER.search(spanne):
                with self.subTest(spanne):
                    self.assertIn(f'"{spanne}"', quelle)

    # ── Pflichtabschnitte ────────────────────────────────────────────────────

    def test_abschnitte_in_der_vereinbarten_reihenfolge(self):
        koepfe = ["## 1. Wofür das gut ist", "## 2. Was nicht geht",
                  "## 3. Vorbereitung: das Netzwerk", "## 4. Schritt für Schritt",
                  "## 5. Prüfen, ob es ankommt", "## 6. Sicherheit",
                  "## 7. Fehlersuche", "## 8. Stand der Erprobung"]
        stellen = [self.text.find(k) for k in koepfe]
        self.assertNotIn(-1, stellen, dict(zip(koepfe, stellen)))
        self.assertEqual(stellen, sorted(stellen))
        for aufbau in ("### Aufbau A", "### Aufbau B", "### Aufbau C"):
            self.assertGreaterEqual(self.text.count(aufbau), 2, aufbau)

    def test_was_nicht_geht_nennt_die_vier_grenzen(self):
        teil = _abschnitt(self.text, "## 2. Was nicht geht")
        for grenze in ("Kein Anschluss über das USB-Kabel des Pults",
                       "kein MIDI-Controller für LightOS",
                       "LightOS steuert kein fremdes Pult fern",
                       "Herstellereigene Sitzungsprotokolle werden nicht gesprochen"):
            with self.subTest(grenze):
                self.assertIn(grenze, teil)

    def test_stand_der_erprobung_ist_ehrlich(self):
        teil = _abschnitt(self.text, "## 8. Stand der Erprobung")
        self.assertIn("durch Tests abgedeckt", teil)
        self.assertIn("Noch nicht erprobt", teil)
        self.assertIn("echten großen Lichtpult", teil)
        self.assertIn("Rückmeldungen sind willkommen", teil)

    # ── Ports gegen den Code ─────────────────────────────────────────────────

    def test_ports_stimmen_mit_dem_code(self):
        from src.core.dmx import artnet, artnet_input, sacn, sacn_input
        from src.core.midi import msc
        from src.core.osc.osc_server import OscServer

        self.assertEqual(artnet.ARTNET_PORT, artnet_input.ARTNET_PORT)
        self.assertEqual(sacn.SACN_PORT, sacn_input.SACN_PORT)
        osc = inspect.signature(OscServer.__init__).parameters["port"].default
        netz = _abschnitt(self.text, "## 3. Vorbereitung: das Netzwerk")
        for zeile in (f"| Art-Net-Eingang | UDP {artnet_input.ARTNET_PORT} |",
                      f"| sACN-Eingang | UDP {sacn_input.SACN_PORT} |",
                      f"| MSC über Netzwerk | UDP {msc.GMA_PORT} "):
            with self.subTest(zeile):
                self.assertIn(zeile, netz)
        self.assertIn(f"| **Port:** | UDP-Port für MSC über Netzwerk. | {msc.GMA_PORT} |",
                      self.text)
        self.assertIn(f"UDP {osc}", self.text)
        # Kein anderer Port steht als „UDP <n>" im Text.
        genannt = {int(n) for n in re.findall(r"UDP (\d+)", self.text)}
        self.assertEqual(genannt, {artnet_input.ARTNET_PORT, sacn_input.SACN_PORT,
                                   msc.GMA_PORT, osc})

    def test_netzwerk_abschnitt_ohne_systembefehle(self):
        """Die Anleitung sagt, WAS freigegeben sein muss — keine Befehle."""
        for wort in ("sudo", "ufw ", "iptables", "nft ", "netsh", "New-NetFirewallRule"):
            with self.subTest(wort):
                self.assertNotIn(wort, self.text)

    # ── Vorgaben gegen den Code ──────────────────────────────────────────────

    def test_msc_vorgaben_stimmen(self):
        from src.core.midi import msc

        st = msc.MscSettings()
        self.assertIs(st.udp_enabled, False)
        self.assertIn("| **GMA-MSC über Netzwerk** | MSC zusätzlich per UDP empfangen. "
                      "| **aus** |", self.text)
        self.assertIs(st.enabled, True)
        self.assertRegex(self.text, r"\| \*\*MSC an\*\* \|[^\n]*\| an \|")
        self.assertEqual(st.device_id, 127)
        self.assertRegex(self.text, r"\| \*\*Device-ID:\*\* \|[^\n]*\| 127 \|")
        self.assertEqual(st.udp_host, "127.0.0.1")
        self.assertRegex(self.text,
                         r"\| \*\*Schnittstelle:\*\* \|[^\n]*\| nur dieser Rechner \|")
        self.assertIs(st.all_formats, False)
        self.assertRegex(self.text,
                         r"\| \*\*alle Formate annehmen\*\* \|[^\n]*\| aus \|")
        # „der erste Eintrag" der SET-Belegung ist die Vorgabe.
        self.assertEqual(st.set_layout, msc.SET_LAYOUTS[0])

    def test_jeder_msc_befehl_hat_eine_zeile(self):
        from src.core.midi import msc

        i = self.text.index("**Was die Befehle in LightOS tun:**")
        j = self.text.index("**Welcher Executor gemeint ist**")
        tabelle = self.text[i:j]
        erste_spalte = " ".join(z.split("|")[1] for z in tabelle.splitlines()
                                if z.startswith("|"))
        for name in msc.COMMAND_NAMES.values():
            with self.subTest(name):
                self.assertRegex(erste_spalte, rf"\b{name.upper()}\b")

    def test_msc_befehle_ohne_wirkung_sind_so_benannt(self):
        """LOAD, RESTORE und RESET loesen im Mapper nichts aus — die Anleitung
        verspricht dort nichts."""
        quelle = _lies("src", "core", "midi", "midi_mapper.py")
        i = quelle.index("def handle_msc")
        j = quelle.index("def _handle_inbound_mapping")
        rumpf = quelle[i:j]
        self.assertIn("return False      # Vorladen kennt LightOS nicht", rumpf)
        self.assertNotIn("_msc.RESTORE", rumpf)
        self.assertNotIn("_msc.RESET", rumpf)
        self.assertIn("| LOAD, RESTORE, RESET | Werden erkannt, lösen aber nichts aus. |",
                      self.text)

    def test_netzwerk_msc_kennung_stimmt(self):
        quelle = _lies("src", "core", "midi", "msc.py")
        self.assertIn(r'b"GMA\x00"', quelle)
        self.assertIn(r'b"MSC\x00"', quelle)
        self.assertRegex(self.text, r"Kennung `GMA`\s+und `MSC`")

    def test_merge_modi_und_timeout_stimmen(self):
        dialog = _lies("src", "ui", "widgets", "output_config.py")
        self.assertEqual(dialog.count('addItems(["HTP", "LTP", "REPLACE"])'), 2)
        for modus in ("HTP", "LTP", "REPLACE"):
            self.assertIn(f"| `{modus}` |", self.text)
        m = re.search(r"^INPUT_SOURCE_TIMEOUT_S = ([0-9.]+)$",
                      _lies("src", "core", "app_state.py"), re.M)
        self.assertTrue(m, "INPUT_SOURCE_TIMEOUT_S nicht gefunden")
        sekunden = m.group(1).replace(".", ",")
        self.assertGreaterEqual(self.text.count(f"{sekunden} Sekunden"), 2)
        # Kein anderer Sekundenwert behauptet einen Timeout.
        self.assertEqual(set(re.findall(r"([0-9]+(?:,[0-9]+)?) Sekunden", self.text)),
                         {sekunden})

    def test_ltp_und_replace_verhalten_sich_im_renderer_gleich(self):
        """Die Anleitung sagt: LTP und REPLACE ersetzen beide. Das gilt, solange
        der Renderer nur HTP gesondert behandelt."""
        quelle = _lies("src", "core", "app_state.py")
        self.assertIn('htp = in_modes.get(univ, "HTP") == "HTP"', quelle)
        self.assertIn("Beide Modi verhalten sich derzeit gleich.", self.text)

    def test_sacn_prioritaet_stimmt(self):
        m = re.search(r"^_E131_DEFAULT_PRIORITY = (\d+)$",
                      _lies("src", "core", "dmx", "sacn.py"), re.M)
        self.assertTrue(m)
        self.assertIn(f"festen Priorität {m.group(1)}", self.text)

    def test_osc_adressen_gibt_es_im_code(self):
        quelle = _lies("src", "core", "osc", "osc_server.py")
        for adresse in ('"/lightos/go"', '"/lightos/back"', '"/lightos/blackout"',
                        '"/lightos/programmer/clear"', '"/lightos/exec/*"',
                        '"/lightos/ch/*"'):
            with self.subTest(adresse):
                self.assertIn(f"d.map({adresse}", quelle)
        for adresse in re.findall(r"`(/lightos/[^`]*)`", self.text):
            kopf = "/".join(adresse.split("/")[:3])     # /lightos/<bereich>
            with self.subTest(adresse):
                self.assertIn(f'd.map("{kopf}', quelle)
        self.assertEqual(
            inspect.signature(__import__("src.core.osc.osc_server", fromlist=["x"])
                              .OscServer.__init__).parameters["ip"].default,
            "127.0.0.1")

    # ── Beschriftungen gegen den Code ────────────────────────────────────────

    def test_genannte_bedienelemente_gibt_es_im_code(self):
        dialog = ("src", "ui", "widgets", "output_config.py")
        midi = ("src", "ui", "views", "midi_view.py")
        fenster = ("src", "ui", "main_window.py")
        fundorte = {
            "Art-Net aktivieren": dialog, "Netzwerkkarte:": dialog,
            "Ziel-IP / Broadcast:": dialog, "Art-Net Startuniversum:": dialog,
            "sACN (E1.31) aktivieren": dialog, "Multicast (239.255.0.x)": dialog,
            "Unicast Ziel-IP:": dialog, "DMX Input": dialog,
            "Art-Net Input": dialog, "sACN Input": dialog,
            "Art-Net Input aktivieren": dialog, "sACN Input aktivieren": dialog,
            "Eingehendes Universe:": dialog, "Merge in Universe:": dialog,
            "Merge-Modus:": dialog, "Übernehmen": dialog, "Ext-Universe": dialog,
            "MIDI Show Control (MSC)": midi, "MSC an": midi, "Device-ID:": midi,
            "GMA-MSC über Netzwerk": midi, "Schnittstelle:": midi, "Port:": midi,
            "SET-Belegung:": midi, "alle Formate annehmen": midi,
            "MIDI-Geräte": midi, "Eingang:": midi, "Eingang öffnen": midi,
            "MIDI Monitor (Eingehende Nachrichten)": midi, "Monitor aktiv": midi,
            "MTC - MIDI Time Code Reader": midi,
            "OSC-Server (Port 7770)": fenster, "Konfigurieren...": fenster,
        }
        for beschriftung, pfad in fundorte.items():
            with self.subTest(beschriftung):
                self.assertIn(f"**{beschriftung}**", self.text,
                              "die Anleitung nennt das Bedienelement nicht mehr")
                self.assertIn(f'"{beschriftung}"', _lies(*pfad),
                              f"{'/'.join(pfad)} kennt die Beschriftung nicht mehr")

    def test_genannte_listeneintraege_und_meldungen_gibt_es_im_code(self):
        midi = _lies("src", "ui", "views", "midi_view.py")
        dialog = _lies("src", "ui", "widgets", "output_config.py")
        for eintrag in ("nur dieser Rechner (127.0.0.1)", "alle Schnittstellen (0.0.0.0)",
                        "grandMA (Executor, Seite)", "Standard (14-Bit-Regler)"):
            with self.subTest(eintrag):
                self.assertIn(f"`{eintrag}`", self.text)
                self.assertIn(f'"{eintrag}"', midi)
        self.assertIn("GMA-MSC: lausche auf", midi)
        self.assertIn("`GMA-MSC: lausche auf <Adresse>:<Port>`", self.text)
        self.assertIn("nicht belegbar", midi)
        self.assertIn('MSC_UDP_PORT_NAME = "MSC/UDP"',
                      _lies("src", "core", "midi", "midi_mapper.py"))
        self.assertIn("`MSC/UDP`", self.text)
        self.assertIn('"Aktiv, aber wirkungslos (U{out_u} nicht als Output "', dialog)
        self.assertIn("`Aktiv, aber wirkungslos (U<n> nicht als Output gepatcht)`",
                      self.text)
        self.assertIn('setText("Gestoppt")', dialog)

    def test_eingang_wird_nicht_gespeichert_und_kennt_keine_geraetesuche(self):
        """Zwei Grenzen aus „Was nicht geht", am Code festgemacht: niemand
        ausser dem Dialog startet die Empfaenger, und es gibt kein ArtPoll."""
        nutzer = []
        for wurzel, _ordner, dateien in os.walk(os.path.join(REPO, "src")):
            for name in dateien:
                if not name.endswith(".py"):
                    continue
                pfad = os.path.join(wurzel, name)
                with open(pfad, encoding="utf-8", errors="replace") as f:
                    quelle = f.read()
                if "get_artnet_receiver(" in quelle or "get_sacn_receiver(" in quelle:
                    nutzer.append(os.path.relpath(pfad, REPO).replace(os.sep, "/"))
                self.assertNotIn("ArtPollReply", quelle, pfad)
        self.assertEqual(sorted(nutzer), ["src/core/dmx/artnet_input.py",
                                          "src/core/dmx/sacn_input.py",
                                          "src/ui/widgets/output_config.py"])
        self.assertIn("Der DMX-Eingang wird nicht gespeichert.", self.text)
        self.assertIn("ArtPoll", self.text)

    def test_grenzen_des_eingangs_reiters_stimmen_mit_dem_code(self):
        """Drei Aussagen unter „Gut zu wissen" (Aufbau B) und im NOT-AUS-Absatz,
        die nur gelten, solange der Code so bleibt."""
        dialog = _lies("src", "ui", "widgets", "output_config.py")
        # Der Reiter laedt den laufenden Zustand nicht: niemand setzt die Haken.
        for haken in ("_check_artnet_in", "_check_sacn_in"):
            with self.subTest(haken):
                self.assertNotIn(f"self.{haken}.setChecked(", dialog)
        self.assertIn("Der Reiter zeigt den laufenden Zustand nicht an.", self.text)
        # Der sACN-Eingang liest die Prioritaet nicht aus dem Paket.
        self.assertNotIn("priority", _lies("src", "core", "dmx", "sacn_input.py").lower())
        self.assertIn("**Priorität** des Absenders nicht aus", self.text)
        # Der Dialog legt HTP als ersten Eintrag vor.
        self.assertIn("Vorgabe ist `HTP`", self.text)
        # Aufbau B nennt den Schritt am Pult.
        i = self.text.index("### Aufbau B — LightOS empfängt vom Pult")
        j = self.text.index("### Aufbau C — das Pult löst Cues aus")
        self.assertIn("**Am Pult**", self.text[i:j])
        self.assertIn("in LightOS gepatchten", _abschnitt(self.text, "## 6. Sicherheit"))

    # ── Bilder und oeffentliches Repo ────────────────────────────────────────

    def test_eingebundene_bilder_existieren(self):
        bilder = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", self.text)
        self.assertEqual(len(bilder), 2, bilder)
        basis = os.path.join(REPO, *REL[:-1])
        for b in bilder:
            with self.subTest(b):
                self.assertTrue(os.path.isfile(os.path.normpath(os.path.join(basis, b))))

    def test_nur_beispieladressen(self):
        """Erlaubt: 2.x / 10.x / 192.168.1.x als Beispiele und die festen
        Sonderadressen (Loopback, alle Schnittstellen, Broadcast, Maske)."""
        erlaubt = re.compile(r"^(2\.0\.0\.\d+|10\.0\.0\.\d+|192\.168\.1\.\d+|"
                             r"127\.0\.0\.1|0\.0\.0\.0|255\.(255|0)\.(255|0)\.(255|0))$")
        for adresse in set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", self.text)):
            with self.subTest(adresse):
                self.assertRegex(adresse, erlaubt)

    def test_keine_privaten_pfade_oder_namen(self):
        for muster in (r"/home/[a-z]", r"C:\\Users\\[A-Za-z]", r"\bMaxi\b", r"\bDavid\b"):
            with self.subTest(muster):
                self.assertNotRegex(self.text, muster)


if __name__ == "__main__":
    unittest.main()
