"""VIZ-50b — die Warmweiss-Leiste des ZQ06121 als eigenes Band.

**Der Befund.** Robins ZQ06121 hat neben seinen 48 RGB-Zonen acht
Warmweiss-Segmente. Sie liegen NICHT auf dem Farbraster: die Leiste laeuft
mittig zwischen Reihe 2 und 3 durch, ist halb so hoch wie eine RGB-Zone, und
ihre acht Segmente decken die zwoelf Spalten ab — je anderthalb also. Im 3D gab
es sie schlicht nicht; ``buildMatrixPanel`` kannte nur die Farbzonen.

**Die Entscheidung, die dieses Item traegt: die ZAHL der Segmente steht in
keinem eigenen Feld.** Woher weiss der Renderer, dass dieses Geraet acht
Weiss-Segmente hat? Aus den KANAELEN des Modus — acht mit dem Attribut
``color_w`` neben 48 mit ``color_r``. Diese Angabe steht seit dem Anlegen des
Geraets in der Bibliothek; die attr#N-Konvention macht daraus die Koepfe 0..7,
und deren Werte reisen als ``heads[j].cw`` laengst in jeder DMX-Nutzlast mit.
Ein zusaetzliches Feld „Anzahl Weiss-Segmente" waere eine KOPIE dieser Zahl —
und eine Kopie, die niemand gegenprueft, laeuft still daneben (FM16E). Gemessen
wird deshalb nicht, ob ein Feld gesetzt ist, sondern ob die Ableitung stimmt:
hier, an der Bibliothek und am echten DMX-Weg.

★ **Was CDX-52 daran korrigiert hat.** Aus derselben Zahl wurde damals auch
geschlossen, OB das Geraet ueberhaupt eine eigene Leiste hat
(``0 < weiss < zonen``) — und das trug sie nicht: eine Kanalzahl hat keine
Ortsangabe. Diese eine Angabe hat seitdem ein Feld
(``FixtureMode.white_rows/white_cols``, gemessen in
``test_cdx52_weissband_geometrie.py``). Die Zahl der Segmente kommt weiterhin
aus den Kanaelen — dieses Modul misst genau das.

Was in dieser Datei geprueft wird, in der Reihenfolge des Datenwegs:

1. **Die Quelle** — die Bibliothek traegt die acht ``color_w``-Kanaele wirklich,
   und zwar nur in dem Modus, der sie hat.
2. **Die Regel** — die Zahl der Segmente ist die Zahl der ``color_w``-Kanaele,
   und ohne solche Kanaele gibt es kein Band. (Dass ein Geraet ueberhaupt eine
   eigene Leiste HAT, sagt seit CDX-52 die hinterlegte Form; RGBW-Emitter, deren
   Weiss zum Pixel gehoert und ueber ``visual_rgb`` schon in dessen Farbe
   steckt, bekommen darum keine.)
3. **Der DMX-Weg** — Weiss-Segment j sitzt wirklich auf Kopf j: gemessen ueber
   ``_collect_attrs`` + ``_build_fixture_payload`` an einem echten Universum,
   nicht an einem von Hand gebauten attrs-Dict.
4. **Die Nutzlast** — ``nWhites`` kommt in ``_fixture_to_dict`` an.

★ **Positivkontrolle durchgehend:** ein Geraet ohne eigene Weiss-Segmente darf
kein Band bekommen. Der schaerfste Fall ist DASSELBE Geraet im anderen Modus
(ZQ06121 144-Kanal): gleiche Zonen, gleiche Rasterform, nur ohne Weiss.

Was daraus im BILD wird — Zahl, Lage, Groesse der Segmente und ihre Farbe aus
den eigenen Kanaelen — misst ``test_viz50b_weissband_scene.py`` in echter
QWebEngine.
"""
from __future__ import annotations

import os
import types
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                  # noqa: E402
from sqlalchemy.orm import Session, selectinload               # noqa: E402

from _fixture_quelle import frische_library                    # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureMode, FixtureProfile, PatchedFixture)


def _profil(session, short):
    return session.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.modes))
        .where(FixtureProfile.short_name == short)
    ).scalars().first()


def _patched(profile_id, mode_name, channel_count, **kw):
    return PatchedFixture(fid=kw.pop("fid", 1), label=kw.pop("label", "Panel"),
                          fixture_profile_id=profile_id, mode_name=mode_name,
                          universe=kw.pop("universe", 1),
                          address=kw.pop("address", 1),
                          channel_count=channel_count,
                          fixture_type=kw.pop("fixture_type", "matrix"), **kw)


_ZQ_WEISS = "154-Kanal 48 Zonen RGB + 8x Weiss"
_ZQ_OHNE = "144-Kanal 48 Zonen RGB"


