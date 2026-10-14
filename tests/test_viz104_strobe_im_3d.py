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
  Periode und Blitzlaenge in ganzen Bildern, Folge exakt periodisch, Deckel,
  traege Bildrate, gedaempfter Modus — und dieselbe Rechnung fuer die
  2D-Live-Ansicht (``core.strobe.blitz_bilder``);
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

    def test_shutter_ohne_bereiche_blitzt_nicht(self):
        """Vorsichtige Regel (Nacharbeit 2026-10-12): ein reiner Shutter-Kanal
        ohne Bereichsangaben blitzt bei KEINEM Wert — 255 heisst dort meist
        „offen". Bis dahin galt pauschal „> 10 = Strobe"."""
        for name in ("Shutter", "Verschluss", ""):
            ch = _ch(attribute="shutter", name=name)
            self.assertFalse(S.ist_ausdruecklicher_strobe_kanal(ch), name)
            for val in (0, 10, 11, 128, 239, 255):
                self.assertEqual(S.strobe_hz(ch, val), 0.0, (name, val))

    def test_strobe_kanal_ohne_bereiche_blitzt(self):
        for ch in (_ch(attribute="strobe", name="Strobe"),
                   _ch(attribute="strobe", name="Kanal 7"),          # Typ genuegt
                   _ch(attribute="shutter", name="Shutter/Strobe"),  # Name genuegt
                   _ch(attribute="shutter", name="Flash"),
                   _ch(attribute="shutter", name="Frequenz"),        # „Strobe 2ch"
                   _ch(attribute="shutter", name="Blitz")):
            self.assertTrue(S.ist_ausdruecklicher_strobe_kanal(ch), ch.name)
            self.assertEqual(S.strobe_hz(ch, 0), 0.0)
            self.assertGreater(S.strobe_hz(ch, 200), 0.0, ch.name)

    def test_mit_bereichen_zaehlt_nur_der_bereich_auch_beim_strobe_kanal(self):
        """„Offen" am oberen Ende (Wert 255) blitzt nicht — auch wenn der Kanal
        „Strobe" heisst; und ein Wert im Strobe-Bereich blitzt auch dann, wenn
        der Kanal nur „Shutter" heisst."""
        ber = [_rng(0, 4, "Zu", "closed"), _rng(5, 250, "Strobe langsam -> schnell", "strobe"),
               _rng(251, 255, "Offen", "open")]
        for ch in (_ch(attribute="strobe", name="Strobe", ranges=ber),
                   _ch(attribute="shutter", name="Shutter", ranges=ber)):
            self.assertEqual(S.strobe_hz(ch, 255), 0.0)
            self.assertEqual(S.strobe_hz(ch, 251), 0.0)
            self.assertEqual(S.strobe_hz(ch, 0), 0.0)
            self.assertAlmostEqual(S.strobe_hz(ch, 5), 0.5)
            self.assertAlmostEqual(S.strobe_hz(ch, 250), 20.0)

    def test_2d_ansicht_nutzt_dieselbe_vorsichtige_regel(self):
        from src.ui.views import live_view
        self.assertEqual(live_view._strobe_hz(_ch(attribute="shutter", name="Shutter"), 255), 0.0)
        self.assertGreater(live_view._strobe_hz(_ch(attribute="strobe", name="Strobe"), 255), 0.0)

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

    def test_nur_kopf_1_oder_nur_kopf_2_oder_verschieden_schnell(self):
        s2 = _ch(ranges=list(_SHUTTER.ranges))
        kan = [_SHUTTER, s2]

        def koepfe(a, b):
            p = self._p({"intensity": 255, "shutter": a, "shutter#1": b,
                         "color_r": 255, "color_r#1": 255}, kan)
            return [h["strobe_hz"] for h in p["heads"]]
        self.assertEqual(koepfe(219, 15), [20.0, 0.0])
        self.assertEqual(koepfe(15, 219), [0.0, 20.0])
        k = koepfe(20, 219)
        self.assertEqual(k, [0.5, 20.0])

    def test_gemeinsamer_strobe_neben_shutter_je_kopf_gilt_fuer_alle_koepfe(self):
        s2 = _ch(ranges=list(_SHUTTER.ranges))
        gemeinsam = _ch(attribute="strobe", name="Strobe")      # ohne Bereiche
        kan = [_SHUTTER, s2, gemeinsam]
        attrs = {"shutter": 15, "shutter#1": 15, "strobe": 255}
        for sfx in ("", "#1"):
            self.assertAlmostEqual(S.strobe_hz_aus_attrs(attrs, kan, sfx), 20.0)
        attrs["strobe"] = 0
        for sfx in ("", "#1"):
            self.assertEqual(S.strobe_hz_aus_attrs(attrs, kan, sfx), 0.0)


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
              deckel: S.STROBE_DECKEL_HZ, bilder: S.BILDER_JE_BLITZ, weichHz: S.WEICH_MAX_HZ,
              weichMin: S.WEICH_MIN, weichStufen: S.WEICH_STUFEN, traegheit: S.TAKT_TRAEGHEIT };
