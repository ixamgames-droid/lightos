"""VIZ-78: 2D-Live-Ansicht zeichnet billiger — bei gleichem Bild.

Gemessen (headless, Mega-Arena, 32 Geraete mit Effekten): ~2/3 eines Bilds in
``drawEllipse`` (geglaettete Ringe, Verlaufs-Kreise, Gehaeuse), dazu ~140
ORM-Attributzugriffe je Geraet und Bild fuer Werte, die sich nur mit dem Patch
aendern. Abgesichert:

- Kachel-Cache: eine Form (nur Fuellung ODER nur Kontur) von einer Kachel ist
  pixelgleich zum direkten Zeichnen — Zoom, krumme Lagen, Clip, Umlenkung.
- Nicht kachelbar bleibt direkt: deckender Verlauf (Qt mischt „Source"),
  duenne Stifte (Kosmetik-Stroker), gedrehter Painter, Deckkraft != 1.
- ``FixtureRenderer.draw`` je Geraetetyp mit/ohne Kachel-Cache pixelgleich,
  und der Cache wird dabei wirklich benutzt.
- Geraete-Steckbrief: Farbe/Strobe/Pan-Tilt wie die alten Helfer, Kanalliste
  nur einmal je Geraet abgefragt, Patch-Aenderung/Alter verwerfen ihn.
- Werte-Leser: ein ``get_all`` je Universum und Bild, Attrappe ohne
  ``get_all`` und fehlendes Universum wie bisher.
"""
import os
import random
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_all_top_level_widgets

import src.ui.views.live_view as LV

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(_app)


def _hintergrund(w=260, h=220, seed=7) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    rnd = random.Random(seed)
    for y in range(h):
        for x in range(w):
            img.setPixel(x, y, 0xFF000000 | rnd.randrange(1 << 24))
    return img


_BG = None


def _bg() -> QImage:
    global _BG
    if _BG is None:
        _BG = _hintergrund()
    return _BG


def _male(fn, zoom, pos, clip=None, kachel=True) -> QImage:
    img = _bg().copy()
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if clip == "rect":
            p.setClipRect(QRect(3, 5, 240, 200))
        elif clip == "region":
            p.setClipRegion(QRegion(QRect(3, 3, 250, 100)).united(
                QRegion(QRect(10, 110, 150, 100))))
        p.scale(zoom, zoom)
        p.translate(*pos)
        kx = LV._kachel_kontext(p) if kachel else None
        fn(p, kx)
    finally:
        p.end()
    return img


