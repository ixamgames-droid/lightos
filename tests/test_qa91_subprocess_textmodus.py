"""QA-91: kein ``subprocess``-Aufruf im Textmodus ohne feste Kodierung.

Befund (Sitzung B, Windows-ARM, auch auf ``main``):
``tests/test_doc60_buehnen_show.py`` rief ``subprocess.run(..., text=True)``
ohne ``encoding`` — der Test fiel mit „``stdout`` ist ``None``".

Die Ursache ist dieselbe wie bei XPLAT-20 (dort hat sie die Belegungstafel
zerstoert): ``text=True`` dekodiert mit der Locale-Kodierung, unter Windows
cp1252. Enthaelt die Ausgabe des Kindes — oder eines Enkels, der dieselbe
Leitung erbt — ein Byte, das cp1252 nicht kennt (``0x81 0x8D 0x8F 0x90 0x9D``;
schon das UTF-8 von „”" endet auf ``0x9D``), stirbt der Lese-Thread von
``subprocess`` an einem ``UnicodeDecodeError``. Der Fehler wird verschluckt:
``stdout`` ist ``None`` bei ``returncode == 0``. Ob das passiert, haengt vom
Rechner ab (Pfade, Geraetenamen, Meldungen) — auf einem faellt der Test, auf
dem naechsten nie.

Deshalb gilt in ``tests/`` und ``tools/``: Textmodus nur mit
``encoding="utf-8", errors="replace"``. ``errors`` gehoert dazu — ``utf-8``
allein wirft genauso, sobald ein Kind in der Locale-Kodierung schreibt.

Geprueft wird das Muster ueber den Syntaxbaum (kein Textvergleich) und das
Verhalten an einem echten Kindprozess. ``PYTHONUTF8`` setzt das Gate bewusst
NICHT (XPLAT-20): die Aufrufe muessen ohne die Variable stimmen.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ORDNER = ("tests", "tools")
FUNKTIONEN = {"run", "check_output", "check_call", "call", "Popen",
              "getoutput", "getstatusoutput"}


def _wahr(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def subprocess_aufrufe(baum: ast.AST):
    """Alle Aufrufe von ``subprocess.run/Popen/check_output/…`` — ueber die
    Importe des Moduls erkannt (``import subprocess as sp``,
    ``from subprocess import run``), damit ``mock.call(..., encoding=…)`` oder
    ein fremdes ``.run()`` nicht mitzaehlen."""
    module, namen = set(), set()
    for node in ast.walk(baum):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "subprocess":
                    module.add(a.asname or a.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for a in node.names:
                if a.name in FUNKTIONEN:
                    namen.add(a.asname or a.name)
    for node in ast.walk(baum):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        ueber_modul = (isinstance(f, ast.Attribute) and f.attr in FUNKTIONEN
                       and isinstance(f.value, ast.Name) and f.value.id in module)
        if ueber_modul or (isinstance(f, ast.Name) and f.id in namen):
            yield node


def _baum(quelle: str) -> ast.AST:
    # Fremde SyntaxWarnings (z. B. ein altes "\s" in einem Docstring) gehoeren
    # nicht in den Bericht dieses Tests.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(quelle)


def textmodus_ohne_kodierung(quelle: str) -> list[tuple[int, str]]:
    """``[(Zeile, Grund)]`` fuer jeden ``subprocess``-Aufruf, der im Textmodus
    liest oder schreibt, ohne Kodierung UND Fehlerbehandlung festzulegen."""
    befunde = []
    for node in subprocess_aufrufe(_baum(quelle)):
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        textmodus = (_wahr(kw.get("text")) or _wahr(kw.get("universal_newlines"))
                     or "encoding" in kw)
        if not textmodus:
            continue
        if "encoding" not in kw:
            befunde.append((node.lineno, "Textmodus ohne encoding"))
        elif "errors" not in kw:
            befunde.append((node.lineno, "encoding ohne errors"))
    return befunde


def _dateien():
    for ordner in ORDNER:
        for pfad in sorted((REPO / ordner).rglob("*.py")):
            if "__pycache__" not in pfad.parts:
                yield pfad


class MusterTest(unittest.TestCase):

    def test_kein_textmodus_ohne_kodierung_in_tests_und_tools(self):
        befunde = []
        for pfad in _dateien():
            try:
                quelle = pfad.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for zeile, grund in textmodus_ohne_kodierung(quelle):
                befunde.append(f"{pfad.relative_to(REPO).as_posix()}:{zeile}  {grund}")
        self.assertEqual(
            befunde, [],
            "subprocess im Textmodus braucht encoding=\"utf-8\", errors=\"replace\" — "
            "sonst ist stdout auf manchen Windows-Rechnern None (QA-91):\n  "
            + "\n  ".join(befunde[:40]))

    def test_die_suche_ist_nicht_leer_gelaufen(self):
        """Gegenprobe: es gibt solche Aufrufe wirklich, und sie werden gesehen."""
        mit_textmodus = 0
        for pfad in _dateien():
            try:
                baum = _baum(pfad.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, SyntaxError):
                continue
            for node in subprocess_aufrufe(baum):
                if any(k.arg == "encoding" for k in node.keywords):
                    mit_textmodus += 1
        self.assertGreater(mit_textmodus, 50)

    def test_die_pruefung_erkennt_jede_spielart(self):
        faelle = {
            'subprocess.run(c, capture_output=True, text=True)': "Textmodus ohne encoding",
            'subprocess.run(c, universal_newlines=True)': "Textmodus ohne encoding",
            'subprocess.Popen(c, stdout=PIPE, text=True)': "Textmodus ohne encoding",
            'subprocess.check_output(c, text=True)': "Textmodus ohne encoding",
            'run(c, text=True)': "Textmodus ohne encoding",
            'subprocess.run(c, text=True, encoding="utf-8")': "encoding ohne errors",
            'subprocess.run(c, encoding="utf-8")': "encoding ohne errors",
        }
        kopf = "import subprocess\nfrom subprocess import run\n"
        for quelle, grund in faelle.items():
            with self.subTest(quelle):
                self.assertEqual(
                    [g for _z, g in textmodus_ohne_kodierung(kopf + quelle)], [grund])
        for quelle in (
                'subprocess.run(c, capture_output=True)',                       # Bytes
                'subprocess.run(c, text=False)',
                'subprocess.run(c, text=True, encoding="utf-8", errors="replace")',
                'subprocess.Popen(c, encoding="utf-8", errors="replace")',
                'etwas.run(c, text=True)',                                      # kein subprocess
                'mock.call(pfad, "w", encoding="utf-8")',
        ):
            with self.subTest(quelle):
                self.assertEqual(textmodus_ohne_kodierung(kopf + quelle), [])
        # Ein Alias-Import wird erkannt.
        self.assertEqual(
            [g for _z, g in textmodus_ohne_kodierung(
                "import subprocess as sp\nsp.run(c, text=True)")],
            ["Textmodus ohne encoding"])


class VerhaltenTest(unittest.TestCase):
    """Warum beide Angaben noetig sind — an echten Bytes."""

    # „vor ” nach" als UTF-8: das schliessende Anfuehrungszeichen endet auf 0x9D.
    BYTES = "vor ” nach\n".encode("utf-8")

    def test_cp1252_kennt_diese_bytes_nicht(self):
        with self.assertRaises(UnicodeDecodeError):
            self.BYTES.decode("cp1252")

    def test_utf8_allein_wirft_bei_locale_bytes(self):
        """Ein Kind, das „ü" in cp1252 schreibt (ein Byte 0xFC), ist kein UTF-8."""
        with self.assertRaises(UnicodeDecodeError):
            "für".encode("cp1252").decode("utf-8")

    def _kind(self, daten: bytes) -> str:
        code = f"import sys; sys.stdout.buffer.write({daten!r}); sys.stdout.buffer.flush()"
        lauf = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        self.assertIsNotNone(lauf.stdout, "stdout ist None — der Lese-Thread ist gestorben")
        return lauf.stdout

    def test_mit_beiden_angaben_kommt_utf8_richtig_an(self):
        self.assertEqual(self._kind(self.BYTES).strip(), "vor ” nach")

    def test_mit_beiden_angaben_ueberlebt_die_ausgabe_auch_locale_bytes(self):
        aus = self._kind("vor für nach\n".encode("cp1252"))
        self.assertTrue(aus.startswith("vor f") and aus.strip().endswith("nach"), aus)
        self.assertIn("�", aus)            # das eine Byte ist ersetzt, der Rest da


if __name__ == "__main__":
    unittest.main()
