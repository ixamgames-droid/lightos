# Fixture Library — Aufbau & Pflege

> Stand: 2026-06-10 · Wie LightOS Fixture-Profile speichert, wie Modi und
> Wertebereiche (ChannelRanges) funktionieren und wie der Programmer daraus
> generische Bedienelemente baut.
> Verwandt: [MOVING_HEADS.md](MOVING_HEADS.md) ·
> [FUTURE_FIXTURE_GENERATOR.md](FUTURE_FIXTURE_GENERATOR.md) ·
> [FIXTURE_3D_GALLERY.md](FIXTURE_3D_GALLERY.md) (gerenderte 3D-Modelle aller Klassen)
>
> Bebilderte Anleitung für Anwender: [Geräte-Bibliothek & eigene Profile](anleitung_geraete_bibliothek/ANLEITUNG.md)

---

## 1. Datenmodell (`src/core/database/models.py`)

```
Manufacturer ─< FixtureProfile ─< FixtureMode ─< FixtureChannel ─< ChannelRange
```

| Ebene | Wichtige Felder | Bedeutung |
|---|---|---|
| `FixtureProfile` | `short_name`, `fixture_type`, `source` | ein Geraetemodell (z. B. ZQ02001) |
| `FixtureMode` | `name`, `channel_count`, **`grid_rows`/`grid_cols`**, **`white_rows`/`white_cols`** | DMX-Modus (z. B. „9-Kanal" / „11-Kanal") |
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

**`FixtureMode.grid_rows`/`grid_cols`** (VIZ-50a) ist die **physische**
Anordnung der Zonen/Pixel eines Panels in DIESEM Modus — `0/0` heisst „nicht
hinterlegt". Ohne die Angabe leitet der 3D-Renderer die Form near-square aus der
Pixelzahl ab (`panelGrid`), was fuer eine Leiste falsch ist: 48 Zonen wurden zu
einem 7x7-Quadrat statt zu 12x4. Im Seed steht die Form als optionales drittes
Tupel-Element `(mode_name, channels, (rows, cols))`; `ensure_builtins` traegt sie
ueber `_ensure_panel_geometrie` auch in bereits befuellte Bibliotheken nach — der
Signatur-Vergleich unten sieht sie naemlich nicht, weil sie in keinem Attribut
steht. Sie sitzt am **Modus** und nicht am Profil, weil die Pixelzahl
modusabhaengig ist; und nicht am gepatchten Geraet, weil sie fuer jedes Exemplar
gilt (im Gegensatz zu `pixel_order`/`element_rotation`, die vom Geraetemenue bzw.
von der Montage abhaengen).