class KachelExaktTest(unittest.TestCase):
    """Eine Form von der Kachel == dieselbe Form direkt gezeichnet."""

    def setUp(self):
        LV._kacheln_leeren()

    def _formen(self):
        c = QColor(200, 40, 90)
        glow = QColor(200, 40, 90, 100)
        ring = QColor(80, 160, 255, 140)
        yield "fuellung_deckend", lambda p, kx: LV._form(
            p, kx, "e", LV._ellipse(0, 0, 12, 12), None, *LV._pinsel(c)[:1],
            None, LV._pinsel(c)[1])
        yield "fuellung_durchscheinend", lambda p, kx: LV._form(
            p, kx, "e", LV._ellipse(0, 0, 9, 9), None, LV._pinsel(glow)[0],
            None, LV._pinsel(glow)[1])
        yield "ring_gestrichelt", lambda p, kx: LV._form(
            p, kx, "e", LV._ellipse(0, 0, 21.6, 21.6),
            *self._nur_stift(LV._stift(ring, 2, Qt.PenStyle.DashLine)))
        yield "kontur_deckend", lambda p, kx: LV._form(
            p, kx, "e", LV._ellipse(0, 0, 15, 15),
            *self._nur_stift(LV._stift(QColor("#555"), 2)))
        yield "verlauf_mit_glow", lambda p, kx: LV._form(
            p, kx, "e", LV._ellipse(0, 0, 12, 12), None,
            LV._verlauf(0, 0, 13.5, ((0, c.lighter(180)), (0.6, c), (1, glow)))[0],
            None,
            LV._verlauf(0, 0, 13.5, ((0, c.lighter(180)), (0.6, c), (1, glow)))[1])
        yield "fx_badge", lambda p, kx: LV._form(
            p, kx, "rr", (5.0, -30.0, 22.0, 12.0, 3, 3), None, LV._B_FX[0],
            None, LV._B_FX[1])
        yield "gehaeuse_beide", lambda p, kx: LV._form(
            p, kx, "rr", (-28.5, -9.0, 57.0, 18.0, 4, 4), *LV._PB_161616_555_15)

    @staticmethod
    def _nur_stift(pk):
        return (pk[0], None, pk[1], None)

    def test_kachel_pixelgleich_ueber_zoom_lage_clip(self):
        for name, fn in self._formen():
            for zoom in (1.0, 0.75, 1.37, 2.0):
                for pos in ((60, 60), (60.5, 61.25), (73.37, 57.81)):
                    for clip in (None, "rect", "region"):
                        with self.subTest(form=name, zoom=zoom, pos=pos, clip=clip):
                            LV._kacheln_leeren()
                            direkt = _male(fn, zoom, pos, clip, kachel=False)
                            _male(fn, zoom, pos, clip)          # merken
                            t0 = LV._KACHEL_STATS["gebaut"] + LV._KACHEL_STATS["treffer"]
                            kachel = _male(fn, zoom, pos, clip)  # bauen + aufblenden
                            kachel2 = _male(fn, zoom, pos, clip)  # Treffer
                            t1 = LV._KACHEL_STATS["gebaut"] + LV._KACHEL_STATS["treffer"]
                            if not (name.startswith("verlauf") and zoom != 1.0):
                                self.assertGreater(t1, t0, "Kachel-Cache nicht benutzt")
                            self.assertTrue(direkt == kachel, "Kachel != direkt")
                            self.assertTrue(direkt == kachel2, "Treffer != direkt")

    def test_kachel_an_anderer_ganzzahliger_lage_wiederverwendet(self):
        fn = lambda p, kx: LV._form(  # noqa: E731
            p, kx, "e", LV._ellipse(0, 0, 21.6, 21.6),
            *self._nur_stift(LV._stift(QColor(80, 160, 255, 140), 2,
                                       Qt.PenStyle.DashLine)))
        for _ in range(LV.KACHEL_AB):
            _male(fn, 1.0, (60.25, 60.5))
        gebaut = LV._KACHEL_STATS["gebaut"]
        treffer = LV._KACHEL_STATS["treffer"]
        img = _male(fn, 1.0, (110.25, 97.5))       # gleicher Nachkomma-Anteil
        self.assertEqual(LV._KACHEL_STATS["gebaut"], gebaut)
        self.assertEqual(LV._KACHEL_STATS["treffer"], treffer + 1)
        self.assertTrue(img == _male(fn, 1.0, (110.25, 97.5), kachel=False))


class NichtKachelbarTest(unittest.TestCase):

    def setUp(self):
        LV._kacheln_leeren()

    def test_deckender_verlauf_hat_keinen_schluessel(self):
        c = QColor(255, 48, 48)
        _br, key = LV._verlauf(0, 0, 12, ((0, c.lighter(140)), (0.7, c),
                                          (1, c.darker(120))))
        self.assertIsNone(key)
        _br, key = LV._verlauf(0, 0, 12, ((0, c), (1, QColor(255, 48, 48, 127))))
        self.assertIsNotNone(key)

    def test_verlauf_nur_ohne_skalierung_und_rechteck_nie(self):
        c = QColor(255, 48, 48)
        br, bk = LV._verlauf(0, 0, 12, ((0, c), (1, QColor(255, 48, 48, 127))))
        pen, pk = LV._pinsel(c)
        for zoom in (0.8, 1.37):
            for _ in range(3):
                _male(lambda p, kx: LV._form(p, kx, "e", LV._ellipse(0, 0, 12, 12),
                                             None, br, None, bk), zoom, (60, 60))
                _male(lambda p, kx: LV._form(p, kx, "r", (-9.0, -3.0, 18.0, 6.0),
                                             None, pen, None, pk), zoom, (60, 60))
        self.assertFalse(LV._KACHELN)
        for _ in range(3):
            _male(lambda p, kx: LV._form(p, kx, "e", LV._ellipse(0, 0, 12, 12),
                                         None, br, None, bk), 1.0, (60.3, 60.7))
        self.assertTrue(LV._KACHELN)

    def test_duenner_stift_bleibt_direkt(self):
        pen, pk = LV._stift(QColor("#222"), 1)
        for _ in range(3):
            _male(lambda p, kx: LV._form(p, kx, "e", LV._ellipse(0, 0, 12, 12),
                                         pen, None, pk, None), 1.0, (60, 60))
        self.assertFalse(LV._KACHELN)

    def test_gedreht_oder_halbdurchsichtig_kein_kontext(self):
        img = QImage(50, 50, QImage.Format.Format_RGB32)
        p = QPainter(img)
        try:
            self.assertIsNotNone(LV._kachel_kontext(p))
            p.rotate(20)
            self.assertIsNone(LV._kachel_kontext(p))
            p.resetTransform()
            p.setOpacity(0.5)
            self.assertIsNone(LV._kachel_kontext(p))
        finally:
            p.end()



