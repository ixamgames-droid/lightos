"""ENG-23: aus dem Per-Effekt-„Einfrieren" fuehrte nur genau EIN Knopf heraus.

Der globale Freeze (F3) haelt alles an, indem er die Tempo-Buses auf 0 BPM
setzt. Der **Per-Effekt**-Freeze haelt nur einen Effekt an — und der war eine
Falle, gleich dreifach:

1. **Aus- und Wiedereinschalten half nicht.** ``_frozen`` ueberlebte
   ``stop() + start()``. Weil ``_on_start`` gleichzeitig ``_step = 0.0`` setzt,
   klemmte der Effekt danach auf Frame 0 (gemessen: Vollrot 255/0/0). Aus- und
   Wiedereinschalten ist der Griff, zu dem jeder greift, wenn etwas haengt.
2. **Es gab keinen absoluten Ausweg in der UI.** ``freeze``/``unfreeze``
   existierten im Code (``rgb_matrix.do_action``), standen aber in **keiner**
   Aktionsliste und waren nur ueber das Freitextfeld des Mehrfach-Aktions-
   Dialogs erreichbar. Sichtbar war ausschliesslich der Toggle.
3. **Der Knopf zeigte den Zustand nicht.** ``paintEvent`` wertete ``action_on``
   nur fuer ``ButtonAction.FREEZE`` aus (VCI-01), nicht fuer die Effekt-Aktion.
   Ein eingefrorener Effekt sah aus wie ein langsamer.

★★ **Das Backlog-Kriterium war falsch adressiert.** Es lautete „fertig, wenn ein
Neustart des Effekts den Freeze aufhebt" — eine Matrix hat aber gar keinen
Neustart (``do_action("restart") -> False``, ``restart`` steht nicht in
``list_actions()``), und ``stop()+start()`` hob ihn nicht auf, sondern setzte
zusaetzlich ``_step = 0.0``.

⚠️ **Und es gab einen zweiten Weg, der das Item neu einordnet:** ``_frozen`` gab
es NUR in ``rgb_matrix.py``. ``efx.py`` und ``chaser.py`` kannten ausschliesslich
den globalen ``_tbm.is_frozen()``, ``sequence.py`` hatte nicht einmal eine
Aktionsliste. Die VC bot „Einfrieren an/aus" trotzdem als allgemeine
Effekt-Aktion an — **auf einem Chaser tat der Knopf stumm gar nichts.**
Ein Bedienelement, das nur manchmal wirkt, ist schlimmer als eines, das fehlt.

★★★ **Beim Nachmessen kam ein vierter Punkt dazu, den der Eintrag nicht kannte:**
das Auftauen eines bus-synchronen Effekts SPRANG um genau die eingefrorene Zeit
(gemessen bei 120 BPM, 2 s Freeze: ``_step`` 2,0000 → gehalten 2,0000 →
**6,0000**). Ein Freeze, aus dem man nicht ohne Sprung herauskommt, ist nur halb
behoben. Die Rechnung dafuer ist dieselbe wie bei ENG-21, nur mit einem
festgehaltenen statt einem umgerechneten ``local``.
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

BPM = 120.0          # 2 Beats je Sekunde — jede Zahl unten von Hand nachrechenbar
FRAME = 0.02


class _Basis(unittest.TestCase):

    def setUp(self):
        # DENSELBEN Zugriff wie die Engine: ensure_bus("Global") liefert einen
        # ANDEREN Bus als get("Global") — siehe ENG-26.
        self.bus = get_tempo_bus_manager().get("Global")
        self.assertIsNotNone(self.bus, "Vorbedingung: der Default-Bus existiert")
        self.bus.set_bpm(BPM)

    def vor(self, sekunden: float):
        for _ in range(int(round(sekunden / FRAME))):
            self.bus.advance_frame(FRAME)

    def alle(self):
        """Die vier zeitbasierten Typen, jeweils lauffaehig."""
        c = Chaser(name="C")
        c.steps = [ChaserStep(function_id=i) for i in range(4)]
        s = Sequence(name="S")
        s.steps = [SequenceStep() for _ in range(4)]
        m = RgbMatrixInstance(name="M")
        m.cols, m.rows = 4, 1
        return (("Matrix", m), ("EFX", EfxInstance(name="E")),
                ("Chaser", c), ("Sequence", s))


class DerFreezeHatEinenAuswegTest(_Basis):

    def test_aus_und_wieder_einschalten_hebt_den_freeze_auf(self):
        """★★★ Punkt 1. Der Griff, zu dem jeder greift, wenn etwas haengt."""
        for name, o in self.alle():
            with self.subTest(klasse=name):
                o.start()
                o.do_action("freeze")
                self.assertTrue(o._frozen, "Vorbedingung: eingefroren")
                o.stop()
                o.start()
                self.assertFalse(o._frozen,
                                 "der Freeze ueberlebt das Wiedereinschalten — "
                                 "und der Effekt klemmt auf Frame 0")

    def test_es_gibt_eine_absolute_aktion_in_beide_richtungen(self):
        """★★ Punkt 2. Ein reiner Toggle ist ein Zustand, den nur er selbst
        wieder aufhebt. ``freeze``/``unfreeze`` sagen, WAS danach gilt — das ist
        auch die richtige Form fuer einen Szenenabruf."""
        for name, o in self.alle():
            with self.subTest(klasse=name):
                keys = [k for k, _ in o.list_actions()]
                for k in ("freeze", "unfreeze", "toggle_freeze"):
                    self.assertIn(k, keys, f"{k} fehlt in list_actions()")

    def test_die_absoluten_aktionen_sind_wirklich_absolut(self):
        """Zweimal ``freeze`` friert ein und bleibt eingefroren — ein Toggle
        haette beim zweiten Druck aufgetaut."""
        for name, o in self.alle():
            with self.subTest(klasse=name):
                o.start()
                o.do_action("freeze"); o.do_action("freeze")
                self.assertTrue(o._frozen)
                o.do_action("unfreeze"); o.do_action("unfreeze")
                self.assertFalse(o._frozen)

    def test_der_knopf_wirkt_auf_ALLEN_vier_typen(self):
        """★★★ Der zweite Weg, und der eigentliche Umfang des Items: ``_frozen``
        gab es nur in der Matrix. Auf Chaser, EFX und Sequenz lieferte
        ``do_action("toggle_freeze")`` schlicht ``False`` — der VC-Knopf tat
        stumm nichts."""
        for name, o in self.alle():
            with self.subTest(klasse=name):
                self.assertTrue(o.do_action("toggle_freeze"),
                                "die Aktion wird gar nicht angenommen")
                self.assertTrue(o._frozen)


class EingefrorenHeisstStEHEN_nichtWEG(_Basis):
    """★★ Die wichtigste Gegenprobe: ein Freeze, der die Ausgabe abschaltet,
    haette jeden „steht still"-Test bestanden und waere ein Blackout."""

    def test_die_matrix_gibt_eingefroren_weiter_aus(self):
        m = RgbMatrixInstance(name="M")
        m.cols, m.rows = 4, 1
        m.start()
        m._advance_step(FRAME)
        vorher = m._step
        m.do_action("freeze")
        for _ in range(10):
            m._advance_step(FRAME)
        self.assertEqual(m._step, vorher, "die Animation laeuft weiter")
        self.assertTrue(m._running, "der Effekt wurde gestoppt statt angehalten")

    def test_der_efx_haelt_seine_phase(self):
        e = EfxInstance(name="E")
        e.tempo_bus_id = ""          # Free-Run: die Phase kommt aus dt
        e.start()
        e._advance(0.5)
        phase = e._phase
        self.assertGreater(phase, 0.0, "Vorbedingung: die Phase ist gelaufen")
        e.do_action("freeze")
        for _ in range(10):
            e._advance(0.5)
        self.assertEqual(e._phase, phase)

    def test_die_sequenz_haelt_ihren_schritt(self):
        """★★ Der Test muss die Sequenz WIRKLICH laufen lassen, bevor er
        einfriert. Seine erste Fassung fragte ``_bus_steps_to_advance()`` auf
        einer frischen Sequenz — dort ist ``_synced_target_prev`` noch ``None``,
        und die Methode liefert **auch ohne Freeze** 0 (Erst-Sync). Sie haette
        also selbst dann bestanden, wenn der Freeze gar nichts taete; die
        Mutationsprobe hat das aufgedeckt."""
        s = Sequence(name="S")
        s.steps = [SequenceStep() for _ in range(4)]
        s.beats_per_step = 1.0
        s.start()
        s._beat_anchor = self.bus.position()
        s._synced_target_prev = None
        s._bus_steps_to_advance()              # Erst-Sync: prev steht jetzt
        self.vor(2.0)                          # 4 Beats
        self.assertGreater(s._bus_steps_to_advance(), 0,
                           "Vorbedingung: ohne Freeze wuerde sie schalten")
        self.vor(2.0)
        s.do_action("freeze")
        self.vor(2.0)
        self.assertEqual(s._bus_steps_to_advance(), 0,
                         "eine eingefrorene Sequenz schaltet weiter")

    def test_die_sequenz_haelt_auch_ohne_bus(self):
        """Der Zeit-Pfad: ohne Bus treibt ``dt`` den Schritt. Eingefroren heisst
        dort „keine Zeit vergeht"."""
        s = Sequence(name="S")
        s.steps = [SequenceStep() for _ in range(4)]
        s.tempo_bus_id = ""
        s.start()
        s.write({}, [], 0.1)
        gelaufen = s._step_elapsed
        self.assertGreater(gelaufen, 0.0, "Vorbedingung: die Zeit laeuft")
        s.do_action("freeze")
        for _ in range(20):
            s.write({}, [], 0.1)
        self.assertEqual(s._step_elapsed, gelaufen,
                         "die eingefrorene Sequenz laeuft im Zeit-Pfad weiter")

    def test_der_chaser_schaltet_eingefroren_nicht_weiter(self):
        """★★★ Der Test muss den CHASER-PFAD betreten, nicht nur die
        Anker-Rechnung nachbilden. Seine erste Fassung rechnete den Ziel-Step
        selbst aus und haette den Halt in ``_advance_from_bus`` gar nicht
        bemerkt — eine Probe, die ihren Gegenstand nicht erreicht, meldet
        „alles gut". Von der Mutationsprobe aufgedeckt."""
        c = Chaser(name="C")
        c.steps = [ChaserStep(function_id=i) for i in range(8)]
        c.beats_per_step = 1.0
        c.start()
        c._beat_anchor = self.bus.position()
        c._synced_target_prev = None
        c._advance_from_bus({}, [], None, FRAME)      # Erst-Sync
        self.vor(1.5)                                 # 3 Beats
        c._advance_from_bus({}, [], None, FRAME)
        gelaufen = c._step_idx
        self.assertNotEqual(gelaufen, 0, "Vorbedingung: der Chaser ist gelaufen")

        c.do_action("freeze")
        self.vor(2.0)                                 # 4 weitere Beats
        c._advance_from_bus({}, [], None, FRAME)
        self.assertEqual(c._step_idx, gelaufen,
                         "der eingefrorene Chaser schaltet weiter")

        c.do_action("unfreeze")
        c._advance_from_bus({}, [], None, FRAME)
        self.assertEqual(c._step_idx, gelaufen,
                         "beim Auftauen holt er die eingefrorene Zeit nach")

    def test_der_chaser_haelt_auch_ohne_bus(self):
        """Der Zeit-/Audio-Pfad."""
        c = Chaser(name="C")
        c.steps = [ChaserStep(function_id=i) for i in range(8)]
        c.tempo_bus_id = ""
        c.start()
        c.write({}, [], 0.1)
        gelaufen = c._step_elapsed
        self.assertGreater(gelaufen, 0.0, "Vorbedingung: die Zeit laeuft")
        c.do_action("freeze")
        for _ in range(20):
            c.write({}, [], 0.1)
        self.assertEqual(c._step_elapsed, gelaufen,
                         "der eingefrorene Chaser laeuft im Zeit-Pfad weiter")


