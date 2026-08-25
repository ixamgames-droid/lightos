"""VIZ-53 — die 2D-Seite kennt `pixel_head` jetzt auch.

**Der Befund (aus FM-14b).** Ein Pixel-Moving-Head ist als ``moving_head``
gepatcht; sein eigenes Render-Modell kommt erst aus ``viz_model_for``. Die zwei
2D-Stellen verzweigten aber nur auf ``spider``/``par_bar``/``mover_bar`` — der
Pixel-Kopf fiel in ``live_view`` sogar buchstaeblich durch ``"head" in ft`` in
den generischen Moving-Head-Zweig und stand als gewoehnlicher Kopf da, waehrend
das 3D-Top-Down-Icon (``topdown_icons.js``) laengst seinen Ring zeigte.
Derselbe 2D/3D-Riss, den VIZ-51/52 fuer die Panel-Reihenfolge geschlossen
haben, nur fuer den neuen Typ.

**Die Zahl, um die es geht.** Die Segmentzahl ist NICHT die Bankzahl. Die
3D-Nutzlast schickt ``nHeads`` (Zahl der ``color_r``-Baenke) und ``pixelBase``
(fuehrende Baenke, die KEIN Ring-Pixel sind, CDX-55); der Ring hat
``nHeads - pixelBase`` Segmente. Beim Robin Spiider im 91-Kanal-Pixelmodus sind
das **20 - 1 = 19**. Wer 20 zeichnet, hat den Fehler von UI-52 nachgebaut.

**Wie hier gemessen wird — der ECHTE Weg.** Nicht ueber einen direkten Aufruf
des Zeichners mit selbst gesetzter Segmentzahl (die Seitentuer, durch die der
Produktionspfad nie geht), sondern:

  * Live-View: eine echte ``StageCanvas`` mit dem echten, aus dem QUELLTEXT
    geseedeten Spiider-Profil, ausgeloest ueber ``grab()`` -> ``paintEvent``.
  * Listen-Icon: ``mini_icons.fixture_icon_for(fixture)`` — genau der Aufruf,
    den Patch-Ansicht und Gruppenbaum machen.

Die Gegenprobe steht ueberall daneben: **dasselbe Geraet im Wash-Modus** ist ein
gewoehnlicher Moving Head, fragt nie nach einem Ring und bekommt sein
bisheriges Symbol — beim Listen-Icon Pixel fuer Pixel nachgewiesen.

**★★★ Und gemessen wird am BILD, nicht an der Naht (Gegenpruefung 25.08.).**
Die erste Fassung zaehlte, mit welcher Zahl ``mini_icons.ring_offsets`` gerufen
wird und wie viele Plaetze zurueckkommen. Zwischen dieser Naht und dem Bild
liegt aber die Zeichenschleife: ein ``break``, ein ``[:1]``, ein entferntes
``drawEllipse`` — und der Nutzer sieht keinen Ring mehr, waehrend die ganze
Datei gruen bleibt. Gemessen (Pruefer): ``ring_offsets(...)[:1]`` an BEIDEN
2D-Stellen liess alle 19 Tests durch, obwohl nur noch EIN Punkt gezeichnet
wurde. **Die Zusage war breiter als die Messung** — genau die Fehlerklasse,
gegen die dieses Projekt seine Testdisziplin gebaut hat.

Deshalb gibt es jetzt zwei Messungen AM PIXEL:

  * ``kranz_messung`` legt ein Helligkeitsprofil auf den Kranzkreis des
    gerenderten Glyphs und zaehlt die **zusammenhaengenden leuchtenden
    Flaechen**. Der Spiider muss auf 19 kommen, ein gewoehnlicher Moving Head
    auf 0 — und ein 3-Zonen-Wash auf 3: der Waechter ZAEHLT, er erkennt nicht
    bloss „Pixel-Kopf ja/nein".
  * ``icon_kranz`` misst am Listen-Icon in der **Vorgabegroesse 16**, mit der
    jeder Produktionsaufrufer ruft: wie viel der Kopfflaeche leuchtet heller als
    die Kopfmitte. Beim Pixel-Kopf die Haelfte, beim Moving Head nichts (dessen
    Mitte IST das Hellste).

**Was dabei ueber das Produkt herauskam.** Die Segmente sind nicht in jeder
Groesse einzeln zaehlbar: bei der Live-View-Vorgabegroesse 30 px liegen 19
Punkte auf 8 px Radius und verlaufen zum leuchtenden Kranz (gemessen 15 von 19
trennbar), beim 16-px-Icon erst recht. Das ist so gewollt und in der Sache
richtig — was der Nutzer dort unterscheiden muss, ist *Ring* gegen
*geschlossene Linse*, und das ist auch klein noch messbar. Die ZAHL wird
deshalb dort gemessen, wo sie sichtbar ist (lesbare Glyphgroesse), die
*Erkennbarkeit* dort, wo der Nutzer sie wirklich sieht (Vorgabegroesse).
"""
from __future__ import annotations

