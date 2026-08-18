"""FM-14b — die Pixel-Segmente BEDIENBAR machen: Ringordnung + Beschriftung.

FM-14 hat den Ring gezeichnet und den Datenweg gelegt (20 Farb-Baenke ->
Kopf 0 = Grundfarbe, Kopf 1..19 = Pixel 1..19). Bedienen liess er sich damit
noch nicht, aus zwei Gruenden — und beide werden hier gemessen:

**(1) Kopf 0 heisst wie ein Pixel, ist aber die GRUNDFARBE.** In der
Programmer-Geraeteliste stand „Kopf 1" — greift man dort hin, faerbt man Linse,
Kegel und Bodenfleck des ganzen Geraets statt des ersten Pixels. „Pixel 1" liegt
eine Zeile tiefer. Eine Beschriftung, die um eins verschoben ist, ist schlimmer
als gar keine.

**(2) Die Auto-Kopf-Matrix (FM-16) ist eine 1xN-Reihe in DMX-Reihenfolge.** Die
Pixel dieses Geraets liegen aber in RINGEN. Ein Lauflicht ueber die Reihe laeuft
deshalb am Ring vorbei: es startet auf der Grundfarbe, faellt in die Mitte,
dreht den Innenring und erreicht den Aussenring erst in den letzten 12 von 20
Schritten — 8 Schritte lang steht der Ring still.

Die Ringordnung selbst ist NICHT neu erfunden, sondern aus dem 3D gespiegelt
(``scene_src/fixtures/pixel_order.js#wabenPlatz`` -> ``core/pixel_order.py``).
Dass beide Fassungen wirklich dieselbe Regel sind, misst
``test_fm14b_pixel_ring_scene.py`` in echter QWebEngine Index fuer Index — eine
zweite Fassung, die still auseinanderlaeuft, ist die Falle, an der VIZ-51/52
gearbeitet haben.

★ **Die Erwartungen stehen als Zahlen aus der QUELLE, nicht aus der Formel.**
Robe Robin Spiider, User Manual Rev. 3.3 S. 15 „Pixel order": Pixel 1 = Mitte,
Pixel 2-7 = innerer Sechserring, Pixel 8-19 = aeusserer Zwoelferring, im
Uhrzeigersinn. Die Firmware nennt die drei Gruppen selbst „Ring 1 (Middle
pixel) / Ring 2 / Ring 3" (DMX-Chart v2.3, Kanal „Background - Active zone").
Die Kanalnummern ebenso: Kanal 8 = Grundfarbe Rot, 35 = Pixel 1 Rot, danach je
drei Kanaele pro Pixel bis 89 = Pixel 19 Rot.

★★ **Positivkontrolle durchgehend an einem Geraet OHNE Ringe**, und zwar am
schaerfsten: ``MOVBAR4`` hat VIER Farb-Baenke, faellt also nicht schon an der
Bank-Zahl heraus — es ist nur kein Pixel-Kopf. Bliebe seine Kopf-Matrix nicht
die 1x4-Reihe von bisher, waere jede Bestands-Show still umsortiert.
"""
from __future__ import annotations

import json
import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                       # noqa: E402
from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session, selectinload                 # noqa: E402

from _fixture_quelle import frische_library                      # noqa: E402
from src.core.pixel_order import waben_platz, waben_raster       # noqa: E402
from src.core.database.models import (                           # noqa: E402
    FixtureGroup, FixtureProfile, PatchedFixture)

# ── Zahlen aus der Primaerquelle (Manual S. 15 / DMX-Chart v2.3) ────────────
_PIXEL_MODE = "91-Kanal Pixel RGB (Mode 7)"
_PIXEL_CH = 91
_WASH_MODE = "27-Kanal Wash (Mode 5)"
_WASH_CH = 27
_MOVBAR_MODE = "22-Kanal 4×Move RGB"
_MOVBAR_CH = 22

_GRUNDFARBE_ROT = 8         # Kanal 8 = „Grundfarbe Rot"
_PIXEL1_ROT = 35            # Kanal 35 = Pixel 1 Rot, danach je 3 Kanaele
_MITTE = 1                  # Pixel 1 ist die Mitte
_INNENRING = tuple(range(2, 8))     # Pixel 2..7  = 6 Plaetze
_AUSSENRING = tuple(range(8, 20))   # Pixel 8..19 = 12 Plaetze


def _rot_kanal(pixel: int) -> int:
    """DMX-Kanal des ROT-Kanals von Pixel ``pixel`` (1-basiert), aus dem Chart."""
    return _PIXEL1_ROT + 3 * (pixel - 1)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ════════════════════════════════════════════════════════════════════════════
