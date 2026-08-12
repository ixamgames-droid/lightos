"""TOOL-SMOKEDIM — „leuchtet" hiess nicht „das Geraet ist hell".

★ Der Anlass: am 2026-08-05 startete Robin in einer frisch gebauten Demo einen
Muster-Effekt, und **nichts leuchtete**. Dem Matrix-Effekt fehlte
``drive_intensity=True`` — er faerbte die Zonen, liess aber den Master-Dimmer
auf CH1 unberuehrt. Der Render-Smoke war gruen, ``lint_show.py --strict``
meldete 0 Fehler und 0 Warnungen, und das Geraet stand stockdunkel da.

**Warum kein Gate das sehen konnte:** ``render_diff`` bildet
``lit = irgendein Kanal > 0``. 144 Farbkanaele auf 255 erfuellen das muehelos.
Derselbe Effekt, einmal hell und einmal dunkel, ist fuer ``lit`` schlicht
ununterscheidbar — der Smoke prueft, ob die Software rechnet, nicht ob Licht
ankommt.

Diese Tests halten die Luecke zu, in beiden Fassungen (gemessen + statisch) und
jeweils mit Positivkontrolle: eine Pruefung, die alles beanstandet, ist genauso
wertlos wie eine, die nichts findet.

Das Herzstueck ist ``BuildAndVerifyDimmerTest`` — dort laeuft der **echte**
Renderer ueber ein **echtes** Profil (ZQ01424, 8-Kanal RGBW: CH1 = intensity),
einmal ohne und einmal mit ``drive_intensity``. Das ist genau die Messung aus
dem Item, nur automatisiert.
"""
import contextlib
import io
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                  # noqa: E402

import pytest as _pytest_xplat15                            # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets     # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


# ── (a) render_diff: der Schnappschuss ───────────────────────────────────────

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