class KachelSchwelleTest(unittest.TestCase):
    """Review VIZ-78 #2: Kachel erst beim dritten gleichen Schluessel."""

    def setUp(self):
        LV._kacheln_leeren()

    @staticmethod
    def _bild(farben):
        """Ein Bild: jede Farbe zweimal (Paar), Fuellung + Glow-Verlauf."""
        img = QImage(1100, 400, QImage.Format.Format_RGB32)
        img.fill(0)
        p = QPainter(img)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            for i, c in enumerate(farben):
                for k in range(2):
                    p.save()
                    p.translate(40 + i * 60, 100 + k * 200)
                    kx = LV._kachel_kontext(p)
                    br, bk = LV._pinsel(c)
                    LV._form(p, kx, "e", LV._ellipse(0, 0, 6, 6), brush=br,
                             brush_key=bk)
                    br, bk = LV._verlauf(0, 0, 18, (
                        (0, c.lighter(160)), (0.7, c),
                        (1, QColor(c.red(), c.green(), c.blue(), 0))))
                    LV._form(p, kx, "e", LV._ellipse(0, 0, 18, 18), brush=br,
                             brush_key=bk)
                    p.restore()
        finally:
            p.end()

    def test_paare_mit_wechselnder_farbe_bauen_keine_kachel(self):
        rnd = random.Random(3)
        gebaut = LV._KACHEL_STATS["gebaut"]
        for _ in range(20):
            self._bild([QColor(rnd.randrange(256), rnd.randrange(256),
                               rnd.randrange(256), 200) for _ in range(16)])
        self.assertEqual(LV._KACHEL_STATS["gebaut"], gebaut)
        self.assertFalse(LV._KACHELN)

    def test_dritte_gleiche_form_baut_vierte_trifft(self):
        fn = lambda p, kx: LV._form(  # noqa: E731
            p, kx, "e", LV._ellipse(0, 0, 9, 9), None,
            LV._pinsel(QColor(10, 200, 90, 150))[0], None,
            LV._pinsel(QColor(10, 200, 90, 150))[1])
        gebaut = LV._KACHEL_STATS["gebaut"]
        _male(fn, 1.0, (60, 60))
        _male(fn, 1.0, (60, 60))
        self.assertEqual(LV._KACHEL_STATS["gebaut"], gebaut)
        _male(fn, 1.0, (60, 60))
        self.assertEqual(LV._KACHEL_STATS["gebaut"], gebaut + 1)
        treffer = LV._KACHEL_STATS["treffer"]
        _male(fn, 1.0, (60, 60))
        self.assertEqual(LV._KACHEL_STATS["treffer"], treffer + 1)



