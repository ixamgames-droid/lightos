"""CDX-55/56 — der Pixel-Ring rechnet nicht mehr mit Annahmen.

Nachlese zu FM-14 (#634). Zwei Befunde aus dem Codex-Review, beide im selben
Codepfad (``builders.js`` -> ``buildPixelHead``/``updatePixelHeadDmx``):

**CDX-55 — Bank 0 wurde unbedingt verworfen.** FM-14 haengte Ring-Segment ``i``
fest an Kopf ``i+1``, weil Kopf 0 „die Grundfarbe" sei. Fuer die Robe Spiider
stimmt das, belegt war es nicht: die automatische Erkennung prueft nur
``1 Pan + 1 Tilt + >=3 Farb-Baenke``, und ueber den Generator-Override
(``FixtureProfile.viz_model``) wird JEDES Geraet zum Pixel-Kopf. Bei einem
importierten Geraet, dessen Baenke ALLE physische Pixel sind, verschwand Pixel 0
damit aus dem Ring — es blieb nur noch als Geraetefarbe an Linse und Kegel
uebrig. ``app_state.pixel_ring_base_banks`` leitet den Versatz jetzt aus dem
Kanal-Layout ab.

**CDX-56 — bei 64 Segmenten wurde stillschweigend abgeschnitten.** ``nHeads``
und das volle ``heads``-Array reisen unveraendert nach JS; gezeichnet wurden
hoechstens 64 Segmente (2D-Icon unabhaengig davon genauso). Diese Datei misst
die PYTHON-Haelfte der Zusage: die Nutzlast meldet jede Bank. Dass das JS sie
auch alle zeichnet, misst ``test_fm14_pixel_head_scene.py`` in echter
QWebEngine — der Deckel sass dort, und nur dort ist er zu widerlegen.

★ Der schaerfste Fall steht durchgehend daneben: die MITGELIEFERTE Bibliothek.
Der Versatz ist eine neue Ableitung auf einem Bestandspfad — wenn sie irgendwo
anders antwortet als die alte feste 1, aendert ein Bestandsgeraet sein Bild.
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
from src.core.app_state import (                               # noqa: E402
    clear_channel_cache, pixel_ring_base_banks, suggest_viz_model)
from src.core.database.models import (                         # noqa: E402
    FixtureMode, FixtureProfile, PatchedFixture)

_PIXEL = "91-Kanal Pixel RGB (Mode 7)"
_WASH = "27-Kanal Wash (Mode 5)"


def _rgb_baenke(n, *, extra=()):
    """``n`` Farb-Baenke als Kanalliste — je Bank R/G/B plus ``extra``.

    ``extra`` sind zusaetzliche Kanaele JE BANK (z.B. ein eigener Dimmer pro
    Pixel). Sie machen den Abstand zwischen den Baenken groesser, aber nicht
    ungleichmaessig — genau der Fall, an dem sich zeigt, ob die Ableitung an
    einer Kanalzahl haengt oder wirklich am Muster."""
    channels = []
    for i in range(n):
        channels.append((f"P{i} Rot", "color_r", 0, 255))
        channels.append((f"P{i} Gruen", "color_g", 0, 255))
        channels.append((f"P{i} Blau", "color_b", 0, 255))
        for name, attr in extra:
            channels.append((f"P{i} {name}", attr, 0, 255))
    return channels


def _attrs(channels):
    return [c[1] for c in channels]


def _patched(profile_id, mode_name, channel_count, **kw):
    return PatchedFixture(fid=kw.pop("fid", 1), label=kw.pop("label", "Ring"),
                          fixture_profile_id=profile_id, mode_name=mode_name,
                          universe=kw.pop("universe", 1),
                          address=kw.pop("address", 1),
                          channel_count=channel_count,
                          fixture_type=kw.pop("fixture_type", "moving_head"),
                          **kw)


def _universe(values: dict[int, int]):
    class _U:
        def get_channel(self, addr):
            return values.get(addr, 0)
    return _U()


def _dict_for(f):
    """Die echte Nutzlast-Ableitung der Bridge (kein nachgebautes Dict)."""
    from src.ui.visualizer.visualizer_window import VisualizerBridge
    fake_self = SimpleNamespace(_state=SimpleNamespace(
        visualizer_positions={}, visualizer_rotations={}, visualizer_docks={}))
    fake_self._viz_model_for = types.MethodType(
        VisualizerBridge._viz_model_for, fake_self)
    return VisualizerBridge._fixture_to_dict(fake_self, f)


class _LibraryCase(unittest.TestCase):
    """Frisch aus dem Quelltext geseedete Bibliothek (FIXTEST-FRESH)."""

    def setUp(self):
        self._eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)

    def _ids(self, short):
        with Session(self._eng) as s:
            p = s.execute(
                select(FixtureProfile).options(selectinload(FixtureProfile.modes))
                .where(FixtureProfile.short_name == short)).scalars().first()
            self.assertIsNotNone(p, f"Profil {short} fehlt in der Bibliothek")
            return p.id, {m.name: m.channel_count for m in p.modes}

    def _kanal_attrs(self, short, mode_name):
        with Session(self._eng) as s:
            m = s.execute(
                select(FixtureMode).options(selectinload(FixtureMode.channels))
                .join(FixtureProfile)
                .where(FixtureProfile.short_name == short,
                       FixtureMode.name == mode_name)).scalars().one()
            return [(c.attribute or "") for c in
                    sorted(m.channels, key=lambda c: c.channel_number)]

    def _importieren(self, short, channels, *, ftype="moving_head",
                     viz_model=None):
        """Legt ein Profil mit EINEM Modus in der frischen Bibliothek an —
        ueber denselben Helfer, den auch die Builtins und der QXF-Import
        benutzen (``_add_modes``), damit die Kanalnummern echt vergeben werden.
        Liefert ``(profile_id, kanalzahl)``."""
        from src.core.database.fixture_db import _add_modes
        from src.core.database.models import Manufacturer
        with Session(self._eng) as s:
            mfr = s.execute(select(Manufacturer)
                            .where(Manufacturer.name == "TestImport")
                            ).scalars().first()
            if mfr is None:
                mfr = Manufacturer(name="TestImport")
                s.add(mfr)
            p = FixtureProfile(manufacturer=mfr, name=short,
                               short_name=short, fixture_type=ftype,
                               power_w=100, source="import")
            if viz_model:
                p.viz_model = viz_model
            s.add(p)
            _add_modes(s, p, [(f"{len(channels)}-Kanal", channels)])
            s.commit()
            pid = p.id
        clear_channel_cache()
        return pid, len(channels)

    def _alle_modi(self):
        with Session(self._eng) as s:
            profs = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))).scalars().all()
            for p in profs:
                for m in p.modes:
                    yield (p.short_name, m.name, p.fixture_type,
                           [(c.attribute or "") for c in
                            sorted(m.channels, key=lambda c: c.channel_number)])


# ════════════════════════════════════════════════════════════════════════════
# 1. CDX-55: der Versatz wird aus dem Kanal-Layout ABGELEITET
# ════════════════════════════════════════════════════════════════════════════

class VersatzAbleitungTest(_LibraryCase):
    """★ Die Ableitung misst EIN Muster: ein Pixel-Feld ist regelmaessig
    (Bank n+1 liegt immer gleich weit hinter Bank n), eine Grundfarben-Lage ist
    es nicht. Hier steht jeder Fall, den diese Regel unterscheiden koennen muss.
    """

    def test_der_echte_spiider_hat_eine_grundfarben_lage(self):
        """★★ Am ECHTEN Chart gemessen, nicht an einer nachgebauten Liste: die
        Grundfarbe liegt auf Kanal 8, Pixel 1 auf 35, danach geht es in
        Dreierschritten weiter. 27 gegen 3 — die Lage steht ausserhalb des
        Feldes, und genau das muss die Ableitung sehen."""
        attrs = self._kanal_attrs("SPIIDER", _PIXEL)
        stellen = [i for i, a in enumerate(attrs) if a == "color_r"]
        self.assertEqual(stellen[1] - stellen[0], 27, "Grundfarbe -> Pixel 1")
        self.assertEqual(stellen[2] - stellen[1], 3, "Pixel 1 -> Pixel 2")
        self.assertEqual(pixel_ring_base_banks(attrs), 1)

    def test_lauter_pixel_baenke_haben_keinen_versatz(self):
        """★★ Der Fall aus CDX-55: alle Baenke sind physische Pixel. Mit der
        alten festen 1 fiel Pixel 0 aus dem Ring."""
        channels = [("Pan", "pan", 128, 128), ("Tilt", "tilt", 128, 128),
                    ("Dimmer", "intensity", 0, 255)] + _rgb_baenke(5)
        attrs = _attrs(channels)
        self.assertEqual(suggest_viz_model("moving_head", attrs), "pixel_head",
                         "Vorbedingung: dieses Geraet ist ein Pixel-Kopf")
        self.assertEqual(pixel_ring_base_banks(attrs), 0)

    def test_ein_dimmer_je_pixel_ist_kein_grund_fuer_einen_versatz(self):
        """★★ Positivkontrolle in der gefaehrlichen Richtung: ein Waechter, der
        hier anschlaegt, LOESCHT bei jeder RGBD-Pixelleiste das erste Pixel.
        Der Abstand ist 4 statt 3 — aber eben ueberall 4."""
        channels = ([("Pan", "pan", 128, 128), ("Tilt", "tilt", 128, 128)]
                    + _rgb_baenke(6, extra=(("Dimmer", "intensity"),)))
        self.assertEqual(pixel_ring_base_banks(_attrs(channels)), 0)

    def test_auch_rgbw_pixel_haben_keinen_versatz(self):
        channels = ([("Pan", "pan", 128, 128), ("Tilt", "tilt", 128, 128)]
                    + _rgb_baenke(6, extra=(("Weiss", "color_w"),)))
        self.assertEqual(pixel_ring_base_banks(_attrs(channels)), 0)

    def test_eine_grundfarben_lage_mit_eigenen_kanaelen_gibt_versatz_eins(self):
        """Die Gegenrichtung frei nachgebaut: eine Lage mit eigenem Shutter und
        Dimmer vor einem regelmaessigen Pixel-Feld."""
        channels = ([("Pan", "pan", 128, 128), ("Tilt", "tilt", 128, 128),
                     ("Grundfarbe Rot", "color_r", 0, 255),
                     ("Grundfarbe Gruen", "color_g", 0, 255),
                     ("Grundfarbe Blau", "color_b", 0, 255),
                     ("Grundfarbe Shutter", "raw", 32, 32),
                     ("Grundfarbe Dimmer", "raw", 255, 255)]
                    + _rgb_baenke(8))
        self.assertEqual(pixel_ring_base_banks(_attrs(channels)), 1)

    def test_ohne_beleg_gibt_es_keinen_versatz(self):
        """★ Bei weniger als drei Baenken fehlt das zweite Abstands-Paar, es
        gibt also nichts zu vergleichen. Dann lautet die Antwort 0 und nicht 1:
        ein faelschlich ANGENOMMENER Versatz loescht ein Pixel aus dem Bild,
        ein faelschlich verneinter zeigt die Geraetefarbe ein zweites Mal —
        sichtbar, nachvollziehbar, nichts verloren."""
        self.assertEqual(pixel_ring_base_banks(
            ["pan", "tilt", "color_r", "color_g", "color_b"]), 0)
        self.assertEqual(pixel_ring_base_banks(
            ["pan", "tilt", "color_r", "color_g", "color_b",
             "raw", "color_r", "color_g", "color_b"]), 0)
        self.assertEqual(pixel_ring_base_banks([]), 0)

    def test_die_ableitung_haengt_an_den_baenken_nicht_an_den_kanalnummern(self):
        """Fuehrende Nicht-Farbkanaele (Pan/Tilt/Dimmer/Makros) duerfen das
        Ergebnis nicht bewegen — sie liegen VOR der ersten Bank."""
        felder = _rgb_baenke(5)
        ohne = pixel_ring_base_banks(_attrs(felder))
        mit = pixel_ring_base_banks(_attrs(
            [("X", "raw", 0, 0)] * 17 + felder))
        self.assertEqual((ohne, mit), (0, 0))


# ════════════════════════════════════════════════════════════════════════════
# 2. Die mitgelieferte Bibliothek sieht unveraendert aus
# ════════════════════════════════════════════════════════════════════════════

class BibliothekBleibtUnveraendertTest(_LibraryCase):
    """★★ Die Zusage, die diese Aenderung schuldig ist, fuer die GANZE
    Bibliothek — nicht fuer ein Stichprobengeraet. Vorher stand ueberall die
    feste 1; wo die neue Ableitung 0 sagt, aendert sich ein Bild."""

    def test_jeder_pixel_kopf_der_bibliothek_behaelt_den_versatz_eins(self):
        treffer = [(kurz, modus, pixel_ring_base_banks(attrs))
                   for kurz, modus, typ, attrs in self._alle_modi()
                   if suggest_viz_model(typ, attrs) == "pixel_head"]
        self.assertEqual(treffer, [("SPIIDER", _PIXEL, 1)],
                         "genau ein Builtin ist ein Pixel-Kopf, und sein "
                         "Versatz muss der bisherige bleiben")

    def test_die_nutzlast_des_spiiders_meldet_den_versatz(self):
        pid, modi = self._ids("SPIIDER")
        d = _dict_for(_patched(pid, _PIXEL, modi[_PIXEL]))
        self.assertEqual((d["model"], d["nHeads"], d["pixelBase"]),
                         ("pixel_head", 20, 1),
                         "20 Baenke, Versatz 1 -> weiterhin 19 Ring-Segmente")

    def test_bestandsgeraete_melden_keinen_versatz(self):
        """★ Positivkontrolle am Bestand: MH8 (Single-Head), SPIDER14
        (Doppelbar) und ZQ06121 (Panel) sind Show-Geraete. Sie sind keine
        Pixel-Koepfe — das neue Feld darf bei ihnen nichts behaupten."""
        for kurz, ftype, erwartet_model in (
                ("MH8", "moving_head", "moving_head"),
                ("SPIDER14", "moving_head", "spider"),
                ("ZQ06121", "matrix", "matrix")):
            pid, modi = self._ids(kurz)
            name = ("154-Kanal 48 Zonen RGB + 8x Weiss"
                    if kurz == "ZQ06121" else next(iter(modi)))
            d = _dict_for(_patched(pid, name, modi[name], fid=7,
                                   fixture_type=ftype))
            self.assertEqual(d["model"], erwartet_model, kurz)
            self.assertEqual(d["pixelBase"], 0,
                             f"{kurz} ist kein Pixel-Kopf")

    def test_der_wash_modus_desselben_geraets_auch_nicht(self):
        """★ Der schaerfste Positivfall: dasselbe Geraet, eine Farb-Bank."""
        pid, modi = self._ids("SPIIDER")
        d = _dict_for(_patched(pid, _WASH, modi[_WASH], fid=8))
        self.assertEqual((d["model"], d["pixelBase"]), ("moving_head", 0))


# ════════════════════════════════════════════════════════════════════════════
# 3. Der volle Weg fuer ein importiertes Geraet aus lauter Pixel-Baenken
# ════════════════════════════════════════════════════════════════════════════

class ImportiertesGeraetTest(_LibraryCase):
    """★ Nicht an der reinen Funktion gemessen, sondern am ganzen Weg:
    Profil in der Bibliothek -> gepatchtes Geraet -> ``get_channels_for_patched``
    -> ``_fixture_to_dict``. Genau diese Kette hat FM-14 die feste 1 verpasst.
    """

    def test_ein_pixel_kopf_ohne_grundfarben_lage_meldet_versatz_null(self):
        channels = [("Pan", "pan", 128, 128), ("Tilt", "tilt", 128, 128),
                    ("Dimmer", "intensity", 0, 255)] + _rgb_baenke(5)
        pid, n = self._importieren("ARINGALL", channels)
        d = _dict_for(_patched(pid, f"{n}-Kanal", n))
        self.assertEqual(d["model"], "pixel_head")
        self.assertEqual(d["nHeads"], 5)
        self.assertEqual(d["pixelBase"], 0,
                         "alle fuenf Baenke sind Pixel — keine davon darf "
                         "als Grundfarben-Lage verworfen werden")

    def test_pixel_null_liegt_auf_kopf_null_und_geht_damit_verloren(self):
        """★★ Die Messung, die den Befund BELEGT statt ihn zu behaupten: bei
        diesem Geraet traegt Kopf 0 die Kanaele von Pixel 0. Ein Ring, der bei
        Kopf 1 anfaengt, zeigt es nirgends — und der Ring haette nur 4 Zellen
        fuer 5 Pixel."""
        from src.ui.visualizer.visualizer_service import (
            VisualizerService, _build_fixture_payload)
        from src.core.app_state import get_channels_for_patched
        channels = [("Pan", "pan", 128, 128), ("Tilt", "tilt", 128, 128),
                    ("Dimmer", "intensity", 0, 255)] + _rgb_baenke(5)
        pid, n = self._importieren("ARINGALL2", channels)
        f = _patched(pid, f"{n}-Kanal", n, universe=0, address=1)
        state = SimpleNamespace(universes={0: _universe({3: 255, 4: 222})},
                                visualizer_positions={1: (0, 0, 0)},
                                visualizer_rotations={}, visualizer_docks={},
                                output_manager=None,
                                get_patched_fixtures=lambda: [f],
                                subscribe=lambda cb: None)
        svc = VisualizerService(state)
        p = _build_fixture_payload(f, svc._collect_attrs(f),
                                   get_channels_for_patched(f))
        self.assertEqual(len(p["heads"]), 5)
        self.assertEqual(p["heads"][0]["r"], 222, "Kanal 4 ist Pixel 0 Rot")
        self.assertEqual(p["heads"][1]["r"], 0)
        d = _dict_for(f)
        self.assertEqual(d["nHeads"] - d["pixelBase"], 5,
                         "fuenf Pixel brauchen fuenf Ring-Segmente")

    def test_auch_ein_ausdruecklicher_override_bekommt_den_abgeleiteten_versatz(self):
        """★ Der zweite Weg zum Pixel-Kopf: kein Pan/Tilt, dafuer
        ``FixtureProfile.viz_model = 'pixel_head'`` aus dem Generator. Die
        Heuristik haette hier 'par_bar' gesagt — der Versatz muss trotzdem aus
        den Kanaelen kommen und nicht aus dem Modell-Namen."""
        channels = [("Dimmer", "intensity", 0, 255)] + _rgb_baenke(6)
        self.assertEqual(suggest_viz_model("led_bar", _attrs(channels)),
                         "par_bar", "Vorbedingung: nur der Override macht es "
                                    "zum Pixel-Kopf")
        pid, n = self._importieren("ARINGOVR", channels, ftype="led_bar",
                                   viz_model="pixel_head")
        d = _dict_for(_patched(pid, f"{n}-Kanal", n, fixture_type="led_bar"))
        self.assertEqual(d["model"], "pixel_head")
        self.assertEqual((d["nHeads"], d["pixelBase"]), (6, 0))


# ════════════════════════════════════════════════════════════════════════════
# 4. CDX-56: die Nutzlast meldet JEDE Bank — auch weit ueber 64
# ════════════════════════════════════════════════════════════════════════════

class GrosseGeraeteTest(_LibraryCase):
    """★ Die Python-Haelfte der Zusage. Der Deckel sass im JS (``Math.min(64,
    …)`` in ``buildPixelHead`` UND noch einmal in ``addRingCells``), waehrend
    Python unveraendert die volle Zahl schickte — das war der Grund, warum die
    fehlenden Pixel nirgends auffielen. Hier steht die Vorbedingung: die
    Nutzlast kappt nichts. Dass das JS sie alle zeichnet, misst
    ``test_fm14_pixel_head_scene.py``."""

    def _grosses_profil(self, baenke, short):
        channels = ([("Pan", "pan", 128, 128), ("Tilt", "tilt", 128, 128)]
                    + _rgb_baenke(baenke))
        return self._importieren(short, channels)

    def test_hundert_baenke_reisen_vollstaendig_in_die_nutzlast(self):
        pid, n = self._grosses_profil(100, "ARING100")
        d = _dict_for(_patched(pid, f"{n}-Kanal", n))
        self.assertEqual(d["model"], "pixel_head")
        self.assertEqual(d["nHeads"], 100,
                         "die Bank-Zahl wird nicht gekappt")

    def test_und_das_heads_array_dazu(self):
        """★★ Die Zusage ist nicht „die ZAHL reist mit", sondern „die WERTE
        reisen mit": Pixel 80 liegt jenseits des alten 64er-Deckels und muss
        seinen eigenen Wert tragen. Gemessen ueber ein echtes Universum."""
        from src.ui.visualizer.visualizer_service import (
            VisualizerService, _build_fixture_payload)
        from src.core.app_state import get_channels_for_patched
        pid, n = self._grosses_profil(100, "ARING100B")
        f = _patched(pid, f"{n}-Kanal", n, universe=0, address=1)
        # Kanal 3 = Pixel 0 Rot -> Pixel 80 Rot liegt auf 3 + 80*3 = 243.
        state = SimpleNamespace(universes={0: _universe({243: 199})},
                                visualizer_positions={1: (0, 0, 0)},
                                visualizer_rotations={}, visualizer_docks={},
                                output_manager=None,
                                get_patched_fixtures=lambda: [f],
                                subscribe=lambda cb: None)
        svc = VisualizerService(state)
        p = _build_fixture_payload(f, svc._collect_attrs(f),
                                   get_channels_for_patched(f))
        self.assertEqual(len(p["heads"]), 100)
        self.assertEqual(p["heads"][80]["r"], 199)
        self.assertEqual(p["heads"][79]["r"], 0)


if __name__ == "__main__":
    unittest.main()
