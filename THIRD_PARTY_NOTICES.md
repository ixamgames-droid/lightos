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

## Geräte-Bibliothek zum Herunterladen (nicht im Repo, FM-53)

LightOS kann eine freie Fixture-Bibliothek **auf Nachfrage** herunterladen
(Erststart-Frage bzw. **Datenbank → Geräte-Bibliothek herunterladen...**). Diese Dateien liegen **nicht** im Repo
und werden nicht mit LightOS weitergegeben; sie kommen direkt von der Quelle auf
den Rechner des Nutzers.

- **QLC+ Fixture-Bibliothek** — GitHub-Archiv einer festen QLC+-Version
  (<https://github.com/mcallegari/qlcplus>), verwendet werden nur die `.qxf`-Dateien.
  Lizenz: Apache License 2.0 — [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).
- **Open Fixture Library** — QLC+-Export (<https://open-fixture-library.org>).
  Lizenz: MIT (<https://github.com/OpenLightingProject/open-fixture-library/blob/master/LICENSE>);
  einzelne Profile stammen ihrerseits aus QLC+ (Apache-2.0).

**Herkunft und Lizenz je Profil** speichert LightOS beim Import in der Tabelle
`profil_herkunft` der Geräte-Datenbank: Quelle, Lizenz, Lizenz-Link, Archiv-Adresse,
SHA-256 und Zeitpunkt. Eigene und schon vorhandene Profile bleiben unberührt.
Details: [`docs/FIXTURE_SOURCES.md`](docs/FIXTURE_SOURCES.md).
