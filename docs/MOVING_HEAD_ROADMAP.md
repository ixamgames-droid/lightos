# Moving-Head-Roadmap (Analyse + To-dos)

> Stand: 2026-06-09 · Analyse (5-Subagent-Audit) **+ vollständige Umsetzung** (Phasen M0–M7).
> Qu-Cross-Referenz: [OUTPUT_MERGE_CONTRACT.md](OUTPUT_MERGE_CONTRACT.md), [FEATURE_MAP.md](FEATURE_MAP.md), [MASTERPLAN_2026-06-08.md](MASTERPLAN_2026-06-08.md), [MOVING_HEAD_SHOW.md](MOVING_HEAD_SHOW.md).

## ✅ Umsetzungsstand (2026-06-09 — alle Phasen erledigt)

- **M0 EFX-Bugfix:** `EfxView(follow_selection=True)` (folgt Auswahl/Gruppe, nur Pan/Tilt-Geräte); zentrale Pan/Tilt-Invert/Swap-Transform (`apply_pan_tilt_orientation`) in `_apply_fixture_map` + `_flush_programmer_to_dmx` + `efx.write`; Channel-Helfer (`find_channel`/`channel_addr`/`open_value_for`); EFX `open_beam` öffnet Dimmer/Shutter → Strahler sichtbar.
- **M1 Capabilities:** `ChannelRange.kind` (+ Migration); ZQ01424/ZQ02001 ins Seed + idempotentes `ensure_builtins()`; MH-Shutter mit Open/Strobe-Ranges; CMY/Iris im Editor.
- **M2 UI:** eigenständiger **Gobo-Tab** (capability-sichtbar); **Shutter-Schnellwahl** im Intensity-Tab; generisches **`PresetTile`** + **Color/Gobo-Kacheln**; Touch-Mindesthöhen.
- **M3 Position:** PositionTool folgt Auswahl + **Live-Modus** + Fine-Bug behoben; **Invert/Swap-Toggles** im Position-Tab + **Patcher-Checkboxen**; Speed-Fader; VCXYPad folgt Auswahl.
- **M4 EFX-Ausbau:** `spread` (Fan), `mirror`, `open_beam`, 8 Algorithmen, bounce.
- **M5 Gruppen-Modi:** **Linked / Einzeln / Relativ** (AttributeSlider + Toolbar + Multivalue-„—").
- **M6 Persistenz:** EFX-Felder serialisiert; **Fixture-Gruppen jetzt in der .lshow** (vorher verloren); ChannelRange-Migration.
- **M7 Demo:** `tools/build_movinghead_show.py` → `shows/MovingHead_Demo.lshow` (4 PAR + 2 MH + APC mini), self-verifizierend; End-to-End-Render bestätigt MH-Bewegung + sichtbar + Gobo/Farbe/Shutter über VC.
- **Kritischer Bonus-Fix:** `get_channels_for_patched` lädt `ranges` jetzt **eager** (sonst crashte `open_value_for` im Per-Frame-Renderer auf detachten Objekten).

Tests: `tests/test_moving_head_efx.py` (11) grün, Gesamtsuite **495 passed**.

---

---

## 1. Wie Moving Heads aktuell modelliert sind

- **Profile (DB):** `FixtureProfile` → `FixtureMode` → `FixtureChannel` (`src/core/database/models.py:65–93`).
  `FixtureChannel` trägt `attribute` (Freitext-String, **kein** ChannelType-Enum), `default_value`, `highlight_value`, `invert`, `resolution` ("8bit").
  Capability-Äquivalent = `ChannelRange(range_from, range_to, name)` — **ohne** semantischen `type` (kein "open"/"strobe"-Marker).
- **Profil-Quellen:** Builtin hardcoded in `fixture_db.py:145–348` (Generic MH Spot 8/16ch, MH Wash 7ch, …); ZQ01424 / ZQ02001 **nur als externe Skripte** `examples/add_zq0*.py` (NICHT in `_seed()`); QLC+-Import `qxf_import.py`; User-Editor.
- **Patch-Instanz:** `PatchedFixture` (`models.py:~100–111`) hat bereits `invert_pan`, `invert_tilt`, `swap_pan_tilt` — werden persistiert (`show_file.py:30/48/79`), aber **nirgends im Renderer ausgewertet** (totes Feld).
- **Kanal-Lookup:** zentral `get_channels_for_patched(fixture)` (`app_state.py:992`, gecacht). **Kein** `find_channel_by_attribute()` — jeder Konsument (efx, carousel, sequence, …) dupliziert dieselbe `for ch … if ch.attribute==attr`-Schleife.
- **Output-Pipeline:** `AppState._render_frame` → Default-Frame (Kanal-`default_value`) → `FunctionManager.tick` (EFX/Matrix `write()`) → Programmer-LTP `_apply_fixture_map` (`app_state.py:816–864`) → Commit. EFX-Pan/Tilt wird via `protect_addrs` sogar gegen Programmer geschützt.

## 2. Warum der EFX-Reiter auf Moving-Head-Gruppen NICHT wirkt (Root Cause)

**Verifiziert am Code.** Die EFX-Engine ist intakt (Phasen-Offset pro Fixture `efx.py:107`, Algorithmen CIRCLE/EIGHT/bounce `_calc`), aber sie wird nie mit den Fixtures der Gruppe gefüttert:

| # | Ursache | Beleg | Prio |
|---|---------|-------|------|
| P0 | **EFX folgt der Auswahl nicht.** Programmer bettet EFX als nacktes `EfxView()` ein — die Matrix daneben als `RgbMatrixView(follow_selection=True)`. | `programmer_view.py:443` vs `:454` | P0 |
| P0 | `EfxView` abonniert **nie** `SELECTION_CHANGED`, liest nie `selected_fids`/`selected_group_id`. | `efx_view.py:120–124` | P0 |
| P0 | `efx.fixtures` wird **nur** in `_add_fixture` befüllt — und das fügt **hartkodiert `patched[0].fid`** hinzu (oft ein PAR ohne Pan/Tilt). | `efx_view.py:381–382` | P0 |
| P0 | Folge: `efx.fixtures` ist leer → `write()` returnt sofort. | `efx.py:128` (`if not self.fixtures: return`) | P0 |
| P1 | Selbst bei korrekt zugewiesener Gruppe bleiben MH **dunkel**: `write()` setzt **nur Pan/Tilt**, weder Dimmer noch Shutter (MH-Default Dimmer=0). | `efx.py:110,143–149` | P1 |
| P2 | `invert_pan/tilt`, `swap_pan_tilt`, `pan_fine/tilt_fine` werden im EFX-Output ignoriert. | `efx.py:123–149` | P2 |

**Ausgeschlossen:** Channel-Mapping ("pan"/"tilt" existieren in allen Profilen), Output-Merge (EFX wird geschützt), Grand-Master (greift nur auf Intensität/Farbe).

## 3. Moving-Head-Capability-Analyse

- **Vorhandene Attribute** (Editor `fixture_editor.py:27–32` + QXF): intensity, color_r/g/b/w/a/uv, color_wheel, pan, tilt, pan_fine, tilt_fine, speed, shutter, gobo_wheel, gobo_rotation, prism, prism_rotation, frost, zoom, focus, macro, raw.
- **Lücken:** `cmy_c/m/y` & `iris` nur im QXF-Import, **nicht** im Editor-Dropdown → CMY-Fixtures manuell nicht definierbar. Keine `animation_wheel`, `gobo_shake`, separate `color_lime/cyan`.
- **`ChannelRange` ohne `type`** → Shutter-Open/Strobe, Farb-Slots, Gobo-Slots sind nur Freitext-Namen, **maschinell nicht auswertbar** → blockiert generische Schnellwahl (Abschnitt 13) und Auto-Open.
- **16-bit:** `resolution` immer "8bit". MSB/LSB-Kopplung: **EFX erledigt** (T-9, 2026-06-14, `EfxInstance.bit16`), VC-XYPad + PositionTool decken die manuelle Eingabe ab; Invert/Swap koppeln das 16-bit-Paar in `apply_pan_tilt_orientation`. Offen bleibt nur eine generische `resolution`-getriebene Kopplung im zentralen Programmer-LTP-Pfad (kein konkreter Bedarf).
- **Defaults:** `default_value` = zugleich Home; `highlight_value` existiert im Modell, wird **nirgends genutzt**. MH-Seeds: Pan/Tilt=128, Dimmer=0, Shutter=0.
- **Seed-Lücke:** ZQ01424/ZQ02001 fehlen in `_seed()` → bei frischer DB nicht vorhanden.

## 4. Dimmer/Shutter-Vertauschung — Einschätzung

> ⚠️ **ÜBERHOLT (2026-06-10):** Reale Gerätedaten des Nutzers haben die
> Vertauschung im **ZQ02001-Profil** doch bestätigt (Strobe gehört VOR den
> Dimmer: 9ch CH5/CH6, 11ch CH7/CH8; 9ch-Modus zudem ohne Fine-Kanäle, mit
> Gobo-FX + Reset). Profil korrigiert, `ensure_builtins()` aktualisiert
> Alt-DBs in-place. Details: [MOVING_HEADS.md](MOVING_HEADS.md),
> Tests: `tests/test_zq02001_profile.py`. Die Analyse unten bleibt als
> historischer Stand erhalten.

**Kein Vertauschen in den eingebauten Profilen nachweisbar.** Geprüfte Kanalfolgen sind alle korrekt:
- MH Spot 8ch: CH5=intensity, CH6=shutter (`fixture_db.py:203–214`)
- MH Spot 16ch: CH6=intensity, CH7=shutter (`:215–234`)
- MH Wash 7ch: CH3=intensity, CH7=shutter (`:235–245`)
- ZQ02001 11ch: CH7=intensity, CH8=shutter (`add_zq02001.py:102–114`, lt. Handbuch)

**Die vom Nutzer wahrgenommene "Vertauschung" ist sehr wahrscheinlich ein Symptom von Abschnitt 2/3:** MH bleibt dunkel, weil Shutter nicht auf Open / Dimmer 0 ist und nirgends automatisch geöffnet wird. → Fix = Shutter-Schnellwahl + Auto-Open (Abschnitt 5), nicht Profil-Korrektur. *(Bei einem konkret betroffenen Fixture-Profil: Kanal-Reihenfolge gegen Handbuch gegenprüfen, bevor man am Profil ändert.)*

## 5. Vorschlag Programmer-Tabs / UI-Struktur

Bestehend (`programmer_view.py:300` QTabWidget): **Intensity · Color · Position · Weitere** + Funktions-Tabs (Helper · EFX · Matrix · Paletten). "Gobo" ist in `ATTR_GROUPS` definiert, wird aber in "Weitere" geworfen.

Ziel-Struktur:

| Tab | Inhalt | Schnellwahl |
|-----|--------|-------------|
| **Intensity / Shutter** | Dimmer-Fader **+ Shutter-Schnellwahl** (Open/Closed/Strobe langsam/mittel/schnell) | Auto-Open beim Aktivieren (capability-gestützt) |
| **Color** | RGB/CMY/Wheel-Fader **+ Farb-Kacheln** (White/Red/Green/Blue/Yellow/Purple…) | `ColorSwatch` wiederverwendet |
| **Gobo** *(nur bei Gobo-Kanal sichtbar, `setTabVisible`)* | Gobo-Slot-Kacheln, Gobo-Rotation, Rotation-Speed/Shake, Reset/Open | generisches `PresetTile` |
| **Position** | 2D-Pan/Tilt-Pad live + Fine + Speed + Invert/Swap-Toggles + Presets | (Abschnitt 6) |
| **EFX** | Bewegungs-EFX mit Follow-Selection (Abschnitt 7) | — |

**Kern-Baustein:** generisches **`PresetTile`**-Widget (Label + Farbe/Icon + DMX-Payload) auf Basis von `ColorSwatch` (`color_picker.py:150`) — einmal gebaut, genutzt für Color, Gobo, Shutter, Prism (= Abschnitt 13). Touch: `--touch`-Infra existiert, Tiles/Slider min-height 44px.

## 6. Position- / Pan-Tilt-Konzept

**Gute Nachricht:** 2D-Pad ist bereits gebaut — `PositionPad`/`PositionTool` (`position_tool.py:41–350`, Drag/Crosshair/Presets) **und** `VCXYPad`. Es fehlt nur die saubere Verdrahtung:

- `PositionTool._apply_to_selection()` nutzt aktuell `state.programmer.keys()` → auf **`state.selected_fids`** umstellen (`position_tool.py:340`).
- Pad live im Position-Tab einbetten (Toggle existiert `programmer_view.py:881`), per Default sichtbar/touchfähig.
- **Invert/Swap zentral** in `_apply_fixture_map` (`app_state.py:859–864`) anwenden — `fx`-Referenz ist dort vorhanden — und **dieselbe** Transform in `efx.write()`. Damit wirkt Invert/Swap auf manuell + EFX gleichzeitig.
- **Fine-Bug:** `position_tool.py:344–347` schreibt Fine nur wenn ≠0 → 0 wird nie zurückgesetzt. Fix.
- **Speed-Kanal** aus "Weitere" in Position-Gruppe heben (`programmer_view.py:91`).
- **Montage/Orientierung:** `StageElement` hat nur `rotation` (kein Fixture-Link), `PatchedFixture` keine 3D-Position. Vorschlag: `PatchedFixture.mounted_inverted: bool` (hängend → Tilt invertiert) + optional `StageElement.fixture_id`. P2.

## 7. Moving-Head-EFX-Konzept

Engine ist vorhanden (Algorithmen CIRCLE/EIGHT/bounce, Phasen-Offset pro Fixture). Ausbau:

1. **Follow-Selection** (P0, der eigentliche Fix): `EfxView(follow_selection=True)`, `SELECTION_CHANGED` abonnieren, `efx.fixtures` aus Gruppe/`selected_fids` neu bauen — **nur Pan/Tilt-fähige** Fixtures, Phase über Index verteilt. Vorbild: `rgb_matrix_view._assign_from_selection()` (`:941–981`).
2. **Sichtbarkeit** (P1): EFX optional Dimmer/Shutter öffnen (Checkbox „Dimmer/Shutter mit-öffnen") oder Highlight-Default anwenden — sonst bewegt sich ein dunkler Strahler.
3. **Bewegungs-Set** sicherstellen/ergänzen: Circle, Sweep (Pan/Tilt), Wave, Figure Eight, Tilt/Pan Bounce, Random.
4. **Gruppen-Verteilung:** Phase-Offset/Spread, gespiegelt (links/rechts), gegenläufig, symmetrisch — pro Gruppe einstellbar.
5. **Invert/Swap/Fine** in EFX (über zentrale Transform aus Abschnitt 6).

## 8. Gruppensteuerung — gemeinsam / einzeln / relativ

Heute: `AttributeSlider` schreibt denselben Wert auf **alle** `_selected_fids` (`programmer_view.py:1124–1127`) = faktisch nur „Linked". Snap/Scene speichern bereits **pro Fixture** (`snap_library.py`, `scene.py`).

| Modus | Verhalten | Anker |
|-------|-----------|-------|
| **Linked** (Default) | ein Control → alle Fixtures gleich | heute schon |
| **Einzeln** | Slider bezieht sich auf Template (`selected[0]`), andere unverändert; „—" bei Divergenz | `AttributeSlider` Mode-Param |
| **Relativ** | Delta `new−old` auf alle addieren (Fan bleibt erhalten) | `set_programmer_value(..., delta=True)` |

UI: `QButtonGroup` (Linked·Einzeln·Relativ) pro Attribut-Tab in `_build_group_tab`. Zusätzlich Sub-Fixture-Auswahl innerhalb der Gruppe (Checkboxen). Engine (`_apply_fixture_map`) bleibt unverändert (schreibt schon per-fid).

---

## 9. To-do-Liste (konsolidiert, priorisiert, dedupliziert)

IDs: M = Moving-Head-Initiative. Phasen P0→P5 + Demo.

### Phase 0 — Fundament & der eigentliche Bug-Fix (P0)
| ID | To-do | Datei(en) | Risiko |
|----|-------|-----------|--------|
| **M0.1** | **EFX Follow-Selection** (EfxView wie Matrix; Gruppe→Pan/Tilt-Fixtures; Phase über Index). DER Haupt-Fix. | `programmer_view.py:443`, `efx_view.py`, `efx.py` | Mittel (zwei EfxView-Instanzen konsistent) |
| M0.2 | Zentrale **Invert/Swap-Transform** in `_apply_fixture_map` **und** `efx.write()` (Felder existieren bereits). | `app_state.py:859–864`, `efx.py:109` | Niedrig–Mittel (heißer Pfad) |
| M0.3 | Helper **`find_channel_by_attribute(fx, attr)` / `channel_addr_for(fx, attr)`** — entdoppelt 6+ Stellen, Basis für alles. | `app_state.py` | Niedrig |
| M0.4 | **EFX-Sichtbarkeit:** optional Dimmer/Shutter mit-öffnen, sonst bleibt MH dunkel. | `efx.py`, `efx_view.py` | Mittel (Layer/EE-02) |
| M0.5 | Quick-Fallback: `EfxView._add_fixture` nutzt **alle `selected_fids`** statt `patched[0]`. | `efx_view.py:381` | Niedrig |

### Phase 1 — Capabilities & Defaults (P1)
| ID | To-do | Datei(en) | Risiko |
|----|-------|-----------|--------|
| M1.1 | **ZQ01424 & ZQ02001 in `_seed()`** aufnehmen (für Demo-Show nötig). | `fixture_db.py`, `examples/add_zq0*.py` | Niedrig |
| M1.2 | **`ChannelRange.type`** (open/closed/strobe/color/gobo/prism) + Migration → ermöglicht generische Schnellwahl & Auto-Open. | `models.py:84`, `qxf_import.py`, Migration | Mittel (Schema) |
| M1.3 | `cmy_c/m/y`, `iris` in Editor-`CHANNEL_ATTRS`. | `fixture_editor.py:27` | Niedrig |
| M1.4 | Saubere **Open/Home/Highlight-Defaults** für Shutter/Pan/Tilt der MH-Profile; `highlight_value` nutzbar machen. | `fixture_db.py`, `app_state.py` | Niedrig |

### Phase 2 — Programmer-UI (P1)
| ID | To-do | Datei(en) | Risiko |
|----|-------|-----------|--------|
| M2.1 | **Gobo-Tab** eigenständig, `setTabVisible` per Capability. | `programmer_view.py:306,803` | Niedrig |
| M2.2 | **Shutter-Schnellwahl** im Intensity-Tab (Open/Closed/Strobe-Stufen). | `programmer_view.py:822` | Mittel (Open-Wert fixture-abh.) |
| M2.3 | Generisches **`PresetTile`**-Widget (Abschnitt 13). | neu: `widgets/preset_tile.py` | Niedrig |
| M2.4 | **Color-Kacheln** + **Gobo-Slot-Kacheln** via PresetTile. | `programmer_view.py`, `color_picker.py:150` | Mittel (Slot-Mapping ohne `type` unsicher → M1.2) |
| M2.5 | AttributeSlider/Tiles **Touch-Mindesthöhe** 44px. | `programmer_view.py:1073` | Niedrig |

### Phase 3 — Position Live (P1/P2)
| ID | To-do | Datei(en) | Risiko |
|----|-------|-----------|--------|
| M3.1 | **PositionTool folgt Selektion** (`selected_fids` statt `programmer.keys()`); Pad default eingebettet. | `position_tool.py:340`, `programmer_view.py:881` | Niedrig |
| M3.2 | **Fine=0-Bug** beheben. | `position_tool.py:344` | Niedrig |
| M3.3 | **Invert/Swap-Toggles + Speed-Fader** im Position-Tab; Speed in Position-Gruppe. | `programmer_view.py:91`, neu | Niedrig |
| M3.4 | **Patcher-Dialog: Checkboxen** invert_pan/tilt/swap. | `patch_view.py:42–93` | Niedrig |
| M3.5 | **Montage/Orientierung** `mounted_inverted` + `StageElement.fixture_id` (+Migration). | `models.py:109`, `stage_definition.py:34` | Mittel (Migration) |
| M3.6 | **VCXYPad** folgt `selected_fids`. | `vc_xypad.py:53` | Niedrig |

### Phase 4 — Moving-Head-EFX-Ausbau (P1/P2)
| ID | To-do | Datei(en) | Risiko |
|----|-------|-----------|--------|
| M4.1 | Vollständiges **Bewegungs-Set** (Sweep/Wave/Bounce/Random) + Parameter (Größe/Speed/Phase). | `efx.py`, `efx_view.py` | Mittel |
| M4.2 | **Gruppen-Verteilung:** Spread/Offset/gespiegelt/gegenläufig/symmetrisch. | `efx.py:102–111`, `efx_view.py` | Mittel |
| M4.3 | **Fine-Kanäle (16-bit)** in EFX optional. ✅ **erledigt 2026-06-14** (T-9): `EfxInstance.bit16` (Default an) zerlegt die Float-Position per `_split16` in coarse+fine; coarse bit-identisch, Invert/Swap koppeln das Paar. | `efx.py` | Niedrig |
| M4.4 | **Pan/Tilt-Speed-Default** beim EFX-Start setzen. | `efx.py` | Niedrig |

### Phase 5 — Gruppen-Modi (P1/P2)
| ID | To-do | Datei(en) | Risiko |
|----|-------|-----------|--------|
| M5.1 | **Mode-Enum** (linked/individual/relative) in `AttributeSlider` + `set_programmer_value(delta=)`. | `programmer_view.py:1064`, `app_state.py:455` | Mittel (Thread-Safety) |
| M5.2 | **Mode-Umschalter-UI** je Attribut-Tab. | `programmer_view.py:822` | Niedrig |
| M5.3 | **Multivalue-Anzeige** „—" bei Divergenz. | `programmer_view.py:1124` | Mittel |
| M5.4 | **Sub-Fixture-Auswahl** innerhalb Gruppe. | `programmer_view.py` Fixture-Panel | Mittel |
| M5.5 | Mode + (optional) Gruppen-ID in `ui_prefs.json`/Snap persistieren. | `snap_library.py` | Niedrig |

### Phase 6 — Save/Load/Migration (begleitend, P0 pro Feld)
| ID | To-do | Risiko |
|----|-------|--------|
| M6.1 | Migration/Defaults für alle neuen Felder (invert/swap/mount/group-mode/presets/efx-offset). Alte Shows laden ohne Crash, fehlende Felder → Default. | Mittel |
| M6.2 | Roundtrip-Tests (save→reload) headless für jedes neue Feld. | Niedrig |

### Phase 7 — Leit-Demo-Show
| ID | To-do |
|----|-------|
| M7.1 | `tools/build_movinghead_show.py` → Show: **4 PAR (Mitte) + je 1 MH links/rechts** + APC mini. Nutzt Gobo/Color/Shutter-Schnellwahl, Position-Presets, Pan/Tilt-EFX (Spread/Mirror), Gruppen-Modi. Verifiziert VC-Wiedergabe der Gobo/Color-Werte. Doku `docs/MOVING_HEAD_SHOW.md`. |

## 10. Abhängigkeiten

```
M0.3 (Helper) ─┬─> M0.2 (Invert/Swap) ──> M3.4 (Patcher-UI), M4.x
               ├─> M2.x (UI-Schnellwahl, Channel-Lookup)
               └─> M3.x (Position)

M0.1 (Follow-Selection) ──> M0.4 (Sichtbarkeit) ──> M4.x (EFX-Ausbau)
M0.1 ──> M7.1 (Demo)

M1.2 (ChannelRange.type) ──> M2.2 (Shutter-Quickselect), M2.4 (Color/Gobo-Slots), M2.3-Payload
M1.1 (Seed ZQ) ──> M7.1 (Demo braucht die Strahler)

M2.3 (PresetTile) ──> M2.2, M2.4, M2.1 (Gobo-Tiles)

M5.1 (Mode-Enum) ──> M5.2, M5.3, M5.4, M5.5

M6.1/M6.2 begleiten JEDES Feature mit neuem persistenten Feld (M0.2/M3.4/M3.5/M5.x).
```
**Kritischer Pfad für den Nutzer-Schmerz:** M0.3 → M0.1 → M0.4 → (M1.1) → M7.1.

## 11. Subagent-Aufteilung für die Umsetzung

| Agent | Modell | Scope | To-dos |
|-------|--------|-------|--------|
| A — Engine/State | Opus/Sonnet stark | Helper, Invert/Swap, EFX-Follow+Ausbau, Render-Merge | M0.1–M0.5, M4.x, M6.1 |
| B — Fixture-DB/Caps | Sonnet | Seed, ChannelRange.type, Editor-Attrs, Defaults, Migration | M1.1–M1.4, M6.2 |
| C — Programmer-UI | Sonnet | Gobo-Tab, Shutter/Color/Gobo-Schnellwahl, PresetTile, Touch | M2.1–M2.5 |
| D — Position-UI | Sonnet | 2D-Pad-Anbindung, Invert/Swap-Toggles, Patcher-Checkboxen, Mount | M3.1–M3.6 |
| E — Gruppen-Modi | Sonnet | Linked/Einzeln/Relativ, Sub-Select, Persistenz | M5.1–M5.5 |
| F — Show/Tests | Sonnet | Demo-Show, headless-Verifikation, Smoke-Tests | M7.1, M6.2 |

Reihenfolge: **A(Phase0) → B(Phase1) parallel C/D-Vorbereitung → C/D/E → A(Phase4) → F**. Jeder Agent: erst Diff vorschlagen, dann nach Freigabe schreiben; headless `QT_QPA_PLATFORM=offscreen` + `pytest`.

## 12. Wahrscheinlich betroffene Dateien

- **Engine/State:** `src/core/app_state.py` (Helper, `_apply_fixture_map`, `set_programmer_value`), `src/core/engine/efx.py`, `src/ui/views/efx_view.py`
- **Fixtures:** `src/core/database/models.py`, `fixture_db.py`, `qxf_import.py`, `fixture_editor.py`, `examples/add_zq0*.py`
- **Programmer-UI:** `src/ui/views/programmer_view.py`, neu `src/ui/widgets/preset_tile.py`, `src/ui/widgets/color_picker.py` (ColorSwatch)
- **Position:** `src/ui/widgets/position_tool.py`, `src/ui/views/patch_view.py`, `src/ui/virtualconsole/vc_xypad.py`, `src/core/stage/stage_definition.py`
- **Show/Persistenz:** `src/core/show/show_file.py`, `src/core/engine/snap_library.py`, `src/core/engine/scene.py`, `palette.py`
- **Tools/Doku:** `tools/build_movinghead_show.py` (neu), `docs/MOVING_HEAD_SHOW.md` (neu)

## 13. Generisches Schnellwahl-/Preset-System (Querschnitt)

Statt zwei Sonderlösungen (Color, Gobo): **ein** `PresetTile` (Label + Farbe/Icon + DMX-Wert/-Bereich) + ein Resolver, der pro Kanal aus `ChannelRange` (nach M1.2 mit `type`) die Presets ableitet. Geeignet für Color Wheel, Gobo Wheel, Shutter, Prism, Frost, Focus, Macros. **Fallback auf Fader**, wenn keine Capability-Daten → keine geratenen Werte. Später in VC nutzbar.

## 14. Testplan (Auszug, vollständig je To-do in Spalte „Testfall")

- **EFX/Gruppe:** MH-Gruppe wählen → EFX → Start → alle MH bewegen Pan/Tilt; mit Offset/Spread; mit invert_pan/tilt; mit swap. (M0.1/M0.2/M4.x)
- **Color:** Fader **und** Kachel setzen Werte; Linked setzt alle, Einzeln nur Template; save/reload. (M2.4/M5.x)
- **Gobo:** Tab nur bei MH sichtbar; Kachel setzt korrekten Wert; Rotation/Shake wenn Kanal da; save/reload. (M2.1/M2.4)
- **Dimmer/Shutter:** Dimmer = Helligkeit, Shutter Open/Closed/Strobe korrekt; MH geht zuverlässig an; alte Shows laden ohne Crash. (M2.2/M1.4/M6.1)
- **Position:** 2D-Pad live + Touch; invert/swap/Orientierung wirken; Speed-Kanal greift. (M3.x)
- **Gruppen:** Linked/Einzeln/Relativ; keine ungewollten Überschreibungen. (M5.x)
- **Save/Load:** jedes neue Feld Roundtrip; Legacy-Shows migrieren. (M6.x)

> **Verifikation immer headless:** `QT_QPA_PLATFORM=offscreen`, `venv\Scripts\python.exe`, danach `pytest`.

## 15. Wichtigste Risiken

1. **Heißer Render-Pfad** (`_apply_fixture_map`): Invert/Swap dürfen Performance/andere Fixtures nicht beeinträchtigen — eng gefasste Bedingung nur für pan/tilt.
2. **Zwei EfxView-Instanzen** (Programmer-Tab + Sub-Tab) konsistent halten.
3. **Schema-Migrationen** (ChannelRange.type, mounted_inverted, group-mode): alte `.lshow`/DB müssen ohne Crash laden — Defaults Pflicht (M6.1).
4. **Gobo/Color-Slot-Mapping** ohne `ChannelRange.type` = Raten → erst M1.2, sonst nur Fader (kein Wert erfinden).
5. **EE-02/Layer-Interaktion** bei EFX-Auto-Open (Dimmer-Master) nicht durchbrechen.
