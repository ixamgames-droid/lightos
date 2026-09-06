"""QA-78: wer ``address + channel`` rechnet, fragt vorher ``fixture_uses_dmx``.

Netzwerk-Laser (Ether Dream, IDN) tragen ``universe``/``address`` nur als
**bedeutungslose Platzhalter**. ``app_state.fixture_uses_dmx`` sagt das seit
LAS-04, und sein Docstring verlangt woertlich, dass **jede** Stelle mit dieser
Rechnung vorher fragt.

★ **Eine Regel, die nur im Docstring steht, ist nicht durchgesetzt — sie ist
eine Bitte.** Gemessen fragten **acht von neun** Schreibern nicht; ``scene.py``
war der erste belegte Schaden (ENG-20b: ein Laser schrieb in einen echten PAR).

**Verfahren beider Teile dieser Datei:** dieselbe Konfiguration zweimal fahren
und nur das ``protocol`` wechseln. Damit ist die Positivkontrolle eingebaut —
schreibt der DMX-Lauf nichts, ist die Probe **wertlos** und ausdruecklich keine
Entwarnung. Genau daran sind beim Messen drei Proben gescheitert (leere
``layers``, falsche Konstruktor-Felder, eine Attrappe die am Commit-Pfad
vorbeischrieb).
"""
from __future__ import annotations

import ast
import glob
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import app_state as AS

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0


_KANAELE = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
            _Ch("color_b", 4), _Ch("pan", 5), _Ch("tilt", 6)]


class _U:
    def __init__(self):
        self.ch = {}

    def set_channel(self, a, v):
        self.ch[a] = v


def _fx(protocol):
    return SimpleNamespace(fid=1, universe=1, address=1, protocol=protocol,
                           channel_count=6, fixture_type="matrix", label="P")


class SchreiberTest(unittest.TestCase):
    """Die sechs Schreiber, je mit eingebauter Positivkontrolle."""

    def setUp(self):
        alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda fx: list(_KANAELE)
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)

    def _beide(self, bauen):
        """``(dmx_adressen, laser_adressen)`` — dieselbe Konfiguration zweimal."""
        dmx = sorted(bauen(_fx("dmx")))
        self.assertTrue(dmx, "die Probe schreibt schon mit DMX nichts — dann "
                             "sagt ihr Ergebnis fuer den Laser NICHTS aus")
        return dmx, sorted(bauen(_fx("etherdream")))

    def test_effect_func_write(self):
        from src.core.engine.effect_func import LayeredEffect

        def bauen(f):
            e = LayeredEffect(name="e")
            e.fixture_ids = [1]
            e.base_value = 1.0
            e.target_attribute = "intensity"
            e.layers = [SimpleNamespace(process=lambda v, t, i: 1.0)]
            e._running = True
            u = _U()
            e.write({1: u}, [f], 0.05)
            return u.ch
        dmx, laser = self._beide(bauen)
        self.assertEqual([], laser, f"der Platzhalter schreibt auf {dmx}")

    def test_carousel_set_attr(self):
        from src.core.engine.carousel import Carousel

        def bauen(f):
            u = _U()
            Carousel(name="c")._set_attr(u, f, "color_r", 200)
            return u.ch
        dmx, laser = self._beide(bauen)
        self.assertEqual([], laser, f"der Platzhalter schreibt auf {dmx}")

    def test_sequence_write(self):
        from src.core.engine.sequence import Sequence, SequenceStep

        def bauen(f):
            s = Sequence(name="s")
            s.steps = [SequenceStep(values={"1": {"color_r": 200}},
                                    fade_in=0.0, hold=1.0)]
            s._running = True
            u = _U()
            s.write({1: u}, [f], 0.05)
            return u.ch
        dmx, laser = self._beide(bauen)
        self.assertEqual([], laser, f"der Platzhalter schreibt auf {dmx}")

    def test_mapped_channel_write(self):
        from src.core.engine.mapped_channel import MappedChannelChange, MappedRule

        def bauen(f):
            m = MappedChannelChange(name="m")
            m.fids = [1]
            m.rules = [MappedRule(target="color_r")]
            m._running = True
            u = _U()
            m.write({1: u}, [f], 0.05)
            return u.ch
        dmx, laser = self._beide(bauen)
        self.assertEqual([], laser, f"der Platzhalter schreibt auf {dmx}")

    def test_script_func_execute_line(self):
        from src.core.engine.script_func import ScriptFunction

        def bauen(f):
            s = ScriptFunction(name="s")
            s._running = True
            u = _U()
            s._execute_line("setfixture 1 color_r 200", {1: u}, [f], None)
            return u.ch
        dmx, laser = self._beide(bauen)
        self.assertEqual([], laser, f"der Platzhalter schreibt auf {dmx}")

    def test_efx_write(self):
        from src.core.engine.efx import EfxInstance, EfxFixture

        def bauen(f):
            e = EfxInstance(name="e")
            e.fixtures = [EfxFixture(fid=1)]
            e._running = True
            u = _U()
            e.write({1: u}, [f], 0.05)
            return u.ch
        dmx, laser = self._beide(bauen)
        self.assertEqual([], laser, f"der Platzhalter schreibt auf {dmx}")


