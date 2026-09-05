"""FM-9/A5 — das VC-XY-Pad respektiert die Kopf-Auswahl.

Ausgangslage: Programmer-Regler (A1), Fächer/Snaps (A2), EFX (A3) und der
VC-Submaster (A4) sind kopf-fähig. Das XY-Pad war die letzte VC-Fläche, die
Pan/Tilt weiterhin geräteweit schrieb — „Kopf 2" gewählt, und trotzdem fuhren
alle vier Köpfe einer Bar.

★ Der eigentliche Trap liegt aber NICHT im Durchreichen des Kopf-Index, sondern
in der Frage, gegen WELCHE Kopfzahl man die Auswahl validiert. ``validate_head_
restrictions`` zählte hart die **Farb**köpfe (``color_r``) — und Farb- und
Bewegungsköpfe sind nicht dieselbe Zahl. **Über die eingebaute Library
ausgezählt (5116 Modi) gehen beide Zählungen bei 831 Modi auseinander:**

* **108 Modi** haben ``>=2`` Bewegungs-, aber ``<2`` Farbköpfe — darunter die
  gängigen Moving-Bars (``Event Bar LED/Pro/Q4``, ``HYDRABEAM 4000 RGBW`` in
  ``19-Kanal``/``32-Kanal``, ``Hydrabeam 400 Series`` ``15-CH``/``28-CH``). Mit
  der Farb-Zählung wird die Einschränkung **verworfen** → „Kopf 2" gewählt und
  trotzdem fahren alle vier. Das ist der Fall, den A5 überhaupt reparieren soll.
* **723 Modi** haben ``>=2`` Farb-, aber ``<2`` Bewegungsköpfe — Pixel-Bars und
  die vier Spider aus Davids Patch (``Speider 14ch``, ``Mini Spider ZQ-B20``).
  Dort wird die Einschränkung fälschlich **behalten** und erzeugt ``pan#1``.

Was ``pan#1`` auf einem Ein-Pan-Gerät wirklich tut, ist gemessen, nicht vermutet:
``_flush_programmer_to_dmx`` läuft über die KANÄLE, der einzige Pan-Kanal fragt
also nach ``"pan"``; ``pan#1`` liest niemand. Der Kanal fällt damit auf seinen
``default_value`` zurück — der Kopf **springt auf seine Default-Position und
folgt dem Pad nicht mehr**. Gemessen: Default 128, Pad schrieb 200, Kanal blieb
128. Kein Fehler, keine Meldung.

Wächter dafür: ``BewegungsKopfzahlTests``.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core import app_state as A  # noqa: E402
from src.ui.virtualconsole.vc_xypad import VCXYPad  # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Ch:
    def __init__(self, attribute):
        self.attribute = attribute


class _Fx:
    def __init__(self, fid, channels, fixture_type=""):
        self.fid = fid
        self.channels = channels
        self.fixture_type = fixture_type


def _mover(fid, heads, *, with_fine=False, colors=None):
    """Mehrkopf-Mover: ``heads`` Pan/Tilt-Paare, optional eigene Farbbänke."""
    ch = []
    for _ in range(heads):
        ch.append(_Ch("pan"))
        if with_fine:
            ch.append(_Ch("pan_fine"))
        ch.append(_Ch("tilt"))
        if with_fine:
            ch.append(_Ch("tilt_fine"))
    for _ in range(colors if colors is not None else heads):
        ch += [_Ch("color_r"), _Ch("color_g"), _Ch("color_b")]
    return _Fx(fid, ch)


def _spider(fid):
    """Der reale Fall aus Davids Patch: 2 Farbbänke, aber nur EIN Pan/Tilt."""
    ch = [_Ch("pan"), _Ch("tilt"), _Ch("dimmer")]
    for _ in range(2):
        ch += [_Ch("color_r"), _Ch("color_g"), _Ch("color_b"), _Ch("color_w")]
    return _Fx(fid, ch)


class _FakeState:
    """Nur die von ``_apply``/``_resolve_heads`` berührte Oberfläche."""

    def __init__(self, fixtures, cells):
        self._fx = {f.fid: f for f in fixtures}
        self._cells = list(cells)
        self.writes = []          # (fid, key, value)

    # — Auswahl —
    def get_selected_cells(self):
        return list(self._cells)

    def get_selected_fids(self):
        from src.core.group_cells import base_fids_in_cells
        return base_fids_in_cells(self._cells)

    def get_patched_fixtures(self):
        return list(self._fx.values())

    # — Schreiben —
    def set_programmer_value(self, fid, attribute, value, undoable=False, head=0):
        key = attribute if not head else f"{attribute}#{int(head)}"
        self.writes.append((fid, key, value))

    # — von validate_head_restrictions benutzt —
    def validate_head_restrictions(self, heads, *, count_heads=None):
        return A.AppState.validate_head_restrictions(
            self, heads, count_heads=count_heads)

    def fids_ohne_bedienbaren_kopf(self, heads, *, count_heads=None):
        return A.AppState.fids_ohne_bedienbaren_kopf(
            self, heads, count_heads=count_heads)

    def _head_restrictions_geprueft(self, heads, count_heads=None):
        return A.AppState._head_restrictions_geprueft(
            self, heads, count_heads)

    def nur_bedienbare_fids(self, fids, heads, *, count_heads=None):
        # FM-45/2 — wie die Schwester darueber an die ECHTE Regel
        # delegiert. Die GANZE Kette, nicht nur der Einstieg: die
        # Methode ruft intern `self.fids_ohne_bedienbaren_kopf`, und
        # eine Attrappe, der die fehlt, laesst den Aufrufer in seinen
        # `except`-Zweig laufen statt zu delegieren.
        return A.AppState.nur_bedienbare_fids(
            self, fids, heads, count_heads=count_heads)

    def keys_for(self, fid):
        return sorted({k for f, k, _v in self.writes if f == fid})


def _install(test, state):
    """Fake-State und Fake-Kanäle einhängen — und zwar so, dass die ECHTE
    ``VCXYPad._apply`` läuft: sie holt sich den State per ``get_state()`` aus
    ``src.core.app_state``, also wird genau dieses Modulattribut umgelenkt. Ein
    nachgebauter ``_apply``-Rumpf im Test würde die Änderung nicht absichern."""
    orig_ch, orig_state = A.get_channels_for_patched, A.get_state
    A.get_channels_for_patched = lambda fx: list(getattr(fx, "channels", []))
    A.get_state = lambda: state

    def _restore():
        A.get_channels_for_patched = orig_ch
        A.get_state = orig_state

    test.addCleanup(_restore)
    return state


def _pad(*, bits16=False, fixed=None):
    pad = VCXYPad("xy")
    pad.bits16 = bits16
    if fixed:
        pad._fixture_ids = list(fixed)
    pad._pan, pad._tilt = 0.5, 0.25
    return pad


class KopfAuswahlTests(unittest.TestCase):
    def test_gewaehlter_kopf_bekommt_nur_seine_kanaele(self):
        fx = _mover(1, 4)
        st = _install(self, _FakeState([fx], ["1:1"]))
        pad = _pad()
        pad._apply()
        self.assertEqual(st.keys_for(1), ["pan#1", "tilt#1"])

    def test_mehrere_koepfe_gleichzeitig(self):
        fx = _mover(1, 4)
        st = _install(self, _FakeState([fx], ["1:1", "1:3"]))
        pad = _pad()
        pad._apply()
        self.assertEqual(st.keys_for(1), ["pan#1", "pan#3", "tilt#1", "tilt#3"])

    def test_ohne_kopf_zelle_bleibt_es_geraeteweit(self):
        """Bestandsverhalten: ganze Zelle -> schlichte Attributnamen, kein ``#N``."""
        fx = _mover(1, 4)
        st = _install(self, _FakeState([fx], ["1"]))
        pad = _pad()
        pad._apply()
        self.assertEqual(st.keys_for(1), ["pan", "tilt"])

    def test_ganzes_geraet_schlaegt_kopf_zellen(self):
        """Vorrang-Regel aus ``head_restrictions``: die gröbere Aussage gewinnt."""
        fx = _mover(1, 4)
        st = _install(self, _FakeState([fx], ["1", "1:2"]))
        pad = _pad()
        pad._apply()
        self.assertEqual(st.keys_for(1), ["pan", "tilt"])

    def test_alle_koepfe_gewaehlt_ist_das_ganze_geraet(self):
        fx = _mover(1, 3)
        cells = ["1:0", "1:1", "1:2"]
        st = _install(self, _FakeState([fx], cells))
        pad = _pad()
        pad._apply()
        self.assertEqual(st.keys_for(1), ["pan", "tilt"])

    def test_kopf_ausserhalb_des_bereichs_faehrt_GAR_NICHTS(self):
        """★★ UMGEKEHRT seit FM-45 Scheibe 2.

        Vorher fiel „Kopf 8" an einem 2-Kopf-Mover auf ``pan``/``tilt``
        zurueck, also auf das ganze Geraet. Genau diese Zeile stand fuer die
        stille Ausweitung, gegen die FM-45/2 antritt: gemeint war ein Kopf,
        gefahren wurde alles. Begruendung ausfuehrlich in
        ``test_fm27_fm28_fm29_kopf_zaehlung.py`` (Altlast-Zelle) und
        ``test_fm45_auswahl_phantomkopf.py``.
        """
        fx = _mover(1, 2)
        st = _install(self, _FakeState([fx], ["1:7"]))
        pad = _pad()
        pad._apply()
        self.assertEqual(st.keys_for(1), [],
                         "der Phantom-Kopf faehrt weiter das ganze Geraet")


