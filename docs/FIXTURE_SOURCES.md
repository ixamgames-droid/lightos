# Fixture Library erweitern — legale Datenquellen (Feature 7)

LightOS hat einen fertigen **QXF-Import** (QLC+-Fixture-Format):
Patchen → „QLC+-Fixtures importieren…" (Dialog `qxf_import_dialog.py`,
Kern `src/core/database/qxf_import.py`). Der Import ist **additiv und
duplikat-sicher**: Fixtures, die es (gleicher Hersteller + Modell) schon gibt,
werden übersprungen — bestehende Profile (insbesondere die korrigierten
Builtins wie ZQ02001) werden **nie** überschrieben.

## Empfohlene Quellen (rechtlich sauber)

### 1. Open Fixture Library (OFL) — empfohlen
- https://open-fixture-library.org — über 1.000 Fixture-Definitionen
- **Lizenz: MIT** (Daten und Code), kommerzielle Nutzung erlaubt
- **Weg in LightOS:** Auf der Fixture-Seite das Export-Format
  **„QLC+ 4.12+ (.qxf)"** wählen → Datei herunterladen → in einen Ordner
  legen → in LightOS über den QXF-Import einlesen.
- Bulk: das OFL-GitHub-Repo (`OpenLightingProject/open-fixture-library`)
  enthält alle Fixtures; per `npm run export` lassen sich alle als QXF
  exportieren (Node.js nötig — manueller Schritt).

### 2. QLC+-Fixture-Bibliothek
- https://github.com/mcallegari/qlcplus → `resources/fixtures/` (~3.000 .qxf)
- **Lizenz: Apache-2.0** — Nutzung mit Quellenangabe erlaubt
- Eine QLC+-Installation bringt dieselben Dateien mit
  (`C:\QLC+\Fixtures` bzw. `/usr/share/qlcplus/fixtures`).
- Direkt mit dem LightOS-QXF-Import einlesbar (ganzer Ordner auf einmal).

### 3. Herstellerdokumentation
- DMX-Kanalbelegungen aus Bedienungsanleitungen sind Faktendaten und dürfen
  als eigenes Fixture-Profil erfasst werden (Fixture-Editor in LightOS).

## Bibliothek herunterladen (FM-53)

Beim **ersten Start** fragt LightOS, ob eine freie Geräte-Bibliothek geladen
werden soll — aber nur, solange die Bibliothek nichts außer den mitgelieferten
Profilen enthält (den eingebauten und denen der LightOS-Bibliothek unter
`fixtures/bibliothek/`, FM-60). Ohne Zustimmung wird **nichts** heruntergeladen. Später geht
es jederzeit über **Datenbank → Geräte-Bibliothek herunterladen...**

Startet LightOS direkt mit einer Show (`--show`, etwa per Autostart), blockiert
kein Dialog den Start: Statt der Frage steht unten in der Statuszeile der Knopf
**Geräte-Bibliothek laden…**. Die Frage gilt erst mit einer Antwort als erledigt
und kommt beim nächsten Start ohne `--show` wieder. Im Kiosk-Modus wird nicht
gefragt (FM-72).

- **Quellen:** QLC+-Fixtures einer festen Version (Apache-2.0, GitHub-Archiv)
  oder die Open Fixture Library als QLC+-Export (MIT). Lizenz, Link und
  ungefähre Größe (QLC+ ca. 12,7 MB, OFL ca. 2,7 MB) stehen im Dialog, **bevor**
  geladen wird. Bis zum Klick auf **Herunterladen** geht keine Anfrage ins Netz.
- **Was passiert:** Download mit SHA-256-Prüfsumme (bei QLC+ gegen die geprüfte
  Fassung; weicht die Datei ab, wird nichts importiert und der Dialog sagt
  warum) → nur die `.qxf`-Dateien
  werden ausgepackt → Import über den vorhandenen QLC+-Import. Vorhandene und
  eigene Profile bleiben unverändert, Doppelte werden übersprungen.
- **Herkunft je Profil:** Quelle, Lizenz, Lizenz-Link, Archiv-Adresse,
  Prüfsumme und Zeitpunkt stehen in `fixtures.db` (Tabelle `profil_herkunft`).
- **Abbrechen** ist jederzeit möglich. Während des Downloads bleibt alles, wie es
  war; im Import bleiben die schon eingelesenen Profile (mit Herkunft) stehen.
  **Ohne Netz** meldet der Dialog das,
  ändert nichts und fragt beim nächsten Start erneut; „Nicht jetzt“ dagegen
  zählt als Antwort, ebenso das Schließen per X oder Esc.

## Was du manuell bereitstellen kannst

Ohne den Download-Dialog, z. B. ohne Internet am Rechner:

1. QLC+ herunterladen/installieren **oder** das QLC+-Repo als ZIP laden,
2. den Ordner `resources/fixtures` (bzw. `Fixtures` der Installation)
   bereitstellen,
3. in LightOS: Patchen → QLC+-Import → diesen Ordner wählen.

Der Import läuft im Hintergrund-Thread mit Fortschrittsanzeige; vorhandene
Fixtures werden gezählt und übersprungen.

## Dokumentationspflicht

Beim Import aus QLC+/OFL gilt: Quelle in der Show-Doku nennen (Apache-2.0
verlangt den Lizenzhinweis, MIT die Copyright-Notiz). Dieses Dokument dient
als zentraler Nachweis; die Lizenzen liegen den jeweiligen Projekten bei.
