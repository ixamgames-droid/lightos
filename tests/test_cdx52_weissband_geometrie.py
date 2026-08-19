"""CDX-52 — das Weiss-Band kommt aus der Geometrie, nicht aus Kanalzahlen.

**Der Befund (Codex-Review zu VIZ-50b).** ``_fixture_to_dict`` stufte
``0 < n_whites < n_heads`` als „eigene Weiss-Leiste quer ueber die Mitte" ein.
Die Begruendung im Code stuetzte sich auf eine Messung ueber die mitgelieferte
Bibliothek — der Fixture-Editor erlaubt aber beliebige Profile. Ein
selbstgebautes Matrix-Profil mit 48 RGB-Pixeln und **einem** globalen
Weiss-Kanal erfuellte ``0 < 1 < 48`` und bekam ein volles Band ueber die ganze
Panelbreite, gefaerbt von ``heads[0].cw``.

★ **Eine Kanalzahl traegt keine Ortsangabe.** Das ist der ganze Befund. Dieselbe
Kanalsignatur (48x ``color_r`` + 8x ``color_w``) passt auf mindestens drei
physisch verschiedene Geraete: auf eine eigene Leiste zwischen den Zonen
(ZQ06121), auf acht Weiss-LEDs, die IN den Zonen sitzen und je sechs davon
teilen, und auf ein globales Weiss in acht Dimmabschnitten. Welches davon
vorliegt, entscheidet der Blick aufs Geraet — beim ZQ06121 Robins Messung vom
2026-08-05, die bis dahin nur in einem Quellkommentar stand.

**Was die Geometrie sagen kann und was nicht.** ``FixtureMode.grid_rows/cols``
(VIZ-50a) beschreibt das Raster der FARBZONEN. Es ist das Koordinatensystem, in
dem die Leiste liegt — aus ihm folgt, WO „mittig zwischen Reihe 2 und 3" ist.
Es sagt aber nichts darueber, OB es eine Leiste gibt: dasselbe 4x12-Raster
tragen beide ZQ06121-Modi, und nur einer hat sie. Diese eine Angabe laesst sich
aus nichts ableiten, was die Bibliothek heute fuehrt — deshalb bekommt sie ein
eigenes Feld (``FixtureMode.white_rows``/``white_cols``), und zwar als FORM und
nicht als Ja/Nein-Marke: die Leiste hat eine. Die ZAHL der Segmente bleibt
abgeleitet (``color_w``-Kanaele); hinterlegt wird nur, was die Kanaele nicht
sagen koennen — der ZQ06121 traegt darum ``(1, 0)`` und nicht ``(1, 8)``.

Geprueft wird in der Reihenfolge des Datenwegs:

1. **Die Quelle** — was die Bibliothek hinterlegt (und wo sie NICHTS behauptet).
2. **Nachtrag in befuellte DBs** — ohne ihn kaeme die Angabe nur in einer frisch
   angelegten Bibliothek an, und Robins ZQ06121 verloere sein Band.
3. **Auflesen** (``white_grid_for``) auf dem echten Weg: DB -> Modus -> Wert.
4. **Die Regel** (``_fixture_to_dict``) — an echten und an selbstgebauten
   Profilen, inklusive des Befunds.

★ **Positivkontrolle ist hier der Kern:** das Geraet, das ein Band haben SOLL,
muss es behalten. Ein Waechter, der Robins Balken seine Leiste nimmt, waere
schaedlicher als der Befund, den er behebt — deshalb steht der ZQ06121 in jedem
Abschnitt.

Was daraus im BILD wird, misst ``test_viz50b_weissband_scene.py`` in echter
QWebEngine (dort auch der Beleg, dass die hinterlegte FORM die Anordnung
bestimmt und nicht nur ihr Vorhandensein).
"""
from __future__ import annotations

import os
import types
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select, text                            # noqa: E402
from sqlalchemy.orm import Session, selectinload               # noqa: E402

from _fixture_quelle import frische_library                    # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureMode, FixtureProfile, PatchedFixture)


_ZQ_WEISS = "154-Kanal 48 Zonen RGB + 8x Weiss"
_ZQ_OHNE = "144-Kanal 48 Zonen RGB"


