# Fixture Library — Aufbau & Pflege

> Stand: 2026-06-10 · Wie LightOS Fixture-Profile speichert, wie Modi und
> Wertebereiche (ChannelRanges) funktionieren und wie der Programmer daraus
> generische Bedienelemente baut.
> Verwandt: [MOVING_HEADS.md](MOVING_HEADS.md) ·
> [FUTURE_FIXTURE_GENERATOR.md](FUTURE_FIXTURE_GENERATOR.md)

---

## 1. Datenmodell (`src/core/database/models.py`)

```
Manufacturer ─< FixtureProfile ─< FixtureMode ─< FixtureChannel ─< ChannelRange
```

| Ebene | Wichtige Felder | Bedeutung |
|---|---|---|
| `FixtureProfile` | `short_name`, `fixture_type`, `source` | ein Geraetemodell (z. B. ZQ02001) |
| `FixtureMode` | `name`, `channel_count` | DMX-Modus (z. B. „9-Kanal" / „11-Kanal") |
| `FixtureChannel` | `channel_number`, `name`, `attribute`, `default_value`, `highlight_value` | ein DMX-Kanal im Modus |
| `ChannelRange` | `range_from`, `range_to`, `name`, **`kind`** | benannter Wertebereich (z. B. 10–19 „Rot") |

**`attribute`** ist der maschinenlesbare Kanaltyp. Verfuegbare Werte
(Editor-Dropdown, `fixture_editor.py` `CHANNEL_ATTRS`): `intensity`,
`color_r/g/b/w/a/uv`, `cmy_c/m/y`, `color_wheel`, `pan(_fine)`, `tilt(_fine)`,
`speed`, `shutter`, `strobe`, `gobo_wheel`, `gobo_rotation`, **`gobo_fx`**,
`prism`, `prism_rotation`, `frost`, `iris`, `zoom`, `focus`, `macro`,
**`reset`**, `raw`. (`gobo_fx` und `reset` neu seit 2026-06-10.)

**`ChannelRange.kind`** (M1.2) macht Bereiche maschinell auswertbar:
`open` · `closed` · `strobe` · `color` · `gobo` · `rotate` · `shake` ·
`sound` · `reset` · `""` (unbekannt). Ohne expliziten kind wird er konservativ
aus dem Namen abgeleitet (`_infer_range_kind`); im Seed koennen Ranges als
4-Tupel `(from, to, name, kind)` exakt angegeben werden.

## 2. Woher Profile kommen

1. **Builtin-Seed** — `fixture_db._seed()` (Generic, Chauvet, Eurolite, ADJ,
   ZQ01424, ZQ02001, U King Spider 14ch, Conti Moving Head 11ch, Klein Conti
   7ch RGBW, Party Lights Laser 7ch …). Laeuft bei leerer DB
   (`%APPDATA%\LightOS\fixtures.db`).
2. **`ensure_builtins()`** — laeuft bei jedem Start: ruestet fehlende
   Builtins nach **und aktualisiert veraltete builtin-Profile in-place**
   (Signatur-Vergleich Mode-Name → Attributliste). Die Profil-ID bleibt
   stabil, daher ueberleben bestehende Patches (sie referenzieren
   `fixture_profile_id` + `mode_name`). Beispiel: die ZQ02001-Korrektur
   (Dimmer/Strobe-Tausch, siehe [MOVING_HEADS.md](MOVING_HEADS.md)).
3. **QLC+-Import** (`qxf_import.py`) und **Fixture-Editor** (eigene Profile,
   `source != "builtin"` — werden von ensure_builtins nie angefasst).
4. **Beispiel-Skripte** (`examples/add_zq0*.py`) — delegieren inzwischen an
   `ensure_builtins()`, die Definition lebt nur noch an einer Stelle.

## 3. Modi sauber abbilden

Geraete mit mehreren DMX-Modi (z. B. ZQ02001 mit 9 und 11 Kanaelen) bekommen
**einen `FixtureMode` pro Modus** mit korrekter Kanalanzahl. Beim Patchen wird
der Modus gewaehlt; `get_channels_for_patched()` (gecacht, laedt Ranges eager)
liefert dem Renderer und der UI die richtigen Kanaele. **Keine modusabhaengige
Sonderlogik im UI-Code** — Kanalnummern und Wertebereiche kommen vollstaendig
aus der Definition.

## 4. Wie der Programmer Capabilities nutzt

- Attribut-Gruppen (`programmer_view.ATTR_GROUPS`) sortieren Kanaele in die
  Tabs Intensity / Color / Position / Gobo / Weitere. `shutter`/`strobe`
  liegen im **Intensity**-Tab (neben dem Dimmer), sind aber bewusst nicht in
  `INTENSITY_ATTRS` (Grand Master/Dimmer-Logik bleibt reiner Dimmer).
- Schnellwahl-Kacheln (`src/ui/widgets/preset_tile.py`) entstehen aus den
  ChannelRanges: Farbrad-Kacheln (kind `color`/`open`, inkl. Split-Farben),
  Strobe-Status + Speed (kind `open`/`closed`/`strobe`), Gobo-Kacheln mit
  Icon-Vorschau (kind `gobo`/`shake`/`rotate`, Icons:
  `src/ui/widgets/gobo_icons.py`), Auto-Farbwechsel (kind `rotate`),
  Reset-Button (Attribut `reset`).
- **Kein Raten:** fehlen Ranges/kinds, zeigt die UI nur Fader bzw. neutrale
  Kacheln.

## 5. Profile richtig pflegen (Checkliste)

1. Kanal-Reihenfolge **gegen das Geraet/Handbuch** pruefen — klassische Fehler
   sind vertauschte Dimmer/Strobe-Kanaele (genau das war beim ZQ02001 der Fall).
2. Jedem Kanal das passende `attribute` geben (nicht `raw`/`macro`, wenn es
   ein passendes gibt; Reset-Kanaele als `reset`, nie als zweiten `macro` —
   der Programmer dedupliziert nach Attribut).
3. Wertebereiche als ChannelRanges mit `kind` pflegen — erst dadurch entstehen
   Farb-/Gobo-/Strobe-Buttons. Gobo-Namen beschreibend waehlen
   („Gobo 6 (Spirale)"), dann passt auch die Icon-Vorschau.
4. Unklare Funktionen **neutral benennen und als Annahme dokumentieren**
   (siehe MOVING_HEADS.md, Abschnitt „Dokumentierte Annahmen").
5. Defaults: Pan/Tilt = 128 (Mitte), Dimmer/Strobe = 0; `highlight_value`
   fuer „Geraet sichtbar machen".
6. Tests ergaenzen (`tests/test_zq02001_profile.py` als Vorlage: Layout,
   Bereiche, ensure_builtins-Idempotenz).

> Mittelfristig soll ein **Fixture Generator** diese Checkliste durch eine
> gefuehrte UI ersetzen: [FUTURE_FIXTURE_GENERATOR.md](FUTURE_FIXTURE_GENERATOR.md)
