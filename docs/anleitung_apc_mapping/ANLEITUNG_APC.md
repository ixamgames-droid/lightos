# Anleitung: APC mini auf die Virtuelle Konsole mappen

> Die **Akai APC mini** (Original oder **mk2**) wird als Hardware-Controller für die
> Virtuelle Konsole genutzt: Pads lösen VC-Tasten aus, die Fader steuern VC-Fader. Mit
> **LED-Feedback** spiegeln die Pads den Zustand zurück. Alles ohne Code, direkt in der
> Oberfläche.

---

## 1. Was wird gemappt?

Jedes **VC-Widget** kann an ein APC-Element gebunden werden:
- **VCButton** (Look-Toggle, Farb-Kachel, TAP, Blackout …) → an ein **Pad** (Note) oder eine Track-/Scene-Taste. Geht **beidseitig**: per „MIDI Lernen" (Weg A) **oder** „MIDI Teach" (Weg B).
- **VCSlider** (Master, BPM, Effekt-Tempo …) → an einen **Fader** (**CC**). Fader werden **nur über „MIDI Teach" (Weg B)** gebunden — „MIDI Lernen" (Weg A) armiert ausschließlich Tasten/Pads, **kein** angeklickter Fader.

Die Bindung wird **mit der Show** gespeichert.

## 2. Weg A — schnell per „MIDI Lernen" (nur Tasten/Pads)

> **Wichtig:** „MIDI Lernen" bindet **ausschließlich VCButtons** (Pads/Tasten). Ein angeklickter
> **Fader/VCSlider wird NICHT armiert** — für Fader gibt es **Weg B** (MIDI Teach, bindet **CC**).

1. In der **Virtual Console** die Toolbar **„MIDI Lernen"** aktivieren (wird orange, der Hinweis
   „MIDI-Learn: Klicke einen Button an..." erscheint auf dem Raster).
2. Den gewünschten **VC-Button anklicken** (der Button wird bewaffnet; ein Klick auf einen Fader oder
   ins Leere bricht den Modus ab).
3. Am APC mini die **Taste/das Pad drücken** — die erste eingehende MIDI-Nachricht wird dem Button
   zugewiesen (Pad/Taste = Note).
4. **„MIDI Lernen"** wieder ausschalten.

> Für **Fader/VCSlider** stattdessen **Weg B** nutzen (Rechtsklick → **„🎹 MIDI Teach..."**) — dort wird
> der Fader an einen **CC** gebunden.

## 3. Weg B — MIDI-Teach-Dialog (mit APC-Abbild)

Im **Bearbeiten**-Modus das Widget **rechtsklicken → „🎹 MIDI Teach..."**. Es öffnet sich ein Abbild
der APC mini:

![MIDI-Teach-Dialog mit APC-Abbild](img/01_midi_teach.png)

- Entweder am Gerät die Taste/den Fader **betätigen** (das Element leuchtet im Bild auf),
- **oder** das Element im Bild direkt **anklicken** — das funktioniert **auch ohne angeschlossene APC**.
- **„Bindung entfernen"** löscht eine bestehende Zuordnung, **OK** speichert.

> Steht oben „🔴 Kein MIDI-Eingang gefunden", ist keine APC erkannt — der Dialog bleibt trotzdem per
> Klick benutzbar. Zum Steuern in Echtzeit die APC per USB anschließen (ggf. neu einstecken).

## 4. APC-mini-Belegung (Noten/CC)

| Bereich | Bereich-Werte | Hinweis |
|---|---|---|
| **Pad-Grid 8×8** | Note **0–63** | `note = Reihe×8 + Spalte`, Reihe 0 = unten |
| **Track-Tasten** (unter dem Grid) | Note **64–71** | 8 Tasten links→rechts |
| **Scene-Tasten** (rechte Spalte) | Note **82–89** | 82 = oben |
| **Fader** (8 + Master) | **CC 48–56** | CC56 = Master-Fader |

Der **mk2** hat dasselbe **Eingangs**-Layout (nur die RGB-LED-Ausgabe ist anders — wird automatisch
erkannt).

## 5. LED-Feedback

Toolbar **„APC LEDs"** einschalten → die Pads spiegeln den Zustand zurück:
- Look-/Funktions-Pad **aktiv** = hell, **gedrückt** = weißer Blitz.
- Farb-Kachel-Pad zeigt die **echte Farbe** (mk2: pulst, wenn die Farbe im Programmer aktiv ist).
- **TAP-Pad** blinkt (mk2) im **Beat** mit (weiß), AUTO/MANUAL-Pad zeigt den Modus.

Original-APC: Grün/Rot/Gelb + Blink. mk2: volle RGB-Farben + Ripple-/Beat-Animationen. Der passende
Modus wird am Port-Namen automatisch gewählt.

## 6. Soft-Takeover (Fader-Pickup)

Damit Fader nach einem **Bank-/Seitenwechsel** nicht springen, gibt es **Pickup**: der physische Fader
übernimmt erst, wenn er den aktuellen VC-Wert **einmal durchfährt**. Ein **gelber Pfeil** zeigt, wohin
der Fader bewegt werden muss. In der VC-Toolbar als **„🎚 Pickup"** schaltbar (aktiv: **„🎚 Pickup AN"**).

---

**Kurz:** **Tasten/Pads** → Virtual Console → **MIDI Lernen** an → Button klicken → APC-Pad drücken.
**Fader** → Rechtsklick → **🎹 MIDI Teach...** → Fader bewegen oder Element im Bild anklicken (bindet **CC**).
Danach **APC LEDs** an für Rückmeldung. Bindungen werden mit der Show gespeichert. Ohne APC läuft alles
per Touch/Tastatur weiter.