def _profil(session, short):
    return session.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.modes))
        .where(FixtureProfile.short_name == short)
    ).scalars().first()


def _modus(session, short, mode_name):
    return next(m for m in _profil(session, short).modes if m.name == mode_name)


def _patched(profile_id, mode_name, channel_count, **kw):
    return PatchedFixture(fid=kw.pop("fid", 1), label=kw.pop("label", "Panel"),
                          fixture_profile_id=profile_id, mode_name=mode_name,
                          universe=kw.pop("universe", 1),
                          address=kw.pop("address", 1),
                          channel_count=channel_count,
                          fixture_type=kw.pop("fixture_type", "matrix"), **kw)


def _dict_for(f):
    """Die ECHTE Nutzlast-Erzeugung des Visualizers (kein nachgebautes Dict)."""
    from src.ui.visualizer.visualizer_window import VisualizerBridge
    fake_self = SimpleNamespace(_state=SimpleNamespace(
        visualizer_positions={}, visualizer_rotations={}, visualizer_docks={}))
    fake_self._viz_model_for = types.MethodType(
        VisualizerBridge._viz_model_for, fake_self)
    return VisualizerBridge._fixture_to_dict(fake_self, f)


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

    def _eigenbau(self, zonen: int, weiss: int, short: str) -> tuple:
        """Ein Profil, wie es der Fixture-Editor anlegt: reine Kanalliste, KEINE
        Geometrie (``create_user_profile`` schreibt keine — das ist kein Mangel
        dieses Tests, sondern der Stand der Bibliothek).

        ★ Genau dieser Weg ist der Befund: der Editor erlaubt jede Kanalzahl,
        und aus einer Kanalzahl wurde bis CDX-52 ein Ort geschlossen."""
        from src.core.database.fixture_db import create_user_profile
        kanaele = []
        for i in range(1, zonen + 1):
            for attr in ("color_r", "color_g", "color_b"):
                kanaele.append({"name": f"Pixel {i} {attr}", "attribute": attr})
        for k in range(1, weiss + 1):
            kanaele.append({"name": f"Weiss {k}", "attribute": "color_w"})
        pid = create_user_profile({
            "manufacturer": "Eigenbau", "short_mfr": "EIGEN",
            "name": f"Selbstgebautes Panel {short}", "short_name": short,
            "fixture_type": "matrix",
            "modes": [{"name": "Standard", "channel_count": len(kanaele),
                       "channels": kanaele}],
        }, engine=self._eng)
        return pid, len(kanaele)


# ════════════════════════════════════════════════════════════════════════════
# 1. Die Quelle: was die Bibliothek ueber die Weiss-Leiste hinterlegt
# ════════════════════════════════════════════════════════════════════════════

