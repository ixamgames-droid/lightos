"""FM-45: ein Kopf, den es nicht gibt, darf nicht das ganze Geraet fahren.

**Der Befund (2026-09-03, beim Kartieren des Zellmodells).** Eine Rasterzelle
``"1:48"`` am ZQ06121 — der hat 48 Koepfe, also 0..47 — wird ueberall anstandslos
angenommen. Wirkungslos ist sie aber nicht: ``channels_for_head(chans, 48)``
lieferte genau die **geteilten** Kanaele (``intensity``, ``shutter``), weil ein
einmaliges Attribut als „geteilt, also bei jedem Kopf dabei" gilt. Mit
``drive_intensity`` stand danach messbar **CH1 = 255** — der Master-Dimmer des
ganzen Balkens.

★ **Die Ursache war eine Luecke, keine falsche Regel.** Die beiden per-Kopf-Zweige
in ``channels_for_head`` pruefen ihre Grenze laengst (``0 <= head < len(...)``);
der Zweig fuer das einmalige Attribut haengt es bedingungslos an. „Jeder Kopf"
hiess damit auch: jeder Kopf, den es nicht gibt.

**Was diese Datei abdeckt:** die RENDERER-Seite und die beiden Parse-Wege.

⚠️ **Was sie NICHT abdeckt** (FM-45 Scheibe 2): die AUSWAHL-Seite. Dort kippt es
in die gefaehrlichere Richtung — ``head_restrictions(["1:48"])`` ergibt
``{1: {48}}``, ``validate_head_restrictions`` klemmt den Phantom-Kopf weg, und
ein **leeres** Ergebnis heisst ausdruecklich „keine Einschraenkung", also das
ganze Geraet. Ein VC-Submaster auf einer reinen Phantom-Auswahl faehrt damit
alles statt nichts. Das ist nicht mit einem Sentinel zu heilen: die Verbraucher
lesen ``heads.get(fid)`` **truthy**, ein leeres Set fiele genauso auf „ganzes
Geraet" zurueck. Ebenfalls offen: die Beschriftung im Editor (``fid·K49``).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import channels_for_head
from src.core.group_cells import parse_group_cell


class _Ch:
    """Kanal-Attrappe — ``channels_for_head`` liest nur ``attribute``."""

    def __init__(self, number, attribute):
        self.number = number
        self.attribute = attribute


def _vier_kopf_balken():
    """Nachbau der Bauform, an der es aufgefallen ist: geteilter Master-Dimmer
    und Shutter, danach vier RGB-Koepfe. 317 Modi der eingebauten Library haben
    genau diese Form (ein Master-Dimmer + mehrere Farbbaenke)."""
    chans = [_Ch(1, "intensity"), _Ch(2, "shutter")]
    nr = 3
    for _kopf in range(4):
        for attr in ("color_r", "color_g", "color_b"):
            chans.append(_Ch(nr, attr))
            nr += 1
    return chans


class RendererTest(unittest.TestCase):
    """``channels_for_head`` — hier sass der Master-Dimmer-Fehler."""

    def test_ein_kopf_den_es_nicht_gibt_bekommt_gar_nichts(self):
        """★★ Der Kern. Vier Koepfe heisst 0..3; 4 gibt es nicht."""
        chans = _vier_kopf_balken()
        for phantom in (4, 9, 48):
            with self.subTest(head=phantom):
                self.assertEqual(
                    {}, channels_for_head(chans, phantom),
                    f"Kopf {phantom} bekommt Kanaele, obwohl es ihn nicht gibt")

    def test_der_master_dimmer_ist_nicht_mehr_dabei(self):
        """★★ Das buehnensichtbare Symptom, ausdruecklich festgenagelt.

        Gemessen VOR dem Fix: ``{intensity, shutter}`` — mit
        ``drive_intensity`` stand CH1 auf 255, der Master-Dimmer des ganzen
        Balkens, waehrend der Nutzer eine einzelne Zelle gefahren hat.
        """
        ergebnis = channels_for_head(_vier_kopf_balken(), 4)
        self.assertNotIn("intensity", ergebnis,
                         "der geteilte Master-Dimmer haengt weiterhin am "
                         "Phantom-Kopf — genau der Fund aus FM-45")
        self.assertNotIn("shutter", ergebnis)

    def test_ein_negativer_kopf_bekommt_gar_nichts(self):
        """Nebenbefund (a) derselben Messung, auf der Renderer-Seite."""
        self.assertEqual({}, channels_for_head(_vier_kopf_balken(), -1))

    def test_die_echten_koepfe_bleiben_unveraendert(self):
        """★ Positivkontrolle — ohne sie waere „Phantom liefert nichts" auch
        dadurch zu erreichen, dass gar kein Kopf mehr etwas bekommt."""
        chans = _vier_kopf_balken()
        for kopf in range(4):
            with self.subTest(head=kopf):
                ergebnis = channels_for_head(chans, kopf)
                self.assertIn("intensity", ergebnis,
                              "der geteilte Master-Dimmer fehlt einem ECHTEN Kopf")
                self.assertIn("color_r", ergebnis)
                # Jeder Kopf hat SEIN eigenes Rot: 3, 6, 9, 12.
                self.assertEqual(3 + 3 * kopf, ergebnis["color_r"].number)

    def test_single_head_kopf_null_liefert_weiter_alle_kanaele(self):
        """★ Die Zusicherung aus dem Docstring von ``channels_for_head``.

        „``head=0`` auf einem Single-Head-Fixture liefert schlicht alle Kanaele
        (byte-identisch zum Nicht-Kopf-Pfad)." Die neue Grenze darf die nicht
        brechen: bei lauter einmaligen Attributen ist die Kopfzahl 1, und 0 ist
        damit gueltig.
        """
        single = [_Ch(1, "intensity"), _Ch(2, "color_r"), _Ch(3, "color_g")]
        self.assertEqual({"intensity", "color_r", "color_g"},
                         set(channels_for_head(single, 0)))
        # ... und Kopf 1 gibt es dort eben nicht.
        self.assertEqual({}, channels_for_head(single, 1))


class ParseTest(unittest.TestCase):
    """``parse_group_cell`` — Nebenbefund (a): der Kopfindex war unten offen."""

    def test_ein_negativer_kopf_ist_keine_kopfzelle(self):
        self.assertEqual((None, None), parse_group_cell("5:-1"))

    def test_er_wird_NICHT_zum_ganzen_geraet_befoerdert(self):
        """★ Die Richtung ist wichtig.

        ``(5, None)`` waere die stille Befoerderung einer kaputten Kopf-Zelle
        zum GANZEN Geraet — also genau dorthin, wovon FM-45 handelt. Verworfen
        heisst hier wie sonst: die Zelle faellt weg.
        """
        fid, _head = parse_group_cell("5:-1")
        self.assertIsNone(fid, "die kaputte Kopf-Zelle wurde zum ganzen Geraet")

    def test_echte_zellen_bleiben_unveraendert(self):
        """★ Positivkontrolle: Rueckwaertskompatibilitaet der Alt-Gruppen."""
        self.assertEqual((5, None), parse_group_cell("5"))
        self.assertEqual((5, None), parse_group_cell(5))
        self.assertEqual((5, 0), parse_group_cell("5:0"))
        self.assertEqual((5, 2), parse_group_cell("5:2"))
        self.assertEqual((None, None), parse_group_cell("x"))


class LoeschPfadTest(unittest.TestCase):
    """Nebenbefund (b): die beiden Haelften desselben Features widersprachen sich.

    Das Aufraeumen beim Geraet-Loeschen entschied per rohem String-Vergleich
    (``v.split(":", 1)[0] == str(fid)``), ob eine Auto-Gruppe ausschliesslich
    Koepfe DIESES Geraets adressiert — und lag damit in beide Richtungen daneben:
    es nahm ``"5:irgendwas"`` an (was ``parse_group_cell`` verwirft) und
    scheiterte an ``"05:2"`` (was als fid 5 parst). Eine Auto-Gruppe wurde also
    je nach Schreibweise geloescht oder stehengelassen.
    """

    #: Die alte Regel, woertlich — nur hier, als Vergleichsmassstab.
    @staticmethod
    def _alte_regel(value, fid) -> bool:
        v = str(value)
        return ":" in v and v.split(":", 1)[0] == str(fid)

    def _neue_regel(self, value, fid) -> bool:
        f, h = parse_group_cell(value)
        return f is not None and h is not None and int(f) == int(fid)

    def test_die_beiden_regeln_gingen_wirklich_auseinander(self):
        """Belegt den Widerspruch, statt ihn zu behaupten."""
        self.assertTrue(self._alte_regel("5:irgendwas", 5))
        self.assertFalse(self._neue_regel("5:irgendwas", 5),
                         "kaputte Zelle gilt weiterhin als Kopf-Zelle")
        self.assertFalse(self._alte_regel("05:2", 5))
        self.assertTrue(self._neue_regel("05:2", 5),
                        "gueltige Kopf-Zelle wird weiterhin nicht erkannt")

    def test_der_loeschpfad_benutzt_den_gemeinsamen_parser(self):
        """Der Quelltext-Waechter dazu.

        Ein Verhaltenstest muesste hier eine Show-DB aufbauen, ein Geraet
        patchen und loeschen; die Zusicherung ist aber, WELCHE Quelle gefragt
        wird. Faellt jemand auf den String-Vergleich zurueck, wird das hier rot.
        """
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(wurzel, "src", "core", "app_state.py"),
                  encoding="utf-8") as f:
            quelle = f.read()
        self.assertNotIn('v.split(":", 1)[0] == str(fid)', quelle,
                         "der rohe String-Vergleich im Loesch-Pfad ist zurueck "
                         "— dann widersprechen sich die beiden Parse-Wege wieder")
        self.assertIn("parse_group_cell as _pgc", quelle,
                      "der Loesch-Pfad fragt nicht mehr den gemeinsamen Parser")


if __name__ == "__main__":
    unittest.main()
