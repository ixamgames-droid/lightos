"""FM-45 Scheibe 2: eine Auswahl aus lauter Phantom-Koepfen faehrt NICHTS.

Scheibe 1 hat die Renderer-Seite geschlossen: ``channels_for_head(chans, 48)``
liefert am 4-Kopf-Geraet jetzt ``{}`` statt der geteilten Kanaele. Die
AUSWAHL-Seite kippte weiter in die gefaehrlichere Richtung, und das ist diese
Datei.

★ **Der Weg, gemessen.** ``head_restrictions(["1:48"])`` -> ``{1: {48}}`` ->
``validate_head_restrictions`` klemmt den Kopf weg, den es nicht gibt -> ``{}``.
Und ``{}`` heisst fuer jeden Verbraucher ausdruecklich **„keine
Einschraenkung"**: sie lesen ``heads.get(fid)`` und fallen auf ``(None,)``
zurueck, also auf das GANZE Geraet. Gemeint waren acht Segmente, gefahren wuerde
der ganze Balken.

⚠️ **Ein Sentinel heilt das nicht.** ``{fid: set()}`` waere falsy — die
Verbraucher lesen truthy und faenden denselben Rueckfall vor. Die Auskunft muss
also an der ZIEL-LISTE ankommen, nicht in der Kopf-Maske.

★★ **Warum es EINE Regel ist und nicht vier Kopien.** ``validate_head_restrictions``
verwirft aus vier Gruenden, aber nur EINER davon bedeutet „dieses Geraet gehoert
raus". Die anderen drei — nicht gepatcht, kein Mehrkopf-Geraet, alle Koepfe
genannt — bedeuten weiterhin „geraeteweit", und ein Fix, der sie mitreisst,
waere schlimmer als der Fehler. Deshalb sichert diese Datei alle vier ab, nicht
nur den neuen.

⚠️ **Die zweite Falle liegt im Rueckfall der Verbraucher.** XY-Pad und
MIDI-Fader fahren bei LEERER Auswahl absichtlich ALLE gepatchten Geraete (M3.6).
Wer die Ziel-Liste vor dieser Weiche kuerzt und dabei auf null kommt, loest
genau diesen Rueckfall aus und faehrt statt acht Segmenten das ganze Rig. Die
Abhilfe waere dann schlimmer als der Fehler; ein eigener Test haelt das fest.

**Nicht in dieser Scheibe:** die Beschriftung im Editor (``fid·K49``).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import app_state as A
from src.core.app_state import AppState
from src.core.group_cells import head_restrictions


class _Ch:
    """Kanal-Attrappe — gelesen wird nur ``attribute``/``channel_number``."""

    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0


class _Fx:
    def __init__(self, fid, channels, universe=1, address=1):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channels = channels


def _vier_koepfe():
    """Vier Koepfe mit je RGB -> ``color_head_count`` = 4, gueltig sind K0..K3."""
    chans, n = [], 1
    for _kopf in range(4):
        for attr in ("color_r", "color_g", "color_b"):
            chans.append(_Ch(attr, n))
            n += 1
    return chans


def _ein_kopf():
    """Ein gewoehnlicher PAR — kein Mehrkopf-Geraet."""
    return [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3)]


def _vier_koepfe_bewegung():
    """Vier Koepfe mit je Pan/Tilt — die Zaehlung, die das XY-Pad benutzt.

    ★ Farb- und Bewegungskoepfe sind NICHT dieselbe Zahl: ueber die eingebaute
    Library gehen sie bei 831 von 5116 Modi auseinander, in beide Richtungen.
    Das XY-Pad zaehlt ueber ``move_head_count_for_channels``; ein reines
    RGB-Geraet haette dort weniger als zwei Koepfe und fiele damit in die Regel
    „kein Mehrkopf-Geraet". Der Test wuerde dann gruen sein, ohne die Sache zu
    pruefen, um die es ihm geht — dieselbe Falle wie in FM-9/A5.
    """
    chans, n = [], 1
    for _kopf in range(4):
        for attr in ("pan", "tilt"):
            chans.append(_Ch(attr, n))
            n += 1
    return chans


def _zustand(test, *fixtures):
    """Echter ``AppState`` mit Patch — und Kanaele ohne Datenbank.

    ``get_channels_for_patched`` wird auf ``fx.channels`` umgelenkt (wie im
    A5-XY-Pad-Test). Ein nachgebauter Regel-Rumpf im Test wuerde die Aenderung
    nicht absichern, deshalb laeuft hier die ECHTE Methode.
    """
    st = AppState.__new__(AppState)
    st._patch_cache = list(fixtures)
    orig = A.get_channels_for_patched
    A.get_channels_for_patched = lambda fx: list(getattr(fx, "channels", []))
    test.addCleanup(lambda: setattr(A, "get_channels_for_patched", orig))
    return st


class RegelTest(unittest.TestCase):
    """``fids_ohne_bedienbaren_kopf`` — der neue Grund, und nur der."""

    def test_ein_kopf_den_es_nicht_gibt_meldet_das_geraet(self):
        """Der Fall aus dem Befund: Zelle ``1:48`` an einem 4-Kopf-Geraet."""
        st = _zustand(self, _Fx(1, _vier_koepfe()))
        roh = head_restrictions(["1:48"])
        self.assertEqual({1: {48}}, roh, "Vorbedingung: die rohe Einschraenkung")
        self.assertEqual({}, st.validate_head_restrictions(roh),
                         "Vorbedingung: geklemmt wird laengst richtig")
        self.assertEqual({1}, st.fids_ohne_bedienbaren_kopf(roh),
                         "das Geraet steht NUR ueber einen Phantom-Kopf in der "
                         "Auswahl und gehoert damit aus der Ziel-Liste")

    def test_ein_echter_kopf_meldet_nichts(self):
        st = _zustand(self, _Fx(1, _vier_koepfe()))
        roh = head_restrictions(["1:2"])
        self.assertEqual({1: {2}}, st.validate_head_restrictions(roh))
        self.assertEqual(set(), st.fids_ohne_bedienbaren_kopf(roh))

    def test_ein_gueltiger_kopf_rettet_das_geraet(self):
        """★ Gemischt gewaehlt heisst NICHT „raus".

        ``1:0 + 1:48`` — ein Kopf existiert, einer nicht. Das Geraet bleibt in
        der Ziel-Liste und wird auf den gueltigen Kopf eingeschraenkt; nur der
        Phantom-Kopf faellt weg. Ohne diesen Arm koennte die Regel „ein
        ungueltiger Kopf genuegt" lauten und waere trotzdem gruen.
        """
        st = _zustand(self, _Fx(1, _vier_koepfe()))
        roh = head_restrictions(["1:0", "1:48"])
        self.assertEqual({1: {0}}, st.validate_head_restrictions(roh))
        self.assertEqual(set(), st.fids_ohne_bedienbaren_kopf(roh))


class DieDreiAltenGruendeTest(unittest.TestCase):
    """★★ Die Gegenprobe: der neue Grund darf die drei alten nicht mitreissen.

    Alle vier sehen am Ende gleich aus — ``validate_head_restrictions`` liefert
    nichts. Nur bei EINEM ist „geraeteweit" falsch.
    """

    def test_nicht_gepatchtes_geraet_bleibt_geraeteweit(self):
        st = _zustand(self)                      # gar nichts gepatcht
        self.assertEqual(set(), st.fids_ohne_bedienbaren_kopf(
            head_restrictions(["7:1"])),
            "ein nicht gepatchtes Geraet ist kein Phantom-Kopf-Fall")

    def test_ein_einkopf_geraet_bleibt_geraeteweit(self):
        """„Kopf 1" eines PAR IST das Geraet — das war nie eine Einschraenkung."""
        st = _zustand(self, _Fx(1, _ein_kopf()))
        self.assertEqual(set(), st.fids_ohne_bedienbaren_kopf(
            head_restrictions(["1:0"])))

    def test_alle_koepfe_genannt_bleibt_geraeteweit(self):
        """Die Auto-Gruppe „… · Koepfe" besteht aus lauter Kopf-Zellen.

        Wuerde sie hier gemeldet, verloere ein bestehender Submaster-Fader sein
        ganzes Geraet — die Regressionen, gegen die die Voll-Abdeckungs-Regel
        gebaut wurde (317 Modi der Library haben diese Form).
        """
        st = _zustand(self, _Fx(1, _vier_koepfe()))
        alle = head_restrictions(["1:0", "1:1", "1:2", "1:3"])
        self.assertEqual({}, st.validate_head_restrictions(alle))
        self.assertEqual(set(), st.fids_ohne_bedienbaren_kopf(alle))


