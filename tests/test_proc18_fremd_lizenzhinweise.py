"""PROC-18: Fremde Dateien im Repo brauchen Lizenztext und Urheberhinweis.

LightOS selbst hat keine Lizenz (Entscheidung des Projektinhabers), liefert aber
three.js (MIT) mit; die Lizenz verlangt, dass der Lizenztext beiliegt. Befund aus
FM-55: fremde Dateien lagen ohne jeden Hinweis im Repo. Dieser Waechter haelt
fest, dass jede Datei in den Fremd-Ordnern in THIRD_PARTY_NOTICES.md steht und
die Lizenztexte da sind.

VIZ-66: die frueheren QLC+-Modelle (Apache-2.0) sind durch eigene Geometrie
ersetzt und mitsamt Apache-Lizenztext entfernt. Dass keine Modelldateien
zurueckkommen, prueft ``test_viz66_keine_fremden_modelle.py``.

TOOL-24: der Eintrag wird GELESEN, nicht gesucht
------------------------------------------------
Bis hierhin pruefte der Waechter per Teilstring ueber die ganze Datei
(``rel in text``). Damit bestand auch:

* ein Dateiname, der nur im Fliesstext, in einem ANDEREN Abschnitt oder in
  einem auskommentierten Block vorkommt;
* ``three.min.js`` ohne Pfad — irgendwo;
* ein Lizenztext, der nur beilaeufig erwaehnt wird, aber zu keinem Eintrag
  gehoert;
* ein Eintrag ohne Urheber oder ohne Herkunft, solange der Dateiname faellt.

Jetzt wird ``THIRD_PARTY_NOTICES.md`` in Abschnitte (``## ``) und deren Felder
(``- **Name:** …``) zerlegt. Eine fremde Datei gilt als ausgewiesen, wenn sie
mit vollem Pfad unter **Dateien:** genau EINES Abschnitts steht und dieser
Abschnitt **Herkunft**, **Urheber** und **Lizenz** (mit Verweis auf einen
vorhandenen Text unter ``licenses/``) nennt. Herkunft: Codex-Review #862.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
LIZENZEN = ROOT / "licenses"

#: Ordner, deren Inhalt komplett fremd ist -> jede Datei muss genannt sein.
FREMD_ORDNER = [
    ROOT / "assets/vendor",
]
#: Einzelne fremde Dateien ausserhalb dieser Ordner.
FREMD_DATEIEN = [
    "src/ui/visualizer/three_local.js",
]


# ── Lesen ────────────────────────────────────────────────────────────────────

_KOMMENTAR = re.compile(r"<!--.*?-->", re.S)
_CODEBLOCK = re.compile(r"^```.*?^```[^\n]*$", re.S | re.M)
_FELD = re.compile(r"^- \*\*(?P<name>[^*:]+):\*\*(?P<rest>.*)$")
_LIZENZ_LINK = re.compile(r"\]\(licenses/(?P<datei>[^)\s]+)\)")
_PFAD_PUNKT = re.compile(r"^\s+- `(?P<pfad>[^`]+)`\s*$")


class Eintrag:
    """Ein ``## ``-Abschnitt mit seinen Feldern."""

    def __init__(self, titel: str):
        self.titel = titel
        self.felder: dict[str, str] = {}
        self.dateien: list[str] = []

    def lizenz_dateien(self) -> list[str]:
        """Lizenztexte, auf die das Feld **Lizenz** bzw. **Lizenztext** zeigt."""
        gefunden = []
        for name in ("Lizenz", "Lizenztext"):
            gefunden += _LIZENZ_LINK.findall(self.felder.get(name, ""))
        return gefunden


def eintraege(text: str) -> list[Eintrag]:
    """Zerlegt die Notices in Abschnitte. Auskommentiertes und Code-Bloecke
    zaehlen nicht — dort steht kein gueltiger Eintrag."""
    text = _CODEBLOCK.sub("", _KOMMENTAR.sub("", text))
    aus: list[Eintrag] = []
    aktuell: Eintrag | None = None
    feld: str | None = None
    for zeile in text.splitlines():
        if zeile.startswith("## "):
            aktuell, feld = Eintrag(zeile[3:].strip()), None
            aus.append(aktuell)
            continue
        if aktuell is None:
            continue
        m = _FELD.match(zeile)
        if m:
            feld = m.group("name").strip()
            aktuell.felder[feld] = m.group("rest").strip()
        elif feld and zeile.startswith(" "):
            # Fortsetzung oder Unterpunkt des Feldes.
            aktuell.felder[feld] += "\n" + zeile
            p = _PFAD_PUNKT.match(zeile)
            if p and feld == "Dateien":
                aktuell.dateien.append(p.group("pfad"))
        else:
            feld = None            # Leerzeile, Fliesstext, anderer Listenpunkt
    return aus