import math
import os
import types
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                  # noqa: E402
from sqlalchemy.orm import Session, selectinload               # noqa: E402

from PySide6.QtCore import QRect                               # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402

# ★ Vor der QApplication importieren: `visualizer_window` zieht
# QtWebEngineWidgets nach, und das muss vor der ersten QApplication geladen
# sein. Die 3D-Nutzlast wird hier gebraucht, weil das Item eine Aussage UEBER
# SIE macht ("dieselbe Segmentzahl, die das 3D bekommt").
from src.ui.visualizer.visualizer_window import VisualizerBridge  # noqa: E402

from _fixture_quelle import frische_library                    # noqa: E402
from src.core.app_state import (                               # noqa: E402
    clear_channel_cache, pixel_ring_banks_for, pixel_ring_segments,
    viz_model_for)
from src.core.pixel_order import ring_segmente                 # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureChannel, FixtureMode, FixtureProfile, Manufacturer, PatchedFixture)

import src.ui.views.live_view as live_view                     # noqa: E402
import src.ui.widgets.mini_icons as mini_icons                 # noqa: E402

_PIXEL = "91-Kanal Pixel RGB (Mode 7)"
_WASH = "27-Kanal Wash (Mode 5)"

# Die Zahl aus dem Chart: 20 Farb-Baenke (Grundfarbe + 19 Pixel), Versatz 1.
ERWARTETE_SEGMENTE = 19

# Glyph-Groesse, bei der die Segmente EINZELN im Bild liegen. Die Vorgabe der
# Live-View ist 30 px (`live_view.StageCanvas._fixture_size`); dort liegen 19
# Punkte auf 8 px Radius und verlaufen zum Kranz — gemessen 15 statt 19
# trennbare Flaechen. Die ZAHL laesst sich nur messen, wo sie sichtbar ist;
# gemessen ist der Wert 19 stabil ab Glyphgroesse 70 (70/80/90/100/120/160/
# 200/240 alle 19). 160 ist eine Groesse, die der Nutzer per Zoom und
# Fixture-Groesse wirklich einstellen kann.
LESBARE_GROESSE = 160
# Die Vorgabe der Live-View — die Groesse, in der der Ring beim ersten Start steht.
VORGABE_GROESSE = 30.0
# Die Vorgabe von `fixture_icon_for(f)`: JEDER Produktionsaufrufer ruft ohne
# Groessenangabe (patch_view.py, fixture_group_view.py, live_view.py 2x), keine
# Ansicht setzt `setIconSize`.
ICON_VORGABE = 16

JS_MODUL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "scene_src", "fixtures", "pixel_order.js")


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _patched(profile_id, mode_name, channel_count, **kw):
    return PatchedFixture(fid=kw.pop("fid", 1), label=kw.pop("label", "Spiider"),
                          fixture_profile_id=profile_id, mode_name=mode_name,
                          universe=kw.pop("universe", 1),
                          address=kw.pop("address", 1),
                          channel_count=channel_count,
                          fixture_type=kw.pop("fixture_type", "moving_head"),
                          **kw)


def _dict_for(f) -> dict:
    """Die ECHTE 3D-Nutzlast dieses Geraets (dieselbe Kette wie im Betrieb)."""
    fake_self = SimpleNamespace(_state=SimpleNamespace(
        visualizer_positions={}, visualizer_rotations={}, visualizer_docks={}))
    fake_self._viz_model_for = types.MethodType(
        VisualizerBridge._viz_model_for, fake_self)
    return VisualizerBridge._fixture_to_dict(fake_self, f)


def _hell(bild, x, y) -> int:
    """Helligkeit eines Bildpunktes (hellster Farbkanal, 0..255)."""
    c = bild.pixelColor(int(round(x)), int(round(y)))
    return max(c.red(), c.green(), c.blue())


def _kranz_profil(bild, mx, my, radius, schritte=3600) -> list:
    """Helligkeit entlang des Kranzkreises, in ``schritte`` Winkelschritten."""
    werte = []
    for i in range(schritte):
        w = math.radians(i * 360.0 / schritte)
        werte.append(_hell(bild, mx + math.cos(w) * radius,
                           my + math.sin(w) * radius))
    return werte


