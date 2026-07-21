# Anleitungen-Audit 2026-07-21 (Phase 5) — show-spezifische Cluster

Fortsetzung nach p4 (#415). Ziel: die **show-spezifischen** Guide-Cluster auf **code-prüfbare**
Drift prüfen (UI-Strings, Menü-/Feld-Labels, Meldungen, Enum-Optionen) — show-daten-spezifische
Bank-/Widget-Layouts sind beispielspezifisch und gelten nicht als Drift.

`anleitung_komplettshow_2026/*` war NICHT im Umfang — parallel in eigener Session als
PR #416 erledigt.

## Methode & Ergebnis

18 Guides je von einem Audit-Agenten gegen `src/` geprüft, jeder Fund adversarial
gegengeprüft (Workflow, wie p4). **7 bestätigte Funde in 6 Guides**, **12 Guides CLEAN**.

| Guide | Sev | Korrektur |
|---|---|---|
| `hochzeit_komplett/mini_farb_muster` | low | Regenbogen (RAINBOW) erzeugt eigene HSV-Töne und ist **nicht** per Farb-Kachel umfärbbar (steht nicht mehr unter „recolorbar") |
| `grosse_demo_2026` | low | „Hintergrundbild entfernen" steht im Kontextmenü **darunter**, nicht darüber |
| `test123_tempo` | **high** | Tempo/Bus-Werte setzt man im **Live-Einstellungen-Dialog per Long-Press** (VCLiveEditor, „Anwenden"), nicht über „⚡ Live-Parameter…" (das erzeugt VC-Bedienelemente, „Erzeugen") |
| `testshow_liveedit` | low | Regler-Labels „Läufer-Anzahl / Läufer-Breite" (mit Bindestrich) |
| `laser` | medium | Kein Fähigkeits-Banner oben im Laser-Tab; das ehrliche Banner sitzt im **Zeichen-Studio** (nur Netzwerk-Laser hat „✏️ Zeichnen…") |
| `LASER_GOBO_TEST` | low | L2600-Farbrad: 0-31 = „Vollfarbe"; „Cyan" liegt bei 128-159 |

## CLEAN (12)

hochzeit_komplett/00_INDEX · mini_ablaeufe · mini_bewegung_efx · mini_dimmer_bewegungen ·
mini_farbe_pro_gruppe · mini_gruenes_lauflicht · mini_live_editor · mini_musik_autoshow ·
mini_strobe_tempo · hochzeit_tempo · ablaeufe_mischen · ANLEITUNGEN_EVENT_DEMO.

Damit sind die offenen Nutzer-Guides (p4) **und** die show-spezifischen Cluster (p5 + #416)
gegen den aktuellen Code geprüft. Reine Doku-Änderung; Doc-Bild-Link-Check grün (252/0).