class AuftauenSpringtNichtTest(_Basis):
    """★★★ Der Punkt, den der Backlog-Eintrag nicht kannte."""

    def _bus_matrix(self):
        m = RgbMatrixInstance(name="M")
        m.cols, m.rows = 4, 1
        m.tempo_bus_id = "Global"
        m.start()
        m._beat_anchor = self.bus.position()
        return m

    def test_das_auftauen_setzt_dort_fort_wo_eingefroren_wurde(self):
        m = self._bus_matrix()
        self.vor(1.0)
        m._advance_step(FRAME)
        vorher = m._step
        self.assertGreater(vorher, 0.0, "Vorbedingung: der Effekt ist gelaufen")
        m.do_action("freeze")
        self.vor(2.0)                      # 4 Beats vergehen am Bus
        m._advance_step(FRAME)
        self.assertEqual(m._step, vorher, "Vorbedingung: gehalten")
        m.do_action("unfreeze")
        m._advance_step(FRAME)
        self.assertAlmostEqual(m._step, vorher, places=9,
                               msg="das Auftauen springt um die eingefrorene Zeit")

    def test_danach_laeuft_es_mit_der_richtigen_rate_weiter(self):
        """Die Gegenprobe: der Anker darf nicht so gesetzt werden, dass der
        Effekt danach steht — 1 s bei 120 BPM sind 2 Beats."""
        m = self._bus_matrix()
        self.vor(1.0); m._advance_step(FRAME)
        m.do_action("freeze"); self.vor(2.0); m._advance_step(FRAME)
        m.do_action("unfreeze"); m._advance_step(FRAME)
        nach_auftauen = m._step
        self.vor(1.0); m._advance_step(FRAME)
        self.assertAlmostEqual(m._step - nach_auftauen, 2.0, places=6)

    def test_ein_chaser_holt_die_eingefrorene_zeit_nicht_nach(self):
        """★★ Fuer Chaser/Sequence waere der Sprung ein Step-BURST: die
        waehrend des Freeze vergangenen Beats auf einmal, in einem Frame."""
        c = Chaser(name="C")
        c.steps = [ChaserStep(function_id=i) for i in range(8)]
        c.beats_per_step = 1.0
        c.tempo_bus_id = "Global"
        c.start()
        c._beat_anchor = self.bus.position()
        c._synced_target_prev = None
        self.vor(1.0)

        def ziel():
            pos = self.bus.position()
            return int(round(((pos - c._beat_anchor) * c.tempo_multiplier
                              + c.phase_offset) / c.beats_per_step, 9))

        vorher = ziel()
        c.do_action("freeze")
        self.vor(3.0)                      # 6 Beats = 6 Schritte
        c.do_action("unfreeze")
        self.assertEqual(ziel(), vorher,
                         "der Chaser holt die eingefrorene Zeit in einem Frame nach")

    def test_ein_zweites_freeze_verschiebt_den_haltepunkt_nicht(self):
        """``freeze`` auf einem bereits eingefrorenen Effekt darf die gemerkte
        Position nicht ueberschreiben — sonst wandert der Haltepunkt mit dem Bus."""
        m = self._bus_matrix()
        self.vor(1.0); m._advance_step(FRAME)
        vorher = m._step
        m.do_action("freeze")
        self.vor(2.0)
        m.do_action("freeze")              # zweites Mal
        self.vor(1.0)
        m.do_action("unfreeze"); m._advance_step(FRAME)
        self.assertAlmostEqual(m._step, vorher, places=9)

    def test_free_run_braucht_keinen_anker(self):
        """Ohne Bus rechnet der Effekt aus ``dt`` — dort gibt es nichts
        nachzuziehen, und es darf auch nichts angefasst werden.

        ⚠️ ``tempo_bus_id`` muss dafuer AUSDRUECKLICH geleert werden: alle vier
        Typen tragen ``tempo_sync_default = True`` und stehen damit von Haus aus
        auf „Global". Der Free-Run ist die Ausnahme, nicht der Normalfall — das
        hat dieser Test beim ersten Lauf selbst aufgedeckt (Anker 42,0 → 46,0,
        weil die Matrix eben doch am Bus hing)."""
        m = RgbMatrixInstance(name="M")
        m.cols, m.rows = 4, 1
        m.tempo_bus_id = ""
        m.start()
        m._beat_anchor = 42.0
        m.do_action("freeze")
        self.vor(2.0)
        m.do_action("unfreeze")
        self.assertEqual(m._beat_anchor, 42.0)


