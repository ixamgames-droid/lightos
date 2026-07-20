# Anleitungen-Audit — 2026-07-20 · Phase 3 (indizierte/verwandte Guides, Batch 1)

Fortsetzung von [Phase 1](ANLEITUNGEN_AUDIT_2026-07-20.md) (12 Kern, #380) und
[Phase 2](ANLEITUNGEN_AUDIT_2026-07-20-p2.md) (ältere Standalone, #381). Phase 3 prüft die
**weiteren indizierten/verwandten Guides** (`anleitung_*`-Unterordner, „Verwandte Dokumente")
gegen den aktuellen Code. Dieser PR ist **Batch 1**.

## Ergebnis (Batch 1)

| Doc | Ergebnis |
|---|---|
| anleitung_vc_widgets/21_baukasten.md | ⚠️→✅ Body konsistent zum bereits vorhandenen „entfernt 2026-07"-Banner gemacht (Baukasten-Sektion historisch). |
| anleitung_web_remote/ANLEITUNG.md | ⚠️→✅ **Sicherheits-Sektion + Handy-URL** aktualisiert (Token-Auth seit 2026-07). |
| anleitung_tempo_controller | ✅ aktuell — alle Panel-Strings exakt (vc_tempo_bus_controller.py). |
| anleitung_bpm_manager | ✅ aktuell — 10-Genre-Preset-Tabelle (50 Werte) + Defaults matchen genre_presets.py / bpm_settings.py exakt. |
| anleitung_zwei_universen | ✅ aktuell — Ausgabe-Konfig exakt (output_config.py). |
| anleitung_programmer | ✅ aktuell — „✖ Clear ▾"-Menü + „Programmer → Szene" (main_window.py / programmer_view.py); Bank-Layout show-spezifisch. |

## Korrekturen

- **anleitung_web_remote (sicherheitsrelevant):** Das Guide beschrieb den alten unsicheren Stand
  („keine Authentifizierung, `cors_allowed_origins="*"`") und gab in §2 eine Handy-URL, die heute
  **403** liefert. Seit 2026-07-14 ([DESIGN_DECISION_REMOTE_SECURITY](DESIGN_DECISION_REMOTE_SECURITY_2026-07-14.md))
  ist das Remote **token-geschützt** (`?k=<token>`, `@before_request`-403-Gate, SocketIO lehnt
  unauth ab; app.py:225/155, remote_settings.py) mit **CORS-Allowlist** statt `"*"`
  (app.py:108/163) und LAN-Toggle-Bind. §2 (Token-URL), §4 (neu geschrieben) + Kurz-Referenz
  korrigiert. → Commit `cb966a5`.
- **anleitung_vc_widgets/21_baukasten:** hatte oben schon einen „entfernt 2026-07"-Banner, der
  Body beschrieb die entfernten VC-Baukasten-Knöpfe aber weiter im Präsens → konsistent gemacht
  (dreifach verifiziert entfernt, wie in #380/#381). → Commit `b02c2f9`.

## Offen (Phase 3, weitere Batches)

anleitung_vc_widgets/01–20 (Widget-Docs) · anleitung_matrix_effekte · anleitung_speed_bpm ·
anleitung_vc_smartbuild · anleitung_vc_workflow · anleitung_3d_visualizer_2026 ·
ANLEITUNG.md (8 Sektionen) · EFFEKTE.md · ANLEITUNG_TEMPO_SYNC.md · tutorial_matrix ·
Show-Walkthroughs (komplettshow_2026/*, hochzeit_komplett/*).
