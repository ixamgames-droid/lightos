#!/usr/bin/env python3
"""Render-Kosten der 3D-Szene messen — die Zahl, die bis 2026-08-03 fehlte.

Vor diesem Werkzeug gab es **kein einziges fps-Datum** fuer den Visualizer. Jede
Aussage ueber die Kosten einer Optik-Aenderung (Bloom, Beam-Shader, mehr Kegel)
war damit eine Behauptung. Deshalb liegt es im Repo und nicht im Scratchpad.

    ./venv/bin/python tools/viz_render_benchmark.py            # 12/32/48 Fixtures
    ./venv/bin/python tools/viz_render_benchmark.py 8 24 64
    ./venv/bin/python tools/viz_render_benchmark.py --json     # nur die Zahlen
    ./venv/bin/python tools/viz_render_benchmark.py 32 --zerlegen   # Anteile trennen

Gemessen wird die Zeit fuer einen kompletten Renderdurchlauf der ECHTEN Szene
(`stage_scene.html`, echter Modulcode) bei voll aufgedrehten Moving Heads —
dem teuersten Fixture-Typ (Beam-Kegel, SpotLight, Bodenfleck).

## Stand 2026-08-03: die Zahlen stimmen jetzt — nach zwei Korrekturen

Dieses Werkzeug hat zweimal das Falsche gemessen, beide Male ueberzeugend:

1. **Die Szene war dunkel.** Das `dmxBatch`-Signal will ein ARRAY
   `[{fid, r, g, b, intensity}]`, bekam aber ein Objekt `{fid: {...}}`; der
   Handler lief ins Leere. Gemessen wurde reine Gehaeuse-Geometrie. Die Werte
   stiegen trotzdem mit der Fixture-Zahl, waren reproduzierbar und deckten sich
   zwischen zwei unabhaengigen Skripten — gefunden hat es erst eine
   Wirkungs-Kontrolle ("0 sichtbare Kegel" bei voll aufgedrehten Movern).
2. **Mehrere Frames in EINEM JS-Task.** Das ist nicht der Betriebsmodus (dort
   gibt rAF einen Frame je Durchlauf) und ausserdem instabil. Jetzt treibt
   Python die Schleife, ein Frame je `runJavaScript`.

Beides ist behoben und gegen einen Rueckfall gesichert: vor jeder Messung wird
geprueft, ob die Szene ueberhaupt leuchtet, und ohne Kegel gibt es eine Warnung
statt einer huebschen Zahl.

**Nebenbei fand dieses Werkzeug den Absturz, der VIZ-PERF war:** ein Rig ab 26
Geraeten liess den Intel-Shader-Compiler scheitern
(`SIMD8 FS compile failed: no register to spill`), weil das Shadow-Budget zu
hoch angesetzt war. Seit dem Dach in `fixtures.js` laufen 32 und 48 Fixtures.

## Zerlegung: EIN PROZESS JE VARIANTE, nicht ein Lauf mit Umschalten

    for v in "" kegel boden schatten spots; do
      ./venv/bin/python tools/viz_render_benchmark.py 32 ${v:+--aus $v}
    done

**Warum umstaendlich?** Weil der bequeme Weg zweimal gescheitert ist. Der Modus
`--zerlegen` schaltet die Bestandteile im selben Prozess nacheinander ab — und
seine eigene Kontrollmessung meldete beide Male "Lauf gestoert": zwischen der
ersten und der letzten Messung DESSELBEN Vollzustands lagen 2,5 bzw. 3,8 ms, bei
gesuchten Anteilen von 1-7 ms. Eine Aufwaermphase machte es schlechter statt
besser. Der Zustand der Seite driftet ueber einen Lauf einfach staerker, als die
Anteile gross sind; ein Ergebnis daraus waere geraten gewesen.

Mit einem frischen Prozess je Variante hat jede Messung dieselbe Vorgeschichte.
Ergebnis bei 32 leuchtenden Movern (Median je Frame, Intel UHD 630):

    voll                 19,50 ms
    ohne Kegel           15,30 ms   -4,20 ms   22 %
    ohne Bodenflecken    16,50 ms   -3,00 ms   15 %
    ohne Schatten        12,40 ms   -7,10 ms   36 %
    ohne SpotLights       9,00 ms  -10,50 ms   54 %

Die Summe der Einzelanteile (17,7 ms) passt zum Gesamtwert (19,5 ms) — der Rest
ist Grundgeometrie. **"Ohne SpotLights" enthaelt die Schatten** (ein unsichtbares
Licht wirft keinen), die reine Beleuchtungsrechnung liegt also bei rund 3,4 ms.

**Rangfolge fuer jede Optimierung: Schatten (36 %) vor Kegeln (22 %) vor
Bodenflecken (15 %).** Das Schatten-Dach von 16 ist bereits gesetzt (VIZ-PERF);
es weiter zu senken ist der naechste wirksame Hebel — und eine Entscheidung mit
optischem Preis, keine reine Technikfrage.

`--zerlegen` bleibt trotzdem im Werkzeug: es ist schnell, und seine
Kontrollmessung sagt ehrlich, wann man ihm nicht glauben darf.

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

Die Szene wird vom **`VisualizerService`** gefuettert, nicht direkt vom
DMX-Ausgang: `TICK_MS = 33`, also rund **30 Hz**, und dabei nur die GEAENDERTEN
Fixtures. Das Budget je Frame ist damit **33 ms**, nicht 22,7 ms.

**Und ein Ueberschreiten staut nichts auf.** Das Dirty-Flag im Render-Loop ist
binaer (`_dirty = true/false`, keine Warteschlange): kommen zwei Batches zwischen
zwei Bildern, zeigt das naechste Bild schlicht den neueren Stand. Die Ansicht
wird also nicht langsamer ODER aelter — sie zeigt weniger Zwischenschritte und
bleibt aktuell. Ueber dem Budget heisst deshalb "weniger Bilder je Sekunde",
nicht "haengt hinterher".
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

# ⚠️ Der Massstab ist die Push-Rate des VISUALIZERS, nicht die des DMX-Ausgangs.
#
# Erste Fassung rechnete gegen 44 Hz (`OutputManager.TARGET_HZ`) und meldete
# daraufhin "ab 32 Geraeten ueberschreitet die Szene das Budget". Das war die
# falsche Zahl: die Szene wird nicht vom Output-Thread gefuettert, sondern vom
# `VisualizerService`, und der tickt mit `TICK_MS = 33`, also rund **30 Hz** —
# und schickt dabei nur die GEAENDERTEN Fixtures (Diff gegen einen Cache).
#
# Mit dem richtigen Budget (33 ms) sieht die Lage deutlich anders aus:
# 32 Fixtures liegen bei 90 % statt bei 130 %, eng wird es erst gegen 48.
VIZ_HZ = 1000.0 / 33.0                  # VisualizerService.TICK_MS
VIZ_BUDGET_MS = 33.0
# Rueckwaertskompatible Namen (die Tests und die Ausgabe unten nutzen sie).
DMX_HZ = VIZ_HZ
DMX_BUDGET_MS = VIZ_BUDGET_MS

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

# EIN Frame je Aufruf. Die Schleife treibt Python, damit zwischen zwei Frames der
# Event-Loop laeuft — genau wie im Betrieb, wo rAF je Durchlauf einen Frame gibt.
#
# ⚠️ Die frueher Fassung liess JS mehrere Frames in EINEM Task rendern. Das ist
# nicht nur unrealistisch, es bringt den Intel-Treiber zum Absturz: gemessen
# laeuft 1 Frame bei 32 leuchtenden Fixtures sauber durch (13,9 ms), 3 Frames im
# selben Task erzeugen reproduzierbar SIGSEGV mit Shader-Assembly im Log. Der
# Absturz war also ein Fehler des WERKZEUGS, nicht der Szene — und er haette
# beinahe als Eigenschaft des Visualizers protokolliert.
_MESSUNG_JS = """
(function () {
  const L = window.__lightos;
  const c = document.querySelector('canvas');
  const gl = c && (c.getContext('webgl2') || c.getContext('webgl'));
  if (!gl) return JSON.stringify({fehler: 'kein GL-Kontext'});
  L.requestRender();
  const t0 = performance.now();
  L.__renderTick();
  gl.finish();                        // ohne das misst man nur die Submission
  return JSON.stringify({ms: +(performance.now() - t0).toFixed(2)});
})()
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


