# Fixture Generator

> Stand: 2026-06-14 · **Umgesetzt** (F-23 / X-4).
> Kontext: [FIXTURE_LIBRARY.md](FIXTURE_LIBRARY.md) · [MOVING_HEADS.md](MOVING_HEADS.md)

## Start (UI-Pfad)

**Patch-Tab → Button „Gerät erstellen…"** öffnet den `FixtureGeneratorDialog`.
Nach dem Speichern wird `SyncEvent.REFRESH_ALL` emittiert — Patch-Tabelle und
Bibliothek aktualisieren sich automatisch (das neue Profil hat `source="user"`
und ist sofort patchbar).

## Was er kann (Ist-Stand)

- **Kopf:** Hersteller, Modell, Kurzname, Typ, Leistung, Notizen.
- **Mehrere Modi** pro Fixture (z. B. 9ch/11ch), umbenennbar, mit eigener
  Kanal-Reihenfolge.
- **Kanal-Editor** (Tabelle, Hoch/Runter): pro Kanal Attribut aus geführter
  Combo **plus Freitext** (mehrfach gleiche Attribute erlaubt — z. B. zwei
  Tilt), Default-/Highlight-Wert, Invert, Auflösung **8bit/16bit** mit
  **Fine-Kanal-Kopplung**.
- **Bereichs-Editor je Kanal:** benannte Segmente (`range_from`/`range_to`,
  Name, `kind`), „Art aus Namen" leitet `kind` automatisch ab, kompakte
  Schnellwahl-Vorschau (Farb-/Gobo-/Strobe-Hinweise).
- **Live-Validierung** (nicht-blockierend): 0–255, Überlappung, Lücke,
  verdrehte Bereiche, doppelte Attribute, Dimmer↔Strobe-Plausibilität,
  fehlender `open`-Bereich am Shutter, 16-bit ohne Fine-Kanal, Modus-Vergleich.
- **Live-Test (echte DMX-Ausgabe):** Universe + Startadresse wählbar, ein Fader
  pro Kanal schreibt direkt ins Universe des globalen OutputManagers,
  „Wackeln" rampt einen Kanal hin/her (Pan/Tilt-Identifikation), „Blackout"
  und **sauberes Restore** der vorher gemerkten Werte beim Stop/Schließen.
- **`.qxf`-Import** als Startpunkt (kein Export).
- **Markdown-Export** des Kanal-Layouts (wie MOVING_HEADS.md).

## Kernlogik (testbar, ohne Fenster)

`src/ui/widgets/fixture_generator.py`:

| Funktion/Klasse | Zweck |
|---|---|
| `GeneratorModel`/`GenMode`/`GenChannel`/`GenRange` | UI-unabhängiges Datenmodell |
| `build_profile_payload(model)` | Modell → serialisierbares DB-Payload |
| `save_generated_profile(payload, engine=…)` | Payload → Fixture-DB (`source="user"`) |
| `validate_model(model)` | Liste `(severity, text)` — `warn`/`error`, nicht-blockierend |
| `LiveTester(universe, base_address)` | `write_channel`/`blackout`/`restore` |
| `model_to_markdown(model)` | Kanal-Layout als Markdown |
| `model_from_qxf(path)` | `.qxf` → `GeneratorModel` (Startpunkt) |

Speicher-Helfer: `src/core/database/fixture_db.py` → `create_user_profile(payload, engine=…)`
(idempotent/nicht-brechend: legt nur Neues an).

Tests: `tests/test_fixture_generator.py` (Round-Trip, Validierungs-Heuristiken,
16-bit-Persistenz, Live-Test gegen ein echtes `Universe`).

---

## Ursprüngliche Motivation (zur Einordnung)

## Motivation

Das manuelle Anlegen von Fixture-Profilen ist fehleranfaellig. Realer Fall:
beim ZQ02001 Mini Moving Head waren **Dimmer- und Strobe-Kanal vertauscht**
und der 9-Kanal-Modus falsch aufgebaut — bemerkt erst am echten Geraet
(Korrektur: 2026-06-10, siehe MOVING_HEADS.md). Auch Gobo-/Farbrad-Werte-
bereiche werden leicht vertippt („3–16" statt „16–23").

