"""FM-14 — Pixel-/Segment-Steuerung an Moving Heads: Bibliothek, Routing, Nutzlast.

**Der Befund.** Per-Segment-Steuerung EINES Geraets gab es nur auf Bars
(``par_bar``/Pixel-Bar), Doppelbars (``spider``) und flachen Panels (``matrix``).
Ein Moving Head mit LED-Ring — ein Kopf, dessen Lichtquelle in einzeln
ansteuerbare Pixel zerlegt ist — hatte kein Modell: er fiel allein wegen seiner
vielen Farb-Baenke in den Spider-Zweig und stand als zwei kippende Leisten da.

**Das reale Geraet, kanalweise belegt.** Robe *Robin Spiider*: 19 einzeln
ansteuerbare RGBW-Multichips (1x 60 W Mitte, 18x 40 W aussen) auf EINEM
Pan/Tilt-Kopf. Quelle „Robin SPIIDER - DMX protocol" v2.3 (robe.cz) —
Modus 7 „Pixel RGB", 91 Kanaele, davon 35-91 = Rot/Gruen/Blau je Pixel 1..19;
gegengelesen im User Manual Rev. 3.3 (S. 15 „Pixel order"). Nichts an diesem
Chart ist geraten; wo das Geraet etwas hat, das LightOS nicht kennt (zweite
Dimmer-/Shutter-Lage, Blumeneffekt-Farben), steht es als ``raw`` drin, statt
eine Farb-Bank zu erfinden.

Geprueft wird hier der Weg bis zur 3D-Nutzlast, in seiner Reihenfolge:

1. **Die Quelle** — das Profil traegt die 19 Pixel wirklich, an den Kanaelen des
   Charts, und der Blumeneffekt ist KEINE Farb-Bank.
2. **Das Routing** — ``suggest_viz_model`` liefert fuer 1 Pan + 1 Tilt + >=3
   Baenke 'pixel_head'. Mit der vollstaendigen Gegenprobe: kein einziger Modus
   der mitgelieferten Bibliothek aendert dadurch sein Modell.
3. **Der DMX-Weg** — Kopf 0 ist die Grundfarbe des Geraets, Pixel N liegt auf
   Kopf N. Gemessen ueber ``_collect_attrs`` + ``_build_fixture_payload`` an
   einem echten Universum, nicht an einem von Hand gebauten attrs-Dict.
4. **Die Nutzlast** — ``_fixture_to_dict`` schickt Modell und Bank-Zahl mit.
5. **Das Ausricht-Werkzeug** — ein Pixel-Kopf ist ein Moving Head und muss
   echte Pan/Tilt-Kanaele bekommen, keine reine Gehaeuse-Drehung (FM-10).

★ **Positivkontrolle durchgehend am schaerfsten Fall:** DASSELBE Geraet im
27-Kanal-Wash-Modus. Gleiche Mechanik, gleicher Name, nur EINE Farb-Bank — es
muss ein ganz gewoehnlicher Moving Head bleiben.

Was daraus im BILD wird — Ring-Segmente, ihre Lage und ihre eigenen Farben —
misst ``test_fm14_pixel_head_scene.py`` in echter QWebEngine.
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
from src.core.app_state import suggest_viz_model               # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureChannel, FixtureMode, FixtureProfile, PatchedFixture)

_WASH = "27-Kanal Wash (Mode 5)"
_PIXEL = "91-Kanal Pixel RGB (Mode 7)"


def _patched(profile_id, mode_name, channel_count, **kw):
    return PatchedFixture(fid=kw.pop("fid", 1), label=kw.pop("label", "Spiider"),
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


class _LibraryCase(unittest.TestCase):
    """Frisch aus dem Quelltext geseedete Bibliothek (FIXTEST-FRESH) — ein Test
    gegen die Datei im App-Ordner pruefte den Stand vom ersten Lauf."""

    def setUp(self):
        from src.core.app_state import clear_channel_cache
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

    def _kanaele(self, short, mode_name):
        with Session(self._eng) as s:
            m = s.execute(
                select(FixtureMode).options(selectinload(FixtureMode.channels))
                .join(FixtureProfile)
                .where(FixtureProfile.short_name == short,
                       FixtureMode.name == mode_name)).scalars().one()
            return sorted(m.channels, key=lambda c: c.channel_number)


# ════════════════════════════════════════════════════════════════════════════
# 1. Die Quelle: das Geraet steht mit seinem echten Chart in der Bibliothek
# ════════════════════════════════════════════════════════════════════════════

class ProfilTest(_LibraryCase):

    def test_der_pixel_modus_hat_die_kanalzahl_des_charts(self):
        _pid, modi = self._ids("SPIIDER")
        self.assertEqual(modi.get(_PIXEL), 91,
                         "Mode 7 (Pixel RGB) hat laut Chart 91 Kanaele")
        self.assertEqual(modi.get(_WASH), 27,
                         "Mode 5 (Wash) hat laut Chart 27 Kanaele")

    def test_die_neunzehn_pixel_liegen_auf_den_kanaelen_des_charts(self):
        """★ Die Zuordnung, an der alles haengt: Kanal 35/36/37 = Pixel 1 R/G/B,
        Kanal 89/90/91 = Pixel 19. Beide Enden gemessen — eine um eins
        verschobene Kanalliste faellt sonst erst am Rig auf."""
        ch = {c.channel_number: c for c in self._kanaele("SPIIDER", _PIXEL)}
        for nr, attr in ((35, "color_r"), (36, "color_g"), (37, "color_b"),
                         (38, "color_r"),
                         (89, "color_r"), (90, "color_g"), (91, "color_b")):
            self.assertEqual(ch[nr].attribute, attr,
                             f"Kanal {nr} traegt nicht {attr}")
        self.assertEqual(ch[35].name, "P1 Rot")
        self.assertEqual(ch[91].name, "P19 Blau")

    def test_zwanzig_farbbaenke_eine_grundfarbe_plus_neunzehn_pixel(self):
        attrs = [c.attribute for c in self._kanaele("SPIIDER", _PIXEL)]
        self.assertEqual(attrs.count("color_r"), 20,
                         "1 Grundfarbe + 19 Pixel")
        self.assertEqual(attrs.count("pan"), 1, "EIN Kopf, EIN Pan-Motor")
        self.assertEqual(attrs.count("tilt"), 1)

    def test_der_blumeneffekt_ist_keine_farbbank(self):
        """★★ Der Fall, der ein naiv abgeschriebenes Chart entlarvt. Das Geraet
        mischt drei LAGEN uebereinander (Background, Blumeneffekt, Pixel) — die
        Blumeneffekt-Lage hat eigene Rot/Gruen/Blau/Weiss-Kanaele, ist aber
        keine zweite Lampe. Als ``color_r`` gefuehrt waere sie eine 21. Bank und
        haette JEDES Ring-Segment um eins verschoben."""
        for c in self._kanaele("SPIIDER", _PIXEL):
            if c.name.startswith("Blumeneffekt"):
                self.assertEqual(c.attribute, "raw",
                                 f"{c.name!r} darf keine Farb-/Dimmer-Rolle haben")

    def test_master_dimmer_und_master_shutter_sind_die_gesteuerten(self):
        """Zwei Dimmer, zwei Shutter — LightOS kennt je einen. Der MASTER
        bekommt die Rolle (er dunkelt/schliesst alles), die Grundfarben-Lage
        laeuft als raw und steht per Default OFFEN. Andersherum haette der
        Dimmer-Fader nur die Grundfarbe gedimmt, waehrend die Pixel weiterleuchten.
        """
        ch = {c.channel_number: c for c in self._kanaele("SPIIDER", _PIXEL)}
        self.assertEqual(ch[33].attribute, "intensity")     # Master Dimmer
        self.assertEqual(ch[33].default_value, 0)
        self.assertEqual(ch[32].attribute, "shutter")       # Master Shutter
        self.assertEqual(ch[32].default_value, 32, "32 = offen (Chart)")
        self.assertEqual(ch[18].attribute, "raw")           # Grundfarben-Dimmer
        self.assertEqual(ch[18].default_value, 255,
                         "die Grundfarben-Lage muss offen stehen, sonst dimmt "
                         "der Master ins Leere")
        self.assertEqual(ch[17].default_value, 32)          # Grundfarben-Shutter

    def test_der_master_shutter_traegt_die_bereiche_des_charts(self):
        """Ohne ``kind``-Bereiche kann ``visual_intensity`` einen geschlossenen
        Shutter nicht als dunkel erkennen — der 3D-Kegel leuchtete weiter."""
        with Session(self._eng) as s:
            m = s.execute(
                select(FixtureMode)
                .options(selectinload(FixtureMode.channels)
                         .selectinload(FixtureChannel.ranges))
                .join(FixtureProfile)
                .where(FixtureProfile.short_name == "SPIIDER",
                       FixtureMode.name == _PIXEL)).scalars().one()
            ch = {c.channel_number: c for c in m.channels}
            arten = {(r.range_from, r.range_to): r.kind for r in ch[32].ranges}
        self.assertEqual(arten.get((0, 31)), "closed")
        self.assertEqual(arten.get((32, 63)), "open")
        self.assertEqual(arten.get((64, 95)), "strobe")


# ════════════════════════════════════════════════════════════════════════════
# 2. Das Routing: wann ist ein Geraet ein Pixel-Kopf?
# ════════════════════════════════════════════════════════════════════════════

class RoutingTest(unittest.TestCase):
    """Reine Heuristik (ohne DB) — dieselben Regeln wie ``viz_model_for``."""

    def test_ein_pan_ein_tilt_und_viele_baenke_ist_ein_pixel_kopf(self):
        attrs = ["pan", "tilt", "color_r", "color_g", "color_b"]
        attrs += ["color_r", "color_g", "color_b"] * 19
        self.assertEqual(suggest_viz_model("moving_head", attrs), "pixel_head")

    def test_die_grenze_liegt_bei_drei_baenken(self):
        """★ Die Entscheidung, die diese Regel gefaehrlich machen koennte:
        ZWEI Baenke sind die Signatur der Doppelbar — auch beim Einzelkopf-
        Spider ('Speider 14ch': 1 Pan, 1 Tilt, 2 Baenke), den
        ``is_spider_fixture`` ausdruecklich als Spider fuehrt. Er darf nicht
        stillschweigend das Modell wechseln."""
        zwei = ["pan", "tilt", "color_r", "color_g", "color_b",
                "color_r", "color_g", "color_b"]
        self.assertEqual(suggest_viz_model("moving_head", zwei), "spider")
        self.assertEqual(suggest_viz_model("moving_head", zwei + ["color_r"]),
                         "pixel_head", "ab der dritten Bank ist es ein Pixel-Kopf")

    def test_mehrere_pan_motoren_bleiben_eine_mover_bar(self):
        """Vier Koepfe mit je eigenem Pan sind eine Bar, kein Ring — auch bei
        vielen Baenken. Die Reihenfolge der Regeln entscheidet das."""
        attrs = (["pan", "tilt", "color_r"] * 4)
        self.assertEqual(suggest_viz_model("moving_head", attrs), "mover_bar")

    def test_ohne_bewegung_bleibt_es_eine_par_bar(self):
        attrs = ["color_r", "color_g", "color_b"] * 8
        self.assertEqual(suggest_viz_model("led_bar", attrs), "par_bar")

    def test_ein_gewoehnlicher_moving_head_bleibt_ohne_modell(self):
        """★ Positivkontrolle: EINE Bank -> ``None`` -> der Aufrufer nimmt den
        fixture_type. Genau der Weg von MH8/MH16."""
        attrs = ["pan", "pan_fine", "tilt", "tilt_fine", "intensity",
                 "color_r", "color_g", "color_b", "color_w"]
        self.assertIsNone(suggest_viz_model("moving_head", attrs))

    def test_ein_laser_bleibt_ein_laser(self):
        attrs = ["pan", "tilt"] + ["color_r"] * 4
        self.assertIsNone(suggest_viz_model("laser", attrs))


class BibliothekBleibtUnveraendertTest(_LibraryCase):
    """★★ Die Zusage, die eine neue Routing-Regel schuldig ist, und zwar fuer
    die GANZE Bibliothek: kein Bestandsgeraet darf sein 3D-Modell wechseln.

    Gemessen wird jeder Modus jedes mitgelieferten Profils — nicht ein
    Stichprobengeraet. Genau daran ist QA-58 im ersten Anlauf gescheitert: der
    Waechter fuhr EIN Segment, versprochen war ein voller Lauf."""

    def _alle_modi(self):
        with Session(self._eng) as s:
            profs = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))).scalars().all()
            for p in profs:
                for m in p.modes:
                    yield (p.short_name, m.name, p.fixture_type,
                           [(c.attribute or "") for c in m.channels])

    def test_genau_ein_modus_der_bibliothek_ist_ein_pixel_kopf(self):
        treffer = [(kurz, modus)
                   for kurz, modus, typ, attrs in self._alle_modi()
                   if suggest_viz_model(typ, attrs) == "pixel_head"]
        self.assertEqual(treffer, [("SPIIDER", _PIXEL)],
                         "die neue Regel darf NUR den neu aufgenommenen "
                         "Pixel-Modus treffen")

    def test_kein_bestandsmodus_erfuellt_die_vorbedingung_der_neuen_regel(self):
        """Schaerfer als der Test darueber: er misst die BEDINGUNG, nicht das
        Ergebnis. Haette die Regel eine andere Grenze (>=2 statt >=3 Baenke),
        faellt hier auf, welche Geraete sie erwischt haette."""
        gefaehrdet = [
            (kurz, modus, attrs.count("color_r"))
            for kurz, modus, _typ, attrs in self._alle_modi()
            if kurz != "SPIIDER" and attrs.count("pan") == 1
            and attrs.count("tilt") == 1 and attrs.count("color_r") >= 2]
        self.assertEqual(gefaehrdet, [],
                         "ein Bestandsgeraet mit 1 Pan + 1 Tilt + >=2 Baenken "
                         "waere der Grenzfall dieser Regel")

    def test_derselbe_spiider_im_wash_modus_ist_ein_normaler_moving_head(self):
        """★ Die Positivkontrolle am schaerfsten Fall: dasselbe Geraet, dieselbe
        Mechanik, nur der andere Modus. Wer das Modell am Geraetenamen statt an
        den Kanaelen festmacht, baut hier auch einen Ring."""
        for kurz, modus, typ, attrs in self._alle_modi():
            if kurz == "SPIIDER" and modus == _WASH:
                self.assertEqual(attrs.count("color_r"), 1)
                self.assertIsNone(suggest_viz_model(typ, attrs))
                return
        self.fail("Wash-Modus nicht gefunden")


class NachruestenTest(_LibraryCase):
    """★ Die Zeile, die das Geraet auf BESTEHENDE Installationen bringt.

    ``_seed`` laeuft nur bei einer leeren Datenbank — auf jedem Rechner, der
    LightOS schon benutzt hat, kommt ein neues Builtin ausschliesslich ueber
    ``ensure_builtins()``. Ohne diesen Test bliebe genau die Eintragszeile
    ungemessen: die ganze Datei waere gruen geblieben, waehrend das Geraet bei
    Robin nie auftaucht (nachgemessen — die Mutation „Zeile entfernt" lief
    29/29 gruen, bevor es diesen Test gab)."""

    def test_ein_bestehender_bestand_bekommt_den_pixel_kopf_nachgereicht(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.app_state import clear_channel_cache

        # Ausgangslage wie auf einem Rechner, der das Geraet noch nicht kennt.
        with Session(self._eng) as s:
            p = s.execute(select(FixtureProfile)
                          .where(FixtureProfile.short_name == "SPIIDER")
                          ).scalars().one()
            s.delete(p)
            s.commit()
        clear_channel_cache()
        with Session(self._eng) as s:
            self.assertIsNone(
                s.execute(select(FixtureProfile)
                          .where(FixtureProfile.short_name == "SPIIDER")
                          ).scalars().first(),
                "Vorbedingung: das Profil ist weg")

        ensure_builtins()

        with Session(self._eng) as s:
            p = s.execute(
                select(FixtureProfile).options(selectinload(FixtureProfile.modes))
                .where(FixtureProfile.short_name == "SPIIDER")).scalars().first()
            self.assertIsNotNone(p, "ensure_builtins reicht das Profil nicht nach")
            self.assertEqual(sorted(m.channel_count for m in p.modes), [27, 91])

    def test_ein_zweiter_lauf_legt_es_nicht_doppelt_an(self):
        """``ensure_builtins`` laeuft bei JEDEM Start — ein zweites Profil
        gleichen Namens waere ein Duplikat in der Geraeteliste."""
        from src.core.database.fixture_db import ensure_builtins
        ensure_builtins()
        ensure_builtins()
        with Session(self._eng) as s:
            treffer = s.execute(select(FixtureProfile)
                                .where(FixtureProfile.short_name == "SPIIDER")
                                ).scalars().all()
        self.assertEqual(len(treffer), 1)


class GeneratorAuswahlTest(unittest.TestCase):
    """★ Das Modell muss auch von HAND waehlbar sein (FM-12-Override): ein
    importiertes QLC+-Profil bringt keine Heuristik mit, die man nachbessern
    koennte, wenn die Auswahl fehlt.

    Gemessen an der echten Combo des Generators, nicht an der Konstante — die
    Liste zu pruefen haette nur belegt, dass die Liste eine Liste ist."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_der_pixel_kopf_ist_im_generator_waehlbar(self):
        from src.ui.widgets.fixture_generator import (
            FixtureGeneratorDialog, GeneratorModel, GenMode, GenChannel)
        model = GeneratorModel(
            manufacturer="TestMfr", model="ATest Ring", short_name="ATESTRING",
            fixture_type="moving_head",
            modes=[GenMode("5ch", [GenChannel("Pan", "pan"),
                                   GenChannel("Tilt", "tilt"),
                                   GenChannel("Rot", "color_r"),
                                   GenChannel("Gruen", "color_g"),
                                   GenChannel("Blau", "color_b")])])
        dlg = FixtureGeneratorDialog(model=model)
        self.addCleanup(dlg.deleteLater)
        idx = dlg._cb_vizmodel.findData("pixel_head")
        self.assertGreaterEqual(idx, 0, "das Modell fehlt in der Auswahl")
        dlg._cb_vizmodel.setCurrentIndex(idx)
        dlg._sync_all()
        self.assertEqual(dlg._model.to_payload()["viz_model"], "pixel_head",
                         "die Wahl kommt nicht im gespeicherten Profil an")