def kranz_messung(bild, mx, my, radius, schritte=3600) -> tuple:
    """``(Kontrast, Zahl der leuchtenden Flaechen)`` — gemessen AM BILD.

    ★★★ Die Antwort auf den Gegenpruefungs-Befund vom 25.08.: gezaehlt wird
    nicht mehr, mit welcher Zahl ``ring_offsets`` gerufen wird, sondern wie
    viele zusammenhaengende helle Stellen auf dem Kranzkreis tatsaechlich
    LIEGEN. Alles, was zwischen Naht und Bild schiefgehen kann — ein ``break``,
    ein ``[:1]``, eine Farbe mit Alpha 0, ein Platz ausserhalb des Rechtecks —
    faellt damit auf.

    ``Kontrast`` = Spanne zwischen dunkelster und hellster Stelle des Kreises.
    Er entscheidet, ob ueberhaupt etwas moduliert ist: die geschlossene Linse
    eines gewoehnlichen Moving Heads ist auf diesem Kreis praktisch gleichmaessig
    hell (gemessen Spanne 2..8 von 255), der Ring des Pixel-Kopfes nicht
    (gemessen 73..84).

    Die Schwelle ist bewusst **absolut nach unten begrenzt** (mindestens 40 ueber
    dem dunkelsten Punkt): eine reine Anteils-Schwelle wuerde auf einer flachen
    Flaeche das Quantisierungsrauschen abtasten und dort Dutzende „Segmente"
    finden — ein Waechter, der alles beanstandet. Nach oben zaehlt der Anteil
    (55 % der Spanne), damit der Richtungs-Strahl des Kopfes (er kreuzt den
    Kranzkreis, ist aber nur ``color`` statt ``color.lighter(160)``) nicht als
    zusaetzliches Segment durchgeht.

    Der Kreis wird zyklisch ausgewertet: eine Flaeche ueber 0 Grad hinweg zaehlt
    einmal, nicht zweimal.
    """
    werte = _kranz_profil(bild, mx, my, radius, schritte)
    tief, hoch = min(werte), max(werte)
    schwelle = tief + max(40.0, 0.55 * (hoch - tief))
    leuchtet = [v > schwelle for v in werte]
    flaechen = sum(1 for i in range(schritte)
                   if leuchtet[i] and not leuchtet[i - 1])
    return hoch - tief, flaechen


def icon_kranz(bild, s) -> tuple:
    """``(Helligkeit der Kopfmitte, leuchtender Anteil der Kopfflaeche)``.

    Fuer das Listen-Icon in der Vorgabegroesse 16. Dort verlaufen 19 Punkte auf
    knapp 2 px Kranzradius zu einem Ring — EINZELN zaehlbar sind sie nicht mehr,
    und der Kranzkreis selbst trifft nur rund zehn verschiedene Bildpunkte. Ein
    Winkelprofil misst in dieser Groesse mehr Rundungsfehler als Ring.

    Gemessen wird deshalb die **Flaeche**: alle Bildpunkte innerhalb des
    Kopfgehaeuses (``d <= 0.17s`` um ``(0.5s, 0.46s)`` — die Kreisdaten des
    Zeichners ``mini_icons._draw_pixel_head``), und davon der Anteil, der
    deutlich heller ist als die Kopfmitte.

    Das ist genau die Unterscheidung, auf die es in dieser Groesse ankommt:
    **Ring gegen geschlossene Linse.** Beim Pixel-Kopf ist die Mitte das dunkle
    Gehaeuse und der Kranz traegt die Farbe; beim gewoehnlichen Moving Head ist
    die Mitte das Hellste im Bild, der Anteil also 0.
    """
    mx, my = s * 0.5, s * 0.46
    mitte = _hell(bild, mx, my)
    kopf = [_hell(bild, x, y)
            for y in range(s) for x in range(s)
            if math.hypot(x + 0.5 - mx, y + 0.5 - my) <= s * 0.17]
    return mitte, sum(1 for v in kopf if v > mitte + 60) / max(1, len(kopf))


class _RingZaehler:
    """Zaehlt die Aufrufe von ``ring_offsets`` und laesst sie echt laufen.

    Nicht gemockt, nur belauscht: gezeichnet wird weiter mit den ECHTEN
    Plaetzen, gemessen wird die Zahl, mit der der Produktionspfad ankommt."""

    def __init__(self, fall):
        self.aufrufe = []          # angeforderte Segmentzahlen
        self.plaetze = []          # tatsaechlich gelieferte Plaetze je Aufruf
        self._echt = mini_icons.ring_offsets
        mini_icons.ring_offsets = self
        fall.addCleanup(setattr, mini_icons, "ring_offsets", self._echt)

    def __call__(self, segments, radius, max_cell=0.0):
        out = self._echt(segments, radius, max_cell)
        self.aufrufe.append(int(segments))
        self.plaetze.append(len(out))
        return out