class _LibraryCase(unittest.TestCase):
    """Frisch aus dem Quelltext geseedete Bibliothek (FIXTEST-FRESH)."""

    def setUp(self):
        from src.core.app_state import clear_channel_cache
        self._eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)

    def _ids(self, short):
        with Session(self._eng) as s:
            p = _profil(s, short)
            self.assertIsNotNone(p, f"Profil {short} fehlt in der Bibliothek")
            return p.id, {m.name: m.channel_count for m in p.modes}


# ════════════════════════════════════════════════════════════════════════════
# 1. Die Quelle: die Bibliothek traegt die Weiss-Segmente als Kanaele
# ════════════════════════════════════════════════════════════════════════════

class QuelleTest(_LibraryCase):
    """★ Ohne diese Zahlen gibt es nichts abzuleiten. Sie stehen nicht in einem
    Geometriefeld, sondern in den Kanaelen — deshalb werden sie hier gezaehlt
    und nicht nachgeschlagen."""

    def _zaehle(self, short, mode_name):
        with Session(self._eng) as s:
            m = s.execute(
                select(FixtureMode)
                .options(selectinload(FixtureMode.channels))
                .join(FixtureProfile)
                .where(FixtureProfile.short_name == short,
                       FixtureMode.name == mode_name)
            ).scalars().one()
            attrs = [c.attribute for c in m.channels]
            return attrs.count("color_r"), attrs.count("color_w")

    def test_der_weiss_modus_hat_acht_weiss_kanaele_auf_48_zonen(self):
        self.assertEqual(self._zaehle("ZQ06121", _ZQ_WEISS), (48, 8))

    def test_derselbe_balken_ohne_weiss_modus_hat_keine(self):
        """★ Positivkontrolle am schaerfsten Fall: dasselbe Geraet, dieselbe
        Rasterform, nur der andere Modus. Wer die Zahl am PROFIL statt am Modus
        ableitete, bekaeme hier acht Segmente, die es in diesem Betrieb nicht
        gibt."""
        self.assertEqual(self._zaehle("ZQ06121", _ZQ_OHNE), (48, 0))

    def test_die_weiss_kanaele_liegen_hinter_den_zonen(self):
        """Die attr#N-Konvention vergibt die Kopf-Nummern in KANALREIHENFOLGE.
        Dass die acht Weiss-Kanaele am Ende stehen, ist also kein Schoenheits-
        detail: es entscheidet, ob Segment j auf Kopf j landet (naechster
        Abschnitt misst genau das am DMX-Weg)."""
        with Session(self._eng) as s:
            m = s.execute(
                select(FixtureMode)
                .options(selectinload(FixtureMode.channels))
                .join(FixtureProfile)
                .where(FixtureProfile.short_name == "ZQ06121",
                       FixtureMode.name == _ZQ_WEISS)
            ).scalars().one()
            nach_nummer = sorted(m.channels, key=lambda c: c.channel_number)
            weiss = [i for i, c in enumerate(nach_nummer)
                     if c.attribute == "color_w"]
            self.assertEqual(weiss, list(range(146, 154)),
                             "die acht Weiss-Kanaele muessen die letzten sein")


# ════════════════════════════════════════════════════════════════════════════
# 2. Der DMX-Weg: Segment j sitzt auf Kopf j
# ════════════════════════════════════════════════════════════════════════════

def _universe(values: dict[int, int]):
    class _U:
        def get_channel(self, addr):
            return values.get(addr, 0)
    return _U()


