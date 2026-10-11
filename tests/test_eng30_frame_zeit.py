"""ENG-30: Engine-Zeit je DMX-Frame — die zwei teuersten Stellen gesenkt.

Gemessen an der Bühnen-Show 2026 (80 Geräte): ein Look kostete 8–10 ms je
Frame bei 22,7 ms Budget. Zwei Stellen trugen den Großteil:

1. **Gerät zu einer fid suchen.** Szenen, Matrizen, EFX und gemappte Kanäle
   liefen je Wert/Zelle durch die ganze Patch-Liste (rund 450 Durchläufe je
   Frame, jeder Vergleich ein Attributzugriff auf ein Datenbank-Objekt).
   Jetzt reicht der ``FunctionManager`` eine Liste mit Tabelle ``fid -> Gerät``
   herein (``PatchListe``).
2. **Adresslisten je Gerät.** ``_render_frame`` leitete in JEDEM Frame für
   jedes Gerät ab, welche Adressen Intensität, Dimmer und Farbe sind — reine
   Patch-Information. Sie steht jetzt im Render-Plan.

Abgesichert ist hier vor allem, dass sich am ERGEBNIS nichts ändert: dieselbe
Antwort wie die Suche (auch bei doppelter fid), dieselbe Ausgabe mit und ohne
Plan, und der alte Weg überall dort, wo Tabelle oder Plan nicht passen.
Zeiten prüft der Test nicht (der Rechner ist nie leer) — er zählt Zugriffe.
"""
from __future__ import annotations

import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A                                      # noqa: E402
from src.core.app_state import AppState                             # noqa: E402
from src.core.dmx.universe import Universe                          # noqa: E402
from src.core.engine import efx, mapped_channel, rgb_matrix, scene  # noqa: E402
from src.core.engine.function_manager import FunctionManager        # noqa: E402
from src.core.engine.patch_index import PatchListe                  # noqa: E402
from src.core.engine.scene import Scene                             # noqa: E402

_SUCHEN = (scene._find_fixture, efx._find_fixture,
           rgb_matrix._find_fixture, mapped_channel._find_fixture)


class _Geraet:
    """Gerät, das mitzählt, wie oft seine fid gelesen wird."""
    gelesen = 0
    channel_count = 8
    protocol = ""
    fixture_type = ""
    label = ""

    def __init__(self, fid, universe=1, address=1):
        self._fid = fid
        self.universe = universe
        self.address = address

    @property
    def fid(self):
        type(self).gelesen += 1
        return self._fid


def _rig(anzahl=40):
    return [_Geraet(i + 1, 1, 1 + i * 8) for i in range(anzahl)]


class PatchListeTest(unittest.TestCase):

    def test_findet_wie_die_suche(self):
        rig = _rig(10)
        liste = PatchListe(rig)
        for fid in (1, 5, 10):
            self.assertIs(liste.finde(fid), rig[fid - 1])
        self.assertIsNone(liste.finde(11))
        self.assertIsNone(liste.finde("5"))             # Text ist keine Zahl
        self.assertEqual(list(liste), rig)              # bleibt eine Liste
        self.assertIsInstance(liste, list)

    def test_bei_doppelter_fid_gewinnt_das_erste(self):
        a, b = _Geraet(7), _Geraet(7)
        for suche in _SUCHEN:
            self.assertIs(suche([a, b], 7), a)
            self.assertIs(suche(PatchListe([a, b]), 7), a)

    def test_alle_vier_suchen_antworten_gleich(self):
        rig = _rig(12)
        liste = PatchListe(rig)
        for suche in _SUCHEN:
            for fid in (1, 6, 12, 13, 0, -1, None):
                self.assertIs(suche(liste, fid), suche(rig, fid), (suche.__module__, fid))

    def test_tabelle_statt_durchlauf(self):
        rig = _rig(40)
        liste = PatchListe(rig)
        _Geraet.gelesen = 0
        for suche in _SUCHEN:
            for fid in range(1, 41):
                suche(liste, fid)
        self.assertEqual(_Geraet.gelesen, 0)
        # Gegenprobe: die gewöhnliche Liste wird durchlaufen.
        scene._find_fixture(rig, 40)
        self.assertEqual(_Geraet.gelesen, 40)

    def test_leere_und_fehlende_liste(self):
        self.assertIsNone(PatchListe().finde(1))
        self.assertIsNone(PatchListe(None).finde(1))
        self.assertEqual(len(PatchListe(None)), 0)

    def test_nicht_hashbare_fid_faellt_auf_die_suche_zurueck(self):
        komisch = types.SimpleNamespace(fid=[1, 2])
        normal = types.SimpleNamespace(fid=3)
        liste = PatchListe([komisch, normal])
        self.assertIs(liste.finde(3), normal)
        self.assertIs(liste.finde([1, 2]), komisch)
        self.assertIsNone(liste.finde([9]))
        # nicht hashbare FRAGE an eine gewöhnliche Tabelle
        self.assertIsNone(PatchListe([normal]).finde([3]))

    def test_nachtraeglich_verlaengert_findet_das_neue(self):
        rig = _rig(3)
        liste = PatchListe(rig)
        neu = _Geraet(99)
        liste.append(neu)
        self.assertIs(liste.finde(99), neu)

    def test_passt_zu(self):
        rig = _rig(4)
        liste = PatchListe(rig)
        self.assertTrue(liste.passt_zu(rig))
        self.assertFalse(liste.passt_zu(list(rig)))         # andere Liste
        rig[0] = _Geraet(50)                                # gleicher Platz, anderes Gerät
        self.assertFalse(liste.passt_zu(rig))
        rig2 = _rig(4)
        liste2 = PatchListe(rig2)
        rig2.append(_Geraet(60))
        self.assertFalse(liste2.passt_zu(rig2))

    def test_passt_zu_liest_keine_attribute(self):
        rig = _rig(40)
        liste = PatchListe(rig)
        _Geraet.gelesen = 0
        for _ in range(10):
            self.assertTrue(liste.passt_zu(rig))
        self.assertEqual(_Geraet.gelesen, 0)


