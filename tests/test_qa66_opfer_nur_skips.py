"""QA-66: Opfer-Segment fuer die Waechter-Deckung — KEIN eigener Testinhalt.

★ **Diese Datei prueft nichts.** Sie ist Werkzeug, nicht Test: das
Opfer-Segment, an dem `test_qa58_bibliothek_schema_unberuehrt.py` belegt, dass
der QA-58-Waechter auch dann greift, wenn ein Segment die Geraetebibliothek
**beim Modul-Import** laedt, ohne dass jemals ein Test laeuft. Genau diese
Luecke sieht eine pytest-Fixture nicht — sie wird nie ausgefuehrt.

**Warum es sie gibt (QA-66).** Vorher diente `tests/test_color_fx_show_render.py`
als Opfer, mit der Annahme „seine Tests ueberspringen sich, die Show ist nicht
committet". Das stimmte in der CI und in einem frischen Worktree — aber
`shows/Farb_FX_VC_Show.lshow` ist bloss **gitignored, nicht abwesend**. Wer
`tools/build_farb_fx_vc_show.py` einmal laufen liess, hat die Datei; das Segment
lief dann (5 passed) und der Waechter wurde rot. Auf Davids Windows-Rechner liegt
sie seit dem 28.07.2026, und der Test faerbte damit **jeden fremden Branch**
falsch rot — genau die Zeitfalle aus QA-53: die Frage „liegt es an meinem Diff?"
war verstellt.

★★ **Die Eigenschaft, um die es geht, haengt jetzt an nichts Zufaelligem mehr:**

* der Modul-Import laedt ``app_state`` und damit ``fixture_db`` — das ist der
  Vorgang, den der Waechter sehen muss;
* ``pytestmark`` ueberspringt **jeden** Test dieser Datei, unabhaengig von
  Arbeitskopie, Betriebssystem und davon, welche Werkzeuge jemand einmal
  laufen liess.

⚠️ Nichts hier hinzufuegen, was laufen soll. Ein Test in dieser Datei waere kein
zusaetzlicher Nutzen, sondern wuerde die Zusicherung zerstoeren, fuer die es sie
gibt.
"""
import pytest

# Der Import IST der Zweck: er zieht ``fixture_db`` in den Prozess, bevor ein
# Test laufen koennte. (F401 ist beabsichtigt — der Name wird nicht benutzt.)
from src.core import app_state  # noqa: F401

#: Gilt fuer die ganze Datei und ist der Kern der Zusicherung.
pytestmark = pytest.mark.skip(
    reason="QA-66: Opfer-Segment. Es laedt die Bibliothek beim Import und "
           "fuehrt absichtlich NIE einen Test aus.")


def test_wird_nie_ausgefuehrt():
    """Platzhalter, damit das Segment ueberhaupt etwas zu ueberspringen hat.

    Laeuft er doch, ist die Zusicherung dieser Datei gebrochen — und der Test,
    der sie benutzt, meldet das ausdruecklich.
    """
    raise AssertionError(
        "Dieser Test darf nie laufen (QA-66). Laeuft er, ueberspringt sich das "
        "Opfer-Segment nicht mehr, und die Waechter-Deckung in "
        "test_qa58_bibliothek_schema_unberuehrt.py belegt nichts mehr.")