class SchnappschussTest(unittest.TestCase):
    """(a) ``render_diff(..., return_snapshot=True)`` — rueckwaerts-vertraeglich."""

    def setUp(self):
        from unittest import mock
        from src.core.app_state import get_state
        # ⚠️ ZUERST den echten AppState anlegen. ``AppState.__init__`` merkt sich
        # den FunctionManager EINMAL (app_state.py:553) — entsteht das Singleton
        # erst unter dem Mock, haengt der MagicMock dauerhaft im Zustand und
        # jeder spaetere ``save_show`` stirbt an „not JSON serializable".
        _app()
        get_state()
        self.fm = mock.MagicMock()
        p = mock.patch("src.core.engine.function_manager.get_function_manager",
                       return_value=self.fm)
        p.start()
        self.addCleanup(p.stop)

    def test_ohne_schluesselwort_bleibt_es_beim_dreier_tupel(self):
        """★ Positivkontrolle fuer die Vertraeglichkeit: jeder Bestandsaufrufer
        packt drei Werte aus. Ein viertes Element waere ein ValueError."""
        from src.core.capability.render_probe import render_diff
        state = _FakeState({1: _FakeUniverse()})
        ergebnis = render_diff(state, [7], frames=2, warmup=1)
        self.assertEqual(3, len(ergebnis))
        lit, moved, changed = ergebnis          # muss auspackbar bleiben
        self.assertFalse(lit)
        self.assertFalse(moved)
        self.assertEqual([], changed)

    def test_schnappschuss_traegt_die_kanalwerte(self):
        from src.core.capability.render_probe import render_diff
        u = _FakeUniverse()
        state = _FakeState({1: u})
        original = state._render_frame

        def rendern(dt):
            original(dt)
            u.set(10, 200)

        state._render_frame = rendern
        lit, moved, changed, snap = render_diff(
            state, [7], frames=2, warmup=1, return_snapshot=True)
        self.assertTrue(lit)
        self.assertEqual(200, snap.ende[10])
        self.assertEqual(200, snap.hoechstwert[10])
        self.assertEqual(0, snap.basis[10], "die Basis wird VOR dem Start gelesen")

    def test_dunkle_kanaele_stehen_mit_null_drin(self):
        """★★ Die Falle: ein Maximum, das nur „groesser als bisher" einsammelt,
        laesst genau die durchweg dunklen Kanaele WEG — und das sind die
        gesuchten. Wer sie nicht findet, kann „gemessen und dunkel" nicht von
        „gar nicht gemessen" unterscheiden und schweigt beide Male."""
        from src.core.capability.render_probe import render_diff
        u = _FakeUniverse()
        state = _FakeState({1: u})
        original = state._render_frame

        def rendern(dt):
            original(dt)
            u.set(2, 255)          # Farbe an, Kanal 1 (Dimmer) bleibt 0

        state._render_frame = rendern
        _l, _m, _c, snap = render_diff(state, [7], frames=2, warmup=1,
                                       return_snapshot=True)
        self.assertIn(1, snap.hoechstwert, "der dunkle Kanal fehlt im Ergebnis")
        self.assertEqual(0, snap.hoechstwert[1])

    def test_ein_blinker_gilt_nicht_als_dunkel(self):
        """★★ Die entscheidende Anti-Fehlalarm-Eigenschaft: ein Chase/Blinker
        steht im letzten Frame regelmaessig auf 0. Wer den Dimmer am ENDBILD
        beurteilt, meldet ausgerechnet die auffaelligsten Effekte als „dunkel".
        Darum ist ``hoechstwert`` das Maximum ueber ALLE Frames."""
        from src.core.capability.render_probe import render_diff
        u = _FakeUniverse()
        state = _FakeState({1: u})
        original = state._render_frame

        def rendern(dt):
            original(dt)
            u.set(1, 255 if state.frames % 2 else 0)   # blinkt, endet auf 0

        state._render_frame = rendern
        _lit, _moved, _changed, snap = render_diff(
            state, [7], frames=4, warmup=0, return_snapshot=True)
        self.assertEqual(0, snap.ende[1], "das Endbild ist wirklich dunkel")
        self.assertEqual(255, snap.hoechstwert[1],
                         "waehrend der Probe war der Kanal aber oben")

    def test_assert_not_inert_reicht_den_schnappschuss_durch(self):
        """``assert_not_inert`` setzt den Rueckgabewert nicht neu zusammen —
        sonst faellt das vierte Element hier still unter den Tisch, und der
        Aufrufer bekommt ein 3-Tupel, obwohl er den Schnappschuss angefordert
        hat."""
        from src.core.capability.render_probe import assert_not_inert
        u = _FakeUniverse()
        state = _FakeState({1: u})
        original = state._render_frame

        def rendern(dt):
            original(dt)
            u.set(3, 99)

        state._render_frame = rendern
        ergebnis = assert_not_inert(state, 7, frames=2, warmup=1,
                                    return_snapshot=True)
        self.assertEqual(4, len(ergebnis))
        self.assertEqual(99, ergebnis[3].hoechstwert[3])

    def test_ohne_schnappschuss_wird_nicht_abgetastet(self):
        """Die Pro-Frame-Abtastung kostet — sie darf nur laufen, wenn sie
        jemand liest. Gemessen an der Zahl der ``get_channel``-Aufrufe."""
        from src.core.capability.render_probe import render_diff

        class ZaehlendesUniversum(_FakeUniverse):
            def __init__(self):
                super().__init__()
                self.lesezugriffe = 0

            def get_channel(self, c):
                self.lesezugriffe += 1
                return super().get_channel(c)

        ohne = ZaehlendesUniversum()
        render_diff(_FakeState({1: ohne}), [7], frames=4, warmup=2)
        mit = ZaehlendesUniversum()
        render_diff(_FakeState({1: mit}), [7], frames=4, warmup=2,
                    return_snapshot=True)
        self.assertGreater(mit.lesezugriffe, ohne.lesezugriffe)


class VerifyRenderSchnappschussTest(unittest.TestCase):
    """Ueber mehrere Einzellaeufe muss der Hoechstwert das Maximum sein —
    sonst loescht der letzte Lauf aus, was der erste hochgezogen hat."""

    def test_hoechstwerte_werden_ueber_alle_funktionen_vereinigt(self):
        from unittest import mock
        from src.core.capability.render_probe import ProbeSchnappschuss
        from src.core.show.showbuilder.builder import ShowBuilder
        b = ShowBuilder.__new__(ShowBuilder)
        b.state = object()

        werte = {1: {5: 255}, 2: {6: 128}}

        def fake(_state, fids, **kw):
            self.assertTrue(kw.get("return_snapshot"))
            h = werte[fids[0]]
            return True, True, [], ProbeSchnappschuss(
                basis={}, ende=dict(h), hoechstwert=dict(h))

        with mock.patch("src.core.capability.render_probe.render_diff", fake):
            _lit, _moved, _changed, snap = b.verify_render(
                [1, 2], return_snapshot=True)
        self.assertEqual({5: 255, 6: 128}, snap.hoechstwert)