class _Merker:
    """Funktion, die festhält, womit ``write`` gerufen wurde."""
    is_running = True
    intensity = 1.0
    priority = 0

    def __init__(self):
        self.gesehen = []

    def write(self, universes, patch_cache, dt, registry=None):
        self.gesehen.append(patch_cache)


def _manager_mit(funktion, fid=1):
    fm = FunctionManager()
    fm._functions[fid] = funktion
    fm._running_ids.add(fid)
    fm._start_order.append(fid)
    return fm


class FunctionManagerTest(unittest.TestCase):

    def test_funktionen_bekommen_die_liste_mit_tabelle(self):
        rig = _rig(5)
        m = _Merker()
        fm = _manager_mit(m)
        fm.tick({1: Universe(1)}, rig, 0.02)
        self.assertIs(type(m.gesehen[0]), PatchListe)
        self.assertEqual(list(m.gesehen[0]), rig)

    def test_tabelle_wird_nur_bei_aenderung_neu_gebaut(self):
        rig = _rig(5)
        m = _Merker()
        fm = _manager_mit(m)
        uni = {1: Universe(1)}
        for _ in range(5):
            fm.tick(uni, rig, 0.02)
        self.assertEqual(len({id(g) for g in m.gesehen}), 1)
        _Geraet.gelesen = 0
        for _ in range(5):
            fm.tick(uni, rig, 0.02)
        self.assertEqual(_Geraet.gelesen, 0, "unveränderte Liste neu durchlaufen")

    def test_neue_liste_neue_tabelle(self):
        rig = _rig(5)
        m = _Merker()
        fm = _manager_mit(m)
        uni = {1: Universe(1)}
        fm.tick(uni, rig, 0.02)
        anderes = _rig(5)                       # so tauscht AppState den Patch
        fm.tick(uni, anderes, 0.02)
        self.assertIsNot(m.gesehen[0], m.gesehen[1])
        self.assertIs(m.gesehen[1].finde(1), anderes[0])

    def test_dieselbe_liste_mit_anderem_inhalt_neue_tabelle(self):
        """Wer die Liste an Ort und Stelle ändert (Tests, Werkzeuge), bekommt
        trotzdem die richtige Antwort."""
        rig = _rig(5)
        m = _Merker()
        fm = _manager_mit(m)
        uni = {1: Universe(1)}
        fm.tick(uni, rig, 0.02)
        ersatz = _Geraet(1, 1, 300)
        rig[0] = ersatz
        fm.tick(uni, rig, 0.02)
        self.assertIs(m.gesehen[-1].finde(1), ersatz)
        rig.append(_Geraet(77))
        fm.tick(uni, rig, 0.02)
        self.assertIsNotNone(m.gesehen[-1].finde(77))

    def test_was_keine_gewoehnliche_liste_ist_geht_unveraendert_durch(self):
        m = _Merker()
        fm = _manager_mit(m)
        uni = {1: Universe(1)}
        for wert in (None, (), tuple(_rig(2))):
            fm.tick(uni, wert, 0.02)
            self.assertIs(m.gesehen[-1], wert)
        fertig = PatchListe(_rig(2))
        fm.tick(uni, fertig, 0.02)
        self.assertIs(m.gesehen[-1], fertig)

    def test_dim_map_bleibt_an_die_urspruengliche_liste_gebunden(self):
        """Der Zwischenspeicher für die Per-Effekt-Intensität hängt an der
        Identität der hereingegebenen Liste. Bekäme er die (neue) Liste mit
        Tabelle, würde er zwar auch treffen — aber nur, solange niemand je Frame
        eine frische baut. Deshalb bleibt er an der Quelle."""
        rig = _rig(3)
        m = _Merker()
        m.intensity = 0.5
        fm = _manager_mit(m)
        gerufen = []
        echt = fm._dim_addr_map
        fm._dim_addr_map = lambda pc: (gerufen.append(pc), echt(pc))[1]
        alt = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: []
        self.addCleanup(setattr, A, "get_channels_for_patched", alt)
        uni = {1: Universe(1)}
        for _ in range(3):
            fm.tick(uni, rig, 0.02)
        self.assertTrue(gerufen)
        self.assertTrue(all(pc is rig for pc in gerufen))

    def test_szene_ueber_den_manager_liest_keine_fids_mehr(self):
        """Der eigentliche Gewinn, als Zählung: eine Szene mit 120 Werten auf
        40 Geräten, 10 Frames. Vorher 120 Durchläufe je Frame."""
        rig = _rig(40)
        sz = Scene(name="S")
        for g in rig:
            for kanal in (1, 2, 3):
                sz.set_value(g._fid, kanal, 100 + kanal)
        fm = FunctionManager()
        fm.add(sz)
        fm.start(sz.id)
        uni = {1: Universe(1)}
        fm.tick(uni, rig, 0.02)                 # baut die Tabelle
        _Geraet.gelesen = 0
        for _ in range(10):
            fm.tick(uni, rig, 0.02)
        self.assertEqual(_Geraet.gelesen, 0)
        self.assertEqual(uni[1].get_channel(1), 101)
        self.assertEqual(uni[1].get_channel(8 * 39 + 3), 103)

    def test_szene_schreibt_mit_tabelle_dasselbe_wie_ohne(self):
        rig = _rig(20)
        rig.append(_Geraet(5, 1, 400))          # doppelte fid: das erste gewinnt
        werte = [(g._fid, k, (g._fid * 7 + k * 13) % 256) for g in rig[:20] for k in (1, 4, 8)]
        werte += [(999, 1, 200), (3, 9, 200)]   # unbekanntes Gerät; Kanal über dem Ende (ENG-20)
        ergebnis = []
        for patch in (rig, PatchListe(rig)):
            sz = Scene(name="S")
            for fid, kanal, wert in werte:
                sz.set_value(fid, kanal, wert)
            sz.start()
            uni = {1: Universe(1)}
            for _ in range(3):
                sz.write(uni, patch, 0.02)
            ergebnis.append(bytes(uni[1].get_all()))
        self.assertEqual(ergebnis[0], ergebnis[1])
        self.assertTrue(any(ergebnis[0]))


