"""BUG-FBW Slice 2 — „Alles Weiß" setzt wirklich alle gepatchten Geraete weiss.

Davids Meldung (2026-08-01): „Alles Weiß macht nicht alles weiß." Seine
Entscheidung (2026-08-02) auf die offene Frage: **ja**, der Knopf soll alle
gepatchten Geraete weiss setzen, statt eine gebundene Szene zu starten, die das
Rig von damals kennt.

Vorher: ``ALL_WHITE`` startete nur die gebundene Funktion — ohne Bindung
passierte gar nichts, und eine aeltere Weiss-Szene liess die spaeter
dazugepatchten Geraete dunkel.

Jetzt: ein Moment-Override im Render-Pfad (Schritt 4a³), absolut geschrieben.
Eine gebundene Funktion laeuft weiter mit; die Ueberdeckung fuellt nur die
Luecke, damit ein bewusst eingestellter Weiss-Look erhalten bleibt.

**Gemessen wird am DMX, nicht am Zustand.** Ein Test, der nur
``_all_white_map`` prueft, belegt nicht, dass am Geraet Licht ankommt — genau
diese Sorte Scheinabdeckung ist bei Panik-Funktionen wertlos. Deshalb rendert
der Kern der Tests echte Frames und liest die Universe-Kanaele.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.all_white import white_attrs_for_fixture              # noqa: E402
from src.core.app_state import (get_channels_for_patched,           # noqa: E402
                                get_state, open_value_of_channel)
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import (FixtureProfile,               # noqa: E402
                                      PatchedFixture)
from src.core.engine.scene import Scene                             # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Kanal:
    """Minimal-Kanal fuer die reine Abbildungs-Pruefung."""
    def __init__(self, attribute, ranges=(), highlight_value=None):
        self.attribute = attribute
        self.ranges = list(ranges)
        self.highlight_value = highlight_value


class _Range:
    def __init__(self, von, bis, kind="", name=""):
        self.range_from, self.range_to = von, bis
        self.kind, self.name = kind, name


class AbbildungTest(unittest.TestCase):
    """Was heisst „weiss + voll" fuer EIN Geraet?"""

    def _weiss(self, channels):
        return white_attrs_for_fixture(channels, open_value_of_channel)

    def test_rgbw_par_wird_weiss_und_voll(self):
        attrs = self._weiss([_Kanal("intensity"), _Kanal("color_r"),
                             _Kanal("color_g"), _Kanal("color_b"),
                             _Kanal("color_w")])
        self.assertEqual(attrs.get("intensity"), 255)
        self.assertEqual(attrs.get("color_w"), 255,
                         "bei echtem RGBW traegt der Weiss-Kanal das Weiss")

    def test_reiner_dimmer_bekommt_nur_helligkeit(self):
        self.assertEqual(self._weiss([_Kanal("intensity")]), {"intensity": 255})

    def test_farbrad_bekommt_den_weiss_slot(self):
        rad = _Kanal("color", ranges=[_Range(0, 9, "color", "Weiß"),
                                      _Range(10, 19, "color", "Rot")])
        attrs = self._weiss([_Kanal("intensity"), rad])
        self.assertEqual(attrs.get("color"), 4,
                         "Mittelpunkt des Weiss-Slots (0..9)")

    def test_shutter_nur_mit_beleg(self):
        """Die sicherheitsrelevante Regel: „Shutter" heisst je nach Geraet
        Blende, Strobe oder Betriebsart. Ohne Beleg im Profil wird er NICHT
        angefasst — lieber ein dunkles Geraet als ein blitzendes."""
        ohne = self._weiss([_Kanal("intensity"), _Kanal("shutter")])
        self.assertNotIn("shutter", ohne, "ohne Range-/Highlight-Daten: Finger weg")

        mit = self._weiss([_Kanal("intensity"),
                           _Kanal("shutter", ranges=[_Range(32, 63, "open", "Offen")])])
        self.assertEqual(mit.get("shutter"), 47, "Mittelpunkt des offenen Bands")

        via_highlight = self._weiss([_Kanal("intensity"),
                                     _Kanal("shutter", highlight_value=200)])
        self.assertEqual(via_highlight.get("shutter"), 200)

    def test_geraet_ohne_passende_kanaele_bleibt_leer(self):
        """Dann fasst der Aufrufer es gar nicht erst an."""
        self.assertEqual(self._weiss([_Kanal("pan"), _Kanal("tilt")]), {})