def messen(stufen, runden=40, still=False, zerlegen=False, kumulativ=False,
           aus=None):
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
        print(f"GPU-Stufe: {tier} · Visualizer-Budget bei {VIZ_HZ:.0f} Hz "
              f"(VisualizerService.TICK_MS): {VIZ_BUDGET_MS:.1f} ms je Frame")

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

        # ⚠️ Das Signal erwartet ein ARRAY von {fid, r, g, b, intensity, pan, tilt}
        # (bridge.js: `for (const d of arr)`), NICHT ein Objekt {fid: {...}}.
        # Die erste Fassung schickte ein Objekt — der Handler lief ins Leere, die
        # Fixtures blieben DUNKEL, und die Messung erfasste nur Gehaeuse-Geometrie
        # ohne Beams, Bodenflecken und Lichter. Gemeldet hat das nicht die Messung
        # (die lieferte plausible Zahlen), sondern die Wirkungs-Kontrolle der
        # Zerlegung: "0 sichtbare Kegel" bei angeblich voll aufgedrehten Movern.
        bridge.dmxBatch.emit(json.dumps([
            {"fid": 1000 + i, "r": 255, "g": 180, "b": 90,
             "intensity": 255, "pan": 128, "tilt": 200}
            for i in range(anzahl)]))
        pumpe(0.8)

        # Und die Gegenprobe dazu: leuchten sie wirklich? Eine Messung an einer
        # dunklen Szene ist keine Messung der Szene.
        aktiv = json.loads(ev(_ZAEHLEN) or "{}")
        if not aktiv.get("antwort"):
            print(f"ABBRUCH: die Seite antwortet nicht mehr (bei {anzahl} "
                  f"Fixtures). Das ist KEINE Messung von 0 — vermutlich ist der "
                  f"Renderer gestorben; im Log nach 'compile failed' suchen.",
                  file=sys.stderr)
            break
        if not still:
            print(f"    aktiv: {aktiv.get('kegel', 0)} Kegel · "
                  f"{aktiv.get('boden', 0)} Bodenflecken · "
                  f"{aktiv.get('spots', 0)} Lichter · "
                  f"{aktiv.get('schatten', 0)} Schatten")
        if not aktiv.get("kegel"):
            # ⚠️ ABBRUCH, nicht Warnung. Eine Warnung geht auf stderr, waehrend
            # die ungueltige Stufe mit --json als ganz normales Ergebnis in der
            # strukturierten Ausgabe landet — genau die Sorte falscher Baseline,
            # gegen die dieses Werkzeug gebaut wurde, nur diesmal maschinell
            # weiterverarbeitbar. Lieber gar keine Zahl als eine, der man
            # ansehen muss, dass sie nichts wert ist.
            ergebnis["stufen"][str(anzahl)] = {
                "fixtures": anzahl, "ungueltig": True,
                "grund": "kein sichtbarer Kegel — Szene dunkel",
                "aktiv": aktiv,
            }
            print(f"ABBRUCH: {anzahl} Fixtures, aber KEIN sichtbarer Kegel — die "
                  f"Szene ist dunkel. Es wird NICHT gemessen; eine Zahl von hier "
                  f"waere reine Geometrie.", file=sys.stderr)
            break

        def einmal_messen(n=None, aufwaermen=0):
            """Sammelt n Einzelframes — je einer pro Event-Loop-Durchlauf.

            `aufwaermen` verwirft die ersten Frames. Nach jedem Zustandswechsel
            (Kegel aus, Schatten aus …) uebersetzt three betroffene Programme
            NEU; die ersten Frames danach tragen diese Kosten und verzerren den
            Median. Ohne das meldete die Zerlegung "ohne Kegel spart -38 %" —
            also eine NEGATIVE Ersparnis, obwohl der Schalter nachweislich 32
            Kegel abgeschaltet hatte.
            """
            for _ in range(aufwaermen):
                ev(_MESSUNG_JS, 30.0)
                app.processEvents()
            zeiten = []
            for _ in range(n or runden):
                roh = ev(_MESSUNG_JS, 30.0)
                d = json.loads(roh or "{}")
                if "ms" not in d:
                    return {"fehler": d.get("fehler", "keine Antwort")}
                zeiten.append(d["ms"])
                app.processEvents()          # dem Compositor Luft lassen
            zeiten.sort()
            def q(p):
                return zeiten[min(len(zeiten) - 1, int(len(zeiten) * p))]
            w = {"runden": len(zeiten), "median_ms": round(q(0.50), 2),
                 "p95_ms": round(q(0.95), 2), "max_ms": round(zeiten[-1], 2)}
            w["fps_p95"] = round(1000.0 / max(w["p95_ms"], 0.001), 1)
            w["folgt_dmx"] = w["p95_ms"] <= DMX_BUDGET_MS
            return w

        if aus:
            # ⚠️ **Der Zustand MUSS vor der ersten getakteten Messung stehen.**
            # Vorher lief hier ein unbedingtes `einmal_messen()` und der
            # `--aus`-Lauf verwarf dessen 40 Frames wieder. Damit meldete der
            # Voll-Lauf sein ERSTES 40-Frame-Fenster, jeder `--aus`-Lauf aber ein
            # SPAETERES — und verglichen wurden am Ende zwei verschiedene
            # Abschnitte der Prozess-Lebenszeit. Genau diese Drift hat die
            # Kontrollmessung im selben Werkzeug mit 2,5 bzw. 3,8 ms beziffert,
            # bei gesuchten Anteilen von 1–7 ms: der Messfehler war so gross wie
            # das Messergebnis. Das Verfahren "ein eigener Prozess je Variante"
            # traegt nur, wenn jeder Prozess auch DIESELBE Vorgeschichte hat —
            # und die kuerzest moegliche ist: gar keine.
            _ABSCHALTER = {
                "kegel": lambda: bridge.settingsChanged.emit(
                    json.dumps({"showCones": False})),
                "boden": lambda: bridge.settingsChanged.emit(
                    json.dumps({"showFloorSpots": False})),
                "schatten": lambda: ev(_SCHATTEN_AUS),
                "spots": lambda: ev(_SPOTS_AUS),
            }
            if aus not in _ABSCHALTER:
                raise SystemExit(f"--aus {aus}: unbekannt "
                                 f"({', '.join(_ABSCHALTER)})")
            vorher = json.loads(ev(_ZAEHLEN) or "{}")
            _ABSCHALTER[aus]()
            pumpe(1.0)
            nachher = json.loads(ev(_ZAEHLEN) or "{}")
            schluessel = {"kegel": "kegel", "boden": "boden",
                          "schatten": "schatten", "spots": "spots"}[aus]
            if nachher.get(schluessel, -1) >= vorher.get(schluessel, 0):
                raise SystemExit(
                    f"--aus {aus} hat NICHTS bewirkt "
                    f"({vorher.get(schluessel)} -> {nachher.get(schluessel)}) — "
                    f"eine Messung waere bedeutungslos")
            werte = einmal_messen()
            werte["fixtures"] = anzahl
            werte["aus"] = aus
            werte["wirkung"] = f"{vorher.get(schluessel)}->{nachher.get(schluessel)}"
            ergebnis["stufen"][str(anzahl)] = werte
            if not still:
                print(f"{anzahl:>3} Fixtures OHNE {aus:<9} median "
                      f"{werte['median_ms']:>6.2f} ms · p95 {werte['p95_ms']:>6.2f} ms "
                      f"[{werte['wirkung']}]")
            continue

        werte = einmal_messen()
        werte["fixtures"] = anzahl
        ergebnis["stufen"][str(anzahl)] = werte

        if not still:
            marke = "ok " if werte["folgt_dmx"] else "ZU LANGSAM"
            print(f"{anzahl:>3} Fixtures: median {werte['median_ms']:>6.2f} ms · "
                  f"p95 {werte['p95_ms']:>6.2f} ms · {werte['fps_p95']:>5.1f} fps  {marke}")

        if zerlegen:
            # mehr Runden: die Anteile sind klein, das Rauschen darf es nicht sein
            # Mehr Runden fuer die Zerlegung: die Anteile sind klein (1-3 ms),
            # das Rauschen darf es nicht auch sein.
            basis = einmal_messen(80, aufwaermen=20)
            werte["zerlegung"] = _zerlegen(
                anzahl, basis, ev, pumpe, bridge,
                lambda: einmal_messen(80, aufwaermen=20), still,
                zurueckschalten=not kumulativ)

    view.setParent(None)
    view.deleteLater()
    pumpe(0.6)
    return ergebnis


