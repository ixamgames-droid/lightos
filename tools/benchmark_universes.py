"""T-8 / RM-Benchmark — Render-Performance fuer mehrere Universen.

Misst die reine `AppState._render_frame()`-Zeit (Default -> Funktionen ->
Executoren -> Programmer -> Commit) ueber N Frames bei 8 / 16 / 32 gepatchten
Universen, jeweils mit laufender Last (eine RGB-Matrix auf die PARs + eine EFX
auf die Moving Heads pro Universum). Keine echte DMX-/Netzwerk-Ausgabe noetig —
der Output-Thread wird per `LIGHTOS_NO_OUTPUT_THREAD=1` gar nicht erst gestartet,
und `_render_frame` wird synchron in der Messschleife aufgerufen.

Aufruf:  venv/Scripts/python.exe tools/benchmark_universes.py [frames]   (Default 300 Frames)
Ergebnis: Tabelle auf stdout + geschrieben nach docs/PERFORMANCE.md.

Hinweis: get_state() wendet beim ersten Aufruf die Output-Konfig aus
data/universes.json an und oeffnet ggf. den dort konfigurierten Enttec-/sACN-Port.
Fuer die Messung ist das irrelevant (Output-Thread aus, send_dmx() wird nie
gerufen) — auf einer Maschine ohne den Port erscheint nur eine Warnzeile.
"""
from __future__ import annotations
import os
import sys
import time
import platform
import statistics
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Output-/Render-Thread NICHT autostarten — wir rufen _render_frame selbst auf.
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state
from src.core.database.models import PatchedFixture
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.efx import EfxAlgorithm, EfxFixture

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOC = os.path.join(_ROOT, "docs", "PERFORMANCE.md")

# Builtin-Profile (wie in tools/build_test_show.py)
PAR_PROFILE, PAR_MODE, PAR_CH = 17, "8-Kanal RGBW", 8        # ZQ01424 RGBW
MH_PROFILE,  MH_MODE,  MH_CH  = 10, "7-Kanal",      7        # Moving Head Wash RGB


def _reset():
    state = get_state()
    fm = get_function_manager()
    fm.stop_all()
    for f in list(fm.all()):
        try:
            fm.remove(f.id)
        except Exception:
            pass
    for f in list(state.get_patched_fixtures()):
        try:
            state.remove_fixture(f.fid, undoable=False)
        except Exception:
            pass
    state.programmer = {}
    return state, fm


def _build(universes: int, pars_per_universe: int):
    """Patcht pro Universum `pars_per_universe` PARs + 2 Moving Heads und legt je
    eine laufende RGB-Matrix (PARs) und EFX (MH) an."""
    state, fm = _reset()
    fid = 1
    for u in range(1, universes + 1):
        addr = 1
        par_fids: list[int] = []
        for _ in range(pars_per_universe):
            if addr + PAR_CH - 1 > 512:
                break
            state.add_fixture(PatchedFixture(
                fid=fid, label=f"PAR U{u}-{fid}", fixture_profile_id=PAR_PROFILE,
                mode_name=PAR_MODE, universe=u, address=addr, channel_count=PAR_CH,
                manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
                fixture_type="color"), undoable=False)
            par_fids.append(fid); addr += PAR_CH; fid += 1
        if len(par_fids) < pars_per_universe:
            print(f"[benchmark] WARN: Universum {u}: nur {len(par_fids)}/"
                  f"{pars_per_universe} PARs gepatcht (512-Adressraum voll).")
        mh_fids: list[int] = []
        for _ in range(2):
            if addr + MH_CH - 1 > 512:
                break
            state.add_fixture(PatchedFixture(
                fid=fid, label=f"MH U{u}-{fid}", fixture_profile_id=MH_PROFILE,
                mode_name=MH_MODE, universe=u, address=addr, channel_count=MH_CH,
                manufacturer_name="Generic", fixture_name="Moving Head Wash RGB 7ch",
                fixture_type="moving_head"), undoable=False)
            mh_fids.append(fid); addr += MH_CH; fid += 1
        if par_fids:
            m = fm.new_rgb_matrix(f"MX U{u}")
            m.algorithm = RgbAlgorithm.RAINBOW
            m.fixture_grid = list(par_fids)
            m.cols = len(par_fids)
            m.rows = 1
            m.matrix_speed = 1.5
            fm.start(m.id)
        if mh_fids:
            e = fm.new_efx(f"EFX U{u}")
            e.algorithm = EfxAlgorithm.CIRCLE
            e.speed_hz = 0.4
            for i, mf in enumerate(mh_fids):
                e.fixtures.append(EfxFixture(fid=mf, start_offset=i / max(len(mh_fids), 1)))
            fm.start(e.id)
    return state


def _measure(state, frames: int, dt: float = 1.0 / 44.0) -> list[float]:
    for _ in range(10):                       # Warmup
        state._render_frame(dt)
    samples: list[float] = []
    for _ in range(frames):
        t0 = time.perf_counter()
        state._render_frame(dt)
        samples.append((time.perf_counter() - t0) * 1000.0)   # ms
    samples.sort()
    return samples


