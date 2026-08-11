"""QA-51 — die Prüfwerkzeuge prüfen jetzt das, wofür sie gebaut wurden.

★ **Der Anlass steht im Item:** am 2026-08-05 waren **alle Gates grün**,
während das Gerät dunkel blieb. Drei Blindstellen zusammen haben das möglich
gemacht:

* Der Show-Lint griff auf genau **2 von 27** Show-Blöcken zu — ausgerechnet
  ``patch``, der bestimmt, *wo das Licht physisch hingeht*, kam nicht vor.
* Der Render-Smoke maß ``lit`` über das **ganze Universum** und erst **nach**
  dem Start der Funktion: eine nachweislich leere Szene bestand damit
  ``assert_not_inert``, sobald irgendwo sonst Licht an war.
* ``build_and_verify`` prüfte alle Funktionen in **einem** Durchlauf — **eine
  funktionierende maskierte beliebig viele inerte**.

Diese Tests halten die drei Lücken zu, jeweils mit Positivkontrolle: ein
Prüfwerkzeug, das alles beanstandet, ist genauso wertlos wie eines, das nichts
findet.
"""
import unittest

from src.core.capability.validate import validate_show_dict, ERROR, WARNING


def _finde(findings, code):
    return [f for f in findings if f.code == code]


class PatchWirdGeprueftTest(unittest.TestCase):
    """★★ Der Block, der bestimmt, wo das Licht hingeht — bisher ungeprüft."""

    def _lint(self, patch):
        return validate_show_dict({"patch": patch, "functions": [],
                                   "virtual_console": {"widgets": []}})

    def test_adressueberlauf_wird_gemeldet(self):
        """Ein 154-Kanal-Panel auf Adresse 400 ist zu 60 % stumm — und nichts
        sagte es. Genau die Geräteklasse, um die es am 2026-08-05 ging."""
        f = self._lint([{"label": "Panel", "universe": 1, "address": 400,
                         "channel_count": 154}])
        treffer = _finde(f, "PATCH-UEBERLAUF")
        self.assertEqual(1, len(treffer), [str(x) for x in f])
        self.assertEqual(ERROR, treffer[0].severity)
        self.assertIn("553", str(treffer[0]), "der belegte Bereich gehoert hin")

    def test_ueberlappung_im_selben_universum(self):
        """Der häufigste Patch-Fehler überhaupt: zwei Geräte auf denselben
        Kanälen. Das zweite gewinnt, das erste bleibt dunkel — und im Programm
        sieht alles normal aus."""
        f = self._lint([
            {"label": "PAR 1", "universe": 1, "address": 1, "channel_count": 8},
            {"label": "PAR 2", "universe": 1, "address": 5, "channel_count": 8},
        ])
        treffer = _finde(f, "PATCH-UEBERLAPPUNG")
        self.assertEqual(1, len(treffer), [str(x) for x in f])
        self.assertIn("PAR 1", str(treffer[0]))
        self.assertIn("PAR 2", str(treffer[0]))

    def test_verschiedene_universen_ueberlappen_nicht(self):
        """★ Positivkontrolle. Dieselben Adressen in ZWEI Universen sind der
        Normalfall eines Mehr-Universen-Rigs — sie zu melden waere ein
        Fehlalarm, der die echten Befunde entwertet."""
        f = self._lint([
            {"label": "A", "universe": 1, "address": 1, "channel_count": 8,
             "mode_name": "8ch"},
            {"label": "B", "universe": 2, "address": 1, "channel_count": 8,
             "mode_name": "8ch"},
        ])
        self.assertEqual([], _finde(f, "PATCH-UEBERLAPPUNG"))

    def test_luecken_los_aneinander_ist_kein_fehler(self):
        """Adresse 1..8 und 9..16 stossen aneinander, ueberlappen aber nicht —
        ein Off-by-one hier waere ein Dauer-Fehlalarm."""
        f = self._lint([
            {"label": "A", "universe": 1, "address": 1, "channel_count": 8,
             "mode_name": "8ch"},
            {"label": "B", "universe": 1, "address": 9, "channel_count": 8,
             "mode_name": "8ch"},
        ])
        self.assertEqual([], _finde(f, "PATCH-UEBERLAPPUNG"), [str(x) for x in f])

    def test_fehlender_modusname_ist_nur_eine_warnung(self):
        """Die Show laeuft damit — die Kanalzahl stammt nur aus einer Annahme.
        Ein ERROR waere hier unverhaeltnismaessig."""
        f = self._lint([{"label": "X", "universe": 1, "address": 1,
                         "channel_count": 4}])
        treffer = _finde(f, "PATCH-MODUS")
        self.assertEqual(1, len(treffer))
        self.assertEqual(WARNING, treffer[0].severity)

    def test_kaputte_zahl_stuerzt_den_lint_nicht_ab(self):
        f = self._lint([{"label": "X", "universe": "eins", "address": 1,
                         "channel_count": 4}])
        self.assertEqual(1, len(_finde(f, "PATCH-ZAHL")))

    def test_sauberer_patch_erzeugt_keine_befunde(self):
        """★ Die wichtigste Positivkontrolle: ein Lint, der jede normale Show
        beanstandet, wird nach zwei Tagen ignoriert."""
        f = self._lint([
            {"label": "PAR 1", "universe": 1, "address": 1, "channel_count": 8,
             "mode_name": "8-Kanal"},
            {"label": "PAR 2", "universe": 1, "address": 9, "channel_count": 8,
             "mode_name": "8-Kanal"},
            {"label": "MH", "universe": 2, "address": 1, "channel_count": 16,
             "mode_name": "16-Kanal"},
        ])
        self.assertEqual([], f, [str(x) for x in f])

    def test_ohne_patch_block_keine_befunde(self):
        """Alte Shows ohne den Block duerfen nicht rot werden."""
        self.assertEqual([], validate_show_dict(
            {"functions": [], "virtual_console": {"widgets": []}}))