class ZielListeTest(unittest.TestCase):
    """``nur_bedienbare_fids`` — die Form, die die vier Verbraucher rufen."""

    def test_kuerzt_genau_das_gemeldete_geraet(self):
        st = _zustand(self, _Fx(1, _vier_koepfe()), _Fx(2, _vier_koepfe()))
        roh = head_restrictions(["1:48", "2:1"])
        self.assertEqual([2], st.nur_bedienbare_fids([1, 2], roh))

    def test_ohne_befund_bleibt_die_liste_unveraendert(self):
        """Reihenfolge inklusive — sie bestimmt die Schreib-Reihenfolge."""
        st = _zustand(self, _Fx(1, _vier_koepfe()))
        self.assertEqual([3, 1, 2],
                         st.nur_bedienbare_fids([3, 1, 2], head_restrictions(["1:1"])))

    def test_ohne_einschraenkung_wird_nichts_angefasst(self):
        st = _zustand(self, _Fx(1, _vier_koepfe()))
        self.assertEqual([1, 2], st.nur_bedienbare_fids([1, 2], {}))


class SubmasterTest(unittest.TestCase):
    """Der VC-Submaster (``_submaster_targets``) — Reichweite „Nur Auswahl"."""

    def _slider(self):
        from src.ui.virtualconsole.vc_slider import VCSlider
        s = VCSlider.__new__(VCSlider)
        s.programmer_scope = "selected"
        s.programmer_group = ""
        return s

    def _state(self, zellen, *fixtures):
        st = _zustand(self, *fixtures)
        st._selected_cells = list(zellen)
        st.get_selected_cells = lambda: list(zellen)
        st.get_selected_fids = lambda: [1]
        return st

    def test_eine_reine_phantom_auswahl_faehrt_NICHTS(self):
        """★★ Der Kern: vorher fuhr der Fader hier das ganze Geraet."""
        st = self._state(["1:48"], _Fx(1, _vier_koepfe()))
        fids, heads = self._slider()._submaster_targets(st)
        self.assertEqual([], fids,
                         "der Fader haelt das Geraet weiter fuer sein Ziel — "
                         "und faehrt es mangels Kopf-Maske GANZ")
        self.assertEqual({}, heads)

    def test_eine_gueltige_kopf_auswahl_bleibt_unveraendert(self):
        st = self._state(["1:2"], _Fx(1, _vier_koepfe()))
        fids, heads = self._slider()._submaster_targets(st)
        self.assertEqual([1], fids)
        self.assertEqual({1: {2}}, heads)