def _pct(sorted_ms: list[float], p: float) -> float:
    if not sorted_ms:
        return 0.0
    k = max(0, min(len(sorted_ms) - 1, int(round(p / 100.0 * (len(sorted_ms) - 1)))))
    return sorted_ms[k]


def run_benchmark(universe_counts=(8, 16, 32), pars_per_universe: int = 12,
                  frames: int = 300) -> list[dict]:
    """Fuehrt den Benchmark fuer jede Universen-Anzahl aus und gibt die Kennzahlen
    zurueck (eine Zeile je Konfiguration)."""
    rows: list[dict] = []
    for n in universe_counts:
        state = _build(n, pars_per_universe)
        fx = len(state.get_patched_fixtures())
        s = _measure(state, frames)
        mean = statistics.fmean(s) if s else 0.0
        rows.append({
            "universes": n, "fixtures": fx, "frames": len(s),
            "p50": _pct(s, 50), "p95": _pct(s, 95), "max": (s[-1] if s else 0.0),
            "mean": mean, "fps": (1000.0 / mean) if mean else 0.0,
        })
    _reset()      # Singleton sauber hinterlassen
    return rows


def _fmt_table(rows: list[dict]) -> str:
    out = [
        "| Universen | Fixtures | Frames | p50 (ms) | p95 (ms) | max (ms) | Ø (ms) | FPS (Ø) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            "| {universes} | {fixtures} | {frames} | {p50:.3f} | {p95:.3f} | "
            "{max:.3f} | {mean:.3f} | {fps:.0f} |".format(**r))
    return "\n".join(out)


def _write_doc(rows: list[dict], pars_per_universe: int, frames: int):
    py = platform.python_version()
    mach = f"{platform.system()} {platform.release()} / {platform.machine()}"
    doc = f"""# Performance — Render-Pipeline (Mehr-Universen-Benchmark)

> **Stand: {date.today().isoformat()}** · erzeugt von `tools/benchmark_universes.py` (Open Point T-8).
> Maschine: {mach}, Python {py}. Reproduzieren: `venv/Scripts/python.exe tools/benchmark_universes.py`.

Gemessen wird die reine **`AppState._render_frame()`**-Zeit (Default-Frame →
Funktionen → Executoren → Programmer → atomarer Commit) **ohne** DMX-/Netzwerk-
Ausgabe (`LIGHTOS_NO_OUTPUT_THREAD=1`). Last pro Universum: {pars_per_universe} PARs
mit laufender **RGB-Matrix** (Rainbow) + 2 Moving Heads mit laufender **EFX** (Kreis),
alle aktiv. {frames} gemessene Frames je Konfiguration (nach 10 Warmup-Frames),
`dt = 1/44 s`.

{_fmt_table(rows)}

## Lesehilfe
- **p50/p95/max**: Median / 95-Perzentil / Worst-Case der Frame-Render-Zeit.
- **FPS (Ø)**: theoretisch erreichbare Bildrate aus der mittleren Render-Zeit
  (`1000 / Ø`). Der reale Output-Loop zielt auf 44 Hz (≈ 22,7 ms Budget/Frame) —
  solange p95 deutlich darunter liegt, ist Headroom vorhanden.

## Methodik / Hinweise
- Synthetischer Patch über `state.add_fixture(PatchedFixture(...))`, Effekte über
  `FunctionManager.new_rgb_matrix` / `new_efx` + `start(id)`.
- Nur die Render-Pipeline wird vermessen; das Senden (Enttec/sACN/Art-Net) ist
  bewusst deaktiviert und nicht Teil der Zahlen.
- Werte sind stark maschinen-, last- und thermik-abhängig (auf diesem ARM64-Gerät
  schwankten die Absolutzeiten zwischen Läufen um ~2×, v.a. bei 16/32 Universen unter
  Dauerlast). Aussagekräftig ist primär der **Trend**: super-lineares Wachstum mit der
  Universen-Zahl, und ab 16–32 Universen liegt die Render-Zeit über dem 44-Hz-Budget
  (≈ 22,7 ms). Für stabile Absolutzahlen auf einer idle Maschine mehrfach laufen lassen.
- Bei Vergleichen dieselbe Konfiguration (PARs/Universum, Frames) verwenden; neu
  erzeugen nach Engine-Änderungen, die den Render-Pfad betreffen.
"""
    os.makedirs(os.path.dirname(_DOC), exist_ok=True)
    with open(_DOC, "w", encoding="utf-8") as fh:
        fh.write(doc)


if __name__ == "__main__":
    frames = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    pars = 12
    print(f"[benchmark] {frames} Frames/Konfig, {pars} PARs/Universum, "
          f"Output-Thread aus …")
    rows = run_benchmark(pars_per_universe=pars, frames=frames)
    table = _fmt_table(rows)
    print(table)
    _write_doc(rows, pars, frames)
    print(f"[benchmark] geschrieben: {_DOC}")
