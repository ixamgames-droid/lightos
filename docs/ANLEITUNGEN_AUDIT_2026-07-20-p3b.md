# Anleitungen-Audit — 2026-07-20 · Phase 3 Batch 2 (VC-Widget- & Feature-Docs)

Fortsetzung von [Batch 1](ANLEITUNGEN_AUDIT_2026-07-20-p3.md) (#382). Batch 2 prüft die
**VC-Widget-Docs** (`anleitung_vc_widgets/*`) und weitere Feature-Guides gegen den Code.

## Ergebnis (Batch 2)

| Doc | Ergebnis |
|---|---|
| vc_widgets/01_button.md | ⚠️→✅ **Aktionstabelle vervollständigt** — 3 fehlende Laser-Aktionen ergänzt. |
| vc_widgets/02_fader.md | ✅ 12-Modi-Liste = SLIDER_MODE_LABELS (vc_slider.py) exakt. |
| vc_widgets/03_farbe.md | ✅ 7-Ziel-Liste = ColorTarget (vc_color.py) exakt. |
| vc_widgets/04_xy_pad.md | ✅ 3 Modi + Feld-Params (vc_xypad.py) bestätigt. |
| vc_widgets/13_tempo_bus.md | ✅ Dialog „Bus-Auswahl" + buses/armed_bus_id (vc_bus_selector.py). |
| anleitung_matrix_effekte | ✅ 6 Effekte = reale RgbAlgorithm-Werte; Bank-Layout show-spezifisch. |

## Korrektur

- **vc_widgets/01_button:** Die Button-Aktionstabelle listete 26 der 29 Aktionen aus
  `BUTTON_ACTION_LABELS` (`vc_button.py:75-105`). Die 3 **Laser-Aktionen** — „Laser scharf/unscharf"
  (LAS-10), „Laser NOT-AUS", „Laser-Muster abrufen" (LAS-18) — fehlten (im Code zwischen „Blackout"
  und „Alles Weiß"). In Code-Reihenfolge ergänzt. → Commit `b08005b`.

Die übrigen geprüften Widget-Docs waren durchweg exakt (Enum-Listen 1:1 mit dem Code) — die
`anleitung_vc_widgets/`-Serie ist sehr gut gepflegt.

## Offen (weitere Batches)

Restliche Widget-Docs (05-12, 14-17, 20, 21 teils erledigt) + Feature-Docs EFFEKTE.md,
ANLEITUNG.md (8 Sektionen), tutorial_matrix, speed_bpm, vc_smartbuild/workflow, 3d_buehne;
Show-Walkthroughs (komplettshow_2026/*, hochzeit_komplett/*).