class QuelleTest(_LibraryCase):

    def test_der_weiss_modus_traegt_eine_reihe(self):
        """★ Robins Balken: EINE Reihe. Die Spaltenzahl bleibt bewusst 0 — sie
        steht als acht ``color_w``-Kanaele im selben Modus, und eine Kopie davon
        liefe beim naechsten Modus-Umbau still daneben (FM16E)."""
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", _ZQ_WEISS)
            self.assertEqual((m.white_rows, m.white_cols), (1, 0))

    def test_derselbe_balken_ohne_weiss_behauptet_keine_leiste(self):
        """★ Der schaerfste Fall: dasselbe Geraet, dieselbe 4x12-Rasterform, nur
        der andere Modus. Wer die Leiste am PROFIL oder an der Rasterform
        festmachte, gaebe sie hier auch."""
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", _ZQ_OHNE)
            self.assertEqual((m.grid_rows, m.grid_cols), (4, 12),
                             "Vorbedingung: die Rasterform ist dieselbe")
            self.assertEqual((m.white_rows, m.white_cols), (0, 0))

    def test_sonst_behauptet_kein_modus_der_bibliothek_eine_leiste(self):
        """★★ Ueber die GANZE Bibliothek: genau ein Modus traegt eine
        Weiss-Leiste. Eine Angabe, die versehentlich breit gestreut wuerde,
        baute Baender an Geraeten, an denen niemand eine gesehen hat."""
        with Session(self._eng) as s:
            modi = s.execute(
                select(FixtureMode)
                .options(selectinload(FixtureMode.fixture))
                .where((FixtureMode.white_rows > 0) | (FixtureMode.white_cols > 0))
            ).scalars().all()
            self.assertEqual([(m.fixture.short_name, m.name) for m in modi],
                             [("ZQ06121", _ZQ_WEISS)])

    def test_wo_eine_leiste_steht_gibt_es_auch_weiss_kanaele(self):
        """★ Der Invarianten-Test: die Form beschreibt SEGMENTE, und die
        Segmente sind Kanaele. Ein Modus mit Leiste, aber ohne ``color_w``,
        behauptete eine Leiste, die niemand ansteuern kann — und der Renderer
        baute sie nicht, weil die Zahl aus den Kanaelen kommt."""
        with Session(self._eng) as s:
            modi = s.execute(
                select(FixtureMode)
                .options(selectinload(FixtureMode.channels))
                .where((FixtureMode.white_rows > 0) | (FixtureMode.white_cols > 0))
            ).scalars().all()
            self.assertTrue(modi, "Vorbedingung: es gibt einen solchen Modus")
            for m in modi:
                weiss = sum(1 for c in m.channels if c.attribute == "color_w")
                zeilen = m.white_rows or 1
                self.assertGreaterEqual(
                    weiss, zeilen,
                    f"Modus '{m.name}': {zeilen} Reihen Leiste, aber nur "
                    f"{weiss} Weiss-Kanaele")


# ════════════════════════════════════════════════════════════════════════════
# 2. Nachtrag: eine BEFUELLTE Bibliothek bekommt die Angabe auch
# ════════════════════════════════════════════════════════════════════════════