class RenderTest(unittest.TestCase):
    """Am DMX gemessen — kommt das Licht wirklich an?"""

    def setUp(self):
        ensure_builtins()
        reset_show()
        self.state = get_state()
        # Mover: hat intensity UND ein Farbrad — beides muss der Override treffen.
        for fid, addr in ((1, 1), (2, 20), (3, 40)):
            self.state.add_fixture(PatchedFixture(
                fid=fid, label=f"MH{fid}", fixture_profile_id=_pid("MH16"),
                mode_name="16-Kanal", universe=1, address=addr,
                channel_count=16, fixture_type="moving_head"), undoable=False)
        # Dazu eine RGB-Bar, damit auch der echte Farb-Pfad gemessen wird.
        self.state.add_fixture(PatchedFixture(
            fid=4, label="Bar", fixture_profile_id=_pid("PARBAR4"),
            mode_name="12-Kanal 4×RGB", universe=1, address=100,
            channel_count=12, fixture_type="par"), undoable=False)
        self.addCleanup(lambda: self.state.set_all_white(False))
        self.addCleanup(self.state.clear_programmer)

    def _frame(self):
        self.state._render_frame(0.02)
        return self.state.universes[1].get_all()

    def _adressen(self, fid: int, attribute: str) -> list[int]:
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == fid)
        addrs = [fx.address + c.channel_number - 1
                 for c in get_channels_for_patched(fx)
                 if c.attribute == attribute]
        # Ohne diese Zusicherung waere jede all()-Pruefung darunter vakuum-gruen:
        # eine leere Adressliste ist "alle Kanaele stimmen". Genau so entsteht ein
        # Test, der auch ohne den Fix bestanden haette (Fallenklasse CDX-18).
        self.assertTrue(addrs, f"Gerät {fid} hat kein Attribut {attribute!r}")
        return addrs

    def _hell(self, frame, fid) -> bool:
        return all(frame[a - 1] == 255 for a in self._adressen(fid, "intensity"))

    def test_ohne_bindung_werden_alle_geraete_hell(self):
        """Der Fall, in dem der Knopf frueher GAR NICHTS tat."""
        vorher = self._frame()
        self.assertFalse(any(self._hell(vorher, f) for f in (1, 2, 3)),
                         "Vorbedingung: dunkel")
        self.assertEqual(self.state.set_all_white(False), 0)

        self.state.set_all_white(True)
        nachher = self._frame()

        for fid in (1, 2, 3):
            self.assertTrue(self._hell(nachher, fid),
                            f"Gerät {fid} muss hell sein")

    def test_loslassen_nimmt_alles_zurueck(self):
        self.state.set_all_white(True)
        self._frame()
        self.state.set_all_white(False)
        frame = self._frame()

        for fid in (1, 2, 3):
            self.assertFalse(self._hell(frame, fid),
                             f"Gerät {fid} darf nach dem Loslassen nicht scharf bleiben")

    def test_neu_gepatchtes_geraet_ist_beim_naechsten_druck_dabei(self):
        """Genau das war Davids Symptom: die Weiss-Szene kannte das Rig von
        damals. Ein Override, der beim Druck gebaut wird, kann nicht veralten."""
        self.state.add_fixture(PatchedFixture(
            fid=9, label="Neu", fixture_profile_id=_pid("MH16"),
            mode_name="16-Kanal", universe=1, address=200,
            channel_count=16, fixture_type="moving_head"), undoable=False)

        self.state.set_all_white(True)
        self.assertTrue(self._hell(self._frame(), 9))

    def test_gebundene_szene_behaelt_ihre_geraete(self):
        """Die Ueberdeckung fuellt nur die Luecke — ein bewusst eingestellter
        Look bleibt erhalten."""
        gedeckt = self.state.set_all_white(True, exclude_fids={1})
        self.assertEqual(gedeckt, 3, "Gerät 1 gehört der Bindung, 2/3/4 nicht")

        frame = self._frame()
        self.assertFalse(self._hell(frame, 1), "Gerät 1 fasst der Override nicht an")
        self.assertTrue(self._hell(frame, 2))
        self.assertTrue(self._hell(frame, 3))

    def test_farbrad_eines_movers_geht_auf_weiss(self):
        """Ein Mover wird nicht durch Helligkeit weiss, sondern durch sein RAD.

        Bis 2026-08-02 kannte die SCHREIB-Richtung nur ``color``, waehrend die
        Lese-Richtung ``color_wheel`` mitnahm — an genau diesen Geraeten haette
        „Alles Weiß" das Rad gar nicht angefasst: ein rot stehendes Rad waere
        rot geblieben, nur heller. Beide Richtungen teilen sich jetzt eine Liste.
        """
        rad = self._adressen(1, "color_wheel")[0]
        self.state.universes[1].set_channel(rad, 40)      # irgendein Farb-Slot

        self.state.set_all_white(True)
        frame = self._frame()

        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 1)
        kanal = next(c for c in get_channels_for_patched(fx)
                     if c.attribute == "color_wheel")
        weiss_slots = [r for r in (kanal.ranges or [])
                       if "weiß" in (r.name or "").lower()
                       or "white" in (r.name or "").lower()]
        self.assertTrue(weiss_slots, "Vorbedingung: das Profil hat einen Weiss-Slot")
        erwartet = (int(weiss_slots[0].range_from) + int(weiss_slots[0].range_to)) // 2
        self.assertEqual(frame[rad - 1], erwartet,
                         "das Farbrad muss auf dem Weiss-Slot stehen")

    def test_bunte_anfrage_zieht_den_offenen_slot_NICHT_an(self):
        """Gegenprobe zur Farbrad-Regel: der offene Slot ist die WEISS-Position,
        kein Allzweck-Kandidat. Sonst beantwortete „mach rot" an einem Rad ohne
        roten Slot plötzlich mit „kein Filter" — schlechter als das ehrliche
        „kann ich nicht"."""
        from src.core.color_utils import color_attrs_for_fixture
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 1)
        chans = get_channels_for_patched(fx)

        weiss = color_attrs_for_fixture(chans, (255, 255, 255))
        rot = color_attrs_for_fixture(chans, (255, 0, 0))

        self.assertEqual(weiss.get("color_wheel"), 7, "Weiß-Slot 0..15")
        self.assertEqual(rot.get("color_wheel"), 23,
                         "Rot-Slot 16..31 — nicht der offene")

    def test_blackout_schlaegt_alles_weiss(self):
        """Sicherheits-Reihenfolge: der Override liegt VOR der 4b-Stufe, damit
        Grand-Master und Blackout weiter darueber wirken. Ein Panik-Knopf darf
        den Notaus nicht aushebeln."""
        self.state.set_all_white(True)
        self.assertTrue(self._hell(self._frame(), 1), "Vorbedingung: hell")

        self.state.submaster_level = 0.0        # Grand-Master ganz zu
        frame = self._frame()
        self.assertFalse(self._hell(frame, 1),
                         "der Master muss über dem Override liegen")
        self.state.submaster_level = 1.0

    def test_laufender_farb_effekt_wird_ueberschrieben(self):
        """Die eigentliche Schwaeche der alten Loesung: besass eine Funktion die
        Farbkanaele, kam die Weiss-Szene nicht mehr durch (der Programmer-LTP
        laesst funktions-getriebene Nicht-Intensitaets-Kanaele in Ruhe). Der
        Override wird absolut geschrieben, ohne ``protect_addrs``.

        **Der Wert der Szene muss vom Default ABWEICHEN**, sonst zaehlt der Kanal
        gar nicht als funktions-getrieben und der Test bewiese nichts: mit
        ``color_g = 0`` (= Default) blieb er auch dann gruen, wenn der Override
        den Schutz respektierte — genau das hat die Mutations-Gegenprobe gezeigt.
        """
        fm = self.state.function_manager
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 4)
        gruen = [c for c in get_channels_for_patched(fx) if c.attribute == "color_g"]
        self.assertTrue(gruen, "Vorbedingung: das Profil hat Grün")
        gruen_addr = fx.address + gruen[0].channel_number - 1
        default = self.state._default_frame.get(1, [0] * 512)[gruen_addr - 1]

        sc = Scene("Halbgrün")
        for c in gruen:
            sc.set_value(4, c.channel_number, 100)
        self.assertNotEqual(100, default,
                            "der Effektwert muss vom Default abweichen, sonst "
                            "gilt der Kanal nicht als funktions-getrieben")
        fm.add(sc)
        self.addCleanup(lambda: fm.remove(sc.id))
        fm.start(sc.id)

        self.assertEqual(self._frame()[gruen_addr - 1], 100,
                         "Vorbedingung: die Szene treibt den Kanal")

        self.state.set_all_white(True)
        self.assertEqual(self._frame()[gruen_addr - 1], 255,
                         "der Override muss gegen den laufenden Effekt durchkommen")


if __name__ == "__main__":
    unittest.main()
