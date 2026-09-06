"""ENG-21: eine Live-Aenderung von „Tempo ד liess Effekte SPRINGEN.

Alle vier zeitbasierten Funktionstypen leiten ihre Position aus DERSELBEN
Formel ab::

    local = (bus.position - _beat_anchor) * tempo_multiplier + phase_offset

``local`` ist die Phase (EFX/Matrix) bzw. der Ziel-Step (Chaser/Sequence).
Aendert man den Faktor im Betrieb, skaliert er die GANZE seit dem Anker
verstrichene Beat-Distanz **rueckwirkend** — der Effekt steht in EINEM Frame an
einer Stelle, an der er nie war.

**Gemessen vor dem Fix** (Bus 120 BPM, 3,1 s nach dem Anker, ×1,0 → ×1,25)::

    Klasse     Weg          local vorher  local nachher     Delta
    EFX        set_param        6,200000       7,750000  +1,550000
    EFX        direkt           6,200000       7,750000  +1,550000
    Matrix     set_param        6,200000       7,750000  +1,550000
    Matrix     direkt           6,200000       7,750000  +1,550000
    Chaser     set_param        6,200000       0,000000  -6,200000   Step 6 -> 0
    Chaser     direkt           6,200000       7,750000  +1,550000   Step 6 -> 7
    Sequence   set_param        6,200000       0,000000  -6,200000   Step 6 -> 0
    Sequence   direkt           6,200000       7,750000  +1,550000   Step 6 -> 7

★★★ **Der Backlog-Eintrag nannte als Vorlage ``shift_clock`` — das waere
falsch gewesen.** ``shift_clock`` verschiebt ``_last_tick``, den
monotonic-Anker des Vorschaupfads, und fasst den Bus-Pfad gar nicht an. Und die
naheliegende Alternative aus dem Haus ist ebenfalls falsch: der F5-Fix
``_reanchor_bus_target`` setzte ``_beat_anchor = bus.position()`` und traegt nur
bei Chaser/Sequence, weil ``_step_idx`` dort EIGENER Zustand ist, der den
Anker-Sprung ueberlebt. Bei EFX/Matrix wird die Phase AUS dem Anker abgeleitet —
dieselbe Zeile erzeugt dort **einen anderen harten Sprung** (Phase 0,200 →
0,000). Richtig ist, ``local`` zu ERHALTEN und nur die Rate zu wechseln.

⚠️ **Und es ist kein EFX/Matrix-Item, sondern ein Loch ueber vier Klassen.**
Die Tempo-Spinboxen der Editoren schreiben ``tempo_multiplier`` **direkt aufs
Objekt** und gehen an ``set_param`` vorbei — vier verifizierte Stellen:
``efx_view.py:1736``, ``rgb_matrix_view.py:1521``, ``chaser_editor.py:406``,
``sequence_editor.py:411``. Ein Fix in ``set_param`` haette fuer VC-Speed-Dial,
MIDI und ``effect_live`` gewirkt — aber **nicht dort, wo man am Tempo dreht**.
Deshalb sitzt die Regel an der ZUWEISUNG (Property auf ``Function``): das ist
die einzige Stelle, die alle Schreiber sieht, heutige wie kuenftige.
"""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.engine.chaser import Chaser, ChaserStep  # noqa: E402
from src.core.engine.efx import EfxInstance  # noqa: E402
from src.core.engine.rgb_matrix import RgbMatrixInstance  # noqa: E402
from src.core.engine.sequence import Sequence, SequenceStep  # noqa: E402
from src.core.engine.tempo_bus import get_tempo_bus_manager  # noqa: E402

#: 120 BPM = 2 Beats je Sekunde. Macht jede Zahl unten von Hand nachrechenbar.
BPM = 120.0
FRAME = 0.02


def _bus():
    """DENSELBEN Zugriff wie die Engine.

    ★ Aus eigenem Schaden: ``ensure_bus("Global")`` liefert einen **anderen**
    Bus als ``get("Global")`` — ``get`` loest den Alias „Global" auf den
    Default-Bus auf, ``ensure_bus`` legt einen Bus namens „Global" an. Die erste
    Fassung dieser Messung hat deshalb einen Bus fortgeschaltet, den der Code
    unter Test nie gelesen hat. Eine Sonde muss ihren Gegenstand ueber denselben
    Weg holen wie der Code, ueber den sie eine Aussage macht.
    """
    bus = get_tempo_bus_manager().get("Global")
    assert bus is not None, "Vorbedingung: der Default-Bus existiert"
    bus.set_bpm(BPM)
    return bus


