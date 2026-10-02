# Fremd-Komponenten in LightOS (Third-Party Notices)

LightOS selbst steht unter **keiner** Open-Source-Lizenz (Entscheidung des
Projektinhabers). Diese Datei betrifft nur die **fremden** Dateien, die im Repo
mitgeliefert werden: Ihre Lizenzen erlauben die Weitergabe, verlangen aber, dass
Lizenztext und Urheberhinweise beiliegen. Die Lizenztexte stehen unter
[`licenses/`](licenses/).

Neue fremde Dateien nur mit Eintrag hier — `tests/test_proc18_fremd_lizenzhinweise.py`
prüft, dass jede Datei in den unten genannten Ordnern aufgeführt ist.

**3D-Modelle sind eigene Arbeit (VIZ-66, 2026-10-02):** Bis dahin lagen unter
`src/ui/visualizer/assets/models/` 19 Modelldateien aus QLC+ (Apache-2.0). Sie sind
entfernt; alle Geräte- und Traversen-Körper im 3D-Visualizer entstehen im Code aus
three.js-Grundkörpern (`scene_src/fixtures/builders.js`, `scene_src/stage/stage_objects.js`).
Damit liefert LightOS keine Apache-2.0-Dateien mehr mit. Ein Wächter
(`tests/test_viz66_keine_fremden_modelle.py`) verhindert, dass wieder `.dae`/`.obj`-Dateien
ins Repo kommen.

## three.js — 3D-Bibliothek (r128)

- **Herkunft:** three.js (<https://github.com/mrdoob/three.js>), Release r128.
- **Urheber:** Copyright © 2010-2021 three.js authors.
- **Lizenz:** MIT — [`licenses/MIT-three.js.txt`](licenses/MIT-three.js.txt).
- **Dateien:**
  - `assets/vendor/three.min.js`
  - `src/ui/visualizer/three_local.js`

## Apache License 2.0 — für Geräteprofile auf QLC+-Basis

- **Lizenztext:** [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).
- **Wofür:** Die eigene Geräte-Bibliothek (FM-56, `fixtures/bibliothek/`) darf Profile enthalten,
  die aus QLC+ (Copyright © Heikki Junnila, Massimo Callegari und die QLC+-Beitragenden)
  übernommen und von LightOS überarbeitet wurden. Jede solche Datei nennt ihre Herkunft,
  den Urheber, die Originaldatei und die Änderungen selbst (Feld `herkunft`).

## GNU FreeFont — Schrift für das Gource-Werkzeug

- **Datei:** `tools/gource/data/fonts/FreeSans.ttf` (nur Entwickler-Werkzeug, nicht Teil der App).
- **Lizenz:** GNU GPL v3 mit Font-Ausnahme — Details in
  [`tools/gource/data/fonts/README.txt`](tools/gource/data/fonts/README.txt), das der Schrift beiliegt.
