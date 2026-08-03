#!/usr/bin/env python3
"""Render-Kosten der 3D-Szene messen — die Zahl, die bis 2026-08-03 fehlte.

Vor diesem Werkzeug gab es **kein einziges fps-Datum** fuer den Visualizer. Jede
Aussage ueber die Kosten einer Optik-Aenderung (Bloom, Beam-Shader, mehr Kegel)
war damit eine Behauptung. Deshalb liegt es im Repo und nicht im Scratchpad.

    ./venv/bin/python tools/viz_render_benchmark.py            # 12/32/48 Fixtures
    ./venv/bin/python tools/viz_render_benchmark.py 8 24 64
    ./venv/bin/python tools/viz_render_benchmark.py --json     # nur die Zahlen

Gemessen wird die Zeit fuer einen kompletten Renderdurchlauf der ECHTEN Szene
(`stage_scene.html`, echter Modulcode) bei voll aufgedrehten Moving Heads —
dem teuersten Fixture-Typ (Beam-Kegel, SpotLight, Bodenfleck).

## Drei Messfallen, alle beim ersten Anlauf hineingetappt

1. **`performance.now()` um `render()` misst die falsche Sache.** WebGL ist
   asynchron: der Aufruf setzt Draw-Calls ab und kehrt zurueck, die GPU rechnet
   danach. Deshalb steht hier `gl.finish()` dahinter — das zwingt die Pipeline
   leer, und erst dann ist die Zeit die echte Arbeit.

2. **Der rAF-Takt taugt in QtWebEngine nicht als Messgroesse.** Gemessen ergab er
   konstant 50 ms (20 Hz) — bei 12, 32 UND 48 Fixtures identisch. Das ist die
   Drosselung fuer nicht-vordergruendige Seiten, kein Leistungswert. Eine Zahl,
   die sich bei vervierfachter Last nicht bewegt, misst nicht die Last.

3. **Fixtures kommen verzoegert an.** Die Bridge-Signale brauchen laenger als
   jedes feste `sleep`; der erste Anlauf mass bei 0/20/36 statt 12/32/48
   Fixtures und haette zu gute Werte gemeldet. Es wird deshalb gewartet, bis die
   Szene die erwartete Zahl BESTAETIGT.

**Immer ein echtes Fenster** (`QT_QPA_PLATFORM` wird geloescht): offscreen laeuft
ueber SwiftShader auf der CPU, die Zahlen waeren bedeutungslos.

## Was die Zahl bedeutet

Der DMX-Ausgang laeuft mit **44 Hz** (`OutputManager.TARGET_HZ`). Bei laufenden
Effekten kommt also alle ~22,7 ms ein `dmxBatch`, und jedes davon macht die Szene
dirty. Bleibt p95 unter 22,7 ms, kann die Ansicht dem Licht folgen; darueber
faengt sie an, Aenderungen zu ueberspringen.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("QT_QPA_PLATFORM", None)          # echtes Fenster = echte GPU
sys.path.insert(0, _REPO)

DMX_HZ = 44.0
DMX_BUDGET_MS = 1000.0 / DMX_HZ

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView           # noqa: E402
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile  # noqa: E402
from PySide6.QtWebChannel import QWebChannel                    # noqa: E402
from PySide6.QtCore import QObject, QUrl, Signal, Slot          # noqa: E402

_HTML = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)), ("dmxBatch", (str,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)), ("viewModeChanged", (str,)),
    ("editModeChanged", (str,)), ("stageLoaded", (str,)), ("addStageObject", (str,)),
    ("addStageObjectData", (str,)), ("removeStageObject", (str,)),
    ("selectStageObject", (str,)), ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)), ("distributeSelected", (str,)),
    ("arrangeSelected", (str,)), ("cameraReset", ()),
    ("brightnessSignal", (float,)), ("brightnessAutoSignal", ()),
    ("updateStageObject", (str,)), ("resizeModeSignal", (bool,)),
    ("pixelRatioSignal", (float,)),
]

_MESSUNG_JS = """
(function (runden) {
  const L = window.__lightos;
  const c = document.querySelector('canvas');
  const gl = c && (c.getContext('webgl2') || c.getContext('webgl'));
  if (!gl) return JSON.stringify({fehler: 'kein GL-Kontext'});
  const z = [];
  for (let i = 0; i < runden; i++) {
    L.requestRender();
    const t0 = performance.now();
    L.__renderTick();
    gl.finish();                      // ohne das misst man nur die Submission
    z.push(performance.now() - t0);
  }
  z.sort((a, b) => a - b);
  const q = (p) => z[Math.min(z.length - 1, Math.floor(z.length * p))];
  return JSON.stringify({
    runden: z.length,
    median_ms: +q(0.50).toFixed(2),
    p95_ms:    +q(0.95).toFixed(2),
    max_ms:    +z[z.length - 1].toFixed(2),
  });
})(%d)
"""


def _bridge_cls():
    attrs = {n: Signal(*t) for n, t in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        # Die Seite ruft das, sobald IHRE Seite der Bruecke steht. Das ist der
        # einzige verlaessliche Startschuss: `__lightosAppReady` sagt nur, dass
        # die Module geladen sind — Signale, die davor abgeschickt werden,
        # landen im Nichts (gemessen: 0 von 12 Fixtures kamen an).
        self._bereit = True

    @Slot(result=str)
    def pollControl(self):
        return "{}"

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("BenchBridge", (QObject,), attrs)


def messen(stufen, runden=150, still=False):
    app = QApplication.instance() or QApplication([])
    view = QWebEngineView()
    view.page().profile().setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
    s = view.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    bridge = _bridge_cls()()
    kanal = QWebChannel(view)
    kanal.registerObject("bridge", bridge)
    view.page().setWebChannel(kanal)
    geladen = []
    view.loadFinished.connect(geladen.append)
    view.resize(1600, 900)
    view.show()
    view.load(QUrl.fromLocalFile(_HTML))

    def pumpe(sekunden):
        bis = time.monotonic() + sekunden
        while time.monotonic() < bis:
            app.processEvents()
            time.sleep(0.02)

    def ev(js, frist=30.0):
        kasten = []
        view.page().runJavaScript(js, kasten.append)
        bis = time.monotonic() + frist
        while not kasten and time.monotonic() < bis:
            app.processEvents()
            time.sleep(0.02)
        return kasten[0] if kasten else None

    bis = time.monotonic() + 40
    while not geladen and time.monotonic() < bis:
        app.processEvents()
        time.sleep(0.05)

    bis = time.monotonic() + 25
    while time.monotonic() < bis:
        if ev("!!window.__lightosAppReady", 3.0):
            break
        pumpe(0.2)

    # ... und dann auf die Bruecke warten, nicht nur auf die Module.
    bis = time.monotonic() + 25
    while time.monotonic() < bis and not getattr(bridge, "_bereit", False):
        pumpe(0.2)
    if not getattr(bridge, "_bereit", False):
        print("WARNUNG: die Seite hat requestFixtures nie gerufen — die Bruecke "
              "steht nicht, Fixtures werden nicht ankommen.", file=sys.stderr)

    tier = ev("(window.__lightos || {}).gpuTier || 'unbekannt'")
    ergebnis = {"gpuTier": tier, "dmx_budget_ms": round(DMX_BUDGET_MS, 1), "stufen": {}}
    if not still:
        print(f"GPU-Stufe: {tier} · DMX-Budget bei {DMX_HZ:.0f} Hz: "
              f"{DMX_BUDGET_MS:.1f} ms je Frame")

    bereits = 0
    for anzahl in stufen:
        for i in range(bereits, anzahl):
            w = (i / max(anzahl, 1)) * math.pi * 2
            bridge.fixtureAdded.emit(json.dumps({
                "fid": 1000 + i, "label": f"B{i}", "type": "moving_head",
                "model": "moving_head", "nHeads": 0,
                "x": math.cos(w) * 8, "y": 5.5, "z": math.sin(w) * 8,
                "rotX": 0, "rotY": 0, "rotZ": 0}))
        bereits = anzahl
        pumpe(0.8)

        # Auf BESTAETIGUNG warten — ein festes sleep reicht nicht (Falle 3).
        frist = time.monotonic() + 30
        da = 0
        while time.monotonic() < frist:
            da = int(ev("Object.keys((window.__lightos||{}).fixtures||{}).length",
                        5.0) or 0)
            if da >= anzahl:
                break
            pumpe(0.3)
        if da < anzahl:
            print(f"ABBRUCH: nur {da} von {anzahl} Fixtures in der Szene", file=sys.stderr)
            break

        bridge.dmxBatch.emit(json.dumps({
            str(1000 + i): {"intensity": 255, "red": 255, "green": 180, "blue": 90,
                            "pan": 128, "tilt": 200, "zoom": 128}
            for i in range(anzahl)}))
        pumpe(0.6)

        roh = ev(_MESSUNG_JS % runden, 90.0)
        werte = json.loads(roh or "{}")
        werte["fixtures"] = anzahl
        werte["fps_p95"] = round(1000.0 / max(werte.get("p95_ms", 1), 0.001), 1)
        werte["folgt_dmx"] = werte.get("p95_ms", 999) <= DMX_BUDGET_MS
        ergebnis["stufen"][str(anzahl)] = werte
        if not still:
            marke = "ok " if werte["folgt_dmx"] else "ZU LANGSAM"
            print(f"{anzahl:>3} Fixtures: median {werte['median_ms']:>6.2f} ms · "
                  f"p95 {werte['p95_ms']:>6.2f} ms · {werte['fps_p95']:>5.1f} fps  {marke}")

    view.setParent(None)
    view.deleteLater()
    pumpe(0.6)
    return ergebnis


def main():
    args = [a for a in sys.argv[1:] if a != "--json"]
    still = "--json" in sys.argv
    stufen = [int(a) for a in args] if args else [12, 32, 48]
    ergebnis = messen(sorted(stufen), still=still)
    if still:
        print(json.dumps(ergebnis, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
