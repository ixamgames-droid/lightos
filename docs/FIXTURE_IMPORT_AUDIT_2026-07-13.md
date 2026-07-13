# Fixture-Import-Audit — QXF & QXW (2026-07-13)

**Auftrag:** AUD-10 (P2, reine Doku) — verifizierte Bug-/Risiko-Liste zum Import von QLC+-
Fixture-Definitionen (`.qxf`) und QLC+-Workspaces (`.qxw`). Betrachtet:

- `src/core/database/qxf_import.py` — QXF-Kanaltyp→Attribut-Mapping (Preset/Group/Name),
  Mehrkopf-`#N`-Ableitung, Fehlertoleranz bei korrupten/unvollständigen QXF.
- `src/core/show/qxw_importer.py` — QLC+-Workspace-Parser (Fixture-/Mode-Auflösung, Adress-Offsets).
- Nachbarschaft: `src/core/attr_groups.py` (`classify_attr`/`ATTR_LABELS`), die Mehrkopf-
  Vorkommens-Logik in `src/core/app_state.py` (`channel_occurrence_keys`) und die einzige
  QXW-Aufrufstelle `src/ui/main_window.py` (`_import_qxw`).

**Abgrenzung:** Dies ist ein Audit, **kein** Code-Fix. Kein Test wird hier hinzugefügt; die
Befunde sind mit einem Wegwerf-Import gegen eine In-Memory-DB **empirisch belegt** (siehe
Methodik), Zeilennummern gegen den Worktree-Stand vom 2026-07-13.

## Methodik

Fünf Dimensionen, jede Hypothese am echten Code + einem QXF/QXW-Beispiel-Snippet verifiziert
(belegt/widerlegt):

1. **Mapping-Vollständigkeit** — welche QLC+-`Preset`/`Group`-Werte werden erkannt, welche fallen
   auf `raw` bzw. die Namens-Heuristik durch?