class NachtragTest(_LibraryCase):
    """★★★ Ohne diesen Weg kaeme die Angabe ausschliesslich in einer frisch
    angelegten ``fixtures.db`` an — und genau die hat niemand, der LightOS
    schon benutzt (gemessen auf Robins Rechner: 1789 Profile, 5122 Modi).
    ``ensure_builtins`` baut ein vorhandenes Profil nur bei abweichender
    ATTRIBUT-Signatur neu, und eine Rasterform steht in keinem Attribut. Der
    ZQ06121 verloere sein Band also auf jedem gewachsenen Rechner."""

    def _leiste_loeschen(self):
        with Session(self._eng) as s:
            s.execute(text("UPDATE fixture_modes SET white_rows = 0, "
                           "white_cols = 0"))
            s.commit()

    def test_ensure_builtins_traegt_die_leiste_nach(self):
        """★ Der Zustand einer Bibliothek, in der VIZ-50a schon gelaufen ist:
        die Rasterform steht (4x12), die Leiste fehlt. Wer beide Angaben an eine
        gemeinsame Bedingung haengt („hat schon Geometrie -> ueberspringen"),
        laesst genau diesen Rechner leer ausgehen."""
        from src.core.database.fixture_db import ensure_builtins
        self._leiste_loeschen()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", _ZQ_WEISS)
            self.assertEqual((m.grid_rows, m.grid_cols), (4, 12),
                             "Vorbedingung: die Rasterform steht bereits")
            self.assertEqual((m.white_rows, m.white_cols), (0, 0), "Vorbedingung")
        ensure_builtins()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", _ZQ_WEISS)
            self.assertEqual(
                (m.white_rows, m.white_cols), (1, 0),
                "in einer bestehenden Bibliothek kam die Weiss-Leiste nie an")

    def test_JEDE_geseedete_leiste_wird_nachgetragen(self):
        """★★ Bewacht die Profil-Liste in ``ensure_builtins``: was ein frischer
        Seed an Leisten anlegt, muss der Nachtrag in einer geleerten DB
        wiederherstellen. Wer einem weiteren Builtin eine Leiste gibt und die
        Liste vergisst, hat sie fuer JEDE bestehende Bibliothek nicht eingebaut
        — und merkt es nie, weil eine frische DB sie ja hat."""
        from src.core.database.fixture_db import ensure_builtins

        def _ist():
            with Session(self._eng) as s:
                return {(m.fixture.short_name, m.name):
                        (m.white_rows, m.white_cols)
                        for m in s.execute(
                            select(FixtureMode)
                            .options(selectinload(FixtureMode.fixture))
                            .where((FixtureMode.white_rows > 0)
                                   | (FixtureMode.white_cols > 0))).scalars()}

        soll = _ist()
        self.assertTrue(soll, "der Seed legt gar keine Leiste an (Vorbedingung)")
        self._leiste_loeschen()
        ensure_builtins()
        self.assertEqual(
            _ist(), soll,
            "diese Weiss-Leisten legt der Seed an, der Nachtrag stellt sie aber "
            "nicht wieder her (Liste in ensure_builtins ergaenzen)")

    def test_nachtrag_ueberschreibt_eine_gesetzte_leiste_nicht(self):
        """★★ Nur ergaenzend. Wuerde der Nachtrag stumpf ueberschreiben, saesse
        eine spaetere Korrektur des Nutzers nach dem naechsten Programmstart
        wieder auf dem Werkswert — ohne Meldung."""
        from src.core.database.fixture_db import ensure_builtins
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", _ZQ_WEISS)
            m.white_rows, m.white_cols = 2, 4
            s.commit()
        ensure_builtins()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", _ZQ_WEISS)
            self.assertEqual((m.white_rows, m.white_cols), (2, 4),
                             "der Nachtrag hat eine gesetzte Leiste zerstoert")

    def test_nachtrag_gibt_keinem_modus_ohne_angabe_eine_leiste(self):
        """★ Positivkontrolle: der Nachtrag fasst nur an, wofuer etwas
        hinterlegt IST. Ein Nachtrag, der alles anfasst, waere so wertlos wie
        keiner — und baute Baender an Geraeten ohne."""
        from src.core.database.fixture_db import ensure_builtins
        self._leiste_loeschen()
        ensure_builtins()
        with Session(self._eng) as s:
            for short, name in (("ZQ06121", _ZQ_OHNE),
                                ("STAIRPP144", "432-Kanal 144 Pixel RGB"),
                                ("DOTZMATRIX", "48-Kanal 16 Pixel RGB")):
                m = _modus(s, short, name)
                self.assertEqual((m.white_rows, m.white_cols), (0, 0),
                                 f"{short}/{name} behauptet eine Weiss-Leiste")

    def test_die_rasterform_bleibt_beim_nachtrag_unberuehrt(self):
        """★ Zwei Angaben, ein Nachtrag: die Leiste nachzutragen darf die
        Rasterform nicht anfassen — und umgekehrt."""
        from src.core.database.fixture_db import ensure_builtins
        with Session(self._eng) as s:
            s.execute(text("UPDATE fixture_modes SET white_rows = 0, "
                           "white_cols = 0, grid_rows = 2, grid_cols = 24"))
            s.commit()
        ensure_builtins()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", _ZQ_WEISS)
            self.assertEqual((m.grid_rows, m.grid_cols), (2, 24),
                             "der Nachtrag hat die Rasterform ueberschrieben")
            self.assertEqual((m.white_rows, m.white_cols), (1, 0),
                             "die Leiste kam trotz gesetzter Rasterform nicht an")

    def test_zweiter_lauf_meldet_keine_aenderung_mehr(self):
        """Idempotenz: ``ensure_builtins`` laeuft bei jedem Engine-Aufbau. Ein
        Nachtrag, der immer wieder „geaendert" meldet, schriebe die Bibliothek
        bei jedem Start neu."""
        from src.core.database import fixture_db as FDB
        self._leiste_loeschen()
        FDB.ensure_builtins()
        with Session(self._eng) as s:
            self.assertFalse(
                FDB._ensure_panel_geometrie(s, "ZQ06121",
                                            FDB._zq06121_modes_data()),
                "der Nachtrag meldet Arbeit, obwohl die Leiste schon steht")


# ════════════════════════════════════════════════════════════════════════════
# 3. Auflesen: white_grid_for
# ════════════════════════════════════════════════════════════════════════════

