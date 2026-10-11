# Performance — Render-Pipeline (Mehr-Universen-Benchmark)

> **Stand: 2026-10-11** · erzeugt von `tools/benchmark_universes.py` (Open Point T-8).
> Maschine: Windows 11 / AMD64, Python 3.12.10. Reproduzieren: `venv/Scripts/python.exe tools/benchmark_universes.py` (Linux/macOS: `./venv/bin/python`).

Gemessen wird die reine **`AppState._render_frame()`**-Zeit (Default-Frame →
Funktionen → Executoren → Programmer → atomarer Commit) **ohne** DMX-/Netzwerk-
Ausgabe (`LIGHTOS_NO_OUTPUT_THREAD=1`). Last pro Universum: 12 PARs
mit laufender **RGB-Matrix** (Rainbow) + 2 Moving Heads mit laufender **EFX** (Kreis),
alle aktiv. 300 gemessene Frames je Konfiguration (nach 10 Warmup-Frames),
`dt = 1/44 s`.

| Universen | Fixtures | Frames | p50 (ms) | p95 (ms) | max (ms) | Ø (ms) | FPS (Ø) |
|---|---|---|---|---|---|---|---|
| 8 | 112 | 300 | 3.269 | 4.751 | 7.667 | 3.539 | 283 |
| 16 | 224 | 300 | 5.901 | 6.682 | 7.710 | 6.002 | 167 |
| 32 | 448 | 300 | 11.903 | 12.962 | 24.966 | 12.060 | 83 |

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
- Werte sind stark maschinen-, last- und thermik-abhängig; zwischen zwei Läufen
  können die Absolutzeiten um den Faktor 2 auseinanderliegen. Aussagekräftig ist der
  **Trend** über die Universen-Zahl. Für stabile Absolutzahlen auf einer unbelasteten
  Maschine mehrfach laufen lassen und den kleinsten Wert nehmen.
- **Verlauf:** Bis ENG-30 (Oktober 2026) wuchs die Zeit super-linear — jede Matrix-Zelle
  und jeder EFX-Kopf suchte sein Gerät per Durchlauf durch die ganze Patch-Liste, und
  der Renderer leitete je Frame für jedes Gerät die Dimmer-/Farbadressen neu ab. Auf
  einem Rechner gemessen (Windows 11 / x64, p50): 8 / 16 / 32 Universen vorher
  5,6 / 14,1 / 39,9 ms, danach 3,1 / 6,0 / 12,0 ms — 32 Universen liegen damit unter
  dem 44-Hz-Budget. Verteilung je Funktionsart an einer echten Show:
  [ENGINE_FRAME_ZEIT.md](ENGINE_FRAME_ZEIT.md).
- Bei Vergleichen dieselbe Konfiguration (PARs/Universum, Frames) verwenden; neu
  erzeugen nach Engine-Änderungen, die den Render-Pfad betreffen.