class _LibraryCase(unittest.TestCase):
    """Frisch aus dem Quelltext geseedete Bibliothek (FIXTEST-FRESH): ein Test
    gegen die Datei im App-Ordner pruefte den Stand vom ersten Lauf."""

    @classmethod
    def setUpClass(cls):
        cls._qapp = _app()

    def setUp(self):
        self._eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)
        # Der Icon-Cache lebt modulweit und ueberdauert die Testdatei.
        mini_icons._cache.clear()
        self.addCleanup(mini_icons._cache.clear)

    def _ids(self, short):
        with Session(self._eng) as s:
            p = s.execute(
                select(FixtureProfile).options(selectinload(FixtureProfile.modes))
                .where(FixtureProfile.short_name == short)).scalars().first()
            self.assertIsNotNone(p, f"Profil {short} fehlt in der Bibliothek")
            return p.id, {m.name: m.channel_count for m in p.modes}

    def _spiider(self, modus, **kw):
        pid, modi = self._ids("SPIIDER")
        return _patched(pid, modus, modi[modus], **kw)

    def _zonen_wash(self, baenke=3, **kw):
        """Ein LED-Wash-Kopf mit ``baenke`` Farbzonen — 1 Pan, 1 Tilt, RGBW.

        ★ Die Klasse, die die Gegenpruefung benannt hat: ``viz_model_for``
        fuehrt seit FM-14 JEDEN Kopf mit 1 Pan + 1 Tilt + >=3 Farb-Baenken als
        ``pixel_head``. In der Bibliothek des Nutzers sind das **88 von 5122
        Modi** — darunter Geraete, die jeder Bediener fuer gewoehnliche Mover
        haelt: Robin 600 LED Wash (Mode 1, 3 Baenke), Robin 800 LEDWash,
        A.leda B-EYE K10/K20, Intimidator Trio. Die MITGELIEFERTE Bibliothek
        enthaelt genau EINEN pixel_head-Modus (SPIIDER, 20 Baenke), diese Klasse
        kam in keinem Test vor.

        Deshalb wird das Geraet hier angelegt — in der frisch geseedeten
        Test-Library im Temp-Verzeichnis, nie in der echten Datei des Nutzers.
        Die Kanalfolge ist die des Robin 600 LED Wash Mode 1: gleichmaessige
        RGBW-Baenke ohne Grundfarben-Lage davor, also Versatz 0 und
        ``baenke`` Segmente (gemessen an der echten Bibliothek: 3, 0, 3).
        """
        with Session(self._eng) as s:
            hersteller = s.execute(select(Manufacturer)).scalars().first()
            attrs = ["pan", "tilt", "dimmer"]
            for _ in range(baenke):
                attrs += ["color_r", "color_g", "color_b", "color_w"]
            modus = FixtureMode(name=f"{len(attrs)}-Kanal Zonen",
                                channel_count=len(attrs))
            for i, a in enumerate(attrs, start=1):
                modus.channels.append(
                    FixtureChannel(channel_number=i, name=a, attribute=a))
            profil = FixtureProfile(
                manufacturer_id=hersteller.id, name=f"Zonen-Wash {baenke}",
                short_name=f"ZONE{baenke}", fixture_type="moving_head",
                source="test")
            profil.modes.append(modus)
            s.add(profil)
            s.commit()
            pid, mname, count = profil.id, modus.name, modus.channel_count
        kw.setdefault("fid", 3)
        kw.setdefault("label", "Wash")
        return _patched(pid, mname, count, **kw)


# ════════════════════════════════════════════════════════════════════════════
# 1. Die Zahl: 2D und 3D rechnen dieselbe Segmentzahl aus denselben Kanaelen
# ════════════════════════════════════════════════════════════════════════════

class SegmentzahlTest(_LibraryCase):

    def test_der_spiider_hat_zwanzig_baenke_und_neunzehn_segmente(self):
        """★ Der Kern des Items: 20 Baenke, Versatz 1 -> 19 Segmente. Wer die
        Bankzahl nimmt, zeichnet 20 und baut UI-52 nach."""
        f = self._spiider(_PIXEL)
        self.assertEqual(pixel_ring_banks_for(f), (20, 1))
        self.assertEqual(pixel_ring_segments(f), ERWARTETE_SEGMENTE)

    def test_die_2d_zahl_ist_die_zahl_der_3d_nutzlast(self):
        """★★ Nicht „zufaellig gleich": die 2D-Zahl wird aus DERSELBEN Rechnung
        auf DENSELBEN zwei Zahlen gebildet, die an das 3D gehen."""
        f = self._spiider(_PIXEL)
        d = _dict_for(f)
        self.assertEqual((d["model"], d["nHeads"], d["pixelBase"]),
                         ("pixel_head", 20, 1))
        _basis, anzahl_3d = ring_segmente(d["nHeads"], d["pixelBase"])
        self.assertEqual(pixel_ring_segments(f), anzahl_3d)

    def test_der_wash_modus_ist_kein_pixel_kopf(self):
        """★ Positivkontrolle: dasselbe Geraet ohne Pixel-Kanaele."""
        f = self._spiider(_WASH, fid=2)
        self.assertEqual(viz_model_for(f) or f.fixture_type, "moving_head")
        self.assertEqual(_dict_for(f)["nHeads"], 0)

    def test_ohne_lesbare_kanaele_faellt_die_ansicht_nicht_aus(self):
        """Ein Geraet, dessen Kanaele nicht zu holen sind, liefert (0, 0) —
        daraus macht ``ring_segmente`` EIN Segment statt einer Ausnahme im
        paintEvent."""
        kaputt = SimpleNamespace(fid=99)
        self.assertEqual(pixel_ring_banks_for(kaputt), (0, 0))
        self.assertEqual(pixel_ring_segments(kaputt), 1)