const RATEN = [15, 24, 25, 30, 34, 38, 42, 45, 52, 60, 75, 120, 144];
const FREQ = [0.5, 1, 2, 3.3, 5, 8, 10, 12, 20, 25];
// Folge von An/Aus im Bildraster: exakt periodisch, EIN Blitz je Periode.
aus.folgen = [];
for (const fps of RATEN) for (const hz of FREQ) {
  const b = S.strobeBilder(hz, fps);
  const n = b.periode * 12;
  const start = 7;                               // bewusst nicht bei 0
  const folge = Array.from({length: n + b.periode}, (_, i) => S.strobeFaktor(start + i, hz, 'flash', fps));
  let periodisch = true, werte = new Set(folge);
  for (let i = 0; i < n; i++) if (folge[i] !== folge[i + b.periode]) periodisch = false;
  let blitze = 0, an = 0;
  for (let i = 0; i < n; i++) {
    if (folge[i] > 0) an += 1;
    if (folge[i] > 0 && folge[(i + n - 1) % n] === 0) blitze += 1;
  }
  aus.folgen.push({ fps, hz, periode: b.periode, an: b.an, periodisch, blitze, anGezaehlt: an,
                    perioden: 12, werte: [...werte].sort(), anzeige: S.strobeAnzeigeHz(hz, fps) });
}
aus.muster = {};
for (const fps of [30, 40, 60]) {
  aus.muster[fps] = Array.from({length: 24}, (_, i) => S.strobeAn(i, 20, fps) ? '#' : '.').join('');
}
aus.dauerlicht = [S.strobeAn(0, 0), S.strobeAn(123, 0), S.strobeAn(5, -1), S.strobeAn(77, NaN),
                  S.strobeBilder(0, 60).periode, S.strobeAnzeigeHz(0, 60)];
