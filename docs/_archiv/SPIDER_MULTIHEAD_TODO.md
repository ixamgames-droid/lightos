# To-Do: Spider mit getrennt ansteuerbaren Köpfen + 3D-Modell

> Status: **geplant / noch nicht umgesetzt** (2026-06-14). Auf ausdrücklichen
> Wunsch nur **analysiert und dokumentiert**, damit es später abgearbeitet
> werden kann. Aktuell ist der `Spider 14ch` als ein Fixture mit **einer**
> gemeinsamen Farbe für beide LED-Bänke eingebaut (siehe
> [FIXTURE_LIBRARY.md](../FIXTURE_LIBRARY.md), `fixture_db._spider_modes_data`).

## 1. Ziel

Der U King Spider (`U-King-Speider.qxf`) hat **zwei RGBW-Bänke** (CH6–9 und
CH10–13), die das Gerät getrennt ansteuern kann. LightOS soll beide Köpfe
**unabhängig einfärben** können — idealerweise schön in die Software integriert
(Programmer, Live View, Effekte, 3D-Viewer), nicht nur als Roh-Fader.

## 2. Warum es heute *nicht* geht (Ist-Zustand)

Das Farbmodell kennt **eine Farbe pro Fixture**. Konkret:

| Stelle | Datei | Verhalten |
|---|---|---|
| Programmer-Werte | `core/app_state.py` `set_programmer_value(fid, attr, val)` | Schlüssel ist **(fid, attribut)** — kein Kopf-Index. |
| DMX-Ausgabe | `app_state._flush_programmer_to_dmx` (≈ Z. 644) | schreibt **jeden** Kanal mit gleichem Attribut auf **denselben** Wert → beide `color_r` bekommen identisch. |
| Live-View-Farbe | `ui/views/live_view.py` `_fixture_color_and_intensity` (Z. 725) | liest genau **ein** r/g/b/w pro Fixture, zeichnet einen Farbpunkt/Beam. |
| 3D-Viewer | `ui/visualizer/stage_scene.html` `buildMovingHead()` / `buildFixtureModel` (Z. 1091) + Daten-Dict `visualizer_window.py` Z. 311 | ein Modell mit **einer** emissiven Linse, gespeist aus der einen Fixture-Farbe. |
| Farb-Kacheln / Paletten / Color-Sequence / RGB-Matrix | Programmer/VC | alle setzen `color_r/g/b/w` global pro Fixture. |

Deshalb teilen sich die beiden Bänke zwangsläufig die Farbe (gleiche Konvention
wie die LED-Bar-Segmente).

## 3. Zwei Lösungswege

### Weg A — „Zwei Fixtures" (schnell, wenig Code)

Den Spider als **zwei Patch-Einträge** anlegen, die sich Adressbereiche teilen,
aber **disjunkte** Kanäle belegen:

- **Spider Kopf 1** (9ch) auf Basisadresse *A*: Pan, Tilt, Speed, Dimmer,
  Shutter, R1, G1, B1, W1 (= CH1–9).
- **Spider Kopf 2** (4ch RGBW) auf Adresse *A+9*: R2, G2, B2, W2 (= CH10–13).
- CH14 (Reset) bleibt ungepatcht oder kommt an Kopf 1 als 10. Kanal.

Damit hat Kopf 2 eine **eigene, unabhängige Farbe** über Programmer / Farb-
Kacheln / RGB-Matrix / Color-Sequence — **ohne** Kerncode-Änderung.

- **Umsetzung:** zwei kleine Builtin-Profile ergänzen (`_add_spider_head1`,
  `_add_spider_head2` in `fixture_db.py`) — analog zu den bestehenden.