# ── Render-Plan ───────────────────────────────────────────────────────────

class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 6
    protocol = ""
    fixture_type = ""
    label = ""

    def __init__(self, fid, universe, address, art="rgb"):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.art = art


_KANAELE = {
    # Dimmer + RGB + Pan + Cyan (subtraktiv): alle Zweige der Einteilung
    "rgb": [("intensity", 1), ("color_r", 2), ("color_g", 3), ("color_b", 4),
            ("pan", 5), ("cyan", 6)],
    # ohne Dimmer: die Farbe ist der virtuelle Dimmer
    "nur_farbe": [("color_r", 1), ("color_g", 2), ("color_b", 3), ("color_w", 4),
                  ("tilt", 5), ("magenta", 6)],
}


def _chans(fx):
    return [_Ch(a, n) for a, n in _KANAELE[fx.art]]


class _FM:
    """Effekt-Ersatz: schreibt je Frame feste Werte (Dimmer, Farbe)."""

    def __init__(self):
        self.werte: dict[tuple[int, int], int] = {}

    def tick(self, universes, patch_cache, dt):
        for (u, a), v in self.werte.items():
            if u in universes:
                universes[u].set_channel(a, v)


def _zustand(patch):
    st = AppState.__new__(AppState)
    st.universes = {u: Universe(u) for u in sorted({f.universe for f in patch} | {1})}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = list(patch)
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st._rebuild_render_plan()
    return st