class KopfZuordnungTest(_LibraryCase):
    """★ Die Behauptung, auf der das ganze Band steht: ``heads[j].cw`` ist der
    Wert von Weiss-Segment j+1. Sie wird hier NICHT angenommen, sondern ueber
    den echten Weg gemessen — echte Kanaele aus der Bibliothek, echtes
    Universum, ``_collect_attrs`` (die attr#N-Vergabe) und
    ``_build_fixture_payload`` (der Kopf-Bau). Ein von Hand gebautes
    attrs-Dict haette sich die guenstige Voraussetzung selbst hergestellt."""

    def _payload(self, werte: dict[int, int]):
        from src.ui.visualizer.visualizer_service import (
            VisualizerService, _build_fixture_payload)
        from src.core.app_state import get_channels_for_patched
        pid, modi = self._ids("ZQ06121")
        f = _patched(pid, _ZQ_WEISS, modi[_ZQ_WEISS], universe=0, address=1)
        state = SimpleNamespace(universes={0: _universe(werte)},
                                visualizer_positions={1: (0, 0, 0)},
                                visualizer_rotations={}, visualizer_docks={},
                                output_manager=None,
                                get_patched_fixtures=lambda: [f],
                                subscribe=lambda cb: None)
        svc = VisualizerService(state)
        attrs = svc._collect_attrs(f)
        return _build_fixture_payload(f, attrs, get_channels_for_patched(f))

    def test_weiss_segment_drei_landet_auf_kopf_zwei(self):
        # Kanalbild: 1 Dimmer, 2 Strobe, 3..146 die 48 RGB-Zonen,
        # 147..154 die acht Weiss-Segmente. Weiss-Segment 3 ist Kanal 149.
        p = self._payload({1: 255, 149: 200})
        heads = p["heads"]
        self.assertEqual(len(heads), 48, "48 Zonen ergeben 48 Koepfe")
        self.assertEqual(heads[2]["cw"], 200,
                         "Weiss-Segment 3 muss auf Kopf 2 liegen")
        for j in (0, 1, 3, 7, 8, 47):
            self.assertEqual(heads[j]["cw"], 0,
                             f"Kopf {j} darf kein fremdes Weiss zeigen")

    def test_nur_die_ersten_acht_koepfe_tragen_ueberhaupt_weiss(self):
        """★ Die Bedingung, aus der die BREITE des Bandes folgt: acht Segmente
        auf 48 Zonen. Waeren die Weiss-Kanaele ueber alle Koepfe verteilt, waere
        es kein Band, sondern ein RGBW-Raster."""
        werte = {1: 255}
        werte.update({147 + k: 10 + k for k in range(8)})
        heads = self._payload(werte)["heads"]
        traegt = [j for j, h in enumerate(heads) if h["cw"]]
        self.assertEqual(traegt, list(range(8)))
        self.assertEqual([heads[j]["cw"] for j in range(8)],
                         [10 + k for k in range(8)],
                         "die Reihenfolge der Segmente darf sich nicht drehen")

    def test_die_zone_traegt_ihre_eigene_farbe_getrennt_vom_weiss(self):
        """★★ Der Fall, der ein naiv gebautes Band entlarvt. Zone 1 ist ROT,
        Weiss-Segment 1 ist AUS. Wer das Band aus ``heads[j].r/g/b`` faerbt,
        malt es hier rot — denn diese Werte sind die Zonenfarbe (und tragen das
        Weiss zusaetzlich additiv, s. ``visual_rgb``). Nur ``cw`` trennt beides.
        """
        p = self._payload({1: 255, 3: 255})     # Kanal 3 = Zone 1 Rot
        h0 = p["heads"][0]
        self.assertEqual((h0["r"], h0["g"], h0["b"]), (255, 0, 0))
        self.assertEqual(h0["cw"], 0,
                         "ohne Weiss-Wert darf das Segment nichts anzeigen")

        # Umgekehrt: Weiss an, Zone aus.
        p2 = self._payload({1: 255, 147: 255})  # Kanal 147 = Weiss-Segment 1
        h0b = p2["heads"][0]
        self.assertEqual(h0b["cw"], 255)
        self.assertEqual(h0b["cr"], 0,
                         "der Rot-KANAL der Zone bleibt unberuehrt")


# ════════════════════════════════════════════════════════════════════════════
# 3. Die Regel: wann hat ein Geraet ein eigenes Band?
# ════════════════════════════════════════════════════════════════════════════

def _dict_for(f):
    from src.ui.visualizer.visualizer_window import VisualizerBridge
    fake_self = SimpleNamespace(_state=SimpleNamespace(
        visualizer_positions={}, visualizer_rotations={}, visualizer_docks={}))
    fake_self._viz_model_for = types.MethodType(
        VisualizerBridge._viz_model_for, fake_self)
    return VisualizerBridge._fixture_to_dict(fake_self, f)