# 1. Das Ring-Raster (rein) — gegen die Zeichnung im Manual
# ════════════════════════════════════════════════════════════════════════════

class RingRasterTest(unittest.TestCase):
    """``waben_raster``: 19 Pixel -> ein Raster, in dem die SPALTE der Winkel
    und die ZEILE der Ring ist."""

    def setUp(self):
        self.cols, self.rows, self.plaetze = waben_raster(19)

    def _zeile(self, r: int) -> list:
        """Die Pixel (1-basiert) der Zeile ``r``, nach Spalte sortiert."""
        return [i + 1 for i, (_c, rr) in sorted(
            self.plaetze.items(), key=lambda kv: kv[1][0]) if rr == r]

    def test_drei_ringe_werden_drei_zeilen(self):
        """Die Firmware kennt „Ring 1 (Middle pixel) / Ring 2 / Ring 3" — genau
        drei. Sie werden die drei Zeilen, damit die Spaltenachse frei bleibt
        fuer den WINKEL."""
        self.assertEqual(self.rows, 3)

    def test_zwoelf_spalten_wie_der_aussenring_plaetze_hat(self):
        """Der aeussere Ring hat 12 Pixel (8..19). Er gibt die Spaltenzahl vor:
        eine Spalte je Winkelposition, damit ein Lauflicht ihn LUECKENLOS
        durchlaeuft."""
        self.assertEqual(self.cols, 12)

    def test_die_mitte_steht_allein_in_der_ersten_zeile(self):
        self.assertEqual(self._zeile(0), [_MITTE])

    def test_der_innenring_ist_die_zweite_zeile_im_uhrzeigersinn(self):
        self.assertEqual(self._zeile(1), list(_INNENRING))

    def test_der_aussenring_ist_die_dritte_zeile_im_uhrzeigersinn(self):
        self.assertEqual(self._zeile(2), list(_AUSSENRING))

    def test_der_aussenring_belegt_jede_spalte_genau_einmal(self):
        """★ Die Bedingung, an der die alte 1xN-Reihe scheitert: kein Schritt
        eines Lauflichts ohne Ring-Pixel."""
        spalten = sorted(self.plaetze[p - 1][0] for p in _AUSSENRING)
        self.assertEqual(spalten, list(range(12)))

    def test_der_innenring_liegt_gleichmaessig_dazwischen(self):
        """Sechs Plaetze auf zwoelf Spalten: jede zweite. So drehen Innen- und
        Aussenring GLEICHZEITIG und phasengleich (eine Umdrehung = 12 Schritte
        fuer beide), statt nacheinander."""
        spalten = sorted(self.plaetze[p - 1][0] for p in _INNENRING)
        self.assertEqual(len(set(spalten)), 6)
        abstaende = {b - a for a, b in zip(spalten, spalten[1:])}
        self.assertEqual(abstaende, {2})

    def test_die_spalte_ist_wirklich_der_winkel(self):
        """★★ Die Zusage hinter der Spaltenachse, an einem Kopf mit VIER Ringen
        (37 Plaetze) gemessen — dort trennt sie sich von der naheliegenden
        falschen Regel „Spalte = Platznummer, auf die Spaltenzahl gestreckt".

        Jede der 18 Spalten deckt einen 20°-Sektor ab; ein Pixel gehoert in den
        Sektor SEINES Winkels. Der Winkel kommt aus ``waben_platz`` — also aus
        der Fassung, die der Zwillingstest gegen das 3D haelt —, nicht aus der
        Raster-Formel. Bei „Platznummer gestreckt" faengt jeder Ring wieder bei
        Spalte 0 an, obwohl die Ringe gegeneinander versetzt sind: der
        Innenring laege dann eine ganze Spalte daneben.

        Bei 19 Pixeln (drei Ringe) waere diese Messung nicht scharf: dort faellt
        der Innenring GENAU auf die Sektorgrenzen, und wohin ein Randfall
        kippt, entscheidet Gleitkomma-Rauschen. Der Randfall selbst steht
        deshalb als eigene Zusage im Test darunter.
        """
        cols, _rows, plaetze = waben_raster(37)
        self.assertEqual(cols, 18, "vier Ringe -> 18 Plaetze im aeussersten")
        breite = 360.0 / cols
        for i, (col, _r) in plaetze.items():
            ring, x, y = waben_platz(i)
            if ring == 0:
                continue
            winkel = (math.degrees(math.atan2(y, x)) % 360 + 360) % 360
            versatz = (270.0 - winkel) % 360.0      # im Uhrzeigersinn ab „unten"
            self.assertEqual(col, int(versatz // breite),
                             f"Pixel {i + 1} (Ring {ring}, {versatz:.1f}° hinter "
                             f"dem Ringanfang) steht in Spalte {col}")

    def test_ein_platz_auf_der_sektorgrenze_geht_im_uhrzeigersinn_weiter(self):
        """★ Der Randfall des realen Geraets: bei drei Ringen liegt jeder
        Innenring-Platz GENAU zwischen zwei Aussenring-Plaetzen, also auf einer
        Spaltengrenze. Er bekommt die naechste Spalte im Uhrzeigersinn — in
        derselben Richtung, in der die Nummerierung laeuft. Ohne festgelegte
        Richtung waere die Zuordnung von Rundungsrauschen abhaengig."""
        _cols, _rows, plaetze = waben_raster(19)
        self.assertEqual([plaetze[p - 1][0] for p in _INNENRING],
                         [1, 3, 5, 7, 9, 11])

    def test_jedes_pixel_bekommt_genau_eine_zelle(self):
        self.assertEqual(len(self.plaetze), 19)
        self.assertEqual(len(set(self.plaetze.values())), 19)
        for (c, r) in self.plaetze.values():
            self.assertTrue(0 <= c < self.cols and 0 <= r < self.rows)

    def test_ein_angebrochener_ring_bleibt_ein_ring(self):
        """Vier Pixel = Mitte + drei vom Innenring. Der Ring ist unvollstaendig;
        das Raster hat trotzdem die Form des Innenrings (6 Spalten — jetzt ist
        ER der aeusserste und bekommt deshalb eine Spalte je Platz), die
        fehlenden drei Plaetze bleiben schlicht Luecken."""
        cols, rows, plaetze = waben_raster(4)
        self.assertEqual((cols, rows), (6, 2))
        self.assertEqual(plaetze[0], (0, 0))
        self.assertEqual(sorted(plaetze[i][0] for i in (1, 2, 3)), [0, 1, 2])
        self.assertEqual({plaetze[i][1] for i in (1, 2, 3)}, {1})

    def test_ohne_pixel_wirft_es_nicht(self):
        """Der Wert kommt aus einem gepatchten Geraet — nie werfen (dieselbe
        Politik wie ``normalize_pixel_order``)."""
        self.assertEqual(waben_raster(0), (1, 1, {}))
        self.assertEqual(waben_raster(-5), (1, 1, {}))
        self.assertEqual(waben_raster(1), (1, 1, {0: (0, 0)}))


# ════════════════════════════════════════════════════════════════════════════
# 2. Die Auto-Kopf-Matrix am ECHTEN Geraet
# ════════════════════════════════════════════════════════════════════════════

class _RigFall(unittest.TestCase):
    """Frisch aus dem Quelltext geseedete Bibliothek (FIXTEST-FRESH) + leere
    Show. Gepatcht wird ueber ``AppState.add_fixture`` — also genau den Weg,
    auf dem die Kopf-Matrix beim Patchen entsteht."""

    def setUp(self):
        from src.core.app_state import clear_channel_cache, get_state
        from src.core.show.show_file import reset_show
        _app()
        self._eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)
        reset_show()
        self.addCleanup(reset_show)
        self.state = get_state()

    def _pid(self, short: str) -> int:
        with Session(self._eng) as s:
            p = s.execute(select(FixtureProfile).options(
                selectinload(FixtureProfile.modes)).where(
                FixtureProfile.short_name == short)).scalars().first()
            self.assertIsNotNone(p, f"Profil {short} fehlt in der Bibliothek")
            return int(p.id)

    def _patch(self, short, mode, chans, *, fid=1, adresse=1, typ="moving_head"):
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"G{fid}", fixture_profile_id=self._pid(short),
            mode_name=mode, universe=1, address=adresse, channel_count=chans,
            fixture_type=typ), undoable=False)
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _spiider(self, **kw):
        return self._patch("SPIIDER", _PIXEL_MODE, _PIXEL_CH, **kw)

    def _gruppe(self, fx):
        gid = self.state.find_head_matrix_group(fx.fid, dedicated=True)
        self.assertIsNotNone(gid, "beim Patchen entstand keine Kopf-Matrix")
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            return g.name, g.cols, g.rows, json.loads(g.positions_json or "{}")


