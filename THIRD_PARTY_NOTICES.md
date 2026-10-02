# Fremd-Komponenten in LightOS (Third-Party Notices)

LightOS selbst steht unter **keiner** Open-Source-Lizenz (Entscheidung des
Projektinhabers). Diese Datei betrifft nur die **fremden** Dateien, die im Repo
mitgeliefert werden: Ihre Lizenzen erlauben die Weitergabe, verlangen aber, dass
Lizenztext und Urheberhinweise beiliegen. Die Lizenztexte stehen unter
[`licenses/`](licenses/).

Neue fremde Dateien nur mit Eintrag hier — `tests/test_proc18_fremd_lizenzhinweise.py`
prüft, dass jede Datei in den unten genannten Ordnern aufgeführt ist.

## QLC+ — 3D-Modelle

- **Herkunft:** QLC+ (<https://github.com/mcallegari/qlcplus>), Ordner `resources/meshes/`,
  unverändert übernommen (byte-gleich, SHA-256 verglichen am 2026-10-02, FM-55).
- **Urheber:** Copyright © Heikki Junnila, Massimo Callegari und die QLC+-Beitragenden.
- **Lizenz:** Apache License 2.0 — [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).
  QLC+ führt keine NOTICE-Datei.
- **Dateien** (`src/ui/visualizer/assets/models/`):
  - `fixtures/hazer.dae`, `fixtures/moving_head.dae`, `fixtures/par.dae`,
    `fixtures/scanner.dae`, `fixtures/smoke.dae`, `fixtures/strobe.dae`
  - `generic/cone.obj`, `generic/cube.obj`, `generic/cylinder.obj`, `generic/plane.obj`,
    `generic/sphere.obj`, `generic/torus.obj`
  - `stage/truss_flat_1m.obj`, `stage/truss_flat_2m.obj`, `stage/truss_square_1m.obj`,
    `stage/truss_square_2m.obj`, `stage/truss_square_corner.obj`,
    `stage/truss_triangle_1m.obj`, `stage/truss_triangle_2m.obj`

## Geräte-Bibliothek

- **Ort:** `fixtures/bibliothek/` (eine JSON-Datei je Gerät, Format in
  [`fixtures/bibliothek/SCHEMA.md`](fixtures/bibliothek/SCHEMA.md)).
- **Herkunft je Datei:** steht im Pflichtfeld `herkunft` der Datei selbst
  (`art`, `lizenz`, bei fremden Vorlagen zusätzlich `urheber`, `original`, `geaendert`).
  Selbst geschriebene Profile (`lizenz: eigen`) sind keine fremden Dateien.
- **Aus QLC+ umgebaute Profile** (`herkunft.art: qlcplus`): Vorlage aus QLC+
  (<https://github.com/mcallegari/qlcplus>, `resources/fixtures/`), Copyright © Heikki
  Junnila, Massimo Callegari und die QLC+-Beitragenden (Urheber der einzelnen Datei in
  `herkunft.urheber`). Lizenz: Apache License 2.0 —
  [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt). Die Dateien sind geändert
  (Apache-2.0 §4b): ins LightOS-Format umgebaut; was genau, steht in `herkunft.geaendert`.
- **Aus der Open Fixture Library umgebaute Profile** (`herkunft.art: ofl`): MIT-Lizenz.
  Der MIT-Lizenztext der Open Fixture Library wird mit dem ersten solchen Profil unter
  `licenses/` abgelegt und hier verlinkt — `tests/test_fm56_bibliothek_waechter.py`
  verlangt das.

## three.js — 3D-Bibliothek (r128)

- **Herkunft:** three.js (<https://github.com/mrdoob/three.js>), Release r128.
- **Urheber:** Copyright © 2010-2021 three.js authors.
- **Lizenz:** MIT — [`licenses/MIT-three.js.txt`](licenses/MIT-three.js.txt).
- **Dateien:**
  - `assets/vendor/three.min.js`
  - `src/ui/visualizer/three_local.js`
  - `src/ui/visualizer/assets/ColladaLoader.js`, `src/ui/visualizer/assets/OBJLoader.js`
    (aus `examples/js/loaders/`)

## GNU FreeFont — Schrift für das Gource-Werkzeug

- **Datei:** `tools/gource/data/fonts/FreeSans.ttf` (nur Entwickler-Werkzeug, nicht Teil der App).
- **Lizenz:** GNU GPL v3 mit Font-Ausnahme — Details in
  [`tools/gource/data/fonts/README.txt`](tools/gource/data/fonts/README.txt), das der Schrift beiliegt.