class _FakeUniverse:
    def __init__(self, werte=None):
        self._w = dict(werte or {})

    def get_channel(self, c):
        return self._w.get(c, 0)

    def set(self, c, v):
        self._w[c] = v


class _FakeState:
    def __init__(self, universes):
        self.universes = universes
        self.frames = 0

    def _render_frame(self, _dt):
        self.frames += 1


class RenderProbeTest(unittest.TestCase):
    """★★ „Eine nachweislich leere Szene besteht ``assert_not_inert``."""

    def setUp(self):
        from unittest import mock
        self.fm = mock.MagicMock()
        self.p = mock.patch(
            "src.core.engine.function_manager.get_function_manager",
            return_value=self.fm)
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_fremdes_licht_macht_eine_inerte_funktion_nicht_hell(self):
        """★ Der Kern: Kanal 100 ist von einem ANDEREN Effekt an, die geprüfte
        Funktion tut nichts. Vorher meldete die Probe ``lit=True`` — sie maß
        „irgendwo im Universum ist Licht" statt „diese Funktion erzeugt Licht".
        """
        from src.core.capability.render_probe import render_diff
        state = _FakeState({1: _FakeUniverse({100: 255})})
        lit, moved, changed = render_diff(state, [7], frames=2, warmup=1)
        self.assertFalse(lit, "fremdes Licht darf nicht als eigener Erfolg zaehlen")
        self.assertFalse(moved)

    def test_eigene_wirkung_wird_erkannt(self):
        """Positivkontrolle: eine Funktion, die wirklich einen Kanal hochzieht."""
        from src.core.capability.render_probe import render_diff
        u = _FakeUniverse()
        state = _FakeState({1: u})
        original = state._render_frame

        def rendern(dt):
            original(dt)
            u.set(10, 200)          # die Funktion schreibt ab dem ersten Frame

        state._render_frame = rendern
        lit, _moved, _changed = render_diff(state, [7], frames=2, warmup=1)
        self.assertTrue(lit)

    def test_fehlendes_universum_ist_ein_eigener_fehler(self):
        """★ „Erzeugt kein DMX" und „dieses Universum gibt es nicht" sind zwei
        verschiedene Diagnosen. Die zweite als die erste zu melden schickt die
        Suche in die falsche Richtung — genau der Fall vom 2026-08-05."""
        from src.core.capability.render_probe import (
            render_diff, KeinUniversumError)
        state = _FakeState({1: _FakeUniverse()})
        with self.assertRaises(KeinUniversumError) as ctx:
            render_diff(state, [7], universe=5, frames=1, warmup=0)
        self.assertIn("5", str(ctx.exception))

    def test_die_probe_stoppt_was_sie_startet(self):
        """Sonst läuft die Funktion weiter und die nächste Probe misst sie mit."""
        from src.core.capability.render_probe import render_diff
        state = _FakeState({1: _FakeUniverse()})
        render_diff(state, [7, 8], frames=1, warmup=0)
        gestoppt = [c.args[0] for c in self.fm.stop.call_args_list]
        self.assertEqual([7, 8], gestoppt)


