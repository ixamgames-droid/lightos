"""QA-100: jede ##-Ueberschrift einer Anleitung steht nur einmal.

Herkunft: beim Einmischen von main in einen Zweig stand in der Anleitung
„Ausgabe einrichten“ Abschnitt 9 zweimal — einmal in der alten, einmal in der
neuen Fassung. Kein Waechter hat es bemerkt; aufgefallen ist es erst beim
naechsten Konflikt. Geprueft wird jede Markdown-Datei in ``docs/anleitung_*/``
sowie ``docs/ANLEITUNG.md`` und ``docs/ANLEITUNGEN.md``: keine ##-Ueberschrift
doppelt, und keine Abschnittsnummer („## 9. …“) doppelt. Ueberschriften in
Codebloecken zaehlen nicht; ###-Unterueberschriften duerfen sich wiederholen.
"""
import collections
import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOCS = os.path.join(_REPO, "docs")
_ZAUN = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_H2 = re.compile(r"^ {0,3}## +(.*?)\s*#*\s*$")
_NUMMER = re.compile(r"^(\d+)[.)](?:\s|$)")


def anleitungen():
    """Alle Anleitungsdateien, relativ zum Repo, sortiert."""
    gefunden = []
    for name in sorted(os.listdir(_DOCS)):
        pfad = os.path.join(_DOCS, name)
        if os.path.isdir(pfad) and name.startswith("anleitung_"):
            for wurzel, _ordner, dateien in os.walk(pfad):
                for datei in dateien:
                    if datei.endswith(".md"):
                        gefunden.append(os.path.join(wurzel, datei))
        elif name in ("ANLEITUNG.md", "ANLEITUNGEN.md"):
            gefunden.append(pfad)
    return sorted(os.path.relpath(p, _REPO).replace(os.sep, "/") for p in gefunden)


def doppelte_ueberschriften(text):
    """Liefert die Beanstandungen: doppelte ##-Ueberschriften und doppelte Nummern."""
    ueberschriften = collections.Counter()
    nummern = collections.defaultdict(list)
    zaun = None
    for zeile in text.splitlines():
        m = _ZAUN.match(zeile)
        if m:
            zeichen = m.group(1)[0]
            if zaun is None:
                zaun = zeichen
            elif zeichen == zaun:
                zaun = None
            continue
        if zaun is not None:
            continue
        m = _H2.match(zeile)
        if not m:
            continue
        titel = " ".join(m.group(1).split())
        ueberschriften[titel] += 1
        n = _NUMMER.match(titel)
        if n:
            nummern[n.group(1)].append(titel)
    fehler = [f"„## {t}“ steht {n}-mal" for t, n in ueberschriften.items() if n > 1]
    fehler += [f"Abschnittsnummer {nr} steht {len(t)}-mal: {t}"
               for nr, t in nummern.items() if len(t) > 1 and len(set(t)) > 1]
    return fehler


class UeberschriftenEinmaligTest(unittest.TestCase):

    def test_jede_ueberschrift_einer_anleitung_nur_einmal(self):
        beanstandet = {}
        for rel in anleitungen():
            with open(os.path.join(_REPO, rel), encoding="utf-8") as f:
                fehler = doppelte_ueberschriften(f.read())
            if fehler:
                beanstandet[rel] = fehler
        self.assertEqual(beanstandet, {}, "doppelte Abschnitte in Anleitungen")

    def test_der_waechter_findet_die_anleitungen(self):
        # Positivkontrolle: sonst waere der Test gruen, weil er nichts liest.
        dateien = anleitungen()
        self.assertGreaterEqual(len(dateien), 100)
        self.assertIn("docs/anleitung_ausgabe_einrichten/ANLEITUNG.md", dateien)
        self.assertIn("docs/anleitung_ausgabe_einrichten/ANLEITUNG.en.md", dateien)
        self.assertIn("docs/ANLEITUNGEN.md", dateien)


class ErkennungTest(unittest.TestCase):

    def test_doppelter_abschnitt_wie_beim_einmischen(self):
        # Der Herkunftsfall: dieselbe Ueberschrift zweimal, Wortlaut darunter verschieden.
        with open(os.path.join(_DOCS, "anleitung_ausgabe_einrichten", "ANLEITUNG.md"), encoding="utf-8") as f:
            echt = f.read()
        kopf = next(z for z in echt.splitlines() if z.startswith("## 9"))
        self.assertEqual(doppelte_ueberschriften(echt), [])
        fehler = doppelte_ueberschriften(echt + "\n" + kopf + "\n\nAlte Fassung.\n")
        self.assertEqual(len(fehler), 1, fehler)
        self.assertIn("2-mal", fehler[0])

    def test_gleiche_nummer_mit_anderem_titel(self):
        fehler = doppelte_ueberschriften("## 9. Neu\n\ntext\n\n## 9. Alt\n\ntext\n")
        self.assertEqual(len(fehler), 1, fehler)
        self.assertIn("Abschnittsnummer 9", fehler[0])

    def test_schreibweisen_der_ueberschrift(self):
        # Abschliessende Rauten und Mehrfach-Leerzeichen machen keine neue Ueberschrift.
        self.assertEqual(len(doppelte_ueberschriften("## Tipps\n\n##  Tipps ##\n")), 1)

    def test_codeblock_und_unterueberschriften_zaehlen_nicht(self):
        text = ("## Beispiel\n\n```bash\n## Beispiel\n```\n\n~~~\n## Beispiel\n~~~\n\n"
                "### Hinweis\n\n## Weiter\n\n### Hinweis\n")
        self.assertEqual(doppelte_ueberschriften(text), [])

    def test_ungeschlossener_codeblock_verdeckt_nichts_danach_nicht_doppelt(self):
        # Ein ```-Zaun schliesst nicht mit ~~~ — was dazwischen steht, bleibt Code.
        text = "## A\n\n```\n~~~\n## A\n```\n\n## A\n"
        self.assertEqual(len(doppelte_ueberschriften(text)), 1)


if __name__ == "__main__":
    unittest.main()