def befunde(text: str, fremd: list[str], lizenztexte: list[str],
            existiert=lambda rel: True) -> list[str]:
    """Alles, was an den Lizenzhinweisen nicht stimmt — leer heisst in Ordnung.

    ``fremd``: repo-relative Pfade aller fremden Dateien; ``lizenztexte``:
    Dateinamen unter ``licenses/``; ``existiert(rel)``: gibt es die Datei?
    """
    alle = eintraege(text)
    aus: list[str] = []
    for rel in fremd:
        treffer = [e for e in alle if rel in e.dateien]
        if not treffer:
            aus.append(f"{rel}: steht in keinem Abschnitt unter **Dateien:**")
            continue
        if len(treffer) > 1:
            aus.append(f"{rel}: steht in mehreren Abschnitten "
                       f"({', '.join(e.titel for e in treffer)})")
        e = treffer[0]
        for pflicht in ("Herkunft", "Urheber", "Lizenz"):
            if not e.felder.get(pflicht, "").strip():
                aus.append(f"{rel}: Abschnitt „{e.titel}“ nennt kein **{pflicht}:**")
        if "Urheber" in e.felder and "Copyright" not in e.felder["Urheber"]:
            aus.append(f"{rel}: **Urheber:** in „{e.titel}“ ohne Copyright-Vermerk")
        if "Lizenz" in e.felder and not _LIZENZ_LINK.search(e.felder["Lizenz"]):
            aus.append(f"{rel}: **Lizenz:** in „{e.titel}“ verweist auf keinen "
                       f"Text unter licenses/")
    for e in alle:
        for rel in e.dateien:
            if not existiert(rel):
                aus.append(f"Abschnitt „{e.titel}“ nennt {rel}, die Datei gibt es nicht")
        for datei in e.lizenz_dateien():
            if datei not in lizenztexte:
                aus.append(f"Abschnitt „{e.titel}“ verweist auf licenses/{datei}, "
                           f"der Text liegt nicht bei")
    verlinkt = {d for e in alle for d in e.lizenz_dateien()}
    for datei in lizenztexte:
        if datei not in verlinkt:
            aus.append(f"licenses/{datei}: kein Abschnitt verweist im Feld "
                       f"**Lizenz:** oder **Lizenztext:** darauf")
    return aus


def _fremde_dateien() -> list[str]:
    aus = []
    for ordner in FREMD_ORDNER:
        aus += [p.relative_to(ROOT).as_posix()
                for p in sorted(ordner.rglob("*")) if p.is_file()]
    return aus + list(FREMD_DATEIEN)


def _lizenztexte() -> list[str]:
    return sorted(p.name for p in LIZENZEN.iterdir() if p.is_file())


# ── Der echte Bestand ────────────────────────────────────────────────────────