# ── Zerlegung: welcher Bestandteil kostet wieviel? ───────────────────────────
#
# Ohne diese Aufteilung optimiert man auf Verdacht. Jede Stufe schaltet GENAU
# EINEN Bestandteil ab und misst neu; die Differenz zur Vollmessung ist sein
# Anteil. Bewusst kumulativ am Ende ("nur Gehaeuse"), damit sichtbar wird, ob
# sich die Einzelanteile ueberhaupt zur Gesamtlast addieren — tun sie es nicht,
# ist die Last woanders (Geometrie, Uniform-Updates, Szenen-Traversierung).

_SCHATTEN_AUS = """
(function () {
  let n = 0;
  for (const fid in window.__lightos.fixtures) {
    const s = window.__lightos.fixtures[fid].spot;
    if (s && s.castShadow) { s.castShadow = false; n += 1; }
  }
  window.__lightos.requestRender();
  return n;
})()
"""

_SPOTS_AUS = """
(function () {
  let n = 0;
  for (const fid in window.__lightos.fixtures) {
    const s = window.__lightos.fixtures[fid].spot;
    if (s && s.visible) { s.visible = false; n += 1; }
  }
  window.__lightos.requestRender();
  return n;
})()
"""


# Stellt den VOLLEN Zustand wieder her — Lichter UND Schatten.
#
# ⚠️ Die erste Fassung setzte nur `spot.visible` zurueck. Die Schatten blieben
# aus, weil `applySettings()` kein `syncSpotShadowBudget()` ruft (das laeuft nur
# beim Hinzufuegen/Entfernen von Fixtures). Folge: nach der Stufe "ohne
# Schatten" waren ALLE weiteren Messungen schattenlos — die SpotLight-Ersparnis
# haette die Schatten-Ersparnis mitgezaehlt, und die Kontrollmessung am Ende
# haette gegen einen unvollstaendigen "Vollzustand" verglichen und ihn fuer
# unauffaellig erklaert. Ein Ruecksetzer, der nur die Haelfte zuruecksetzt, ist
# schlimmer als keiner: er macht die Zerlegung falsch UND meldet sie als gueltig.
_ALLES_AN = """
(function (budget) {
  const L = window.__lightos;
  let vergeben = 0;
  for (const fid in L.fixtures) {
    const s = L.fixtures[fid].spot;
    if (!s) continue;
    s.visible = true;
    s.castShadow = vergeben < budget;      // dieselbe fid-Reihenfolge wie
    if (s.castShadow) vergeben += 1;       // syncSpotShadowBudget()
  }
  L.requestRender();
  return vergeben;
})(%d)
"""

