"""ENG-28: Generatoren oeffnen den Shutter nur mit Beleg — nie mit 255.

Folgepunkt aus dem Review von ENG-27 (#844). ``open_value_for(fx, "shutter")``
faellt ohne Beleg auf den Vorgabewert 255 zurueck, an vielen Shuttern
„schnelles Blitzen". Seit ENG-27 kommt dieser Rueckfall auch dann, wenn der
``highlight_value`` eines Shutters ohne ``open``-Bereich im ``strobe``- oder
``closed``-Bereich liegt. Zehn Generatoren in ``tools/`` riefen
``open_value_for`` an 13 Stellen OHNE erkennbaren ``fallback`` auf und schrieben
diese 255 in Szenen, „Alles Weiss"-Szenen und Grundwerte (``base_levels``).

Jetzt gilt in ``tools/`` dieselbe Regel wie in „Alles Weiss" und im
EFX-Sichtbarkeits-Shutter: ``tools/_shutter.shutter_offen`` liefert den belegten
Wert oder ``None`` — und ohne Beleg bleibt der Shutter stehen.

Der Waechter unten prueft ALLE Werkzeuge, nicht nur die zehn.
"""
import ast
import contextlib
import io
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import src.core.app_state as A      # noqa: E402

_FUNKTIONEN = ("open_value_for", "open_value_of_channel")
#: Attribute, an denen 255 ohne Beleg „schnelles Blitzen" heissen kann.
_SHUTTER = ("shutter", "strobe")


def _aufrufe_ohne_rueckfall(quelltext, name="<quelle>"):
    """Aufrufe von ``open_value_for`` (am Shutter) und ``open_value_of_channel``
    ohne ausdruecklichen ``fallback`` — oder mit einem DMX-Wert (>= 0) als
    fallback. ``open_value_for(fx, "intensity")`` darf 255 behalten.

    Liefert ``(alle Aufrufe, Beanstandungen)``.
    """
    try:
        baum = ast.parse(quelltext, filename=name)
    except SyntaxError:
        return 0, []
    alle, treffer = 0, []
    for k in ast.walk(baum):
        if not isinstance(k, ast.Call):
            continue
        f = k.func
        fname = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if fname not in _FUNKTIONEN:
            continue
        alle += 1
        if fname == "open_value_for" and len(k.args) > 1 and isinstance(k.args[1], ast.Constant) \
                and k.args[1].value not in _SHUTTER:
            continue        # z. B. "intensity": dort ist 255 der richtige Rueckfall
        stelle = 2 if fname == "open_value_for" else 1
        rueckfall = k.args[stelle] if len(k.args) > stelle else next(
            (kw.value for kw in k.keywords if kw.arg == "fallback"), None)
        if rueckfall is None or (isinstance(rueckfall, ast.Constant)
                                 and isinstance(rueckfall.value, int)
                                 and rueckfall.value >= 0):
            treffer.append(f"{name}:{k.lineno}  {ast.unparse(k)}")
    return alle, treffer


def _werkzeuge():
    """Alle lebenden Werkzeuge (``tools/*.py`` und Unterordner, ohne ``_archiv``)."""
    for wurzel, ordner, dateien in os.walk(TOOLS):
        ordner[:] = [o for o in ordner if o not in ("_archiv", "__pycache__")]
        for d in sorted(dateien):
            if d.endswith(".py"):
                yield os.path.join(wurzel, d)


class KeinWerkzeugOeffnetOhneBeleg(unittest.TestCase):

    def test_jeder_aufruf_hat_einen_erkennbaren_rueckfall(self):
        alle, treffer = 0, []
        for pfad in _werkzeuge():
            with open(pfad, encoding="utf-8", errors="replace") as f:
                n, t = _aufrufe_ohne_rueckfall(f.read(), os.path.relpath(pfad, REPO))
            alle += n
            treffer += t
        self.assertGreaterEqual(alle, 1, "Vorbedingung: der Scanner sieht die Aufrufe")
        self.assertEqual(treffer, [], (
            "Aufruf ohne erkennbaren fallback — ohne Beleg wuerde 255 geschrieben "
            "(an vielen Shuttern schnelles Blitzen). tools/_shutter.shutter_offen "
            "benutzen:\n  " + "\n  ".join(treffer)))

    def test_der_scanner_erkennt_die_alten_formen(self):
        """Positivkontrolle — sonst waere der Waechter oben leer gruen."""
        quelle = (
            'a = open_value_for(fx, "shutter")\n'
            'b = open_value_for(fx, "shutter", 255)\n'
            'c = A.open_value_of_channel(ch)\n'
            'd = open_value_for(fx, "shutter", fallback=0)\n'
            'e = open_value_for(fx, "shutter", -1)\n'
            'f = open_value_for(fx, "shutter", KEIN_BELEG)\n'
            'g = open_value_of_channel(ch, fallback=-1)\n'
            'h = open_value_for(fx, "intensity")\n')
        alle, treffer = _aufrufe_ohne_rueckfall(quelle)
        self.assertEqual(alle, 8)
        self.assertEqual([t.split(":")[1].split()[0] for t in treffer], ["1", "2", "3", "4"])


