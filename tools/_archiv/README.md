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

## Altgenerations-Builder (TOOLS-ALTGEN, 2026-07-27)

Aus den ~20 Kandidaten des Werkzeug-Audits sind **6** archiviert worden — die
uebrigen 14 bleiben in `tools/`, weil ein lebender Test, ein Begleit-Werkzeug
oder eine als aktuell gefuehrte `docs/`-Anleitung sie ausdruecklich als
**Regenerier-Quelle** nennt (Details im BACKLOG-Eintrag `TOOLS-ALTGEN`).
Gemeinsames Kriterium der 6: Ziel-Show liegt ausschliesslich in
`shows/_archiv/`, **kein** Test, **kein** Skill, **kein** Werkzeug und keine
gepflegte Anleitung mit „neu bauen"-Befehl verweist darauf.

| Skript | Ziel-Show (in `shows/_archiv/`) | Warum archiviert |
|---|---|---|
| `build_apc_probier_show.py` | `APC_Probier.lshow` | Einzige Referenz ist die Provenienz-Kopfzeile von `docs/APC_PROBIER.md` — ein Hardware-Test-Bug-Log vom 2026-06-11, dessen 11 To-Dos alle abgehakt sind und das das Repo selbst zweimal als „historisches Log / kein Walkthrough" fuehrt. |
| `build_custom_path_demo.py` | `CustomPath_Demo.lshow` | Keine eigene Anleitung; nur ein Changelog-Abschnitt in `docs/UPDATE_2026-06-11.md`. Die demonstrierten Features (Custom Paths, Keyboard-Mapping) sind dauerhaft ueber `tests/test_efx_path.py` / `tests/test_keyboard_mapping.py` abgedeckt. |
| `build_master_demo_show.py` | `Master_Demo.lshow` | `docs/MASTER_DEMO.md` nennt den Generator nur als Kopf-Attribution, ohne Aufruf-Befehl. Kein Test, kein Werkzeug, kein Skill. |
| `build_practice_show.py` | `Praxis_Demo.lshow` | Praxisvalidierung der Umsetzungsrunde 2026-06-10 (P1/P4/P5/P6/P10/P11) — ein erledigter Runden-Snapshot. Einzige Doku-Spur: eine Erwaehnung in `docs/DEMO_SHOW_NOTES.md`. |
| `build_profi_show.py` | `Profi_Modus.lshow` | Grenzfall: `docs/PROFI_MODUS.md` ist als „aktuell" gefuehrt, nutzt das Skript aber rein als Provenienz-/Seed-Nachweis, nicht als Regenerier-Befehl. |
| `build_vc_test_2026.py` | `VC_Test_2026.lshow` | Sauberster Fall — als einziger Kandidat **ohne** jede eigene `docs/`-Anleitung; ausser dem generierten `tools/README.md` gibt es repo-weit keine Referenz. |

## ⚠ Pfad-Fallstrick beim Archivieren (gefixt 2026-07-27)

Skripte in `tools/` leiten den Repo-Root aus der **Ordnertiefe** ab:

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

Aus `tools/` heraus stimmt das. Nach einem `git mv` in `tools/_archiv/` zeigt
dieselbe Zeile **eine Ebene zu tief — auf `tools/`**. Beim Werkzeug-Audit
2026-07-19 ist das allen neun damals verschobenen Skripten passiert und blieb
unbemerkt, weil danach keines mehr lief:

* der Repo-Root stand nicht mehr auf `sys.path` → jeder `from src.core… import`
  waere mit `ModuleNotFoundError` abgebrochen (die Skripte waren nicht nur
  ausgemustert, sondern schlicht **nicht mehr startbar**);
* `_ROOT`/`SHOW`/`OUT` zeigten auf `tools/shows/<Name>.lshow` statt auf
  `shows/<Name>.lshow` — ein reaktiviertes Skript haette seine Show
  klammheimlich in den Werkzeug-Ordner geschrieben.

**Regel seither:** archivierte Skripte holen sich den Repo-Root ueber
[`_bootstrap.py`](_bootstrap.py) (Marker-Suche nach dem Ordner mit `src/` +
`tools/`, statt Tiefen-Raten):

```python
import _bootstrap                  # Repo-Root + tools/ auf sys.path
import _gen_env  # noqa: F401      # spawn-sichere Env-Schalter + isolierte Show-DB
from src.core.app_state import get_state
...
_ROOT = _bootstrap.REPO_ROOT       # statt dirname(dirname(__file__))
```

`tests/test_tools_archiv_paths.py` haelt die Regel gruen. Damit ist
Archivieren wieder ein **reines `git mv`** — der Bootstrap funktioniert in
`tools/` wie in `tools/_archiv/`.

**Reaktivieren:** zurueck nach `tools/` schieben; `import _bootstrap` gegen die
uebliche `sys.path`-Zeile tauschen (oder stehen lassen — der Marker-Bootstrap
funktioniert auch aus `tools/`) und pruefen, dass `import _gen_env` vorhanden
ist (setzt seit STAB-CURSHOW (a) eine isolierte `LIGHTOS_SHOW_DB`). Show-Pfade
zum Lesen ueber `from _showpath import find_show` aufloesen (prueft `shows/`
**und** `shows/_archiv/`).