# ── (b) build_and_verify: die gemessene Fassung, echter Renderer ─────────────

def _baue(drive_intensity, kurzname="ZQ01424", kanalzahl=8,
          modus="8-Kanal RGBW"):
    """Baut die Show aus dem Item: ein Farbeffekt auf einem Geraet mit
    Master-Dimmer. Liefert die Ausgabe von ``build_and_verify``."""
    from tools._builder import build_and_verify, RgbAlgorithm
    from src.core.show.showbuilder.builder import ShowBuilder
    _app()
    b = ShowBuilder(reset=True)
    fids = b.patch(kurzname, count=2, channel_count=kanalzahl, mode_name=modus)
    mx = b.matrix("Farbe", algorithm=RgbAlgorithm.PLAIN, style="RGB",
                  fixtures=fids, colors=[(255, 255, 255)],
                  drive_intensity=drive_intensity)
    with tempfile.TemporaryDirectory() as ordner:
        ziel = os.path.join(ordner, "SmokeDim.lshow")
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            build_and_verify(b, ziel, render=[mx])
        return puffer.getvalue()


class BuildAndVerifyDimmerTest(unittest.TestCase):
    """★★ (b) Der echte Pfad: echtes Profil, echter Renderer, echtes DMX.

    ZQ01424 „8-Kanal RGBW" hat CH1 = ``intensity``, CH2..5 = RGBW. Genau die
    Bauart, an der es passiert ist.
    """

    def test_ohne_drive_intensity_wird_gewarnt(self):
        ausgabe = _baue(drive_intensity=False)
        self.assertIn("Master-Dimmer", ausgabe,
                      f"die Warnung fehlt — Ausgabe war:\n{ausgabe}")
        self.assertIn("dunkel", ausgabe)

    def test_mit_drive_intensity_bleibt_es_still(self):
        """★ Positivkontrolle. Derselbe Effekt, ein Schalter anders — und die
        Pruefung MUSS schweigen, sonst warnt sie in jeder gesunden Show."""
        ausgabe = _baue(drive_intensity=True)
        self.assertNotIn("Master-Dimmer", ausgabe, ausgabe)
        self.assertIn("OK:", ausgabe, "der Build muss trotzdem durchlaufen")

    def test_geraet_ohne_dimmer_wird_nie_gemeldet(self):
        """★ Positivkontrolle. PAR3 ist ein reiner RGB-PAR ohne Dimmerkanal —
        bei ihm gibt es nichts hochzuziehen."""
        ausgabe = _baue(drive_intensity=False, kurzname="PAR3", kanalzahl=3,
                        modus="3-Kanal RGB")
        self.assertNotIn("Master-Dimmer", ausgabe, ausgabe)

    def test_die_warnung_bricht_den_build_nicht_ab(self):
        """Ein Geraet darf bewusst dunkel bleiben. Ein harter Fehler wuerde
        Bestandsskripte brechen — deshalb Warnung, nicht Abbruch."""
        ausgabe = _baue(drive_intensity=False)
        self.assertIn("OK:", ausgabe, ausgabe)


class DunkleGeraeteFilterTest(unittest.TestCase):
    """Was die gemessene Fassung BEWUSST nicht behauptet."""

    def _state_mit_zq(self):
        from src.core.show.showbuilder.builder import ShowBuilder
        _app()
        b = ShowBuilder(reset=True)
        b.patch("ZQ01424", count=1, channel_count=8,
                mode_name="8-Kanal RGBW", universe=1, start_address=1)
        return b.state

    def test_dimmer_auf_null_wird_gemeldet(self):
        from src.core.capability.dimmer_check import dunkle_geraete
        state = self._state_mit_zq()
        # Farbkanaele voll, CH1 (Dimmer) auf 0 — die Messung aus dem Item.
        hoechst = {1: 0, 2: 255, 3: 255, 4: 255, 5: 255}
        self.assertEqual(1, len(dunkle_geraete(state, hoechst, universe=1)))

    def test_dimmer_oben_wird_nicht_gemeldet(self):
        """★ Positivkontrolle."""
        from src.core.capability.dimmer_check import dunkle_geraete
        state = self._state_mit_zq()
        self.assertEqual([], dunkle_geraete(
            state, {1: 255, 2: 255, 3: 255, 4: 255, 5: 255}, universe=1))

    def test_anderes_universum_ist_keine_aussage(self):
        """★ Ueber ein Universum, das die Probe gar nicht gemessen hat, darf
        nichts behauptet werden — sonst meldet jedes Mehr-Universen-Rig
        reihenweise Fehlalarme (vgl. TOOL-RENDERUNI)."""
        from src.core.capability.dimmer_check import dunkle_geraete
        state = self._state_mit_zq()
        self.assertEqual([], dunkle_geraete(state, {1: 0}, universe=3))

    def test_ohne_messwerte_fuer_den_kanal_kein_befund(self):
        """``channels=`` kann den Ausschnitt eingrenzen. Fehlt der Dimmerkanal
        im Schnappschuss, ist er nicht „0", sondern ungemessen."""
        from src.core.capability.dimmer_check import dunkle_geraete
        state = self._state_mit_zq()
        self.assertEqual([], dunkle_geraete(state, {200: 255}, universe=1))


