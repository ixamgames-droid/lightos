# Quellen für Geräteprofile und 3D-Modelle — Recherche FM-55 (Stand 2026-10-02)

**Frage:** Welche Fixture-Profile und 3D-Modelle darf LightOS **mitliefern** (im öffentlichen
Repo), welche darf es **zur Laufzeit herunterladen**, und welche gar nicht?
**Wichtigstes Kriterium:** die Lizenz.

**Das ist keine Rechtsberatung.** Wo eine Aussage auf eigener Schlussfolgerung beruht, steht das
dabei. Die Entscheidungen trifft der Projektinhaber.

---

## Kurzfassung

| | Geräteprofile | 3D-Modelle |
|---|---|---|
| **Mitliefern** (erst nach PROC-11, s. u.) | Open Fixture Library (MIT), QLC+-Fixtures (Apache-2.0) | GDTF-Default-Meshes (ausdrücklich frei), QLC+-Meshes (Apache-2.0, **liegen schon im Repo**) |
| **Download zur Laufzeit** (nur nach Zustimmung) | OFL (ohne Konto) und QLC+ (GitHub-Archiv): beide direkt mit dem **vorhandenen** QXF-Import lesbar. GDTF-Share nur mit dem **eigenen Konto des Nutzers** | Modelle aus `.gdtf`-Dateien, die der Nutzer selbst lädt oder importiert |
| **Gar nicht** | Hersteller-Downloads ohne Lizenz, Konsolen-Bibliotheken (grandMA, Avolites, Onyx, ChamSys, Martin M-Series), Freestyler, SoundSwitch, Lightkey, DMXIS | Hersteller-CAD, TurboSquid/CGTrader, BlenderKit „Royalty Free", aus Visualizern extrahierte Bibliotheken |

### ★ Befund vorab: LightOS verteilt schon heute fremde Dateien ohne Lizenzhinweis

Alle 19 Modelldateien unter `src/ui/visualizer/assets/models/` sind **byte-gleich** mit
`resources/meshes/` aus QLC+ (SHA-256 einzeln verglichen am 2026-10-02):

- `fixtures/`: `hazer`, `moving_head`, `par`, `scanner`, `smoke`, `strobe` (`.dae`)
- `generic/`: `cone`, `cube`, `cylinder`, `plane`, `sphere`, `torus` (`.obj`)
- `stage/`: `truss_flat_1m/2m`, `truss_square_1m/2m`, `truss_square_corner`,
  `truss_triangle_1m/2m` (`.obj`)

QLC+ steht unter **Apache-2.0**. Im Mesh-Ordner gibt es keine eigene Lizenzdatei, also gilt die
des Repos. Apache-2.0 erlaubt die Weitergabe, verlangt aber in §4 eine Kopie der Lizenz und den
Erhalt der Urheberhinweise. LightOS hat **keine eigene Lizenzdatei** (PROC-11) und nennt die
Herkunft dieser Dateien nirgends. In Gebrauch sind `par`, `strobe`, `smoke` und `hazer` (als
Überlagerung, `fixtures/builders.js`) sowie `truss_square_2m` (`stage/stage_objects.js`).

