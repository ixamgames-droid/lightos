"""UI-135: gleichmaessige Blitzabstaende in der 2D-Ansicht.

**Befund (B am echten Bildschirm, 15.11.2026).** Strobe 1x blinkte
gleichmaessig, 2x/4x unregelmaessig.

**Ursache.** Geblitzt wird in ganzen Takt-Bildern (VIZ-104). Die Bilder selbst
kamen aber nicht gleichmaessig: der Zeitgeber feuerte im festen Strobe-Takt
(50 ms), und das Budget liess nur jedes zweite oder dritte Feuern zeichnen.
Gemessen (Sitzung D, 16.11., Windows x64, 250 %, 68 blinkende Geraete, je
12 s): Bildabstaende rund 63 und 125 ms im Wechsel (Streuung 30 ms) - der
grobe Windows-Zeitgeber rastet auf 15,6 ms. Bei der kleinsten Blitzperiode
(3 Bilder) schwankte der Blitzabstand so zwischen 239 und 315 ms.

**Jetzt.** Im Strobe-Takt IST der Zeitgeber der Budget-Abstand: Takt =
Zeichenzeit / STROBE_UI_ANTEIL (mindestens STROBE_TAKT_MS), mit Hysterese,
als genauer Zeitgeber, und jedes Feuern zeichnet. Die Blitzfolge rechnet mit
genau diesem Takt.
"""
from __future__ import annotations

import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

from src.ui.views import live_view                                  # noqa: E402

_app = QApplication.instance() or QApplication([])