class JsFassungTest(unittest.TestCase):
    """Die JS-Fassung rendert (3D-Modell + Top-Down-Icon), die Python-Fassung
    zeichnet 2D — zwei Formeln, die still auseinanderlaufen, waeren die
    Drift-Quelle aus der FM16E-Lehre."""

    def test_js_hat_dieselbe_ring_regel(self):
        js = open(JS_MODUL, encoding="utf-8").read()
        self.assertIn("export function ringSegmente(nBaenke, basisBaenke)", js)
        self.assertIn("Math.max(1, Math.floor(nBaenke || 0))", js)
        self.assertIn("Math.min(Math.max(0, Math.floor(basisBaenke || 0)), baenke - 1)", js)
        self.assertIn("return { basis, anzahl: baenke - basis };", js)

    def test_python_liefert_dieselben_zahlen(self):
        # Dieselben Faelle, die die JS-Zeilen oben beschreiben.
        self.assertEqual(ring_segmente(20, 1), (1, 19))     # Spiider, Pixelmodus
        self.assertEqual(ring_segmente(20, 0), (0, 20))     # alles Pixel
        self.assertEqual(ring_segmente(0, 0), (0, 1))       # unvollstaendige Nutzlast
        self.assertEqual(ring_segmente(3, 9), (2, 1))       # Versatz frisst nie alles
        self.assertEqual(ring_segmente(100, 1), (1, 99))    # keine Kappung (CDX-56)


# ════════════════════════════════════════════════════════════════════════════
# 2. Der echte Weg 1: die 2D-Live-View (paintEvent einer echten StageCanvas)
# ════════════════════════════════════════════════════════════════════════════

class _LiveViewCase(_LibraryCase):
    """Gemeinsame Buehne fuer beide Live-View-Klassen: EIN Geraet, EIN
    ``paintEvent``, feste Position — Prefs des Rechners spielen nicht mit."""

    # Wo das Glyph steht (Weltkoordinaten) und wie gross der Ausschnitt ist, in
    # dem NUR das Symbol liegt: das Label sitzt ab ``size*0.55`` = 16.5 px
    # darunter, der Ausschnitt endet bei 15.
    MITTE = (200.0, 150.0)
    GLYPH = QRect(200 - 15, 150 - 15, 30, 30)

    def _canvas(self, fixture, groesse=VORGABE_GROESSE):
        c = live_view.StageCanvas()
        self.addCleanup(c.deleteLater)
        # Prefs des Rechners neutralisieren — Zoom/Groesse duerfen das Ergebnis
        # nicht bewegen.
        c.zoom = 1.0
        c._fixture_size = float(groesse)
        c._apply_canvas_size()
        c._positions = {fixture.fid: self.MITTE}
        c._nn_gap = {fixture.fid: 1e9}
        c._state.get_patched_fixtures = lambda: [fixture]
        self.addCleanup(lambda: c._state.__dict__.pop("get_patched_fixtures", None))
        return c

    def _gezeichnet(self, fixture):
        """Rendert die Canvas EINMAL ueber den echten paintEvent."""
        zaehler = _RingZaehler(self)
        gerufen = []
        echt = live_view.FixtureRenderer.draw

        def _mit(painter, fixture_type, *a, **kw):
            gerufen.append((fixture_type, kw.get("ring_segments", 0)))
            return echt(painter, fixture_type, *a, **kw)

        live_view.FixtureRenderer.draw = staticmethod(_mit)
        self.addCleanup(setattr, live_view.FixtureRenderer, "draw",
                        staticmethod(echt))
        # Nur der Glyph-Ausschnitt: das Label darunter traegt ein anderes
        # Praefix ("PIX" statt "MH") und wuerde einen Bildvergleich schon
        # deshalb bestehen lassen, ohne dass am SYMBOL etwas anders waere.
        bild = self._canvas(fixture).grab().toImage().copy(self.GLYPH)
        return zaehler, gerufen, bild