class BandRegelTest(_LibraryCase):
    """``nWhites`` ist die abgeleitete Zahl der EIGENEN Weiss-Segmente.
    ``0`` heisst „dieses Geraet hat keine" — und nur daran erkennt der
    Renderer, dass er nichts zusaetzlich zeichnen soll."""

    def test_der_balken_bringt_acht_segmente_mit(self):
        pid, modi = self._ids("ZQ06121")
        d = _dict_for(_patched(pid, _ZQ_WEISS, modi[_ZQ_WEISS]))
        self.assertEqual(d["model"], "matrix")
        self.assertEqual(d["nHeads"], 48)
        self.assertEqual(d["nWhites"], 8)

    def test_derselbe_balken_im_anderen_modus_bekommt_kein_band(self):
        """★ Positivkontrolle am schaerfsten Fall (s. Modul-Kopf)."""
        pid, modi = self._ids("ZQ06121")
        d = _dict_for(_patched(pid, _ZQ_OHNE, modi[_ZQ_OHNE], fid=2))
        self.assertEqual(d["nHeads"], 48)
        self.assertEqual((d["gridRows"], d["gridCols"]), (4, 12),
                         "die Rasterform bleibt dieselbe (Vorbedingung)")
        self.assertEqual(d["nWhites"], 0,
                         "ohne Weiss-Kanaele darf kein Band entstehen")

    def test_ein_gewoehnliches_panel_bekommt_kein_band(self):
        """★ Positivkontrolle fuer den Normalfall: die Panels, die es heute
        gibt, duerfen sich um keinen Pixel aendern."""
        for short, mode in (("MATRIXPANEL", "8×8 (64 Pixel RGB)"),
                            ("DOTZMATRIX", "48-Kanal 16 Pixel RGB"),
                            ("STAIRPP144", "432-Kanal 144 Pixel RGB")):
            pid, modi = self._ids(short)
            d = _dict_for(_patched(pid, mode, modi[mode], fid=3))
            self.assertEqual(d["nWhites"], 0, f"{short} hat keine Weiss-Leiste")

    def test_rgbw_emitter_sind_kein_band(self):
        """★★ Die andere Haelfte der Regel, an einem echten Geraet gemessen:
        die PARBAR4 hat im 16-Kanal-Modus VIER Weiss-Kanaele auf vier Farb-
        banken — ein Weiss PRO Emitter. Dort gehoert das Weiss zum Emitter und
        steckt ueber ``visual_rgb`` schon in dessen Farbe; ein zusaetzliches
        Band waere dieselbe Information ein zweites Mal.

        Sie kommt hier gar nicht erst in die Zaehlung: ein Geraet ohne
        Bewegung wird als ``par_bar`` gerendert, und Weiss-Segmente zaehlt nur
        das Panel-Modell. Seit CDX-52 haelt zusaetzlich die fehlende hinterlegte
        Leiste den Fall auf — ein RGBW-Panel bleibt bandlos, auch wenn es eines
        Tages als ``matrix`` gerendert wird (gemessen in
        ``test_cdx52_weissband_geometrie.py``)."""
        pid, modi = self._ids("PARBAR4")
        name = "16-Kanal 4×RGBW"
        d = _dict_for(_patched(pid, name, modi[name], fid=4,
                               fixture_type="led_bar"))
        self.assertEqual(d["nHeads"], 4, "vier Farbbanken (Vorbedingung)")
        self.assertEqual(d["nWhites"], 0,
                         "ein Weiss je Emitter ist kein eigenes Band")

    def test_ein_geraet_ohne_koepfe_faellt_nicht_auf_die_nase(self):
        """Ein einfacher RGBW-PAR hat genau ein ``color_w`` und ein
        ``color_r``. Kein Multi-Emitter-Modell, also gar keine Zaehlung — und
        auf keinen Fall ein Band."""
        pid, modi = self._ids("PARW")
        name = "4-Kanal RGBW"
        d = _dict_for(_patched(pid, name, modi[name], fid=5,
                               fixture_type="par"))
        self.assertEqual(d["nHeads"], 0)
        self.assertEqual(d["nWhites"], 0)


class NutzlastUnveraendertTest(_LibraryCase):
    """★ Die Abnahmebedingung: der neue Schluessel darf nichts verdraengen und
    bei keinem Bestandsgeraet etwas behaupten."""

    def test_das_feld_ist_immer_da(self):
        """Wie bei ``gridRows``: JS haette sonst zwei Faelle zu unterscheiden
        (fehlt / ist 0), und einer davon wird irgendwann vergessen. Ein
        Moving-Head zaehlt seine Kanaele gar nicht erst — das Feld muss
        trotzdem in der Nutzlast stehen."""
        pid, modi = self._ids("MH8")
        d = _dict_for(_patched(pid, "8-Kanal", modi["8-Kanal"], fid=6,
                               fixture_type="moving_head"))
        self.assertEqual(d["model"], "moving_head")
        self.assertIn("nWhites", d)
        self.assertEqual(d["nWhites"], 0)

    def test_bestandsfelder_bleiben_vollstaendig(self):
        pid, modi = self._ids("DOTZMATRIX")
        d = _dict_for(_patched(pid, "3-Kanal RGB", modi["3-Kanal RGB"], fid=7))
        for schluessel in ("fid", "label", "type", "model", "nHeads",
                           "pixelOrder", "elementRotation", "elementFlip",
                           "gridRows", "gridCols", "mirror", "x", "y", "z",
                           "rotX", "rotY", "rotZ", "panRange", "tiltRange",
                           "panZero", "tiltZero", "dockedTo", "r", "g", "b",
                           "intensity", "pan", "tilt"):
            self.assertIn(schluessel, d)


if __name__ == "__main__":
    unittest.main()