class DerFreezeUeberlebtDieShowDateiNichtTest(_Basis):
    """★★ Die Gegenrichtung zu „es gibt einen Ausweg": ein Freeze darf gar nicht
    erst in einer gespeicherten Show landen. Sonst startete die Show mit einem
    stehenden Effekt, und der Bediener suchte einen Zustand, den er nie gesetzt
    hat — die Falle, nur eine Sitzung spaeter."""

    def test_der_freeze_wird_nicht_gespeichert(self):
        for name, o in self.alle():
            with self.subTest(klasse=name):
                o.start()
                o.do_action("freeze")
                self.assertNotIn("_frozen", o.to_dict())
                self.assertNotIn("frozen", o.to_dict())

    def test_ein_geladener_effekt_laeuft(self):
        """★★ Ueber den Weg, den eine SHOW nimmt: ``FunctionManager.from_dict``.

        Die erste Fassung rief ``type(o).from_dict(...)`` — die Klassen-Methode.
        Die generischen Felder (``tempo_bus_id``, ``tempo_multiplier``, …) setzt
        aber der **FunctionManager** nach dem Bau des Objekts
        (``function_manager.py:612``), und genau dort waere ein neu
        hinzugefuegtes ``_frozen`` gelandet. Die Mutationsprobe hat gezeigt,
        dass der Test diesen Weg gar nicht betrat: ein ``f._frozen = ...`` an
        jener Stelle blieb unbemerkt. Wieder dieselbe Klasse — eine Probe, die
        ihren Gegenstand nicht erreicht, meldet „alles gut"."""
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        for name, o in self.alle():
            with self.subTest(klasse=name):
                o.start()
                o.do_action("freeze")
                d = o.to_dict()
                d["_frozen"] = True        # als waere er doch gespeichert worden
                fm.from_dict({"functions": [d]})
                self.addCleanup(lambda: fm.from_dict({"functions": []}))
                geladen = list(fm.all())[0] if hasattr(fm, "all") else None
                if geladen is None:
                    geladen = list(fm._functions.values())[0]
                self.assertFalse(geladen._frozen,
                                 "der Freeze kam aus der Show-Datei zurueck")