class WhiteGridForTest(_LibraryCase):

    def test_liest_die_hinterlegte_leiste_des_modus(self):
        from src.core.app_state import white_grid_for
        pid, modi = self._ids("ZQ06121")
        f = _patched(pid, _ZQ_WEISS, modi[_ZQ_WEISS])
        self.assertEqual(white_grid_for(f), (1, 0))

    def test_ohne_angabe_null(self):
        from src.core.app_state import white_grid_for
        pid, modi = self._ids("ZQ06121")
        self.assertEqual(white_grid_for(_patched(pid, _ZQ_OHNE, modi[_ZQ_OHNE])),
                         (0, 0))

    def test_unbekanntes_profil_faellt_weich(self):
        from src.core.app_state import white_grid_for
        self.assertEqual(white_grid_for(_patched(999999, "Egal", 9)), (0, 0))
        self.assertEqual(white_grid_for(SimpleNamespace()), (0, 0))

    def test_beide_raster_desselben_modus_bleiben_getrennt(self):
        """★★ Farbzonen-Raster und Weiss-Leiste kommen aus DEMSELBEN Modus und
        teilen sich den Cache. Steht das Feld nicht im Schluessel, gibt der
        zweite Aufruf die Antwort des ersten zurueck — und der ZQ06121 bekaeme
        ein 4x12-Weiss-Band ueber seinen Zonen. Beide Reihenfolgen, weil der
        Fehler sonst nur in einer Richtung auffiele."""
        from src.core.app_state import (clear_channel_cache, panel_grid_for,
                                        white_grid_for)
        pid, modi = self._ids("ZQ06121")
        f = _patched(pid, _ZQ_WEISS, modi[_ZQ_WEISS])
        self.assertEqual(panel_grid_for(f), (4, 12))
        self.assertEqual(white_grid_for(f), (1, 0))
        clear_channel_cache()
        self.assertEqual(white_grid_for(f), (1, 0))
        self.assertEqual(panel_grid_for(f), (4, 12))

    def test_der_cache_folgt_dem_modus_wechsel(self):
        """Wie die Rasterform haengt die Leiste am MODUS. Nach einem
        Modus-Wechsel (und der zugehoerigen Invalidierung) muss der neue Wert
        kommen, nicht der gecachte alte."""
        from src.core.app_state import clear_channel_cache, white_grid_for
        pid, modi = self._ids("ZQ06121")
        f = _patched(pid, _ZQ_WEISS, modi[_ZQ_WEISS])
        self.assertEqual(white_grid_for(f), (1, 0))
        f.mode_name = _ZQ_OHNE
        f.channel_count = modi[_ZQ_OHNE]
        clear_channel_cache()
        self.assertEqual(white_grid_for(f), (0, 0),
                         "nach dem Modus-Wechsel kam der alte Wert zurueck")


# ════════════════════════════════════════════════════════════════════════════
# 4. Die Regel in der Nutzlast: wann entsteht ein Band?
# ════════════════════════════════════════════════════════════════════════════