Ein **Fixture Generator** soll solche Fehler strukturell verhindern: Kanaele,
Modi, Wertebereiche, Farben, Gobos, Strobe, Reset und Effektbereiche werden
**grafisch erfasst**, daraus entsteht automatisch eine konsistente
Fixture-Definition.

## Was der Generator koennen soll

1. **Grafische Erfassung**
   - Modi anlegen (z. B. 9ch / 11ch), Kanaele per Drag & Drop ordnen.
   - Pro Kanal: Attribut-Auswahl (gefuehrte Liste statt Freitext),
     Default-/Highlight-Wert, Feinkanal-Zuordnung (16-bit).
   - Pro Kanal: Wertebereiche als Tabelle/Slider-Strecke mit `kind`
     (open/strobe/color/gobo/shake/rotate/reset/…).
2. **Automatische UI-Bausteine**
   - **Farb-Buttons automatisch erzeugen** (inkl. Split-Farben aus zwei
     Farbwoertern, Vorschaufarbe direkt im Generator waehlbar).
   - **Gobo-Buttons automatisch erzeugen**, mit Auswahl/Erstellung der
     **Icons/SVGs** je Gobo (gobo_icons-Stile oder eigene Zeichnung).
   - Strobe-/Shutter-Schnellwahl und Reset-Button aus den kinds ableiten.
3. **Validierung**
   - DMX-Bereiche: lueckenlos? ueberlappend? 0–255 eingehalten?
   - Plausibilitaet: Dimmer und Strobe vertauscht? (Heuristik: Strobe-Kanal
     mit 0–255-Default, Dimmer mit Ranges → Warnung), doppelte Attribute
     (z. B. zweimal `macro`), fehlender `open`-Bereich am Shutter.
   - Vergleich zwischen Modi (gleiche Funktionen, andere Kanalnummern).
4. **Mehrere Modi pro Fixture verwalten** — gemeinsame Kanal-Definitionen
   einmal pflegen, pro Modus nur Reihenfolge/Vorhandensein.
5. **Dokumentation automatisch erzeugen** — Markdown-Tabelle des Kanal-Layouts
   + Wertebereiche (wie MOVING_HEADS.md), inklusive markierter Annahmen.
6. **Export/Import** — in die Fixture-DB schreiben (source="user"),
   optional QLC+ `.qxf`/GDTF-Export.

## Nutzen

- Weniger manuelle Fehler (vertauschte Kanaele, falsche Gobo-Werte).
- Schnellwahl-Kacheln (Farben, Gobos, Strobe) entstehen ohne Code-Aenderung,
  weil das Capability-System (`ChannelRange.kind`) bereits generisch ist.
- Eigene Geraete der Nutzer sind in Minuten statt Stunden sauber definiert.

## Vorhandene Bausteine (heute schon im Code)

| Baustein | Datei |
|---|---|
| Datenmodell inkl. `ChannelRange.kind` | `src/core/database/models.py` |
| Seed-/Update-Mechanik (in-place, idempotent) | `src/core/database/fixture_db.py` (`ensure_builtins`) |
| Einfacher Fixture-Editor (Tabelle) | `src/ui/widgets/fixture_editor.py` |
| Generische Schnellwahl aus Ranges | `src/ui/widgets/preset_tile.py` |
| Gobo-Icon-Renderer | `src/ui/widgets/gobo_icons.py` |
| Profil-Tests als Vorlage | `tests/test_zq02001_profile.py` |

## Status

**Idee / Backlog.** Erfasst auch in
[OPEN_POINTS_OVERVIEW.md](OPEN_POINTS_OVERVIEW.md). Naechster sinnvoller
Schritt waere ein UI-Mockup des Bereichs-Editors (Slider-Strecke mit
benennbaren Segmenten) auf Basis des bestehenden Fixture-Editors.
