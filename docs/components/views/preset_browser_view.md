# preset_browser_view (PresetBrowserView)

> Durchsuchbarer Browser über alle Paletten + Fixture-Gruppen (UI-01).

## Zweck

Schneller, filterbarer Einstieg zu den vorhandenen Presets. Listet Paletten
(🎨) und Fixture-Gruppen (👥) gemeinsam und filtert live über ein Suchfeld.
Auswahl wendet das Preset auf die aktuelle Programmer-Auswahl an bzw.
selektiert die Gruppe.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Suchfeld | Live-Filter über Paletten + Gruppen |
| Kind-Präfix (`_KIND_PREFIX`) | 🎨 Palette · 👥 Gruppe |
| Eintrag anwenden | Palette auf Auswahl anwenden / Gruppe selektieren |

## Verknüpfungen

- **PaletteManager + Gruppen:** liest Paletten und Fixture-Gruppen frisch ein
  ([`palette_view`](palette_view.md), [`fixture_group_view`](fixture_group_view.md)).
- **Bus:** abonniert Änderungs-Events (`bus.subscribe`), um die Liste bei
  Palette-/Gruppen-Änderungen neu zu filtern.
- **Programmer:** wendet auf die aktuelle Auswahl an (None = alle Geräte-Fallback).

## Zugehörige Tests

- `tests/test_preset_browser.py` — Filter, Anwenden, Präfixe.

## Quelle (file:line)

- `src/ui/views/preset_browser_view.py:22` — Klasse `PresetBrowserView`
- `src/ui/views/preset_browser_view.py:76` — Liste neu einlesen + filtern
- `src/ui/views/preset_browser_view.py:19` — `_KIND_PREFIX`