class AutoGruppeTest(_RigFall):

    def test_der_pixel_kopf_bekommt_das_ringraster(self):
        name, cols, rows, _pos = self._gruppe(self._spiider())
        self.assertEqual((cols, rows), (12, 3),
                         "die Kopf-Matrix ist noch die 1xN-Reihe — ein "
                         "Lauflicht darueber laeuft am Ring vorbei")
        self.assertTrue(name.endswith("· Pixel"),
                        f"die Gruppe heisst {name!r}; „Köpfe“ waere hier "
                        f"falsch, in den Zellen stehen Pixel")

    def test_die_grundfarbe_steht_nicht_im_raster(self):
        """★★ Der Kern von (1) auf der Raster-Seite: Kopf 0 faerbt das GANZE
        Geraet. Als Matrix-Zelle wuerde jeder Effekt sie mitziehen und den Ring,
        den er gerade zeichnet, sofort ueberstrahlen."""
        _n, _c, _r, pos = self._gruppe(self._spiider())
        koepfe = sorted(int(v.split(":")[1]) for v in pos.values())
        self.assertEqual(koepfe, list(range(1, 20)))
        self.assertNotIn(0, koepfe, "die Grundfarbe steht als Pixel im Raster")

    def test_kopf_n_traegt_pixel_n(self):
        """Die Zuordnung aus FM-14 bleibt: Pixel N liegt auf Kopf N. Gemessen an
        der Stelle, an der das Manual die Ringe beginnen laesst — Zeile 2
        (Aussenring), Spalte 0 = Pixel 8."""
        fx = self._spiider()
        _n, _c, _r, pos = self._gruppe(fx)
        self.assertEqual(pos["0,0"], f"{fx.fid}:1", "Zeile 0 ist die Mitte")
        self.assertEqual(pos["0,2"], f"{fx.fid}:8",
                         "der Aussenring beginnt mit Pixel 8")
        self.assertEqual(pos["11,2"], f"{fx.fid}:19",
                         "und endet mit Pixel 19")

    def test_ein_geraet_ohne_ringe_behaelt_seine_reihe(self):
        """★★ POSITIVKONTROLLE, und die scharfe: MOVBAR4 hat VIER Farb-Baenke —
        es faellt also nicht schon an der Bank-Zahl heraus, sondern allein
        daran, dass es kein Pixel-Kopf ist. Waere die Weiche zu breit, waeren
        Bestands-Shows still umsortiert."""
        fx = self._patch("MOVBAR4", _MOVBAR_MODE, _MOVBAR_CH, fid=2, adresse=200)
        name, cols, rows, pos = self._gruppe(fx)
        self.assertEqual((cols, rows), (4, 1))
        self.assertTrue(name.endswith("· Köpfe"), name)
        self.assertEqual(pos, {f"{i},0": f"{fx.fid}:{i}" for i in range(4)},
                         "die 1xN-Reihe in DMX-Reihenfolge hat sich geaendert")

    def test_ein_von_hand_gesetzter_pixel_kopf_zaehlt_auch(self):
        """★ Die Regel haengt am ZENTRALEN Modell-Routing, nicht an der
        Bank-Zahl: setzt jemand im Fixture-Generator ausdruecklich
        ``viz_model = 'pixel_head'``, gilt sie auch fuer sein Geraet. Hier an
        einem Spider mit ZWEI Baenken — also Grundfarbe + genau EIN Pixel. Auch
        dieser Randfall geht durch dieselbe Regel (Kopf 0 bleibt draussen), es
        gibt keinen zweiten Zweig fuer „zu wenige Pixel"."""
        from src.core.app_state import clear_channel_cache
        with Session(self._eng) as s:
            p = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "SPIDER14")).scalars().one()
            p.viz_model = "pixel_head"
            s.commit()
        clear_channel_cache()
        fx = self._patch("SPIDER14", "14-Kanal", 14, fid=4, adresse=400)
        name, cols, rows, pos = self._gruppe(fx)
        self.assertEqual((cols, rows), (1, 1))
        self.assertTrue(name.endswith("· Pixel"), name)
        self.assertEqual(pos, {"0,0": f"{fx.fid}:1"},
                         "die Grundfarbe steht auch hier nicht im Raster")

    def test_derselbe_spiider_im_wash_modus_hat_gar_keine_koepfe(self):
        """Dasselbe Geraet, eine Farb-Bank: kein Mehrkopf, also wie bisher gar
        keine Kopf-Matrix. Die Probe, dass der Ring an den KANAELEN haengt und
        nicht am Geraetenamen."""
        fx = self._patch("SPIIDER", _WASH_MODE, _WASH_CH, fid=3, adresse=300)
        self.assertIsNone(self.state.find_head_matrix_group(fx.fid, dedicated=True))


