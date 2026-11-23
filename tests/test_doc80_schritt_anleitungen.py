"""DOC-80: die Schritt-fuer-Schritt-Reihe aus dem Live-Klicktest (23.11.2026).

32 kurze Anleitungen in zehn Ordnern ``docs/anleitung_<thema>_schritte/``,
je ``ANLEITUNG.md`` und ``img/`` mit Einzelbildern und einem GIF je Ablauf.
Dieser Waechter haelt fest, was beim Einbau entschieden wurde:

* jeder Ordner steht in ``docs/ANLEITUNGEN.md``, die README verweist auf den
  Abschnitt;
* jedes Bild ist eingebunden, jeder Bildverweis zeigt auf eine Datei
  (keine verwaisten Bestaende wie bei DOC-15);
* das Repo waechst nicht unnoetig: Bilder hoechstens 1600 px breit, GIFs
  hoechstens 900 px breit, 20 Einzelbilder und 1 MB, die ganze Reihe unter
  16 MB (aus 26 MB Rohmaterial);
* die Anleitungen beschreiben die Bedienung, nicht die Fehler aus dem
  Klicktest — keine Hinweise auf „bekannte Fehler“, Pruefberichte oder
  Umgehungen.
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")

ORDNER = (
    "anleitung_patch_bibliothek_schritte",
    "anleitung_gruppen_schritte",
    "anleitung_matrix_effekte_schritte",
    "anleitung_buehne_2d_schritte",
    "anleitung_show_dateien_schritte",
    "anleitung_programmer_schritte",
    "anleitung_vc_schritte",
    "anleitung_playback_schritte",
    "anleitung_ausgabe_schritte",
    "anleitung_web_handy_schritte",
)

#: Saetze, die einen Fehler aus dem Klicktest beschreiben oder umgehen.
VERBOTEN = (
    "bekannter Fehler", "Klicktest-Protokoll", "Prüfbericht", "Stand Test",
    "Stand 23.11.2026)", "stürzte", "Absturz von 3D",
    "`at` statt `@`", "Statt **@** kannst du auch **at**",
    "aus 510 wird 51", "Nach jedem Verschieben springt",
    "ohne Nachfrage weg", "fragt nicht nach", "wird die Cue trotzdem gespeichert",
    "Tab-Taste vervollständigt", "bleibt stehen, auch wenn die 3 Sekunden",
    "landen immer an derselben Stelle", "Fixture ~",
)

_BILD = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _lies(*teile):
    with open(os.path.join(*teile), encoding="utf-8") as f:
        return f.read()


class SchrittAnleitungenTest(unittest.TestCase):

    def test_ordner_und_index(self):
        index = _lies(DOCS, "ANLEITUNGEN.md")
        for name in ORDNER:
            with self.subTest(ordner=name):
                self.assertTrue(os.path.isfile(os.path.join(DOCS, name, "ANLEITUNG.md")))
                self.assertIn(f"({name}/ANLEITUNG.md)", index)
        self.assertIn("## Schritt für Schritt mit GIF", index)
        self.assertIn("docs/ANLEITUNGEN.md#schritt-für-schritt-mit-gif",
                      _lies(REPO, "README.md"))

    def test_zusammen_32_anleitungen(self):
        zahl = 0
        for name in ORDNER:
            text = _lies(DOCS, name, "ANLEITUNG.md")
            zahl += len(re.findall(r"^## ", text, re.M))
        self.assertEqual(zahl, 32)

    def test_bilder_eingebunden_und_vorhanden(self):
        for name in ORDNER:
            text = _lies(DOCS, name, "ANLEITUNG.md")
            verweise = _BILD.findall(text)
            self.assertTrue(verweise, name)
            for ref in verweise:
                with self.subTest(ordner=name, bild=ref):
                    self.assertTrue(ref.startswith("img/"), ref)
                    self.assertRegex(ref, r"^img/[a-z0-9_]+\.(png|gif)$")
                    self.assertTrue(os.path.isfile(os.path.join(DOCS, name, ref)))
            for datei in os.listdir(os.path.join(DOCS, name, "img")):
                with self.subTest(ordner=name, datei=datei):
                    self.assertIn(f"img/{datei})", text, "verwaistes Bild")

    def test_groessen(self):
        from PIL import Image
        gesamt = 0
        for name in ORDNER:
            img = os.path.join(DOCS, name, "img")
            for datei in os.listdir(img):
                pfad = os.path.join(img, datei)
                groesse = os.path.getsize(pfad)
                gesamt += groesse
                with self.subTest(datei=f"{name}/{datei}"), Image.open(pfad) as im:
                    self.assertLessEqual(im.width, 1600)
                    if datei.endswith(".gif"):
                        self.assertLessEqual(im.width, 900)
                        self.assertLessEqual(getattr(im, "n_frames", 1), 20)
                        self.assertLessEqual(groesse, 1024 * 1024)
                    else:
                        self.assertLessEqual(groesse, 400 * 1024)
        self.assertLess(gesamt, 16 * 1024 * 1024)

    def test_keine_fehler_beschreibungen(self):
        for name in ORDNER:
            text = _lies(DOCS, name, "ANLEITUNG.md")
            for satz in VERBOTEN:
                with self.subTest(ordner=name, satz=satz):
                    self.assertNotIn(satz, text)

    def test_der_waechter_greift(self):
        self.assertTrue(any(s in "Achtung: aus 510 wird 51." for s in VERBOTEN))
        self.assertFalse(_BILD.findall("kein Bild"))
        self.assertEqual(_BILD.findall("![x](img/a.png)"), ["img/a.png"])


if __name__ == "__main__":
    unittest.main()