# Wirkungs-Kontrolle: zaehlt, was gerade WIRKLICH aktiv ist. Ohne sie sieht ein
# Schalter, der nichts bewirkt, in der Messung aus wie ein Bestandteil, der
# nichts kostet — genau die Verwechslung, die diese Zerlegung aufloesen soll.
# ⚠️ Das `antwort`-Feld ist kein Zierrat, sondern der Unterschied zwischen
# "nichts ist aktiv" und "niemand hat geantwortet".
#
# `ev()` liefert `None`, wenn `runJavaScript` nicht antwortet — etwa weil der
# Renderer-Prozess gestorben ist. Ohne Sentinel wird daraus `json.loads("{}")`
# und damit `{kegel: 0, boden: 0, ...}`, also exakt dasselbe Bild wie eine
# dunkle Szene. Genau so ist am 2026-08-03 die Meldung "bei 48 Fixtures leuchtet
# nichts" entstanden: der Renderer war zu dem Zeitpunkt bereits am
# Shader-Compiler gescheitert, und das Schweigen wurde als Messwert gelesen.
# Es hat einen halben Tag gekostet, das als eigenes Raetsel zu verfolgen.
_ZAEHLEN = """
(function () {
  const L = window.__lightos;
  if (!L || !L.fixtures) return JSON.stringify({antwort: 1, fehler: 'kein __lightos'});
  let kegel = 0, boden = 0, schatten = 0, spots = 0;
  for (const fid in L.fixtures) {
    const f = L.fixtures[fid];
    if (f.beam && f.beam.visible) kegel += 1;
    if (f.floorSpot && f.floorSpot.visible) boden += 1;
    if (f.spot && f.spot.castShadow) schatten += 1;
    if (f.spot && f.spot.visible) spots += 1;
  }
  return JSON.stringify({antwort: 1, geraete: Object.keys(L.fixtures).length,
                         kegel, boden, schatten, spots});
})()
"""