# ════════════════════════════════════════════════════════════════════════════
# 3. Das Lauflicht — bis auf die DMX-Kanaele gemessen
# ════════════════════════════════════════════════════════════════════════════

class LauflichtTest(_RigFall):
    """★ Die Abnahme: ein Lauflicht ueber die Kopf-Matrix laeuft am Geraet als
    RING. Gemessen am Universum, nicht an einem Zwischenobjekt — und die
    Rueckrechnung Kanal -> Pixel kommt aus dem CHART (Kanal 35 = Pixel 1 Rot),
    nicht aus der Funktion, die auch geschrieben hat."""

    def _matrix(self, fx, *, achse: str = "H"):
        from src.core.engine.rgb_matrix import (RgbMatrixInstance, RgbAlgorithm,
                                                MatrixStyle, grids_from_positions)
        _n, cols, rows, pos = self._gruppe(fx)
        grid, head_grid = grids_from_positions(pos, cols, rows)
        inst = RgbMatrixInstance(
            name="Ring", cols=cols, rows=rows, fixture_grid=grid,
            head_grid=head_grid, algorithm=RgbAlgorithm.CHASE)
        inst.style = MatrixStyle.RGB
        # Ein einzelner, harter Laeufer ohne Schweif: dann ist „welche Zelle
        # leuchtet" eine Frage mit genau einer Antwort je Zeile.
        inst.params.update({"axis": achse, "movement": "normal",
                            "runner_width": 1, "runner_count": 1,
                            "after_fade": 0.0})
        inst.start()
        return inst

    def _leuchtende_pixel(self, inst, fx, schritt: int) -> set:
        """Schritt setzen, schreiben, Universum lesen -> welche Pixel leuchten.

        Der Ruecksprung Kanal -> Pixel benutzt die Kanalnummern des Charts, also
        eine von der Produktion unabhaengige Quelle."""
        from src.core.dmx.universe import Universe
        u = Universe(fx.universe)
        inst._step = float(schritt)
        inst.write({fx.universe: u}, self.state.get_patched_fixtures(), 0.0)
        an = set()
        for p in range(1, 20):
            k = _rot_kanal(p)
            if any(u.get_channel(k + o) for o in (0, 1, 2)):
                an.add(p)
        self._grundfarbe_an = any(
            u.get_channel(_GRUNDFARBE_ROT + o) for o in (0, 1, 2))
        return an

    def _lauf(self, achse="H", schritte=12) -> list:
        fx = self._spiider()
        inst = self._matrix(fx, achse=achse)
        return [self._leuchtende_pixel(inst, fx, t) for t in range(schritte)]

    def test_das_lauflicht_dreht_den_aussenring_pixel_fuer_pixel(self):
        """★★ Die Kernzusage. Erwartung aus dem Manual: der Aussenring zaehlt
        im Uhrzeigersinn 8, 9, … 19 — ein Lauflicht muss ihn in genau dieser
        Reihenfolge abgehen, EINEN Platz je Schritt."""
        aussen = [sorted(an & set(_AUSSENRING)) for an in self._lauf()]
        self.assertEqual(aussen, [[p] for p in _AUSSENRING],
                         "der Aussenring wird nicht Platz fuer Platz "
                         "weitergedreht")

    def test_kein_schritt_laesst_den_ring_stehen(self):
        """★ Genau der Befund, um den FM-14b geht: in der 1x20-Reihe kommt der
        Aussenring erst in den letzten 12 von 20 Schritten dran — 8 Schritte
        lang steht er still. Hier muss JEDER Schritt ihn weiterdrehen."""
        leer = [t for t, an in enumerate(self._lauf())
                if not (an & set(_AUSSENRING))]
        self.assertEqual(leer, [], f"Schritte ohne Aussenring-Pixel: {leer}")

    def test_nach_einer_umdrehung_faengt_es_wieder_vorn_an(self):
        """12 Plaetze, 12 Schritte: Schritt 12 muss wieder Pixel 8 sein — sonst
        ist es keine Umdrehung, sondern eine Reihe, die zufaellig rundlaeuft."""
        lauf = self._lauf(schritte=13)
        self.assertEqual(lauf[12] & set(_AUSSENRING), {8})

    def test_innen_und_aussenring_drehen_gleichzeitig(self):
        """★ „Am Ring vorbei" heisst auch: in der Reihe leuchten Innen- und
        Aussenring NIE zusammen (erst der eine, dann der andere). Im Ring-Raster
        dreht der Innenring mit — auf jeder zweiten Spalte, weil er halb so
        viele Plaetze hat."""
        lauf = self._lauf()
        gemeinsam = [t for t, an in enumerate(lauf)
                     if (an & set(_INNENRING)) and (an & set(_AUSSENRING))]
        self.assertEqual(len(gemeinsam), 6,
                         f"Innen- und Aussenring leuchten in {len(gemeinsam)} "
                         f"von 12 Schritten zusammen, erwartet 6")
        innen = [sorted(an & set(_INNENRING)) for an in lauf]
        self.assertEqual([x for x in innen if x], [[p] for p in _INNENRING],
                         "der Innenring dreht nicht im Uhrzeigersinn mit")

    def test_das_lauflicht_faerbt_nie_das_ganze_geraet(self):
        """★★ Die Bedienbarkeits-Zusage (1) auf der Wirkungs-Seite: die
        Grundfarbe faerbt Linse, Kegel und Bodenfleck. Stuende sie im Raster,
        wuerde der Effekt sie einmal je Umdrehung voll aufziehen und den Ring
        ueberstrahlen."""
        fx = self._spiider()
        inst = self._matrix(fx)
        for t in range(12):
            self._leuchtende_pixel(inst, fx, t)
            self.assertFalse(self._grundfarbe_an,
                             f"Schritt {t} zieht die Grundfarbe hoch")

    def test_senkrecht_laeuft_es_von_der_mitte_nach_aussen(self):
        """Die zweite Achse ist damit auch bedienbar: die ZEILE ist der Ring,
        ein senkrechtes Lauflicht ist also eine Welle von innen nach aussen."""
        lauf = self._lauf(achse="V", schritte=3)
        self.assertEqual(lauf[0], {_MITTE})
        self.assertEqual(lauf[1], set(_INNENRING))
        self.assertEqual(lauf[2], set(_AUSSENRING))

    def test_ein_geraet_ohne_ringe_laeuft_wie_bisher(self):
        """POSITIVKONTROLLE am DMX: die 1x4-Reihe des MOVBAR4 leuchtet Kopf fuer
        Kopf in DMX-Reihenfolge — ein Kopf je Schritt, wie vor FM-14b."""
        from src.core.dmx.universe import Universe
        fx = self._patch("MOVBAR4", _MOVBAR_MODE, _MOVBAR_CH, fid=2, adresse=1)
        inst = self._matrix(fx)
        self.assertEqual((inst.cols, inst.rows), (4, 1))
        # MOVBAR4 22ch: Kopf k hat Rot auf 7 + 4k (Chart: je Kopf Pan,Tilt,R,G,B
        # ab Kanal 5) — hier reicht die REIHENFOLGE, also welcher Kopf-Block.
        gesehen = []
        for t in range(4):
            u = Universe(fx.universe)
            inst._step = float(t)
            inst.write({fx.universe: u}, self.state.get_patched_fixtures(), 0.0)
            gesehen.append(self._heller_kopf(fx, u))
        self.assertEqual(gesehen, [0, 1, 2, 3])

    def _heller_kopf(self, fx, u) -> int:
        """Welcher Kopf leuchtet? Ueber die Kanal-Attribute des Profils, nicht
        ueber ``channels_for_head`` (das schreibt selbst)."""
        from src.core.app_state import get_channels_for_patched
        rot = [c for c in get_channels_for_patched(fx)
               if (getattr(c, "attribute", "") or "") == "color_r"]
        an = [i for i, c in enumerate(rot)
              if u.get_channel(fx.address + int(c.channel_number) - 1)]
        self.assertEqual(len(an), 1, f"genau ein Kopf erwartet, an: {an}")
        return an[0]