class BewegungsKopfzahlTests(unittest.TestCase):
    """★ Beide Richtungen, in denen Farb- und Bewegungs-Kopfzahl auseinandergehen.

    Die Farb-Zählung liegt in **831 von 5116** Library-Modi falsch — und zwar in
    beide Richtungen. Ein Test je Richtung, plus je eine Gegenprobe, dass die
    alte Zählung den Fehler wirklich produziert hätte."""

    # ── Richtung A: viele Bewegungs-, wenige Farbköpfe (108 Modi) ─────────────
    def test_moving_bar_ohne_pro_kopf_farbe_behaelt_die_kopf_auswahl(self):
        """``Event Bar LED``/``HYDRABEAM 4000 RGBW [19-Kanal]``: 4 Pan/Tilt, aber
        nur EINE Farbbank. Mit der Farb-Zählung fiele die Einschränkung weg und
        alle vier Köpfe führen — genau der Bug, den A5 reparieren soll."""
        fx = _mover(5, 4, colors=1)
        st = _install(self, _FakeState([fx], ["5:2"]))
        pad = _pad()
        pad._apply()
        self.assertEqual(st.keys_for(5), ["pan#2", "tilt#2"])

    def test_gegenprobe_farbzaehlung_wuerde_hier_verwerfen(self):
        fx = _mover(5, 4, colors=1)
        st = _install(self, _FakeState([fx], ["5:2"]))
        self.assertEqual(st.validate_head_restrictions({5: {2}}), {})
        self.assertEqual(
            st.validate_head_restrictions(
                {5: {2}}, count_heads=A.move_head_count_for_channels), {5: {2}})

    # ── Richtung B: viele Farb-, wenige Bewegungsköpfe (723 Modi) ─────────────
    def test_spider_bewegt_sich_weiterhin_geraeteweit(self):
        """Davids vier Spider: 2 Farbbänke, 1 Pan/Tilt. ``pan#1`` liest hier
        niemand — ``_flush_programmer_to_dmx`` läuft über die KANÄLE, und der
        einzige Pan-Kanal fragt nach ``"pan"``. Der Kanal fiele auf seinen
        ``default_value`` zurück: der Kopf springt auf Default-Position und folgt
        dem Pad nicht mehr (gemessen: Default 128, Pad schrieb 200, blieb 128)."""
        fx = _spider(27)
        st = _install(self, _FakeState([fx], ["27:1"]))
        pad = _pad()
        pad._apply()
        self.assertEqual(
            st.keys_for(27), ["pan", "tilt"],
            "Spider hat nur EINEN Pan/Tilt — 'pan#1' liest kein Kanal, der Kopf "
            "fiele auf seinen Default-Wert und folgte dem Pad nicht mehr")

    def test_gegenprobe_farbzaehlung_wuerde_hier_behalten(self):
        fx = _spider(27)
        st = _install(self, _FakeState([fx], ["27:1"]))
        self.assertEqual(st.validate_head_restrictions({27: {1}}), {27: {1}})
        self.assertEqual(
            st.validate_head_restrictions(
                {27: {1}}, count_heads=A.move_head_count_for_channels), {})