def _zerlegen(anzahl, voll, ev, pumpe, bridge, messen_fn, still,
              zurueckschalten=True):
    """Anteil je Bestandteil — EINZELN, nicht kumulativ, mit Kontrollmessung.

    **Der erste Anlauf war nicht auswertbar, und das ist die Lehre.** Er schaltete
    kumulativ ab (Kegel, dann zusaetzlich Bodenflecken, dann Schatten …) und las
    p95 ab. Ergebnis: 14,6 → 15,2 → 16,1 → 14,2 ms. Die Werte STIEGEN zwischendurch,
    obwohl jeder Schritt nur zusaetzlich Arbeit wegnimmt — die Einzelanteile
    (1–3 ms) liegen unter dem Rauschen von p95 (zwischen zwei Vollmessungen allein
    1,3 ms Unterschied gemessen).

    Deshalb hier drei Aenderungen:
      * **Median statt p95.** p95 ist ein Ausreisser-Mass und darum das
        rauschigste; fuer einen Anteilsvergleich ist der Median die stabilere Zahl.
      * **Einzeln statt kumulativ**, jeweils mit vollem Rueckbau dazwischen. Sonst
        summieren sich die Messfehler ueber die Kette.
      * **Kontrollmessung am Ende:** derselbe Vollzustand wie am Anfang wird
        erneut gemessen. Weicht er deutlich ab, war der Lauf gestoert und die
        Anteile sind nichts wert — das sagt das Werkzeug dann selbst.
    """
    def voll_herstellen():
        bridge.settingsChanged.emit(json.dumps({"showCones": True,
                                                "showFloorSpots": True}))
        ev(_ALLES_AN % schatten_budget)
        pumpe(0.6)

    # (Name, Schaltfunktion, Schluessel in der Wirkungs-Kontrolle)
    stufen = [
        ("ohne Kegel", lambda: bridge.settingsChanged.emit(
            json.dumps({"showCones": False})), "kegel"),
        ("ohne Bodenflecken", lambda: bridge.settingsChanged.emit(
            json.dumps({"showFloorSpots": False})), "boden"),
        ("ohne Schatten", lambda: ev(_SCHATTEN_AUS), "schatten"),
        ("ohne SpotLights", lambda: ev(_SPOTS_AUS), "spots"),
    ]
    # Wieviele Schatten waren im Vollzustand aktiv? Das ist die Zahl, auf die
    # `voll_herstellen()` zurueckstellen muss — sie steht in der Wirkungs-
    # Kontrolle, die vor der ersten Stufe gelesen wird.
    schatten_budget = int(json.loads(ev(_ZAEHLEN) or "{}").get("schatten", 0))
    basis = voll.get("median_ms", 0)
    raus = {"basis_median_ms": basis, "schatten_im_vollzustand": schatten_budget}
    if not still:
        print(f"    Zerlegung bei {anzahl} Fixtures (Median voll: {basis:.2f} ms) — "
              f"jeder Bestandteil EINZELN abgeschaltet:")
    for name, schalten, schluessel in stufen:
        vorher = json.loads(ev(_ZAEHLEN) or "{}")
        schalten()
        pumpe(0.7)
        nachher = json.loads(ev(_ZAEHLEN) or "{}")
        wirkte = nachher.get(schluessel, -1) < vorher.get(schluessel, 0)

        w = messen_fn()
        gespart = basis - w["median_ms"]
        raus[name] = {"median_ms": w["median_ms"], "anteil_ms": round(gespart, 2),
                      "aktiv_vorher": vorher.get(schluessel),
                      "aktiv_nachher": nachher.get(schluessel),
                      "schalter_wirkte": wirkte}
        if not still:
            anteil = (gespart / basis * 100) if basis else 0
            beleg = (f"{vorher.get(schluessel)}→{nachher.get(schluessel)}" if wirkte
                     else f"SCHALTER OHNE WIRKUNG ({vorher.get(schluessel)}"
                          f"→{nachher.get(schluessel)}) — Zeile bedeutungslos")
            print(f"      {name:<20} Median {w['median_ms']:>6.2f} ms  "
                  f"(−{gespart:>5.2f} ms = {anteil:>4.1f} %)  [{beleg}]")
        if zurueckschalten:
            voll_herstellen()

    kontrolle = messen_fn()
    abweichung = abs(kontrolle["median_ms"] - basis)
    raus["kontrolle_median_ms"] = kontrolle["median_ms"]
    raus["kontrolle_abweichung_ms"] = round(abweichung, 2)
    grenze = max(0.5, basis * 0.10)
    raus["belastbar"] = abweichung <= grenze
    if not still:
        urteil = ("ok — Anteile belastbar" if raus["belastbar"] else
                  "ACHTUNG: Lauf gestoert, Anteile NICHT verwertbar")
        print(f"      {'Kontrolle (voll)':<20} Median "
              f"{kontrolle['median_ms']:>6.2f} ms  "
              f"(Abweichung {abweichung:.2f} ms) — {urteil}")
    return raus