2. **Klassifikations-Kohärenz** — emittiert der Import Attributnamen, die `attr_groups.classify_attr`
   / `attr_label` **nicht** kennt (landen also in „Other" mit Rohnamen)? Das ist genau die
   ENG-07-Fallenklasse — dessen Attributname (`prism_rotation`) stammt aus exakt diesem Import
   (`qxf_import.py:112-113`, dokumentiert in `attr_groups.py:34-36`).
3. **Mehrkopf-`#N`-Ableitung** — der Import emittiert **kein** `#N`; Köpfe entstehen implizit über
   wiederholte Basis-Attribute (`color_r` zweimal) und werden erst zur Laufzeit per
   Vorkommens-Zähler in `channel_occurrence_keys` (`app_state.py:2221-2236`) zu `attr#N`. Korrekt
   nur, wenn die Kanal-Reihenfolge (= `channel_number`-Sortierung) stimmt.
4. **QXF-Fehlertoleranz** — Verhalten bei fehlenden/kaputten `Number`-Attributen, fehlenden
   `<Channel>`-Definitionen, korruptem XML.
5. **QXW-Auflösung** — Adress-/Universe-Offsets (0- → 1-basiert), Verhalten bei defekten Feldern,
   und ob das Parse-Ergebnis überhaupt in die Show übernommen wird.

**Belegte Reproduktion (Kurzform, alle in dieser Runde ausgeführt):**

- Zweibank-RGB-Spider (`IntensityRed`/`IntensityGreen` je zweimal) → gespeichert als
  `[(1,color_r),(2,color_g),(3,color_r),(4,color_g)]`, Laufzeit-Keys
  `[color_r, color_g, color_r#1, color_g#1]` → **Mehrkopf-Ableitung korrekt** (widerlegt als Bug).
- `SpeedPanTiltSlowFast`-Kanal → Attribut `speed` → `classify_attr('speed') == 'Other'`,
  `attr_label('speed') == 'speed'` → **belegt** (FIMP-01).
- QXF-Mode mit `Number="xx"` (ungültig) neben `Number="2"` → beide Kanäle bekommen
  `channel_number == 3` (Kollision) → **belegt** (FIMP-02).
- QXW mit einem Fixture mit `Address="notanumber"` → Fixture **still verworfen**, Meldung zählt
  nur die überlebenden → **belegt** (FIMP-04).

## Befunde (nach Severity)

| Nr | Datei:Zeile | Schwere | Beschreibung | Status |
|----|-------------|---------|--------------|--------|
| **FIMP-01** | `src/core/database/qxf_import.py:75-80`, `:127` · `src/core/attr_groups.py:16-47`, `:57-79` | 🟡 P3 | **`speed`-Kanäle landen in „Other" mit Rohlabel — die ENG-07-Falle, ein Schritt weiter.** `PRESET_MAP` bildet `SpeedPan…/SpeedTilt…/SpeedPanTilt…` (`:75-80`) und `GROUP_MAP["Speed"]` (`:127`) auf das Attribut `speed` ab. `attr_groups.ATTR_GROUPS` (`:16-47`) enthält aber **keine** Gruppe mit `speed`, und `ATTR_LABELS` (`:57-79`) kein Label dafür → `classify_attr("speed")` fällt durch Pass 1 **und** Pass 2 auf `"Other"`, `attr_label("speed")` gibt den Rohnamen `"speed"` zurück. Jeder importierte Moving Head mit Pan/Tilt-Speed-Kanal zeigt diesen im „Other"-Tab mit englischem Rohnamen statt in Position/Effect mit deutschem Label. Analog steht `effect_speed` sehr wohl in `Effect` — die Inkonsistenz ist offensichtlich. | **belegt** (`classify_attr('speed')=='Other'`, `attr_label('speed')=='speed'`) |
| **FIMP-02** | `src/core/database/qxf_import.py:521-527` (Kern: `:525` `num = len(ch_refs)`) | 🟠 P2 | **Kaputtes/fehlendes `Number` im Mode kollidiert auf `channel_number` und verschiebt die Adressbelegung.** Der Fallback bei nicht-parsebarem `Number` ist der **fixe** Wert `len(ch_refs)` (`:525`). Mehrere defekte Refs — oder ein defekter Ref neben dem legitim letzten Kanal — bekommen damit **dieselbe** `channel_number`. Empirisch: Mode mit `<Channel>Red</Channel>` (kein `Number` → Default `"0"`→1), `<Channel Number="xx">Green` (→ Fallback 3) und `<Channel Number="2">Blue` (→3) ergibt gespeicherte Kanäle `[(1,color_r),(3,color_g),(3,color_b)]` — Kanal 2 fehlt, 3 doppelt belegt. Da `get_channels_for_mode` nach `channel_number` sortiert (`app_state.py:2206`), wird die Kopf-/Attribut-Reihenfolge unbestimmt und die DMX-Offsets stimmen nicht mehr. | **belegt** (Kollision auf `channel_number==3` reproduziert) |
| **FIMP-03** | `src/core/database/qxf_import.py:57-65`, `:87-89`, `:38-49`, `:93-94` | 🟢 P4 (bewusste Grenze) | **Erkannte, aber modell-lose Kanaltypen fallen auf `raw` → aus Farb-/Feature-Logik heraus.** HSV/Indigo/Lime (`IntensityHue/Saturation/Value/Indigo/Lime`, `:57-65`), Farbtemperatur-Mischer (`ColorCTO/CTB/CTCMixer`, `:87-89`) und **alle** Fine-Farbbytes (`Intensity*Fine`, `:44-56`) werden bewusst auf `raw` gesetzt → kein Color-Tab/Picker, 16-Bit-Dimmer verliert das Fine-Byte als steuerbaren Wert. Footprint/Adressbreite bleibt korrekt (jeder Kanal existiert), nur die Semantik fehlt. Der Code dokumentiert das als Absicht (Kommentare `:50-65`, `:87`). Kein Fehler, aber eine reale Feature-Lücke für HSV-/CTO-Mover. | **belegt, bewusste Grenze** |
| **FIMP-04** | `src/core/show/qxw_importer.py:88-110` (Broad-`except` `:108-110`), `:97` | 🟠 P2 | **QXW verwirft ganze Fixtures still bei einem einzigen defekten Zahlenfeld; die Erfolgsmeldung überzählt Vertrauen.** `_parse_fixture` liest `Universe`/`Address`/`Channels` per `int(...)` (`:95-97`) im gemeinsamen `try`; ein einziges nicht-numerisches Feld (`Address="notanumber"`) wirft → `except Exception → return None` (`:108-110`) → das komplette Fixture verschwindet, nur ein `print` auf stdout. Die zusammenfassende Meldung (`:69-72`, angezeigt in `main_window.py:1486-1492`) zählt lediglich die überlebenden Fixtures → der Nutzer sieht „Importiert: 2 Fixtures" und erfährt nie, dass ein drittes wegen eines Tippfehlers ausfiel. Zusätzlich macht ein fehlendes `<Channels>` still `channel_count=1` (Default `"1"`, `:97`) → falscher Footprint. | **belegt** (drittes Fixture verworfen, Meldung „2 Fixtures") |
| **FIMP-05** | `src/ui/main_window.py:1471-1492` · `src/core/show/qxw_importer.py:24-76` | 🟡 P3 | **QXW-„Import" parst nur, übernimmt aber nichts — Adress-Offsets/Modes werden nie angewandt.** `_import_qxw` ruft `import_qxw`, zeigt die Zählmeldung und einen Hinweis, aber die geparsten `fixtures`/`functions`/`virtual_console` werden **nirgends** in Patch/Show gemappt (der Dialog sagt es selbst: „Mapping … ist nicht automatisch"). Die geparsten `universe`/`address` (0→1-basiert, korrekt, `qxw_importer.py:95-96`) und `mode_name` (nur String, nie gegen ein DB-Profil aufgelöst) sind reine Anzeigedaten. Für die Nutzererwartung „QLC+-Workspace importieren" ist das eine große Funktionslücke, kein Rechenfehler. | **belegt** (Aufrufstelle verwirft das Ergebnis) |

