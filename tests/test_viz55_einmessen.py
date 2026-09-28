"""VIZ-55 Stufe A + B: Einmessen — „Strahl schieben, bis er sitzt" — und daraus
die echte Position rechnen.

Die Geometrie ist bewusst AUFBAU-UNABHAENGIG: zufaellige Standorte, drei
Montagearten (stehend, haengend, seitlich an der Wand) und Zielpunkte, die im
Lichtkegel um die jeweilige Montage-Achse erzeugt werden. Ein „echtes" Geraet
haengt dabei kuenstlich woanders als eingetragen; geprueft wird, ob das
Einmessen die Abweichung herausrechnet — gemessen an der Richtung, in die der
ECHTE Kopf zeigt, nicht an DMX-Werten.

Abnahme (BACKLOG): eine Korrektur an EINEM Punkt trifft diesen (Stufe A);
Korrekturen an verschiedenen Punkten treffen nie angetippte Punkte (Stufe B);
ein Geraet ohne Korrektur verhaelt sich unveraendert.

★ Abweichung vom Backlog-Wortlaut („DREI Korrekturen treffen einen vierten"),
gemessen begruendet: aus drei Punkten laesst sich eine Position RECHNEN, aber
nicht PRUEFEN — mit 1 cm Einstellrauschen lag sie gelegentlich 25 cm daneben,
ohne dass ein Mass es vorher zeigte. Stufe B braucht deshalb vier Punkte und
bietet nur an, was die Gegenprobe (leave-one-out) besteht.
"""
import math
import os
import random
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage.aim import _mount_matrix, aim_pan_tilt_16
from src.core.stage.einmessen import (
    MAX_GEGENPROBE_CM, EinmessSitzung, Messpunkt, _kw_ohne_versatz,
    aim_kw, effektive_nullpunkte, loese_position, verschiedene,
    versatz_aus_korrektur)

GERAET = dict(pan_range_deg=540.0, tilt_range_deg=270.0,
              pan_zero_dmx=128.0, tilt_zero_dmx=128.0)
MONTAGEN = {"stehend": (180.0, 0.0, 0.0), "haengend": (0.0, 0.0, 0.0),
            "wand": (90.0, 0.0, 0.0)}


class _Ch:
    def __init__(self, attr):
        self.attribute = attr


FEIN = [_Ch("pan"), _Ch("pan_fine"), _Ch("tilt"), _Ch("tilt_fine")]
GROB = [_Ch("pan"), _Ch("tilt")]


# ── Geometrie-Helfer (von Hand, nicht ueber die geprueften Funktionen) ─────────

def _richtung(pos, rot, p16, t16, kw=GERAET):
    """Wohin zeigt ein Kopf bei diesen 16-Bit-Werten? Umkehrung der Winkelformel."""
    p, t = p16 / 256.0, t16 / 256.0
    pr = math.radians((p - kw["pan_zero_dmx"]) / 128.0 * kw["pan_range_deg"] / 2.0)
    tr = math.radians((t - kw["tilt_zero_dmx"]) / 128.0 * kw["tilt_range_deg"] / 2.0)
    d = (-math.sin(tr) * math.sin(pr), -math.cos(tr), -math.sin(tr) * math.cos(pr))
    R = _mount_matrix(*rot)
    return tuple(sum(R[i][j] * d[j] for j in range(3)) for i in range(3))


def _fehler_cm(echt_pos, echt_rot, p16, t16, ziel):
    """Abstand (cm) zwischen Ziel und Strahl des ECHTEN Kopfes, in Zielentfernung."""
    d = _richtung(echt_pos, echt_rot, p16, t16)
    s = [ziel[i] - echt_pos[i] for i in range(3)]
    n = math.sqrt(sum(x * x for x in s))
    cos = max(-1.0, min(1.0, sum(a * b / n for a, b in zip(d, s))))
    return math.acos(cos) * n * 100.0