class XYPadRueckfallTest(unittest.TestCase):
    """⚠️ Die gefaehrlichste Stelle: „leer heisst ALLE Geraete" (M3.6).

    Das XY-Pad faehrt ohne Auswahl absichtlich alle gepatchten Geraete. Wer die
    Ziel-Liste VOR dieser Weiche kuerzt, macht aus „diese Geraete nicht" ein
    „nichts gewaehlt" — und fuehrt damit das ganze Rig. Dieser Test haelt die
    Reihenfolge fest, nicht nur das Ergebnis.
    """

    def _pad(self):
        from src.ui.virtualconsole.vc_xypad import VCXYPad
        p = VCXYPad.__new__(VCXYPad)
        p._fixture_ids = []
        return p

    def _state(self, zellen, *fixtures):
        st = _zustand(self, *fixtures)
        st.get_selected_cells = lambda: list(zellen)
        st.get_selected_fids = lambda: sorted(
            {int(str(z).split(":", 1)[0]) for z in zellen})
        return st

    def test_phantom_auswahl_faehrt_nicht_das_ganze_rig(self):
        st = self._state(["1:48"], _Fx(1, _vier_koepfe_bewegung()),
                         _Fx(2, _vier_koepfe_bewegung()))
        self.assertEqual([], self._pad()._ziel_fids(st),
                         "aus 'dieses Geraet nicht' wurde 'nichts gewaehlt' "
                         "— und der M3.6-Rueckfall faehrt dann ALLE Geraete")

    def test_ohne_auswahl_gilt_der_rueckfall_weiterhin(self):
        """★ Die Gegenprobe: der Bestandspfad bleibt unangetastet."""
        st = self._state([], _Fx(1, _vier_koepfe_bewegung()),
                         _Fx(2, _vier_koepfe_bewegung()))
        self.assertEqual([1, 2], self._pad()._ziel_fids(st),
                         "ohne Auswahl muessen weiterhin alle gepatchten "
                         "Geraete fahren (M3.6)")

    def test_eine_feste_zuweisung_bleibt_unberuehrt(self):
        """Eine feste Fixture-Liste ist keine Zell-Auswahl."""
        st = self._state(["1:48"], _Fx(1, _vier_koepfe_bewegung()))
        pad = self._pad()
        pad._fixture_ids = [1]
        self.assertEqual([1], pad._ziel_fids(st))


