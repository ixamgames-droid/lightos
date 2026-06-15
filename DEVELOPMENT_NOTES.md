# DEVELOPMENT NOTES — Umsetzungsrunde 2026-06-10 (P1–P13)

> Ergänzt [docs/OPEN_POINTS_OVERVIEW.md](docs/OPEN_POINTS_OVERVIEW.md) (zentrale
> Offene-Punkte-Liste) und [ARCHITECTURE.md](ARCHITECTURE.md) (kanonische
> Architektur). Diese Datei dokumentiert die Auftragsrunde „P1–P13 +
> UI-Audit" — behobene Bugs, kritische Stellen, entfernte Workarounds und
> offene Punkte.

## Behobene Bugs / Ursachen

| # | Problem | Ursache | Fix |
|---|---------|---------|-----|
| P1 | Kein intelligenter Kanalvorschlag | Logik existierte nicht | **Neu:** `AppState.suggest_address(universe, channel_count)` ([src/core/app_state.py](src/core/app_state.py)) — lückenbewusst, pro Universum; UI-Anbindung im Fixture-Browser (Vorschlag + Warnung bei vollem Universum) |
| P2 | Listen-Auswahl ohne Canvas-Highlight, kein Multi-Select | Liste war `SingleSelection`, Sync nur Canvas→State | Multi-Select (Strg/Shift), bidirektionaler Sync Liste↔Canvas↔`set_selected_fids` (SELECTION_CHANGED) |
| P3 | Gruppenname in Live View nicht editierbar | Nur Read-only-Label | Editierbares Namensfeld im Gruppen-Panel (leer = verworfen, GROUP_CHANGED verteilt) |
| P4 | Live-View-Zustand unvollständig gespeichert | Nur Positionen in der Show; Zoom/Grid/Snap nur in ui_prefs | **`state.live_view_meta`** wandert mit der Show (`live_view.meta` in show.json); alte Shows: Fallback auf ui_prefs. Auto-Save jetzt **dirty-basiert** (inkl. neuem `SyncEvent.LIVE_VIEW_CHANGED`) |
| P5 | Gruppen nicht voll editierbar; Ordner fehlten im Programmer | `_refresh_group_list` ignorierte `FixtureGroup.folder` (`order_by(name)`) | „Umbenennen"-Button im Patch-Gruppen-Editor; Programmer-Gruppenliste zeigt Ordner-Kopfzeilen (sortiert nach folder+name) |
| P6 | Weiß = RGB voll **plus** W voll | `COLOR_PRESETS`-Payload setzte beides stumpf | **Neu:** `src/core/color_utils.py` (`adapt_color_payload`) — RGBW-Konvertierung (w=min(r,g,b), RGB reduziert); angebunden in Quick-Colors (`preset_tile._apply_payload`) und ColorPicker (nur wenn W-Slider=0 → manuelle W/A/UV bleiben bewusste Konfiguration) |
| P7 | Slider folgten externen Änderungen nicht | `AttributeSlider` las State nur beim Rebuild | ProgrammerView abonniert `PROGRAMMER_CHANGED` (30-ms-Coalescing-Timer) → `_load_current_value()` aller Slider (blockSignals = keine Echos; gedrückte Slider werden übersprungen) |
| P8 | Position-Tool verschob/überlappte das Layout | dynamisches addWidget/deleteLater per Toggle-Button | **Neu:** wiederverwendbares `CollapsibleSection`-Widget ([src/ui/widgets/collapsible_section.py](src/ui/widgets/collapsible_section.py)); Position-Tool fest im Layoutfluss, Zustand in ui_prefs |
| P9 | Pan/Tilt-Invert-Crash | (a) Zombie-Subscriber-Klasse (siehe crash.log-Fixes vom 2026-06-10: `subscribe_widget` + Selbstheilung in `StateSync.emit`); (b) **neu gefunden:** `apply_pan_tilt_orientation._invert` warf bei nicht-numerischen Werten ungefangen im Render-Thread | (a) bereits strukturell gefixt + Regressionstest `tests/test_invert_crash_regression.py`; (b) defensive int-Konvertierung |
| P10 | Split-Colors unübersichtlich | alle Farbrad-Slots in einem Grid | Split-/Half-Colors in eigenem `CollapsibleSection` (eingeklappt, ausgeblendet wenn keine vorhanden) |
| P11 | EFX-Reiter gestaucht, Vorschau = blauer Punkt | eine überladene Form; Trail-Preview | Editor in 3 Gruppen (Form&Geometrie / Tempo&Richtung / Sichtbarkeit&Verteilung) in ScrollArea; **Pfad-Visualisierung** (echte `_calc`-Samples, Richtungspfeil, animierte Fixture-Punkte mit Fan/Mirror, Statuszeile) |
| P12 | APC-Mini-Status unklar | — | Verifiziert: `page_select`-Mapping, VC-Banken (≥8), Templates, LED-Feedback, Persistenz (global `data/midi_mappings.json` + VC-Bindings in der Show). Details: docs/APC_*.md + docs/DEMO_SHOW_NOTES.md |