# ── (c) lint_show: die statische Fassung ────────────────────────────────────

def _profil_id(kurzname):
    """Die ECHTE Profil-ID dieses Rechners — festverdrahtete Zahlen waeren auf
    jedem anderen Rechner etwas anderes."""
    from src.core.show.showbuilder.builder import ShowBuilder
    _app()
    return ShowBuilder(reset=False).profile_id(kurzname)


def _show(profil, *, drive_intensity=False, modus="8-Kanal RGBW", kanalzahl=8,
          funktionen=None, widgets=None, **rest):
    matrix = {"id": 1, "type": "RGBMatrix", "name": "Farbe",
              "algorithm": "PLAIN", "style": "RGB",
              "fixture_grid": [1], "drive_intensity": drive_intensity}
    show = {
        "patch": [{"fid": 1, "label": "PAR 1", "fixture_profile_id": profil,
                   "mode_name": modus, "universe": 1, "address": 1,
                   "channel_count": kanalzahl}],
        "functions": [matrix] + list(funktionen or []),
        "virtual_console": {"widgets": list(widgets or [])},
    }
    show.update(rest)
    return show


class StatischeFassungTest(unittest.TestCase):
    """(c) Ohne Rendern — was allein aus der Show-Datei ablesbar ist."""

    @classmethod
    def setUpClass(cls):
        cls.zq = _profil_id("ZQ01424")
        cls.par = _profil_id("PAR3")

    def _codes(self, show):
        from src.core.capability.dimmer_check import statische_befunde
        return [f.code for f in statische_befunde(show)]

    def test_faerbender_effekt_ohne_drive_intensity(self):
        """★★ Der Fall aus dem Item — statisch erkannt, ohne einen Frame."""
        from src.core.capability.dimmer_check import statische_befunde
        befunde = statische_befunde(_show(self.zq, drive_intensity=False))
        self.assertEqual(1, len(befunde), [str(b) for b in befunde])
        self.assertEqual("DIMMER-DUNKEL", befunde[0].code)
        self.assertEqual("warning", befunde[0].severity,
                         "ein Fehler wuerde Bestandsskripte brechen")
        self.assertIn("drive_intensity", befunde[0].message)

    def test_mit_drive_intensity_kein_befund(self):
        """★ Positivkontrolle."""
        self.assertEqual([], self._codes(_show(self.zq, drive_intensity=True)))

    def test_alt_show_ohne_den_schluessel_gilt_als_getrieben(self):
        """★ Positivkontrolle fuer Alt-Shows: ``rgb_matrix.from_dict`` liest
        einen fehlenden ``drive_intensity``-Schluessel als True. Wer hier
        anders raet, warnt reihenweise in Shows, die hell sind."""
        show = _show(self.zq)
        show["functions"][0].pop("drive_intensity")
        self.assertEqual([], self._codes(show))

    def test_dimmer_style_treibt_den_dimmer_ebenfalls(self):
        """★ Positivkontrolle: eine Matrix im Dimmer-Style schreibt AUSSCHLIESS-
        LICH auf die Dimmerkanaele — unabhaengig von ``drive_intensity``."""
        show = _show(self.zq, drive_intensity=False)
        show["functions"][0]["style"] = "Dimmer"
        self.assertEqual([], self._codes(show))

    def test_eine_szene_auf_dem_dimmer_entschaerft(self):
        """★ Positivkontrolle: eine Szene, die CH1 hochzieht, macht das Geraet
        hell — auch wenn die Matrix nur faerbt."""
        szene = {"id": 2, "type": "Scene", "name": "Dimmer auf",
                 "values": [{"fid": 1, "ch": 1, "val": 255}]}
        self.assertEqual([], self._codes(_show(self.zq, funktionen=[szene])))

    def test_eine_szene_mit_wert_null_entschaerft_nicht(self):
        """Gegenprobe zur Zeile darueber — sonst wuerde jede Szene, die den
        Kanal nur erwaehnt, die Warnung stumm schalten."""
        szene = {"id": 2, "type": "Scene", "name": "Dimmer zu",
                 "values": [{"fid": 1, "ch": 1, "val": 0}]}
        self.assertEqual(["DIMMER-DUNKEL"],
                         self._codes(_show(self.zq, funktionen=[szene])))

    def test_eine_sequence_auf_dem_dimmer_entschaerft(self):
        """★ Positivkontrolle: eine Sequence speichert je Schritt
        ``{fid: {attribut: wert}}`` — ein Intensity-Wert darin macht hell."""
        seq = {"id": 2, "type": "Sequence", "name": "Cue", "speed_hz": 0,
               "steps": [{"values": {"1": {"intensity": 200}}}]}
        self.assertEqual([], self._codes(_show(self.zq, funktionen=[seq])))

    def test_eine_sequence_ohne_helligkeit_entschaerft_nicht(self):
        """Gegenprobe: eine Sequence, die nur Farbe faehrt, hilft nicht."""
        seq = {"id": 2, "type": "Sequence", "name": "Cue", "speed_hz": 0,
               "steps": [{"values": {"1": {"color_r": 255}}}]}
        self.assertEqual(["DIMMER-DUNKEL"],
                         self._codes(_show(self.zq, funktionen=[seq])))

    def test_efx_mit_open_beam_entschaerft(self):
        """★ Positivkontrolle: ``open_beam`` faehrt Dimmer und Shutter auf
        (efx.write) — dann ist das Geraet hell, auch ohne drive_intensity."""
        efx = {"id": 2, "type": "EFX", "name": "Kreis", "motion": True,
               "speed_hz": 1.0, "algorithm": "Circle", "open_beam": True,
               "fixtures": [{"fid": 1, "offset": 0}]}
        self.assertEqual([], self._codes(_show(self.zq, funktionen=[efx])))

    def test_efx_ohne_open_beam_entschaerft_nicht(self):
        """Gegenprobe: eine EFX ohne ``open_beam`` bewegt nur — das Geraet
        bleibt dunkel, und genau darum geht es hier."""
        efx = {"id": 2, "type": "EFX", "name": "Kreis", "motion": True,
               "speed_hz": 1.0, "algorithm": "Circle", "open_beam": False,
               "fixtures": [{"fid": 1, "offset": 0}]}
        self.assertEqual(["DIMMER-DUNKEL"],
                         self._codes(_show(self.zq, funktionen=[efx])))

    def test_luecke_im_raster_ist_kein_geraet(self):
        """``fixture_grid`` darf ``None``-Luecken enthalten. Wer sie als fid
        liest, ordnet Effekte falschen Geraeten zu."""
        show = _show(self.zq)
        show["functions"][0]["fixture_grid"] = [None, 1, None]
        self.assertEqual(["DIMMER-DUNKEL"], self._codes(show))
        show["functions"][0]["fixture_grid"] = [None, None]
        self.assertEqual([], self._codes(show))

    def test_basiswert_auf_dem_dimmer_entschaerft(self):
        """★ Positivkontrolle: ein gespeicherter Basiswert haelt den Dimmer
        oben, ganz ohne laufende Funktion."""
        self.assertEqual([], self._codes(_show(
            self.zq, base_levels={"1": {"intensity": 255}})))

    def test_geraet_ohne_dimmer_erzeugt_nichts(self):
        """★ Positivkontrolle: PAR3 hat keinen Dimmerkanal."""
        self.assertEqual([], self._codes(_show(
            self.par, modus="3-Kanal RGB", kanalzahl=3)))

    def test_unbenutztes_geraet_wird_nicht_gemeldet(self):
        """★ Positivkontrolle und bewusste Grenze: ein gepatchtes Geraet, das
        KEIN Effekt anfasst (Reserve, von Hand gefahren), ist kein Befund —
        sonst warnte fast jede reale Show."""
        show = _show(self.zq)
        show["functions"][0]["fixture_grid"] = []
        self.assertEqual([], self._codes(show))

    def test_unlesbare_funktionsart_laesst_die_pruefung_schweigen(self):
        """★★ Ein Script kann jeden Kanal setzen; das ist aus dem Dict nicht
        ablesbar. Dann lieber gar nichts sagen als etwas Falsches."""
        show = _show(self.zq, funktionen=[
            {"id": 9, "type": "Script", "name": "Irgendwas"}])
        self.assertEqual([], self._codes(show))

    def test_hebender_regler_laesst_die_pruefung_schweigen(self):
        """Ein Level-Regler zieht Kanaele von Hand hoch — dann kann die Show
        hell sein, ohne dass eine Funktion das leistet."""
        show = _show(self.zq, widgets=[
            {"type": "VCSlider", "caption": "CH1", "mode": "Level"}])
        self.assertEqual([], self._codes(show))

    def test_grandmaster_schaltet_die_pruefung_nicht_stumm(self):
        """Gegenprobe: ein GrandMaster SKALIERT nur — aus einem dunklen Geraet
        macht er kein helles. Wuerde er die Pruefung stumm schalten, waere sie
        in praktisch jeder Show wirkungslos (fast jede hat einen)."""
        show = _show(self.zq, widgets=[
            {"type": "VCSlider", "caption": "Master", "mode": "GrandMaster"}])
        self.assertEqual(["DIMMER-DUNKEL"], self._codes(show))

    def test_unbekanntes_profil_erzeugt_keinen_befund(self):
        """★ Auf einem anderen Rechner steht das Profil nicht in der
        Bibliothek. „Kenne ich nicht" darf nicht wie „kein Dimmer" oder wie
        „dunkel" aussehen."""
        self.assertEqual([], self._codes(_show(999999)))

    def test_ohne_patch_block_keine_befunde(self):
        from src.core.capability.dimmer_check import statische_befunde
        self.assertEqual([], statische_befunde(
            {"functions": [], "virtual_console": {"widgets": []}}))


