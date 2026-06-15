"""Headless-Verifikation der Komplett_Demo.lshow (AUTO-SHOW + Moving Heads).

Laedt die Show ohne UI, prueft Referenz-Integritaet (Timeline/Chaser/VC),
startet die AUTO-SHOW-Timeline und tickt den echten Renderer
(AppState._render_frame) ueber >1 Loop-Durchlauf. Verifiziert, dass sich die
Pan/Tilt-Kanaele der Moving Heads in den EFX-Abschnitten tatsaechlich bewegen
und dass der Timeline-Loop sauber neu startet.

Aufruf:  venv\\Scripts\\python.exe tools\\verify_komplett_demo.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHOW = os.path.join("shows", "Komplett_Demo.lshow")
FPS = 44.0
DT = 1.0 / FPS

ok = True


def fail(msg: str):
    global ok
    ok = False
    print(f"FEHLER: {msg}")


def main():
    from src.core.app_state import get_state, get_channels_for_patched
    from src.core.show.show_file import load_show

    state = get_state()
    load_show(SHOW)
    fm = state.function_manager
    funcs = {f.id: f for f in fm.all()}
    print(f"Show geladen: {len(state.get_patched_fixtures())} Fixtures, "
          f"{len(funcs)} Funktionen")

    # ── 1. Referenz-Integritaet ────────────────────────────────────────────
    from src.core.engine.show_engine import Show
    show = funcs.get(74)
    if show is None or not isinstance(show, Show):
        fail("AUTO-SHOW (id 74) fehlt oder ist kein Show-Typ")
        return 1
    for tr in show.tracks:
        for sf in tr.show_functions:
            if sf.function_id not in funcs:
                fail(f"Timeline-Referenz {sf.function_id} (Track {tr.name}) fehlt")
    for f in funcs.values():
        for attr in ("step_ids", "function_ids"):
            for cid in (getattr(f, attr, None) or []):
                if isinstance(cid, int) and cid not in funcs:
                    fail(f"Funktion {f.id} ({f.name}) referenziert fehlende id {cid}")
    # Chaser-Steps (Werte-Steps oder Funktions-Steps)
    for f in funcs.values():
        for st in (getattr(f, "steps", None) or []):
            cid = getattr(st, "function_id", None)
            if isinstance(cid, int) and cid and cid not in funcs:
                fail(f"Chaser {f.id} ({f.name}) Step referenziert fehlende id {cid}")
    # VC-Layout: Funktions-Bindungen
    import json
    vc = getattr(state, "_vc_layout", {}) or {}
    def _walk(node):
        if isinstance(node, dict):
            fid = node.get("function_id")
            if isinstance(fid, int) and fid and fid not in funcs:
                fail(f"VC-Widget {node.get('label', '?')} referenziert "
                     f"fehlende Funktion {fid}")
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
    _walk(vc)
    print("Referenz-Check: Timeline/Chaser/VC ok" if ok else "Referenz-Check: FEHLER s.o.")

    # ── 2. Moving-Head-Kanal-Layout ────────────────────────────────────────
    mh_addr = {}   # fid -> (pan_addr, tilt_addr, dim_addr)
    for fx in state.get_patched_fixtures():
        if fx.fid not in (5, 6):
            continue
        chans = get_channels_for_patched(fx)
        layout = {c.attribute: fx.address + c.channel_number - 1 for c in chans}
        print(f"  MH fid={fx.fid} addr={fx.address} mode={fx.mode_name}: "
              + ", ".join(f"{c.channel_number}:{c.attribute}" for c in chans))
        if "pan" not in layout or "tilt" not in layout:
            fail(f"MH fid={fx.fid}: kein pan/tilt-Attribut im Profil!")
            continue
        mh_addr[fx.fid] = (layout["pan"], layout["tilt"],
                           layout.get("intensity") or layout.get("dimmer"))
    if not mh_addr:
        fail("Keine Moving Heads (fid 5/6) im Patch gefunden")
        return 1

    # ── 3. AUTO-SHOW ticken (85 s = 1 Loop + 13 s) ────────────────────────
    fm.start(74)
    if not fm.is_running(74):
        fail("AUTO-SHOW liess sich nicht starten")
        return 1

    samples = []   # (t, {fid: (pan, tilt, dim)})
    t = 0.0
    frames = int(85.0 * FPS)
    for i in range(frames):
        state._render_frame(DT)
        t += DT
        if i % int(FPS) == 0:   # 1 Sample/s
            u = state.universes[1]
            snap = {fid: tuple(u.get_channel(a) for a in addrs if a)
                    for fid, addrs in mh_addr.items()}
            samples.append((round(t, 1), snap))

    def pan_values(t0, t1, fid=5):
        return [s[fid][0] for ts, s in samples if t0 <= ts <= t1]

    # 0–10 s: Pos Publikum (statisch) — Pan konstant
    v = pan_values(2, 9)
    if len(set(v)) > 1:
        print(f"  Hinweis: Pan 2-9s nicht konstant: {v}")
    # 11–21 s: EFX 'MH Kreis' — Pan MUSS sich bewegen
    v = pan_values(12, 21)
    if len(set(v)) < 3:
        fail(f"MH bewegt sich NICHT waehrend 'MH Kreis' (12-21s): Pan={v}")
    else:
        print(f"  MH-Bewegung 12-21s ok (Pan variiert: {sorted(set(v))[:6]}…)")
    # 47–57 s: 'MH Bounce' — Pan muss sich ebenfalls bewegen
    v = pan_values(48, 57)
    if len(set(v)) < 3:
        fail(f"MH bewegt sich NICHT waehrend 'MH Bounce' (48-57s): Pan={v}")
    # Dimmer/Shutter: open_beam → Intensitaet > 0 waehrend EFX
    dim = [s[5][2] for ts, s in samples if 12 <= ts <= 21 and len(s[5]) > 2]
    if dim and max(dim) == 0:
        fail(f"MH-Dimmer bleibt 0 waehrend EFX (open_beam wirkungslos): {dim}")
    # Loop: nach 72 s muss die Timeline neu laufen (AUTO-SHOW noch running)
    if not fm.is_running(74):
        fail("AUTO-SHOW laeuft nach Loop-Grenze (72s) nicht mehr")
    v = pan_values(73, 81)
    if len(set(v)) > 1:
        print(f"  Hinweis: 73-81s Pan variiert {sorted(set(v))[:4]} "
              f"(erwartet: statisch Pos Publikum nach Loop-Restart)")

    fm.stop(74)
    print("OK — alle Checks bestanden" if ok else "FEHLGESCHLAGEN — s. FEHLER oben")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