class KachelKontextGrenzenTest(unittest.TestCase):
    """Review VIZ-78 #3/#4: Zeichenmodus, Render-Hinweise, Zielformat."""

    def setUp(self):
        LV._kacheln_leeren()

    def _kontext(self, fmt=QImage.Format.Format_RGB32, modus=None):
        img = QImage(40, 40, fmt)
        p = QPainter(img)
        try:
            if modus is not None:
                p.setCompositionMode(modus)
            return LV._kachel_kontext(p)
        finally:
            p.end()

    def test_nur_source_over(self):
        CM = QPainter.CompositionMode
        self.assertIsNotNone(self._kontext(modus=CM.CompositionMode_SourceOver))
        for m in (CM.CompositionMode_Plus, CM.CompositionMode_Source,
                  CM.CompositionMode_Multiply):
            with self.subTest(modus=m):
                self.assertIsNone(self._kontext(modus=m))

    def test_nur_8bit_ziele(self):
        F = QImage.Format
        for fmt in (F.Format_RGB32, F.Format_ARGB32_Premultiplied,
                    F.Format_RGBA8888_Premultiplied, F.Format_RGBX8888,
                    F.Format_RGB888):
            with self.subTest(fmt=fmt):
                self.assertIsNotNone(self._kontext(fmt))
        for fmt in (F.Format_ARGB32, F.Format_RGB30,
                    F.Format_A2RGB30_Premultiplied,
                    F.Format_RGBA64_Premultiplied, F.Format_RGB16):
            with self.subTest(fmt=fmt):
                self.assertIsNone(self._kontext(fmt))

    def test_render_hinweise_teilen_keine_kachel(self):
        br, bk = LV._pinsel(QColor(30, 140, 250, 170))

        def male(aa):
            img = _bg().copy()
            p = QPainter(img)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, aa)
                p.translate(60.3, 70.6)
                LV._form(p, LV._kachel_kontext(p), "e",
                         LV._ellipse(0, 0, 11, 11), None, br, None, bk)
            finally:
                p.end()
            return img

        for _ in range(LV.KACHEL_AB + 1):
            male(True)
        img = QImage(_bg().copy())
        p = QPainter(img)
        try:
            p.translate(60.3, 70.6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(br)
            p.drawEllipse(QRectF(*LV._ellipse(0, 0, 11, 11)))
        finally:
            p.end()
        self.assertTrue(male(False) == img,
                        "ohne Antialiasing darf keine AA-Kachel kommen")


_TYPEN = ("par", "moving_head", "pixel_head", "par_bar", "mover_bar", "matrix",
          "led_bar", "strobe", "dimmer", "spider", "scanner", "laser", "hazer",
          "other", "unbekannt")


class FixtureRendererPixelgleichTest(unittest.TestCase):
    """Jedes Symbol mit und ohne Kachel-Cache Pixel fuer Pixel gleich."""

    def _zeichne(self, ft, zoom, ohne_cache, **kw):
        img = _bg().copy()
        p = QPainter(img)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.scale(zoom, zoom)
            LV.FixtureRenderer.draw(p, ft, 90.37 / zoom, 100.6 / zoom, 30,
                                    QColor(220, 60, 30), kw.pop("intensity", 255),
                                    "7", zoom=zoom, ring_segments=12, **kw)
        finally:
            p.end()
        return img

    def test_alle_typen_pixelgleich_und_cache_benutzt(self):
        orig = LV._kachel_kontext
        varianten = (
            dict(),
            dict(effects=["Chase", "Programmer"], anim_phase=0.3, selected=True),
            dict(effects=["X"], highlighted=True, intensity=90, lod=1),
            dict(blink_off=True, intensity=0, lod=2),
        )
        for ft in _TYPEN:
            for zoom in (1.0, 0.8, 1.6):
                for i, kw in enumerate(varianten):
                    with self.subTest(typ=ft, zoom=zoom, variante=i):
                        LV._kachel_kontext = lambda p: None
                        try:
                            ref = self._zeichne(ft, zoom, True, **dict(kw))
                        finally:
                            LV._kachel_kontext = orig
                        LV._kacheln_leeren()
                        for _ in range(LV.KACHEL_AB - 1):
                            self._zeichne(ft, zoom, False, **dict(kw))
                        a = self._zeichne(ft, zoom, False, **dict(kw))
                        b = self._zeichne(ft, zoom, False, **dict(kw))
                        self.assertTrue(ref == a, "erste Kachel weicht ab")
                        self.assertTrue(ref == b, "Treffer weicht ab")
        LV._kacheln_leeren()
        for _ in range(LV.KACHEL_AB + 1):
            self._zeichne("par", 1.0, False, effects=["X"], anim_phase=0.1)
        self.assertGreater(LV._KACHEL_STATS["treffer"], 0)
        self.assertTrue(LV._KACHELN, "PAR mit Effekt muss Kacheln anlegen")


# ── Steckbrief + Werte-Leser ───────────────────────────────────────────────────

class _UniGetAll:
    def __init__(self, vals):
        self.vals = vals
        self.get_all_aufrufe = 0
        self.get_channel_aufrufe = 0

    def get_channel(self, a):
        self.get_channel_aufrufe += 1
        return self.vals.get(a, 0)

    def get_all(self):
        self.get_all_aufrufe += 1
        return bytes(self.vals.get(i, 0) for i in range(1, 513))


class _UniNurKanal:
    def __init__(self, vals):
        self.vals = vals

    def get_channel(self, a):
        return self.vals.get(a, 0)


def _ch(n, attr, **kw):
    return SimpleNamespace(channel_number=n, attribute=attr, ranges=kw.get("ranges", []))


def _fixture(fid=1, address=1, **kw):
    f = SimpleNamespace(fid=fid, universe=1, address=address, label=f"F{fid}",
                        fixture_type="moving_head", pan_range_deg=540,
                        tilt_range_deg=270, pan_zero_dmx=128, tilt_zero_dmx=128,
                        aim_offset_pan=0.0, aim_offset_tilt=0.0)
    for k, v in kw.items():
        setattr(f, k, v)
    return f


_KANAELE = [_ch(1, "intensity"), _ch(2, "color_r"), _ch(3, "color_g"),
            _ch(4, "color_b"), _ch(5, "pan"), _ch(6, "pan_fine"), _ch(7, "tilt"),
            _ch(8, "shutter", ranges=[
                SimpleNamespace(range_from=0, range_to=9, name="Offen", kind="open"),
                SimpleNamespace(range_from=10, range_to=255, name="Strobe",
                                kind="strobe")]),
            _ch(9, "color_r")]        # zweiter Kopf: darf die Farbe nicht stellen


class SteckbriefTest(unittest.TestCase):

    def setUp(self):
        self.c = LV.StageCanvas()
        self.addCleanup(self.c.deleteLater)
        self.aufrufe = []
        orig = LV.get_channels_for_patched

        def kanaele(f):
            self.aufrufe.append(f.fid)
            return _KANAELE
        LV.get_channels_for_patched = kanaele
        self.addCleanup(setattr, LV, "get_channels_for_patched", orig)
        self.alt = self.c._state.universes
        self.addCleanup(setattr, self.c._state, "universes", self.alt)

    def _vorab(self):
        return {"namen": {}, "square": {}, "prog": set()}

    def test_farbe_und_strobe_wie_alte_helfer(self):
        fx = _fixture()
        rnd = random.Random(3)
        for uni_cls in (_UniGetAll, _UniNurKanal):
            for _ in range(40):
                vals = {i: rnd.randrange(256) for i in range(1, 10)}
                self.c._state.universes = {1: uni_cls(vals)}
                lese = self.c._wert_leser()
                sb = self.c._steckbrief(fx)
                alt_farbe, alt_int = self.c._fixture_color_and_intensity(fx)
                neu_farbe, neu_int = self.c._farbe_aus_steckbrief(sb, lese)
                self.assertEqual(alt_farbe.rgba(), neu_farbe.rgba())
                self.assertEqual(alt_int, neu_int)
                alt = self.c._get_strobe_info(fx.fid, fx, [], self._vorab())
                neu = self.c._strobe_aus_steckbrief(sb, lese, self._vorab())
                self.assertEqual(alt[0], neu[0])

    def test_fehlendes_universum_wie_bisher(self):
        self.c._state.universes = {}
        sb = self.c._steckbrief(_fixture())
        farbe, inten = self.c._farbe_aus_steckbrief(sb, self.c._wert_leser())
        self.assertEqual((farbe.red(), farbe.green(), farbe.blue(), inten), (60, 60, 60, 0))
        self.assertEqual(self.c._strobe_aus_steckbrief(sb, self.c._wert_leser(),
                                                       self._vorab()), (0.0, True))

    def test_ein_get_all_je_universum_und_bild(self):
        uni = _UniGetAll({1: 255, 2: 10})
        self.c._state.universes = {1: uni}
        lese = self.c._wert_leser()
        for fid in (1, 2, 3):
            sb = self.c._steckbrief(_fixture(fid, address=1 + 10 * fid))
            self.c._farbe_aus_steckbrief(sb, lese)
            self.c._strobe_aus_steckbrief(sb, lese, self._vorab())
        self.assertEqual(uni.get_all_aufrufe, 1)
        self.assertEqual(uni.get_channel_aufrufe, 0)

    def test_kanalliste_nur_einmal_je_geraet_und_patch_verwirft(self):
        self.c._state.universes = {1: _UniGetAll({})}
        fx = _fixture()
        for _ in range(5):
            self.c._steckbrief(fx)
        self.assertEqual(self.aufrufe, [1])
        fx.address = 20                          # Umadressieren -> neuer Fingerabdruck
        sb = self.c._steckbrief(fx)
        self.assertEqual(self.aufrufe, [1, 1])
        self.assertIn(("intensity", 20), sb["farbe"])
        self.c._patch_geaendert()                # Patch-Event
        self.c._steckbrief(fx)
        self.assertEqual(self.aufrufe, [1, 1, 1])

    def test_spider_dual_tilt_umschalten_verwirft_steckbrief(self):
        """Review VIZ-78 #6: get_channels_for_patched haengt auch an
        ``spider_dual_tilt`` — Umschalten muss sofort wirken (wie vorher),
        nicht erst nach dem Hoechstalter."""
        self.c._state.universes = {1: _UniGetAll({})}
        fx = _fixture(spider_dual_tilt=False)
        self.c._steckbrief(fx)
        fx.spider_dual_tilt = True
        self.c._steckbrief(fx)
        self.assertEqual(self.aufrufe, [1, 1])

    def test_paint_fragt_kanalliste_nicht_je_bild(self):
        """Rot ohne Steckbrief: jedes Bild fragte die Kanalliste mehrfach je Geraet."""
        fx = _fixture()
        self.c._state.get_patched_fixtures = lambda: [fx]
        self.addCleanup(vars(self.c._state).pop, "get_patched_fixtures", None)
        self.c._state.universes = {1: _UniGetAll({1: 255, 2: 200})}
        self.c._positions = {1: (100.0, 100.0)}
        self.c.resize(300, 250)
        for _ in range(4):
            self.c.grab()
        self.assertEqual(self.aufrufe, [1])

    def test_steckbrief_verfaellt_nach_hoechstalter(self):
        self.c._state.universes = {1: _UniGetAll({})}
        fx = _fixture()
        self.c._state.get_patched_fixtures = lambda: [fx]
        self.addCleanup(vars(self.c._state).pop, "get_patched_fixtures", None)
        self.c._positions = {1: (100.0, 100.0)}
        self.c.resize(300, 250)
        self.c.grab()
        self.c._steckbrief_zeit -= self.c.STECKBRIEF_MAX_ALTER_S + 0.5
        self.c.grab()
        self.assertEqual(self.aufrufe, [1, 1])


class CanvasBildTest(unittest.TestCase):
    """Ganzes Canvas-Bild: Kachel-Cache an == aus (mehrere DMX-Staende)."""

    def test_canvas_mit_und_ohne_cache_gleich(self):
        c = LV.StageCanvas()
        self.addCleanup(c.deleteLater)
        orig_k = LV.get_channels_for_patched
        LV.get_channels_for_patched = lambda f: _KANAELE
        self.addCleanup(setattr, LV, "get_channels_for_patched", orig_k)
        typen = ("par", "moving_head", "led_bar", "spider", "laser", "hazer")
        fxs = [_fixture(i + 1, address=1 + 10 * i, fixture_type=t)
               for i, t in enumerate(typen)]
        c._state.get_patched_fixtures = lambda: fxs
        self.addCleanup(vars(c._state).pop, "get_patched_fixtures", None)
        alt = c._state.universes
        self.addCleanup(setattr, c._state, "universes", alt)
        c._positions = {f.fid: (80.0 + 70.3 * i, 120.0 + 13.7 * (i % 3))
                        for i, f in enumerate(fxs)}
        c._compute_label_gaps()
        c.set_selection([2])
        c.resize(600, 300)
        rnd = random.Random(11)
        orig_kontext = LV._kachel_kontext
        import time as _time
        LV.time = SimpleNamespace(time=lambda: 1000.25, monotonic=_time.monotonic)
        self.addCleanup(setattr, LV, "time", _time)
        for z in (1.0, 0.75, 1.3):
            c.set_zoom(z)
            for _ in range(3):
                vals = {i: rnd.randrange(256) for i in range(1, 70)}
                c._state.universes = {1: _UniGetAll(vals)}
                LV._kachel_kontext = lambda p: None
                try:
                    ref = c.grab().toImage()
                finally:
                    LV._kachel_kontext = orig_kontext
                c.grab()
                self.assertTrue(ref == c.grab().toImage(), f"Zoom {z}")


if __name__ == "__main__":
    unittest.main()
