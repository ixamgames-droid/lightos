"""PRIV-07: Beispiel-Netzadressen in der Doku kommen aus den
Dokumentationsbereichen (RFC 5737), nicht aus einem Heimnetz.

Befund (Verwalter-Sitzung, 25.10.2026): Anleitungen nannten Adressen wie
``192.168.178.99`` — typischer Router-Bereich, einzelne stammten erkennbar aus
dem echten Aufbau (ein Stabilitaetsbericht nannte Adresse, Gateway und DNS des
Rechners). Das Repo ist oeffentlich.

Regel (``COORDINATION.md``): Beispiele aus ``192.0.2.0/24`` bzw.
``198.51.100.0/24`` (Broadcast ``192.0.2.255``) oder dem Art-Net-Bereich
``2.x.x.x``. Dieser Waechter prueft ``docs/`` und die Anleitungs-Dateien im
Repo-Wurzelordner auf private IPv4-Adressen (``192.168.x.y``, ``10.x.y.z``,
``172.16–31.x.y``). Bewusst NICHT geprueft: ``BACKLOG.md``/``CHANGELOG.md``
(Verlauf), Quelltext und Tests — dort sind private Bereiche teils Gegenstand
(LAN-IP-Ermittlung, Erkennung privater Bereiche, Netzlogik).

Waechter-Entscheidung ``tools/session_claim.py``/``pruefe_oeffentlich()``: KEINE
zusaetzliche Warnung fuer ``192.168.178.x``. Die Funktion kennt nur Funde, die
einen Text abweisen, und gilt seit PROC-25 nur noch fuer die wenigen Texte, die
ins oeffentliche Repo gehen; eine Adresse ist dort fachlich zulaessig
(``tests/test_session_claim.py`` laesst „Art-Net an 192.168.1.99 antwortet
nicht“ ausdruecklich durch). Den Platz, an dem Adressen wirklich landen — die
Doku — sichert dieser Waechter.
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

PRIVAT = re.compile(
    r"(?<![\d.])(?:192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d])")

#: Text-Dateien unter docs/, die geprueft werden.
ENDUNGEN = {".md", ".txt", ".json", ".py", ".ps1", ".html", ".csv"}
#: Anleitungs-/Regeldateien im Wurzelordner.
WURZEL = ("README.md", "INSTALL.md", "COORDINATION.md", "AGENTS.md",
          "CONTRIBUTING.md", "WORKFLOW.md")

#: Ausdruecklich erlaubt: (Datei, Adresse) mit Grund.
ERLAUBT = {
    # Die Tabelle erklaert die Werks-Adressbereiche von Pulten/Art-Net-Geraeten
    # (2.x.x.x und 10.x.x.x mit Maske 255.0.0.0) — der Bereich IST der Inhalt.
    ("docs/anleitung_externe_pulte/ANLEITUNG_EXTERNE_PULTE.md", "10.0.0.10"),
    ("docs/anleitung_externe_pulte/ANLEITUNG_EXTERNE_PULTE.md", "10.0.0.20"),
}


def funde_in(text: str) -> list[str]:
    return [m.group(0) for m in PRIVAT.finditer(text)]


def doku_dateien() -> list[pathlib.Path]:
    dateien = [p for p in (ROOT / "docs").rglob("*")
               if p.is_file() and p.suffix.lower() in ENDUNGEN]
    dateien += [ROOT / n for n in WURZEL if (ROOT / n).is_file()]
    return sorted(dateien)


def alle_funde() -> set[tuple[str, str]]:
    funde = set()
    for p in doku_dateien():
        text = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(ROOT).as_posix()
        funde |= {(rel, a) for a in funde_in(text)}
    return funde


class GegenprobeTest(unittest.TestCase):

    def test_private_adressen_schlagen_an(self):
        text = ("Node `192.168.178.99`, Broadcast 192.168.1.255, "
                "sACN → 10.0.0.5, Docker 172.17.0.1, Gateway 172.31.255.1")
        self.assertEqual(funde_in(text), ["192.168.178.99", "192.168.1.255",
                                          "10.0.0.5", "172.17.0.1", "172.31.255.1"])

    def test_dokumentationsbereiche_und_andere_schlagen_nicht_an(self):
        for t in ("192.0.2.50", "192.0.2.255", "198.51.100.20", "203.0.113.7",
                  "2.0.0.10", "255.255.255.0", "172.15.0.1", "172.32.0.1",
                  "110.0.0.1", "Version 10.2.3", "192.168.x.x", "192.168.1.x",
                  "1.10.0.0.5"):
            self.assertEqual(funde_in(t), [], t)


class DokuTest(unittest.TestCase):

    def test_es_wird_wirklich_etwas_geprueft(self):
        namen = {p.relative_to(ROOT).as_posix() for p in doku_dateien()}
        for n in ("docs/anleitung_ausgabe_einrichten/ANLEITUNG.md",
                  "docs/anleitung_enttec_artnet/ANLEITUNG_ENTTEC_ARTNET.md",
                  "README.md", "INSTALL.md"):
            self.assertIn(n, namen)
        self.assertGreater(len(namen), 100)

    def test_keine_heimnetz_adressen_in_der_doku(self):
        rest = sorted(alle_funde() - ERLAUBT)
        self.assertEqual(rest, [], "Beispiele aus 192.0.2.0/24 bzw. "
                                   "198.51.100.0/24 nehmen (RFC 5737)")

    def test_ausnahmen_sind_noch_noetig(self):
        self.assertEqual(ERLAUBT - alle_funde(), set())


if __name__ == "__main__":
    unittest.main()