class DieUiKenntDenZustandTest(unittest.TestCase):

    def test_die_absoluten_aktionen_stehen_in_der_vc_liste(self):
        """★★ Punkt 2 auf der UI-Seite. Sie existierten im Code und waren nur
        ueber ein Freitextfeld erreichbar."""
        from src.ui.virtualconsole.vc_button import EFFECT_ACTION_LABELS
        keys = [k for k, _ in EFFECT_ACTION_LABELS]
        for k in ("freeze", "unfreeze", "toggle_freeze"):
            self.assertIn(k, keys)

    def test_die_kuratierte_liste_verspricht_nichts_unmoegliches(self):
        """★★★ Der Grund, aus dem der zweite Weg ueberhaupt entstand: die VC
        bietet ``EFFECT_ACTION_LABELS`` unabhaengig vom Ziel an. Was dort steht,
        muss jeder zeitbasierte Effekt auch KOENNEN — sonst ist es ein Knopf,
        der manchmal nichts tut."""
        from src.ui.virtualconsole.vc_button import EFFECT_ACTION_LABELS
        from src.core.engine.function import Function
        angeboten = {k for k, _ in EFFECT_ACTION_LABELS}
        basis = {k for k, _ in Function.FREEZE_ACTIONS}
        self.assertTrue(basis <= angeboten,
                        "die Basis kann etwas, das die VC nicht anbietet")
        for k in basis:
            self.assertTrue(Function().do_action(k),
                            f"{k} wird von der Basisklasse nicht angenommen")

    def _knopf(self, key: str, effekt):
        """Die Anzeige-Regel ohne Widget und ohne Datenbank befragen.

        ★ ``_aktionszustand`` haengt an genau drei Dingen: ``action``,
        ``effect_action_key`` und den gebundenen Funktions-IDs. Ein echter
        ``VCButton`` zoege MIDI-Threads und die Fixture-DB nach sich — und ein
        ``repaint()`` auf einem elternlosen Widget hat headless den Renderer
        mitgerissen. Deshalb wird die Methode ungebunden auf einem Doppel
        aufgerufen; geprueft wird die REGEL, nicht Qt.
        """
        from unittest import mock
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction

        class _Attrappe:
            action = ButtonAction.EFFECT_ACTION
            effect_action_key = key

            def _all_function_ids(self):
                return [7]

        class _FM:
            def get(self, fid):
                return effekt if fid == 7 else None

        with mock.patch("src.core.engine.function_manager.get_function_manager",
                        lambda: _FM()):
            return VCButton._aktionszustand(_Attrappe())

    def test_der_knopf_zeigt_den_eingefrorenen_zustand(self):
        """★★ Punkt 3. Ein eingefrorener Effekt sah aus wie ein langsamer — und
        der Bediener suchte den Fehler im Rig."""
        m = RgbMatrixInstance(name="ENG23")
        m._frozen = False
        self.assertFalse(self._knopf("toggle_freeze", m),
                         "der Knopf leuchtet, obwohl nichts steht")
        m._frozen = True
        self.assertTrue(self._knopf("toggle_freeze", m),
                        "ein eingefrorener Effekt bleibt unsichtbar")

    def test_auch_die_absoluten_aktionen_zeigen_den_zustand(self):
        m = RgbMatrixInstance(name="ENG23c")
        m._frozen = True
        for key in ("freeze", "unfreeze"):
            with self.subTest(aktion=key):
                self.assertTrue(self._knopf(key, m))

    def test_eine_andere_effekt_aktion_leuchtet_nicht(self):
        """Gegenprobe: die Anzeige darf nicht an JEDER Effekt-Aktion haengen."""
        m = RgbMatrixInstance(name="ENG23b")
        m._frozen = True
        self.assertFalse(self._knopf("next_color", m))


if __name__ == "__main__":
    unittest.main()