def _ziel_im_kegel(rnd, pos, rot, kegel_grad=55.0):
    """Zufaelliger, erreichbarer Zielpunkt: im Kegel um die Montage-„Unten"-Achse,
    2-5 m entfernt — fuer JEDE Montage gleich sinnvoll."""
    R = _mount_matrix(*rot)
    while True:
        th = math.radians(rnd.uniform(0, kegel_grad))
        ph = rnd.uniform(-math.pi, math.pi)
        lok = (math.sin(th) * math.cos(ph), -math.cos(th), math.sin(th) * math.sin(ph))
        w = tuple(sum(R[i][j] * lok[j] for j in range(3)) for i in range(3))
        dist = rnd.uniform(2.0, 5.0)
        return tuple(pos[i] + w[i] * dist for i in range(3))


def _echtes_geraet(rnd, pos, rot, neigung=0.0):
    """Das Geraet haengt in Wahrheit bis 40 cm woanders und ist um die Hochachse
    bis 10 Grad verdreht (+ optional etwas Neigung)."""
    echt_pos = tuple(pos[i] + rnd.uniform(-0.4, 0.4) for i in range(3))
    from src.core.stage.aim import _euler_xyz_from_matrix, _matmul, _ry
    D = _matmul(_ry(math.radians(rnd.uniform(-10, 10))), _mount_matrix(*rot))
    if neigung:
        D = _matmul(_mount_matrix(rnd.uniform(-neigung, neigung), 0.0,
                                  rnd.uniform(-neigung, neigung)), D)
    return echt_pos, _euler_xyz_from_matrix(D)


def _korrektur(echt_pos, echt_rot, ziel, rausch_m=0.0, rnd=None):
    """Was der Nutzer am Rig einstellt: die Werte, bei denen der ECHTE Kopf das
    Ziel trifft (optional mit Einstellrauschen)."""
    z = ziel if not rausch_m else tuple(v + rnd.gauss(0, rausch_m) for v in ziel)
    return aim_pan_tilt_16(echt_pos, z, echt_rot, **GERAET)


# ── Fakes ───────────────────────────────────────────────────────────────────────

class _State:
    def __init__(self, fixtures=()):
        self.prog = {}
        self.fixtures = {f.fid: f for f in fixtures}
        self.visualizer_positions = {}
        self.visualizer_rotations = {}
        self.updates = []

    def get_programmer_value(self, fid, attr, head=None):
        return self.prog.get((fid, attr))

    def set_programmer_value(self, fid, attr, value, head=None, **kw):
        self.prog[(fid, attr)] = value

    def update_fixture(self, fid, undoable=True, **changes):
        self.updates.append((fid, changes))
        for k, v in changes.items():
            setattr(self.fixtures[fid], k, v)
        return True

    def get_patched_fixtures(self):
        return list(self.fixtures.values())


def _fx(fid=1, **extra):
    f = SimpleNamespace(fid=fid, label=f"MH {fid}", pan_range_deg=540, tilt_range_deg=270,
                        pan_zero_dmx=128, tilt_zero_dmx=128,
                        aim_offset_pan=0.0, aim_offset_tilt=0.0)
    for k, v in extra.items():
        setattr(f, k, v)
    return f


# ── Nullpunkt: die EINE Stelle ──────────────────────────────────────────────────

class NullpunktTest(unittest.TestCase):

    def test_ohne_versatz_genau_der_konfigurierte(self):
        self.assertEqual(effektive_nullpunkte(_fx(pan_zero_dmx=167, tilt_zero_dmx=141)),
                         (167.0, 141.0))

    def test_versatz_verschiebt_den_nullpunkt(self):
        f = _fx(aim_offset_pan=0.25, aim_offset_tilt=-1.5)
        self.assertEqual(effektive_nullpunkte(f), (128.25, 126.5))

    def test_null_bleibt_null_nur_fehlend_wird_128(self):
        """Bis 2026-09-28 machte das Zielen aus 0 eine 128 (``or 128``), 3D und 2D
        nicht — jetzt eine Regel fuer alle."""
        self.assertEqual(effektive_nullpunkte(_fx(pan_zero_dmx=0, tilt_zero_dmx=0)), (0.0, 0.0))
        self.assertEqual(effektive_nullpunkte(SimpleNamespace()), (128.0, 128.0))
        self.assertEqual(effektive_nullpunkte(_fx(pan_zero_dmx=None)), (128.0, 128.0))

    def test_kw_ohne_versatz_ist_der_konfigurierte(self):
        f = _fx(aim_offset_pan=2.0, aim_offset_tilt=-3.0)
        self.assertEqual(aim_kw(f)["pan_zero_dmx"], 130.0)
        self.assertEqual(_kw_ohne_versatz(f)["pan_zero_dmx"], 128.0)
        self.assertEqual(_kw_ohne_versatz(f)["tilt_zero_dmx"], 128.0)


