"""VIZ-104: Strobe im 3D-Visualizer sichtbar machen.

Befund: ein Shutter im Strobe-Bereich war im 3D Dauerlicht
(``color_utils.visual_intensity`` -> 255); nur die 2D-Live-Ansicht blinkte. Die
Lichtdaten kommen mit 15/30/44 Hz — ein 20-Hz-Strobe laesst sich darueber nicht
abbilden. Jetzt schickt Python die Blitzfrequenz mit (``strobe_hz``), und die
Szene schaltet selbst im Bildtakt.

Geprueft wird hier ohne Seite:

* die Frequenz aus dem Profil und die Naeherung ohne Bereichsdaten
  (``src/core/strobe.py``) — offen, zu, Strobe-Bereich, Frequenz im Namen;
* 2D und 3D benutzen DIESELBE Funktion;
* der Payload traegt die Frequenz, 0 bei Dauerlicht, je Kopf bei eigenem Shutter;
* die Einstellung „Strobe im 3D zeigen" wird gespeichert und gelesen;
* die Blitz-Funktion der Szene (``scene_src/fixtures/strobe.js``, unter Node):
  Tastverhaeltnis, Deckel, Bildraten-Grenze, gedaempfter Modus;
* Python- und JS-Konstanten stimmen ueberein;
* die Anleitung beschreibt Verhalten, Begrenzung, Einstellung und Warnhinweis.

Die Verdrahtung in der echten Seite prueft ``test_viz104_strobe_im_3d_scene.py``.
"""
import json
import os
import re
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import strobe as S                                   # noqa: E402
from src.ui.visualizer import strobe_prefs as P                    # noqa: E402
from src.ui.visualizer.visualizer_service import _build_fixture_payload  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCENE = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src")
_MODUL = os.path.join(_SCENE, "fixtures", "strobe.js")
_ANLEITUNG = os.path.join(_REPO, "docs", "anleitung_3d_visualizer_2026",
                          "ANLEITUNG_3D_BUEHNE.md")


def _rng(lo, hi, name, kind=""):
    return SimpleNamespace(range_from=lo, range_to=hi, name=name, kind=kind)


def _ch(attribute="shutter", ranges=(), name="Shutter"):
    return SimpleNamespace(attribute=attribute, ranges=list(ranges), name=name)


_SHUTTER = _ch(ranges=[
    _rng(0, 9, "Zu", "closed"),
    _rng(10, 19, "Offen", "open"),
    _rng(20, 219, "Strobe langsam -> schnell", "strobe"),
    _rng(220, 239, "Zufall", "sound"),
    _rng(240, 255, "Open"),            # ohne kind, Name heisst eindeutig „an"
])


