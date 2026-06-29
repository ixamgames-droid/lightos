# Loop-Findings — beim Demo-/Anleitungs-Bau entdeckt

> Laufendes Log von **Bugs / Stolpersteinen / Verbesserungsideen**, die mir beim Bauen der
> `Hochzeit_Komplett_2026`-Show und der Minianleitungen (Übernahmemodus im echten UI) auffallen.
> **Loop-fertig formuliert** (Problem + Fix-Vorschlag + Akzeptanzkriterium), damit David später den
> Loop drüberlaufen lassen kann. Verlinkt aus [`BACKLOG.md`](../BACKLOG.md).
>
> Reihenfolge ≈ Relevanz. Stand: laufend (Session 2026-06-29).

| ID | Prio | Bereich | Titel | Problem → Fix → Akzeptanzkriterium |
|----|------|---------|-------|-------------------------------------|
| DEMO-02 | P2 | STAB/ENG | Generatoren ohne `__main__`-Guard → Windows-Spawn korrumpiert Patch | **Problem:** `tools/build_*.py` ohne `if __name__ == "__main__":`-Guard werden auf Windows von einem **vom OutputManager gespawnten Kindprozess** als `__mp_main__` re-importiert → zwei Prozesse bauen die Show, der FLD-FID-Guard in `add_fixture` vergibt verwaiste fids neu → **nur ein Teil der Fixtures landet** (Symptom: läuft als `python -c …` sauber, als Datei nur teilweise). **Fix:** Guard in alle Generatoren (oder die OutputManager-Serial-Isolation beim Headless-Build unterdrücken). **DoD:** jeder `build_*.py` headless ergibt reproduzierbar den vollständigen Patch; Test, der einen Generator headless baut und die Fixture-Zahl prüft. |
| DEMO-03 | P2 | STAB/ENG | `reset_show()` räumt verwaiste `current_show.db`-Patch-Zeilen nicht hart | **Problem:** Nach einem abgestürzten Generator-Lauf bleiben Patch-Zeilen in `current_show.db`. `reset_show()` (über `_replace_patch_from_data(state, [])`) löscht sie **nicht hart** (anders als `clear_patch()`) → der FLD-FID-Guard weicht beim nächsten Patch auf `next_fid()` aus (überraschend verschobene fids). **Fix:** `reset_show()` ruft zusätzlich `clear_patch()` (hartes `DELETE` der Patch-Tabelle), wie es `load_show` bereits tut. **DoD:** nach simuliertem verwaisten Eintrag liefert `reset_show()` + Patch die beabsichtigten fids; Test. |
| DEMO-04 | P2 | ENG/UX | Bus-gekoppelte Dimmer-Effekte gehen **dunkel**, wenn der Bus nicht läuft | **Problem:** Ein an einen Tempo-Bus gekoppelter **Dimmer-Matrix**-Effekt friert ein, wenn der Bus nicht getaktet wird (z. B. nicht armiert / bpm 0). Bei Dimmer-Style heißt „eingefroren" = **Intensität 0 = Fixtures dunkel** (nicht nur statisch). Headless reproduziert: `intensity`-Peak 0. **Fix:** Wenn der gekoppelte Bus steht (bpm 0 / nicht laufend), soll der Effekt **frei laufen** (Fallback auf `matrix_speed`) statt dunkel einzufrieren. **DoD:** bus-gekoppelte Dimmer-Matrix animiert auch bei gestopptem Bus (kein Black-out); Test. |
| DEMO-01 | P3 | QA/Tooling | Pad-Koordinaten-Formel in `lo.ps1`/Doku stimmt nicht fürs aktuelle Fenster | **Problem:** Die dokumentierte VC-Pad-Formel `pad(row,col) ≈ (98+133·col, 437+132·row)` (in `SHOW_AUTOBUILD_WORKFLOW.md` §4) trifft die Pads bei 2880×1920 nicht — real ist es ca. `(98+132·col, 530+135·row)`. Kostet beim Capture viel Kalibrierzeit (Fehlklicks: „grün" → „blau"). **Fix:** `lo.ps1 calib`-Befehl, der das Pad-Raster aus einem Vollbild-Crop ableitet (oder die Formel im Doc auf das echte Layout korrigieren + Auflösungs-Hinweis). **DoD:** ein dokumentierter, zuverlässiger Weg an die Pad-Mittelpunkte ohne Trial-and-Error. |
| DEMO-05 | P3 | ENG | `ColorSequence` ist nicht iterierbar | **Problem:** `for c in matrix.colors` / `list(matrix.colors)` wirft `TypeError: 'ColorSequence' object is not iterable` — nur `len()` und `set_color(i, …)` gehen. Erschwert Debugging/Tools, die die Farben auslesen wollen. **Fix:** `__iter__`/`__getitem__` (liefert Tupel) ergänzen. **DoD:** `list(seq)` liefert die Farb-Tupel; Test. |
| DEMO-06 | P3 | QA/Tooling | `lo.ps1 fg` race + Datei-Öffnen-Dialog-Automatik flaky | **Problem:** `lo.ps1 fg` liefert gelegentlich `hwnd=0`, wenn das Fenster noch nicht oben ist (Race); das native „Show öffnen"-Dialog-Automatisieren ist fragil (Namensfeld-Position/Fokus variiert). **Fix:** `fg` mit kurzer Retry-Schleife; ein robuster `lo.ps1 loadshow <pfad>`-Helfer (Dialog öffnen → Namensfeld sicher fokussieren → Pfad → Enter). **DoD:** Show-Reload per Skript klappt reproduzierbar ohne manuelles Koordinaten-Raten. |

---

## Beim weiteren Bauen ergänzen
_(neue Beobachtungen hier anhängen — UI-Label-Klipping, verwirrende Abläufe, fehlende Hinweise etc.)_