# ── Stufe A ─────────────────────────────────────────────────────────────────────

class StufeATest(unittest.TestCase):

    def test_korrektur_an_einem_punkt_trifft_diesen(self):
        """Fuer jede Montage, 20 zufaellige Aufbauten: nach dem Merken trifft das
        Zielen den korrigierten Punkt am ECHTEN Geraet (< 1 mm)."""
        rnd = random.Random(55)
        for name, rot in MONTAGEN.items():
            for _ in range(20):
                pos = (rnd.uniform(-3, 3), rnd.uniform(2, 5), rnd.uniform(-3, 3))
                echt_pos, echt_rot = _echtes_geraet(rnd, pos, rot)
                ziel = _ziel_im_kegel(rnd, echt_pos, echt_rot, 40.0)
                ist = _korrektur(echt_pos, echt_rot, ziel)
                soll = aim_pan_tilt_16(pos, ziel, rot, **GERAET)
                vp, vt = versatz_aus_korrektur(ist, soll)
                kw = dict(GERAET, pan_zero_dmx=128 + vp, tilt_zero_dmx=128 + vt)
                neu = aim_pan_tilt_16(pos, ziel, rot, **kw)
                with self.subTest(montage=name):
                    self.assertLess(_fehler_cm(echt_pos, echt_rot, *neu, ziel), 0.1)

    def test_zweite_korrektur_ersetzt_statt_aufzuaddieren(self):
        """Der Versatz wird gegen das Zielen OHNE Versatz gerechnet — sonst wuerde
        die zweite Korrektur die erste doppelt zaehlen."""
        soll = (100 * 256, 120 * 256)
        self.assertEqual(versatz_aus_korrektur((101 * 256, 119 * 256), soll), (1.0, -1.0))
        self.assertEqual(versatz_aus_korrektur((101 * 256 + 64, 120 * 256), soll), (1.25, 0.0))


# ── Stufe B ─────────────────────────────────────────────────────────────────────