def _aus_option() -> str | None:
    """`--aus <teil>`: schaltet EINEN Bestandteil ab und misst nur diesen Fall.

    Gedacht fuer den Aufruf in einem EIGENEN Prozess je Variante. Grund: die
    Zerlegung im selben Prozess ist zweimal an der eigenen Kontrollmessung
    gescheitert (Abweichung 2,5 bzw. 3,8 ms zwischen erster und letzter Messung
    desselben Vollzustands, bei Anteilen von 1-7 ms). Der Zustand der Seite
    driftet ueber einen Lauf staerker, als die gesuchten Anteile gross sind —
    eine Aufwaermphase hat es nicht besser, sondern schlechter gemacht.

    Mit einem frischen Prozess je Variante hat jede Messung dieselbe
    Vorgeschichte. Das ist langsamer und dafuer vergleichbar.
    """
    for i, a in enumerate(sys.argv):
        if a == "--aus" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    aus = _aus_option()
    if aus:
        args = [a for a in args if a != aus]
    still = "--json" in sys.argv
    zerlegen = "--zerlegen" in sys.argv
    kumulativ = "--kumulativ" in sys.argv
    stufen = [int(a) for a in args] if args else [12, 32, 48]
    if aus and len(stufen) != 1:
        # ⚠️ `--aus` schaltet einen Bestandteil ab und raeumt ihn NICHT wieder
        # ein — der Zustand traegt in die naechste Stufe hinueber. Was dann
        # passiert, haengt vom Bestandteil ab: bei `kegel` bricht die naechste
        # Stufe als "Szene dunkel" ab, bei `boden`/`schatten`/`spots` schlaegt
        # die Wirkungskontrolle zu ("hat NICHTS bewirkt") oder — schlimmer —
        # der Vergleich mischt abgeschaltete Altbestaende mit frisch
        # hinzugefuegten aktiven Fixtures.
        #
        # Zurueckschalten waere die andere Loesung, aber nicht die richtige:
        # `--aus` existiert genau deshalb, weil im selben Prozess gemessene
        # Varianten nicht vergleichbar sind (s. `_aus_option`). Eine zweite
        # Stufe im selben Prozess ist derselbe Fehler eine Ebene hoeher.
        # Ohne Zahl greift der Default [12, 32, 48] — auch das faengt das hier.
        raise SystemExit(
            f"--aus {aus} misst genau EINE Fixture-Zahl (angefragt: "
            f"{', '.join(str(s) for s in sorted(stufen))}). Jede Variante "
            f"gehoert in einen eigenen Prozess — sonst traegt der abgeschaltete "
            f"Zustand in die naechste Stufe hinueber. Beispiel: "
            f"tools/viz_render_benchmark.py 32 --aus {aus}")
    ergebnis = messen(sorted(stufen), still=still, zerlegen=zerlegen,
                      kumulativ=kumulativ, aus=aus)
    if still:
        print(json.dumps(ergebnis, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