aus.negativ = [S.strobeAn(-1, 20, 30), S.strobeAn(-3, 20, 30), S.strobeAn(-2, 20, 30)];
// Gleiche Frequenz -> gleiche Folge (ein Zaehler fuer alle); andere Frequenz -> andere Periode.
aus.gleich = Array.from({length: 60}, (_, i) => S.strobeAn(i, 5, 60) === S.strobeAn(i, 5.0, 60)).every(Boolean);
aus.verschieden = [S.strobeBilder(2, 60).periode, S.strobeBilder(5, 60).periode];
aus.faktor = {
  aus: [S.strobeFaktor(10, 20, 'off', 60), S.strobeFaktor(60, 20, 'off', 60)],
  keinStrobe: [S.strobeFaktor(10, 0, 'flash', 60), S.strobeFaktor(60, 0, 'soft', 60)],
};
aus.weich = {};
for (const fps of [15, 30, 40, 60]) {
  const p = S.weichBilder(20, fps);
  const w = Array.from({length: p * 6 + 1}, (_, i) => S.strobeFaktor(3 + i, 20, 'soft', fps));
  let wechsel = 0, groessterSchritt = 0, periodisch = true;
  for (let i = 1; i < w.length; i++) {
    const d = Math.abs(w[i] - w[i - 1]);
    if (d > 0) wechsel += 1;
    if (d > groessterSchritt) groessterSchritt = d;
  }
  for (let i = 0; i + p < w.length; i++) if (w[i] !== w[i + p]) periodisch = false;
  aus.weich[fps] = { periode: p, hz: fps / p, min: Math.min(...w), max: Math.max(...w),
                     wechselJeWelle: wechsel / 6, groessterSchritt, periodisch,
                     stufen: new Set(w.map(v => v.toFixed(4))).size };
}
aus.weichLangsam = S.weichBilder(0.5, 60);
aus.modus = [S.strobeModus('soft'), S.strobeModus('x'), S.strobeModus(undefined), S.strobeModus('off')];
// Bildrate: gemittelt wird der ABSTAND. Wechseln 33- und 17-ms-Bilder (zwei
// gezeichnete, zwei uebersprungene), sind das 40 Bilder/s — nicht 45.
let fps = 60;
for (let i = 0; i < 200; i++) fps = S.fpsNachfuehren(fps, 50);
let gemischt = 60;
for (let i = 0; i < 400; i++) gemischt = S.fpsNachfuehren(gemischt, (i % 4 < 2) ? 33.3 : 16.7);
aus.fps = { nach20: fps, gemischt, pause: S.fpsNachfuehren(60, 5000), null: S.fpsNachfuehren(60, 0) };
// Traeger Takt: eine um +-5 % schwankende Messung schaltet die Periode nie um.
let takt = 40, wechselTakt = 0;
for (let i = 0; i < 500; i++) {
  const neu = S.taktFps(takt, 40 + 2 * Math.sin(i * 1.7));
  if (neu !== takt) wechselTakt += 1;
  takt = neu;
}
aus.takt = { ruhig: wechselTakt, bleibt: S.taktFps(60, 55), folgt: S.taktFps(60, 40),
             start: S.taktFps(0, 37), unsinn: S.taktFps(60, NaN) };
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
    """Die Blitz-Rechnung der Szene, im BILDRASTER (Sichtprobe 2026-10-12:
    die Abtastung einer Uhr-Phase gab Doppelblitze mit ungleichen Luecken)."""

    def test_konstanten_gleich_python(self):
        k = _js()["konst"]
        self.assertEqual(tuple(k["modi"]), P.MODES)
        self.assertEqual(k["vorgabe"], P.DEFAULT_MODE)
        self.assertEqual(k["tast"], P.DUTY)
        self.assertEqual(k["deckel"], P.CAP_HZ)
        self.assertEqual(k["bilder"], P.FRAMES_PER_FLASH)
        self.assertEqual(k["weichHz"], P.SOFT_MAX_HZ)
        self.assertEqual(k["weichMin"], P.SOFT_MIN)
        # ... und gleich der Rechnung der 2D-Ansicht.
        self.assertEqual((k["tast"], k["deckel"], k["bilder"]),
                         (S.TAST, S.DECKEL_HZ, S.BILDER_JE_BLITZ))

    def test_folge_ist_exakt_periodisch_mit_einem_blitz_je_periode(self):
        folgen = _js()["folgen"]
        self.assertGreater(len(folgen), 100)
        for f in folgen:
            with self.subTest(fps=f["fps"], hz=f["hz"]):
                self.assertTrue(f["periodisch"], f)
                self.assertEqual(f["werte"], [0, 1])
                self.assertEqual(f["blitze"], f["perioden"], "ein Blitz je Periode")
                self.assertEqual(f["anGezaehlt"], f["an"] * f["perioden"])

    def test_periode_und_blitzlaenge_in_ganzen_bildern(self):
        for f in _js()["folgen"]:
            with self.subTest(fps=f["fps"], hz=f["hz"]):
                ziel = min(f["hz"], P.CAP_HZ)
                self.assertEqual(f["periode"],
                                 max(int(f["fps"] / ziel + 0.5), P.FRAMES_PER_FLASH))
                self.assertEqual(f["an"], max(1, int(f["periode"] * P.DUTY + 0.5)))
                self.assertGreaterEqual(f["periode"] - f["an"], 2, "mindestens zwei Bilder dunkel")
                # Gleiche Rechnung wie die 2D-Ansicht (src/core/strobe.py).
                self.assertEqual(S.blitz_bilder(f["hz"], f["fps"]), (f["periode"], f["an"]))

    def test_muster_bei_30_40_und_60_bildern(self):
        m = _js()["muster"]
        self.assertEqual(m["30"], "#..#..#..#..#..#..#..#..")
        self.assertEqual(m["40"], "#...#...#...#...#...#...")
        self.assertEqual(m["60"], "##....##....##....##....")

    def test_deckel_wird_auf_30_bis_60_bildern_erreicht(self):
        """Der Deckel ist so gewaehlt, dass er dort ankommt, wo gemessen wurde
        (34-52 Bilder/s beim Blitzen): drei Bilder je Blitz * 10 Hz = 30."""
        self.assertEqual(P.CAP_HZ, 10)
        self.assertEqual(P.CAP_HZ * P.FRAMES_PER_FLASH, 30)
        schnell = [f for f in _js()["folgen"] if f["hz"] >= P.CAP_HZ]
        for f in schnell:
            with self.subTest(fps=f["fps"], hz=f["hz"]):
                if f["fps"] in (30, 60, 120):
                    self.assertAlmostEqual(f["anzeige"], P.CAP_HZ)
                if 30 <= f["fps"] <= 144:
                    # Zwischen den glatten Bildraten: eine halbe Bildlaenge je Periode.
                    self.assertTrue(8.5 <= f["anzeige"] <= 11.7, f)
                if f["fps"] < 30:
                    self.assertAlmostEqual(f["anzeige"], f["fps"] / 3)   # ehrlich weniger
        # Gemeldete Frequenz unter dem Deckel: sie wird gezeigt (auf ganze Bilder gerundet).
        for f in _js()["folgen"]:
            if f["hz"] <= 5 and f["fps"] >= 30:
                self.assertAlmostEqual(f["anzeige"], f["hz"], delta=f["hz"] * 0.1, msg=f)

    def test_tastverhaeltnis_kurzer_blitz(self):
        self.assertTrue(0.20 <= P.DUTY <= 0.30)
        for f in _js()["folgen"]:
            anteil = f["an"] / f["periode"]
            self.assertTrue(0.16 <= anteil <= 0.34, f)

    def test_null_oder_unsinn_ist_dauerlicht(self):
        self.assertEqual(_js()["dauerlicht"], [True, True, True, True, 0, 0])

    def test_negativer_bildzaehler(self):
        self.assertEqual(_js()["negativ"], [False, True, False])

    def test_gleiche_frequenz_gleiche_phase_andere_frequenz_eigene_periode(self):
        e = _js()
        self.assertTrue(e["gleich"])
        self.assertEqual(e["verschieden"], [30, 12])

    def test_faktor_aus_und_kein_strobe(self):
        f = _js()["faktor"]
        self.assertEqual(f["aus"], [1, 1])
        self.assertEqual(f["keinStrobe"], [1, 1])

    def test_gedaempft_pulsiert_langsam_flach_und_in_wenigen_schritten(self):
        for fps, w in _js()["weich"].items():
            with self.subTest(fps=fps):
                self.assertTrue(w["periodisch"])
                self.assertEqual(w["max"], 1)
                self.assertAlmostEqual(w["min"], P.SOFT_MIN)
                self.assertGreaterEqual(w["min"], 0.5)          # nie dunkel
                self.assertLessEqual(w["hz"], P.SOFT_MAX_HZ + 1e-9)
                self.assertGreaterEqual(w["hz"], 1.4)
                self.assertEqual(w["periode"] % 8, 0, "gleich lange Schritte")
                # Acht Aenderungen je Welle — nicht eine je Bild (Sichtprobe: der
                # gedaempfte Modus war der teuerste, bis zu 32 Aenderungen/s).
                self.assertEqual(w["wechselJeWelle"], 8)
                self.assertEqual(w["stufen"], 5)
                self.assertLess(w["groessterSchritt"], 0.17)
        self.assertLessEqual(P.SOFT_MAX_HZ, 3)                   # unter drei Wechseln je Sekunde
        self.assertEqual(_js()["weichLangsam"], 120)             # 0,5 Hz bleibt 0,5 Hz

    def test_modus_normalisieren(self):
        self.assertEqual(_js()["modus"], ["soft", "flash", "flash", "off"])

    def test_bildrate_aus_dem_mittleren_bildabstand(self):
        f = _js()["fps"]
        self.assertAlmostEqual(f["nach20"], 20, delta=0.1)
        self.assertAlmostEqual(f["gemischt"], 40, delta=1.5)
        self.assertEqual(f["pause"], 60)                # Tab im Hintergrund zaehlt nicht
        self.assertEqual(f["null"], 60)

    def test_takt_ist_traege(self):
        t = _js()["takt"]
        self.assertEqual(t["ruhig"], 0, "eine schwankende Messung schaltete die Periode um")
        self.assertEqual(t["bleibt"], 60)
        self.assertEqual(t["folgt"], 40)
        self.assertEqual(t["start"], 37)
        self.assertEqual(t["unsinn"], 60)


