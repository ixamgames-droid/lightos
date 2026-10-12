# Geräte klonen — was eine Lampe kann, auf andere übertragen

> **Worum geht's:** Ein neues oder anderes Gerät soll überall das tun, was ein
> vorhandenes schon tut — in Gruppen, Effekten, Snaps, Szenen, Cues und Paletten —
> ohne dass du jede Stelle einzeln anfasst. **Klonen** zeigt dir vorher, was sich wo
> ändert, und schreibt erst, wenn du **Anwenden** drückst.

> **Stand:** erste Fassung (ENG-36, Bauschritte 1 und 2). Was noch fehlt, steht unter
> [Was Klonen noch nicht tut](#8-was-klonen-noch-nicht-tut). Diese Anleitung hat noch
> keine Bilder — die Liste der aufzunehmenden Bilder steht [am Ende](#bilder-die-noch-fehlen).

---

## 1. Wozu

Beispiel: Vier PARs bilden den Hintergrund. Eine fünfte Lampe kommt dazu. Sie soll in
dieselben Gruppen, in dasselbe Lauflicht und in jeden Snap, in dem Lampe 1 steckt.
Du klonst Lampe 1 auf Lampe 5 — fertig.

Das geht auch zwischen **verschiedenen Gerätetypen**: ein RGB-PAR auf einen RGBW-PAR,
einen CMY-Scheinwerfer oder ein Gerät mit Farbrad. Dimmer und Farbe werden dabei
übersetzt; was das Ziel nicht kann, fällt weg und steht in der Vorschau.

## 2. Vorbereitung: das Ziel patchen

Klonen patcht nichts und stellt nichts auf die Bühne. Das Zielgerät muss schon im
Reiter **Patch** stehen (**+ Gerät hinzufügen** oder **Mit Offset kopieren…**).

## 3. Schritt für Schritt

1. Im Reiter **Patch** die Quelle markieren — ein Gerät oder mehrere.
2. Rechtsklick → **Klonen auf …** (bei mehreren: „*n* Geräte klonen auf …") oder der
   Knopf **Klonen…** in der Leiste über der Tabelle.
3. Im Fenster **Klonen auf …** die Ziele wählen (mehrere mit Strg oder Umschalt) →
   **Weiter**.
   - **Eine** Quelle auf beliebig viele Ziele: alle bekommen dasselbe.
   - **Gleich viele** Quellen wie Ziele: paarweise in Reihenfolge der Nummern
     (1 → 11, 2 → 12 …). Das Fenster zeigt die Paare an.
   - Sonst gibt es eine Meldung — es wird nicht geraten.
4. Im Dialog **Klonen**:
   - **Was** — Häkchen: Gruppen · Matrix & Bewegungs-Effekte · Snaps & Szenen · Cues ·
     Paletten · Tasten der Konsole · Grundwerte.
   - **Wie** — **Hinzufügen** oder **Ersetzen**. Hier ist nichts vorgewählt; solange du
     nicht gewählt hast, bleibt **Anwenden** grau und die Vorschau leer.
   - **Position in Gruppe, Raster und Fächer** — **ans Ende** (Vorgabe) oder
     **neben die Quelle**.
5. Die **Vorschau** rechts lesen (siehe unten), dann **Anwenden**.

Unten in der Statuszeile steht danach, wie viele Stellen geklont wurden.

## 4. Hinzufügen oder Ersetzen

Der Unterschied zeigt sich nur dort, wo das Ziel **schon einen Wert hat**.

Snap „Rot": Lampe 1 hat Rot 255 und Grün 0. Lampe 5 steht schon mit Rot 7 und Blau 99 drin.

| | Rot | Grün | Blau |
|---|---|---|---|
| **Hinzufügen** | bleibt 7 | wird 0 (kam dazu) | bleibt 99 |
| **Ersetzen** | wird 255 | wird 0 | bleibt 99 |

**Ersetzen löscht nichts.** Blau bleibt in beiden Fällen stehen, weil die Quelle an
dieser Stelle kein Blau hat. Und ein Snap, in dem die Quelle gar nicht vorkommt, wird
nie angefasst.

Bei Mitgliedschaften (Gruppen, Raster, Gerätelisten) gibt es keinen Unterschied: ist
das Ziel schon dabei, bleibt es, wo es ist.

## 5. Die Vorschau lesen

Über der Liste stehen drei Zähler, jede Zeile trägt eines der drei Kennzeichen:

- **unverändert übernommen** (grün, ✓) — der Wert oder die Mitgliedschaft geht 1:1 ans Ziel.
- **übersetzt** (gelb, ≈) — der Wert wurde für das Ziel umgerechnet; die Zeile nennt
  die Farbe und die neuen Werte.
- **fällt weg** (rot, ✗) — das Ziel kann es nicht, oder es kommt erst in einem späteren
  Schritt. Der Grund steht dabei.

Grau (·) und mit eigenem Zähler **bleibt, wie es ist**: Stellen, an denen nichts
geschieht, weil das Ziel dort schon steht.

Jede Zeile nennt den Ort beim Namen, zum Beispiel `Snap „Rot“ · 1 → 5`. Eine Cueliste
oder Sequenz wird zu einer Zeile je Kennzeichen zusammengefasst („· 12 Stellen").
Unter der Liste stehen Hinweise in Gelb, etwa wenn Quelle und Ziel verschiedene
Gerätetypen sind.

## 6. Verschiedene Gerätetypen: was übersetzt wird, was wegfällt

„Gleicher Typ" heißt: dasselbe Profil im selben Modus. Dann geht alles 1:1.
Sonst gilt für **gespeicherte Werte** (Snaps, Snapshots, Szenen, Cues, Sequenzen,
Paletten, Grundwerte):

| Baustein | Was geschieht |
|---|---|
| Dimmer | Dimmer → Dimmer, Wert 1:1. Ziel ohne Dimmer: fällt weg. |
| RGB ↔ RGBW | über die sichtbare Farbe. Hat das Ziel einen Weiß-Kanal, wandert der Weißanteil dorthin (wie beim Farbwähler): Weiß 255/255/255 wird Weiß 255, Rot/Grün/Blau 0. |
| RGB/RGBW ↔ CMY | über die sichtbare Farbe: Cyan = 255 − Rot und so weiter. |
| Amber, UV | nur, wenn beide Geräte den Kanal haben; sonst fällt er weg. |
| Farbe → Farbrad | der nächstliegende **benannte** Platz im Rad, in der Vorschau als „ungefähr" markiert. Passt kein Platz: fällt weg. |
| Farbrad → Farbmischung | die Farbe des Platzes laut seinem Namen. Platz ohne Farbwort oder Rotation: fällt weg. |
| Farbe → Gerät nur mit Weiß oder ohne Farbe | fällt weg. |
| Pan/Tilt, Zoom, Fokus, Gobo, Prisma, Shutter/Strobe, Makros | fallen in dieser Fassung weg — „kommt in einem späteren Schritt". |
| Werte einzelner Köpfe (Mehrkopf-Geräte) | fallen zwischen verschiedenen Typen weg. Werte ohne Kopf-Angabe gelten am Ziel für alle Köpfe. |

**Farbe und Dimmer bleiben getrennt.** Ein geklonter Farb-Snap bringt keinen
Dimmerwert mit. Hat die Quelle keinen Dimmer, bekommt das Ziel keinen — das steht als
Hinweis in der Vorschau, den Dimmer des Ziels stellst du selbst ein.

**Mitgliedschaften** brauchen keine Übersetzung, weil die Effekte ihre Werte je Gerät
passend ausrechnen. Sie gehen auch zwischen verschiedenen Typen:

- **Fixture-Gruppen:** das Ziel kommt ans Ende (hinter die letzte belegte Zelle; ist das
  Raster voll, bekommt es eine Zeile dazu) oder neben die Quelle. In einer einzeiligen
  Gruppe rücken die Geräte dahinter um einen Platz; in einem mehrzeiligen Raster geht
  „neben die Quelle" nur, wenn die Zelle rechts frei ist — sonst kommt das Ziel ans Ende
  und die Vorschau sagt es. Die automatische Köpfe-Gruppe der Quelle bleibt unberührt.
- **Matrix-Raster:** ebenso; eine einzeilige Matrix wird um eine Zelle länger.
- **Bewegungs-Effekte:** das Ziel reiht sich in den Fächer ein und übernimmt den
  Versatz der Quelle; der Fächer verteilt sich neu (die Vorschau nennt „4 → 5 Ziele").
  Hat das Ziel kein Pan/Tilt, fällt es weg.
- **Effekte mit Geräteliste**, **Blackout-Tasten mit Ziel** und **XY-Pads** der Konsole:
  das Ziel kommt in die Liste.
- Stehen von einem Mehrkopf-Gerät nur einzelne **Köpfe** in Gruppe, Raster oder Fächer
  und das Ziel ist ein anderer Typ, kommt das Ziel als **ein** ganzes Gerät hinein
  (Kennzeichen „übersetzt"). Zellen für Weiß-Segmente fallen dann weg.

## 7. Rückgängig und Sicherung

- **Vor jedem Klonen** legt LightOS eine Sicherung der Show an, Anlass
  **„vor dem Klonen"**. Du findest sie unter **Datei → Ältere Version öffnen…**.
  Lässt sich keine Sicherung anlegen, fragt der Dialog nach, bevor er etwas schreibt.
- **Bearbeiten → Rückgängig** (Strg+Z) nimmt das ganze Klonen in **einem** Schritt
  zurück. Hast du inzwischen an anderen Geräten weitergearbeitet, bleibt das stehen:
  es gehen nur die Einträge des Ziels wieder heraus.
- Rückgängig gilt bis zum nächsten Laden einer Show und für die letzten 100 Schritte.

## 8. Was Klonen noch nicht tut

- **Bewegung, Optik, Gobo** zwischen verschiedenen Typen (Pan/Tilt über den Winkel,
  Shutter/Strobe nach Bereich, Gobo und Prisma nach Namen) — folgt in späteren Schritten.
- **Mehrkopf ↔ Einkopf** bei gespeicherten Werten: Kopf-Werte fallen weg.
- **Kommandozeile** (`clone 1 at 5 thru 8`) und **Menü Bearbeiten** — der Einstieg ist
  vorerst nur der Reiter **Patch**.
- **Nicht geklont werden:** Adresse und Patch-Einstellungen, 2D-/3D-Position, der
  aktuelle Programmer-Inhalt, Kanal-Gruppen und Submaster (sie kennen nur DMX-Kanäle,
  kein Gerät), in Snapshots die Liste der ignorierten Kanäle, Laser-Muster.
- Tasten, die einen Snap oder Effekt auslösen, werden nicht verändert — sie wirken von
  selbst mit, weil das Ziel jetzt im Snap oder Effekt steckt.
- Gleicher Wert heißt nicht gleicher Punkt auf der Bühne: hängt das Ziel woanders,
  zeigt es woanders hin. Positionen musst du nachziehen.
- Ein Farbrad trifft Farben nur ungefähr.

---

## Bilder, die noch fehlen

Diese Anleitung ist bisher nur Text. Aufzunehmen sind:

1. Reiter **Patch** mit markierter Quelle, Knopf **Klonen…** und offenem Rechtsklick-Menü
   mit **Klonen auf …**.
2. Fenster **Klonen auf …** mit zwei gewählten Zielen und der Zeile der Paare.
3. Dialog **Klonen** direkt nach dem Öffnen: nichts unter **Wie** gewählt, **Anwenden** grau.
4. Dialog **Klonen**, gleicher Typ, **Hinzufügen**, Vorschau gefüllt.
5. Dialog **Klonen**, verschiedene Typen (RGB-PAR → RGBW-PAR und → Gerät mit Farbrad),
   mit „übersetzt" und „fällt weg".
6. Vorher/Nachher einer Fixture-Gruppe und eines Matrix-Rasters (ans Ende / neben die Quelle).
7. **Datei → Ältere Version öffnen…** mit dem Eintrag „vor dem Klonen".
8. Menü **Bearbeiten** mit dem Eintrag „Rückgängig: Klonen 1 → 5".