class LiveViewTest(_LiveViewCase):
    """Misst an der NAHT: welche Zahl reist den Produktionsweg entlang?
    Die Klasse weiter unten misst, was davon im Bild ankommt."""

    def test_der_pixel_kopf_bekommt_neunzehn_segmente(self):
        """★★★ Der echte Weg: gepatchtes Geraet -> paintEvent -> Ring.
        Gemessen wird an der Stelle, an der die Segment-Plaetze entstehen."""
        zaehler, gerufen, _bild = self._gezeichnet(self._spiider(_PIXEL))
        self.assertEqual(gerufen, [("pixel_head", ERWARTETE_SEGMENTE)],
                         "die Canvas muss den Typ erkennen UND die Zahl mitgeben")
        self.assertEqual(zaehler.aufrufe, [ERWARTETE_SEGMENTE])
        self.assertEqual(zaehler.plaetze, [ERWARTETE_SEGMENTE],
                         "es muessen auch so viele Plaetze gezeichnet werden")

    def test_die_gezeichnete_zahl_ist_die_zahl_der_3d_nutzlast(self):
        """★★ Die Zusage des Items in einem Satz: 2D zeichnet so viele
        Segmente, wie das 3D bekommt."""
        f = self._spiider(_PIXEL)
        d = _dict_for(f)
        zaehler, _gerufen, _bild = self._gezeichnet(f)
        self.assertEqual(zaehler.plaetze,
                         [ring_segmente(d["nHeads"], d["pixelBase"])[1]])

    def test_ein_gewoehnlicher_moving_head_fragt_nie_nach_einem_ring(self):
        """★ Positivkontrolle am ECHTEN Geraet: derselbe Spiider im Wash-Modus.
        Kein Ring, keine Segmentzahl — sein Zweig ist unberuehrt."""
        zaehler, gerufen, _bild = self._gezeichnet(self._spiider(_WASH, fid=2))
        self.assertEqual(gerufen, [("moving_head", 0)])
        self.assertEqual(zaehler.aufrufe, [],
                         "ein Moving Head darf gar nicht erst nach Ring-Plaetzen "
                         "fragen — sonst beanstandet der Waechter alles")

    def test_pixel_kopf_und_moving_head_sehen_verschieden_aus(self):
        """★★ Dass eine ZAHL ankommt, heisst noch nicht, dass sie zu sehen ist:
        beide Geraete stehen an derselben Stelle, in derselben Groesse — die
        Bilder muessen sich unterscheiden."""
        _z1, _g1, pixelbild = self._gezeichnet(self._spiider(_PIXEL, fid=7))
        _z2, _g2, mhbild = self._gezeichnet(self._spiider(_WASH, fid=7))
        self.assertNotEqual(pixelbild, mhbild,
                            "der Pixel-Kopf bekam wieder das Moving-Head-Symbol")


# ════════════════════════════════════════════════════════════════════════════
# 2b. Dieselbe Live-View, aber AM BILD gezaehlt (Gegenpruefung 25.08.)
# ════════════════════════════════════════════════════════════════════════════

class LiveViewBildTest(_LiveViewCase):
    """★★★ Was WIRKLICH auf der Flaeche landet.

    Die Klasse darueber misst an der Naht (``ring_offsets``) — notwendig, um zu
    zeigen, dass die richtige ZAHL den Produktionsweg entlangreist, aber nicht
    hinreichend: zwischen Naht und Bild liegt die Zeichenschleife. Hier wird
    deshalb das gerenderte Bild abgetastet und gezaehlt, wie viele leuchtende
    Flaechen auf dem Kranzkreis liegen. Kein Spion, kein Patch — nur
    ``StageCanvas.grab()`` und ``pixelColor``.
    """

    def _bild(self, fixture, groesse=LESBARE_GROESSE):
        """Das GANZE gerenderte Bild (der Kranz ist breiter als ``GLYPH``)."""
        return self._canvas(fixture, groesse).grab().toImage()

    def _kranz(self, fixture, groesse=LESBARE_GROESSE):
        return kranz_messung(self._bild(fixture, groesse), *self.MITTE,
                             groesse * 0.27)

    def test_das_bild_zeigt_neunzehn_leuchtende_segmente(self):
        """★★★ Die Zusage des Items, am Bild gepruefte Fassung: der Ring hat
        genau so viele SICHTBARE Segmente, wie das 3D Segmente bekommt."""
        kontrast, flaechen = self._kranz(self._spiider(_PIXEL))
        self.assertGreaterEqual(
            kontrast, 40,
            "auf dem Kranzkreis ist gar nichts moduliert — es wurde kein Ring "
            "gezeichnet")
        self.assertEqual(flaechen, ERWARTETE_SEGMENTE,
                         "so viele leuchtende Flaechen liegen wirklich auf dem "
                         "Kranz")

    def test_die_gezaehlten_flaechen_sind_die_zahl_der_3d_nutzlast(self):
        """★★ 2D-Bild gegen 3D-Nutzlast, ohne Zwischenhaendler."""
        f = self._spiider(_PIXEL)
        d = _dict_for(f)
        _kontrast, flaechen = self._kranz(f)
        self.assertEqual(flaechen, ring_segmente(d["nHeads"], d["pixelBase"])[1])

    def test_ein_gewoehnlicher_moving_head_kommt_nicht_auf_neunzehn(self):
        """★ Die geforderte Gegenprobe: dieselbe Zaehlung am Wash-Kopf. Seine
        Linse ist auf dem Kranzkreis gleichmaessig hell — keine Flaeche, kein
        Kontrast. Ein Waechter, der auch hier 19 faende, wuerde nichts messen."""
        kontrast, flaechen = self._kranz(self._spiider(_WASH, fid=2))
        self.assertEqual(flaechen, 0)
        self.assertLess(kontrast, 20,
                        "die geschlossene Linse darf nicht moduliert sein")

    def test_ein_drei_zonen_wash_zeigt_genau_drei_flaechen(self):
        """★★ Der Waechter ZAEHLT, er erkennt nicht bloss den Typ: dasselbe
        Verfahren, dasselbe Bild, andere Zahl. Zugleich die Absicherung fuer die
        Geraeteklasse aus der Gegenpruefung (3-Bank-Wash, 88 Modi in der
        Bibliothek des Nutzers) — sie kam bisher in keinem Test vor."""
        f = self._zonen_wash(3)
        self.assertEqual(viz_model_for(f), "pixel_head")
        self.assertEqual(pixel_ring_banks_for(f), (3, 0))
        kontrast, flaechen = self._kranz(f)
        self.assertGreaterEqual(kontrast, 40)
        self.assertEqual(flaechen, 3)

    def test_in_der_vorgabegroesse_bleibt_der_ring_ein_ring(self):
        """★★ Die Groesse, die beim ersten Start steht (30 px). Einzeln zaehlbar
        sind 19 Punkte auf 8 px Radius nicht mehr (gemessen 15 trennbare
        Flaechen) — der Unterschied, auf den es hier ankommt, ist auch ein
        anderer: **moduliertes Leuchten gegen geschlossene Linse.** Genau das
        wird gemessen, und der Moving Head daneben."""
        kontrast, flaechen = self._kranz(self._spiider(_PIXEL),
                                         VORGABE_GROESSE)
        self.assertGreaterEqual(kontrast, 40)
        self.assertGreater(flaechen, 0)
        mh_kontrast, mh_flaechen = self._kranz(self._spiider(_WASH, fid=2),
                                               VORGABE_GROESSE)
        self.assertEqual(mh_flaechen, 0)
        self.assertLess(mh_kontrast, 20)