class _Basis(unittest.TestCase):

    def setUp(self):
        self.bus = _bus()

    def vor(self, sekunden: float):
        for _ in range(int(round(sekunden / FRAME))):
            self.bus.advance_frame(FRAME)

    def local(self, o) -> float:
        """Die Groesse, aus der ALLE vier Typen ihre Position ableiten."""
        return round((self.bus.position() - o._beat_anchor)
                     * (o.tempo_multiplier or 1.0) + o.phase_offset, 9)

    # ── Die vier Bauer ──────────────────────────────────────────────────────
    def efx(self):
        return self._anker(EfxInstance(name="E"))

    def matrix(self):
        return self._anker(RgbMatrixInstance(name="M"))

    def chaser(self):
        c = Chaser(name="C")
        c.steps = [ChaserStep(function_id=i) for i in range(8)]
        c.beats_per_step = 1.0
        c._synced_target_prev = None
        return self._anker(c)

    def sequence(self):
        s = Sequence(name="S")
        s.steps = [SequenceStep() for _ in range(8)]
        s.beats_per_step = 1.0
        s._synced_target_prev = None
        return self._anker(s)

    def _anker(self, o):
        o.tempo_bus_id = "Global"
        o._beat_anchor = self.bus.position()
        o._running = True
        return o

    def alle(self):
        return (("EFX", self.efx), ("Matrix", self.matrix),
                ("Chaser", self.chaser), ("Sequence", self.sequence))


class TempoWechselIstStetigTest(_Basis):

    def _wechsel(self, bauer, weg, faktor=1.25, warten=3.1):
        """Ein Tempowechsel MITTEN im Lauf. Liefert (vorher, nachher)."""
        o = bauer()
        self.vor(warten)
        vorher = self.local(o)
        # ★★ Vorbedingung, nicht Annahme: liegt der Effekt noch auf seinem Anker,
        # ist local 0 und es gibt gar nichts zu verlieren — die Messung waere
        # wertlos und saehe wie eine Entwarnung aus.
        self.assertGreater(abs(vorher), 1e-6,
                           "Vorbedingung verletzt: der Effekt ist nicht gelaufen")
        if weg == "set_param":
            o.set_param("tempo_multiplier", faktor)
        else:
            o.tempo_multiplier = faktor
        self.assertAlmostEqual(o.tempo_multiplier, faktor, places=9,
                               msg="Vorbedingung verletzt: der Faktor wurde gar "
                                   "nicht uebernommen")
        return o, vorher, self.local(o)

    def test_kein_sprung_ueber_alle_vier_typen_und_beide_wege(self):
        """★★★ Der Kern. Vier Klassen × zwei Schreibwege — vorher sprangen
        sieben von acht Kombinationen."""
        for name, bauer in self.alle():
            for weg in ("set_param", "direkt"):
                with self.subTest(klasse=name, weg=weg):
                    _o, vorher, nachher = self._wechsel(bauer, weg)
                    self.assertAlmostEqual(
                        nachher, vorher, places=9,
                        msg=f"{name} springt im Wechsel-Frame um "
                            f"{nachher - vorher:+.6f} Beats")

    def test_der_editor_weg_ist_der_wichtigere(self):
        """★★ Die eigentliche Einordnung des Items: die Tempo-Spinboxen der vier
        Editoren schreiben das Attribut DIREKT. Ein Fix nur in ``set_param``
        haette genau dort nicht gewirkt, wo man am Tempo dreht — deshalb haengt
        die Regel an der Zuweisung, nicht am Setter-Namen."""
        for name, bauer in self.alle():
            with self.subTest(klasse=name):
                _o, vorher, nachher = self._wechsel(bauer, "direkt", faktor=4.0)
                self.assertAlmostEqual(nachher, vorher, places=9)

    def test_auch_das_verlangsamen_ist_stetig(self):
        """Die andere Richtung — sonst koennte ein Fix „gelingen", der nur
        Beschleunigen abfaengt."""
        for name, bauer in self.alle():
            with self.subTest(klasse=name):
                _o, vorher, nachher = self._wechsel(bauer, "direkt", faktor=0.25)
                self.assertAlmostEqual(nachher, vorher, places=9)

    # ── Die Gegenprobe: der Fix darf nicht durch Einfrieren „gelingen" ──────
    def test_die_neue_rate_gilt_ab_dem_naechsten_frame(self):
        """★★★ Die wichtigere Haelfte. Ein Anker, der die Position einfach
        festhaelt, wuerde jeden Stetigkeits-Test bestehen und das Feature
        zerstoeren. Bei 120 BPM sind das 2 Beats je Sekunde: mit ×1,25 muessen
        in einer Sekunde 2,5 Beats vergehen, vorher waren es 2,0."""
        for name, bauer in self.alle():
            with self.subTest(klasse=name):
                o, _v, nach_wechsel = self._wechsel(bauer, "direkt", faktor=1.25)
                self.vor(1.0)
                self.assertAlmostEqual(self.local(o) - nach_wechsel, 2.5, places=6,
                                       msg="die neue Rate greift nicht")

    def test_ohne_wechsel_laeuft_es_mit_der_alten_rate(self):
        """Positivkontrolle zur Zeile darueber: 2,0 statt 2,5."""
        o = self.efx()
        self.vor(3.1)
        vorher = self.local(o)
        self.vor(1.0)
        self.assertAlmostEqual(self.local(o) - vorher, 2.0, places=6)

    def test_der_ziel_step_bleibt_und_burstet_nicht(self):
        """★★ Fuer Chaser/Sequence ist die sichtbare Groesse der Step. Der alte
        F5-Fix hielt ihn ueber ``_step_idx`` — aber nur ueber ``set_param``;
        ueber den Editor-Weg gab es einen Burst."""
        for name, bauer in (("Chaser", self.chaser), ("Sequence", self.sequence)):
            for weg in ("set_param", "direkt"):
                with self.subTest(klasse=name, weg=weg):
                    o, vorher, nachher = self._wechsel(bauer, weg, faktor=2.0)
                    per = float(o.beats_per_step or 1)
                    self.assertEqual(int(round(nachher / per, 9)),
                                     int(round(vorher / per, 9)),
                                     "der Ziel-Step ist gesprungen")

    def test_auch_der_bruchteil_im_laufenden_schritt_bleibt(self):
        """★ Was der alte F5-Fix zusaetzlich wegwarf: er ankerte auf
        ``bus.position()``, der angefangene Schritt begann also von vorn. Der
        Step blieb sichtbar stehen, das TIMING des naechsten Wechsels nicht."""
        o, vorher, nachher = self._wechsel(self.chaser, "set_param", faktor=2.0)
        self.assertAlmostEqual(nachher % 1.0, vorher % 1.0, places=9)