class VerifyRenderEinzelnTest(unittest.TestCase):
    """★★ „Eine funktionierende Funktion maskiert beliebig viele inerte."""

    def test_jede_funktion_wird_einzeln_geprueft(self):
        from unittest import mock
        from src.core.show.showbuilder.builder import ShowBuilder
        b = ShowBuilder.__new__(ShowBuilder)
        b.state = object()
        laeufe = []

        def fake(_state, fids, **_kw):
            laeufe.append(list(fids))
            return (fids != [2]), True, []     # Funktion 2 ist inert

        with mock.patch("src.core.capability.render_probe.render_diff", fake):
            lit, _moved, _changed = b.verify_render([1, 2, 3])
        self.assertEqual([[1], [2], [3]], laeufe,
                         "die Funktionen muessen einzeln laufen")
        self.assertFalse(lit, "die inerte Funktion 2 haette auffallen muessen")

    def test_gemeinsam_messen_bleibt_moeglich_aber_benannt(self):
        from unittest import mock
        from src.core.show.showbuilder.builder import ShowBuilder
        b = ShowBuilder.__new__(ShowBuilder)
        b.state = object()
        laeufe = []

        def fake(_state, fids, **_kw):
            laeufe.append(list(fids))
            return True, True, []

        with mock.patch("src.core.capability.render_probe.render_diff", fake):
            b.verify_render([1, 2, 3], einzeln=False)
        self.assertEqual([[1, 2, 3]], laeufe)


class SyntaxGateDecktToolsAbTest(unittest.TestCase):
    """★ Kein Gate kompilierte ``tools/``.

    Ein Syntaxfehler in einem Werkzeug fiel erst auf, wenn jemand es benutzte
    — und ``gen_tools_index.py`` verwandelt einen ``SyntaxError`` beim Einlesen
    sogar in die harmlose Index-Zelle „(Docstring nicht lesbar)". Die kaputte
    Datei steht damit ordentlich im Verzeichnis, und der Index bestaetigt sie.
    """

    def test_der_runner_kompiliert_auch_tools(self):
        import pathlib
        runner = (pathlib.Path(__file__).resolve().parent.parent
                  / "tools" / "verify_loop.sh")
        text = runner.read_text(encoding="utf-8")
        self.assertIn("compileall -q src tools", text,
                      "der Syntax-Check muss tools/ einschliessen")

    def test_tools_sind_syntaktisch_in_ordnung(self):
        """Die Gegenprobe zum Schritt oben — und zugleich die Aussage, die er
        im Gate treffen soll."""
        import compileall
        import io
        import contextlib
        import pathlib
        tools = pathlib.Path(__file__).resolve().parent.parent / "tools"
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            ok = compileall.compile_dir(str(tools), quiet=1, force=True)
        self.assertTrue(ok, f"Syntaxfehler in tools/:\n{puffer.getvalue()}")


if __name__ == "__main__":
    unittest.main()