# ════════════════════════════════════════════════════════════════════════════
# 3. Der echte Weg 2: das Listen-Icon (Patch-Ansicht, Gruppenbaum)
# ════════════════════════════════════════════════════════════════════════════

class ListenIconTest(_LibraryCase):

    def test_der_pixel_kopf_bekommt_sein_eigenes_icon_mit_neunzehn_segmenten(self):
        """★★★ Der echte Weg: ``fixture_icon_for`` ist der Aufruf der
        Listen-Ansichten."""
        zaehler = _RingZaehler(self)
        icon = mini_icons.fixture_icon_for(self._spiider(_PIXEL), 32)
        self.assertFalse(icon.isNull())
        self.assertEqual(zaehler.aufrufe, [ERWARTETE_SEGMENTE])
        self.assertEqual(zaehler.plaetze, [ERWARTETE_SEGMENTE])

    def test_der_moving_head_behaelt_sein_bisheriges_icon_pixelgenau(self):
        """★★ Positivkontrolle mit Bildvergleich: das Icon des Wash-Kopfes ist
        Pixel fuer Pixel das unveraenderte ``fx_moving_head``-Glyph."""
        zaehler = _RingZaehler(self)
        icon = mini_icons.fixture_icon_for(self._spiider(_WASH, fid=2), 32)
        self.assertEqual(zaehler.aufrufe, [])
        self.assertEqual(icon.pixmap(32, 32).toImage(),
                         mini_icons.icon_for_kind("fx_moving_head", 32)
                         .pixmap(32, 32).toImage())

    def test_zwei_verschiedene_pixel_koepfe_teilen_sich_kein_bild(self):
        """★ Die Cache-Falle: der Schluessel war (kind, size). Ohne die
        Segmentzahl darin bekaeme der zweite Pixel-Kopf das Bild des ersten."""
        a = mini_icons.icon_for_kind("fx_pixel_head", 32, 19)
        b = mini_icons.icon_for_kind("fx_pixel_head", 32, 7)
        self.assertNotEqual(a.pixmap(32, 32).toImage(),
                            b.pixmap(32, 32).toImage())
        self.assertIs(a, mini_icons.icon_for_kind("fx_pixel_head", 32, 19),
                      "der Cache muss weiterhin greifen")

    def test_das_pixel_icon_unterscheidet_sich_vom_moving_head(self):
        self.assertNotEqual(
            mini_icons.icon_for_kind("fx_pixel_head", 32, ERWARTETE_SEGMENTE)
            .pixmap(32, 32).toImage(),
            mini_icons.icon_for_kind("fx_moving_head", 32).pixmap(32, 32).toImage())


# ════════════════════════════════════════════════════════════════════════════
# 3b. Dasselbe Icon in der GROESSE, mit der die Produktion ruft (16 px)
# ════════════════════════════════════════════════════════════════════════════