class HuelleTest(unittest.TestCase):
    """``gibt_ueber_dmx_aus`` — und ihre bewusst gewaehlte sichere Richtung."""

    def test_ein_gewoehnliches_geraet_darf_schreiben(self):
        from src.core.engine.function import gibt_ueber_dmx_aus
        self.assertTrue(gibt_ueber_dmx_aus(_fx("dmx")))

    def test_ein_netzwerk_laser_nicht(self):
        from src.core.engine.function import gibt_ueber_dmx_aus
        for proto in ("etherdream", "idn", "ETHERDREAM"):
            with self.subTest(protocol=proto):
                self.assertFalse(gibt_ueber_dmx_aus(_fx(proto)))

    def test_im_zweifel_JA(self):
        """⚠️ Die sichere Richtung ist hier SCHREIBEN, nicht schweigen.

        Ein Alt-Objekt ohne ``protocol`` und ein Objekt, dessen Zugriff wirft,
        muessen weiter gefahren werden. Eine Funktion, die stumm nichts mehr
        tut, ist auf der Buehne schlimmer als eine, die zu viel tut — dieselbe
        Abwaegung wie bei FM-45/2 und ENG-20.
        """
        from src.core.engine.function import gibt_ueber_dmx_aus

        class _Boese:
            @property
            def protocol(self):
                raise RuntimeError("kaputt")

        self.assertTrue(gibt_ueber_dmx_aus(SimpleNamespace(fid=1)))
        self.assertTrue(gibt_ueber_dmx_aus(_Boese()))


class WaechterTest(unittest.TestCase):
    """★★ Schritt (c): die Regel wird aufgezaehlt, nicht erbeten.

    Sucht per **AST** die Funktionen, die eine Geraete-Adresse rechnen UND ins
    Universum schreiben, und haelt fest, dass jede die Regel konsultiert.

    ⚠️ Die zwei Ausnahmen unten sind **benannt und selbstraeumend**: der Test
    prueft, dass die Liste EXAKT stimmt. Wird eine davon behoben, faellt er und
    zwingt zum Streichen — eine Ausschlussliste, die still verrotten kann, waere
    genau der Waechter, vor dem Sitzung A gewarnt hat.
    """

    #: Geprueft und geschuetzt — mit dem Grund, nicht bloss als Name.
    BEGRUENDET = {
        "core/app_state.py::_render_frame":
            "geschuetzt ueber den Render-Plan: _rebuild_render_plan gibt "
            "Netzwerk-Geraeten keine Defaults/Spans, der Commit ist "
            "span-begrenzt (gemessen 2026-09-06)",
    }

    #: Gemessen ERREICHBAR, noch offen — Sitzung A zieht sie selbst nach (QA-78).
    OFFEN = {
        "core/engine/rgb_matrix.py::write",
        "core/engine/rgb_matrix.py::_weiss_achse_schreiben",
    }

    def _schreiber(self) -> dict:
        """``{"pfad::funktion": fragt_die_regel}`` fuer alle Adress-Schreiber."""
        def namen(baum):
            out = set()
            for k in ast.walk(baum):
                if isinstance(k, ast.Call):
                    f = k.func
                    out.add(f.attr if isinstance(f, ast.Attribute)
                            else getattr(f, "id", ""))
            return out

        gefunden = {}
        for pfad in glob.glob(os.path.join(_REPO, "src", "**", "*.py"),
                              recursive=True):
            with open(pfad, encoding="utf-8") as f:
                quelle = f.read()
            try:
                baum = ast.parse(quelle)
            except SyntaxError:
                continue
            rel = os.path.relpath(pfad, os.path.join(_REPO, "src"))
            rel = rel.replace(os.sep, "/")
            for fn in ast.walk(baum):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                rechnet = any(
                    isinstance(k, ast.BinOp) and isinstance(k.op, (ast.Add, ast.Sub))
                    and ".address" in ast.unparse(k) for k in ast.walk(fn))
                if not rechnet:
                    continue
                ruft = namen(fn)
                if not (ruft & {"set_channel", "set_channels", "set_range"}):
                    continue
                fragt = bool(ruft & {"fixture_uses_dmx", "gibt_ueber_dmx_aus",
                                     "_gibt_ueber_dmx_aus", "_fixture_uses_dmx",
                                     "_adresse_fuer"})
                gefunden[f"{rel}::{fn.name}"] = fragt
        return gefunden

    def test_die_suche_findet_ueberhaupt_schreiber(self):
        """★ Ohne das waere die Pruefung unten trivial gruen."""
        self.assertGreaterEqual(len(self._schreiber()), 9,
                                "die AST-Suche findet die bekannten Schreiber "
                                "nicht mehr — dann prueft dieser Waechter nichts")

    def test_jeder_schreiber_fragt_die_regel(self):
        ohne = {k for k, fragt in self._schreiber().items() if not fragt}
        unerwartet = sorted(ohne - set(self.BEGRUENDET) - self.OFFEN)
        self.assertEqual([], unerwartet,
                         "Diese Stellen rechnen eine Geraete-Adresse und "
                         "schreiben, ohne fixture_uses_dmx zu fragen — ein "
                         "Netzwerk-Laser schreibt dort in fremde Geraete: "
                         f"{unerwartet}")

    def test_die_offene_liste_raeumt_sich_selbst(self):
        """★★ Die Ausnahmeliste darf nicht still verrotten.

        Sobald A ihre beiden Stellen nachzieht, faellt dieser Test und zwingt
        zum Streichen. Eine Liste, die auch dann gruen bleibt, wenn ihr Grund
        entfallen ist, ist genau der Waechter, der zu viel schluckt.
        """
        ohne = {k for k, fragt in self._schreiber().items() if not fragt}
        erledigt = sorted(self.OFFEN - ohne)
        self.assertEqual([], erledigt,
                         f"Diese Stellen fragen die Regel inzwischen — bitte "
                         f"aus OFFEN streichen: {erledigt}")

    def test_die_begruendeten_tragen_einen_grund(self):
        for name, grund in self.BEGRUENDET.items():
            with self.subTest(stelle=name):
                self.assertGreater(len(grund), 40,
                                   "eine Ausnahme ohne nachvollziehbaren Grund "
                                   "ist eine Ausschlussliste")


if __name__ == "__main__":
    unittest.main()
