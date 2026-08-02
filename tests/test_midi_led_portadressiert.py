"""MIDI-LED-AUX — die APC-LEDs haengen nicht mehr daran, was die MIDI-Ansicht
gerade anzeigt.

**Gemessen vor dem Umbau** (beide APC-Treiber, gleiche Kette):

1. LED gesetzt, waehrend der geteilte Ausgang auf den APC zeigt → Note geht raus.
2. Jemand waehlt in der MIDI-Ansicht ein anderes Geraet → **keine Note mehr**,
   ohne Fehler und ohne Meldung. Die Knoepfe bleiben einfach stehen.
3. Zurueck auf den APC, derselbe Wunsch nochmal → **immer noch keine Note.**

Punkt 3 ist der eigentliche Schaden und stand so nicht im Backlog: der
Diff-Cache merkte sich in Schritt 2 den Wunschwert, obwohl nichts gesendet
wurde. Danach gilt die LED als "steht schon richtig" — und nur ein *anderer*
Wert wuerde je wieder senden. Aus einem voruebergehenden Aussetzer wird ein
**dauerhaft falsches Pult**.

Dazu kam eine zweite, stille Verweigerung: startete der Treiber, waehrend ein
fremder Ausgang offen war, gab er ganz auf ("LED-Feedback bleibt aus") — sichtbar
nur auf der Konsole.

Beides faellt weg, wenn die Note ihr **Ziel beim Namen nennt**
(``MidiManager.send_message_to``, MIDI-OUT-MULTI): sie kann das fremde Geraet
gar nicht erreichen, also gibt es nichts mehr zu sperren. Der geteilte Ausgang
bleibt dabei unangetastet — er gehoert weiterhin der MIDI-Ansicht.

Die Tests pruefen deshalb immer **zwei Dinge zugleich**: dass gesendet wurde
UND wohin. Nur "es ging etwas raus" waere hier die gefaehrlichere Zusicherung —
genau davor schuetzte die alte Sperre.
"""
from __future__ import annotations

import unittest


class _FakeManager:
    """MidiManager-Ersatz, der Haupt- und portadressierten Weg auseinanderhaelt."""

    def __init__(self, ports, current="", to_ok=True):
        self._ports = list(ports)
        self._current = current
        self._to_ok = to_ok
        self.geteilt: list[tuple] = []          # ueber den gemeinsamen Ausgang
        self.an_port: list[tuple[str, tuple]] = []   # portadressiert
        self.open_calls: list[str] = []
        self.aux_freigegeben: list[str] = []

    def list_outputs(self):
        return list(self._ports)

    def current_output_name(self):
        return self._current

    def open_output(self, name, **_kw):
        self.open_calls.append(name)
        self._current = name
        return True

    def send_message(self, msg):
        self.geteilt.append(tuple(msg))
        return True

    def send_message_to(self, port, msg):
        if not self._to_ok:
            return False
        self.an_port.append((str(port), tuple(msg)))
        return True

    def close_aux_output(self, port):
        self.aux_freigegeben.append(str(port))