class ListenIconVorgabeTest(_LibraryCase):
    """★★ Der Befund der Gegenpruefung: alle pixelgenauen Vergleiche liefen mit
    ``size=32``, waehrend JEDER Produktionsaufrufer ``fixture_icon_for(f)`` ohne
    Groessenangabe ruft — also mit **16**. Ein Ring, der erst bei 16 px zum
    ununterscheidbaren Fleck verlaeuft, waere dem Waechter nicht aufgefallen.

    Hier wird deshalb genau so gerufen, wie ``patch_view``, ``fixture_group_view``
    und ``live_view`` rufen: ``fixture_icon_for(f)``, ohne zweites Argument.
    Gemessen wird am BILD.
    """

    def _bild(self, fixture):
        icon = mini_icons.fixture_icon_for(fixture)
        bild = icon.pixmap(ICON_VORGABE, ICON_VORGABE).toImage()
        self.assertEqual((bild.width(), bild.height()),
                         (ICON_VORGABE, ICON_VORGABE),
                         "die Vorgabegroesse von fixture_icon_for hat sich "
                         "geaendert — dann misst dieser Test die falsche Groesse")
        return bild

    def test_der_pixel_kopf_zeigt_auch_bei_sechzehn_pixeln_einen_ring(self):
        """★★★ Das Produkt-Urteil: in der Groesse, die der Nutzer wirklich
        sieht, ist die Kopfmitte dunkel und rundherum leuchtet es — der Ring ist
        als Ring erkennbar. Gemessen: Mitte 106, 12 der 24 Kopfpunkte deutlich
        heller (mit nur EINEM gezeichneten Segment waeren es 2)."""
        mitte, anteil = icon_kranz(self._bild(self._spiider(_PIXEL)),
                                   ICON_VORGABE)
        self.assertGreaterEqual(
            anteil, 0.30,
            "im Kopf leuchtet fast nichts — was gezeichnet wurde, ist kein Ring")
        self.assertLess(mitte, 160, "die Kopfmitte muss das dunkle Gehaeuse "
                                    "sein, nicht die Linse")

    def test_der_moving_head_hat_dort_keinen_ring(self):
        """★ Die Gegenprobe mit derselben Messung: beim gewoehnlichen Kopf IST
        die Mitte das Hellste — kein Punkt im Kopf liegt darueber."""
        mitte, anteil = icon_kranz(self._bild(self._spiider(_WASH, fid=2)),
                                   ICON_VORGABE)
        self.assertEqual(anteil, 0.0)
        self.assertGreaterEqual(mitte, 200)

    def test_ein_drei_zonen_wash_zeigt_dort_ebenfalls_seinen_ring(self):
        """Die Geraeteklasse aus der Gegenpruefung, auch im Listen-Icon."""
        mitte, anteil = icon_kranz(self._bild(self._zonen_wash(3)),
                                   ICON_VORGABE)
        self.assertGreaterEqual(anteil, 0.30)
        self.assertLess(mitte, 160)

    def test_die_segmentzahl_erreicht_auch_das_bild_der_vorgabegroesse(self):
        """★★ Dass bei 16 px ueberhaupt noch die ZAHL ankommt und nicht nur
        „irgendein Ring": zwei Geraete mit verschieden vielen Segmenten bekommen
        verschiedene Bilder — beide ueber den echten ``fixture_icon_for``."""
        neunzehn = self._bild(self._spiider(_PIXEL))
        drei = self._bild(self._zonen_wash(3))
        self.assertNotEqual(neunzehn, drei)


# ════════════════════════════════════════════════════════════════════════════
# 4. Die Kranz-Geometrie selbst
# ════════════════════════════════════════════════════════════════════════════

class RingOffsetsTest(unittest.TestCase):

    def test_es_kommen_genau_so_viele_plaetze_wie_segmente(self):
        for n in (1, 2, 3, 7, 19, 20, 64, 99):
            with self.subTest(n=n):
                self.assertEqual(len(mini_icons.ring_offsets(n, 10.0)), n)

    def test_ein_einzelnes_segment_sitzt_in_der_mitte(self):
        """Wie ``wabenPlatz(0)`` im 3D: Segment 0 ist die Mitte."""
        (dx, dy, _r), = mini_icons.ring_offsets(1, 10.0)
        self.assertEqual((dx, dy), (0.0, 0.0))

    def test_die_plaetze_liegen_auf_dem_kranz(self):
        for dx, dy, _r in mini_icons.ring_offsets(19, 10.0):
            self.assertAlmostEqual((dx * dx + dy * dy) ** 0.5, 10.0, places=6)

    def test_dichter_kranz_bekommt_kleinere_punkte(self):
        """Sonst waeren 19 Segmente ein Fleck statt eines Rings."""
        gross = mini_icons.ring_offsets(6, 10.0)[0][2]
        klein = mini_icons.ring_offsets(19, 10.0)[0][2]
        self.assertLess(klein, gross)
        self.assertGreater(klein, 0.0)

    def test_keine_segmente_keine_plaetze(self):
        self.assertEqual(mini_icons.ring_offsets(0, 10.0), [])


if __name__ == "__main__":
    unittest.main()
