# Wer gewinnt? Prioritäten für Effekte einstellen und prüfen

Laufen zwei Dinge gleichzeitig auf derselben Lampe, muss LightOS entscheiden, wessen Wert
am Ende gesendet wird. Diese Anleitung zeigt die ganze Reihenfolge von unten nach oben und
wie du die Reihenfolge deiner **Effekte** selbst festlegst: über fünf benannte **Stufen**.

Du brauchst dafür keine besondere Show — jede Show mit ein paar Effekten genügt.

## 1. Die Reihenfolge in einem Bild

Jedes Bild (44-mal je Sekunde) wird neu aufgebaut, Schicht für Schicht. Was weiter unten in
der Tabelle steht, kommt später und setzt sich durch.

| # | Schicht | Regel in einem Satz |
|---|---|---|
| 1 | Grundwerte | Jedes Bild beginnt mit den Ruhewerten der Geräte — nichts „bleibt hängen“. |
| 2 | **Effekte und Funktionen** (Szene, Chaser, Sequenz, Bewegung, Matrix …) | Schreiben zwei denselben Kanal, gewinnt die höhere **Stufe**; bei gleicher Stufe gewinnt, wer **zuletzt gestartet** wurde. Es gibt hier kein „höchster Wert gewinnt“ — auch nicht beim Dimmer. |
| 3 | Cue-Listen (Wiedergabe) | Liegen über allen Effekten und ersetzen deren Werte. |
| 4 | Programmer — dazu gehören **alle Snap-Tasten** der Virtual Console | Liegt über Effekten und Cue-Listen, mit zwei Ausnahmen: Einen Kanal für Farbe, Bewegung oder Gobo, den ein laufender Effekt gerade treibt, behält der Effekt. Und einen Dimmer, den ein laufender Effekt schreibt, behält ebenfalls der Effekt. |
| 5 | Automatische Helligkeit | Leuchtet eine Farbe und treibt niemand den Dimmer, wird er von selbst geöffnet (abschaltbar über **Programmer → Farbe macht automatisch hell**). |
| 6 | „Alles Weiß“ | Überschreibt alles darunter, auch laufende Farb-Effekte. |
| 7 | Gruppen-Fader, Geräte-Dimmer, Submaster | Multiplizieren die Helligkeit, ersetzen nichts. |
| 8 | Eingemischtes DMX von außen | Je Universum einstellbar: höchster Wert gewinnt oder ersetzt. |
| 9 | Simple Desk mit „Manueller Override“ | Nur bei gesetztem Haken; dann gewinnen die dort gezogenen Kanäle. |
| 10 | Laser-NOT-AUS, Grand Master, Blackout | Wirken ganz am Ende und behalten immer das letzte Wort. |

**Die Stufen ordnen nur Schicht 2.** Snap-Tasten, Cue-Listen, Fader und Master behalten
ihren festen Platz.

## 2. Die fünf Stufen

| Stufe (stärkste oben) | Gedacht für |
|---|---|
| **Notfall** | Was immer durchkommen muss, solange es läuft. |
| **Strobe & Blinder** | Kurze, laute Effekte über allem anderen. |
| **Akzente** | Effekte, die sich über das laufende Programm legen. |
| **Effekte** | Die Vorgabe. Alles aus älteren Shows steht hier. |
| **Grundlicht** | Ruhiges Licht, das jeder andere Effekt überdecken darf. |

Ein Effekt hat genau **eine** Stufe. Innerhalb einer Stufe gibt es keine Reihenfolge: dort
gewinnt, wer zuletzt gestartet wurde.

**Alte Shows** öffnen sich unverändert — alles steht in „Effekte“. Hattest du im Matrix- oder
Bewegungs-Editor eine eigene Zahl eingetragen (das Feld hieß früher „Layer-Priorität“), bleibt
sie erhalten und wird als **eigene Zahl (n)** angezeigt, bis du bewusst eine Stufe wählst.
Eine höhere Zahl gewinnt weiterhin; die Stufen entsprechen den Zahlen −20, 0, 20, 40 und 60.
Auch eine **Kanal-Kopplung** steht als „eigene Zahl (10)“ in der Liste: sie liest die Bewegung
der Effekte darunter und rechnet deshalb absichtlich direkt nach der Stufe „Effekte“.

