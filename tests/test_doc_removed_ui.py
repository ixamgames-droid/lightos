"""DOC-10 Teil b — keine Anleitung weist auf entfernte Bedienelemente hin.

Der Chase-Builder wurde am **2026-06-30** entfernt (PR #116: Widget,
`WIDGET_REGISTRY`, Toolbar-Eintrag, Inspector-Label, Tests, zehn Generatoren).
**Drei Anleitungen schickten den Nutzer trotzdem weiter dorthin** — über einen
Monat lang, darunter eine Überschrift ("Live-Chase selbst bauen ... +
Chase-Builder") und eine nummerierte Handlungsanweisung. Wer danach arbeitet,
sucht ein Bedienfeld, das es nicht mehr gibt, und hält sich selbst für den Fehler.

**Warum diese Form von Gate und keine allgemeine:** ein Versuch, *alle* in den
Anleitungen zitierten UI-Beschriftungen gegen den Quelltext zu prüfen, ergab 177
Treffer auf 960 Zitate — fast alles Falschmeldungen (Typografie, Platzhalter wie
"Widget: ... ändern", Namen aus Demo-Shows wie "PAR Rot", dynamische
Statuszeilen wie "Selektion: 8 Fixtures"). Ein Gate mit dieser Trefferquote
würde ignoriert und wäre damit schlechter als keines.

Die Liste unten ist deshalb **klein und handgepflegt**: nur Bedienelemente, die
nachweislich entfernt wurden. Wer eines entfernt, trägt es hier ein — und
erfährt im selben Moment, welche Anleitungen er mitziehen muss.

**Geprüft wird nur, was der Nutzer als Handlungsanweisung liest** — also
Anleitungen. Audit-Berichte, Pläne und abgeschlossene Test-Logs *sollen* den
alten Stand nennen; das ist ihr Zweck. `_ist_anleitung()` zieht diese Grenze,
und `test_abgrenzung_ist_wirksam` hält sie ehrlich, damit die Auswahl nicht
irgendwann versehentlich leer läuft und das Gate lautlos grün wird.
"""
from __future__ import annotations

import ast
import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOCS = os.path.join(_REPO, "docs")
_SRC = os.path.join(_REPO, "src")

# Name -> (entfernt am, wodurch ersetzt). Beides landet im Fehlertext, damit der
# nächste Leser nicht erst Archäologie betreiben muss.
_ENTFERNT = {
    "Chase-Builder": ("2026-06-30 (PR #116)",
                      "Chase-Liste (VCColorList) zeigt die Folge; gebaut wird "
                      "über Farb-Kacheln und Live-Aktionen"),
    "Chase Builder": ("2026-06-30 (PR #116)", "s. Chase-Builder"),
    "Fixtures bearbeiten": ("2026-08-02 (PR #552)",
                            "Modus 'Bauen' + Tab 'Fixtures'"),
    "Bühne bearbeiten": ("2026-08-02 (PR #552)",
                         "Modus 'Bauen' + Tab 'Bühne'"),
}

# Erwähnung als GESCHICHTE ist erlaubt — nur die aktive Anweisung ist das Problem.
_HISTORISCH = re.compile(r"früher|frueher|entfernt|ehemal|bis \d{4}-|seit \d{4}-",
                         re.I)


# Berichte und Pläne tragen ihre Art im Namen — das ist hier gewachsene
# Konvention (ANLEITUNGEN_AUDIT_*, *_PLAN.md, …), nicht meine Erfindung.
_BERICHT_IM_NAMEN = re.compile(r"AUDIT|PLAN|ANALYSIS|FINDINGS|BUGLOG")
# Dokumente zu archivierten Shows sagen das im Kopf ("beide archiviert —
# TOOLS-ALTGEN 2026-07-27"). Sie beschreiben korrekt, was die Show DAMALS tat.
_ARCHIV_MARKE = re.compile(r"archiviert", re.I)
_KOPFZEILEN = 10


def _ist_anleitung(pfad: str) -> bool:
    """Anleitung = etwas, dem ein Leser HEUTE Schritt für Schritt folgt.

    Umgekehrte Beweislast: alles gilt als Anleitung, außer es weist sich
    selbst als Rückblick aus. So fällt ein neues Dokument nicht stillschweigend
    aus der Prüfung — es müsste sich aktiv als Bericht deklarieren.
    """
    if _BERICHT_IM_NAMEN.search(os.path.basename(pfad).upper()):
        return False
    with open(pfad, encoding="utf-8", errors="replace") as fh:
        kopf = "".join(zeile for _n, zeile in zip(range(_KOPFZEILEN), fh))
    return not _ARCHIV_MARKE.search(kopf)


def _anleitungen():
    for wurzel, verz, dateien in os.walk(_DOCS):
        verz[:] = [v for v in verz if v != "_archiv"]
        for f in dateien:
            pfad = os.path.join(wurzel, f)
            if f.endswith(".md") and _ist_anleitung(pfad):
                yield pfad


