"""STAB-28: der Freeze-Dump muss sagen, ob der Blockierer ueberhaupt in Python liegt.

**Der Befund (Crash-Intake 01.09.2026, Sitzung B).** In ``crash.log`` stehen 22
``UI-FREEZE``-Eintraege; die Standby-Erkennung filtert die grossen Luecken
zuverlaessig heraus, es bleiben 19 echte. Die **letzten drei** (06.08. 28 s,
07.08. 11 s, 07.08. 13 s) liegen nach den beiden bekannten Fixes und sehen
anders aus als alles davor.

Ihr Dump zeigt sechs Threads in ihren voellig normalen Warteschleifen —
``AudioCapture`` in ``numpy.fft``, ``DMX-Output`` im Sendeloop, ``MidiDispatch``
in ``queue.get`` — und den Hauptthread mit genau zwei Rahmen::

    Thread 0x00007658 [CrBrowserMain] (most recent call first):
      File "main.py", line 592 in main
      File "main.py", line 596 in <module>

Das ist der Einstieg in ``app.exec()`` und sonst nichts: der Hauptthread steckte
nicht in Python-Code, sondern in einem nativen Aufruf darunter. Dass er
``CrBrowserMain`` heisst, kommt daher, dass QtWebEngine/Chromium den OS-Thread
umbenennt, sobald es ihn uebernimmt.

★ **Der Schaden ist nicht, dass der Dump schweigt, sondern dass er in die
falsche Richtung zeigt.** Wer sechs Stacks mit Dateinamen aus ``src/`` liest,
sucht den Blockierer dort — und findet sechs gesunde Threads. Das ist die
teuerste Sorte Diagnose.

★★ **Berichtigung zur ersten Fassung des Items:** dort stand „gar kein
Python-Stack im Hauptthread". Am echten Log nachgesehen stimmt das nicht — es
gibt einen, er ist nur nichtssagend. Geprueft wird deshalb nicht die
*Abwesenheit* eines Stacks, sondern ob sein innerster Rahmen ueber den
Event-Loop-Einstieg hinausgeht.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from src.core import crash_logging as cl


#: Der Stack aus dem echten Log vom 07.08.2026, innerster Rahmen zuerst.
ECHTER_FREEZE_STACK = [
    ("C:\\...\\main.py", 592, "main"),
    ("C:\\...\\main.py", 596, "<module>"),
]


class HauptthreadBefundTest(unittest.TestCase):
    """Die reine Logik — ohne Qt, ohne faulthandler, ohne laufende App."""

    def test_der_echte_freeze_aus_dem_log_wird_als_nativ_erkannt(self):
        """★★ Der Fall, um den es geht — mit den Daten, die ihn ausgeloest haben."""
        text = cl.hauptthread_befund(ECHTER_FREEZE_STACK)
        self.assertIn("nativ", text.lower(),
                      "der Befund benennt den nativen Blockierer nicht: " + text)
        self.assertIn("592", text,
                      "der Befund nennt den Rahmen nicht, den der Leser unten "
                      "im Dump sieht: " + text)

    def test_er_warnt_ausdruecklich_vor_den_nebenthreads(self):
        """★ Ohne diese Warnung bleibt die Fehldeutung, gegen die STAB-28 steht.

        Ein Befund, der nur „nativ\" sagt, hindert niemanden daran, die sechs
        gesunden Stacks darunter fuer den Fund zu halten — genau das ist real
        passiert.
        """
        text = cl.hauptthread_befund(ECHTER_FREEZE_STACK)
        self.assertIn("KEIN Befund", text,
                      "die Nebenthreads werden nicht ausdruecklich "
                      "ausgeschlossen: " + text)

    def test_ein_freeze_IM_python_code_wird_unveraendert_gemeldet(self):
        """★ Die Positivkontrolle, die das Item verlangt.

        Der haeufigere Fall — der Hauptthread haengt wirklich in Python — muss
        weiterhin den Rahmen nennen, in dem er haengt. Ohne diesen Test waere
        „nie wieder in die falsche Richtung zeigen\" auch dadurch zu erreichen,
        dass der Befund gar nichts mehr aussagt.
        """
        stack = [
            ("C:\\...\\src\\ui\\views\\simple_desk.py", 812, "set_tint"),
            ("C:\\...\\main.py", 592, "main"),
            ("C:\\...\\main.py", 596, "<module>"),
        ]
        text = cl.hauptthread_befund(stack)
        self.assertIn("set_tint", text, text)
        self.assertIn("812", text, text)
        self.assertNotIn("nativ", text.lower(),
                         "ein Freeze IM Python-Code wird faelschlich als nativ "
                         "gemeldet: " + text)

    def test_ohne_jeden_rahmen_bleibt_es_ehrlich(self):
        """Kein Rahmen gefunden ist etwas anderes als „alles in Ordnung\"."""
        for leer in (None, []):
            text = cl.hauptthread_befund(leer)
            self.assertIn("KEIN Python-Rahmen", text, text)
            self.assertIn("nativ", text.lower(), text)