# ════════════════════════════════════════════════════════════════════════════
# 3. Der DMX-Weg: Kopf 0 ist die Grundfarbe, Pixel N liegt auf Kopf N
# ════════════════════════════════════════════════════════════════════════════

class KopfZuordnungTest(_LibraryCase):
    """★ Die Behauptung, auf der der ganze Ring steht. Sie wird hier NICHT
    angenommen, sondern ueber den echten Weg gemessen: echte Kanaele aus der
    Bibliothek, echtes Universum, ``_collect_attrs`` (die attr#N-Vergabe) und
    ``_build_fixture_payload`` (der Kopf-Bau)."""

    def _payload(self, werte: dict[int, int]):
        from src.ui.visualizer.visualizer_service import (
            VisualizerService, _build_fixture_payload)
        from src.core.app_state import get_channels_for_patched
        pid, modi = self._ids("SPIIDER")
        f = _patched(pid, _PIXEL, modi[_PIXEL], universe=0, address=1)
        state = SimpleNamespace(universes={0: _universe(werte)},
                                visualizer_positions={1: (0, 0, 0)},
                                visualizer_rotations={}, visualizer_docks={},
                                output_manager=None,
                                get_patched_fixtures=lambda: [f],
                                subscribe=lambda cb: None)
        svc = VisualizerService(state)
        attrs = svc._collect_attrs(f)
        return _build_fixture_payload(f, attrs, get_channels_for_patched(f))

    def test_zwanzig_koepfe_grundfarbe_plus_neunzehn_pixel(self):
        p = self._payload({33: 255})
        self.assertEqual(len(p["heads"]), 20)

    def test_pixel_drei_landet_auf_kopf_drei(self):
        """Kanalbild: 35/36/37 = Pixel 1, also 41/42/43 = Pixel 3 (Rot 41)."""
        p = self._payload({33: 255, 42: 200})       # Pixel 3 GRUEN
        heads = p["heads"]
        self.assertEqual(heads[3]["g"], 200, "Pixel 3 muss auf Kopf 3 liegen")
        for j in (0, 1, 2, 4, 19):
            self.assertEqual(heads[j]["g"], 0,
                             f"Kopf {j} darf keinen fremden Pixelwert zeigen")

    def test_das_letzte_pixel_geht_nicht_verloren(self):
        """★ Off-by-one am oberen Ende: Kanal 89-91 ist Pixel 19 = Kopf 19."""
        p = self._payload({33: 255, 89: 210})
        self.assertEqual(p["heads"][19]["r"], 210)

    def test_kopf_null_ist_die_grundfarbe_und_nicht_pixel_eins(self):
        """★★ Der Fall, der eine um eins verschobene Ring-Zuordnung entlarvt.
        Kanal 8 ist die GRUNDFARBE Rot (Background), Kanal 35 ist Pixel 1 Rot.
        Hier leuchtet nur die Grundfarbe: Kopf 0 traegt sie, Kopf 1 (Pixel 1)
        muss dunkel bleiben. Wer die Baenke um eins verschiebt, faerbt hier das
        erste Ring-Segment."""
        p = self._payload({33: 255, 8: 255})
        self.assertEqual(p["heads"][0]["r"], 255)
        self.assertEqual(p["heads"][1]["r"], 0,
                         "Pixel 1 hat eigene Kanaele und ist hier aus")
        self.assertEqual(p["r"], 255,
                         "die Geraetefarbe (Kegel/Linse) kommt aus der Grundfarbe")

    def test_und_umgekehrt_faerbt_pixel_eins_nicht_das_ganze_geraet(self):
        """Die Gegenrichtung: nur Pixel 1 an. Die Geraetefarbe bleibt schwarz —
        sonst waere der Kegel ein zweites Bild desselben Pixels."""
        p = self._payload({33: 255, 35: 255})
        self.assertEqual(p["heads"][1]["r"], 255)
        self.assertEqual(p["heads"][0]["r"], 0)
        self.assertEqual(p["r"], 0)