class FeineKanaeleTests(unittest.TestCase):
    def test_16bit_fine_kanal_traegt_denselben_kopf_index(self):
        fx = _mover(1, 4, with_fine=True)
        st = _install(self, _FakeState([fx], ["1:2"]))
        pad = _pad(bits16=True)
        pad._apply()
        self.assertEqual(st.keys_for(1),
                         ["pan#2", "pan_fine#2", "tilt#2", "tilt_fine#2"])

    def test_16bit_geraeteweit_bleibt_ohne_suffix(self):
        fx = _mover(1, 4, with_fine=True)
        st = _install(self, _FakeState([fx], ["1"]))
        pad = _pad(bits16=True)
        pad._apply()
        self.assertEqual(st.keys_for(1),
                         ["pan", "pan_fine", "tilt", "tilt_fine"])


class FesteZuweisungTests(unittest.TestCase):
    def test_festes_pad_ignoriert_die_kopf_auswahl(self):
        """Feste Zuweisung ist eine ausdrückliche Ansage — dieselbe Vorrang-Regel
        wie beim VC-Submaster (A4)."""
        fx = _mover(1, 4)
        st = _install(self, _FakeState([fx], ["1:1"]))
        pad = _pad(fixed=[1])
        pad._apply()
        self.assertEqual(st.keys_for(1), ["pan", "tilt"])


class RegressionSubmasterTests(unittest.TestCase):
    def test_default_zaehlung_bleibt_die_farb_zaehlung(self):
        """A4 (VC-Submaster) darf sich nicht mitverändern: ohne ``count_heads``
        entscheidet weiterhin die Farb-Kopfzahl."""
        fx = _mover(9, 1, colors=4)          # 1 Pan/Tilt, aber 4 Farbbänke
        st = _install(self, _FakeState([fx], []))
        self.assertEqual(st.validate_head_restrictions({9: {2}}), {9: {2}})



if __name__ == "__main__":
    unittest.main()