## Entfernte Workarounds
- „Position Tool einbetten"-Toggle (dynamisches Widget-add/delete) → ersetzt
  durch festen Aufklapp-Bereich (`_toggle_embedded_position` entfernt).
- Direkte `state.selected_fids = …`-Zuweisungen in der Live View → zentraler
  Setter `set_selected_fids` (emittiert SELECTION_CHANGED).
- Blindes 5-Minuten-Auto-Save → dirty-basiert (kein unnötiger Disk-Write).

## Kritische Stellen für künftige Änderungen
- **Render-Pfad/Merge:** `AppState._render_frame` + `docs/OUTPUT_MERGE_CONTRACT.md` — JEDE neue Wertquelle muss sich als Schicht einordnen.
- **Event-Bus:** Views, die zerstört/neu gebaut werden können, MÜSSEN `sync.subscribe_widget(event, self, cb)` nutzen (nie nacktes `subscribe` mit Lambda) — sonst Zombie-Subscriber (Crash-Klasse aus crash.log).
- **Farb-Logik:** Farb-Payloads immer durch `core/color_utils.adapt_color_payload` schicken (White-Kanal-Regel an EINER Stelle).
- **Programmer-Slider:** externe Wertänderungen laufen über `PROGRAMMER_CHANGED` → `_refresh_sliders_from_state` (kein direktes Slider-Setzen von außen).
- **Persistenz:** Neue Show-Bestandteile in `show_file.py` IMMER mit Fallback für alte Shows (Beispiel: `live_view.meta`); `reset_show()` mitziehen.
- **Auto-Save:** neue änderbare Zustände brauchen ein SyncEvent (oder `LIVE_VIEW_CHANGED`-Analog), sonst sieht das Dirty-Flag sie nicht.

## Offene Punkte aus dieser Runde
- UI-Audit-Restliste („manuell prüfen") → siehe Abschlussbericht im Repo-Verlauf; echte Sichtprüfung am Gerät steht aus (offscreen-Tests können „abgeschnitten" nicht sehen).
- Gruppen-Dimmer als APC-Fader: nur über Funktions-/Master-Fader abbildbar (kein direkter „Gruppen-Dimmer-Fader"-Modus im Mapper) — als Wunsch in docs/OPEN_POINTS_OVERVIEW.md.
- ColorPicker zeigt aktuellen Programmer-Wert nicht an (nur senden) — Folge-Idee: bidirektionaler Sync wie P7.
- Weitere offene Punkte zentral: [docs/OPEN_POINTS_OVERVIEW.md](docs/OPEN_POINTS_OVERVIEW.md) (B-1 sACN-Hardware, B-8 Lock-freier UI-Lesezugriff, T-9 16-bit-Kopplung, X-1 ZQ02001-Hardware-Verifikation, B-10 Freeze-Watchdog-Beobachtung).

## Neue/zentrale Utilities dieser Runde
| Utility | Ort | Zweck |
|---|---|---|
| `suggest_address` | src/core/app_state.py | nächster freier zusammenhängender Kanalbereich |
| `adapt_color_payload` / `fixture_attr_set` | src/core/color_utils.py | RGBW-Weiß-Konvertierung pro Fixture |
| `CollapsibleSection` | src/ui/widgets/collapsible_section.py | Accordion mit Pfeil + ui_prefs-Persistenz |
| `StateSync.subscribe_widget` | src/core/sync.py | lebenszeit-gebundene Event-Subscriptions |
| `SyncEvent.LIVE_VIEW_CHANGED` | src/core/sync.py | Dirty-Signal für Live-View-Layout |
| Freeze-Watchdog | main.py | Thread-Dump in crash.log bei UI-Stillstand >10 s |

## Tests dieser Runde (neu)
`test_address_suggest.py` (8), `test_color_white_channel.py` (7),
`test_slider_sync.py` (3), `test_live_view_meta_persist.py` (2),
`test_invert_crash_regression.py` (2), `test_sync_safe_subscribe.py` (4),
`EfxBounceTest` in `test_moving_head_efx.py` (4).
