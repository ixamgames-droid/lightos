"""QA-74: die EINE Antwort auf „die Szene kam nicht hoch" — und ihre Grenzen.

**Der Fund (Sitzung A, Gate-Lauf zu FM-41).** Der WebGL-Waechter aus QA-70 stand
nur in EINER der Szenen-Testdateien. ``tests/test_viz14_drag_scene.py`` fiel mit
3 von 3 Methoden, und im Segment-Log stand Zeichen fuer Zeichen die
QA-70-Signatur — isoliert lief die Datei in 6,5 s durch, und es lief keine
LightOS-Instanz (XPLAT-14 scheidet aus).

★ **Nachgemessen war es groesser und zugleich kleiner als gemeldet.** 28
Testdateien warten auf ``__lightosAppReady`` — aber nur **drei** rufen
``view.show()``, und genau das ist das in XPLAT-17 gemessene Unterscheidungs-
merkmal fuer den Kontextverlust. Es sind dieselben drei, die die Diagnose lesen.
Diese drei beantworteten dieselbe Frage **drei Mal verschieden**:

* ``place_ghost`` (QA-70) — bei GL-Ausfall ueberspringen,
* ``drag`` (XPLAT-17/19) — einmal neu laden, danach scheitern,
* ``deselect`` (XPLAT-19) — sofort scheitern.

Dazu stand die Diagnose selbst (``_DIAG_JS`` + ``_szenen_diagnose``) in allen
dreien woertlich gleich. Beides liegt jetzt in ``tests/_webgl_gate.py``.

⚠️ **Die Gefahr ist nicht der Flake, sondern die Reparatur.** Ein Ueberspringer,
der zu viel schluckt, versteckt echte Szenenfehler hinter einem gruenen Lauf —
A hat ausdruecklich darauf hingewiesen. Diese Datei haelt deshalb BEIDE
Richtungen fest.
"""
from __future__ import annotations

import json
import os
import unittest

import _webgl_gate

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wortlaut aus den Segment-Logs (QA-70 2026-09-01, QA-74 2026-09-03).
ECHTE_GL_FEHLER = ("Error creating WebGL context.", "Context lost during MakeCurrent")

#: Die drei Dateien, die `view.show()` rufen und den Ausfall damit sehen koennen.
SZENEN_DATEIEN = ("tests/test_viz14_place_ghost_scene.py",
                  "tests/test_viz14_drag_scene.py",
                  "tests/test_viz14_deselect_scene.py")


def _diagnose(err, **rest):
    felder = {"err": err, "ready": False, "three": "object", "api": "undefined",
              "chan": True, "canvas": 0, "doc": "complete"}
    felder.update(rest)
    return json.dumps(felder)


class ErkennungTest(unittest.TestCase):
    """Der Klassifikator — eng, und in beide Richtungen belegt."""

    def test_die_echten_meldungen_werden_erkannt(self):
        for text in ECHTE_GL_FEHLER:
            with self.subTest(text=text):
                self.assertTrue(_webgl_gate.ist_gl_kontext_ausfall(_diagnose(text)))

    def test_ein_echter_skriptfehler_wird_NICHT_geschluckt(self):
        """★★ Die wichtigere Haelfte.

        Ein TypeError sieht in der Diagnose fast genauso aus (``canvas: 0``,
        ``api: undefined``) — er ist aber ein Fehler, den diese Tests FINDEN
        sollen.
        """
        for text in ("TypeError: window.__lightos.setEditMode is not a function",
                     "ReferenceError: THREE is not defined",
                     "SyntaxError: Unexpected token '<'"):
            with self.subTest(text=text):
                self.assertFalse(_webgl_gate.ist_gl_kontext_ausfall(_diagnose(text)))

    def test_ohne_oder_mit_unlesbarer_ursache_wird_nicht_geschluckt(self):
        """Unbekannt ist nicht dasselbe wie harmlos — im Zweifel rot (QA-53)."""
        for roh in ("", None, _diagnose(""), _diagnose("", three="undefined"),
                    "kein Rueckruf (Renderer-Prozess tot?)",
                    "nicht lesbar: RuntimeError()", "[]", "null"):
            with self.subTest(roh=roh):
                self.assertFalse(_webgl_gate.ist_gl_kontext_ausfall(roh))