Das ist kein theoretischer Fall für später, sondern der heutige Stand. **Empfehlung:** PROC-11
vorziehen, bevor irgendeine weitere fremde Datei hinzukommt (s. „Nächste Items").

---

## Methode und Grenzen

- **Selbst gelesen** (Primärquelle, GitHub bzw. `raw.githubusercontent.com`): Lizenzdateien und
  READMEs von QLC+, OFL, der GDTF-Spezifikation, die GDTF-Share-API-Beschreibung, der Byte-Vergleich
  der Meshes und die Zählungen unten. Diese Stellen sind mit **[gelesen]** markiert.
- **Gesperrt** (Egress-Proxy dieser Sitzung, nicht umgangen): `gdtf-share.com`,
  `open-fixture-library.org`, `gdtf.eu`, `qlcplus.org`, `forum.qlcplus.org`, `thomann.de`,
  `steinigke.de`, `cameolight.com`, `chauvetprofessional.com`, `adj.com`, `martin.com`, `harman.com`,
  `robe.cz`, `avolites.com`, `obsidiancontrol.com`, `lightkeyapp.com`, `sketchfab.com`,
  `polyhaven.com`, `blenderkit.com`, `turbosquid.com`, `cgtrader.com`, `creativecommons.org`,
  `web.archive.org`.
- Aussagen zu diesen Seiten stammen aus Suchmaschinen-Auszügen und sind mit **[Auszug]** markiert.
  **Vor einer Entscheidung, die darauf beruht, den Wortlaut auf der Seite selbst prüfen.**
- **[Schluss]** = eigene Folgerung.

---

## 1. Geräteprofile

### Übersicht

| Quelle | Format | Umfang | Lizenz | Mitliefern? | Aktualität | Weg |
|---|---|---|---|---|---|---|
| [QLC+ `resources/fixtures`](https://github.com/mcallegari/qlcplus/tree/master/resources/fixtures) | `.qxf` (XML) | 1781 Geräte / 143 Hersteller laut `FixturesMap.xml` [gelesen]; ~1850 Dateien laut GitHub-Codesuche | Apache-2.0 | **ja** (Lizenztext + Hinweise) | sehr aktiv, Fixture-Commits bis 2026-09-26 | GitHub-Archiv, `raw.githubusercontent.com` |
| [Open Fixture Library](https://github.com/OpenLightingProject/open-fixture-library) | eigenes JSON; Export u. a. als QLC+ `.qxf` | 134 Hersteller [gelesen]; ~660 Geräte | MIT | **ja** (Copyright-Hinweis) | sehr aktiv, Commits bis 2026-10-02 | REST-API ohne Konto, Sammel-Download je Format, GitHub-Archiv |
| GDTF-Share (gdtf-share.com) | `.gdtf` (ZIP: XML + Modelle + Gobos) | ~3000 Dateien [Auszug] | keine Weitergabe-Lizenz; Rechte beim jeweiligen Inhaber [Auszug] | **nein**; nur Download mit Konto des Nutzers | laufend (Hersteller laden selbst hoch) | öffentliche API mit Login [gelesen] |
| Hersteller-Downloads | meist PDF-Anleitungen; teils GDTF (über GDTF-Share) | – | keine offene Lizenz gefunden | **nein** | – | – |
| Konsolen-Bibliotheken | proprietär | – | keine Weitergabe-Lizenz | **nein** | – | – |
| Sonstige (Freestyler, SoundSwitch, Lightkey, DMXIS, DMXControl 3) | proprietär oder ungeklärt | – | keine offene Lizenz gefunden | **nein** | – | – |

### 1.1 QLC+ (Q Light Controller Plus)

- **Lizenz [gelesen]:** `README.md` — „Licensed under the **Apache 2.0** License. See COPYING for
  details." und „Copyright © Heikki Junnila, Massimo Callegari".
  `COPYING` ist die Apache License, Version 2.0.
  Quellen: <https://github.com/mcallegari/qlcplus/blob/master/README.md>,
  <https://raw.githubusercontent.com/mcallegari/qlcplus/master/COPYING>.
- Die `.qxf`-Dateien tragen keinen eigenen Lizenzkopf, nur einen `<Creator>`-Block (Werkzeug,
  Version, Autor). Eine `NOTICE`-Datei gibt es im QLC+-Repo nicht.
- **Klarstellung des Maintainers [Auszug]:** „Fixtures, as the rest of QLC+, are covered by the
  Apache 2.0 license" (<https://forum.qlcplus.org/viewtopic.php?p=39620>).
- **Mitliefern: ja**, sobald LightOS die Pflichten aus Apache-2.0 §4 erfüllt: Lizenzkopie beilegen,
  Urheberhinweise erhalten (der `<Creator>`-Block, s. QA-72) und geänderte Dateien kennzeichnen.
- **[Schluss]** Apache-2.0 ist mit GPLv3 vereinbar, **nicht** mit GPLv2-only. Das spielt bei der
  Lizenzwahl für LightOS (PROC-11) eine Rolle.

### 1.2 Open Fixture Library (OFL)

- **Lizenz [gelesen]:** `LICENSE` — „MIT License / Copyright (c) 2017 Florian & Felix Edelmann /
  Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
  associated documentation files (the "Software"), to deal in the Software without restriction …"
  sowie `package.json`: `"license": "MIT"`.
  Quelle: <https://github.com/OpenLightingProject/open-fixture-library/blob/master/LICENSE>.
- **[Schluss]** Eine eigene Datenlizenz gibt es nicht; die MIT-Lizenz des Repos deckt die
  Geräte-JSONs mit ab. Die Projektseite spricht ausdrücklich nur vom „code" [Auszug].
- **Nuance:** Rund 50 OFL-Geräte tragen `"importPlugin": {"plugin": "qlcplus_4.12.1"}`, stammen
  also ursprünglich aus QLC+ (Apache-2.0). Wer OFL mitliefert, nennt beide Lizenzen.
- **Formate [gelesen, `plugins/plugins.json`]:** Import aus `ecue`, `gdtf`, `qlcplus_4.12.2`;
  Export nach `aglight`, `color-chief`, `colorsource`, `d-light`, `dmxcontrol3`, `dragonframe`,
  `ecue`, `millumin`, `ofl`, `op-z`, **`qlcplus_4.12.2`**. Einen **GDTF-Export** gibt es nicht.
- **Download-Weg [gelesen im Quelltext, `ui/components/DownloadButton.vue`]:**
  `/download.<plugin>` für alle Geräte, `/<hersteller>/<gerät>.<plugin>` für eines; also
  `https://open-fixture-library.org/download.qlcplus_4.12.2`. **Nicht abgerufen**, die Seite ist
  hier gesperrt.
- **REST-API [gelesen, `docs/rest-api.md`]:** `https://open-fixture-library.org/api/v1`, u. a.
  `GET /manufacturers`, `POST /get-search-results`, ohne Anmeldung.
- **Physische Daten:** `physical.dimensions` (mm), Gewicht, Leistung, `lens.degreesMinMax`,
  Pixel-Maße. Diese Felder sind für die 3D-Ansicht nützlich (Kapitel 2).
- **Mitliefern: ja**, mit Copyright-Hinweis. Download zur Laufzeit ebenso unbedenklich.

### 1.3 GDTF-Share und das GDTF-Format

- **Das Format ist offen [gelesen]:** „The GDTF file format is standardized in DIN SPEC 15800 …
  The file format is developed using open source formats, and manufacturers … are welcome to use
  this open source technology." (<https://github.com/mvrdevelopment/spec>). Ein Importer darf also
  frei gebaut werden; die Spezifikation liegt dort als Markdown.
- **Nutzungsbedingungen der Plattform [Auszug]**
  (<https://gdtf-share.com/landing/pages/termsAndConditions.php>):
  „Title and intellectual property rights in and to any content displayed by or accessed through
  the GDTF Website belongs to the respective content owner. Such content may be protected by
  copyright …" sowie „You must not use any part of the materials on our Website for commercial
  purposes without obtaining a license to do so from us or our licensors."
  **Eine Erlaubnis zur Weitergabe ist nicht zu finden.**
- **API [gelesen]** (<https://github.com/mvrdevelopment/tools/blob/main/GDTF_Share_API/GDTF%20Share%20API.md>):
  „A GDTF Share account is required for users to access the functionality provided by the API."
  und „it is not intended to be used as a replacement for the GDTF Share website." Endpunkte:
  `login.php` (Session-Cookie), `getList.php`, `downloadFile.php?rid=…`.
- **Vorbild:** BlenderDMX (GPL-3.0) nutzt genau diese API mit den Zugangsdaten des Nutzers.
- **Mitliefern: nein.** **Zur Laufzeit: ja, aber nur nutzer-ausgelöst mit dessen eigenem Konto,
  kein Massen-Download.**

### 1.4 Hersteller

Keine Herstellerseite war erreichbar. **[Schluss]** Ohne ausdrückliche Lizenz gilt das normale
Urheberrecht; Profile, die ein Hersteller auf GDTF-Share stellt, fallen unter 1.3.

| Hersteller | Gefunden | Urteil |
|---|---|---|
| Stairville, Varytec (Thomann) | nur PDF-Anleitungen [Auszug] | **nein** (DMX-Tabelle nur als Vorlage für ein eigenes Profil) |
| Eurolite (Steinigke) | PDF-Datenblätter [Auszug] | **nein** |
| Cameo (Adam Hall) | GDTF für neue Geräte [Auszug] | **nein**; GDTF über 1.3 |
| Chauvet | verweist auf GDTF-Share, „Manufacturer Only" [Auszug] | über 1.3 |
| ADJ | kein Profil-Download gefunden | **nein** |
| Robe | GDTF zu jedem Produkt über eigenes GDTF-Share-Konto [Auszug] | über 1.3 |
| Martin (Harman) | M-Series-Bibliothek, LightJockey `.Udf` (binär) [Auszug]; Harman-Nutzungsbedingungen verbieten Kopieren und Weitergabe [Auszug] | **nein** |

### 1.5 Konsolen- und sonstige Bibliotheken

grandMA3 (MA Fixture Share / GDTF über World Server), Avolites (Titan Personalities), Obsidian Onyx
(Bibliothek von AtlaBase Ltd), ChamSys MagicQ (`heads.all`, „over 28,500" Profile), Martin M-Series:
alle **proprietär, keine Weitergabe-Lizenz gefunden** [Auszug] → **nein**.
Freestyler (`.ffx`, teils kostenpflichtig gehandelt), SoundSwitch (Abo), Lightkey (eigener Dienst),
Enttec DMXIS (Konto nötig), DMXControl 3 (kein öffentliches Profil-Repo mit Lizenz gefunden)
→ **nein**, solange keine Lizenz belegt ist.

### 1.6 Sind DMX-Kanalbelegungen überhaupt geschützt?

Eine belastbare Quelle **speziell zu DMX-Belegungen** wurde nicht gefunden. Allgemein hat der EuGH
(C-604/10, *Football Dataco*) entschieden, dass regelgebundene Faktenlisten nicht allein wegen des
Aufwands urheberrechtlich geschützt sind. **[Schluss]** Eine Kanalbelegung aus einer Anleitung
abzutippen und als eigenes Profil anzulegen, ist wahrscheinlich unkritisch. Ganze Dateien zu
kopieren oder eine Bibliothek in großen Teilen zu übernehmen ist etwas anderes (Urheberrecht an der
Datei, EU-Datenbankherstellerrecht). `docs/FIXTURE_SOURCES.md` formuliert das heute sicherer, als es
belegt ist („Faktendaten … dürfen"). Eine verbindliche Aussage kann nur ein Jurist geben.

---

## 2. 3D-Modelle

### Übersicht

| Quelle | Format | Umfang | Lizenz | Mitliefern? | Konto nötig | Für three.js |
|---|---|---|---|---|---|---|
| [QLC+ `resources/meshes`](https://github.com/mcallegari/qlcplus/tree/master/resources/meshes) | `.dae`, `.obj` | 6 Geräte, 7 Traversen, 6 Grundkörper | Apache-2.0 | **ja** (liegen schon im Repo, Hinweis fehlt) | nein | Collada/OBJ-Loader vorhanden |
| [GDTF-Default-Meshes](https://github.com/mvrdevelopment/spec/tree/main/meshes) | `.3ds` | Base, Yoke, Head, Scanner, Conventional (1.0 und 1.1) | ausdrücklich frei (s. u.) | **ja** | nein | über `TDSLoader` oder nach GLB wandeln |
| Modelle in `.gdtf`-Dateien (GDTF-Share) | GLB oder 3DS (Spec) | je Gerät | beim Inhaber, keine Weitergabe-Lizenz [Auszug] | **nein** | ja | ideal (glTF 2.0) |
| Open Fixture Library | keine Modelle; Maße in mm, Linsenwinkel | – | MIT | Maße: **ja** | nein | zum Skalieren eigener Grundkörper |
| MVR (DIN SPEC 15801) | glTF 2.0 / GLB (3DS veraltet) | Austauschformat | offen | – | – | Import von Bühne/Traversen |
| Hersteller-CAD (Martin, Elation u. a.) | DWG, 3DS | – | keine offene Lizenz; Harman verbietet Weitergabe [Auszug] | **nein** | – | – |
| Sketchfab | glTF/GLB | einige Dutzend relevante [Schluss] | je Modell (CC0/CC-BY/… ) [Auszug] | nur einzeln geprüfte CC0/CC-BY | Download-API nur mit OAuth des Nutzers [Auszug] | ideal |
| Thingiverse/Printables | meist STL | wenige | je Modell | praktisch **nein** | – | ungeeignet |
| BlenderKit | `.blend` | – | „Royalty Free" verbietet Weitergabe in Originalform [Auszug]; CC0 erlaubt | RF **nein**, CC0 ja (kaum Geräte) | ja | Umweg über Blender |
| Poly Haven | glTF u. a. | keine Scheinwerfer gefunden | CC0 [Auszug] | ja, falls Passendes | nein | ideal |
| TurboSquid/CGTrader (auch Gratis-Modelle) | diverse | – | Weitergabe der Datei verboten [Auszug] | **nein** | ja | – |
| [BlenderDMX](https://github.com/open-stage/blender-dmx) | GLB-Grundkörper, eigene `.gdtf` | 5 Grundkörper, 8 Profile | GPL-3.0 | vorerst **nein** (Lizenzentscheidung fehlt) | nein | ideal |
| Capture, WYSIWYG, Vectorworks, Depence, grandMA3 | proprietär | – | keine offene Lizenz | **nein**; Austausch über MVR/GDTF | – | – |

### 2.1 GDTF-Default-Meshes

- **Lizenz [gelesen]** (`README.md` von <https://github.com/mvrdevelopment/spec>): „The folder
  meshes contains the default meshes that are used by the GDTF spec. They are free to use, modify,
  and distribute, including in commercial applications, without any licensing fees or royalties."
- **Format laut Spec:** „Preferable format for the 3D model is GLTF"; erlaubt sind 3DS und GLB,
  glTF 2.0 ohne Erweiterungen und Animationen, je Gerät höchstens 1200 Eckpunkte in der
  Standardstufe.
- **Nutzen:** ein generischer Baukasten (Fuß, Bügel, Kopf, Scanner, Scheinwerfer) mit klarer
  Erlaubnis, skalierbar mit den OFL-Maßen.

### 2.2 Namensnennung in der App

- **Apache-2.0** (QLC+): Lizenzkopie beilegen, Urheberhinweise erhalten, Änderungen kennzeichnen.
- **MIT** (OFL, three.js): Copyright- und Erlaubnis-Hinweis beilegen. `three_local.js` trägt ihn
  im Kopf (`SPDX-License-Identifier: MIT`); eine Übersicht fremder Bestandteile gibt es nicht.
- **CC-BY:** Urheber, Lizenz-Link und Änderungen nennen. **CC-BY-SA meiden**, weil ein geändertes
  Modell sonst unter dieselbe Lizenz fällt.
- **[Schluss]** Praktisch heißt das: eine Datei mit fremden Bestandteilen (Name, Quelle, Lizenz,
  Änderungen), die auch im Über-Dialog erscheint. Solange LightOS selbst keine Lizenz hat, würden
  GPL-Bestandteile die Wahl vorwegnehmen.

---

## 3. Abgleich mit dem, was LightOS heute kann

- **Profile:** Es gibt **nur einen Importer**, für QLC+-`.qxf`:
  - `src/core/database/qxf_import.py` mit `import_all_qxf()` (ganzer Ordner) und `import_qxf_file()`.
  - Aufruf über den Dialog `src/ui/widgets/qxf_import_dialog.py`; Einzeldatei im Generator über
    `model_from_qxf()` (`src/ui/widgets/fixture_generator.py`).
  - Importierte Profile tragen `source='qlcplus'` (Generator: `'user'`), die Herkunft aus dem
    `<Creator>`-Block steht in `provenance` (QA-72).
  - **Nicht übernommen** werden u. a. `<Dimensions>`, Gewicht, Linse, `<Focus PanMax/TiltMax>`
    (Pan/Tilt-Bereich steht nur am gepatchten Gerät, Standard 540/270) und Farben/Bilder der
    Rad-Fächer.
  - **GDTF, OFL-JSON, MA, Avolites:** kein Importer. GDTF steht nur als Notiz in
    `docs/OPEN_POINTS_OVERVIEW.md`.
- **Folge für OFL:** OFL exportiert QLC+-`.qxf`. Damit liest LightOS OFL **schon heute ohne neuen
  Code**, nur der Download fehlt.
- **Kein Netzzugriff:** In `src/` gibt es keinen Download- oder Update-Mechanismus, und
  `docs/FIXTURE_SOURCES.md` sagt ausdrücklich: LightOS lädt „nichts automatisch aus dem Netz".
  Ein Download beim ersten Start **ändert diese Regel**; das ist eine Entscheidung für den
  Projektinhaber, kein Detail der Umsetzung.
- **Mitgelieferte Daten:** keine fremden Profile (`fixtures/gdtf/` enthält nur `.gitkeep`; `qlcplus-src/`,
  `fixtures/custom/` und `data/*.db` sind ignoriert). Etwa 49 eingebaute Profile entstehen im Code
  (`_seed_if_empty` / `ensure_builtins`).
- **3D:** überwiegend prozedurale three.js-Körper (`scene_src/fixtures/registry.js`,
  `builders.js`). Geladen werden nur `.obj` und `.dae`
  (`scene/model_loader.js`, `OBJLoader`/`ColladaLoader`). **Kein glTF-Loader**; die gebündelte
  three.js-Version (r128) bringt ihn nicht mit (vgl. VIZ-15). Das Modell eines Geräts wählt
  `viz_model_for()` (`src/core/app_state.py`).
- **Hersteller-Namen:** `Manufacturer.name` ist eindeutig, aber **ohne Normalisierung**. Der
  QXF-Import, `_get_or_create_mfr` und der Fixture-Editor gleichen jeweils anders ab; „U King",
  „UKing" und „U-King" würden drei Hersteller.
- **`docs/FIXTURE_SOURCES.md` ist veraltet:** dort steht „~3.000 .qxf"; gezählt sind 1781 Einträge
  im Index bzw. ~1850 Dateien.

---

## 4. Empfehlung

1. **Zuerst PROC-11 abschließen** (Lizenz für LightOS wählen, Lizenztexte und eine Übersicht
   fremder Bestandteile beilegen). Das betrifft die heute schon mitgelieferten QLC+-Meshes und
   three.js. Vorher sollte **nichts** Fremdes hinzukommen. Für Apache-2.0-Daten scheidet dabei
   GPLv2-only aus.
2. **Mitliefern:** GDTF-Default-Meshes und die QLC+-Meshes (beide mit Hinweis), dazu weiter die
   eigenen prozeduralen Körper. Fremde **Profile** eher nicht ins Repo legen (Größe, laufende
   Aktualisierung), sondern auf Knopfdruck holen.
3. **Download zur Laufzeit, nur nach ausdrücklicher Zustimmung:**
   - OFL als QLC+-Export (`/download.qlcplus_4.12.2`) oder als GitHub-Archiv → vorhandener
     QXF-Import. Kein Konto nötig.
   - QLC+-Fixtures als GitHub-Archiv → vorhandener QXF-Import.
   - GDTF-Share nur nutzer-ausgelöst mit dessen eigenem Konto; nie im Repo.
4. **Gar nicht:** Hersteller-CAD und -Bibliotheken ohne Lizenz, Konsolen-Bibliotheken,
   TurboSquid/CGTrader, BlenderKit RF, extrahierte Visualizer-Bibliotheken.

## 5. Vorschlag für nächste Items

IDs vergibt A beim Anlegen (`tools/backlog_ids.py`); die Reihenfolge ist die empfohlene.

1. **PROC-11 vorziehen und um den Mesh-Befund ergänzen:** Lizenz, Lizenztexte, Übersicht fremder
   Bestandteile (QLC+-Meshes, three.js, Controller-Bibliothek), Anzeige im Über-Dialog.
   Ein Test kann prüfen, dass jede Datei unter `assets/models/` in der Übersicht steht.
2. **„Bibliothek erweitern" (OFL/QLC+ auf Knopfdruck):** Download nach Zustimmung → `import_all_qxf`;
   `provenance` mit Quelle und Stand füllen. Erst nach der Entscheidung zu „nichts automatisch aus
   dem Netz".
3. **Hersteller-Normalisierung:** ein Abgleich-Schlüssel (Groß-/Kleinschreibung, Leer- und
   Satzzeichen, Aliasliste) für alle drei Anlegewege; OFL liefert mit `manufacturers.json`
   134 Hersteller als Vorlage.
4. **QXF-Import vervollständigen:** `<Dimensions>`, `<Focus PanMax/TiltMax>`, Linsenwinkel und
   Rad-Farben übernehmen. Das bringt Maße für die 3D-Ansicht ohne neues Format.
5. **3D-Zielformat GLB:** glTF-Loader (und ggf. `TDSLoader`) in die gebündelte three.js-Version
   aufnehmen; GDTF-Default-Meshes und QLC+-Meshes beim Bauen nach GLB wandeln.
6. **GDTF-Import für vom Nutzer gelieferte `.gdtf`:** DMX-Modi plus eingebettete GLB/3DS-Geometrie.
   Grundlage für VIZ-56 (MVR).
7. **Nativer OFL-JSON-Import** (Maße, Linsen, Pixel-Raster ohne den Umweg über QXF), später.
8. **`docs/FIXTURE_SOURCES.md` nachziehen:** Zahlen, Netzregel, vorsichtigere Rechtsaussage.