class BandRegelTest(_LibraryCase):

    def test_robins_balken_behaelt_sein_band(self):
        """★ Die Positivkontrolle, an der dieses Item haengt: das Geraet, das
        ein Band haben SOLL, behaelt es — mit derselben Segmentzahl wie vor
        CDX-52, und jetzt zusaetzlich mit der hinterlegten Form."""
        pid, modi = self._ids("ZQ06121")
        d = _dict_for(_patched(pid, _ZQ_WEISS, modi[_ZQ_WEISS]))
        self.assertEqual(d["model"], "matrix")
        self.assertEqual((d["nHeads"], d["nWhites"]), (48, 8))
        self.assertEqual((d["gridRows"], d["gridCols"]), (4, 12))
        self.assertEqual((d["whiteRows"], d["whiteCols"]), (1, 0))

    def test_der_befund_ein_globaler_weiss_kanal_ist_kein_band(self):
        """★★ DER BEFUND. 48 selbstgebaute RGB-Pixel, EIN globaler Weiss-Kanal.
        ``0 < 1 < 48`` war wahr — das Geraet bekam ein Band ueber die volle
        Breite, gefahren von ``heads[0].cw``. Es hat keines: eine Kanalzahl
        traegt keine Ortsangabe."""
        pid, kanaele = self._eigenbau(48, 1, "EIGEN48W1")
        d = _dict_for(_patched(pid, "Standard", kanaele, fid=10))
        self.assertEqual(d["model"], "matrix", "Vorbedingung: ein Panel")
        self.assertEqual(d["nHeads"], 48, "Vorbedingung: 48 Farbzonen")
        self.assertEqual(d["nWhites"], 0,
                         "ein globaler Weiss-Kanal ist keine Leiste")
        self.assertEqual((d["whiteRows"], d["whiteCols"]), (0, 0))

    def test_dieselben_kanaele_wie_robins_balken_reichen_nicht(self):
        """★★★ Der schaerfste Fall des Befunds: ein selbstgebautes Profil mit
        EXAKT der Kanalsignatur des ZQ06121 — 48 Zonen, 8 Weiss-Kanaele. Aus den
        Kanaelen ist es von Robins Balken nicht zu unterscheiden; die Bibliothek
        hat fuer dieses Geraet aber niemand nachgesehen. Wer hier ein Band baut,
        hat die Kanalzahl nur umbenannt."""
        pid, kanaele = self._eigenbau(48, 8, "EIGEN48W8")
        d = _dict_for(_patched(pid, "Standard", kanaele, fid=11))
        self.assertEqual(d["nHeads"], 48)
        self.assertEqual(d["nWhites"], 0,
                         "ohne hinterlegte Leiste gibt es kein Band — auch bei "
                         "acht Weiss-Kanaelen auf 48 Zonen nicht")

    def test_ein_rgbw_panel_bekommt_weiterhin_kein_band(self):
        """★ Die andere Haelfte: gleich viele Weiss-Kanaele wie Zonen heisst
        RGBW-Emitter. Dort gehoert das Weiss zum Pixel und steckt ueber
        ``visual_rgb`` schon in dessen Farbe — ein Band waere dieselbe
        Information ein zweites Mal."""
        pid, kanaele = self._eigenbau(16, 16, "EIGENRGBW")
        d = _dict_for(_patched(pid, "Standard", kanaele, fid=12))
        self.assertEqual(d["nHeads"], 16)
        self.assertEqual(d["nWhites"], 0)

    def test_hinterlegte_leiste_ohne_weiss_kanaele_bleibt_leer(self):
        """★ Die ZAHL kommt weiter aus den Kanaelen, nicht aus dem Feld. Ein
        Modus mit hinterlegter Leiste, aber ohne ``color_w``, bekommt kein
        Band — sonst waere das Feld eine zweite, ungepruefte Zaehlung."""
        pid, modi = self._ids("ZQ06121")
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", _ZQ_OHNE)
            m.white_rows, m.white_cols = 1, 0
            s.commit()
        from src.core.app_state import clear_channel_cache
        clear_channel_cache()
        d = _dict_for(_patched(pid, _ZQ_OHNE, modi[_ZQ_OHNE], fid=13))
        self.assertEqual((d["whiteRows"], d["whiteCols"]), (1, 0),
                         "Vorbedingung: die Leiste ist hinterlegt")
        self.assertEqual(d["nWhites"], 0,
                         "ohne Weiss-Kanaele gibt es nichts zu zeichnen")

    def test_die_felder_stehen_in_jeder_nutzlast(self):
        """Wie bei ``gridRows``: JS haette sonst zwei Faelle zu unterscheiden
        (fehlt / ist 0), und einer davon wird irgendwann vergessen."""
        pid, modi = self._ids("MH8")
        d = _dict_for(_patched(pid, "8-Kanal", modi["8-Kanal"], fid=14,
                               fixture_type="moving_head"))
        self.assertEqual(d["model"], "moving_head")
        self.assertEqual((d["whiteRows"], d["whiteCols"]), (0, 0))

    def test_ein_geraet_ohne_bibliothek_faellt_nicht_auf_die_nase(self):
        """Ein Fixture, dessen Profil es nicht (mehr) gibt: die Nutzlast muss
        trotzdem entstehen — der Visualizer baut die ganze Szene daraus."""
        d = _dict_for(_patched(999999, "Weg", 12, fid=15))
        self.assertEqual((d["whiteRows"], d["whiteCols"]), (0, 0))
        self.assertEqual(d["nWhites"], 0)


if __name__ == "__main__":
    unittest.main()
