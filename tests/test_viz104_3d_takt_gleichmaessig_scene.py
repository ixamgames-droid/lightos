"""VIZ-104 (3D-Takt): gleichmaessiger Strobe — die Verdrahtung in der ECHTEN Seite.

``test_viz104_3d_takt_gleichmaessig.py`` prueft die reine Rechnung unter Node.
Hier laeuft der Betriebsweg der Seite: ``tickStrobe`` zaehlt je Bild eins
weiter und misst die Bildrate — nur die Zeit je Bild kommt aus einer
stellbaren Uhr (``__strobeMessUhr``), damit sich die Bildfolge der Sichtprobe
nachstellen laesst (60 Bilder/s mit einzelnen 66-ms-Bildern, ein echter
Wechsel auf 30, eine Pause).

Gemessen wird in Zeit: Blitzbeginne je Geraet, Abstand der Blitze, Zahl der
Takt-Wechsel (``strobeInfo().taktWechsel``).

Kein WebGL noetig: gemessen wird der Szenenzustand.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz92_gobo_feinschliff_scene import _Basis, _FID, _geraet  # noqa: E402
from test_viz104_strobe_im_3d_scene import _STROBE_5HZ, _payload_fid  # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_STROBE_2HZ = 20 + round(199 * (2 - 1) / 19)
_FIDS = [_FID, _FID + 1, _FID + 2]

# Eine Bildfolge in EINEM Aufruf (kein fremder Tick dazwischen): Mess-Uhr
# stellen, je Bild die Zeit vorstellen und einmal ticken. Je Bild: Zeit und
# An/Aus jedes Geraets; am Ende der Takt-Zustand.
_LAUF_JS = """
(function(){
  const L = window.__lightos, fids = %s, dts = %s;
  window.__t104t = 1000;
  L.__strobeMessUhr(() => window.__t104t, %r);
  const zeiten = [], folge = fids.map(() => []), faktor = fids.map(() => []);
  for (const dt of dts) {
    window.__t104t += dt;
    L.__renderTick();
    zeiten.push(window.__t104t - 1000);
    fids.forEach((fid, k) => {
      const f = L.fixtures[String(fid)];
      folge[k].push(f.spot.intensity > 0 ? 1 : 0);
      faktor[k].push(L.strobeInfo(fid).faktor);
    });
  }
  const info = L.strobeInfo(fids[0]), infos = fids.map(fid => L.strobeInfo(fid));
  L.__strobeMessUhr(null);
  return JSON.stringify({ zeiten, folge: folge.map(f => f.join('')), faktor, info, infos });
})()
"""


def _folge(dauer_ms, normal, lang=None, lange=()):
    dts, t, k = [], 0.0, 0
    while t < dauer_ms:
        dt = normal
        if k < len(lange) and t >= lange[k]:
            dt, k = lang, k + 1
        dts.append(dt)
        t += dt
    return dts


def _blitze(zeiten, folge, ab_ms=500):
    an = [zeiten[i] for i, c in enumerate(folge)
          if c == "1" and i > 0 and folge[i - 1] == "0" and zeiten[i] >= ab_ms]
    return an, [b - a for a, b in zip(an, an[1:])]


class Viz104TaktGleichmaessigSzeneTest(_Basis):
    GERAETE = [_geraet(fid=f, x=(i - 1) * 2.0) for i, f in enumerate(_FIDS)]

    def _start(self, modus=None):
        self._load_and_wait()
        if modus:
            self._bridge_obj.settingsChanged.emit(json.dumps({"strobeMode": modus}))
            self._poll_until_true(
                "window.__lightos.strobeInfo(%d).modus === '%s'" % (_FID, modus))
        self._push(_payload_fid(_FIDS[0], shutter=_STROBE_5HZ),
                   _payload_fid(_FIDS[1], shutter=_STROBE_5HZ),
                   _payload_fid(_FIDS[2], shutter=_STROBE_2HZ))

    def _lauf(self, dts, start_fps=60):
        return json.loads(self._eval(_LAUF_JS % (json.dumps(_FIDS), json.dumps(dts),
                                                 float(start_fps))))

    def test_lange_einzelbilder_verstellen_den_takt_nicht(self):
        """(a) 60 Bilder/s, alle 2-4 s ein 66-ms-Bild, 10 s."""
        self._start()
        r = self._lauf(_folge(10000, 1000 / 60, 66, (2100, 5300, 7400, 9600)))
        self.assertEqual(r["info"]["taktWechsel"], 0, r["info"])
        self.assertEqual(r["info"]["taktFps"], 60)
        self.assertAlmostEqual(r["info"]["fps"], 60, delta=0.01)
        self.assertEqual(r["info"]["periode"], 12)
        a, b, c = r["folge"]
        self.assertEqual(a, b, "gleiche Frequenz muss gemeinsam blitzen")
        p_c = r["infos"][2]["periode"]
        self.assertTrue(29 <= p_c <= 31, r["infos"][2])        # ~2 Hz
        for folge, periode in ((a, 12), (c, p_c)):
            _an, abst = _blitze(r["zeiten"], folge)
            self.assertGreaterEqual(len(abst), 9.5 * 60 / periode - 2)   # ab 0,5 s
            soll = periode * 1000 / 60
            self.assertAlmostEqual(min(abst), soll, delta=0.01)
            self.assertLessEqual(max(abst) - min(abst), 66 - 1000 / 60 + 0.01, abst)

    def test_echter_wechsel_wird_einmal_uebernommen_phase_bleibt(self):
        """(c) 3 s 60 Bilder/s, dann 4 s 30 Bilder/s."""
        self._start()
        dts = _folge(3000, 1000 / 60) + _folge(4000, 1000 / 30)
        r = self._lauf(dts)
        self.assertEqual(r["info"]["taktWechsel"], 1, r["info"])
        self.assertAlmostEqual(r["info"]["taktFps"], 30, delta=0.01)
        self.assertEqual(r["info"]["periode"], 6)
        a, b, _c = r["folge"]
        self.assertEqual(a, b)
        _an, abst = _blitze(r["zeiten"], a)
        # Bis zur Uebernahme laeuft die 12er-Periode im 30er-Tempo (400 ms),
        # danach 6 Bilder = 200 ms. Nie kuerzer als eine Periode, nie laenger
        # als die alte Periode im neuen Tempo (+ ein Bild).
        self.assertGreaterEqual(min(abst), 200 - 0.01, abst)
        self.assertLessEqual(max(abst), 400 + 1000 / 30 + 0.01, abst)
        self.assertNotIn("11111", a)                    # kein zusammengeklebter Doppelblitz
        hinten = [x for t, x in zip(_an[1:], abst) if t > 5000]
        self.assertTrue(hinten and all(abs(x - 200) < 0.01 for x in hinten), hinten)

    def test_pause_verstellt_nichts(self):
        """(f) Tab im Hintergrund: ein Abstand von 2 s zaehlt nicht."""
        self._start()
        dts = _folge(2000, 1000 / 60) + [2000.0] + _folge(2000, 1000 / 60)
        r = self._lauf(dts)
        self.assertEqual(r["info"]["taktWechsel"], 0, r["info"])
        self.assertAlmostEqual(r["info"]["fps"], 60, delta=0.01)
        a = r["folge"][0]
        for i in range(len(a) - 12):
            self.assertEqual(a[i], a[i + 12], "Takt stolpert bei Bild %d" % i)

    def test_weich_ohne_phasensprung(self):
        """(e) 'weich' mit den langen Einzelbildern: die Welle bleibt im
        Bildraster periodisch (32 Bilder bei 60/s)."""
        self._start("soft")
        r = self._lauf(_folge(6000, 1000 / 60, 66, (1500, 3900)))
        self.assertEqual(r["info"]["taktWechsel"], 0, r["info"])
        w = r["faktor"][0]
        self.assertGreaterEqual(min(w), 0.5)
        self.assertEqual(max(w), 1)
        for i in range(len(w) - 32):
            self.assertEqual(w[i], w[i + 32], "weiche Welle springt bei Bild %d" % i)

    def test_aus_bleibt_dauerlicht(self):
        self._start("off")
        r = self._lauf(_folge(2000, 1000 / 60, 66, (700,)) + _folge(1500, 1000 / 30))
        for f in r["folge"]:
            self.assertNotIn("0", f)