# ── Verhalten von shutter_offen ──────────────────────────────────────────────

class _Range:
    def __init__(self, lo, hi, kind="", name=""):
        self.range_from, self.range_to, self.kind, self.name = lo, hi, kind, name


class _Ch:
    def __init__(self, attr, num, highlight=255, ranges=None, name=""):
        self.attribute, self.channel_number = attr, num
        self.default_value, self.highlight_value = 0, highlight
        self.ranges, self.name = ranges or [], name


class _Fx:
    def __init__(self, name):
        self.name, self.fid = name, 1


class ShutterOffen(unittest.TestCase):

    def setUp(self):
        import _shutter
        self.mod = _shutter
        self.mod._gemeldet.clear()
        self._orig = A.get_channels_for_patched
        self.kanaele = []
        A.get_channels_for_patched = lambda fx: self.kanaele

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _frage(self, *kanaele, name="Spot"):
        self.kanaele = list(kanaele)
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            wert = self.mod.shutter_offen(_Fx(name))
        return wert, aus.getvalue()

    def test_strobe_highlight_ohne_open_bereich_ist_kein_beleg(self):
        shutter = _Ch("shutter", 4, 200, [_Range(0, 9, "closed", "Zu"),
                                          _Range(10, 255, "strobe", "Strobe")], "Shutter")
        wert, ausgabe = self._frage(_Ch("intensity", 1), shutter)
        self.assertIsNone(wert, "ohne Beleg haette der Generator 255 geschrieben")
        self.assertIn("Spot", ausgabe)
        self.assertIn("unberuehrt", ausgabe)

    def test_open_bereich_ist_der_beleg(self):
        shutter = _Ch("shutter", 4, 200, [_Range(0, 7, "closed"), _Range(8, 15, "open"),
                                          _Range(16, 255, "strobe")])
        wert, ausgabe = self._frage(shutter)
        self.assertEqual(wert, 11)
        self.assertEqual(ausgabe, "")

    def test_kein_shutter_kein_wert(self):
        wert, _ = self._frage(_Ch("intensity", 1), name="Par")
        self.assertIsNone(wert)

    def test_meldung_nur_einmal_je_geraet(self):
        shutter = _Ch("shutter", 4, 5, [_Range(0, 9, "closed"), _Range(10, 255, "strobe")])
        _, erste = self._frage(shutter, name="Mover 1")
        _, zweite = self._frage(shutter, name="Mover 1")
        self.assertTrue(erste)
        self.assertEqual(zweite, "")


class GeneratorenNutzenDieRegel(unittest.TestCase):
    """Die zehn Generatoren aus dem Befund holen den Shutter-Wert ueber
    ``shutter_offen`` — der Waechter oben allein wuerde auch ein Entfernen
    der Shutter-Zeilen durchlassen."""

    GENERATOREN = (
        "build_demo_show_full.py", "build_event_demo_2026.py",
        "build_farb_fx_vc_show.py", "build_hochzeit_komplett.py",
        "build_mega_arena_2026.py", "build_musik_show_2026.py",
        "build_neue_demo_show.py", "build_party_demo_show.py",
        "build_testshow_2026.py", "build_tutorial_matrix_show.py",
    )

    def test_shutter_offen_statt_open_value_for(self):
        for name in self.GENERATOREN:
            with self.subTest(generator=name):
                with open(os.path.join(TOOLS, name), encoding="utf-8") as f:
                    baum = ast.parse(f.read())
                aufrufe = [k for k in ast.walk(baum) if isinstance(k, ast.Call)
                           and isinstance(k.func, ast.Name) and k.func.id == "shutter_offen"]
                self.assertTrue(aufrufe, f"{name} holt den Shutter nicht ueber shutter_offen")


if __name__ == "__main__":
    unittest.main()