# ════════════════════════════════════════════════════════════════════════════
# 4. Die Nutzlast an das 3D
# ════════════════════════════════════════════════════════════════════════════

def _dict_for(f):
    from src.ui.visualizer.visualizer_window import VisualizerBridge
    fake_self = SimpleNamespace(_state=SimpleNamespace(
        visualizer_positions={}, visualizer_rotations={}, visualizer_docks={}))
    fake_self._viz_model_for = types.MethodType(
        VisualizerBridge._viz_model_for, fake_self)
    return VisualizerBridge._fixture_to_dict(fake_self, f)


class NutzlastTest(_LibraryCase):

    def test_der_pixel_modus_schickt_modell_und_bankzahl(self):
        pid, modi = self._ids("SPIIDER")
        d = _dict_for(_patched(pid, _PIXEL, modi[_PIXEL]))
        self.assertEqual(d["model"], "pixel_head")
        self.assertEqual(d["nHeads"], 20,
                         "ohne die Bank-Zahl baut der Renderer genau EIN Segment")

    def test_der_pixel_kopf_meldet_kein_weissband(self):
        """★ Das Weissband (VIZ-50b) ist eine Aussage ueber PANELS. Der Spiider
        hat EINEN Weiss-Kanal auf 20 Baenken und erfuellt damit die Bedingung
        ``0 < weiss < baenke`` — ohne die Modell-Einschraenkung haette er ein
        Band gemeldet, das es nicht gibt."""
        pid, modi = self._ids("SPIIDER")
        d = _dict_for(_patched(pid, _PIXEL, modi[_PIXEL]))
        self.assertEqual(d["nWhites"], 0)

    def test_der_wash_modus_bleibt_ein_moving_head(self):
        """★ Positivkontrolle: dasselbe Geraet ohne Pixel-Kanaele."""
        pid, modi = self._ids("SPIIDER")
        d = _dict_for(_patched(pid, _WASH, modi[_WASH], fid=2))
        self.assertEqual(d["model"], "moving_head")
        self.assertEqual(d["nHeads"], 0,
                         "ein Single-Head bekommt keine Kopfzahl")

    def test_ein_bestandsgeraet_schickt_dieselbe_nutzlast_wie_bisher(self):
        """★★ Positivkontrolle am Bestand: MH8 ist ein Show-Geraet. Modell,
        Kopfzahl, Weissband — nichts davon darf sich bewegt haben."""
        pid, modi = self._ids("MH8")
        name = next(iter(modi))
        d = _dict_for(_patched(pid, name, modi[name], fid=3))
        self.assertEqual(d["model"], "moving_head")
        self.assertEqual((d["nHeads"], d["nWhites"]), (0, 0))

    def test_ein_panel_behaelt_sein_weissband(self):
        """★★ Die Kehrseite der Modell-Einschraenkung: das Band, das VIZ-50b
        gebaut hat, muss weiterhin gemeldet werden."""
        pid, modi = self._ids("ZQ06121")
        name = "154-Kanal 48 Zonen RGB + 8x Weiss"
        d = _dict_for(_patched(pid, name, modi[name], fid=4,
                               fixture_type="matrix"))
        self.assertEqual((d["model"], d["nHeads"], d["nWhites"]),
                         ("matrix", 48, 8))


