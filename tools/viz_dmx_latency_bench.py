"""VIZ-71 — wie schnell und wie schlank kommen die Lichtdaten im 3D-Viewer an?

Zwei Messungen, beide headless (``QT_QPA_PLATFORM=offscreen``):

``spike``
    Der Spike aus VIZ-71 S0: ruft im 33-ms-Takt ``page().runJavaScript`` mit
    Rueckruf gegen die echte Visualizer-Seite auf und zaehlt, wie viele Rueckrufe
    ankommen und wie lange sie brauchen. Davon haengt ab, ob der DMX-Push ueber
    ``runJavaScript`` laufen kann (Weg A) oder einen eigenen Poll braucht
    (Weg B). Gemessen am 2026-10-04 auf Linux offscreen: 187 von 187 Rueckrufen,
    p50 2,4 ms, p95 2,8 ms — auch bei verstecktem Widget.

``messen --show <datei.lshow>``
    Simuliert die Seite in Python (Poll alle 130 ms, ``runJavaScript`` als
    Attrappe mit 3 ms Rueckruf) und misst je Szene (Leerlauf, Farb-Chase ueber
    alle Geraete, Pan/Tilt auf allen Movern): uebertragene Bytes je Sekunde,
    Dauer von ``VisualizerService._tick`` (p50/p95) und die Python-seitige
    Wartezeit vom Schreiben eines DMX-Werts bis zum ersten Senden, das ihn
    enthaelt. Erkennt selbst, ob der Push-Kanal existiert — dieselbe Messung
    laeuft also auch gegen einen aelteren Stand (``--repo``).

    Eine passende grosse Show baut ``tools/build_mega_arena_2026.py``. Die Show
    wird in ein Temp-Verzeichnis kopiert, die Show-Datenbank ebenfalls dort
    angelegt — am Arbeitsstand aendert die Messung nichts.

Aufruf (Linux)::

    ./venv/bin/python -u tools/viz_dmx_latency_bench.py spike
    ./venv/bin/python -u tools/viz_dmx_latency_bench.py messen --show shows/X.lshow
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
import time

REPO_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _qt(repo: str):
    sys.path.insert(0, repo)
    os.chdir(repo)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # Wie tools/_gen_env.py: kein 44-Hz-Output-Thread (er wuerde den
    # Display-Frame aus der Show rechnen und die Mess-Schreibvorgaenge im
    # Rohpuffer ueberdecken), kein Audio, kein Enttec-Kindprozess.
    os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
    os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")
    os.environ.setdefault("LIGHTOS_SERIAL_INPROC", "1")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _pumpen(app, sekunden: float) -> None:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        app.processEvents()
        time.sleep(0.001)


def spike(repo: str, dauer: float) -> None:
    app = _qt(repo)
    from PySide6.QtCore import QTimer
    from src.ui.visualizer.visualizer_view import Visualizer3DView
    v = Visualizer3DView()
    v.resize(800, 600)
    v.show()
    t0 = time.monotonic()
    while time.monotonic() - t0 < 30:
        box: list = []
        v._view.page().runJavaScript("!!window.__lightosAppReady", box.append)
        _pumpen(app, 0.05)
        if box and box[0]:
            break
    print(f"Seite bereit nach {time.monotonic() - t0:.2f} s")
    gesendet: dict = {}
    zurueck: dict = {}
    nr = [0]

    def feuern():
        nr[0] += 1
        n = nr[0]
        gesendet[n] = time.perf_counter()
        v._view.page().runJavaScript(
            f"(function(){{return {n};}})()",
            lambda r, n=n: zurueck.__setitem__(n, (time.perf_counter(), r)))

    takt = QTimer()
    takt.timeout.connect(feuern)
    takt.start(33)
    _pumpen(app, dauer)
    takt.stop()
    _pumpen(app, 1.0)
    lat = sorted((zurueck[n][0] - gesendet[n]) * 1000 for n in gesendet if n in zurueck)
    falsch = sum(1 for n, (_t, r) in zurueck.items() if r != n)
    print(f"gesendet {len(gesendet)}, zurueck {len(zurueck)}, falsche Rueckgabe {falsch}")
    if lat:
        print(f"Rueckruf ms: p50 {lat[len(lat) // 2]:.1f} p95 {lat[int(len(lat) * 0.95)]:.1f}"
              f" max {lat[-1]:.1f}")


def messen(repo: str, show: str, dauer: float) -> None:
    tmp = tempfile.mkdtemp(prefix="viz71_mess_")
    os.environ["LIGHTOS_SHOW_DB"] = os.path.join(tmp, "show.db")
    kopie = os.path.join(tmp, os.path.basename(show))
    shutil.copy(os.path.abspath(show), kopie)
    app = _qt(repo)
    from PySide6.QtCore import QTimer
    from src.core.app_state import get_state, get_channels_for_patched
    from src.core.show.show_file import load_show
    from src.core.stage.stage_definition import resolve_active_stage
    from src.ui.visualizer.visualizer_service import VisualizerService, VisualizerTarget
    from src.ui.visualizer.visualizer_window import VisualizerBridge
    try:
        from src.ui.visualizer import dmx_push
    except ImportError:
        dmx_push = None
    ok, _msg = load_show(kopie)
    st = get_state()
    print("Stand:", "Push (VIZ-71)" if dmx_push else "Poll (vor VIZ-71)",
          "| Show geladen:", ok, "| Geraete:", len(st.get_patched_fixtures()),
          "platziert:", len(st.visualizer_positions))

    farb, pt = [], []
    for f in st.get_patched_fixtures():
        for ch in get_channels_for_patched(f):
            a = ch.attribute or ""
            adr = f.address + ch.channel_number - 1
            if not 1 <= adr <= 512:
                continue
            if a.startswith("color_") or a in ("intensity", "dimmer"):
                farb.append((f.universe, adr, a))
            elif a in ("pan", "tilt"):
                pt.append((f.universe, adr, a))

    print(f"Kanaele: Farbe {len(farb)}, Pan/Tilt {len(pt)}")
    svc = VisualizerService(st)
    tick_ms: list = []
    orig_tick = svc._tick

    def gemessener_tick():
        a = time.perf_counter()
        orig_tick()
        tick_ms.append((time.perf_counter() - a) * 1000)
    svc._tick = gemessener_tick          # vor dem Timer-Bau setzen (connect)
    schritt = {"n": 0, "t": {}, "snap": 0}
    orig_snap = svc._build_snapshot

    def snap():
        s = orig_snap()
        schritt["snap"] = schritt["n"]
        return s
    svc._build_snapshot = snap

    bridge = VisualizerBridge(st)
    stage, _k, _n = resolve_active_stage(getattr(st, "active_stage_name", "simple") or "simple")
    bridge.push_settings({"beamOpacity": 0.35, "showCones": True, "brightness": 0.45})
    bridge.push_stage_definition(stage)
    a = time.perf_counter()
    bridge.requestFixtures()
    print(f"requestFixtures (inkl. _build_fixture_list): {(time.perf_counter() - a) * 1000:.1f} ms")
    bridge._poll_events.clear()

    z = {"js": 0, "js_n": 0, "poll": 0, "poll_n": 0, "sends": []}
    if dmx_push is not None:
        class _Seite:
            def runJavaScript(self, script, cb=None):
                z["js"] += len(script)
                z["js_n"] += 1
                z["sends"].append((time.perf_counter(), schritt["snap"]))
                if cb is not None:
                    QTimer.singleShot(3, lambda: cb(1))

        class _View:
            _s = _Seite()

            def page(self):
                return self._s
        kanal = dmx_push.DmxPushChannel(
            _View(), on_need_full=lambda: svc.force_full_resync(ziel), poll=bridge)
        ziel = VisualizerTarget("mess", bridge.dmxBatch.emit, emit_payloads=kanal.push)
        revs: dict = {}

        def poll():
            out = bridge.pollControlRev(json.dumps(revs))
            z["poll"] += len(out)
            z["poll_n"] += 1
            d = json.loads(out)
            revs.update(d.get("_rev") or {})
            if d.get("dmx"):
                z["sends"].append((time.perf_counter(), schritt["snap"]))
    else:
        ziel = VisualizerTarget("mess", bridge.dmxBatch.emit)

        def poll():
            out = bridge.pollControl()
            z["poll"] += len(out)
            z["poll_n"] += 1
            if '"dmx"' in out:
                z["sends"].append((time.perf_counter(), schritt["snap"]))

    svc.attach_target(ziel)
    svc.set_target_active(ziel, True)
    ptimer = QTimer()
    ptimer.timeout.connect(poll)
    ptimer.start(130)

    def schreiben(szene):
        schritt["n"] += 1
        k = schritt["n"]
        if szene == "chase":
            for i, (u, adr, a) in enumerate(farb):
                v = 255 if a in ("intensity", "dimmer") else int(127 + 127 * math.sin(k * 0.2 + i))
                st.universes[u].set_channel(adr, v)
        else:
            for i, (u, adr, _a) in enumerate(pt):
                st.universes[u].set_channel(adr, int(127 + 120 * math.sin(k * 0.1 + i * 0.3)))
        schritt["t"][k] = time.perf_counter()

    def lauf(szene):
        for k in ("js", "js_n", "poll", "poll_n"):
            z[k] = 0
        z["sends"] = []
        k0 = schritt["n"]
        tick_ms.clear()
        w = QTimer()
        if szene != "leerlauf":
            w.timeout.connect(lambda: schreiben(szene))
            w.start(23)                  # ~44 Hz wie der DMX-Ausgang
        t0 = time.monotonic()
        _pumpen(app, dauer)
        w.stop()
        dt = time.monotonic() - t0
        lat = []
        for k in range(k0 + 1, schritt["n"] + 1):
            tk = schritt["t"][k]
            for ts, kk in z["sends"]:
                if kk >= k and ts >= tk:
                    lat.append((ts - tk) * 1000)
                    break
        lat.sort()
        ts_ = sorted(tick_ms) or [0.0]
        lat_txt = (f"p50 {lat[len(lat) // 2]:.0f} p95 {lat[int(len(lat) * 0.95)]:.0f} ms"
                   if lat else "–")
        print(f"{szene:9s} | {(z['js'] + z['poll']) / dt / 1024:7.1f} KB/s"
              f" (JS {z['js'] / dt / 1024:6.1f} KB/s in {z['js_n'] / dt:4.1f}/s,"
              f" Poll {z['poll'] / dt / 1024:6.1f} KB/s in {z['poll_n'] / dt:4.1f}/s)"
              f" | _tick p50 {ts_[len(ts_) // 2]:.2f} p95 {ts_[int(len(ts_) * 0.95)]:.2f} ms"
              f" | Wartezeit {lat_txt}")

    _pumpen(app, 1.0)                    # Einschwingen (Vollbatch)
    for szene in ("leerlauf", "chase", "pantilt", "leerlauf"):
        lauf(szene)
    a = time.perf_counter()
    for _ in range(5):
        bridge._build_fixture_list()
    print(f"_build_fixture_list: {(time.perf_counter() - a) * 1000 / 5:.1f} ms")
    shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("modus", choices=("spike", "messen"))
    ap.add_argument("--show", help="Show-Datei fuer 'messen'")
    ap.add_argument("--sekunden", type=float, default=8.0)
    ap.add_argument("--repo", default=REPO_DEFAULT,
                    help="Code-Stand, gegen den gemessen wird (Default: dieser)")
    a = ap.parse_args(argv)
    if a.modus == "spike":
        spike(a.repo, a.sekunden)
    else:
        if not a.show:
            ap.error("'messen' braucht --show")
        messen(a.repo, a.show, a.sekunden)
    sys.stdout.flush()
    os._exit(0)                          # Qt-Abbau ueberspringen (Messwerkzeug)


if __name__ == "__main__":
    sys.exit(main())