class GleichmaessigTest(unittest.TestCase):

    def setUp(self):
        c = live_view.StageCanvas()
        c._update_timer.stop()               # Takt hier von Hand
        self.zeit = [100.0]
        c._uhr = lambda: self.zeit[0]
        c._darf_zeichnen = lambda: True
        c._animiert = True
        self.bilder: list[float] = []
        self.zeichnet = True                 # False: das Bild bleibt aus (UI-Thread belegt)

        def update(*_a):                     # statt zu zeichnen
            if self.zeichnet:
                self.bilder.append(self.zeit[0])
                c._takt_bild_zaehlen()       # wie am Anfang von paintEvent
        c.update = update
        self.addCleanup(c.deleteLater)
        self.c = c

    def _blinkt(self, hz=10.0):
        leer = {"strobe": [], "uni": 1, "fp": (42,)}
        return self.c._strobe_aus_steckbrief(leer, lambda _u, _a: 255, {"square": {42: hz}})

    def _zeichenzeit(self, ms):
        self.c._zeichenzeiten.clear()
        self.c._zeichenzeiten.extend([ms / 1000.0] * 5)

    def _laufen(self, sekunden):
        """Der Zeitgeber feuert in seinem eingestellten Abstand; jedes Bild sieht
        das blinkende Geraet wieder (wie das Zeichnen)."""
        c = self.c
        ende = self.zeit[0] + sekunden
        while self.zeit[0] < ende:
            self._blinkt()
            c._on_render_tick()
            self.zeit[0] += c._update_timer.interval() / 1000.0

    # ── der Takt ─────────────────────────────────────────────────────────────

    def test_strobe_takt_ist_der_budget_abstand(self):
        """34 ms je Bild (gemessen, 250 %) -> 34 / 0,33 = 103,03 -> 104 ms."""
        c = self.c
        self._zeichenzeit(34)
        self._blinkt()
        erwartet = math.ceil(34 / c.STROBE_UI_ANTEIL)
        self.assertEqual(erwartet, 104)
        self.assertEqual(c._takt_ms(), erwartet)
        self.assertLessEqual(34 / c._takt_ms(), c.STROBE_UI_ANTEIL)
        self.assertEqual(c._bild_abstand_s(), 0.0, "der Zeitgeber haelt das Budget selbst")
        self.assertAlmostEqual(c._strobe_bildrate(), 1000.0 / erwartet, places=6)

    def test_schnelles_zeichnen_bleibt_beim_mindesttakt(self):
        c = self.c
        self._zeichenzeit(5)
        self._blinkt()
        self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)

    def test_nie_seltener_als_ein_bild_je_sekunde(self):
        c = self.c
        self._zeichenzeit(900)
        self._blinkt()
        self.assertEqual(c._takt_ms(), int(c.MAX_BILD_ABSTAND_S * 1000))

    def test_hysterese_kleine_schwankung_aendert_den_takt_nicht(self):
        """Sonst spraenge die Blitzperiode (ganze Bilder aus Bildrate / Frequenz)."""
        c = self.c
        self._zeichenzeit(34)
        self._blinkt()
        c._on_render_tick()
        self.assertEqual(c._takt_ms(), 104)
        self._zeichenzeit(36)                    # 110 ms: +6 %
        c._on_render_tick()
        self.assertEqual(c._takt_ms(), 104)
        self._zeichenzeit(31)                    # 94 ms: -10 %
        c._on_render_tick()
        self.assertEqual(c._takt_ms(), 104)
        self._zeichenzeit(45)                    # 137 ms: +32 % - gilt erst, wenn es anhaelt
        for _ in range(c.STROBE_TAKT_GEDULD - 1):
            c._on_render_tick()
            self.assertEqual(c._takt_ms(), 104)
        c._on_render_tick()
        self.assertEqual(c._takt_ms(), 137)
        self._zeichenzeit(40)                    # 122 ms: -11 % von 137
        for _ in range(c.STROBE_TAKT_GEDULD + 2):
            c._on_render_tick()
        self.assertEqual(c._takt_ms(), 137)

    def test_kurze_stoerung_aendert_den_takt_nicht(self):
        """Nachmessung 16.11.: einige langsame Bilder (UI-Thread kurz belegt)
        hoben den Takt an und gleich wieder ab - zwei Spruenge der Blitzphase,
        und danach ein leicht anderer Takt. Jetzt muss die Abweichung
        STROBE_TAKT_GEDULD Feuern hintereinander anhalten."""
        c = self.c
        self._zeichenzeit(34)
        self._blinkt()
        c._on_render_tick()
        self.assertEqual(c._takt_ms(), 104)
        for _runde in range(3):
            self._zeichenzeit(60)                # 182 ms: +75 %
            for _ in range(c.STROBE_TAKT_GEDULD - 1):
                c._on_render_tick()
            self.assertEqual(c._takt_ms(), 104)
            self._zeichenzeit(33)                # wieder wie vorher: die Geduld beginnt neu
            c._on_render_tick()
            self.assertEqual(c._takt_ms(), 104)

    def test_neuer_strobe_rechnet_neu(self):
        """Nach dem Nachlauf ist der gemerkte Takt weg - der naechste Strobe
        beginnt mit der dann geltenden Zeichenzeit."""
        c = self.c
        self._zeichenzeit(34)
        self._blinkt()
        self.assertEqual(c._takt_ms(), 104)
        self.zeit[0] += c.STROBE_NACHLAUF_S + 0.5
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)
        self._zeichenzeit(20)
        self._blinkt()
        self.assertEqual(c._takt_ms(), 61)

    # ── der Zeitgeber ────────────────────────────────────────────────────────

    def test_zeitgeber_im_strobe_takt_genau_und_im_budget_abstand(self):
        c = self.c
        self._zeichenzeit(34)
        c._update_timer.setInterval(c.RENDER_INTERVAL_MS)
        self._blinkt()
        c._on_render_tick()
        self.assertEqual(c._update_timer.interval(), 104)
        self.assertEqual(c._update_timer.timerType(), Qt.TimerType.PreciseTimer,
                         "der grobe Windows-Zeitgeber rastet auf 15,6 ms")
        self.zeit[0] += c.STROBE_NACHLAUF_S + 0.5
        c._on_render_tick()
        self.assertEqual(c._update_timer.interval(), c.RENDER_INTERVAL_MS)
        self.assertEqual(c._update_timer.timerType(), Qt.TimerType.CoarseTimer)

    def test_zeitgeber_folgt_auch_ohne_neues_bild(self):
        """Nach dem Strobe steht das Bild still (nichts animiert, Signatur
        gleich): der Takt zeichnet nicht - der Zeitgeber muss trotzdem sofort
        zurueck, nicht erst mit dem naechsten Bild."""
        c = self.c
        self._zeichenzeit(34)
        self._blinkt()
        c._on_render_tick()
        self.assertEqual(c._update_timer.interval(), 104)
        self.zeit[0] += c.STROBE_NACHLAUF_S + 0.5
        c._animiert = False
        c._paint_sig = c._anzeige_signatur()
        c._takte_ohne_paint = 0
        n = len(self.bilder)
        c._on_render_tick()
        self.assertEqual(len(self.bilder), n, "Voraussetzung: dieser Takt zeichnet nicht")
        self.assertEqual(c._update_timer.interval(), c.RENDER_INTERVAL_MS)

    # ── die Bilder und die Blitze ────────────────────────────────────────────

    def test_jedes_feuern_zeichnet(self):
        c = self.c
        self._zeichenzeit(34)
        self._blinkt()
        c._on_render_tick()                      # stellt den Zeitgeber
        self.bilder.clear()
        self._laufen(3.0)
        abstaende = [round((b - a) * 1000) for a, b in zip(self.bilder, self.bilder[1:])]
        self.assertGreater(len(abstaende), 20)
        self.assertEqual(set(abstaende), {104}, "Bilder muessen im festen Abstand kommen")

    def test_blitzabstaende_sind_gleich(self):
        """★ Der Befund: bei der kleinsten Periode (3 Bilder) wechselten die
        Blitzabstaende, weil die Bilder im Raster 50 ms mit Budget kamen."""
        c = self.c
        self._zeichenzeit(34)
        for hz in (4.0, 10.0, 20.0):
            with self.subTest(hz=hz):
                self.zeit[0] += 10.0
                c._strobe_bild = 0
                self._blinkt(hz)
                c._on_render_tick()
                self.bilder.clear()
                blitze, war_an = [], False
                ende = self.zeit[0] + 6.0
                while self.zeit[0] < ende:
                    self._blinkt(hz)
                    n = len(self.bilder)
                    c._on_render_tick()
                    if len(self.bilder) > n:                 # ein Bild: leuchtet es?
                        an = c._blink_an(hz)
                        if an and not war_an:
                            blitze.append(self.zeit[0])
                        war_an = an
                    self.zeit[0] += c._update_timer.interval() / 1000.0
                abst = [round((b - a) * 1000) for a, b in zip(blitze, blitze[1:])]
                self.assertGreater(len(abst), 8)
                self.assertEqual(len(set(abst)), 1, f"Blitzabstaende {sorted(set(abst))} ms")

    def test_zwei_feuern_vor_einem_bild_zaehlen_als_eines(self):
        """★ Nachmessung 16.11.: rund jeder zwanzigste Blitzabstand war doppelt
        so lang. Der Zaehler zaehlte je Feuern; feuerte der Zeitgeber zweimal,
        bevor gezeichnet war, uebersprang er ein Bild - bei der kleinsten
        Periode (ein Bild von dreien leuchtet) fiel so der Blitz aus."""
        c = self.c
        self._zeichenzeit(34)
        self._blinkt()
        c._on_render_tick()
        vorher = c._strobe_bild
        self.zeichnet = False                    # UI-Thread belegt: kein Bild
        for _ in range(2):
            self.zeit[0] += c._update_timer.interval() / 1000.0
            c._on_render_tick()
        self.assertEqual(c._strobe_bild, vorher, "ohne Bild zaehlt nichts weiter")
        c._takt_bild_zaehlen()                   # jetzt wird gezeichnet
        self.assertEqual(c._strobe_bild, vorher + 1)
        c._takt_bild_zaehlen()                   # Bild aus der Bedienung (Maus, Auswahl)
        self.assertEqual(c._strobe_bild, vorher + 1)

    def test_kein_blitz_faellt_aus_wenn_bilder_ausbleiben(self):
        """Jedes fuenfte Feuern bleibt ohne Bild: trotzdem leuchtet in der
        Folge der GEZEICHNETEN Bilder genau jedes dritte."""
        c = self.c
        self._zeichenzeit(34)
        self._blinkt()
        c._on_render_tick()
        self.bilder.clear()
        folge = []
        for i in range(60):
            self._blinkt()
            self.zeichnet = i % 5 != 4
            n = len(self.bilder)
            c._on_render_tick()
            if len(self.bilder) > n:
                folge.append("#" if c._blink_an(10.0) else ".")
            self.zeit[0] += c._update_timer.interval() / 1000.0
        text = "".join(folge)
        self.assertEqual(len(text), 48)
        erster = text.index("#")
        self.assertEqual(text[erster:erster + 45], "#.." * 15, text)

    def test_echtes_zeichnen_zaehlt_das_takt_bild(self):
        """Durch den echten Zeichenweg: ein Feuern + ein Bild = ein Schritt,
        ein weiteres Bild ohne Feuern = kein Schritt."""
        c = live_view.StageCanvas()
        c._update_timer.stop()
        self.addCleanup(c.deleteLater)
        c._darf_zeichnen = lambda: True
        c._animiert = True
        c.resize(200, 150)
        vorher = c._strobe_bild
        c._on_render_tick()
        self.assertEqual(c._strobe_bild, vorher, "der Takt meldet das Bild nur an")
        c.grab()
        self.assertEqual(c._strobe_bild, vorher + 1)
        c.grab()
        self.assertEqual(c._strobe_bild, vorher + 1)

    def test_anteil_bleibt_unter_der_vorgabe(self):
        c = self.c
        for ms in (12, 20, 34, 45, 60, 90):
            with self.subTest(zeichenzeit=ms):
                self.zeit[0] += 10.0
                self._zeichenzeit(ms)
                self._blinkt()
                takt = c._takt_ms()
                self.assertLessEqual(ms / takt, c.STROBE_UI_ANTEIL + 1e-9)
                self.assertLess(ms / takt, 0.5)

    def test_ohne_strobe_wie_bisher(self):
        c = self.c
        self._zeichenzeit(34)
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)
        self.assertAlmostEqual(c._bild_abstand_s(), 0.034 / c.MAX_UI_ANTEIL, places=4)
        c._on_render_tick()
        self.assertEqual(c._update_timer.interval(), c.RENDER_INTERVAL_MS)
        self.assertEqual(c._update_timer.timerType(), Qt.TimerType.CoarseTimer)


if __name__ == "__main__":
    unittest.main()
