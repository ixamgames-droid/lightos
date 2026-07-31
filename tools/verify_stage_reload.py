#!/usr/bin/env python3
"""VIZ-STAGE-RELOAD-PACING — ueberlebt das volle Rig einen Renderer-Neustart?

Der offene Rest dieses Items war genau diese Frage, und sie liess sich nur am
laufenden Fenster beantworten. Gemessen wird NICHT am Bild, sondern an
``window.__lightos`` (der Debug-API der Szene): welche Buehnenobjekte und
Fixtures liegen wirklich im three.js-Graph — vor und nach „Szene neu laden"
(``_on_reload_scene`` -> ``service.reload_all_targets`` -> ``_reload_own_page``).

★ Warum kein Screenshot: die Fehlerbilder dieses Items sind **gedroppte**
Elemente (zu wenig) und **Zombies** (zu viel). Beides sind Zahlen und IDs, keine
Optik — ein Bild koennte nur „sieht voll aus" sagen.

Aufruf::

    venv/bin/python tools/verify_stage_reload.py [pfad/zur/show.lshow]

Exit 0 = identisch (Abnahme bestanden), 1 = Abweichung, 2/3 = Lauf kaputt.

★ VIER PINS, ohne die der Lauf entweder Davids Daten anfasst oder nichts misst
(Lehren aus ``reference_lightos_ui_automation``):
  1. ``XDG_DATA_HOME`` -> Wegwerf (Snaps, Buehnen, ``crash.log``).
  2. ``LIGHTOS_SHOW_DB`` -> Wegwerf. Der Default ist RELATIV zum Arbeits-
     verzeichnis; aus ``repo/`` gestartet schriebe der Lauf in die echte Show-DB.
  3. ``LIGHTOS_FIXTURE_DB`` -> die echte Library, nur lesend. Mit leerer Library
     laedt die Show 0 Fixtures und der Test misst nichts.
  4. ``LIGHTOS_NO_OUTPUT_THREAD`` -> kein Sendethread. Auf ``/dev/ttyUSB0`` kann
     der HW-5-Langzeitlauf liegen; ein zweiter Oeffner wuerde ihn stoeren.

★ Und die Falle, die diesen Lauf zweimal „bestanden" melden liess, ohne etwas zu
messen: die Show referenziert ihre Buehne nur per NAME (``stage_snapshot``), die
Definition liegt in ``<XDG>/LightOS/stages/``. Mit frischem XDG-Ordner ist die
Buehne leer -> ``0 Buehnenobjekte vorher UND nachher`` -> „identisch". Deshalb
kopiert dieser Lauf die Buehnen in den Sandkasten. **Merke: ein Vergleich, bei
dem beide Seiten 0 sind, ist kein Beweis** — darum prueft der Bericht auch, dass
ueberhaupt etwas da war.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_tmp = tempfile.mkdtemp(prefix="vizverify_")
os.environ["XDG_DATA_HOME"] = os.path.join(_tmp, "xdg")
os.environ["LIGHTOS_SHOW_DB"] = os.path.join(_tmp, "show.db")
os.environ["LIGHTOS_FIXTURE_DB"] = os.path.expanduser(
    "~/.local/share/LightOS/fixtures.db")
os.environ["LIGHTOS_NO_OUTPUT_THREAD"] = "1"
os.environ.setdefault("DISPLAY", ":0")
os.environ.pop("QT_QPA_PLATFORM", None)          # echtes Fenster, nicht offscreen

_echte_stages = os.path.expanduser("~/.local/share/LightOS/stages")
_sandkasten_stages = os.path.join(_tmp, "xdg", "LightOS", "stages")
if os.path.isdir(_echte_stages):
    os.makedirs(os.path.dirname(_sandkasten_stages), exist_ok=True)
    shutil.copytree(_echte_stages, _sandkasten_stages)

# DMX-Sicherheit UNMITTELBAR vor dem Start pruefen — ein pytest-Lauf schreibt
# data/universes.json nachweislich zurueck (Lehre 2026-07-28).
_cfg_path = os.path.join(REPO, "data", "universes.json")
_cfg = open(_cfg_path, encoding="utf-8").read() if os.path.exists(_cfg_path) else "[]"
for _bad in ("255.255.255.255", "192.168.", "10.0.", "COM", "/dev/tty"):
    if _bad in _cfg:
        raise SystemExit(
            f"ABBRUCH: data/universes.json enthaelt {_bad!r} — das wuerde ins "
            f"echte Rig senden. Fuer diesen Lauf EIN Art-Net auf 127.0.0.1 "
            f"eintragen.\n{_cfg}")

from PySide6.QtCore import QTimer                                  # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402

DEFAULT_SHOW = "/home/maxi/projects/lightos/repo/shows/Mega_Arena_2026.lshow"

JS = """(function(){
  try {
    var L = window.__lightos || {};
    return JSON.stringify({
      ready: !!window.__lightosAppReady,
      stage: Object.keys(L.stageObjects || {}).length,
      fixtures: Object.keys(L.fixtures || {}).length,
      ids: Object.keys(L.stageObjects || {}).sort()
    });
  } catch (e) { return 'JSERR ' + e; }
})()"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    show = argv[0] if argv else DEFAULT_SHOW
    if not os.path.exists(show):
        print(f"Show nicht gefunden: {show}")
        return 2

    app = QApplication.instance() or QApplication(sys.argv)
    from src.core.app_state import get_state
    from src.core.show.show_file import load_show
    from src.ui.main_window import MainWindow

    win = MainWindow(touch=True)
    win.show()
    zustand: dict = {"viz": None, "vorher": None, "nachher": None}

    def sichten(cb):
        vw = zustand["viz"]
        view = getattr(vw, "_view", None) if vw is not None else None
        if view is None:
            print("[verify] FEHLER: kein Visualizer-View")
            return ende()
        view.page().runJavaScript(JS, cb)

    def schritt_show():
        ok, msg = load_show(show)
        n = len(get_state().get_patched_fixtures())
        print(f"[verify] {msg}  (Fixtures im State: {n})")
        if not ok or not n:
            print("[verify] ABBRUCH: Show nicht geladen — ohne Rig misst der Lauf nichts")
            return ende()
        QTimer.singleShot(1500, schritt_viz)

    def schritt_viz():
        win._open_visualizer()
        vw = getattr(win, "_visualizer_window", None)
        zustand["viz"] = vw
        if vw is not None:
            # QtWebEngine drosselt versteckte Seiten, und erst showEvent meldet
            # dem Service „mein Target ist aktiv" — ohne das bleibt die Szene leer.
            vw.show(); vw.raise_(); vw.activateWindow()
        print(f"[verify] Visualizer offen (sichtbar={vw.isVisible() if vw else None})")
        QTimer.singleShot(12000, schritt_vorher)

    def schritt_vorher():
        def cb(res):
            zustand["vorher"] = res
            print(f"[verify] VORHER : {res}")
            QTimer.singleShot(500, schritt_reload)
        sichten(cb)

    def schritt_reload():
        print("[verify] -> Szene neu laden (Renderer-Neustart)")
        zustand["viz"]._on_reload_scene()
        QTimer.singleShot(9000, schritt_nachher)

    def schritt_nachher():
        def cb(res):
            zustand["nachher"] = res
            print(f"[verify] NACHHER: {res}")
            ende()
        sichten(cb)

    def ende():
        try:
            a = json.loads(zustand["vorher"] or "{}")
            b = json.loads(zustand["nachher"] or "{}")
        except Exception:
            a = b = {}
        etwas_da = bool(a.get("stage")) and bool(a.get("fixtures"))
        gleich = (a.get("stage"), a.get("fixtures"), a.get("ids")) == \
                 (b.get("stage"), b.get("fixtures"), b.get("ids"))
        fehlend = sorted(set(a.get("ids") or ()) - set(b.get("ids") or ()))
        zuviel = sorted(set(b.get("ids") or ()) - set(a.get("ids") or ()))
        print("=" * 66)
        print(f"  Buehnenobjekte vorher/nachher : {a.get('stage')} / {b.get('stage')}")
        print(f"  Fixtures       vorher/nachher : {a.get('fixtures')} / {b.get('fixtures')}")
        print(f"  fehlend nach Reload           : {fehlend or '—'}")
        print(f"  Zombies nach Reload           : {zuviel or '—'}")
        if not etwas_da:
            print("  VERDIKT: NICHTS GEMESSEN — die Szene war schon vorher leer.")
        else:
            print(f"  VERDIKT: {'IDENTISCH — Abnahme bestanden' if gleich else 'ABWEICHUNG'}")
        print("=" * 66)
        app.exit(0 if (etwas_da and gleich) else 1)

    QTimer.singleShot(2500, schritt_show)
    QTimer.singleShot(75000, lambda: (print("[verify] TIMEOUT"), app.exit(3)))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