def _befunde_in(zeilen, quelle: str):
    """Kern der Prüfung — als Funktion, damit die positive Kontrolle unten
    genau denselben Weg nimmt wie der Lauf über die echten Dateien."""
    treffer = []
    for nr, zeile in enumerate(zeilen, 1):
        if _HISTORISCH.search(zeile):
            continue
        for name in _ENTFERNT:
            if name in zeile:
                treffer.append((quelle, nr, name))
    return treffer


def _quelltext_literale() -> set:
    """Alle String-Literale des Quelltexts (ohne Docstrings).

    Ein lebendes Bedienelement steht als **Literal** im Code — ein Kommentar
    ("bis 2026-08-02 hieß das X") ist Prosa und darf den Namen nennen. Über den
    AST zu gehen statt über den Rohtext trennt beides sauber; Kommentare kommen
    im AST gar nicht erst vor.
    """
    literale = set()
    for wurzel, _v, dateien in os.walk(_SRC):
        for f in dateien:
            pfad = os.path.join(wurzel, f)
            with open(pfad, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            if f.endswith(".py"):
                try:
                    baum = ast.parse(text)
                except SyntaxError:  # pragma: no cover — compileall fängt das
                    literale.add(text)
                    continue
                docstrings = set()
                for knoten in ast.walk(baum):
                    if isinstance(knoten, (ast.Module, ast.ClassDef,
                                           ast.FunctionDef, ast.AsyncFunctionDef)):
                        doc = ast.get_docstring(knoten, clean=False)
                        if doc is not None:
                            docstrings.add(doc)
                for knoten in ast.walk(baum):
                    if (isinstance(knoten, ast.Constant)
                            and isinstance(knoten.value, str)
                            and knoten.value not in docstrings):
                        literale.add(knoten.value)
            elif f.endswith((".js", ".html")):
                ohne_block = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
                literale.update(re.sub(r"//[^\n]*", " ", ohne_block).split("\n"))
    return literale


class EntfernteUiTest(unittest.TestCase):

    def test_liste_nennt_nur_wirklich_entferntes(self):
        """Gegenprobe: steht ein Eintrag noch als Beschriftung im Code, ist die
        Liste falsch — und das Gate würde eine korrekte Anleitung anmeckern."""
        literale = _quelltext_literale()
        self.assertGreater(len(literale), 5000,
                           "zu wenige Literale gefunden — der Scan greift ins Leere")
        noch_da = sorted(n for n in _ENTFERNT
                         if any(n in lit for lit in literale))
        self.assertEqual(
            noch_da, [],
            "diese Namen stehen noch als Beschriftung im Quelltext, gelten "
            f"hier aber als entfernt: {noch_da}")

    def test_abgrenzung_ist_wirksam(self):
        """Die Auswahl darf weder leer sein (Gate liefe ins Nichts) noch alles
        umfassen (Audits/Pläne würden zu Unrecht angemeckert)."""
        gewaehlt = {os.path.relpath(p, _REPO) for p in _anleitungen()}
        alle = sum(1 for _w, _v, d in os.walk(_DOCS) for f in d
                   if f.endswith(".md"))
        self.assertGreater(len(gewaehlt), alle // 3,
                           "kaum Anleitungen erfasst — Abgrenzung zu weit")
        for muss_raus, warum in (
                ("docs/APC_PROBIER.md", "Log zu archivierter Show"),
                ("docs/MASTER_DEMO.md", "Log zu archivierter Show"),
                ("docs/VIZ3D_OVERHAUL_PLAN.md", "Plan"),
                ("docs/ANLEITUNGEN_AUDIT_2026-07-20.md", "Bericht")):
            self.assertNotIn(muss_raus, gewaehlt,
                             f"{muss_raus} ist {warum}, keine Anleitung")
        for muss_rein in ("docs/anleitung_ablaeufe/ANLEITUNG_ABLAEUFE_MISCHEN.md",
                          "docs/anleitung_vc_widgets/19_matrix_editor.md",
                          "docs/RIG_CHECKLISTE.md"):
            self.assertIn(muss_rein, gewaehlt)

    def test_erkennt_einen_verweis(self):
        """Positive Kontrolle: findet die Prüfung überhaupt etwas, und lässt
        sie die historische Erwähnung wirklich durch?"""
        self.assertEqual(
            len(_befunde_in(["1. Öffne den Chase-Builder in der Toolbar."], "x")),
            1)
        self.assertEqual(
            _befunde_in(["Der Chase-Builder wurde 2026 entfernt."], "x"), [])

    def test_keine_anleitung_weist_auf_entferntes_hin(self):
        befunde = []
        for pfad in _anleitungen():
            with open(pfad, encoding="utf-8", errors="replace") as fh:
                befunde += _befunde_in(fh, os.path.relpath(pfad, _REPO))
        hinweis = "; ".join(f"{n}: entfernt {_ENTFERNT[n][0]} -> {_ENTFERNT[n][1]}"
                            for n in _ENTFERNT)
        self.assertEqual(
            befunde, [],
            f"Anleitung verweist auf entferntes Bedienelement. {hinweis}. "
            "Als Geschichte erwaehnen ist erlaubt (Wort 'frueher'/'entfernt' "
            f"in derselben Zeile), als Handlungsanweisung nicht: {befunde}")


if __name__ == "__main__":
    unittest.main()