class EntscheidungTest(unittest.TestCase):
    """``nach_szenen_timeout`` — die drei Ausgaenge, aus einer Quelle."""

    def test_erster_gl_ausfall_laedt_einmal_neu(self):
        """Wie das Produkt selbst (VIZ-SCENE-SELFHEAL) — und laut."""
        with self.assertWarns(RuntimeWarning):
            weiter = _webgl_gate.nach_szenen_timeout(
                AssertionError("Timeout"), _diagnose(ECHTE_GL_FEHLER[0]),
                zweiter_versuch=False)
        self.assertTrue(weiter, "der erste Ausfall fuehrt nicht zum Neuversuch")

    def test_zweiter_gl_ausfall_ueberspringt(self):
        """★★ Genau hier ist `drag` bei A gescheitert.

        Der Neuversuch reichte nicht — und dann faellt der Test an einer
        Zusicherung, die er gar nicht pruefen konnte.
        """
        with self.assertRaises(unittest.SkipTest) as ctx:
            _webgl_gate.nach_szenen_timeout(
                AssertionError("Timeout"), _diagnose(ECHTE_GL_FEHLER[1]),
                zweiter_versuch=True)
        self.assertIn("QA-70/QA-74", str(ctx.exception),
                      "der Grund nennt sein Item nicht — dann sieht niemand im "
                      "-rs-Bericht, warum hier nichts geprueft wurde")

    def test_jeder_andere_fehler_scheitert_weiterhin(self):
        """★ Die Gegenprobe: aus dem Ueberspringer darf kein Freibrief werden."""
        for zweiter in (False, True):
            with self.subTest(zweiter_versuch=zweiter):
                with self.assertRaises(AssertionError) as ctx:
                    _webgl_gate.nach_szenen_timeout(
                        AssertionError("Timeout bei ready"),
                        _diagnose("TypeError: x is not a function"),
                        zweiter_versuch=zweiter)
                self.assertNotIsInstance(ctx.exception, unittest.SkipTest)
                self.assertIn("TypeError", str(ctx.exception),
                              "die eigentliche Fehlermeldung geht verloren")


class EineQuelleTest(unittest.TestCase):
    """Damit die vierte Datei in einem halben Jahr nicht wieder ohne dasteht.

    A's Auflage woertlich: „aus EINER Quelle loesen (Helfer statt Kopie), sonst
    steht die dritte Datei in einem halben Jahr wieder ohne."
    """

    def _quelle(self, rel):
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            return f.read()

    def test_jede_szenen_datei_fragt_die_gemeinsame_quelle(self):
        ohne = [rel for rel in SZENEN_DATEIEN
                if "_webgl_gate.nach_szenen_timeout" not in self._quelle(rel)]
        self.assertEqual([], ohne,
                         f"Diese Dateien entscheiden wieder selbst: {ohne}")

    def test_keine_datei_haelt_eine_eigene_kopie(self):
        """Weder den Klassifikator noch die Diagnose — beides stand dreifach da."""
        kopien = []
        for rel in SZENEN_DATEIEN:
            quelle = self._quelle(rel)
            for merkmal in ("def ist_gl_kontext_ausfall", "_DIAG_JS = ("):
                if merkmal in quelle:
                    kopien.append(f"{rel}: {merkmal}")
        self.assertEqual([], kopien,
                         "eine eigene Kopie ist zurueck — genau der Zustand, "
                         f"den QA-74 aufgeraeumt hat: {kopien}")

    def test_die_liste_deckt_wirklich_die_show_dateien_ab(self):
        """★ Ohne das waere die Pruefung oben trivial: eine leere Liste hat
        keine Luecken.

        Geprueft wird gegen das gemessene Merkmal aus XPLAT-17 — den Ausfall
        sehen nur Dateien, die ``view.show()`` rufen.
        """
        import glob
        mit_show = []
        eigene = os.path.basename(os.path.abspath(__file__))
        for pfad in glob.glob(os.path.join(REPO, "tests", "test_*.py")):
            # ⚠ Diese Datei selbst ausnehmen: sie HANDELT vom Muster und
            # nennt es in Docstring und Kommentaren, ist aber keine
            # Szenen-Datei. Ohne die Ausnahme findet der Waechter sich
            # selbst — beim Bau prompt zweimal passiert. Dieselbe Falle
            # wie in test_gate_runner_parity (dort schrieb proc02d
            # Dateinamen in ein Wegwerf-Repo) und beim ersten Anlauf
            # dieser Pruefung.
            if os.path.basename(pfad) == eigene:
                continue
            with open(pfad, encoding="utf-8") as f:
                quelle = f.read()
            # ⚠ Der AUFRUF, nicht die Erwaehnung: eine blosse Textsuche nach
            # ".show()" traf beim Bau dieses Waechters prompt seinen eigenen
            # Docstring. Dieselbe Falle wie in test_gate_runner_parity
            # (dort schrieb proc02d Dateinamen in ein Wegwerf-Repo).
            if "__lightosAppReady" in quelle and "._view.show()" in quelle:
                # (self._view.show() und cls._view.show() - `drag` ruft
                #  es in setUpClass, die anderen beiden je Test.)
                mit_show.append("tests/" + os.path.basename(pfad))
        self.assertEqual(sorted(SZENEN_DATEIEN), sorted(mit_show),
                         "die Liste der Szenen-Dateien passt nicht mehr zu den "
                         "Dateien, die view.show() rufen — eine neue steht "
                         "womoeglich ohne Waechter da")


if __name__ == "__main__":
    unittest.main()
