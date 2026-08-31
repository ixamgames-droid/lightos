"""CDX-50: Die Doku nannte den alten Ort der Gate-Sperre.

Nach PROC-02b (#625) haengt die Sperrdatei am gemeinsamen Git-Verzeichnis.
``WORKFLOW.md`` und ``COORDINATION.md`` schickten weiterhin an den aeusseren
Projektordner — wer eine haengende Sperre loesen will, sah an der falschen
Stelle nach.

★ Eine einmalige Korrektur haette denselben Zustand nur verschoben: die naechste
Verlegung der Sperre laesst die Doku wieder driften. Dieser Test fragt das
**Skript selbst** nach seinem Sperrpfad (Dry-Run) und prueft, dass die Doku
denselben Ort nennt — er wird also rot, sobald die beiden auseinanderlaufen.
"""
import os
import re
import shutil
import subprocess
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOKU = ("WORKFLOW.md", "COORDINATION.md")

# ⚠️ QA-69: dieser Test fragt ``verify_loop.sh`` per ``bash`` nach seinem
# Sperrpfad — und hatte dafuer gar keinen Guard.
#
# ★ Warum das besonders tueckisch war: auf Windows haengt das Ergebnis davon ab,
# WER pytest startet. In einer Git-Bash liegt ``bash`` im PATH, der Test lief und
# war gruen. Im Gate laeuft pytest aus der PowerShell — dort ist ``bash`` NICHT
# im PATH (nachgemessen), der Aufruf starb mit ``FileNotFoundError [WinError 2]``.
# Dieselbe Datei war damit im Gate rot und einzeln nachgefahren gruen, was
# zuverlaessig nach einem Parallellast-Artefakt aussieht und keines war. Wer den
# Unterschied so deutet, sucht den Fehler dauerhaft an der falschen Stelle.
#
# Die Zusicherung selbst (Doku nennt den echten Sperrort) ist nicht
# plattformabhaengig — nur ihre Messung, weil sie das Linux-Gate befragt. Auf
# Windows gibt es dafuer kein Gegenstueck (XPLAT-23).
_BASH_DA = shutil.which("bash") is not None and os.name != "nt"
_BASH_GRUND = ("fragt verify_loop.sh per bash nach dem Sperrpfad — auf Windows "
               "ist bash je nach startender Shell da oder nicht (im Gate: "
               "nicht), und das Linux-Gate ist dort ohnehin nicht das echte "
               "(XPLAT-23)")


def _sperrpfad_laut_skript() -> str:
    """Was ``verify_loop.sh`` als Sperrdatei meldet — die eine Quelle."""
    umgebung = dict(os.environ)
    umgebung["LIGHTOS_VERIFY_DRYRUN"] = "1"
    umgebung["LIGHTOS_VERIFY_NOLOCK"] = "1"     # nur fragen, nicht belegen
    umgebung.pop("LIGHTOS_LOCKFILE", None)
    r = subprocess.run(["bash", os.path.join(_REPO, "tools", "verify_loop.sh")],
                       cwd=_REPO, env=umgebung, capture_output=True, text=True,
                       timeout=180)
    for zeile in r.stdout.splitlines():
        if zeile.startswith("[verify] Sperrdatei:"):
            return zeile.split(":", 1)[1].strip()
    raise AssertionError(f"keine Sperrdatei-Zeile:\n{r.stdout}\n{r.stderr}")


class DokuNenntDieEchteSperreTest(unittest.TestCase):
    # ★ Kein ``setUp``, das ``_sperrpfad_laut_skript()`` holt. Es lief fuer JEDE
    # Testmethode dieser Klasse — auch fuer die Positivkontrolle, die bloss eine
    # Datei liest. Ein Skip auf der bash-Methode allein haette also nichts
    # genuetzt: die andere Methode waere im Gate weiter an ``setUp`` gestorben.
    # Der Aufruf steht deshalb dort, wo er gebraucht wird, hinter dem Guard.

    # Guard NUR hier, nicht auf der Klasse: die Positivkontrolle unten
    # liest bloss WORKFLOW.md und muss auf jeder Plattform laufen.
    @unittest.skipUnless(_BASH_DA, _BASH_GRUND)
    def test_die_doku_nennt_den_ort_den_das_skript_benutzt(self):
        """Das Verzeichnis, an dem die Sperre haengt, muss in der Doku stehen.

        Verglichen wird nicht der ganze Pfad — der enthaelt das
        Arbeitsverzeichnis dieses Rechners und haette in einem oeffentlichen
        Repo nichts zu suchen. Verglichen wird das VERZEICHNIS: heute `.git`.
        """
        pfad = _sperrpfad_laut_skript()
        anker = os.path.basename(os.path.dirname(pfad))    # ".git"
        for datei in _DOKU:
            text = open(os.path.join(_REPO, datei), encoding="utf-8").read()
            self.assertIn(".pytest_lock", text,
                          f"{datei} erwaehnt die Sperre gar nicht")
            self.assertIn(
                f"{anker}/.pytest_lock", text,
                f"{datei} nennt die Sperrdatei, aber nicht das Verzeichnis "
                f"'{anker}', an dem sie laut verify_loop.sh haengt "
                f"({pfad}). Wer sie loesen will, sucht falsch.")

    # ★ Bewusst KEIN Test „der alte Ort darf nicht mehr vorkommen".
    #
    # Die erste Fassung hatte ihn — und er schlug sofort an, naemlich auf den
    # historischen Nebensatz „Bis PROC-02b (#625) lag sie im aeusseren
    # Projektordner", der genau die Frage beantwortet, mit der jemand hier
    # landet. Ein Waechter, der die nuetzliche Erklaerung beanstandet, ist ein
    # Fehlalarm; und Fehlalarme sind der sicherste Weg, ein Gate abzuschalten
    # (siehe QA-54). Die positive Aussage oben reicht: sie wird rot, sobald
    # Doku und Skript auseinanderlaufen — und nur dann.

    def test_die_messung_wuerde_eine_abweichung_auch_sehen(self):
        """POSITIVKONTROLLE: mit einem erfundenen Anker muss der Vergleich
        scheitern. Sonst koennte `assertIn` auf etwas treffen, das ohnehin
        ueberall steht."""
        umfeld = open(os.path.join(_REPO, "WORKFLOW.md"), encoding="utf-8").read()
        self.assertNotIn("cdx50-kein-echtes-verzeichnis", umfeld)


if __name__ == "__main__":
    unittest.main()