## Positiv bestätigt (widerlegte Verdachtsfälle)

- **Mehrkopf-`#N`-Ableitung korrekt.** Der Import emittiert bewusst kein `#N`; wiederholte
  Basis-Attribute (`color_r`, `pan`, `tilt` …) werden erst zur Laufzeit über den Vorkommens-Zähler
  in `channel_occurrence_keys` (`app_state.py:2221-2236`) zu `attr#N` — Kopf 0 = Basisname, jedes
  weitere Vorkommen `+#N`. Reproduziert: Zweibank-Spider → `color_r, color_g, color_r#1, color_g#1`.
  Voraussetzung ist nur die korrekte `channel_number`-Reihenfolge — die FIMP-02 im Korruptionsfall
  verletzt, im Normalfall aber hält.
- **`prism_rotation`/`gobo_rotation`-Klassifikation korrekt (ENG-07/ENG-09 halten).**
  `PrismRotationSlowFast → prism_rotation` (`qxf_import.py:112-113`) und `GoboIndex → gobo_rotation`
  (`:93`) stehen **exakt** in `Effect` bzw. `Gobo` (`attr_groups.py:40`, `:32`), sodass der
  Beam-Substring `prism` sie nicht fälschlich als Beam zieht; `classify_attr` strippt das
  `#N`-Suffix vorab (`attr_groups.py:110-115`). Verifiziert: `classify_attr('prism_rotation')=='Effect'`.
- **CMY-Mischung korrekt geführt.** `IntensityCyan/Magenta/Yellow → cmy_c/cmy_m/cmy_y`
  (`qxf_import.py:51-53`) stehen exakt in `Color` (`attr_groups.py:27-29`) → Color-Tab/Picker, kein
  Other-Fallback.
- **QXF-Datei-Isolierung robust.** `import_all_qxf` kapselt jede Datei in `begin_nested()` +
  `try/except` (`qxf_import.py:550-556`); korruptes XML gibt sauber `False` zurück
  (`:422-426`) — eine kaputte `.qxf` rollt nur sich selbst zurück, nie den ganzen Lauf.

## Empfohlene ENG-/QA-Folge-Items

- **ENG (P3): `speed` in die Klassifikation aufnehmen (FIMP-01).** Entweder `speed` (+ `pan_speed`,
  `tilt_speed`) in eine Gruppe (`Position` oder `Effect`) in `attr_groups.ATTR_GROUPS` und ein Label
  in `ATTR_LABELS` eintragen — **oder** bewusst als „Other" dokumentieren. Keine reine
  Import-Änderung; die Wahrheit ist die gemeinsame `attr_groups`-Quelle.
- **ENG (P2): QXF-`Number`-Fallback kollisionsfrei machen (FIMP-02).** Statt `num = len(ch_refs)`
  einen laufenden Index (Position im Mode) oder das Überspringen defekter Refs verwenden;
  optional auf Duplikate in `channel_number` prüfen und den Import als unvollständig melden.
- **ENG (P2): QXW-Feldfehler granular machen + sichtbar zählen (FIMP-04).** Pro Zahlenfeld einzeln
  parsen (Default statt Totalverlust), verworfene/teil-defekte Fixtures in der Rückgabe **zählen**
  und in der UI-Meldung ausweisen („2 importiert, 1 übersprungen").
- **ENG (P2/größer): QXW-Ergebnis tatsächlich anwenden (FIMP-05)** — Fixtures per
  Hersteller/Modell/Mode gegen die DB auflösen und mit den (bereits korrekten) 1-basierten
  Adressen patchen, sonst den Menüpunkt als „nur Vorschau" kennzeichnen.
- **QA: Regressions-Guard** für die ENG-07-Fallenklasse (siehe unten), damit künftig **kein**
  vom Import emittierter Attributname unklassifiziert nach „Other" fällt.

## Regressionstest-Idee

Headless, gegen eine In-Memory-DB (`Base.metadata.create_all` + `Session`), Muster wie in der
Methodik oben:

1. **Klassifikations-Vollständigkeit (deckt FIMP-01 + verhindert künftige ENG-07-Rückfälle):** Über
   alle **distinct** Zielwerte von `PRESET_MAP` und `GROUP_MAP` (außer `raw`) iterieren und
   `assert classify_attr(attr) != "Other"` sowie `assert attr in ATTR_LABELS` fordern — so schlägt
   jeder künftig neu gemappte, aber nicht klassifizierte Attributname sofort an.
2. **`Number`-Fallback (FIMP-02):** QXF-Mode mit einem `Number="xx"`-Ref neben `Number="2"`
   importieren und `assert` erheben, dass die `channel_number` aller Kanäle des Modes **eindeutig**
   sind.
3. **QXW-Teilfehler (FIMP-04):** QXW mit 3 Fixtures, davon 1 mit defektem `Address`, durch
   `import_qxw` schicken und prüfen, dass die Rückgabe die Anzahl der übersprungenen Fixtures
   ausweist (nach dem Fix) — bzw. dokumentieren, dass sie es heute **nicht** tut.