**Wo die Angabe herkommt** (FM-23/FM-26): aus dem Seed (Builtins), aus dem
**Fixture-Editor** UND aus dem **Fixture-Generator** (Patch-View → „Generator")
— beide Dialoge tragen die Zeile „Pixel-Raster: Zeilen x Spalten" an jedem
Mode-Tab — oder aus dem **QXF-Import**, der sie aus `<Physical><Layout Width=
Height=/>` uebernimmt (QLC+ fuehrt sie dort; `Width` sind Spalten, `Height`
Zeilen). Das gilt fuer **beide** QXF-Wege: den Import in die Bibliothek
(`qxf_import`) und den Import-Knopf des Generators, der eine `.qxf` als
Startpunkt zum Weiterbearbeiten laedt — dort steht die Zahl danach im
sichtbaren Feld und laesst sich vor dem Speichern noch aendern (bis FM-26 ging
sie auf diesem Weg verloren). Ein `1x1` gilt dabei als KEINE Angabe: das ist QLC+' Vorgabewert, und
uebernommen wuerde daraus fuer ein 48-Pixel-Panel eine 48 Zeilen hohe Saeule —
`panelGrid` zieht die fehlende Zahl aus der Pixelzahl hoch und behandelt das
Ergebnis dann als *explizit*, also samt physischer Panel-Masse.

> **Bedienung beider Dialoge (FM-30):** `Return` in einem Eingabefeld speichert
> **nicht**. Gespeichert wird ausschliesslich ueber den Knopf „Speichern",
> geschlossen ohne Speichern ueber „Abbrechen" oder `Escape`. Vorher loeste ein
> `Return` in irgendeinem Feld den Standardknopf aus — eine getippte Rasterzahl
> plus Return legte ein halb eingegebenes Profil in der Bibliothek an. Im
> Generator war das nicht mehr zu berichtigen, weil er ein bestehendes Profil
> nicht wieder oeffnen kann.

**`FixtureMode.white_rows`/`white_cols`** (CDX-52) ist die Rasterform einer
**eigenen Weiss-Leiste** — eines Streifens weisser LEDs, der NICHT auf dem
Farbraster liegt (der ZQ06121 hat acht Warmweiss-Segmente quer ueber die
Panelmitte). `0/0` heisst „keine eigene Leiste", und dann gibt es im 3D auch
keine. Das ist der Unterschied zur Rasterform oben: dort heisst „nichts
hinterlegt" WEITERRATEN, hier heisst es NEIN.

> ⚠️ Bis VIZ-50b stand hier, das Feld brauche es nicht — der Renderer erkenne
> die Leiste an **weniger `color_w`- als `color_r`-Kanaelen**. Das galt fuer die
> mitgelieferte Bibliothek und sonst nirgends: **eine Kanalzahl traegt keine
> Ortsangabe.** Dieselbe Signatur (48x `color_r` + 8x `color_w`) passt auf eine
> eigene Leiste, auf acht Weiss-LEDs, die IN den Zonen sitzen, und auf ein
> globales Weiss in acht Dimmabschnitten. Ein selbstgebautes Panel mit 48 Zonen
> und EINEM globalen Weiss-Kanal bekam so ein volles Band quer ueber die Mitte.

Hinterlegt wird nur, was die Kanaele nicht sagen koennen: die **Form**, nicht
die **Zahl**. Die Zahl der Segmente bleibt aus den `color_w`-Kanaelen
abgeleitet — der ZQ06121 traegt deshalb `(1, 0)` und nicht `(1, 8)`; eine Kopie
der 8 liefe still daneben. Eingetragen wird die Leiste im **Fixture-Editor**
oder im **Fixture-Generator** (in beiden am Mode-Tab, „Weiss-Leiste: Zeilen x
Spalten") oder im Seed als optionales **viertes** Tupel-Element `(mode_name, channels, (rows, cols), (wrows, wcols))`.
Der **QXF-Import kann sie nicht ableiten**: das QLC+-Format kennt keinen Begriff
fuer ein zweites Raster neben dem Farbraster — `<Layout>` beschreibt EIN Raster,
ein `<Head>` ist eine Kanalgruppe ohne Ortsangabe.

> **Zwei Dialoge, eine Angabe** (FM-26): den Fixture-Editor erreicht man ueber
> die Fixture-Bibliothek, den reicheren **Fixture-Generator** ueber die
> Patch-View. Der Generator hat den Live-Test am echten Geraet und ist damit der
> Weg, auf dem ein selbstgebautes Panel ueblicherweise entsteht — er schreibt
> die vier Zahlen seit FM-26 genauso in den Modus wie der Editor. Wer an einem
> der beiden Dialoge etwas an dieser Zeile aendert, prueft den anderen mit;
> zwischen FM-23 und FM-26 hatte nur einer von beiden die Felder.

### Mehrere Dimmer und Weiß-Segmente (FM-46)

Hat ein Gerät eine **eigene Weiß-Leiste** (mehr oder weniger `color_w`- als
`color_r`-Kanäle) und **mehrere Dimmer**, steht in der Kanalliste nicht, welcher
Dimmer welches Weiß-Segment dimmt. LightOS rät das zur Laufzeit **nie** — ein
falsch geratener Dimmer ließe ein Segment dunkel oder dimmte das falsche, ohne
dass es jemand merkt. Ohne Angabe wählt die Matrix deshalb keinen einzelnen
Dimmer aus, sondern fährt bei „Dimmer mit treiben“ **alle gemeinsam** (FM-46,
Etappe 2 — siehe unten „Ohne Zuordnung“).

Die Angabe macht man im **Fixture-Editor** oder im **Fixture-Generator**, Spalte
**„Weiß-Segment“** der Kanaltabelle (`FixtureChannel.segment`):

- Die Spalte ist nur an Dimmer-Kanälen (`intensity`, `dimmer`, `master`)
  wählbar, an allen anderen leer und grau. „—“ heißt *keine Zuordnung*,
  „1 … n“ ist das n-te Weiß-Segment in Kanalreihenfolge.
- **„Vorschlag aus Reihenfolge“** füllt die Spalte, wenn die Reihenfolge es
  eindeutig hergibt: jeder Dimmer steht direkt **vor** seinem Weiß
  (`Dimmer, Weiß, Dimmer, Weiß`), direkt **nach** ihm, oder die Kanäle bilden
  **gleich große Blöcke** (`Dimmer, R, G, B, Weiß` je Segment). Gibt es keinen
  eindeutigen Vorschlag, sagt der Knopf das und ändert nichts. Weicht der
  Vorschlag von schon eingetragenen Werten ab, fragt er nach (Ja = überall
  übernehmen, Nein = nur leere Zellen füllen).
- Die Zuordnung hängt am Weiß-**Kanal**: löscht oder verschiebt man einen
  Weiß-Kanal oder ändert sein Attribut, ziehen die Segmentnummern mit; ein
  gelöschtes Segment wird zu „—“.
- Solange der Modus eigene Weiß-Segmente und mehrere Dimmer hat, aber keine
  Zuordnung trägt, steht unter der Geometrie-Zeile ein **Hinweis** (im
  Generator zusätzlich in der Hinweisliste, dort mit dem Vorschlag). Derselbe
  Platz meldet eine unstimmige Zuordnung: ein Segment ist mehreren Dimmern
  zugeordnet (dann wirkt es bei keinem), ein Segment gibt es nicht, oder ein
  Dimmer hat als einziger kein Segment.

Mit Bildern Schritt für Schritt:
[Geräte-Bibliothek & eigene Profile, Schritt 4](anleitung_geraete_bibliothek/ANLEITUNG.md#4-mehrere-dimmer-und-weiß-segmente).

**Wie man es im Handbuch erkennt:** in der DMX-Tabelle des Herstellers gehört
ein Dimmer zu dem Weiß, das im selben Abschnitt steht („Zone 2“, „Segment 2“,
„Teil B“) oder direkt davor bzw. danach aufgeführt ist. Steht dort nur
„Dimmer 1“, „Dimmer 2“ ohne Bezug, hilft der Test am Gerät: Weiß-Kanäle auf
voll, dann einen Dimmer nach dem anderen hochziehen und schauen, welches
Segment hell wird.

Wirksam wird **nur die gespeicherte** Zuordnung. Mit ihr zieht ein Weiß-Feld der
Matrix bei „Dimmer mit treiben“ genau den eingetragenen Dimmer auf (derselbe
Weg gilt für Muster-Chaser, Weiß-Regler und Kommandozeile). Ein einzelner
Dimmer braucht keine Angabe: er gilt als gemeinsamer Master und fährt ohnehin
mit. Ältere Bibliotheken bekommen die Spalte beim Start automatisch, ohne
Zuordnung.

**Beim QLC+-Import** (Bibliothek und „QLC+ importieren“ im Generator) wird die
Zuordnung aus den Kopf-Gruppen der `.qxf` gelesen (`<Head>` je Modus) — aber nur,
wenn die Datei sie eindeutig sagt:

- Ein Kopf mit **genau einem** Dimmer und **genau einem** Weiß-Kanal ordnet
  diesen Dimmer dem Segment dieses Weiß zu (n-tes Weiß in Kanalreihenfolge).
- Köpfe ohne Weiß zählen nicht. Mehrere Dimmer oder mehrere Weiß in einem Kopf,
  ein Dimmer in mehreren Weiß-Köpfen (typisch: ein Master-Dimmer, den die Datei
  in jeden Kopf legt) oder ein Segment, das mehrere Dimmer bekämen, ergeben für
  diese Dimmer **keine** Zuordnung.
- Nur Modi mit eigener Weiß-Leiste und mehreren Dimmern; eine schon gespeicherte
  Zuordnung wird nicht überschrieben.

Gemessen an den QLC+-Dateien der 26 betroffenen Modi einer großen Bibliothek
bekommen 13 so eine Zuordnung; bei den übrigen sagt die Datei es nicht (keine
Köpfe, Dimmer außerhalb der Köpfe oder in mehreren). Dort bleibt der Hinweis
im Editor stehen. Bereits importierte Profile ändern sich nicht von selbst,
und ein erneuter Bibliotheks-Import hilft nicht: er überspringt ein Profil,
dessen Hersteller und Modell schon in der Bibliothek stehen. Für ein solches
Profil trägt man die Zuordnung im **Fixture-Editor** ein. („QLC+ importieren“
im Generator liest sie zwar mit, legt beim Speichern aber ein **zusätzliches**
eigenes Profil an — das vorhandene und die damit gepatchten Geräte bleiben, wie
sie sind.)

**Ohne Zuordnung (FM-46, Etappe 2).** Die Matrix soll möglichst immer leuchten,
und ein Hinweis ist besser als ein stumm dunkles Segment:

- Fährt die Matrix die Dimmer („Dimmer mit treiben“), zieht ein Weiß-Feld ohne
  gültige Zuordnung **alle freien** Vorkommen des Dimmers auf
  (`app_state.weiss_rueckfall_dimmer`). Nicht frei ist ein Dimmer, der einem
  *anderen* Weiß-Segment zugeordnet ist, laut Kopf-Karte einem Farbkopf gehört
  oder an einen **reinen Farbabschnitt** grenzt: die Kanalliste wird an den
  Dimmern in Abschnitte geteilt, und ein Dimmer direkt vor oder hinter einem
  Abschnitt mit R/G/B, aber ohne Weiß (RGB-Ring, Pixelsektion) könnte einen
  Farbteil aufleuchten lassen. Liegt das Weiß selbst in einem RGBW-Abschnitt,
  fahren nur die Dimmer an genau diesem Abschnitt. Leitsatz: lieber ein Segment
  zu wenig öffnen als einen fremden Teil — ein Master direkt vor einer
  Pixelsektion fährt deshalb ebenfalls nicht. Das ist kein Raten: es wird nicht
  *ein* Dimmer als „der richtige“ gewählt, sondern bewusst alle freien geöffnet.
  Die Helligkeit trägt der Weiß-Kanal, die Intensität der Matrix wirkt über die
  Dimmer (der Merge skaliert alle Dimmer-Adressen) — nicht doppelt. Teilweise
  Zuordnung: ein Segment mit eigenem Dimmer fährt nur diesen, die übrigen
  Segmente teilen sich die freien. Ein Segment, das mehreren Dimmern zugeordnet
  ist, fährt sie alle.
- Fährt die Matrix die Dimmer nicht, bleibt alles wie bisher: die Dimmer gehören
  dem Nutzer. ⚠️ Das ist seit dem Umbau der Bedienelemente der Normalfall für
  **neue** Matrizen (`drive_intensity` hat kein Bedienelement mehr, neue
  Matrizen stehen auf aus, Matrizen aus älteren Shows ohne den Schlüssel auf an).
- Der **RGB-Matrix-Editor** zeigt unter der Vorschau einen Hinweis, sobald ein
  Gerät auf der Weiß-Achse liegt und die Zuordnung fehlt oder unstimmig ist —
  mit dem Wortlaut passend zu dem, was die Matrix tatsächlich tut.
  `tools/lint_show.py` meldet denselben Fall als Warnung
  `WEISS-DIMMER-ZUORDNUNG`.

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
5. **Eigene Bibliothek** (`fixtures/bibliothek/*.json`, `source = "lightos"`) — siehe
   „Eigene Bibliothek (LightOS-Profile)“ unten.

### Eigene Bibliothek (LightOS-Profile)

Seit FM-56 können mitgelieferte Geräte als **Datei** statt als Python-Tupel vorliegen:
eine JSON-Datei je Gerät unter `fixtures/bibliothek/<hersteller>/<modell>.json`. Das
Format („LightOS-Profil“) ist in [`fixtures/bibliothek/SCHEMA.md`](../fixtures/bibliothek/SCHEMA.md)
beschrieben; Prüfung und Einspielen stehen in `src/core/database/bibliothek_format.py`.

- **Herkunft ist Pflicht.** Jede Datei trägt `quelle` (Handbuch-Titel/Version/Datum/URL)
  und `herkunft` (`art`: `lightos` · `hersteller-handbuch` · `qlcplus` · `ofl`, mit
  `lizenz`). Umgebaute QLC+- (Apache-2.0) und OFL-Profile (MIT) nennen zusätzlich
  Urheber, Originaldatei und die Änderungen; die Lizenztexte deckt der Abschnitt
  „Geräte-Bibliothek“ in `THIRD_PARTY_NOTICES.md`.
- **Einspielen:** `ensure_builtins()` spielt die Dateien mit `source = "lightos"` ein —
  je Datei nur, wenn sie neu ist, sich geändert hat oder ihr Profil in der DB fehlt
  (Stempel je Datei in `bibliothek_stempel`). Eine kaputte Datei bricht den Start nie ab.
  Neu → anlegen; geändert → Kopf und Modi aus der Datei neu aufbauen, die Profil-ID
  bleibt; ungültig → gemeldet und übersprungen. Gibt es Hersteller + Modell schon als
  Builtin oder eigenes Profil, bleibt die Datei draußen — sonst stünde das Gerät doppelt
  in der Bibliothek (FM-43). Ein gleichnamiger **QLC+-Import** verdeckt die Datei nicht
  mehr: das LightOS-Profil kommt dazu und **löst den Import ab** (FM-63) — der Import
  bleibt in der DB (Shows laden ihn weiter über seine ID), Suche und Auswahl bieten das
  LightOS-Profil an, der Fixture-Browser den Import unter „Ältere QLC+-Importe“. Ein im
  Fixture-Editor geändert gespeicherter Import (Bearbeitet-Marke in `herkunft`) zählt wie
  ein eigenes Profil und wird nie abgelöst. `user`- und `qlcplus`-Profile werden nie
  angefasst.
- **Die Herkunft geht nie verloren.** Beim Einspielen und beim Import einer Datei
  steht die vollständige Herkunft (quelle, herkunft, geprueft, autor) auch in der DB
  (`FixtureProfile.herkunft`, JSON). Der Export — Werkzeug wie Editor — liest sie von
  dort; ein QLC+-Import bleibt Apache-2.0, ein im Editor bearbeitetes fremdes Profil
  bekommt den Vermerk in `geaendert`. Lässt sich die Herkunft nicht belegen, bricht
  der Export ab, statt „eigen“ einzutragen.
- **`lightos` zählt wie `builtin`** überall, wo „mitgeliefert vor importiert“ entschieden
  wird: Show-Laden bei nicht passender ID (FM-43), Showbuilder, `tools/_profil.py`,
  Dubletten-Meldung (QA-68). Die Konstante dafür ist `models.MITGELIEFERT_QUELLEN`.
  Der FM-50-Abgleich und die Signatur-Migrationen bleiben bei `builtin` — die Dateien
  haben ihren eigenen Abgleich.
- **Eigene Profile im eigenen Format:** Fixture-Editor → „Als LightOS-Profil
  exportieren…“ / „LightOS-Profil importieren…“ (Import legt ein eigenes Profil,
  `source = "user"`, an). Dasselbe auf der Kommandozeile:
  `tools/bibliothek_profil.py export|import`.
- **QLC+-Datei umbauen:** `tools/bibliothek_profil.py qxf <datei.qxf> --bibliothek` —
  läuft über den vorhandenen QXF-Import (Attribute, Bereichs-Arten, Rasterform,
  Weiß-Segmente aus `<Head>`) und setzt `herkunft` selbst. Ein OFL-Konverter ist
  vorgesehen (`ofl_zu_daten`), aber noch nicht gebaut.
- **Prüfen:** `tools/bibliothek_profil.py pruefen`; Wächter-Test
  `tests/test_fm56_bibliothek_waechter.py`.
- **Builtins bleiben vorerst Tupel.** Der Round-trip Tupel → Datei → DB ist für alle
  eingebauten Profile feldgleich nachgewiesen (`tests/test_fm56_bibliothek_format.py`);
  die Überführung selbst ist ein eigener Schritt, weil sie bestehende Installationen von
  `builtin` auf `lightos` umstellen muss. Bis dahin liegen drei Muster unter
  `fixtures/bibliothek/_beispiele/` (werden nicht eingespielt).

### Profil bearbeiten (UI-74)

Ein gespeichertes Profil öffnet man über **Datenbank → „Fixture-Profil bearbeiten…“**
(Suche nach Hersteller/Modell) oder im Patch per Rechtsklick auf ein Gerät →
**„Profil bearbeiten…“**.

- **Eigene Profile** (`source = "user"`) und **QLC+-Importe** (`qlcplus`) werden im
  Fixture-Editor bearbeitet und an Ort und Stelle gespeichert; die Profil-ID bleibt. Der
  QLC+-Download überspringt ein Profil, das es unter Hersteller + Modell schon gibt — die
  Änderung bleibt also stehen. Ein QLC+-Import, der dabei **wirklich geändert** wird,
  bekommt die FM-63-Bearbeitet-Marke (`source` bleibt `qlcplus`) und wird danach nie mehr
  von einem LightOS-Profil abgelöst; Speichern ohne Änderung setzt sie nicht.
- **Abgelöste QLC+-Importe** (FM-63) stehen in „Fixture-Profil bearbeiten…“ weiter in
  der Liste — markiert als „QLC+-Import · abgelöst durch LightOS-Profil“, der Tooltip nennt
  das ablösende Profil —, damit Shows, die sie nutzen, korrigierbar bleiben. Wie im
  Fixture-Browser: wählbar, aber nicht verwechselbar.
- **Mitgelieferte** (`builtin`, `lightos`) lassen sich nur **ansehen** (Speichern, Import
  und die Modus-/Kanal-Knöpfe gesperrt) oder **als eigenes Profil kopieren** — die Kopie
  bekommt den Zusatz „(eigen)“ am Modellnamen und `source = "user"`; Herkunft (Lizenz),
  Notizen und 3D-Modell übernimmt sie vom Original. Grund: die nächste
  Bibliotheks-Aktualisierung bzw. `ensure_builtins()` schriebe eine Änderung am Original
  still zurück. Der Editor prüft die Quelle selbst, auch ohne „nur ansehen“ vom Aufrufer.
- **Kopie aus dem Patch:** Wird ein mitgeliefertes Profil per Rechtsklick im Patch
  kopiert, fragt LightOS danach, ob die gepatchten Geräte auf die Kopie umgehängt werden
  sollen — nur Geräte, deren Modus (Name und Kanalzahl) es in der Kopie gibt; die übrigen
  bleiben beim Original, mit Hinweis. Das Umhängen ist **ein** Rückgängig-Schritt.
- **Gepatchte Profile:** Der Editor baut beim Speichern alle Modi neu (neue Modus-IDs).
  Das bricht keinen Patch — gepatchte Geräte verweisen auf `fixture_profile_id` +
  `mode_name` (+ ihre Kanalzahl), nie auf eine Modus-ID. Brechen kann, was man im Editor
  ändert: einen gepatchten Modus umbenennen oder löschen (das Gerät fiele still auf einen
  anderen Modus zurück), seine Kanalzahl ändern (der Patch belegt weiter die alte Zahl
  Adressen) oder Hersteller/Modell umbenennen (die Show trägt die alten Namen). In diesen
  Fällen zeigt der Editor vor dem Speichern die betroffenen Geräte der geladenen Show und
  fragt nach; Standard ist „Nein“. Andere Show-Dateien werden nicht geprüft.
- Modusnamen müssen eindeutig sein — der Editor speichert keine zwei Modi gleichen Namens
  (gepatchte Geräte finden ihren Modus über Profil + Modusname).
- Ein zweites Profil unter demselben Hersteller + Modell legt der Editor nicht an
  (FM-43: mehrdeutige Auflösung beim Laden einer Show); verglichen wird wie bei FM-63
  ohne Groß-/Kleinschreibung (`fixture_db.profil_schluessel`). Gesperrt werden nur
  **neue** Dubletten: behält ein geladenes Profil Hersteller + Modell, darf es speichern,
  auch wenn ein gleichnamiges daneben steht (abgelöster Import neben seinem
  LightOS-Profil). Hersteller werden ohne Groß-/Kleinschreibung und ohne Mehrfach-Leerzeichen
  wiedergefunden (`bibliothek_format.hersteller_ohne_gross_klein`, wie `profil_schluessel`) —
  „eurolite“ landet bei „Eurolite“; dasselbe gilt beim Einspielen der Bibliothek und beim
  Namens-Rückfall beim Laden einer Show.
- Die Geräteauswahl („Gerät hinzufügen“) zeigt zum gewählten Profil eine Zeile
  **Herkunft** (z. B. „LightOS-Bibliothek (aus QLC+, überarbeitet) · ungeprüft“);
  „geprüft ✓“ nur bei `geprueft.ok` der Datei, Einzelheiten im Tooltip.

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