class FremdLizenzhinweiseTest(unittest.TestCase):
    def setUp(self):
        self.text = NOTICES.read_text(encoding="utf-8")

    def test_jede_fremde_datei_hat_einen_vollstaendigen_eintrag(self):
        self.assertEqual(
            befunde(self.text, _fremde_dateien(), _lizenztexte(),
                    existiert=lambda rel: (ROOT / rel).is_file()),
            [], "THIRD_PARTY_NOTICES.md")

    def test_fremd_ordner_sind_nicht_leer(self):
        # Gegenprobe: ein verschobener Ordner liesse den Waechter leer gruen werden.
        for ordner in FREMD_ORDNER:
            self.assertTrue(any(p.is_file() for p in ordner.rglob("*")), ordner)

    def test_fremd_dateien_existieren(self):
        # Gegenprobe: eine umbenannte Datei liesse ihren Eintrag ins Leere zeigen.
        for rel in FREMD_DATEIEN:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_three_js_eintrag_passt_zu_seinem_lizenztext(self):
        """Nicht irgendein Eintrag und irgendein Text: DER Abschnitt, der die
        three.js-Dateien fuehrt, verweist auf DEN MIT-Text, und dessen
        Copyright-Zeile nennt denselben Urheber."""
        zustaendig = [e for e in eintraege(self.text)
                      if "assets/vendor/three.min.js" in e.dateien]
        self.assertEqual(len(zustaendig), 1)
        e = zustaendig[0]
        self.assertIn("src/ui/visualizer/three_local.js", e.dateien)
        self.assertEqual(e.lizenz_dateien(), ["MIT-three.js.txt"])
        self.assertIn("MIT", e.felder["Lizenz"])
        self.assertIn("three.js authors", e.felder["Urheber"])
        self.assertIn("github.com/mrdoob/three.js", e.felder["Herkunft"])
        mit = (LIZENZEN / "MIT-three.js.txt").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted", mit)
        self.assertIn("three.js authors", mit)

    def test_jeder_lizenztext_gehoert_zu_einem_eintrag(self):
        # VIZ-66: ein Lizenztext ohne Komponente (z. B. Apache-2.0 nach dem
        # Entfernen der QLC+-Modelle) behauptete eine Fremd-Datei, die es nicht
        # gibt. TOOL-24: „gehoert zu" heisst, ein Abschnitt verweist in seinem
        # Lizenz-Feld darauf — eine Erwaehnung im Fliesstext genuegt nicht.
        verlinkt = {d for e in eintraege(self.text) for d in e.lizenz_dateien()}
        self.assertEqual(sorted(verlinkt), _lizenztexte())


# ── Der Waechter selbst: findet er, was er finden soll? ──────────────────────

_GUT = """# Fremd-Komponenten

Einleitung.

## three.js — 3D-Bibliothek (r128)

- **Herkunft:** three.js (<https://github.com/mrdoob/three.js>), Release r128.
- **Urheber:** Copyright © 2010-2021 three.js authors.
- **Lizenz:** MIT — [`licenses/MIT-three.js.txt`](licenses/MIT-three.js.txt).
- **Dateien:**
  - `assets/vendor/three.min.js`
  - `src/ui/visualizer/three_local.js`

## Apache License 2.0

- **Lizenztext:** [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).
- **Wofür:** Geräteprofile.
"""
_FREMD = ["assets/vendor/three.min.js", "src/ui/visualizer/three_local.js"]
_TEXTE = ["Apache-2.0.txt", "MIT-three.js.txt"]


