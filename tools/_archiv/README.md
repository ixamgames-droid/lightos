# tools/_archiv — ausgemusterte Einmal-Werkzeuge

Spiegel zur Konvention `shows/_archiv/` (Davids Show-Archiv): Skripte hier sind
**bewusst ausgemustert**, bleiben aber versioniert nachlesbar. Sie werden von
keinem Skill, keiner Doku-Anleitung und keinem Test mehr aufgerufen
(Werkzeug-Audit 2026-07-19). Grund je Datei:

| Skript | Warum archiviert |
|---|---|
| `verify_matrix_group_scope.py` | Einmal-Regressions-Check von Juni 2026; Prueflogik lebt dauerhaft in `tests/test_matrix_group_scope.py`. Gefahr im Altzustand: ohne `LIGHTOS_SHOW_DB` traf `reset_show()` + `delete(FixtureGroup)` die echte `data/current_show.db`. |
| `_shot_matrix_group_scope.py` / `_shot_matrix_group_scope_live.py` | Screenshot-Begleiter des obigen Checks; Ziel-Show `Matrix_Gruppen_Test.lshow` ist archiviert. Der `_live`-Variante fehlten zudem die `LIGHTOS_`-Praefixe der Hardware-Gates (Output-Thread/Audio starteten real). |
| `verify_efx_group_scope.py` | Wie Matrix-Pendant: durch `tests/test_efx_group_scope.py` abgedeckt; gleicher DB-Footgun. |
| `verify_komplett_demo.py` | Verifikator der Komplett_Demo-Runde (Juni); Ziel-Show liegt in `shows/_archiv/`, hartkodierte IDs (Funktion 74, fids 5/6) binden ihn an genau diese Show. |
| `patch_stage_show_pages.py` + `build_stage_show.py` | Paar (Builder + In-Place-Patcher) fuer `Buehnen_Show.lshow` (archiviert). Der Patcher schrieb die `.lshow` nur mit `show.json` zurueck — wuerde heute `assets/vc/*` (VC-IMG) stillschweigend verwerfen. |
| `build_hardstyle_vc.py` | In-Place-Umbau der archivierten `Hardstyle_Show.lshow`; Nachfolger ist die Mega-Arena-Generation. |
| `build_snaps_show.py` | APC-Snap-Runde; ueberschrieb `%APPDATA%/LightOS/snapshots.json` **und** die Crash-Recovery-Autosave `auto_save.lshow` der echten App. |
| `diag_hardstyle.py` / `diag_movers.py` | Erledigte Einmal-Diagnosen (Beat-Blink bzw. Mover-DMX) gegen inzwischen archivierte Shows. |

**Reaktivieren:** zurueck nach `tools/` schieben und die Kopfzeilen an die
aktuellen Konventionen anpassen — `import _gen_env` (setzt seit STAB-CURSHOW (a)
auch eine isolierte `LIGHTOS_SHOW_DB`) und Show-Pfade ueber
`from _showpath import find_show` aufloesen (prueft `shows/` + `shows/_archiv/`).
