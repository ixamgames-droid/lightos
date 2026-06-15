# Output-Merge-Vertrag (verbindlich)

> Stand: 2026-06-08 (OUT-01). Beschreibt die **einzig gueltige** Schichtreihenfolge,
> mit der `AppState._render_frame` jeden DMX-Frame berechnet. Alle Wertquellen müssen
> sich an diesen Vertrag halten. Regressionstests: `tests/test_render_frame.py`,
> `tests/test_dimmer_master.py`, `tests/test_programmer_priority.py`,
> `tests/test_function_layer_order.py`, `tests/test_iso_simple_desk.py`.

## Ein Renderer, ein Thread

Es gibt **genau einen** Render-Pfad: `AppState._render_frame(dt)`, registriert als
Tick-Callback des `OutputManager` (44 Hz). Kein zweiter Thread schreibt in die
Universen. Jeder Frame beginnt mit einem **vollständigen Clear** (Scratch-Universen
werden mit dem Default-Frame vorbelegt) → keine hängenden Werte gestoppter Quellen.

## Schichtreihenfolge (unten = niedrigste Priorität)

| # | Schicht | Quelle | Semantik |
|---|---------|--------|----------|
| 1 | **Default-Frame** | `base_levels` + Fixture-`default_value` | Basis jedes Frames (Per-Frame-Clear) |
| 2 | **Funktionen** | `FunctionManager.tick` (Scene/Chaser/EFX/RGB-Matrix/…) | LTP in **Start-Reihenfolge** (`_start_order`): zuletzt gestartet gewinnt (LAYER-01) |
| 3 | **Executoren** | `PlaybackEngine.compute_merged` (Cues) | LTP über Funktionen |
| 4 | **Programmer** | `state.programmer` (inkl. Matrix-Programmer) | LTP, **eingeschränkt** durch WP-6 + EE-02 (s. u.) |
| 4b | **Dimmer-Master** | `submaster_level` · `fixture_dimmers` · Programmer-Dimmer | multiplikativ auf Intensitäts-/Ersatz-Farbkanäle |
| 4c | **Simple Desk** | `state.simple_desk` (ISO-03) | **nur wenn `simple_desk_override` aktiv** — sonst reine Anzeige; dann oberste Schicht, nur explizit gesetzte Kanäle |
| 5 | **Commit** | gepatchte Spans atomar; freie Kanäle über Engine-Extra (+ Freigabe) | ins Live-Universe |
| — | **Grand Master / Blackout** | `OutputManager._send_all` (GM-Adressmaske) | erst beim Senden, nur Intensität/Farbe |

## Sonderregeln (warum der Programmer NICHT „durchfunkt")

- **WP-6 — Funktions-Kanalschutz:** Treibt eine laufende Funktion in *diesem* Frame
  einen **Nicht-Intensitäts-Kanal** (Scratch ≠ Default), überschreibt der Programmer-LTP
  diesen Kanal **nicht** (`_apply_fixture_map(..., protect_addrs=func_driven)`). Eine
  laufende Matrix-/EFX-Farbe wird also nicht vom Color-Tab „weggebügelt".
- **EE-02 — Programmer-Dimmer multipliziert:** Läuft ein Effekt auf den Intensitäts-
  Kanälen eines Fixtures, **ersetzt** der Programmer-Dimmer ihn nicht per LTP, sondern
  **multipliziert** ihn (Faktor 0..1). Ohne Effekt: normaler LTP-Ersatz.
- **Cues > Funktionen:** Executoren (Schicht 3) liegen bewusst über Funktionen; ein
  Cue ersetzt laufende Effektwerte per LTP (gewollt).

## Isolation & Sichtbarkeit (Phase 0)

- **Kein „VC Priority Mode" nötig.** Programmer/Matrix-Programmer teilen sich `state.programmer`
  und sind durch WP-6/EE-02 bereits gegen ungewolltes Überschreiben laufender Effekte geschützt.
- **Simple Desk (ISO-03)** ist seit 2026-06-08 keine Roh-Bypass-Schreibebene mehr, sondern
  Schicht 4c — deterministisch, sicht- und löschbar. **Default = reine Anzeige (Monitor):**
  die Fader spiegeln die Live-Ausgabe und wirken nicht. Erst die Checkbox **„Manueller
  Override"** (`set_simple_desk_override(True)`) gibt ihnen absolute Oberhand; beim
  Ausschalten werden die Override-Werte verworfen.
- **Sichtbarkeit (ISO-01):** `programmer_active()` / `simple_desk_active()` → Badge in der
  oberen Leiste.
- **Zentrales Clear (ISO-02):** `clear_programmer()`, `clear_simple_desk()`,
  `clear_all_non_vc()`. Löscht **nur** aktive manuelle Werte — niemals laufende Funktionen,
  gespeicherte Effekte, Shows, Patches oder Fixtures.

## Invarianten (dürfen nicht gebrochen werden)

1. Nur `_render_frame` schreibt in die Universen (außer roh: OSC-/Input-Merge auf freie Kanäle).
2. Neue Wertquellen ordnen sich als **Schicht** in diese Tabelle ein — kein Direkt-Write
   ins Live-Universe am Renderer vorbei (sonst Flicker/Zombie wie der alte Simple-Desk-Bug).
3. Jede manuelle Override-Quelle muss `*_active()`-zählbar und über ein `clear_*` löschbar sein.