class LintShowIntegrationTest(unittest.TestCase):
    """Die statische Fassung muss auch wirklich im Linter ankommen."""

    def test_lint_meldet_die_warnung_an_einer_echten_show(self):
        from tools._builder import RgbAlgorithm
        from src.core.show.showbuilder.builder import ShowBuilder
        import tools.lint_show as lint
        _app()
        b = ShowBuilder(reset=True)
        fids = b.patch("ZQ01424", count=1, channel_count=8,
                       mode_name="8-Kanal RGBW")
        b.matrix("Farbe", algorithm=RgbAlgorithm.PLAIN, style="RGB",
                 fixtures=fids, colors=[(255, 255, 255)],
                 drive_intensity=False)
        with tempfile.TemporaryDirectory() as ordner:
            ziel = os.path.join(ordner, "Dunkel.lshow")
            b.save(ziel)
            puffer = io.StringIO()
            with contextlib.redirect_stdout(puffer):
                rc = lint.main(["--strict", ziel])
        ausgabe = puffer.getvalue()
        self.assertIn("DIMMER-DUNKEL", ausgabe, ausgabe)
        self.assertIn("1 Warnungen", ausgabe, ausgabe)
        self.assertEqual(1, rc, "--strict macht aus der Warnung einen Abbruch")

    def test_lint_bleibt_still_wenn_der_dimmer_getrieben_wird(self):
        """★ Positivkontrolle am echten Linter: dieselbe Show, ein Schalter
        anders — 0 Fehler, 0 Warnungen, Exit 0."""
        from tools._builder import RgbAlgorithm
        from src.core.show.showbuilder.builder import ShowBuilder
        import tools.lint_show as lint
        _app()
        b = ShowBuilder(reset=True)
        fids = b.patch("ZQ01424", count=1, channel_count=8,
                       mode_name="8-Kanal RGBW")
        b.matrix("Farbe", algorithm=RgbAlgorithm.PLAIN, style="RGB",
                 fixtures=fids, colors=[(255, 255, 255)],
                 drive_intensity=True)
        with tempfile.TemporaryDirectory() as ordner:
            ziel = os.path.join(ordner, "Hell.lshow")
            b.save(ziel)
            puffer = io.StringIO()
            with contextlib.redirect_stdout(puffer):
                rc = lint.main(["--strict", ziel])
        ausgabe = puffer.getvalue()
        self.assertNotIn("DIMMER-DUNKEL", ausgabe, ausgabe)
        self.assertEqual(0, rc, ausgabe)


if __name__ == "__main__":
    unittest.main()
