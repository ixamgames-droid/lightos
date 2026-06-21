# Performance — Render-Pipeline (Mehr-Universen-Benchmark)

> **Stand: 2026-06-15** · erzeugt von `tools/benchmark_universes.py` (Open Point T-8).
> Maschine: Windows 11 / ARM64, Python 3.14.5. Reproduzieren: `venv/Scripts/python.exe tools/benchmark_universes.py`.

Gemessen wird die reine **`AppState._render_frame()`**-Zeit (Default-Frame →
Funktionen → Executoren → Programmer → atomarer Commit) **ohne** DMX-/Netzwerk-
Ausgabe (`LIGHTOS_NO_OUTPUT_THREAD=1`). Last pro Universum: 12 PARs
mit laufender **RGB-Matrix** (Rainbow) + 2 Moving Heads mit laufender **EFX** (Kreis),
alle aktiv. 300 gemessene Frames je Konfiguration (nach 10 Warmup-Frames),
`dt = 1/44 s`.

| Universen | Fixtures | Frames | p50 (ms) | p95 (ms) | max (ms) | Ø (ms) | FPS (Ø) |
|---|---|---|---|---|---|---|---|
| 8 | 112 | 300 | 14.423 | 20.953 | 29.379 | 13.176 | 76 |
| 16 | 224 | 300 | 41.812 | 54.608 | 77.607 | 42.231 | 24 |
| 32 | 448 | 300 | 120.485 | 144.115 | 272.496 | 121.651 | 8 |

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