## 3. Stufe vergeben — in der Ansicht „Prioritäten“

1. Öffne die Sektion **Programmer** und dort den Reiter **Prioritäten**.
2. Ganz oben steht ausgegraut **Snaps / Programmer — liegt immer darüber**. Die Zeile ist
   fest; sie erinnert daran, dass Snap-Tasten keine Effekte sind.
3. Darunter die fünf Stufen, die stärkste zuerst. Jeder Effekt der Show steht in seiner
   Stufe mit **Art** (Szene, Chaser, Matrix …) und **Fasst an**: Dimmer, Farbe, Bewegung,
   Gobo oder Sonstiges. Steht dort **unbekannt**, lässt sich das nicht aus der Show ablesen
   (zum Beispiel bei einem Skript oder einer Szene mit Geräten, die nicht mehr gepatcht sind).
4. Ein laufender Effekt ist fett und trägt **● läuft**.
5. Stufe ändern — vier Wege, alle auch für mehrere Zeilen (Strg oder Umschalt beim Klicken):
   - die Zeile in eine andere Stufe **ziehen**,
   - **▲ Stufe höher** / **▼ Stufe tiefer**,
   - im Feld **Auswahl in Stufe** die Stufe wählen,
   - Rechtsklick → **In Stufe „…“**.
6. Jede Änderung ist **ein** Schritt für **Bearbeiten → Rückgängig**, auch wenn sie mehrere
   Effekte betrifft.

Nicht in der Liste stehen Audio-Funktionen (sie schreiben kein DMX) und ungespeicherte
Entwürfe aus dem Bewegungs-Editor.

## 4. Stufe vergeben — im Editor

Jeder Editor hat das feste Feld **Stufe**: Szene, Chaser, Sequenz, Sammlung, Skript,
Ebenen-Effekt, Carousel, Matrix und Bewegung (EFX). Im Matrix- und im Bewegungs-Editor steht
es in der Gruppe *Tempo & Blende* bzw. *Tempo & Richtung*, dort wo früher das Zahlenfeld war.

Die Auswahl im Editor und die Ansicht **Prioritäten** zeigen dasselbe — ändert man es an der
einen Stelle, zieht die andere nach.

## 5. Farbe und Dimmer konkurrieren nicht

Eine Farb-Matrix und ein Dimmer-Lauflicht auf denselben Lampen nehmen sich nichts weg: sie
schreiben getrennte Kanäle. Die Stufe spielt erst eine Rolle, wenn zwei Effekte **denselben**
Baustein derselben Lampe treiben — zwei Dimmer-Effekte, zwei Farb-Effekte, zwei Bewegungen.
Die Spalte **Fasst an** zeigt dir das auf einen Blick.

## 6. Was die Stufen nicht regeln

- **Sammlung, Chaser, Show:** Was *in* einer Sammlung, einem Chaser oder einer Show läuft,
  läuft auf **deren** Stufe. Die eigene Stufe eines Mitglieds zählt nur, wenn du es einzeln
  startest. Der Hinweis steht in der Ansicht als Tooltip an der Zeile („Läuft auch in: …“).
- **Snap-Tasten:** liegen immer über den Effekten (Schicht 4), unabhängig von jeder Stufe.
- **Kein „Untergrund“:** Ein Dimmer-Lauflicht schreibt für *jede* seiner Lampen einen Wert,
  auch 0 für die gerade dunklen. Liegt es über einem anderen Dimmer-Effekt, verdeckt es ihn
  auf diesen Lampen vollständig — eine höhere Stufe macht daraus keinen Läufer *über* einem
  Untergrund.
- **Master und Blackout:** Grand Master, Gruppen-Fader, Blackout und Laser-NOT-AUS wirken
  nach allen Effekten, egal auf welcher Stufe.

## Bilder, die noch aufzunehmen sind

Diese Anleitung ist bewusst noch ohne Bilder; aufzunehmen sind:

1. Schichten-Schaubild von den Grundwerten bis zum NOT-AUS.
2. Ansicht **Prioritäten** mit einer laufenden Party-Show.
3. Ziehen eines Effekts in „Strobe & Blinder“, vorher und nachher.
4. Feld **Stufe** im Matrix-Editor.
5. Feld **Stufe** im Szenen-Editor.
6. Eine alte Show mit „eigene Zahl (n)“ in der Liste.
