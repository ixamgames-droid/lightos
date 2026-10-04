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

## Apache License 2.0 — für Geräteprofile auf QLC+-Basis

- **Lizenztext:** [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).
- **Wofür:** Die eigene Geräte-Bibliothek (FM-56, `fixtures/bibliothek/`) darf Profile enthalten,
  die aus QLC+ (Copyright © Heikki Junnila, Massimo Callegari und die QLC+-Beitragenden)
  übernommen und von LightOS überarbeitet wurden. Jede solche Datei nennt ihre Herkunft,
  den Urheber, die Originaldatei und die Änderungen selbst (Feld `herkunft`).

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