class DeckungTest(unittest.TestCase):
    """★★ Damit der fuenfte Verbraucher nicht in einem halben Jahr ohne dasteht.

    A's Massstab woertlich: „was erzeugt ein Konsument, der den Sonderwert
    nicht kennt? Muss *nichts* sein, nicht *irgendwas*." Diese Regel liegt
    bewusst NICHT als Sonderwert in ``heads`` — ein Verbraucher, der sie nicht
    kennt, liest also nichts falsch. Er verhaelt sich aber wie bisher, und
    „wie bisher" IST hier *irgendwas*, naemlich das ganze Geraet. Die Regel ist
    damit pro Verbraucher opt-in; dieser Waechter macht das Vergessen sichtbar,
    statt es dem Rig zu ueberlassen.

    ⚠️ Gesucht wird der AUFRUF im Syntaxbaum, nicht der Text. Eine Textsuche
    nach ``head_restrictions(`` findet auch ``validate_head_restrictions(`` und
    meldet damit ``app_state.py`` — gemessen, beim ersten Anlauf dieses
    Waechters. Dieselbe Falle wie in QA-74 und ``test_gate_runner_parity``.
    """

    #: Die Regel selbst — wer ``head_restrictions`` auswertet, muss sie kennen.
    REGEL = ("nur_bedienbare_fids", "fids_ohne_bedienbaren_kopf")

    def _aufrufer(self):
        """Dateien unter ``src/``, die ``head_restrictions(...)`` WIRKLICH rufen."""
        import ast
        import glob
        treffer = {}
        wurzel = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
        for pfad in glob.glob(os.path.join(wurzel, "**", "*.py"), recursive=True):
            with open(pfad, encoding="utf-8") as f:
                quelle = f.read()
            try:
                baum = ast.parse(quelle)
            except SyntaxError:                 # nicht unsere Sorge
                continue
            namen = set()
            for k in ast.walk(baum):
                if not isinstance(k, ast.Call):
                    continue
                f_ = k.func
                name = (f_.id if isinstance(f_, ast.Name)
                        else f_.attr if isinstance(f_, ast.Attribute) else "")
                namen.add(name)
                # ⚠️ Auch die defensive Form zaehlt als Konsultation:
                # ``getattr(state, "fids_ohne_bedienbaren_kopf", None)`` ist ein
                # echter Aufruf der Regel, erzeugt aber keinen Knoten mit ihrem
                # NAMEN. Der erste Anlauf dieses Waechters meldete deshalb
                # cmdline/parser.py — er mass „gibt es einen Direktaufruf"
                # statt der Frage, die er stellt: „kennt diese Datei die
                # Regel". Ein blosses Vorkommen im Text zaehlt weiterhin
                # nicht: verlangt ist ein getattr-AUFRUF mit dem Namen als
                # Zeichenkette.
                if name == "getattr" and len(k.args) >= 2:
                    zweites = k.args[1]
                    if isinstance(zweites, ast.Constant) and isinstance(
                            zweites.value, str):
                        namen.add(zweites.value)
            if "head_restrictions" in namen:
                treffer[os.path.relpath(pfad, wurzel).replace("\\", "/")] = namen
        return treffer

    def test_die_liste_der_aufrufer_ist_nicht_leer(self):
        """★ Ohne das waere die Pruefung unten trivial gruen.

        Ein Waechter, der nichts findet, hat auch nichts zu beanstanden — das
        ist die Form, in der Deckungspruefungen still nutzlos werden.
        """
        self.assertGreaterEqual(len(self._aufrufer()), 4,
                                "die AST-Suche findet die bekannten Verbraucher "
                                "nicht mehr — dann prueft dieser Waechter nichts")

    def test_jeder_aufrufer_kennt_die_regel(self):
        ohne = sorted(datei for datei, namen in self._aufrufer().items()
                      if not any(r in namen for r in self.REGEL))
        self.assertEqual([], ohne,
                         "Diese Stellen werten head_restrictions aus, kuerzen "
                         "ihre Ziel-Liste aber nicht — eine reine "
                         f"Phantom-Auswahl faehrt dort das ganze Geraet: {ohne}")

    def test_app_state_ist_kein_aufrufer(self):
        """⚠️ Die Falle festgenagelt: ``validate_head_restrictions`` ist ein
        anderer Name. Faellt der Waechter je auf die Textsuche zurueck, meldet
        er hier sofort."""
        self.assertNotIn("core/app_state.py", self._aufrufer(),
                         "app_state definiert die Regel, es ruft "
                         "head_restrictions nicht auf — hier misst eine "
                         "Textsuche statt des Syntaxbaums")


if __name__ == "__main__":
    unittest.main()
