"""WEB-12 „Fertig, wenn“: die Anleitung ``docs/anleitung_web_remote/`` stimmt
Satz fuer Satz mit dem Code.

Geprueft wird, was sich maschinell gegen den Code halten laesst: jede
Beschriftung, die die Anleitung aus dem Dialog, der Seitenleiste und der
Handy-Seite zitiert, steht dort wirklich; die Tabelle „ab Werk“ stimmt mit
``remote_settings.DEFAULTS``; die Adressen der festen Fernbedienung stimmen mit
der Rechte-Tabelle; jede Halten-Taste und jede Fader-Art mit Laser-Pruefung ist
in der Anleitung genannt (eine neue Art ohne Eintrag hier faellt auf); die
Bedingungen der Laser-Freigabe stehen im Bestaetigungsfenster und auf der
eigenen Seite gleich.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
DOKU = ROOT / "docs" / "anleitung_web_remote"


def _lies(*teile) -> str:
    return ROOT.joinpath(*teile).read_text(encoding="utf-8")


def _anleitung() -> str:
    return (DOKU / "ANLEITUNG.md").read_text(encoding="utf-8")


def _laser_seite() -> str:
    return (DOKU / "LASER_VOM_HANDY.md").read_text(encoding="utf-8")


def _flach(text: str) -> str:
    """Zeilenumbrueche und Mehrfach-Leerzeichen zu einem Leerzeichen."""
    return re.sub(r"\s+", " ", text)


class DialogBeschriftungTest(unittest.TestCase):
    """Was die Anleitung aus dem Verbindungs-Dialog zitiert, steht im Dialog."""

    ZITATE = (
        "📱 Handy verbinden",
        "📱 Handy verbunden — QR-Code scannen",
        "Web-Remote: Verbindung & Token",
        "Handy-Konsole (bedient nur Elemente der Handy-Seiten)",
        "LAN-/Handy-Remote (aus = nur dieser PC)",
        "Laser vom Handy erlauben",
        "Erweitert",
        "Feste Fernbedienung (GO, Executor-Fader, Blackout) — ",
        "eigener Schlüssel",
        "Roh-DMX über die feste Fernbedienung",
        "Schlüssel erneuern (neues Token)",
        "Link kopieren",
        "Kopieren",
        "Web-Interface: aus",
        "läuft — nur dieser PC",
        "läuft — im (W)LAN erreichbar",
        "Handy-Konsole: bereit",
        "Laser freigeben",
        "Abbrechen",
    )

    def test_zitate_stehen_im_dialog(self):
        quelle = _lies("src", "ui", "widgets", "web_remote_dialog.py")
        doku = _flach(_anleitung() + _laser_seite())
        for z in self.ZITATE:
            with self.subTest(z):
                self.assertIn(z, quelle)
                # Der Dialog teilt die Beschriftung der festen Seite auf zwei
                # Zeilen; die Anleitung nennt sie am Stueck.
                self.assertTrue(z.rstrip(" —").strip() in doku, z)

    def test_nur_dieser_pc_zeigt_die_adresse_die_gilt(self):
        self.assertIn("„… läuft — nur\ndieser PC (127.0.0.1:5000)\"", _anleitung())
        quelle = _lies("src", "ui", "widgets", "web_remote_dialog.py")
        self.assertIn('return f"http://127.0.0.1:{self.PORT}"', quelle)

    def test_statusleiste(self):
        quelle = _lies("src", "ui", "main_window.py")
        self.assertIn('f"Web: :{port} OK"', quelle)
        self.assertIn('"Web: aus"', quelle)
        self.assertIn("„Web: :5000 OK\"", _anleitung())
        self.assertIn("„Web: aus\"", _anleitung())


class AbWerkTest(unittest.TestCase):

    def test_tabelle_ab_werk_stimmt_mit_den_vorgaben(self):
        from src.web import remote_settings
        doku = _anleitung()
        zeilen = {
            "Handy-Konsole (bedient nur Elemente der Handy-Seiten)": "vc_remote_enabled",
            "LAN-/Handy-Remote (aus = nur dieser PC)": "lan_remote_enabled",
            "Laser vom Handy erlauben": "laser_vom_handy",
            "Erweitert → Feste Fernbedienung": "feste_seite_enabled",
            "Erweitert → Roh-DMX": "roh_dmx_enabled",
        }
        for name, schluessel in zeilen.items():
            with self.subTest(name):
                zeile = re.search(r"(?m)^\| \*\*" + re.escape(name) + r"\*\* \|.*\| (\S+) \|$",
                                  doku)
                self.assertIsNotNone(zeile, name)
                self.assertEqual(zeile.group(1), "aus")
                self.assertIs(remote_settings.DEFAULTS[schluessel], False)
        self.assertIn("Web-Interface, Zugriff aus dem WLAN, Handy-Konsole, feste\n"
                      "  Fernbedienung, Roh-DMX und Laser-Freigabe sind ab Werk aus.", doku)


class FesteSeiteTest(unittest.TestCase):

    def test_adressen_der_festen_seite_stimmen_mit_der_rechte_tabelle(self):
        from src.web import app as webapp
        abschnitt = _anleitung().split("## 6. Erweitert", 1)[1]
        genannt = set(re.findall(r"`(?:POST |GET )?(/api/[^`]+)`", abschnitt))
        genannt = {re.sub(r"<(\w+)>", r"<int:\1>", p) for p in genannt}
        fest = {r for r, recht in webapp.ROUTEN_RECHTE.items() if recht == webapp.RECHT_FEST}
        roh = {r for r, recht in webapp.ROUTEN_RECHTE.items() if recht == webapp.RECHT_ROH_DMX}
        self.assertEqual(genannt, fest | roh)
        self.assertEqual(roh, {"/api/channel/<int:universe>/<int:channel>"})

    def test_fehlercodes(self):
        self.assertIn("mit **400**, ein unbekannter Slot oder Kanal mit **404**", _anleitung())
        quelle = _lies("src", "web", "app.py")
        self.assertIn('_fehler("unbekannter_slot", 404)', quelle)
        self.assertIn('_fehler("unbekannter_kanal", 404)', quelle)
        self.assertIn('"wert_ungueltig"}, 400', quelle)


class HandySeiteTest(unittest.TestCase):

    def test_meldungen_der_handy_seite(self):
        html = _lies("src", "web", "templates", "konsole.html")
        doku = _anleitung()
        for text in ("LASER NOT-AUS AKTIV", "🔒 Laser – Freigabe am Pult",
                     "Blackout kam nicht von diesem Handy – aufheben am Pult"):
            with self.subTest(text):
                self.assertIn(text, html)
                self.assertIn(text, doku)
        self.assertIn("🔒 Laser – Freigabe am Pult", _laser_seite())

    def test_jede_halten_taste_ist_genannt(self):
        from src.ui.virtualconsole import vc_fernbedienung as vf
        from src.ui.virtualconsole.vc_button import ButtonAction
        namen = {               # Aktion (+ Snap-Modus) -> Name in der Anleitung
            ("Flash", ""): "Flash",
            ("FunctionFlash", ""): "„nur gehalten\"",
            ("Blackout", ""): "Blackout",
            ("AllWhite", ""): "Alles Weiß",
            ("LibrarySnap", "flash"): "Bibliothek-Snap im Flash-Modus",
        }

        class _W:
            pass

        zeile = next(z for z in _anleitung().splitlines() if z.startswith("| **Taste** |"))
        for wert in [v for k, v in vars(ButtonAction).items()
                     if k.isupper() and isinstance(v, str)]:
            for snap in ("", "flash", "toggle"):
                w = _W()
                w.action, w.snap_mode = wert, snap
                if vf._halteart(w) != "halten":
                    continue
                schluessel = (wert, snap if wert == "LibrarySnap" else "")
                with self.subTest(wert=wert, snap=snap):
                    self.assertIn(schluessel, namen, "neue Halten-Taste: Anleitung "
                                                     "und diese Tabelle ergaenzen")
                    self.assertIn(namen[schluessel], zeile)

    def test_schluessel_im_protokoll(self):
        from src.core import diagnose_log
        self.assertEqual(diagnose_log.SCHLUESSEL_ERSATZ, "<schluessel>")
        self.assertIn("erscheint statt des Schlüssels `<schluessel>`", _anleitung())
        self.assertEqual(diagnose_log.schluessel_schwaerzen("/konsole?k=abc123"),
                         "/konsole?k=<schluessel>")


class LaserSeiteTest(unittest.TestCase):

    def test_link_im_bestaetigungsfenster_fuehrt_auf_die_seite(self):
        from src.ui.widgets import web_remote_dialog as d
        self.assertTrue((ROOT / "docs" / d.LASER_BEDINGUNGEN).is_file())
        self.assertIn(f'href="{d.LASER_BEDINGUNGEN}"', d.LASER_TEXT)
        self.assertIn("](LASER_VOM_HANDY.md)", _anleitung())
        self.assertIn("](ANLEITUNG.md)", _laser_seite())

    def test_bedingungen_gleich_im_fenster_und_auf_der_seite(self):
        from src.ui.widgets import web_remote_dialog as d
        punkte = re.findall(r"<li>(.*?)</li>", d.LASER_TEXT)
        seite = _flach(_laser_seite().split("## Die Bedingungen", 1)[1]
                       .split("## Was der Schalter", 1)[0])
        nummern = re.findall(r"(?:^| )(\d)\. \*\*", seite)
        self.assertEqual(len(punkte), 5)
        self.assertEqual(nummern, ["1", "2", "3", "4", "5"])
        # je Bedingung ein Stichwort, das in beiden steht
        for wort in ("Laser-Bereich und das Publikum", "NOT-AUS", "eigenen WLAN",
                     "Scharfschalten", "Schalter wieder ausschalten"):
            with self.subTest(wort):
                self.assertTrue(any(wort in _flach(re.sub("<[^>]+>", "", p)) for p in punkte),
                                wort)
                self.assertIn(wort, seite)
        self.assertIn("Mit **„Laser freigeben\"** im Bestätigungsfenster", _laser_seite())

    def test_jede_fader_art_ist_eingeordnet(self):
        from src.ui.virtualconsole.vc_slider import SliderMode as M
        seite = _flach(_laser_seite())
        # Fader-Art -> Stichwort auf der Seite (None = nur Tempo, nie gesperrt)
        arten = {
            M.LEVEL: "DMX-Kanal eines Lasers",
            M.PLAYBACK: "Playback-Fader",
            M.SUBMASTER: "Submaster",
            M.GRANDMASTER: "Grand-Master-Fader",
            M.PROGRAMMER: "Programmer-Fader",
            M.EFFECT_INTENSITY: "Funktion mit Laser",
            M.EFFECT_SPEED: "Effekt-Tempo",
            M.EFFECT_PARAM: "-Parameter",
            M.GROUP_DIMMER: "Gruppen-Dimmer",
            M.FEATURE_DIMMER: "Gruppen-Dimmer",
            M.BPM: None, M.SPEED: None, M.TEMPO_BUS: None,
        }
        alle = {v for k, v in vars(M).items() if k.isupper() and isinstance(v, str)}
        self.assertEqual(alle, set(arten), "neue Fader-Art: Laser-Pruefung und "
                                           "LASER_VOM_HANDY.md ergaenzen")
        for art, wort in arten.items():
            if wort is not None:
                with self.subTest(art):
                    self.assertIn(wort, seite)


if __name__ == "__main__":
    unittest.main()