- **Grenzen:** Bewegung/Dimmer/Shutter/EFX nur an Kopf 1 (ist physisch ohnehin
  geteilt); zwei Einträge im Patch; in Live View/3D erscheinen es zwei Geräte
  (die man nah nebeneinander platziert — genau die „zwei Moving Heads"-Idee).

**Empfehlung:** Das ist der pragmatische erste Schritt für „Farbe getrennt".

### Weg B — Native Mehrkopf-Unterstützung (die „coole", größere Lösung)

Ein echtes **Kopf-/Sub-Fixture-Konzept** einführen. QLC+ liefert die Info schon
mit: die `<Head>`-Elemente in `U-King-Speider.qxf` definieren, welche Kanäle zu
welchem Kopf gehören (der QXF-Importer ignoriert sie aktuell).

Nötige Änderungen (Aufwand: groß, mehrere Bereiche):

1. **Datenmodell** (`core/database/models.py`): `FixtureChannel.head` (int) ODER
   eigene Zweitkopf-Attribute (`color_r2/g2/b2/w2`). Heads beim QXF-Import lesen
   (`qxf_import.py` `<Head>`).
2. **Programmer/Farbmodell** (`app_state.py`): Wert-Key um Kopf-Index erweitern
   bzw. Zweitkopf-Attribute überall mitführen; `_flush_programmer_to_dmx`,
   Farb-Picker, Paletten, Color-Sequence, Highlight/`open_value_for`.
3. **RGB-Matrix/Effekte**: jede Bank als eigene Matrix-Zelle behandeln (die
   Matrix arbeitet bereits zell-/fixtureweise → gut anknüpfbar).
4. **Live View** (`live_view.py`): `_fixture_color_and_intensity` → Liste von
   Kopf-Farben; zwei Punkte/Beams je Fixture; Auswahl/Position ggf. je Kopf.
5. **3D-Viewer** (`stage_scene.html` + `visualizer_window.py`): `buildSpider()`
   mit N Linsen; Farb-/Intensitäts-**Array** statt Einzelwert ins Daten-Dict
   (Z. 311) reichen; je Linse emissive.
6. **Virtuelle Konsole**: Farb-Widgets brauchen ein „Kopf-Ziel".
7. **Show-Datei** (`core/show/show_file.py`): evtl. neuer Per-Kopf-State.

**Empfehlung:** Später, als eigenes Feature. Weg A deckt den Akutwunsch ab.

## 4. 3D-Render-Modell für den Spider

Heute wählt der 3D-Viewer das Modell nur per `fixture_type`
(`buildFixtureModel`, `stage_scene.html` Z. 1091): prozedurale Geometrie +
optionales `.dae`-Overlay aus `assets/models/fixtures/`
(`moving_head.dae`, `par.dae`, `strobe.dae`, `scanner.dae`, `hazer.dae`,
`smoke.dae`). Es gibt **kein** Spider/Derby-Modell und keine Pro-Fixture-Auswahl.

Optionen:

- **Sofort/Fallback (Nutzer-Vorschlag):** den Spider als **zwei Moving-Head-
  Meshes nah nebeneinander** zeigen (passt zu Weg A) oder `moving_head.dae`
  wiederverwenden. Kein neues Asset nötig.
- **Eigenes Modell:** `buildSpider()` mit Korpus + mehreren kleinen Linsen
  bauen und/oder ein echtes Mesh laden. Quellen für freie 3D-Modelle:
  - **GDTF Share / gdtf.eu** — viele Spider/Derby-Fixtures inkl. glTF-3D-Modell
    (GLB). Das Repo hat bereits `fixtures/gdtf/` + geplanten GDTF-Import → ein
    GDTF mit `<Geometry>`/GLB ließe sich als Quelle nutzen.
  - **ROBE Lighting** stellt GDTF mit glTF-Modellen bereit; **BlenderDMX**
    konsumiert GDTF-Modelle (Referenz, wie man GLB→Szene bringt).
  - GLB → `.dae`/Three.js: der Viewer hat `ColladaLoader.js` + `OBJLoader.js`;
    für GLB bräuchte es einen GLTFLoader oder Konvertierung nach `.dae`/`.obj`.
  - Ggf. neuen `fixture_type` `flower`/`spider` einführen (Icon + TYPE_COLORS +
    `buildFixtureModel`-Case) statt `moving_head`.

## 5. Empfohlene Reihenfolge

1. **Weg A** als Builtin-Doppelprofil → Farbe der Köpfe sofort getrennt.
2. 3D: zwei Moving-Head-Meshes nebeneinander (Fallback) verdrahten.
3. Später **Weg B** (echtes Kopf-Konzept) + eigenes Spider-Mesh, wenn das
   Mehrkopf-Feature breiter gebraucht wird (auch für andere Flower/Derby).

## 6. Berührte Dateien (Checkliste für später)

- `src/core/database/fixture_db.py` (Weg A: zwei Profile)
- `src/core/database/models.py`, `qxf_import.py` (Weg B: Heads)
- `src/core/app_state.py` (Programmer/Flush/Farbe)
- `src/ui/views/live_view.py` (`_fixture_color_and_intensity`, Zeichnen)
- `src/ui/visualizer/stage_scene.html`, `visualizer_window.py` (Modell + Daten)
- `src/core/show/show_file.py` (Persistenz, falls nötig)
- ggf. `src/ui/widgets/mini_icons.py`, `patch_view.py` (neuer Typ/Icon)