class BildrechnungPythonTest(unittest.TestCase):
    """Dieselbe Rechnung fuer die 2D-Live-Ansicht (``core.strobe.blitz_bilder``)."""

    def test_periode_und_an(self):
        self.assertEqual(S.blitz_bilder(20, 10), (3, 1))      # 2D: 10 Bilder/s
        self.assertEqual(S.blitz_bilder(5, 10), (3, 1))
        self.assertEqual(S.blitz_bilder(2, 10), (5, 1))
        self.assertEqual(S.blitz_bilder(1, 10), (10, 3))
        self.assertEqual(S.blitz_bilder(20, 60), (6, 2))
        self.assertEqual(S.blitz_bilder(20, 30), (3, 1))
        self.assertEqual(S.blitz_bilder(1, 10, tast=0.5), (10, 5))
        self.assertEqual(S.blitz_bilder(20, 10, tast=0.5), (3, 2))

    def test_kein_strobe_und_unsinn(self):
        for hz, fps in ((0, 10), (-1, 10), (5, 0), (None, 10), ("x", 10)):
            self.assertEqual(S.blitz_bilder(hz, fps), (0, 0))
            self.assertTrue(S.blitz_an(3, hz, fps))

    def test_folge_ist_periodisch(self):
        for hz in (0.5, 1, 2, 5, 12, 20):
            for fps in (1, 4, 10, 20):
                periode, an = S.blitz_bilder(hz, fps)
                folge = [S.blitz_an(i, hz, fps) for i in range(periode * 5)]
                self.assertEqual(folge, folge[:periode] * 5)
                self.assertEqual(sum(folge[:periode]), an)
                self.assertTrue(folge[0] and not folge[periode - 1])