# ════════════════════════════════════════════════════════════════════════════
# 4. Die Beschriftung — „Kopf 1" ist beim Pixel-Kopf die Grundfarbe
# ════════════════════════════════════════════════════════════════════════════

class BeschriftungTest(_RigFall):

    def test_am_pixel_kopf_heisst_kopf_null_grundfarbe(self):
        from src.core.app_state import head_label
        fx = self._spiider()
        self.assertEqual(head_label(fx, 0), "Grundfarbe")
        self.assertEqual(head_label(fx, 1), "Pixel 1")
        self.assertEqual(head_label(fx, 19), "Pixel 19")

    def test_ein_geraet_ohne_ringe_zaehlt_weiter_koepfe(self):
        """POSITIVKONTROLLE: vier Farb-Baenke, aber kein Pixel-Kopf — die
        Bestandsbeschriftung bleibt Wort fuer Wort."""
        from src.core.app_state import head_label
        fx = self._patch("MOVBAR4", _MOVBAR_MODE, _MOVBAR_CH, fid=2, adresse=200)
        self.assertEqual(head_label(fx, 0), "Kopf 1")
        self.assertEqual(head_label(fx, 3), "Kopf 4")

    def test_die_programmer_liste_sagt_es_auch(self):
        """★ Gemessen an der Flaeche, um die es geht: die Geraeteliste des
        Programmers, gebaut vom echten ``_refresh_fixture_list``."""
        from src.ui.views.programmer_view import ProgrammerView
        fx = self._spiider()
        view = ProgrammerView()
        self.addCleanup(view.deleteLater)
        lst = view._fixture_list
        texte = [lst.item(i).text().strip() for i in range(lst.count())]
        kopfzeilen = [t.lstrip("└ ").strip() for t in texte if t.startswith("└")]
        self.assertEqual(len(kopfzeilen), 20,
                         f"20 Kopf-Zeilen erwartet: {kopfzeilen}")
        self.assertEqual(kopfzeilen[0], "Grundfarbe")
        self.assertEqual(kopfzeilen[1], "Pixel 1")
        self.assertEqual(kopfzeilen[19], "Pixel 19")
        self.assertEqual([t for t in kopfzeilen if t.startswith("Kopf")], [],
                         "am Pixel-Kopf steht weiterhin „Kopf N“ in der Liste")
        # Die Zeile waehlt weiterhin denselben Kopf aus — nur ihr NAME aendert
        # sich. Sonst haette die Umbenennung die Auswahl mitverschoben.
        from PySide6.QtCore import Qt
        zellen = [lst.item(i).data(Qt.ItemDataRole.UserRole)
                  for i in range(lst.count())]
        self.assertIn(f"{fx.fid}:0", zellen)
        self.assertIn(f"{fx.fid}:19", zellen)

    def test_die_programmer_liste_eines_geraets_ohne_ringe_bleibt(self):
        """POSITIVKONTROLLE an derselben Flaeche."""
        from src.ui.views.programmer_view import ProgrammerView
        self._patch("MOVBAR4", _MOVBAR_MODE, _MOVBAR_CH, fid=2, adresse=200)
        view = ProgrammerView()
        self.addCleanup(view.deleteLater)
        lst = view._fixture_list
        texte = [lst.item(i).text().strip() for i in range(lst.count())]
        kopfzeilen = [t.lstrip("└ ").strip() for t in texte if t.startswith("└")]
        self.assertEqual(kopfzeilen, [f"Kopf {i}" for i in range(1, 5)])

    def test_die_matrix_vorschau_nennt_die_zelle_beim_namen(self):
        """Der Tooltip der Matrix-Zelle: dort sieht man, WELCHES Pixel man
        gerade adressiert. „Kopf 4" waere hier um eins daneben."""
        from src.core.engine.rgb_matrix import (RgbMatrixInstance,
                                                grids_from_positions)
        from src.ui.views.rgb_matrix_view import MatrixPreview
        fx = self._spiider()
        _n, cols, rows, pos = self._gruppe(fx)
        grid, head_grid = grids_from_positions(pos, cols, rows)
        inst = RgbMatrixInstance(name="Ring", cols=cols, rows=rows,
                                 fixture_grid=grid, head_grid=head_grid)
        p = MatrixPreview()
        self.addCleanup(p.deleteLater)
        p.set_matrix(inst)
        p.set_labels({fx.fid: "Spiider"}, {fx.fid: "pixel_head"})
        # Zeile 2 (Aussenring), Spalte 2 -> Pixel 10 (Manual: 8, 9, 10, …).
        self.assertEqual(p.assignment_text(2 * cols + 2), "Spiider · Pixel 10")
        self.assertEqual(p.assignment_text(0), "Spiider · Pixel 1")

    def test_der_matrix_tab_reicht_das_modell_wirklich_durch(self):
        """★★ Die VIZ-51-Lehre: „Feld vorhanden, Funktion richtig, Nutzlast
        leer". Der Test darueber ruft ``set_labels`` selbst auf und wuerde auch
        dann gruen bleiben, wenn der Matrix-Tab das Modell nie mitschickt.

        Hier laeuft der ECHTE Weg: Gruppe waehlen -> ``+ Neu`` -> Raster aus der
        Gruppe binden (``_assign_from_selection``) -> die eine Naht, die die
        Vorschau umschaltet (``_sync_preview`` -> ``_update_assignment_ui``).
        Gefragt wird danach die Vorschau selbst."""
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        fx = self._spiider()
        gid = self.state.find_head_matrix_group(fx.fid, dedicated=True)
        self.state.set_selected_group_id(gid)
        mv = RgbMatrixView()
        self.addCleanup(mv.deleteLater)
        mv._add()
        mv._assign_from_selection()
        self.assertIsNotNone(mv._current, "keine Matrix angelegt")
        self.assertEqual((mv._current.cols, mv._current.rows), (12, 3))
        # Zeile 2, Spalte 2 -> Pixel 10 (Aussenring beginnt bei Pixel 8).
        self.assertEqual(
            mv._preview.assignment_text(2 * 12 + 2).split(" · ")[-1], "Pixel 10",
            "der Matrix-Tab schickt das Render-Modell nicht mit — die Zelle "
            "heisst weiter nach ihrer Kopfnummer")

    def test_die_rasterzelle_im_gruppen_editor_sagt_es_auch(self):
        """★ Die dritte Flaeche, und die, auf der das RING-Raster angesehen und
        umsortiert wird. Sie hat nur Platz fuer eine Kurzform — die kommt aus
        derselben Beschriftung (``head_label_short``), sonst hiesse dasselbe
        Pixel hier „K4" und im Programmer „Pixel 3".

        Gemessen an der berechneten Aufschrift, nicht am gemalten Bild: dafuer
        ist sie aus ``paintEvent`` herausgezogen."""
        from src.core.app_state import head_label_short
        from src.ui.views.fixture_group_view import FixtureGridWidget
        fx = self._spiider()
        w = FixtureGridWidget()
        self.addCleanup(w.deleteLater)
        w.update_fixture_labels({fx.fid: "Spiider"}, {fx.fid: "pixel_head"})
        self.assertEqual(w.zell_beschriftung(f"{fx.fid}:3"), f"{fx.fid}·P3")
        self.assertEqual(w.zell_beschriftung(f"{fx.fid}:0"), f"{fx.fid}·GR")
        self.assertEqual(w.zell_beschriftung(fx.fid), f"{fx.fid}")
        # Die Kurzform ist wirklich abgeleitet, nicht zweitgeschrieben.
        self.assertEqual(head_label_short("pixel_head", 3), "P3")
        self.assertEqual(head_label_short("", 3), "K4")

    def test_die_rasterzelle_eines_geraets_ohne_ringe_bleibt(self):
        """POSITIVKONTROLLE: ohne Modell-Angabe (Bestandsgeraet, Alt-Aufrufer)
        steht in der Zelle weiter die Kopfnummer."""
        from src.ui.views.fixture_group_view import FixtureGridWidget
        w = FixtureGridWidget()
        self.addCleanup(w.deleteLater)
        w.update_fixture_labels({7: "Bar"})
        self.assertEqual(w.zell_beschriftung("7:0"), "7·K1")
        self.assertEqual(w.zell_beschriftung("7:3"), "7·K4")
        self.assertEqual(w.zell_beschriftung(7), "7")

    def test_der_gruppen_editor_reicht_das_modell_wirklich_durch(self):
        """★★ Wieder die VIZ-51-Frage: kommt das Modell auch an? Gefahren wird
        der echte Aufbau des Editors (``_refresh_fixtures`` laeuft im
        Konstruktor), gefragt wird das Raster-Widget."""
        from src.ui.views.fixture_group_view import FixtureGroupView
        fx = self._spiider()
        view = FixtureGroupView()
        self.addCleanup(view.deleteLater)
        self.assertEqual(
            view._grid_widget.zell_beschriftung(f"{fx.fid}:3"), f"{fx.fid}·P3",
            "der Gruppen-Editor schickt das Render-Modell nicht ans Raster")

    def test_die_matrix_vorschau_ohne_modell_bleibt_bei_kopf(self):
        """POSITIVKONTROLLE: ohne Modell-Angabe (Alt-Aufrufer, Geraet ohne
        Ringe) steht dort weiter „Kopf N"."""
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        from src.ui.views.rgb_matrix_view import MatrixPreview
        inst = RgbMatrixInstance(name="Reihe", cols=4, rows=1,
                                 fixture_grid=[7, 7, 7, 7],
                                 head_grid=[0, 1, 2, 3])
        p = MatrixPreview()
        self.addCleanup(p.deleteLater)
        p.set_matrix(inst)
        p.set_labels({7: "Bar"})
        self.assertEqual(p.assignment_text(0), "Bar · Kopf 1")
        self.assertEqual(p.assignment_text(3), "Bar · Kopf 4")


if __name__ == "__main__":
    unittest.main()