class _Basis:
    """Beide Treiber haben dieselbe Kopplung — also dieselben Pruefungen.

    Unterklassen liefern ``_bau`` und ``_setze(fb, index, wert)``; letzteres
    kapselt set_led vs. set_pad.
    """

    PORT = "APC mini mk2"

    def _bau(self, mgr):                      # pragma: no cover — Unterklasse
        raise NotImplementedError

    def _setze(self, fb, i, wert):            # pragma: no cover — Unterklasse
        raise NotImplementedError

    # ── 1. Der gemessene Kern ────────────────────────────────────────────────

    def test_led_laeuft_nach_dem_umschalten_weiter(self):
        mgr = _FakeManager([self.PORT, "Anderes Pult"], current="")
        fb = self._bau(mgr)
        self._setze(fb, 3, 1)
        self.assertEqual(len(mgr.an_port), 1)

        mgr._current = "Anderes Pult"          # MIDI-Ansicht schaltet um
        self._setze(fb, 4, 2)
        self.assertEqual(len(mgr.an_port), 2,
                         "Feedback verstummte nach dem Umschalten")
        self.assertTrue(all(p == self.PORT for p, _m in mgr.an_port),
                        f"Note ging an ein fremdes Geraet: {mgr.an_port}")
        self.assertEqual(mgr.geteilt, [],
                         "Note lief ueber den geteilten Ausgang statt adressiert")

    def test_gescheiterter_versuch_vergiftet_den_cache_nicht(self):
        """Der eigentliche Schaden von vorher: ein nicht gesendeter Wert galt
        trotzdem als gesetzt, und derselbe Wunsch wurde nie wiederholt."""
        mgr = _FakeManager([self.PORT], current="", to_ok=False)
        fb = self._bau(mgr)
        self._setze(fb, 3, 1)
        self.assertEqual(mgr.an_port, [], "Vorbedingung: Senden schlaegt fehl")

        mgr._to_ok = True                      # Port wieder erreichbar
        self._setze(fb, 3, 1)                  # GENAU derselbe Wunsch
        self.assertEqual(len(mgr.an_port), 1,
                         "Wunsch galt als erledigt, obwohl nie gesendet wurde")

    def test_wiederholung_ohne_aenderung_sendet_nicht_doppelt(self):
        """Gegenprobe zum vorigen Test: der Diff-Cache muss weiter greifen,
        sonst ist die 'Reparatur' nur ein abgeschaltetes Diff-Update."""
        mgr = _FakeManager([self.PORT], current="")
        fb = self._bau(mgr)
        self._setze(fb, 3, 1)
        self._setze(fb, 3, 1)
        self.assertEqual(len(mgr.an_port), 1, "Diff-Update greift nicht mehr")

    # ── 2. Der fremde Ausgang bleibt fremd ───────────────────────────────────

    def test_startet_auch_bei_belegtem_ausgang_und_reisst_ihn_nicht_weg(self):
        mgr = _FakeManager([self.PORT, "Anderes Pult"], current="Anderes Pult")
        fb = self._bau(mgr)
        self.assertTrue(fb.is_connected,
                        "Treiber gab bei belegtem Ausgang still auf")
        self.assertEqual(mgr.open_calls, [], "fremder Ausgang wurde uebernommen")
        self.assertEqual(mgr.current_output_name(), "Anderes Pult")

        self._setze(fb, 3, 1)
        self.assertEqual([p for p, _m in mgr.an_port], [self.PORT])
        self.assertEqual(mgr.geteilt, [])

    def test_freier_ausgang_wird_weiterhin_uebernommen(self):
        """Ist niemand dran, soll der APC der gemeinsame Ausgang werden — das
        spart den Zweit-Client, den `send_message_to` sonst haelt."""
        mgr = _FakeManager([self.PORT], current="")
        self._bau(mgr)
        self.assertEqual(mgr.open_calls, [self.PORT])

    # ── 3. Aufraeumen ────────────────────────────────────────────────────────

    def test_close_gibt_den_zweit_ausgang_frei(self):
        mgr = _FakeManager([self.PORT, "Anderes Pult"], current="Anderes Pult")
        fb = self._bau(mgr)
        fb.close()
        self.assertIn(self.PORT, mgr.aux_freigegeben,
                      "Zweit-Handle blieb bis zum Prozessende offen")


class MiniTest(_Basis, unittest.TestCase):
    def setUp(self):
        self._patches = []

    def _bau(self, mgr):
        from unittest import mock
        from src.core.midi import apc_mini_feedback as mod
        p1 = mock.patch.object(mod, "_RTMIDI", True)
        p2 = mock.patch("src.core.midi.midi_manager.get_midi_manager",
                        lambda: mgr)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)
        fb = mod.APCMiniFeedback(port_hint="APC")
        self.addCleanup(lambda: setattr(mod, "_instance", None))
        return fb

    def _setze(self, fb, i, wert):
        fb.set_led(i, wert)


class Mk2Test(_Basis, unittest.TestCase):
    def _bau(self, mgr):
        from unittest import mock
        from src.core.midi import apc_mk2_feedback as mod
        p1 = mock.patch.object(mod, "_RTMIDI", True)
        p2 = mock.patch("src.core.midi.midi_manager.get_midi_manager",
                        lambda: mgr)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)
        # canvas=None: der Update-Loop wird hier nie gestartet, geprueft
        # wird allein der Sendeweg.
        return mod.ApcMk2Feedback(None)

    def _setze(self, fb, i, wert):
        fb.set_pad(i, wert)


if __name__ == "__main__":
    unittest.main()