class FrequenzAusProfilTest(unittest.TestCase):
    def test_zu_und_offen_blitzen_nicht(self):
        for val in (0, 9, 10, 19, 240, 255):
            self.assertEqual(S.strobe_hz(_SHUTTER, val), 0.0, val)

    def test_bereich_anderer_art_blitzt_nicht(self):
        self.assertEqual(S.strobe_hz(_SHUTTER, 230), 0.0)

    def test_strobe_bereich_steigt_von_min_auf_max(self):
        self.assertAlmostEqual(S.strobe_hz(_SHUTTER, 20), S.HZ_MIN)
        self.assertAlmostEqual(S.strobe_hz(_SHUTTER, 219), S.HZ_MAX)
        mitte = S.strobe_hz(_SHUTTER, 120)
        self.assertTrue(S.HZ_MIN < mitte < S.HZ_MAX, mitte)
        werte = [S.strobe_hz(_SHUTTER, v) for v in range(20, 220)]
        self.assertEqual(werte, sorted(werte))

    def test_wert_ausserhalb_aller_bereiche_blitzt_nicht(self):
        ch = _ch(ranges=[_rng(10, 100, "Strobe", "strobe")])
        self.assertEqual(S.strobe_hz(ch, 5), 0.0)
        self.assertEqual(S.strobe_hz(ch, 200), 0.0)

    def test_frequenz_im_bereichsnamen_gilt(self):
        ch = _ch(ranges=[_rng(16, 115, "Strobe 1-25 Hz", "strobe"),
                         _rng(116, 135, "Strobe 10 Hz", "strobe"),
                         _rng(136, 235, "Strobe fast to slow", "strobe")])
        self.assertAlmostEqual(S.strobe_hz(ch, 16), 1.0)
        self.assertAlmostEqual(S.strobe_hz(ch, 115), 25.0)
        self.assertAlmostEqual(S.strobe_hz(ch, 120), 10.0)
        self.assertAlmostEqual(S.strobe_hz(ch, 136), S.HZ_MAX)
        self.assertAlmostEqual(S.strobe_hz(ch, 235), S.HZ_MIN)

    def test_namen_ohne_frequenz_und_unsinn(self):
        self.assertIsNone(S.hz_spanne_aus_name("Strobe langsam -> schnell"))
        self.assertIsNone(S.hz_spanne_aus_name(None))
        self.assertIsNone(S.hz_spanne_aus_name("Strobe 0-900 Hz"))      # Tippfehler
        self.assertEqual(S.hz_spanne_aus_name("Strobe 0,5 bis 12,5 Hz"), (0.5, 12.5))
        self.assertEqual(S.hz_spanne_aus_name("1Hz - 20Hz"), (1.0, 20.0))

    def test_ohne_bereichsdaten_gilt_die_naeherung_der_2d_ansicht(self):
        ch = _ch(attribute="strobe", name="Strobe")
        for val in (0, 5, 10):
            self.assertEqual(S.strobe_hz(ch, val), 0.0, val)
        self.assertAlmostEqual(S.strobe_hz(ch, 11), 0.5)
        self.assertAlmostEqual(S.strobe_hz(ch, 255), 20.0)
        # Genau die Formel, die bis VIZ-104 in live_view.py stand (FM-48).
        for val in (11, 60, 128, 200, 255):
            self.assertAlmostEqual(S.strobe_hz(ch, val), 0.5 + (val - 11) / 244.0 * 19.5)

    def test_unlesbarer_wert(self):
        self.assertEqual(S.strobe_hz(_SHUTTER, None), 0.0)
        self.assertEqual(S.strobe_hz(_SHUTTER, "x"), 0.0)