def _patch():
    return [_Fx(1, 1, 1, "rgb"), _Fx(2, 1, 7, "nur_farbe"),
            _Fx(3, 2, 1, "rgb"), _Fx(4, 2, 507, "rgb")]      # 4: ragt über 512


class RenderPlanTest(unittest.TestCase):

    def setUp(self):
        alt = A.get_channels_for_patched
        A.get_channels_for_patched = _chans
        self.addCleanup(setattr, A, "get_channels_for_patched", alt)
        self.st = _zustand(_patch())

    def _zaehle_ableitungen(self, st):
        echt = st._adress_listen
        gerufen = []

        def ersatz(fx, chans):
            gerufen.append(fx.fid)
            return echt(fx, chans)
        st._adress_listen = ersatz
        return gerufen

    def test_plan_haelt_fuer_jedes_geraet_die_drei_listen(self):
        st = self.st
        self.assertEqual(set(st._adress_plan), {1, 2, 3, 4})
        for fid, (fx, chans) in st._fix_index.items():
            eintrag = st._adress_plan[fid]
            self.assertIs(eintrag[0], st._fix_index[fid])
            self.assertEqual((eintrag[1], eintrag[2]), (fx.address, fx.universe))
            self.assertEqual(tuple(eintrag[3:]), st._adress_listen(fx, chans))

    def test_die_drei_listen(self):
        st = self.st
        # Gerät 1 (Adresse 1): Dimmer 1; Farbe 2,3,4 und Cyan 6 (für „Farbe aktiv")
        self.assertEqual(st._adress_listen(*st._fix_index[1]), ([1], [1], [2, 3, 4, 6]))
        # Gerät 2 (Adresse 7) ohne Dimmer: additive Farbe ist der virtuelle
        # Dimmer — Magenta (subtraktiv) NICHT, steht aber in der Farb-Liste.
        self.assertEqual(st._adress_listen(*st._fix_index[2]),
                         ([7, 8, 9, 10], [], [7, 8, 9, 10, 12]))
        # Gerät 4 (Adresse 507): Kanäle über 512 fallen weg.
        self.assertEqual(st._adress_listen(*st._fix_index[4]),
                         ([507], [507], [508, 509, 510, 512]))

    def test_frame_nimmt_den_plan_statt_neu_abzuleiten(self):
        gerufen = self._zaehle_ableitungen(self.st)
        for _ in range(5):
            self.st._render_frame(0.02)
        self.assertEqual(gerufen, [])

    def test_frame_veraendert_die_geteilten_listen_nicht(self):
        st = self.st
        vorher = {fid: tuple(list(l) for l in e[3:]) for fid, e in st._adress_plan.items()}
        st.function_manager.werte = {(1, 1): 200, (1, 2): 90, (1, 8): 120}
        st.programmer = {1: {"intensity": 128}, 2: {"color_r": 255}}
        st.fixture_dimmers = {1: 0.5, 2: 0.25}
        for _ in range(4):
            st._render_frame(0.02)
        nachher = {fid: tuple(list(l) for l in e[3:]) for fid, e in st._adress_plan.items()}
        self.assertEqual(vorher, nachher)

    def test_von_hand_gesetzter_fix_index_wird_wie_bisher_gerechnet(self):
        """Viele Tests (und Werkzeuge) setzen ``_fix_index`` selbst. Der Plan
        gehört dann zu ANDEREN Einträgen und darf nicht gelten."""
        st = self.st
        fx = _Fx(1, 1, 101, "rgb")
        st._fix_index = {1: (fx, _chans(fx))}
        st._default_frame = {1: bytes(512)}
        st._commit_spans = {1: [(101, 6)]}
        st._patched_set = {1: frozenset(range(101, 107))}
        st.function_manager.werte = {(1, 101): 200}
        st.fixture_dimmers = {1: 0.5}
        gerufen = self._zaehle_ableitungen(st)
        st._render_frame(0.02)
        self.assertEqual(gerufen, [1])
        self.assertEqual(st.universes[1].get_channel(101), 100)     # an der NEUEN Adresse gedimmt
        self.assertEqual(st.universes[1].get_channel(1), 0)

    def test_ausgetauschter_eintrag_an_derselben_adresse(self):
        """Derselbe Platz, andere Kanäle: Adresse und Universum stimmen, der
        Eintrag ist aber ein anderer — die Listen des Plans gehören zum alten
        Gerät (Dimmer auf Adresse 1) und dürfen nicht gelten."""
        st = self.st
        fx = _Fx(1, 1, 1, "nur_farbe")              # Farbe ist hier der Dimmer
        st._fix_index = dict(st._fix_index)
        st._fix_index[1] = (fx, _chans(fx))
        st.function_manager.werte = {(1, 2): 200}
        st.fixture_dimmers = {1: 0.5}
        gerufen = self._zaehle_ableitungen(st)
        st._render_frame(0.02)
        self.assertEqual(gerufen, [1])
        self.assertEqual(st.universes[1].get_channel(2), 100)

    def test_am_objekt_geaenderte_adresse_wird_wie_bisher_gerechnet(self):
        st = self.st
        fx = st._fix_index[1][0]
        fx.address = 201                        # ohne Plan-Neubau
        gerufen = self._zaehle_ableitungen(st)
        st._render_frame(0.02)
        self.assertEqual(gerufen, [1])
        fx.address = 1
        del gerufen[:]
        st._render_frame(0.02)
        self.assertEqual(gerufen, [])

    def test_ohne_plan_feld_wie_bisher(self):
        """Zustände, die ohne ``__init__`` gebaut und nie geplant wurden."""
        st = self.st
        del st._adress_plan
        st.function_manager.werte = {(1, 1): 200}
        st.fixture_dimmers = {1: 0.5}
        gerufen = self._zaehle_ableitungen(st)
        st._render_frame(0.02)
        self.assertEqual(sorted(gerufen), [1, 2, 3, 4])
        self.assertEqual(st.universes[1].get_channel(1), 100)

    def test_neuer_patch_neuer_plan(self):
        st = self.st
        st._patch_cache = [_Fx(9, 1, 50, "nur_farbe")]
        st._rebuild_render_plan()
        self.assertEqual(set(st._adress_plan), {9})
        self.assertEqual(st._adress_plan[9][3], [50, 51, 52, 53])
        gerufen = self._zaehle_ableitungen(st)
        st._render_frame(0.02)
        self.assertEqual(gerufen, [])

    def test_geraet_dessen_ableitung_wirft_bleibt_ohne_eintrag(self):
        st = self.st
        echt = AppState._adress_listen

        def wirft_bei_3(fx, chans):
            if fx.fid == 3:
                raise ValueError("kaputt")
            return echt(st, fx, chans)
        st._adress_listen = wirft_bei_3
        st._rebuild_render_plan()
        self.assertEqual(set(st._adress_plan), {1, 2, 4})

    def _lauf(self, mit_plan: bool) -> list[bytes]:
        """Dieselben Frames mit und ohne Plan; alle Ebenen, die die Listen
        lesen: Programmer-Multiply (2b/4), implizite Helligkeit (4a²),
        Submaster/Geräte-Dimmer (4b)."""
        st = _zustand(_patch())
        if not mit_plan:
            st._adress_plan = {}
        st.implicit_brightness = True
        bilder = []
        schritte = [
            ({}, {}, {}),
            ({(1, 1): 200, (1, 2): 90, (1, 8): 120}, {}, {}),
            ({(1, 2): 255}, {}, {}),                                    # Farbe ohne Dimmer -> 4a²
            ({(1, 1): 200, (2, 1): 180}, {1: {"intensity": 128}}, {}),  # Programmer multipliziert
            ({(1, 8): 250, (1, 12): 99}, {2: {"color_g": 200}}, {2: 0.3}),
            ({(2, 507): 255, (2, 508): 255}, {3: {"color_r": 9}}, {4: 0.5, 1: 0.1}),
        ]
        for effekt, programmer, dimmer in schritte:
            st.function_manager.werte = dict(effekt)
            st.programmer = {k: dict(v) for k, v in programmer.items()}
            st.fixture_dimmers = dict(dimmer)
            for _ in range(2):
                st._render_frame(0.02)
                bilder.append(b"".join(bytes(st.universes[u].get_all())
                                       for u in sorted(st.universes)))
        return bilder

    def test_gleiche_ausgabe_mit_und_ohne_plan(self):
        mit, ohne = self._lauf(True), self._lauf(False)
        self.assertEqual(mit, ohne)
        self.assertTrue(any(any(b) for b in mit), "Probe schreibt gar nichts")
        self.assertGreater(len(set(mit)), 3, "Probe unterscheidet die Schritte nicht")


if __name__ == "__main__":
    unittest.main()
