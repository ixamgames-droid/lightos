# tools/ — Werkzeug-Index

> **Generiert** von `tools/gen_tools_index.py` — nicht von Hand pflegen;
> nach neuem/umbenanntem Tool den Generator laufen lassen
> (`tests/test_tools_index.py` erinnert daran). Zweck-Zeile = erste
> Docstring-/Synopsis-Zeile des Skripts.

| Werkzeug | Zweck |
|---|---|
| `_builder.py` | Gemeinsame Build-Boilerplate für tools/build_*.py — ersetzt das ~95% copy- |
| `_gen_env.py` | Spawn-sichere Bootstrap-Schicht fuer alle ``tools/build_*.py``-Generatoren (DEMO-02). |
| `_run_showcase_app.py` | Wegwerf-Launcher fuer die Doku-Captures: startet LightOS UND laedt direkt die |
| `_showpath.py` | Show-Datei-Aufloesung fuer tools/-Skripte: shows/ mit Fallback shows/_archiv/. |
| `app.ps1` | LightOS App-Treiber — App starten/stoppen/warten/screenshotten aus EINEM Skript. |
| `audit_tooltip_coverage.py` | QA-13 Tooltip-/Label-Coverage-Audit fuer interaktive Steuerelemente. |
| `backlog_compact.py` | Backlog-Verdichter + Queue-View fuer BACKLOG.md (Loop-Werkzeug). |
| `benchmark_universes.py` | T-8 / RM-Benchmark — Render-Performance fuer mehrere Universen. |
| `build_apc_probier_show.py` | APC-PROBIER-SHOW — Testfeld fuer Davids reales Setup (4 PAR + 2 MH + APC mini). |
| `build_apc_test_show.py` | KOMPLETTE Test-/Demo-Show fuer Davids reale Hardware: |
| `build_custom_path_demo.py` | DEMO: Custom Paths + EFX-Live-Steuerung + Keyboard-Mapping (2026-06-11). |
| `build_demo_show.py` | Erzeugt eine komplett vorprogrammierte Demo-Show (.lshow) fuer die 3 RGBW-PARs |
| `build_demo_show_full.py` | DEMO SHOW FULL — komplette, nach ZWECK organisierte Show auf Davids realem Rig. |
| `build_demo_zq_show.py` | Demo-/Bühnen-Show fuer Davids reale Hardware (DMO-01, Masterplan 2026-06-08): |
| `build_event_demo_2026.py` | EVENT-DEMO 2026 — grosse, vollstaendige Demo-Show fuer ein Event. |
| `build_farb_fx_vc_show.py` | FARB-/EFFEKT-VC-SHOW — 4-Seiten Virtual Console fuer Davids Rig. |
| `build_feature_showcase.py` | FEATURE-SHOWCASE — die "alles drin"-Test-/Demo-Show. |
| `build_feature_test_show.py` | FEATURE-TEST-SHOW — spielt ALLE neuen Funktionen vom 2026-06-12 durch. |
| `build_full_show.py` | Komplette Demo-Lightshow fuer 3 RGBW-PARs + APC mini mk2 (v4). |
| `build_grosse_demo_show_2026.py` | Grosse Demo-/Testshow 2026 — ~30 Fixtures, mehrere VC-Bank-Seiten, animierte |
| `build_grosses_rig.py` | Grosses Rig 2026 — komplette Show mit Trassen-Rig (Davids Auftrag 2026-07-08). |
| `build_hochzeit_komplett.py` | HOCHZEIT KOMPLETT 2026 — Feature-Demo auf Davids Hochzeits-Rig. |
| `build_komplett_demo_show.py` | KOMPLETT-DEMO-SHOW: alle Features der Software auf Davids realer Hardware. |
| `build_komplette_animierte_show.py` | „Komplette Show mit animierten Buttons" — volle Test-Show (Laser + Gobo-Moving- |
| `build_laser_gobo_test.py` | „Laser Gobo Test 2026" — Test-Show mit Laser + Gobo-Moving-Heads + PARs + Nebel |
| `build_live_demo_show.py` | Demo-Show fuer das LIVE-PROGRAMMING der RGB-Matrix (Phase 7 der Matrix-Initiative). |
| `build_live_edit_show.py` | LIVE-EDIT-SHOW — vordefinierte Effekte live einmappen & bearbeiten (Quadranten). |
| `build_master_demo_show.py` | MASTER-DEMO-SHOW — „alles, was die Show jetzt kann", auf mehrere Banks verteilt. |
| `build_mega_arena_2026.py` | MEGA ARENA SHOW 2026 — die grosse Hardstyle-Arena-Demo auf einem 4-Trassen-Rig. |
| `build_movinghead_show.py` | LEIT-DEMO-SHOW: Moving Heads + PARs + APC mini (Moving-Head-Initiative). |
| `build_musik_show_2026.py` | MUSIK SHOW 2026 — Auto-Lichtshow, die zur Musik im BPM-Takt mitläuft. |
| `build_neue_demo_show.py` | NEUE DEMO 2026 — Quadranten-Layout + echtes PLAYBACK, alles auf einer Show. |
| `build_party_demo_show.py` | PARTY DEMO 2026 — BPM-getaktete Party-Show + Musik-Playlist. |
| `build_practice_show.py` | PRAXIS-DEMO-SHOW (P13): Praxisvalidierung aller neuen Funktionen der |
| `build_profi_show.py` | PROFI-MODUS-SHOW — sektioniertes Quadranten-Layout (APC-Probier To-Do #11). |
| `build_test_show.py` | Erzeugt eine KOMPLETT vorprogrammierte Test-Show (.lshow) zum Anschauen aller |
| `build_testshow_2026.py` | TESTSHOW 2026 — komplette musik-synchrone Show für Davids reales Rig. |
| `build_tutorial_matrix_show.py` | TUTORIAL_MATRIX — Begleit-Show zur bebilderten Schritt-fuer-Schritt-Anleitung. |
| `build_uxtest3_full.py` | UXTEST-3 „Full Rig" — 30-Fixture-Test-Show für den UI-Audit (Davids Auftrag 2026-07-15). |
| `build_validated_demo.py` | Beispiel-/Proof-Show über die ShowBuilder-DSL — baut eine kleine, ECHTE Show, |
| `build_vc_elements_showcase.py` | VC-Elemente-Schaukasten: legt JEDEN der 15 VC-Widget-Typen einmal beschriftet |
| `build_vc_test_2026.py` | VC-TEST-SHOW 2026 — Rig-Positionen + Gruppen + sofort leuchtende Test-Effekte |
| `build_vc_widgets_showcase.py` | VC-Widgets-Schaukasten (Doku) — legt JEDEN der 18 VC-Widget-Typen einmal |
| `capture_hochzeit_tempo_guide.py` | Reproduzierbare Screenshots für die Hochzeit-Tempo-Anleitung. |
| `capture_test123_tempo_guide.py` | Reproduzierbare Screenshots fuer die Test123-Tempo-Anleitung. |
| `check_demo_show_full.py` | Prueft shows/Demo_Show_Full.lshow headless und rendert echte Bilder: |
| `check_doc_images.py` | DOC-10 Anleitungs-/Bild-Audit: findet TOTE Bild-Links in der Doku. |
| `check_doc_links.py` | QA-17 Doc-Link-Checker: findet TOTE relative Markdown-Querverweise. |
| `crop_vc_widgets.py` | Cropper fuer die VC-Widget-Doku: schneidet aus EINEM Vollbild-Screenshot |
| `gallery_server.py` | DOC-11 Galerie-Render-Server (Dev-/Doku-Werkzeug). |
| `gen_capabilities.py` | Erzeugt den Agenten-Vertrag aus dem Code: docs/CAPABILITIES.md + |
| `gen_tools_index.py` | Generiert tools/README.md — Index aller Werkzeuge mit Zweck-Zeile. |
| `gen_vc_gallery.py` | Erzeugt die eingebaute VC-Button-Grafik-Galerie (Bilder + animierte GIFs mit |
| `import_qlc_input_profile.py` | CLI-Wrapper: QLC+-Inputprofil (.qxi) → LightOS-Controller-Profil (JSON). |
| `janitor.py` | Worktree-, Branch- und Artefakt-Hygiene fuer den LightOS-Loop (report-first). |
| `lint_show.py` | CLI: prüft eine oder mehrere .lshow (oder show.json) gegen die echten |
| `render_apc_pages.py` | Rendert jede Seite (VC-Bank) der APC-Test-Show als PNG — fuer die Anleitung. |
| `render_neue_demo_pages.py` | Rendert die 5 Banks der Neue_Demo_2026-Show als PNG (für die Doku/Vorschau). |
| `ui_verification_checklist.py` | QA-12 UI-Verifikations-Checklisten-Generator/-Checker. |
| `vc_click_targets.py` | Berechnet aus einem Vollbild-Screenshot (mit der Magenta-Kalibrier-Kachel |
| `verify_color_dimmer_separation.py` | Verifikation: Trennung FARBE <-> DIMMER an Effekten (Color/Matrix/Chase). |
| `verify_loop.ps1` | tools/verify_loop.ps1 - Test-Gate fuer den LightOS Loop-Modus |

## _archiv/ — ausgemustert

Begruendungen: [tools/_archiv/README.md](_archiv/README.md).

- `_archiv/_shot_matrix_group_scope.py`
- `_archiv/_shot_matrix_group_scope_live.py`
- `_archiv/build_hardstyle_vc.py`
- `_archiv/build_snaps_show.py`
- `_archiv/build_stage_show.py`
- `_archiv/diag_hardstyle.py`
- `_archiv/diag_movers.py`
- `_archiv/patch_stage_show_pages.py`
- `_archiv/verify_efx_group_scope.py`
- `_archiv/verify_komplett_demo.py`
- `_archiv/verify_matrix_group_scope.py`