class LiveView2dBlinktImBildtaktTest(unittest.TestCase):
    """Sichtprobe 2026-10-12: die 2D-Ansicht blinkte langsam und unregelmaessig
    (~0,7 s an, lange aus) — die Phase wurde je Bild aus der Uhr abgetastet.
    Jetzt zaehlt die Ansicht ihre Takt-Bilder (ohne Fenster geprueft)."""

    def _canvas(self, abstand_s=0.0):
        import src.ui.views.live_view as LV
        c = SimpleNamespace(RENDER_INTERVAL_MS=LV.StageCanvas.RENDER_INTERVAL_MS,
                            _strobe_bild=0, _bild_abstand_s=lambda: abstand_s)
        c._strobe_bildrate = lambda: LV.StageCanvas._strobe_bildrate(c)
        c._blink_an = lambda hz, r=False: LV.StageCanvas._blink_an(c, hz, r)
        return LV, c

    def _folge(self, c, hz, n, rechteck=False):
        aus = []
        for i in range(n):
            c._strobe_bild = i
            aus.append("#" if c._blink_an(hz, rechteck) else ".")
        return "".join(aus)

    def test_bildrate_ist_der_takt_der_ansicht(self):
        LV, c = self._canvas()
        self.assertEqual(LV.StageCanvas.RENDER_INTERVAL_MS, 100)
        self.assertAlmostEqual(c._strobe_bildrate(), 10.0)
        _LV, gebremst = self._canvas(abstand_s=0.25)        # UI-86 bremst
        self.assertAlmostEqual(gebremst._strobe_bildrate(), 4.0)

    def test_schneller_strobe_ein_bild_an_zwei_aus(self):
        _LV, c = self._canvas()
        for hz in (5, 10, 20):
            self.assertEqual(self._folge(c, hz, 12), "#..#..#..#..", hz)

    def test_langsamer_strobe_in_seiner_frequenz(self):
        _LV, c = self._canvas()
        self.assertEqual(self._folge(c, 2, 15), "#....#....#....")
        self.assertEqual(self._folge(c, 1, 20), "###.......###.......")

    def test_rechteck_effekt_bleibt_halb_an_halb_aus(self):
        _LV, c = self._canvas()
        self.assertEqual(self._folge(c, 1, 20, rechteck=True), "#####.....#####.....")

    def test_gebremste_ansicht_bleibt_gleichmaessig(self):
        _LV, c = self._canvas(abstand_s=0.25)
        self.assertEqual(self._folge(c, 20, 9), "#..#..#..")

    def test_steckbrief_weg_nutzt_den_bildzaehler(self):
        LV, c = self._canvas()
        ch = _ch(ranges=[_rng(0, 9, "Zu", "closed"), _rng(10, 255, "Strobe 5 Hz", "strobe")])
        sb = {"strobe": [(ch, 7, {})], "uni": 1, "fp": (42,)}
        lese = lambda _uni, _addr: 100
        folge = []
        for i in range(6):
            c._strobe_bild = i
            hz, an = LV.StageCanvas._strobe_aus_steckbrief(c, sb, lese, {"square": {}})
            self.assertAlmostEqual(hz, 5.0)
            folge.append(an)
        self.assertEqual(folge, [True, False, False, True, False, False])
        # Rechteck-Effekt (kein Shutter-Strobe): halbe Periode an.
        leer = {"strobe": [], "uni": 1, "fp": (42,)}
        c._strobe_bild = 4
        self.assertEqual(LV.StageCanvas._strobe_aus_steckbrief(
            c, leer, lese, {"square": {42: 1.0}}), (1.0, True))
        c._strobe_bild = 5
        self.assertEqual(LV.StageCanvas._strobe_aus_steckbrief(
            c, leer, lese, {"square": {42: 1.0}}), (1.0, False))

    def test_keine_abtastung_der_uhr_mehr(self):
        import src.ui.views.live_view as LV
        with open(LV.__file__, encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertNotIn("time.time() * freq_hz", quelle)
        self.assertEqual(quelle.count("self._blink_an(freq_hz, rechteck)"), 2)
        tick = quelle[quelle.index("    def _on_render_tick(self)"):]
        tick = tick[:tick.index("\n    # ── VIZ-70")]
        self.assertLess(tick.index("_strobe_bild"), tick.index("self.update()"))


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

    def _strobe_block(self):
        fx = self._lies("fixtures", "fixtures.js")
        return fx[fx.index("// ── VIZ-104: Strobe im Bildtakt"):fx.index("// ── Spaet-Bindung")]

    def test_keine_erzwungene_schatten_neuberechnung(self):
        for quelle in (self._strobe_block(), self._lies("fixtures", "strobe_hell.js")):
            self.assertNotIn("requestShadowUpdate(", quelle)
            self.assertNotIn("needsUpdate", quelle)

    def test_takt_zaehlt_bilder_statt_die_uhr_abzutasten(self):
        block = self._strobe_block()
        m = re.search(r"function _bildJetzt\(\) \{(.*?)\n\}", block, re.S)
        self.assertIsNotNone(m)
        self.assertIn("_strobeBild", m.group(1))
        tick = block[block.index("export function tickStrobe()"):block.index("export function strobeNeuBewerten")]
        self.assertIn("_strobeBild += 1;", tick)
        self.assertIn("taktFps(_strobeTakt, _strobeFps)", tick)
        # Die Uhr dient nur noch der Messung der Bildrate, nie der Phase.
        self.assertNotIn("performance.now", block.replace(tick, ""))
        self.assertNotIn("strobeFaktor(jetzt", block)

    def test_takt_wendet_den_dmx_stand_nicht_neu_an(self):
        """Je Wechsel nur Helligkeiten (strobe_hell.js) — die volle Anwendung
        bleibt dem DMX-Update und, als Ausnahme, dem Laser."""
        block = self._strobe_block()
        tick = block[block.index("export function tickStrobe()"):block.index("export function strobeNeuBewerten")]
        self.assertNotIn("updateFixtureDmx(", tick)
        zeigen = block[block.index("function _strobeZeigen(f)"):block.index("/** Vor jedem Bild")]
        self.assertLess(zeigen.index("hellSetzen("), zeigen.index("updateFixtureDmx("))
        self.assertEqual(block.count("updateFixtureDmx("), 1)
        hell = self._lies("fixtures", "strobe_hell.js")
        code = "\n".join(z for z in hell.split('"use strict"')[1].splitlines()
                         if not z.strip().startswith("//"))
        for wort in ("updateFixtureDmx", "applyFloorAim", "applyGobo", "applyOptics",
                     "applyPrism", "updateMatrixWorld", "new THREE", "needsUpdate",
                     ".map =", "syncSpotPool", "requestRender"):
            self.assertNotIn(wort, code, wort)

    def test_spot_pool_haelt_licht_und_schatten_in_der_dunkelphase(self):
        pool = self._lies("scene", "spot_pool.js")
        self.assertEqual(pool.count("_strobeFaktor === 0"), 2)

    def test_einstellung_kommt_in_der_szene_an(self):
        br = self._lies("bridge", "bridge.js")
        self.assertIn("s.strobeMode", br)
        self.assertIn("strobeNeuBewerten()", br)
        self.assertIn("strobeMode: 'flash'", self._lies("state.js"))


class LiesmichHinweisTest(unittest.TestCase):
    """Oeffentlicher Hinweis zu Lichtblitzen (Entscheidung des Projektinhabers)."""

    def test_readme_nennt_strobe_epilepsie_und_die_einstellung(self):
        with open(os.path.join(_REPO, "README.md"), encoding="utf-8") as fh:
            text = fh.read()
        for wort in ("photosensitiver Epilepsie", "Stroboskop", "Strobe im 3D zeigen",
                     "Gedämpft", "Aus"):
            self.assertIn(wort, text, wort)


class AnleitungTest(unittest.TestCase):
    def test_abschnitt_strobe(self):
        with open(_ANLEITUNG, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("## Strobe im 3D", text)
        a = text.index("## Strobe im 3D")
        ende = text.find("\n## ", a + 5)
        abschnitt = text[a:ende if ende > 0 else len(text)]
        for wort in ("Strobe im 3D zeigen", "Blitzen", "Gedämpft", "Dauerlicht",
                     f"{P.CAP_HZ} Blitze", "mindestens drei Bilder", "gleichmäßig",
                     "photosensitiver Epilepsie", "DMX-Ausgabe",
                     "eigenen Shutter je Kopf", "ohne Bereichsangaben"):
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

    def test_auswahl_passt_in_die_schmale_spalte(self):
        """Sichtprobe 2026-10-12: die Auswahl war rechts abgeschnitten — ihr
        laengster Eintrag bestimmte die Breite der Zeile. Jetzt darf sie
        schmaler sein als ihr laengster Eintrag (Muster wie bei der Stufe)."""
        from PySide6.QtWidgets import QComboBox, QLabel
        win, tab = self._fenster({})
        combo = win._combo_strobe
        self.assertEqual(combo.sizeAdjustPolicy(),
                         QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.assertEqual(combo.minimumContentsLength(), 12)
        titel = [l for l in tab.findChildren(QLabel) if l.text() == "Strobe im 3D zeigen:"]
        self.assertEqual(len(titel), 1)
        # Schmalste Spalte 330 px; davon gehen Raender von Reiter, Gruppe und
        # Rollbalken ab (grosszuegig 60).
        zeile = titel[0].sizeHint().width() + combo.minimumSizeHint().width() + 12
        self.assertLessEqual(zeile, 330 - 60, zeile)
        laengster = max(combo.fontMetrics().horizontalAdvance(combo.itemText(i))
                        for i in range(combo.count()))
        self.assertLess(combo.minimumSizeHint().width(), laengster + 30)
        self.assertTrue(win._lbl_strobe_warnung.wordWrap())