class EineFunktionFuer2dUnd3dTest(unittest.TestCase):
    def test_live_view_benutzt_die_gemeinsame_funktion(self):
        from src.ui.views import live_view
        self.assertIs(live_view._strobe_hz, S.strobe_hz)

    def test_live_view_hat_keine_eigene_formel_mehr(self):
        with open(os.path.join(_REPO, "src", "ui", "views", "live_view.py"),
                  encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertNotIn("def _strobe_hz", quelle)
        self.assertNotIn("* 19.5", quelle)

    def test_payload_ruft_die_gemeinsame_funktion(self):
        attrs = {"intensity": 255, "shutter": 120}
        with patch("src.core.strobe.strobe_hz", return_value=7.0) as m:
            p = _build_fixture_payload(SimpleNamespace(fid=1), attrs, [_SHUTTER])
        self.assertTrue(m.called)
        self.assertEqual(p["strobe_hz"], 7.0)


class PayloadTest(unittest.TestCase):
    def _p(self, attrs, channels):
        return _build_fixture_payload(SimpleNamespace(fid=3), attrs, channels)

    def test_strobe_bereich_traegt_frequenz_und_volle_helligkeit(self):
        p = self._p({"shutter": 219, "color_r": 255}, [_SHUTTER])
        self.assertEqual(p["strobe_hz"], 20.0)
        # Helligkeit bleibt die OHNE Strobe — getaktet wird erst in der Szene.
        self.assertEqual(p["intensity"], 255)

    def test_dauerlicht_ist_null(self):
        for val in (15, 250):
            self.assertEqual(self._p({"shutter": val}, [_SHUTTER])["strobe_hz"], 0.0)

    def test_shutter_zu_ist_dunkel_und_ohne_strobe(self):
        p = self._p({"shutter": 0}, [_SHUTTER])
        self.assertEqual((p["intensity"], p["strobe_hz"]), (0, 0.0))

    def test_geraet_ohne_shutter_kanal(self):
        kan = [_ch("intensity", name="Dimmer"), _ch("color_r", name="Rot")]
        self.assertEqual(self._p({"intensity": 200, "color_r": 255}, kan)["strobe_hz"], 0.0)

    def test_ohne_kanalliste_kein_strobe(self):
        self.assertEqual(self._p({"intensity": 200, "shutter": 200}, None)["strobe_hz"], 0.0)

    def test_dimmer_und_farbe_bleiben_unberuehrt(self):
        kan = [_ch("intensity", name="Dimmer"), _SHUTTER]
        ohne = self._p({"intensity": 90, "shutter": 15, "color_r": 10, "color_g": 20,
                        "color_b": 30}, kan)
        mit = self._p({"intensity": 90, "shutter": 120, "color_r": 10, "color_g": 20,
                       "color_b": 30}, kan)
        for k in ("r", "g", "b", "intensity", "pan", "tilt"):
            self.assertEqual(ohne[k], mit[k], k)
        self.assertGreater(mit["strobe_hz"], 0)

    def test_mehrkopf_gemeinsamer_shutter_kein_feld_je_kopf(self):
        attrs = {"intensity": 255, "shutter": 219, "color_r": 255, "color_r#1": 255}
        p = self._p(attrs, [_SHUTTER])
        self.assertEqual(p["strobe_hz"], 20.0)
        self.assertEqual(len(p["heads"]), 2)
        for h in p["heads"]:
            self.assertNotIn("strobe_hz", h)

    def test_mehrkopf_eigener_shutter_je_kopf(self):
        s2 = _ch(ranges=list(_SHUTTER.ranges))
        attrs = {"intensity": 255, "shutter": 15, "shutter#1": 219,
                 "color_r": 255, "color_r#1": 255}
        p = self._p(attrs, [_SHUTTER, s2])
        self.assertEqual([h["strobe_hz"] for h in p["heads"]], [0.0, 20.0])
        # Das Geraet als Ganzes: die hoechste Frequenz (so rechnet auch 2D).
        self.assertEqual(p["strobe_hz"], 20.0)

    def test_frequenz_je_kopf_aus_attrs(self):
        s2 = _ch(ranges=list(_SHUTTER.ranges))
        attrs = {"shutter": 219, "shutter#1": 20}
        self.assertAlmostEqual(S.strobe_hz_aus_attrs(attrs, [_SHUTTER, s2], ""), 20.0)
        self.assertAlmostEqual(S.strobe_hz_aus_attrs(attrs, [_SHUTTER, s2], "#1"), 0.5)
        self.assertAlmostEqual(S.strobe_hz_aus_attrs(attrs, [_SHUTTER, s2]), 20.0)
        self.assertEqual(S.strobe_hz_aus_attrs(attrs, [_SHUTTER, s2], "#2"), 0.0)
        self.assertTrue(S.hat_kopf_shutter([_SHUTTER, s2]))
        self.assertFalse(S.hat_kopf_shutter([_SHUTTER]))


class PraeferenzTest(unittest.TestCase):
    def _mit_prefs(self, prefs):
        return patch("src.ui.views.programmer_view._load_prefs", return_value=prefs)

    def test_vorgabe_ist_blitzen(self):
        with self._mit_prefs({}):
            self.assertEqual(P.strobe_mode_pref(), "flash")
        self.assertEqual(P.DEFAULT_MODE, "flash")

    def test_wert_wird_gelesen(self):
        for m in P.MODES:
            with self._mit_prefs({P.PREF_KEY: m}):
                self.assertEqual(P.strobe_mode_pref(), m)

    def test_unsinn_und_kaputte_prefs_fallen_auf_die_vorgabe(self):
        for wert in ("blitz", None, 3, ""):
            with self._mit_prefs({P.PREF_KEY: wert}):
                self.assertEqual(P.strobe_mode_pref(), "flash", wert)
        with patch("src.ui.views.programmer_view._load_prefs", side_effect=OSError("x")):
            self.assertEqual(P.strobe_mode_pref(), "flash")

    def test_speichern_schreibt_den_schluessel(self):
        with patch("src.ui.views.programmer_view._save_prefs") as m:
            self.assertEqual(P.save_strobe_mode("soft"), "soft")
            self.assertEqual(P.save_strobe_mode("???"), "flash")
        self.assertEqual([c.args[0] for c in m.call_args_list],
                         [{"viz_strobe_mode": "soft"}, {"viz_strobe_mode": "flash"}])

    def test_speichern_und_lesen_ueber_die_echte_ablage(self):
        """Ueber die Prefs-Datei des Testlaufs (conftest lenkt den Datenort um)."""
        from src.ui.views import programmer_view as PV
        vorher = PV._load_prefs().get(P.PREF_KEY)
        try:
            P.save_strobe_mode("off")
            self.assertEqual(P.strobe_mode_pref(), "off")
        finally:
            PV._save_prefs({P.PREF_KEY: vorher if vorher else P.DEFAULT_MODE})

    def test_fenster_gibt_die_auswahl_an_die_szene(self):
        import src.ui.visualizer.visualizer_window as VW
        combo = SimpleNamespace(currentData=lambda: "soft")
        self.assertEqual(P.strobe_mode_value(SimpleNamespace(_combo_strobe=combo)), "soft")
        # Stub ohne das Feld (Bestandstests): die gespeicherte Einstellung.
        with self._mit_prefs({P.PREF_KEY: "off"}):
            self.assertEqual(P.strobe_mode_value(SimpleNamespace()), "off")
        with open(VW.__file__, encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertIn('"strobeMode":      strobe_mode_value(self)', quelle)
        self.assertIn("Strobe im 3D zeigen:", quelle)
        self.assertIn("strobe_prefs.WARNHINWEIS", quelle)

    def test_eingebettete_ansicht_schickt_dieselbe_einstellung(self):
        with open(os.path.join(_REPO, "src", "ui", "visualizer", "visualizer_view.py"),
                  encoding="utf-8") as fh:
            self.assertIn('"strobeMode":     strobe_mode_pref()', fh.read())

    def test_stufen_und_warnhinweis(self):
        self.assertEqual([w for w, _t in P.MODE_LABELS], list(P.MODES))
        texte = dict(P.MODE_LABELS)
        self.assertTrue(texte["flash"].startswith("Blitzen"))
        self.assertTrue(texte["soft"].startswith("Gedämpft"))
        self.assertTrue(texte["off"].startswith("Aus"))
        self.assertIn("photosensitiver Epilepsie", P.WARNHINWEIS)


# ── JS: die Blitz-Funktion unter Node ────────────────────────────────────────

def _node_verfuegbar() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:                       # pragma: no cover
        return False


_TREIBER = """
import * as S from './strobe.mjs';
const aus = {};
aus.konst = { modi: S.STROBE_MODI, vorgabe: S.STROBE_MODUS_VORGABE, tast: S.STROBE_TAST,
              deckel: S.STROBE_DECKEL_HZ, bilder: S.BILDER_JE_BLITZ, weichHz: S.WEICH_MAX_HZ, weichMin: S.WEICH_MIN };
// Anteil „an" und Zahl der Blitze ueber `dauer` ms bei Abtastung alle `schritt` ms.
function lauf(fn, dauer, schritt, start = 0) {
  let an = 0, n = 0, blitze = 0, vor = false, laengsteAus = 0, ausLauf = 0;
  for (let t = start; t < start + dauer; t += schritt) {
    const a = fn(t);
    n += 1;
    if (a) { an += 1; ausLauf = 0; if (!vor) blitze += 1; }
    else { ausLauf += 1; if (ausLauf > laengsteAus) laengsteAus = ausLauf; }
    vor = a;
  }
  return { anteil: an / n, blitze, laengsteAus };
}
aus.fein5 = lauf(t => S.strobeAn(t, 5), 10000, 0.5);
aus.fein20 = lauf(t => S.strobeAn(t, 20), 10000, 0.5);
aus.fein20ohneDeckel = lauf(t => S.strobeAn(t, 20, 0.25, 100), 10000, 0.5);
aus.dauerlicht = [S.strobeAn(0, 0), S.strobeAn(123, 0), S.strobeAn(5, -1), S.strobeAn(77, NaN)];
aus.eigenerTast = lauf(t => S.strobeAn(t, 4, 0.5), 10000, 0.5);
aus.anzeige = {
  normal: S.strobeAnzeigeHz(5, 60), deckel: S.strobeAnzeigeHz(20, 60),
  langsam: S.strobeAnzeigeHz(20, 15), null: S.strobeAnzeigeHz(0, 60),
  sehrLangsam: S.strobeAnzeigeHz(20, 8),
};
aus.tast = { normal: S.strobeTast(5, 60), langsam: S.strobeTast(5, 15), grenze: S.strobeTast(4, 8) };
// Bildraster: 60, 30 und 15 Bilder/s, Strobe 20 Hz gemeldet. Start bewusst krumm.
aus.raster = {};
for (const fps of [60, 30, 15]) {
  aus.raster[fps] = lauf(t => S.strobeFaktor(t, 20, 'flash', fps) > 0, 10000, 1000 / fps, 3.7);
}
aus.faktor = {
  aus: [S.strobeFaktor(10, 20, 'off', 60), S.strobeFaktor(60, 20, 'off', 60)],
  keinStrobe: [S.strobeFaktor(10, 0, 'flash', 60), S.strobeFaktor(60, 0, 'soft', 60)],
  blitzWerte: [...new Set(Array.from({length: 2000}, (_, i) => S.strobeFaktor(i, 9, 'flash', 60)))].sort(),
};
const weich = Array.from({length: 4000}, (_, i) => S.strobeFaktor(i, 20, 'soft', 60));
let wechsel = 0, groessterSchritt = 0, maxima = 0;
for (let i = 1; i < weich.length; i++) {
  const d = Math.abs(weich[i] - weich[i - 1]);
  if (d > 0) wechsel += 1;
  if (d > groessterSchritt) groessterSchritt = d;
}
for (let i = 1; i < weich.length; i++) if (weich[i] === 1 && weich[i - 1] < 1) maxima += 1;
aus.weich = { min: Math.min(...weich), max: Math.max(...weich), wechsel, groessterSchritt, maxima };
aus.modus = [S.strobeModus('soft'), S.strobeModus('x'), S.strobeModus(undefined), S.strobeModus('off')];
let fps = 60;
for (let i = 0; i < 200; i++) fps = S.fpsNachfuehren(fps, 50);
aus.fps = { nach20: fps, pause: S.fpsNachfuehren(60, 5000), null: S.fpsNachfuehren(60, 0) };
// Phase haengt an der Uhr, nicht am Aufruf: dieselbe Zeit -> dieselbe Antwort.
aus.phase = [S.strobeAn(1234.5, 5), S.strobeAn(1234.5, 5), S.strobeAn(1234.5 + 200, 5)];
console.log(JSON.stringify(aus));
"""

_ERGEBNIS = None


def _js():
    global _ERGEBNIS
    if _ERGEBNIS is None:
        with open(_MODUL, encoding="utf-8") as fh:
            quelle = fh.read()
        with tempfile.TemporaryDirectory() as verz:
            with open(os.path.join(verz, "strobe.mjs"), "w", encoding="utf-8") as fh:
                fh.write(quelle)
            with open(os.path.join(verz, "treiber.mjs"), "w", encoding="utf-8") as fh:
                fh.write(_TREIBER)
            out = subprocess.run(["node", os.path.join(verz, "treiber.mjs")],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=60)
        if out.returncode != 0:
            raise AssertionError(out.stderr)
        _ERGEBNIS = json.loads(out.stdout)
    return _ERGEBNIS


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class BlitzFunktionTest(unittest.TestCase):
    def test_konstanten_gleich_python(self):
        k = _js()["konst"]
        self.assertEqual(tuple(k["modi"]), P.MODES)
        self.assertEqual(k["vorgabe"], P.DEFAULT_MODE)
        self.assertEqual(k["tast"], P.DUTY)
        self.assertEqual(k["deckel"], P.CAP_HZ)
        self.assertEqual(k["bilder"], P.FRAMES_PER_FLASH)
        self.assertEqual(k["weichHz"], P.SOFT_MAX_HZ)
        self.assertEqual(k["weichMin"], P.SOFT_MIN)

    def test_tastverhaeltnis_zwischen_20_und_30_prozent(self):
        self.assertTrue(0.20 <= P.DUTY <= 0.30)
        e = _js()["fein5"]
        self.assertAlmostEqual(e["anteil"], P.DUTY, delta=0.005)
        self.assertEqual(e["blitze"], 50)               # 5 Hz ueber 10 s

    def test_deckel_begrenzt_die_dargestellte_frequenz(self):
        e = _js()
        self.assertEqual(e["fein20"]["blitze"], P.CAP_HZ * 10)
        self.assertAlmostEqual(e["fein20"]["anteil"], P.DUTY, delta=0.005)
        self.assertEqual(e["fein20ohneDeckel"]["blitze"], 200)
        self.assertTrue(10 <= P.CAP_HZ <= 12)

    def test_null_oder_unsinn_ist_dauerlicht(self):
        self.assertEqual(_js()["dauerlicht"], [True, True, True, True])

    def test_eigenes_tastverhaeltnis(self):
        self.assertAlmostEqual(_js()["eigenerTast"]["anteil"], 0.5, delta=0.005)

    def test_anzeigefrequenz_hoechstens_ein_drittel_der_bildrate(self):
        a = _js()["anzeige"]
        self.assertEqual(a["normal"], 5)
        self.assertEqual(a["deckel"], P.CAP_HZ)
        self.assertEqual(a["langsam"], 5)               # 15 Bilder/s
        self.assertAlmostEqual(a["sehrLangsam"], 8 / 3)
        self.assertGreaterEqual(P.FRAMES_PER_FLASH, 2)  # nie ueber der halben Bildrate
        self.assertEqual(a["null"], 0)

    def test_blitz_dauert_mindestens_ein_bild(self):
        t = _js()["tast"]
        self.assertEqual(t["normal"], P.DUTY)           # 60 Bilder/s: 25 % reichen
        self.assertAlmostEqual(t["langsam"], 1 / 3)     # 5 Hz bei 15 Bildern/s
        self.assertAlmostEqual(t["grenze"], 1 / 3)      # nie mehr als ein Drittel

    def test_bildraster_trifft_jeden_blitz_und_jede_pause(self):
        """Ehrlich bei niedriger Bildrate: im Raster der Bilder gezaehlt entsteht
        genau die begrenzte Frequenz — kein Blitz geht verloren, keiner
        verschmilzt mit dem naechsten (das waere die Schwebung)."""
        r = _js()["raster"]
        erwartet = {"60": 12.0, "30": 10.0, "15": 5.0}
        for fps, hz in erwartet.items():
            with self.subTest(fps=fps):
                self.assertAlmostEqual(r[fps]["blitze"] / 10.0, hz, delta=0.15)
                # Im Bildraster ist ein Blitz ein oder zwei Bilder lang (60 Bilder/s,
                # 12 Hz: Periode genau 5 Bilder, je nach Phasenlage 1 oder 2 an).
                self.assertTrue(0.2 <= r[fps]["anteil"] <= 0.41, r[fps])
                # Laengste Dunkelphase in Bildern: nie mehr als eine Periode.
                self.assertLessEqual(r[fps]["laengsteAus"], round(int(fps) / hz), r[fps])

    def test_faktor_blitzen_kennt_nur_an_und_aus(self):
        f = _js()["faktor"]
        self.assertEqual(f["blitzWerte"], [0, 1])
        self.assertEqual(f["aus"], [1, 1])
        self.assertEqual(f["keinStrobe"], [1, 1])

    def test_gedaempft_pulsiert_langsam_und_flach(self):
        w = _js()["weich"]
        self.assertEqual(w["max"], 1)
        self.assertAlmostEqual(w["min"], P.SOFT_MIN)
        self.assertGreaterEqual(w["min"], 0.5)          # nie dunkel
        # 20 Hz gemeldet, gezeigt hoechstens 2 Hz: 4 s -> 8 Wellen.
        self.assertEqual(w["maxima"], P.SOFT_MAX_HZ * 4)
        self.assertLessEqual(P.SOFT_MAX_HZ, 3)          # unter drei Wechseln je Sekunde
        # Kleine Stufen (kein Sprung), und nur wenige Neuberechnungen je Welle.
        self.assertLess(w["groessterSchritt"], 0.06)
        self.assertLessEqual(w["wechsel"], 8 * 2 * 8 + 2)

    def test_modus_normalisieren(self):
        self.assertEqual(_js()["modus"], ["soft", "flash", "flash", "off"])

    def test_bildrate_wird_nachgefuehrt(self):
        f = _js()["fps"]
        self.assertAlmostEqual(f["nach20"], 20, delta=0.1)
        self.assertEqual(f["pause"], 60)                # Tab im Hintergrund zaehlt nicht
        self.assertEqual(f["null"], 60)

    def test_phase_haengt_an_der_uhr(self):
        a, b, c = _js()["phase"]
        self.assertEqual(a, b)
        self.assertEqual(a, c)                          # eine ganze Periode spaeter


class VerdrahtungTest(unittest.TestCase):
    """Textpruefung der Quelle — die Seite selbst faehrt der Szenen-Test."""

    def _lies(self, *teile):
        with open(os.path.join(_SCENE, *teile), encoding="utf-8") as fh:
            return fh.read()

    def test_modul_ist_rein(self):
        quelle = self._lies("fixtures", "strobe.js")
        self.assertIsNone(re.search(r"^\s*import\s", quelle, re.M))
        for wort in ("performance.now", "Date.now", "window.", "document."):
            self.assertNotIn(wort, quelle.split('"use strict"')[1])

    def test_takt_laeuft_je_bild_vor_der_glaettung(self):
        app = self._lies("app.js")
        self.assertLess(app.index("  tickStrobe();"), app.index("  tickBewegungGlaettung();"))
        self.assertNotIn("registerLiveAnimation(strobe", app)   # kein Dauer-Rendern

    def test_update_merkt_den_stand_ohne_strobe(self):
        fx = self._lies("fixtures", "fixtures.js")
        self.assertIn("f._dmx = dmx;", fx)
        self.assertIn("extra.strobe_hz", fx)
        # Nur die Helligkeit wird skaliert — keine Farbe, kein Pan/Tilt.
        m = re.search(r"function _mitStrobe\(dmx, fak\) \{(.*?)\n\}", fx, re.S)
        self.assertIsNotNone(m)
        self.assertIn("intNorm: dmx.intNorm * fak", m.group(1))
        for wort in ("color", "pan", "tilt", "heads", " r:", " g:", " b:"):
            self.assertNotIn(wort, m.group(1).split("return")[1])

    def test_keine_erzwungene_schatten_neuberechnung(self):
        fx = self._lies("fixtures", "fixtures.js")
        a = fx.index("// ── VIZ-104: Strobe im Bildtakt")
        b = fx.index("// ── Spaet-Bindung")
        self.assertNotIn("requestShadowUpdate(", fx[a:b])
        self.assertNotIn("needsUpdate", fx[a:b])

    def test_einstellung_kommt_in_der_szene_an(self):
        br = self._lies("bridge", "bridge.js")
        self.assertIn("s.strobeMode", br)
        self.assertIn("strobeNeuBewerten()", br)
        self.assertIn("strobeMode: 'flash'", self._lies("state.js"))


class AnleitungTest(unittest.TestCase):
    def test_abschnitt_strobe(self):
        with open(_ANLEITUNG, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("## Strobe im 3D", text)
        a = text.index("## Strobe im 3D")
        ende = text.find("\n## ", a + 5)
        abschnitt = text[a:ende if ende > 0 else len(text)]
        for wort in ("Strobe im 3D zeigen", "Blitzen", "Gedämpft", "Dauerlicht",
                     f"{P.CAP_HZ} Blitze", "ein Drittel der Bildrate",
                     "photosensitiver Epilepsie", "DMX-Ausgabe"):
            self.assertIn(wort, abschnitt, wort)


if __name__ == "__main__":
    unittest.main()


class EinstellungenReiterTest(unittest.TestCase):
    """Der ECHTE Reiter „Einstellungen" (ohne Seite, ohne Fenster auf dem
    Bildschirm): die Auswahl steht bei der Render-Qualitaet, zeigt die
    gespeicherte Einstellung, und ein Wechsel wird gemerkt und an die Szene
    gegeben — ohne die Szene neu zu laden."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def _fenster(self, prefs):
        import src.ui.visualizer.visualizer_window as VW
        from unittest.mock import MagicMock

        class _Fenster(VW.VisualizerWindow):
            def __init__(self):                       # ohne QWebEngineView
                VW.QMainWindow.__init__(self)

        with patch("src.ui.views.programmer_view._load_prefs", return_value=prefs):
            win = _Fenster()
            win._state = SimpleNamespace(show_fixture_labels=True)
            win._bridge = MagicMock()
            win._on_settings_changed = MagicMock()
            win._on_reload_scene = MagicMock()
            tab = VW.VisualizerWindow._build_settings_tab(win)
        self.addCleanup(win.deleteLater)
        self.addCleanup(tab.deleteLater)
        return win, tab

    def test_auswahl_steht_bei_der_render_qualitaet(self):
        from PySide6.QtWidgets import QGroupBox
        win, tab = self._fenster({})
        gruppe = [g for g in tab.findChildren(QGroupBox) if g.title() == "Render-Qualität"]
        self.assertEqual(len(gruppe), 1)
        self.assertTrue(gruppe[0].isAncestorOf(win._combo_strobe))
        self.assertTrue(gruppe[0].isAncestorOf(win._lbl_strobe_warnung))
        combo = win._combo_strobe
        self.assertEqual([combo.itemData(i) for i in range(combo.count())], list(P.MODES))
        self.assertEqual([combo.itemText(i) for i in range(combo.count())],
                         [t for _w, t in P.MODE_LABELS])
        self.assertEqual(combo.currentData(), "flash")             # Vorgabe
        self.assertIn("photosensitiver Epilepsie", win._lbl_strobe_warnung.text())
        self.assertIn("photosensitiver Epilepsie", combo.toolTip())

    def test_gespeicherte_einstellung_wird_gezeigt(self):
        win, _tab = self._fenster({P.PREF_KEY: "soft"})
        self.assertEqual(win._combo_strobe.currentData(), "soft")

    def test_wechsel_wird_gemerkt_und_an_die_szene_gegeben(self):
        import src.ui.visualizer.visualizer_window as VW
        win, _tab = self._fenster({})
        with patch("src.ui.views.programmer_view._save_prefs") as speichern:
            win._combo_strobe.setCurrentIndex(win._combo_strobe.findData("off"))
        speichern.assert_called_once_with({"viz_strobe_mode": "off"})
        win._on_settings_changed.assert_called_once()
        win._on_reload_scene.assert_not_called()                   # kein Neuladen
        self.assertEqual(VW.VisualizerWindow._collect_settings(win)["strobeMode"], "off")
