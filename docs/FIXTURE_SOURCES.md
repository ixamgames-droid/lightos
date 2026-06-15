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

## Was du manuell bereitstellen musst

LightOS lädt bewusst **nichts automatisch aus dem Netz**. Für eine
Massen-Erweiterung der Bibliothek:

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