class WaechterFindetLueckenTest(unittest.TestCase):
    """Jeder Fall nennt, ob die ALTE Pruefung (Teilstring ueber die ganze
    Datei) ihn durchgelassen haette — das ist der Befund von TOOL-24."""

    def _alt_gruen(self, text: str) -> bool:
        """Die Pruefung vor TOOL-24, sinngleich nachgebildet."""
        for rel in _FREMD:
            kurz = rel.split("/")[-1] if rel.startswith("assets/vendor/") else rel
            if kurz not in text and rel not in text:
                return False
        return all(f"licenses/{t}" in text for t in _TEXTE)

    def _befunde(self, text: str, **kw):
        return befunde(text, _FREMD, _TEXTE, **kw)

    def test_die_gute_fassung_hat_keinen_befund(self):
        self.assertEqual(self._befunde(_GUT), [])
        self.assertTrue(self._alt_gruen(_GUT))

    def test_datei_nur_im_fliesstext_genannt(self):
        text = _GUT.replace("  - `src/ui/visualizer/three_local.js`\n", "") \
            + "\nHinweis: `src/ui/visualizer/three_local.js` ist eine Kopie.\n"
        self.assertTrue(self._alt_gruen(text), "die alte Pruefung liess das durch")
        b = self._befunde(text)
        self.assertEqual(len(b), 1, b)
        self.assertIn("src/ui/visualizer/three_local.js", b[0])
        self.assertIn("keinem Abschnitt", b[0])

    def test_datei_nur_im_auskommentierten_block(self):
        text = _GUT.replace(
            "  - `src/ui/visualizer/three_local.js`\n",
            "<!--\n  - `src/ui/visualizer/three_local.js`\n-->\n")
        self.assertTrue(self._alt_gruen(text), "die alte Pruefung liess das durch")
        self.assertTrue(any("three_local.js" in x for x in self._befunde(text)))

    def test_datei_steht_im_falschen_abschnitt(self):
        """Unter „Apache" gelistet: der Abschnitt hat weder Herkunft noch
        Urheber noch ein Lizenz-Feld — die Datei waere falsch ausgewiesen."""
        text = _GUT.replace("  - `src/ui/visualizer/three_local.js`\n", "") \
            + "- **Dateien:**\n  - `src/ui/visualizer/three_local.js`\n"
        self.assertTrue(self._alt_gruen(text), "die alte Pruefung liess das durch")
        b = [x for x in self._befunde(text) if "three_local.js" in x]
        self.assertEqual(len(b), 3, b)          # Herkunft, Urheber, Lizenz fehlen
        self.assertTrue(all("Apache License 2.0" in x for x in b))

    def test_nur_der_dateiname_ohne_pfad_genuegt_nicht(self):
        text = _GUT.replace("`assets/vendor/three.min.js`", "`three.min.js`")
        self.assertTrue(self._alt_gruen(text), "die alte Pruefung liess das durch")
        self.assertTrue(any(x.startswith("assets/vendor/three.min.js: steht in keinem")
                            for x in self._befunde(text)))

    def test_eintrag_ohne_herkunft_urheber_oder_lizenz(self):
        for feld in ("Herkunft", "Urheber", "Lizenz"):
            with self.subTest(feld):
                text = re.sub(rf"^- \*\*{feld}:\*\*.*\n", "", _GUT, count=1, flags=re.M)
                if feld != "Lizenz":
                    self.assertTrue(self._alt_gruen(text),
                                    "die alte Pruefung liess das durch")
                b = self._befunde(text)
                self.assertTrue(any(f"kein **{feld}:**" in x for x in b), b)

    def test_lizenz_ohne_verweis_auf_einen_text(self):
        text = _GUT.replace(
            "- **Lizenz:** MIT — [`licenses/MIT-three.js.txt`](licenses/MIT-three.js.txt).",
            "- **Lizenz:** MIT.") + "\nDer Text liegt unter licenses/MIT-three.js.txt.\n"
        self.assertTrue(self._alt_gruen(text), "die alte Pruefung liess das durch")
        b = self._befunde(text)
        self.assertTrue(any("verweist auf keinen Text" in x for x in b), b)
        self.assertTrue(any(x.startswith("licenses/MIT-three.js.txt: kein Abschnitt")
                            for x in b), b)

    def test_lizenztext_nur_beilaeufig_erwaehnt(self):
        text = _GUT.replace(
            "- **Lizenztext:** [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).\n",
            "") + "\nFrüher lag hier auch licenses/Apache-2.0.txt.\n"
        self.assertTrue(self._alt_gruen(text), "die alte Pruefung liess das durch")
        self.assertEqual(
            self._befunde(text),
            ["licenses/Apache-2.0.txt: kein Abschnitt verweist im Feld "
             "**Lizenz:** oder **Lizenztext:** darauf"])

    def test_verweis_auf_fehlenden_lizenztext(self):
        b = befunde(_GUT, _FREMD, ["MIT-three.js.txt"])
        self.assertEqual(len(b), 1, b)
        self.assertIn("licenses/Apache-2.0.txt, der Text liegt nicht bei", b[0])

    def test_eintrag_nennt_eine_datei_die_es_nicht_gibt(self):
        b = self._befunde(_GUT, existiert=lambda rel: "three_local" not in rel)
        self.assertEqual(len(b), 1, b)
        self.assertIn("die Datei gibt es nicht", b[0])

    def test_datei_in_zwei_abschnitten(self):
        text = _GUT + "- **Dateien:**\n  - `assets/vendor/three.min.js`\n"
        self.assertTrue(any("mehreren Abschnitten" in x for x in self._befunde(text)))

    def test_neue_fremde_datei_ohne_eintrag(self):
        b = befunde(_GUT, _FREMD + ["assets/vendor/neu.min.js"], _TEXTE)
        self.assertEqual(b, ["assets/vendor/neu.min.js: steht in keinem Abschnitt "
                             "unter **Dateien:**"])


if __name__ == "__main__":
    unittest.main()