class WasSichNichtAendernDarfTest(_Basis):
    """Die Zaeune um den Fix herum."""

    def test_phase_offset_verschiebt_weiterhin(self):
        """★★★ Der bewusst NICHT behobene Nachbar. ``phase_offset`` ist der
        Regler, der die Phase verschieben SOLL — ihn „stetig" zu machen hiesse,
        ihn wirkungslos zu machen. Stetig gehoert die RATE, nicht der Versatz.
        Dieser Test steht hier, damit ein spaeterer „Vereinheitlicher" ihn nicht
        aus Symmetrie mit in die Property zieht."""
        for name, bauer in self.alle():
            with self.subTest(klasse=name):
                o = bauer()
                self.vor(3.1)
                vorher = self.local(o)
                o.phase_offset = 0.25
                self.assertAlmostEqual(self.local(o) - vorher, 0.25, places=9,
                                       msg="der Versatz-Regler tut nichts mehr")

    def test_free_run_bleibt_unberuehrt(self):
        """Ohne Bus wirkt der Multiplier im Bus-Pfad gar nicht — dann darf auch
        kein Anker angefasst werden."""
        for name, bauer in self.alle():
            with self.subTest(klasse=name):
                o = bauer()
                o.tempo_bus_id = ""
                o._beat_anchor = 42.0
                o.tempo_multiplier = 3.0
                self.assertEqual(o._beat_anchor, 42.0)

    def test_ein_nicht_laufender_effekt_wird_nicht_umgeankert(self):
        """★★ Der Show-Ladepfad. ``from_dict`` setzt ``tempo_multiplier``, und
        ein Anker, der beim LADEN aus einem gerade laufenden Bus abgeleitet
        wird, waere frei erfunden — der Effekt hat noch keine Phase. ``start()``
        ankert ihn ohnehin."""
        for name, bauer in self.alle():
            with self.subTest(klasse=name):
                o = bauer()
                o._running = False
                o._beat_anchor = 7.0
                self.vor(1.0)
                o.tempo_multiplier = 2.0
                self.assertEqual(o._beat_anchor, 7.0)

    def test_ein_faktor_von_null_friert_nicht_ein(self):
        """F7-Parity: die Leser behandeln ``<= 0`` als 1.0, statt stehenzu-
        bleiben. Die Umankerung waere dort eine Division durch Null — sie muss
        sich heraushalten, nicht abstuerzen."""
        o = self.efx()
        self.vor(3.1)
        anker = o._beat_anchor
        o.tempo_multiplier = 0.0
        self.assertEqual(o._beat_anchor, anker)
        self.assertEqual(o.tempo_multiplier, 0.0)

    def test_ein_kaputter_ALTER_faktor_wird_wie_beim_lesen_behandelt(self):
        """★ F7-Parity in der anderen Richtung. Ein aus einer Alt-Show geladener
        Faktor ``<= 0`` umgeht den Clamp von ``set_param``; die LESER behandeln
        ihn als 1.0. Wer beim Umankern mit der 0 rechnet, wirft die ganze
        gelaufene Distanz weg — die Umankerung muss dieselbe Annahme treffen wie
        der Leser, sonst springt es genau beim Reparieren des Wertes."""
        o = self.efx()
        o._tempo_multiplier = 0.0            # am Setter vorbei, wie beim Laden
        self.vor(3.1)
        vorher = self.local(o)               # local() liest ``or 1.0`` — wie der Leser
        o.tempo_multiplier = 2.0
        self.assertAlmostEqual(self.local(o), vorher, places=9,
                               msg="das Reparieren eines kaputten Faktors springt")

    def test_ein_NEGATIVER_alter_faktor_wird_nicht_geraten(self):
        """★★ Die ehrliche Luecke, als Test festgehalten. Einen negativen
        Altwert lesen die beiden Familien UNTERSCHIEDLICH — EFX/Matrix ueber
        ``or 1.0`` (laesst -2 stehen), Chaser/Sequence ueber ``<= 0 -> 1.0``.
        Ohne eindeutige Vorgeschichte gibt es keine Phase zu erhalten; dann darf
        die Regel keine erfinden, sondern muss sich heraushalten."""
        o = self.efx()
        self.vor(3.1)
        o._tempo_multiplier = -2.0
        anker = o._beat_anchor
        o.tempo_multiplier = 2.0
        self.assertEqual(o._beat_anchor, anker,
                         "aus einem uneindeutigen Altzustand wurde ein Anker "
                         "geraten")

    def test_muell_aendert_weder_wert_noch_anker(self):
        o = self.efx()
        self.vor(3.1)
        anker, wert = o._beat_anchor, o.tempo_multiplier
        o.tempo_multiplier = "schnell"
        self.assertEqual((o._beat_anchor, o.tempo_multiplier), (anker, wert))

    def test_der_wert_ueberlebt_speichern_und_laden(self):
        """Die Property darf die Serialisierung nicht verlieren — ``to_dict``
        liest ueber den Getter, ``from_dict`` schreibt ueber den Setter."""
        o = self.efx()
        o.tempo_multiplier = 2.5
        self.assertEqual(o.to_dict().get("tempo_multiplier"), 2.5)

    def test_gleicher_wert_ist_trotzdem_kein_sprung(self):
        """Ein Editor, der bei jedem Fokuswechsel denselben Wert zurueck-
        schreibt, darf nichts anrichten."""
        o = self.efx()
        self.vor(3.1)
        vorher = self.local(o)
        for _ in range(5):
            o.tempo_multiplier = o.tempo_multiplier
        self.assertAlmostEqual(self.local(o), vorher, places=9)


class DieRegelStehtNurEinmalTest(unittest.TestCase):
    """★★ Review-Checkliste 17. Vier Klassen, eine Formel — und vorher zwei
    verschiedene Antworten darauf (``_reanchor_bus_target`` bei Chaser/Sequence,
    gar nichts bei EFX/Matrix)."""

    def test_es_gibt_keinen_zweiten_re_anker_mehr(self):
        import inspect
        from src.core.engine import chaser, sequence
        for modul in (chaser, sequence):
            with self.subTest(modul=modul.__name__):
                quelle = inspect.getsource(modul)
                self.assertNotIn("def _reanchor_bus_target", quelle,
                                 "der zweite Re-Anker ist zurueck — dann "
                                 "beantworten wieder zwei Stellen dieselbe Frage")

    def test_die_regel_haengt_an_der_zuweisung(self):
        from src.core.engine.function import Function
        self.assertIsInstance(Function.tempo_multiplier, property,
                              "ohne Property sieht die Regel den Editor-Weg "
                              "nicht — und genau der ist der haeufigere")


if __name__ == "__main__":
    unittest.main()