class BefundIstVerdrahtetTest(unittest.TestCase):
    """Der Befund muss ZWISCHEN Kopfzeile und Dump stehen.

    Die reine Logik oben kann noch so richtig sein — steht der Aufruf nicht an
    der richtigen Stelle, liest der Mensch den Dump wie bisher. Ein
    Verhaltenstest dafuer muesste einen echten Freeze der laufenden App
    herstellen; diese Pruefung am Quelltext ist das, was im Gate laufen kann
    (gleiche Bauart wie ``test_xplat31_anteils_schutz``).
    """

    def test_der_befund_steht_vor_dem_dump(self):
        import os
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(wurzel, "main.py"), encoding="utf-8") as f:
            quelle = f.read()
        for name in ("freeze_header", "hauptthread_befund", "dump_traceback"):
            self.assertIn(name, quelle, f"{name} fehlt in main.py")
        self.assertLess(
            quelle.index("freeze_header"), quelle.index("hauptthread_befund"),
            "der Befund steht vor der Kopfzeile — dann haengt er im Log am "
            "falschen Eintrag")
        self.assertLess(
            quelle.index("hauptthread_befund"), quelle.index("dump_traceback"),
            "der Befund steht NACH dem Dump — dann liest man erst sechs "
            "gesunde Stacks und die Einordnung danach, also genau in der "
            "Reihenfolge, die zur Fehldeutung gefuehrt hat")


class HauptthreadStackTest(unittest.TestCase):
    """Die Reihenfolge — die einzige Stelle, an der es still falsch werden kann.

    ``faulthandler`` druckt „most recent call first\". Liefert der Sammler die
    umgekehrte Reihenfolge, beschreibt der Befund ``<module>`` statt des
    tatsaechlich innersten Rahmens — und zeigt damit **wieder** auf den
    falschen: er meldete dann bei JEDEM Freeze „nativ\", auch bei einem, der
    mitten im Python-Code haengt.
    """

    def test_der_innerste_rahmen_steht_vorne(self):
        """Gemessen wie im Ernstfall: ein FREMDER Thread sieht dem Hauptthread zu.

        Der Sammler aus dem Hauptthread heraus aufzurufen waere ein anderer
        Vorgang — dann stuende sein eigener Rahmen ganz innen, und der Test
        pruefte nicht den Weg, den der Watchdog geht.
        """
        code = (
            "import json, threading, main\n"
            "erg, bereit, fertig = {}, threading.Event(), threading.Event()\n"
            "def sammler():\n"
            "    bereit.wait(30)\n"
            "    erg['s'] = main._hauptthread_stack()\n"
            "    fertig.set()\n"
            "threading.Thread(target=sammler, name='Sammler').start()\n"
            "def ganz_innen():\n"
            "    bereit.set()\n"
            "    fertig.wait(30)\n"
            "def eine_ebene_darueber():\n"
            "    ganz_innen()\n"
            "eine_ebene_darueber()\n"
            "print(json.dumps([f[2] for f in erg['s']]))\n"
        )
        erg = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(0, erg.returncode, erg.stderr[-800:])
        namen = json.loads(erg.stdout.strip().splitlines()[-1])
        for gesucht in ("ganz_innen", "eine_ebene_darueber", "<module>"):
            self.assertIn(gesucht, namen,
                          f"{gesucht} fehlt im gesammelten Stack: {namen}")
        self.assertLess(
            namen.index("ganz_innen"), namen.index("eine_ebene_darueber"),
            "der Stack kommt in der falschen Reihenfolge zurueck — der Befund "
            "beschriebe dann einen anderen Rahmen als der Dump darunter, und "
            f"meldete bei JEDEM Freeze 'nativ': {namen}")
        self.assertLess(
            namen.index("eine_ebene_darueber"), namen.index("<module>"), namen)


if __name__ == "__main__":
    unittest.main()