# ════════════════════════════════════════════════════════════════════════════
# 5. Das Ausricht-Werkzeug: ein Pixel-Kopf ist ein Moving Head
# ════════════════════════════════════════════════════════════════════════════

class AusrichtenTest(_LibraryCase):
    """★ FM-10-Klasse: ein Geraet, das der Aim-Zweig nicht als Moving Head
    erkennt, landet im statischen Zweig — dort wird nur das Gehaeuse im 3D
    gedreht, waehrend am echten Geraet gar nichts passiert. Der Pixel-Kopf
    faellt wegen seiner Baenke unter ``is_spider_fixture`` und waere genau
    dort gelandet."""

    def _ist_mh(self, f):
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        return VisualizerBridge._is_moving_head(SimpleNamespace(), f)

    def test_ein_pixel_kopf_wird_ausgerichtet(self):
        pid, modi = self._ids("SPIIDER")
        self.assertTrue(self._ist_mh(_patched(pid, _PIXEL, modi[_PIXEL])))

    def test_derselbe_spiider_im_wash_modus_auch(self):
        pid, modi = self._ids("SPIIDER")
        self.assertTrue(self._ist_mh(_patched(pid, _WASH, modi[_WASH], fid=2)))

    def test_ein_gewoehnlicher_moving_head_weiterhin(self):
        pid, modi = self._ids("MH8")
        name = next(iter(modi))
        self.assertTrue(self._ist_mh(_patched(pid, name, modi[name], fid=3)))

    def test_ein_spider_weiterhin_nicht(self):
        """★ Positivkontrolle: der Doppelbar-Spider kippt nur, ihn auf einen
        Punkt zu zielen ergibt keinen Sinn — das war der Grund fuer die
        Spider-Ausnahme und bleibt so."""
        pid, modi = self._ids("SPIDER14")
        name = next(iter(modi))
        self.assertFalse(self._ist_mh(_patched(pid, name, modi[name], fid=4)))


if __name__ == "__main__":
    unittest.main()
