# Anleitung: Farb-Matrix (RGB/RGBW-Effekte über eine Gerätegruppe)

> Die **Farb-Matrix** legt einen **Farbeffekt** über eine ganze Gerätegruppe — Lauflicht,
> Verlauf, Atmen, Feuer u. v. m. Das **Raster folgt der Gruppe** (jedes Gerät ist eine
> Zelle). Sie schreibt nur **Farbe** (kombinierbar mit einer Dimmer-Matrix als Helligkeits-Ebene).
> Für den konkreten *Blau-Weiß-Chase* siehe die Anleitung **Farbchase** — hier das allgemeine Prinzip.

---

## 1. Anlegen

Programmer → Tab **Matrix** → **+ Neu** → in **Grundeinstellungen**:

- **Stil: RGB** (reine Farbe) oder **RGBW** (mit Weiß-Kanal — z. B. Spider/RGBW-PAR).
- **Spalten:** so viele wie Geräte, **Reihen: 1** (oder ein echtes 2D-Raster für Flächen).
- **Algorithmus** wählen (siehe unten).

Das **Raster folgt der Programmer-Auswahl**: erst die Gruppe wählen (z. B. *Farb-Matrix (10)* =
alle PAR + Spider), dann deckt die Matrix genau diese Geräte ab. Steht „0 Fixtures", die Gruppe in
der Gruppen-Liste **neu anklicken**.

![Farb-Matrix im Editor (Style RGB, Chase)](img/01_matrix_rgb.png)

## 2. Algorithmen (Auswahl)

Im Auswahlfeld (Klappliste) **Algorithmus** stehen u. a.: **Plain** (volle Fläche), **Chase** (Lauflicht),
**Wipe** (Wisch), **Wave** (Welle), **Gradient** (Farbverlauf), **Rainbow** (Regenbogen),
**Fill** (Schritt-für-Schritt-Füllen), **Random** (Zufall), **Color Fade** (Crossfade),
**Strobe**, **Schachbrett**, **Radar**, **Spirale**, **Sine Plasma**, **Windrad**,
**Atmen (Puls)**, **Feuer** und **Regen**. Die meisten Algorithmen nutzen 1–3 Farben (C1/C2/C3)
bzw. eine **Color Sequence**; manche (z. B. **Rainbow**) nutzen **keine** Farbfelder und erzeugen
ihre Farben selbst — dort blendet der Editor die Farbauswahl aus.

> **Hinweis:** „Komet" und „Ripple" sind **keine eigenen Algorithmen mehr** — ein Komet ist
> jetzt ein **Chase** mit Schweif (Regler „Schweif (%)"), ein Ripple ist eine **Wave** mit
> Ursprung *radial*. Alte Shows mit diesen Namen laden weiterhin (Legacy-Migration).

- **„Farbe pro Runde wechseln" (color_cycle):** schaltet von Einzelfarbe auf eine ganze
  **Farbfolge** (Color Sequence) um — dann läuft z. B. ein Chase Blau→Weiß→Grün.
- **Läufer-Anzahl / Schweif (%):** mehr/dichtere Läufer bzw. weicher Übergang hinter dem
  Läufer (0 % = harter Wechsel, 100 % = langer weicher Übergang). Beides nur bei Chase mit
  Bewegung *normal*.

## 3. Style RGBW (Weiß-Kanal)

Mit **Style RGBW** treibt die Matrix zusätzlich den **Weiß-Kanal** (Spider/RGBW-PAR) — sattere,
hellere Mischfarben. Ein eigener Weißanteil ist **nicht** einstellbar: RGBW erzeugt echtes Weiß
automatisch über den W-Kanal.

**Geräte mit eigener Weiß-Leiste und mehreren Dimmern.** Liegen Weiß-Segmente eines solchen
Geräts im Raster (Weiß-Felder aus dem Fixture-Gruppen-Editor), muss LightOS wissen, welcher
Dimmer welches Segment dimmt — das trägt man im Fixture-Editor ein (Spalte „Weiß-Segment“,
siehe `docs/FIXTURE_LIBRARY.md`, Abschnitt „Mehrere Dimmer und Weiß-Segmente“). Fehlt die
Angabe, steht unter der Vorschau ein gelber Hinweis. Was die Matrix dann tut, hängt davon ab,
ob sie die Dimmer selbst fährt („Dimmer mit treiben“; heute ohne eigenes Bedienelement —
**neue Matrizen fahren die Dimmer nicht**, Matrizen aus älteren Shows schon):

- **Matrix fährt die Dimmer** (ältere Shows): ohne Zuordnung werden **alle freien Dimmer des
  Geräts gemeinsam** aufgezogen — frei heißt: keinem anderen Weiß-Segment und keinem Farbteil
  zugeordnet (ein Dimmer direkt neben einem reinen RGB-Abschnitt fährt nie). Die Intensität
  der Matrix wirkt über diese Dimmer. Gibt es keinen freien Dimmer, bleibt das Segment
  hinter seinem Dimmer so hell, wie dieser steht.
- **Matrix fährt keine Dimmer** (neue Matrizen): die Dimmer gehören dir. Die Weiß-Segmente
  leuchten nur, wenn die Dimmer anderweitig offen sind (Programmer, Szene); die Intensität
  der Matrix dimmt dann das Weiß selbst. Die Zuordnung sorgt hier dafür, dass Weiß-Regler und
  Kommandozeile den richtigen Dimmer mitziehen.

## 4. Kombinieren

Farbe (diese Matrix) + Helligkeit (Dimmer-Matrix) + Bewegung (EFX) sind **getrennte Ebenen** über
denselben Geräten — siehe *Dimmer-Matrix* (relative Geschwindigkeit) und *EFX*. So sieht eine
laufende Farb-Matrix aus:

![Farb-Matrix](../tutorial_matrix/gif/farb_matrix.gif)

→ **Schritt-für-Schritt-Beispiel** (Blau-Weiß-Chase mit Color Sequence): [Farbchase](../anleitung_farbchase/ANLEITUNG_FARBCHASE.md).

---

**Kurz:** Matrix-Tab → **+ Neu** → **Style RGB/RGBW** + Algorithmus → Spalten = Geräte → Gruppe
auswählen (Raster folgt) → optional „Farbe pro Runde wechseln" + Color Sequence. Kombinierbar mit
Dimmer-Matrix (Helligkeit) und EFX (Bewegung).