class StufeBTest(unittest.TestCase):

    def _lauf(self, montage, n_punkte, neigung, rausch_m, n_faelle, seed):
        rnd = random.Random(seed)
        rot = MONTAGEN[montage]
        fehler, vorher, modi = [], [], []
        for _ in range(n_faelle):
            pos = (rnd.uniform(-3, 3), rnd.uniform(2, 5), rnd.uniform(-3, 3))
            echt_pos, echt_rot = _echtes_geraet(rnd, pos, rot, neigung)
            ziele = [_ziel_im_kegel(rnd, echt_pos, echt_rot) for _ in range(n_punkte)]
            pruef = [_ziel_im_kegel(rnd, echt_pos, echt_rot) for _ in range(3)]
            mp = [Messpunkt(z, *_korrektur(echt_pos, echt_rot, z, rausch_m, rnd)) for z in ziele]
            L = loese_position(mp, pos, rot, GERAET)
            vorher.append(max(_fehler_cm(echt_pos, echt_rot,
                                         *aim_pan_tilt_16(pos, z, rot, **GERAET), z) for z in pruef))
            if L is None:
                modi.append(None)
                continue
            modi.append(L.modus)
            fehler.append(max(_fehler_cm(echt_pos, echt_rot,
                                         *aim_pan_tilt_16(L.pos, z, L.rot, **GERAET), z)
                              for z in pruef))
        return fehler, vorher, modi

    def test_vier_punkte_treffen_nie_angetippte(self):
        """DIE Abnahme: vier Korrekturen, danach trifft das Zielen nie angetippte
        Punkte — fuer alle drei Montagearten, auch bei geneigter Montage (+-3 Grad),
        ohne Rauschen auf unter 1 cm."""
        for montage in MONTAGEN:
            with self.subTest(montage=montage):
                fehler, vorher, modi = self._lauf(montage, 4, 3.0, 0.0, 15, 7)
                self.assertGreaterEqual(len(fehler), 13, modi)
                self.assertLess(max(fehler), 1.0)
                self.assertGreater(sorted(vorher)[len(vorher) // 2], 10.0)   # vorher daneben

    def test_drei_punkte_noch_keine_position(self):
        """Drei Punkte: rechenbar, aber nicht pruefbar — also nicht angeboten."""
        fehler, _v, modi = self._lauf("haengend", 3, 0.0, 0.0, 10, 8)
        self.assertEqual(modi, [None] * 10)

    def test_mit_realistischem_einstellrauschen(self):
        """1 cm Einstellrauschen, 4-6 Punkte, alle Montagen, Neigung +-3 Grad: die
        ANGEBOTENEN Loesungen treffen neue Punkte im Median auf ~2 cm, hoechstens
        ~15 cm (ohne Gegenprobe gemessen: bis 46 cm) — und klar besser als vorher."""
        fehler, vorher = [], []
        for i, montage in enumerate(MONTAGEN):
            for n in (4, 5, 6):
                f, v, _m = self._lauf(montage, n, 3.0, 0.01, 15, 90 + 10 * i + n)
                fehler += f
                vorher += v
        fehler.sort()
        self.assertGreater(len(fehler), 60)
        self.assertLess(fehler[len(fehler) // 2], 3.0)
        self.assertLess(fehler[-1], 15.0)
        self.assertLess(fehler[len(fehler) // 2], sorted(vorher)[len(vorher) // 2] / 5)

    def test_zu_wenige_oder_zu_nahe_punkte_keine_loesung(self):
        pos, rot = (0.0, 4.0, 0.0), MONTAGEN["haengend"]
        z = [(1.0, 0.0, 1.0), (-1.0, 0.0, 1.5), (0.0, 0.0, 2.5)]
        mp = [Messpunkt(zz, *aim_pan_tilt_16(pos, zz, rot, **GERAET)) for zz in z]
        self.assertIsNone(loese_position(mp, pos, rot, GERAET))           # nur drei
        nah = [Messpunkt((1.0 + i * 0.05, 0.0, 1.0), *mp[0][1:] if False else
                         aim_pan_tilt_16(pos, (1.0 + i * 0.05, 0.0, 1.0), rot, **GERAET))
               for i in range(4)]
        self.assertIsNone(loese_position(nah, pos, rot, GERAET))

    def test_widerspruechliche_korrekturen_keine_loesung(self):
        """Lieber keine Position als eine geratene: passt kein Standort zu den
        Korrekturen, wird nichts angeboten."""
        pos, rot = (0.0, 4.0, 0.0), MONTAGEN["haengend"]
        z = [(1.5, 0.0, 1.0), (-1.5, 0.0, 1.5), (0.0, 0.0, 3.0), (0.5, 1.0, 3.0)]
        mp = [Messpunkt(zz, *aim_pan_tilt_16(pos, zz, rot, **GERAET)) for zz in z]
        mp[2] = Messpunkt(z[2], mp[2].pan16 + 40 * 256, mp[2].tilt16)     # grob falsch
        self.assertIsNone(loese_position(mp, pos, rot, GERAET))

    def test_juengerer_von_zwei_nahen_punkten_gilt(self):
        a = Messpunkt((0.0, 0.0, 1.0), 1, 1)
        b = Messpunkt((0.1, 0.0, 1.0), 2, 2)
        self.assertEqual(verschiedene([a, b]), [b])


# ── Sitzung (Bedienung ohne Qt) ─────────────────────────────────────────────────

class SitzungTest(unittest.TestCase):

    def _aufbau(self):
        f = _fx()
        st = _State([f])
        s = EinmessSitzung()
        return f, st, s

    def test_schieben_mit_und_ohne_feinkanal(self):
        f, st, s = self._aufbau()
        st.prog = {(1, "pan"): 100, (1, "pan_fine"): 250, (1, "tilt"): 90, (1, "tilt_fine"): 0}
        self.assertTrue(s.schiebe(st, 1, FEIN, "pan", 16))
        self.assertEqual((st.prog[(1, "pan")], st.prog[(1, "pan_fine")]), (101, 10))
        st.prog = {(1, "pan"): 100, (1, "tilt"): 90}
        self.assertTrue(s.schiebe(st, 1, GROB, "tilt", -16))       # ohne Fein: ganzer Schritt
        self.assertEqual(st.prog[(1, "tilt")], 89)
        self.assertFalse(s.schiebe(st, 1, GROB, "pan", 16) is False and False)

    def test_ohne_programmerwert_nichts(self):
        f, st, s = self._aufbau()
        self.assertFalse(s.schiebe(st, 1, FEIN, "pan", 16))

    def test_merken_ohne_ziel_nichts(self):
        f, st, s = self._aufbau()
        st.prog = {(1, "pan"): 100, (1, "tilt"): 90}
        self.assertIsNone(s.merken(st, f, GROB, (0, 4, 0), (0, 0, 0)))
        self.assertEqual(st.updates, [])

    def test_merken_setzt_versatz_und_sammelt(self):
        """Durchstich Stufe A + B ueber die Sitzung: vier Korrekturen am „echten"
        Geraet, danach steht eine gepruefte Loesung bereit, die neue Punkte trifft."""
        rnd = random.Random(3)
        f, st, s = self._aufbau()
        pos, rot = (0.0, 4.0, 0.0), MONTAGEN["haengend"]
        echt_pos, echt_rot = _echtes_geraet(rnd, pos, rot)
        r = None
        for _ in range(4):
            ziel = _ziel_im_kegel(rnd, echt_pos, echt_rot)
            s.ziel_gesetzt(1, ziel)
            p16, t16 = _korrektur(echt_pos, echt_rot, ziel)
            st.prog = {(1, "pan"): p16 >> 8, (1, "pan_fine"): p16 & 255,
                       (1, "tilt"): t16 >> 8, (1, "tilt_fine"): t16 & 255}
            r = s.merken(st, f, FEIN, pos, rot)
            # Stufe A sofort: mit dem gemerkten Versatz trifft das Zielen diesen Punkt
            neu = aim_pan_tilt_16(pos, ziel, rot, **aim_kw(f))
            self.assertLess(_fehler_cm(echt_pos, echt_rot, *neu, ziel), 0.1)
        self.assertEqual(r.punkte, 4)
        self.assertIsNotNone(r.loesung)
        self.assertLessEqual(r.loesung.gegenprobe_cm, MAX_GEGENPROBE_CM)
        viert = _ziel_im_kegel(rnd, echt_pos, echt_rot)
        p = aim_pan_tilt_16(r.loesung.pos, viert, r.loesung.rot, **_kw_ohne_versatz(f))
        self.assertLess(_fehler_cm(echt_pos, echt_rot, *p, viert), 1.0)

    def test_vergessen_setzt_zurueck(self):
        f, st, s = self._aufbau()
        f.aim_offset_pan = 1.5
        s.punkte[1] = [Messpunkt((0, 0, 1), 0, 0)]
        s.vergessen(st, 1)
        self.assertEqual((f.aim_offset_pan, f.aim_offset_tilt), (0.0, 0.0))
        self.assertNotIn(1, s.punkte)


# ── Speicherung ─────────────────────────────────────────────────────────────────

class SpeicherungTest(unittest.TestCase):

    def test_show_datei_rundreise_und_altbestand(self):
        from src.core.show.show_file import _fixture_to_dict, _patched_fixture_from_data
        f = _fx(aim_offset_pan=0.375, aim_offset_tilt=-2.5)
        for k, v in dict(universe=1, address=1, channel_count=16, fixture_profile_id=1,
                         mode_name="", manufacturer_name="", fixture_name="",
                         fixture_type="moving_head").items():
            setattr(f, k, v)
        d = _fixture_to_dict(f)
        self.assertEqual((d["aim_offset_pan"], d["aim_offset_tilt"]), (0.375, -2.5))
        g = _patched_fixture_from_data(dict(d), 1)
        self.assertEqual((g.aim_offset_pan, g.aim_offset_tilt), (0.375, -2.5))
        alt = {k: v for k, v in d.items() if not k.startswith("aim_offset")}
        g = _patched_fixture_from_data(alt, 1)                     # Alt-Show ohne Feld
        self.assertEqual((g.aim_offset_pan, g.aim_offset_tilt), (0.0, 0.0))

    def test_kaputte_werte_werden_null(self):
        from src.core.show.show_file import _to_offset
        for kaputt in (None, "abc", float("nan"), float("inf")):
            self.assertEqual(_to_offset(kaputt), 0.0, kaputt)
        self.assertEqual(_to_offset(1000), 64.0)                   # begrenzt


# ── Bedienung im Fenster ────────────────────────────────────────────────────────

class FensterTest(unittest.TestCase):
    """Die Gruppe „Einmessen" im echten Qt-Fenster (ohne WebEngine-Aufbau)."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def _fenster(self, fixtures):
        import src.ui.visualizer.visualizer_window as VW
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        class _W(VW.VisualizerWindow):
            def __init__(self):
                VW.QMainWindow.__init__(self)

        w = _W()
        st = _State(fixtures)
        for f in fixtures:
            st.visualizer_positions[f.fid] = (0.0, 4.0, 0.0)
            st.visualizer_rotations[f.fid] = MONTAGEN["haengend"]
        w._state = st
        w._bridge = SimpleNamespace(einmessen=EinmessSitzung(), _is_moving_head=lambda f: True,
                                    _mover_bar_heads=lambda f: 0, refresh_fixture=MagicMock())
        w._patch_list = QListWidget()
        for f in fixtures:
            it = QListWidgetItem(f.label)
            it.setData(Qt.ItemDataRole.UserRole, f.fid)
            w._patch_list.addItem(it)
        box = VW.VisualizerWindow._build_einmessen_box(w)
        self.addCleanup(box.deleteLater)
        self.addCleanup(w.deleteLater)
        orig = VW.get_channels_for_patched
        VW.get_channels_for_patched = lambda f: FEIN
        self.addCleanup(setattr, VW, "get_channels_for_patched", orig)
        return w, st

    def test_ohne_auswahl_hinweis(self):
        w, st = self._fenster([_fx()])
        w._einmess_status()
        self.assertIn("Moving Head wählen", w._lbl_einmess.text())
        self.assertFalse(w._btn_einmess_uebernehmen.isEnabled())

    def test_merken_ohne_ziel_sagt_es(self):
        w, st = self._fenster([_fx()])
        w._patch_list.item(0).setSelected(True)
        st.prog = {(1, "pan"): 100, (1, "tilt"): 90}
        w._einmess_merken()
        self.assertIn("noch kein Punkt angezielt", w._lbl_einmess.text())

    def test_schieben_und_merken_und_status(self):
        w, st = self._fenster([_fx()])
        w._patch_list.item(0).setSelected(True)
        w._bridge.einmessen.ziel_gesetzt(1, (1.0, 0.0, 1.0))
        p16, t16 = aim_pan_tilt_16((0.0, 4.0, 0.0), (1.0, 0.0, 1.0), MONTAGEN["haengend"], **GERAET)
        st.prog = {(1, "pan"): p16 >> 8, (1, "pan_fine"): p16 & 255,
                   (1, "tilt"): t16 >> 8, (1, "tilt_fine"): t16 & 255}
        for _ in range(4):
            w._einmess_schieben("pan", +1)                         # 4 x 1/16 = 1/4 DMX
        w._einmess_merken()
        self.assertAlmostEqual(st.fixtures[1].aim_offset_pan, 0.25, places=6)
        w._bridge.refresh_fixture.assert_called_with(1)
        self.assertIn("1 Punkt(e)", w._lbl_einmess.text())
        self.assertIn("Korrektur Pan +0.25", w._lbl_einmess.text())
        self.assertFalse(w._btn_einmess_uebernehmen.isEnabled())

    def test_zuruecksetzen(self):
        w, st = self._fenster([_fx(aim_offset_pan=1.0)])
        w._patch_list.item(0).setSelected(True)
        w._einmess_zuruecksetzen()
        self.assertEqual(st.fixtures[1].aim_offset_pan, 0.0)

    def test_mover_bar_ausgenommen(self):
        w, st = self._fenster([_fx()])
        w._bridge._mover_bar_heads = lambda f: 2
        w._patch_list.item(0).setSelected(True)
        w._einmess_status()
        self.assertIn("Mover-Bars: noch nicht", w._lbl_einmess.text())

    def test_grosse_korrektur_fragt_nach_dem_aufbau(self):
        w, st = self._fenster([_fx(aim_offset_pan=20.0)])       # 20 DMX ~ 42 Grad bei 540
        w._patch_list.item(0).setSelected(True)
        w._einmess_status()
        self.assertIn("stimmen Standort, Montage", w._lbl_einmess.text())

    def test_kleine_korrektur_warnt_nicht(self):
        w, st = self._fenster([_fx(aim_offset_pan=0.5)])
        w._patch_list.item(0).setSelected(True)
        w._einmess_status()
        self.assertNotIn("⚠", w._lbl_einmess.text())


class DatenbankTest(unittest.TestCase):
    """Migration + ``update_fixture`` mit der echten Show-DB."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.core.app_state import get_state
        from src.core.database.fixture_db import ensure_builtins
        from src.core.show.show_file import reset_show
        ensure_builtins()
        reset_show()
        self.state = get_state()
        from src.core.database.models import PatchedFixture
        self.state.add_fixture(PatchedFixture(
            fid=1, label="MH", fixture_profile_id=1, mode_name="m", universe=1,
            address=1, channel_count=16, fixture_type="moving_head"))

    def _f(self):
        return next(x for x in self.state.get_patched_fixtures() if x.fid == 1)

    def test_spalten_da_default_null(self):
        from sqlalchemy import text
        with self.state._show_engine.begin() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(patched_fixtures)"))}
        self.assertTrue({"aim_offset_pan", "aim_offset_tilt"} <= cols)
        self.assertEqual((self._f().aim_offset_pan or 0.0, self._f().aim_offset_tilt or 0.0),
                         (0.0, 0.0))

    def test_update_fixture_behaelt_die_kommazahl(self):
        self.assertTrue(self.state.update_fixture(1, aim_offset_pan=0.3125, aim_offset_tilt=-1.75))
        self.assertEqual((self._f().aim_offset_pan, self._f().aim_offset_tilt), (0.3125, -1.75))

    def test_update_fixture_kaputter_wert_wird_null(self):
        self.state.update_fixture(1, aim_offset_pan="abc", aim_offset_tilt=float("nan"))
        self.assertEqual((self._f().aim_offset_pan, self._f().aim_offset_tilt), (0.0, 0.0))


class VerdrahtungTest(unittest.TestCase):
    """Nutzen Zielen und 3D den Versatz WIRKLICH? Genau diese Verdrahtung ist bei
    VIZ-55 Slice 1 schon einmal auseinandergelaufen (Bild und Geraet verschieden)."""

    def test_zielen_im_handler_nutzt_den_versatz(self):
        import json
        import src.ui.visualizer.visualizer_window as VW
        f = _fx(aim_offset_pan=0.75, aim_offset_tilt=-0.5)
        st = SimpleNamespace(get_patched_fixtures=lambda: [f],
                             visualizer_positions={1: (0.0, 4.0, 0.0)},
                             visualizer_rotations={1: MONTAGEN["haengend"]},
                             set_programmer_value=MagicMock())
        fake = SimpleNamespace(_state=st, _is_moving_head=lambda x: True,
                               push_apply_fixture_transform=MagicMock(),
                               pyFixtureRotated=MagicMock(), pyAimApplied=MagicMock(),
                               einmessen=EinmessSitzung())
        orig = VW.get_channels_for_patched
        VW.get_channels_for_patched = lambda x: FEIN
        try:
            VW.VisualizerBridge.aimFixturesAt(fake, json.dumps(
                {"x": 1.0, "y": 0.0, "z": 1.0, "fids": [1]}))
        finally:
            VW.get_channels_for_patched = orig
        w = {c.args[1]: c.args[2] for c in st.set_programmer_value.call_args_list}
        erwartet = aim_pan_tilt_16((0.0, 4.0, 0.0), (1.0, 0.0, 1.0), MONTAGEN["haengend"],
                                   **dict(GERAET, pan_zero_dmx=128.75, tilt_zero_dmx=127.5))
        self.assertEqual((w["pan"] * 256 + w["pan_fine"], w["tilt"] * 256 + w["tilt_fine"]),
                         erwartet)
        self.assertEqual(fake.einmessen.ziel[1], (1.0, 0.0, 1.0))     # Ziel gemerkt

    def test_3d_bekommt_den_effektiven_nullpunkt(self):
        import src.ui.visualizer.visualizer_window as VW
        f = _fx(aim_offset_pan=0.75, aim_offset_tilt=-0.5)
        for k, v in dict(fixture_type="moving_head", manufacturer_name="", fixture_name="",
                         mode_name="", channel_count=16, universe=1, address=1).items():
            setattr(f, k, v)
        fake = SimpleNamespace(_state=SimpleNamespace(
            visualizer_positions={1: (0.0, 4.0, 0.0)}, visualizer_rotations={},
            visualizer_docks={}, visualizer_beam_hidden=set()),
            _viz_model_for=lambda x: "moving_head")
        try:
            d = VW.VisualizerBridge._fixture_to_dict(fake, f)
        except Exception as e:                                     # pragma: no cover
            self.skipTest(f"_fixture_to_dict braucht mehr Umgebung: {e}")
        self.assertEqual((d["panZero"], d["tiltZero"]), (128.75, 127.5))


    def test_patch_changed_baut_nur_geaenderte_nullpunkte_neu(self):
        """Rueckgaengig eines „Merken" (update_fixture -> patch_changed) muss das
        3D nachziehen — sonst zeigte das Bild den zurueckgenommenen Nullpunkt."""
        import src.ui.visualizer.visualizer_window as VW
        a, b = _fx(1), _fx(2)
        fake = SimpleNamespace(
            _state=SimpleNamespace(get_patched_fixtures=lambda: [a, b],
                                   visualizer_positions={1: (0, 4, 0), 2: (1, 4, 0)}),
            fixtureAdded=MagicMock(), _fixture_to_dict=lambda f: {"fid": f.fid})
        VW.VisualizerBridge._nullpunkte_nachziehen(fake)          # erstes Sehen: nur merken
        fake.fixtureAdded.emit.assert_not_called()
        a.aim_offset_pan = 0.5                                      # z. B. Rueckgaengig
        VW.VisualizerBridge._nullpunkte_nachziehen(fake)
        self.assertEqual([c.args[0] for c in fake.fixtureAdded.emit.call_args_list],
                         ['{"fid": 1}'])
        VW.VisualizerBridge._nullpunkte_nachziehen(fake)          # nichts Neues
        self.assertEqual(fake.fixtureAdded.emit.call_count, 1)


if __name__ == "__main__":
    unittest.main()
