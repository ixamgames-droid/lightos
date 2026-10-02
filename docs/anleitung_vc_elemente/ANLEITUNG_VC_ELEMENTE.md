# Referenz: Alle VC-Elemente (Virtual Console)

> **Überblick aller 19 Bau-Elemente** der Virtual Console — was sie sind, wie man sie
> bedient und was man einstellen kann. Plus die **Baukasten-Knöpfe** (komplette Blöcke).
>
> *Die früheren Baukasten-Blöcke Controller-Vorlage, Color-Chase und Chase-Bereich
> gibt es nicht mehr — an ihre Stelle ist das **Live-Edit-Panel** getreten
> (siehe [LIVE_EDIT_FENSTER.md](../LIVE_EDIT_FENSTER.md)).*
>
> Vorlage zum Anschauen: `shows/VC_Elemente_Showcase.lshow` (Generator
> `tools/build_vc_elements_showcase.py`) — legt 14 der Typen einmal beschriftet ab (die 14 aus
> der Tabelle unten). Alle 19 zeigt der Widget-Schaukasten der
> [Widget-Referenz](../anleitung_vc_widgets/README.md).

![Alle VC-Elemente in der Übersicht](img/01_alle_elemente.png)

---

## So legt man ein Element an

Es gibt **zwei Wege**:

### Weg A — über die Toolbar

1. In der VC oben **„Bearbeiten"** anklicken (→ „Bearbeiten ✓").
2. In der Toolbar den gewünschten **Knopf** klicken → das Element erscheint in der
   Canvas-Mitte und kann an seinen Platz gezogen werden.
3. **Doppelklick** auf das Element → **Einstellungen**-Dialog.
4. **Rechtsklick** → Kontextmenü (siehe unten).

> **Neu:** Die Toolbar bietet **16 Typen** als Knopf an — auch die früher nur
> intern verfügbaren **Effekt-Farben, Musik, BPM, Tempo-Bus** sowie **Tempo-Controller** und **Live-Edit**. Passt nicht alles in eine
> Zeile, bricht die Toolbar automatisch in eine zweite Zeile um.

![Toolbar mit allen Hinzufügen-Knöpfen](img/02_toolbar_alle_knoepfe.png)

### Weg B — Effekt aus der Bibliothek auf die Canvas ziehen

Du kannst auch einen **Effekt aus der Bibliothek direkt auf die Canvas ziehen** — LightOS
baut dir dann das passende Bedien-Element praktisch von selbst.

- **Drop auf eine freie Stelle** → es öffnet sich die Karte **„Effekt einrichten"**
  (Fenster). Sie zeigt den Hinweis *„… direkt verknüpfen — es wird kein neuer Effekt erzeugt. Welche Bedienelemente brauchst du?"* und **je Aspekt eine
  ankreuzbare Zeile** („An/Aus (Toggle)", „Tempo (Geschwindigkeit)", „Helligkeit",
  „Farben ändern…", „Bewegung (XY-Feld)…", „Tempo-Bus zuweisen…",
  „Tempo-Multiplikator (×½ ×2)…" …). „An/Aus (Toggle)" ist vorangekreuzt. Pro Zeile gibt es — wo mehrere Bedien-Typen
  passen — den Knopf **„Widget: … ▸ ändern"**, der die **grafische Widget-Galerie** öffnet
  (Element per Bild wählen statt aus einer Liste). Ein Klick auf **„Erstellen"** legt für jedes Häkchen ein fertig
  verdrahtetes Widget an — alles in **einem** Undo-Schritt. (Selten gebrauchte Parameter
  liegen im **zugeklappten** Bereich **„Mehr Parameter (N)"**; in der Galerie wählst du eine
  Kachel und bestätigst mit **OK** oder Doppelklick.)

  ![Drop-Karte „Effekt einrichten"](img/04_drop_karte.png)

  ![Grafische Widget-Galerie](img/05_widget_galerie.png)

- **Drop auf einen schon belegten Regler** → es erscheint die **Konflikt-Karte**
  „Regler ist schon belegt". Sie sagt dir, was der Regler bereits steuert, und bietet drei
  klare Wege: **„Ersetzen"** (Regler steuert nur noch den neuen Effekt), **„Dazu koppeln"**
  (beide Effekte am selben Regler, eine Gruppe / ein Tempo) oder **„Neues Widget daneben"**
  (lässt den Regler in Ruhe, legt ein eigenes Element an). Abbrechen lässt alles unverändert.

  ![Konflikt-Karte „Regler ist schon belegt"](img/06_konflikt_karte.png)

### Rechtsklick-Menü (Kontextmenü)

Rechtsklick auf ein Element (im Bearbeiten-Modus) öffnet:

- **Einstellungen…** — derselbe Dialog wie beim Doppelklick.
- **↔ Widget ändern…** — tauscht den Bedien-Typ bindungserhaltend über die grafische
  **Widget-Galerie** (nur wenn für den Aspekt mehrere Typen passen, z. B. Tempo →
  Speed-Rad *oder* Fader).
- **⚡ Live-Parameter…** — nur bei effektgebundenen Elementen mit Live-Parametern.
- **🎹 MIDI Teach…** / **⌨ Taste zuweisen…** — MIDI- bzw. Tastatur-Bindung lernen
  (je nach Element-Typ).
- **Bank** (Untermenü) — Element einer Bank zuordnen: **„Alle Banks"** oder **Bank 1…10**.
- **Löschen** / **Vordergrund-Farbe** / **Hintergrund-Farbe**.

---

## Die 14 Elemente im Detail

| Element | Was es ist | Bedienung (Betrieb) | Wichtigste Einstellungen (Doppelklick) |
|---|---|---|---|
| **Button** (VCButton) | Steuertaste | Klick löst die Aktion aus | **Aktion** („Funktion an/aus", „Funktion (nur gehalten)", „Effekt-Aktion (Live)", „Snapshot abrufen", „Gruppe auswählen", „Tap-Tempo", „Musik: …" …), **Ziele** (Funktionen/Effekte, Liste „Schaltet mit"), Beschriftung, Pad-Stil, Exklusiv/Solo, MIDI |
| **Fader** (VCSlider) | Schieberegler | Hoch/runter ziehen (0–255) | **Modus** („DMX-Kanal (Level)", „Submaster", „Grand Master", „Programmer-Attribut", „Tempo (BPM)", „Tempo-Bus (BPM)", „Speed (alle Effekte)", „Effekt-Helligkeit", „Effekt-Tempo", „Effekt-Parameter", „Gruppen-Dimmer", „Feature-Dimmer (Gruppe)", „Playback (Executor)"), Tempo-Bus, Wert min/max, Invertieren, **Steuert** (Effekte), MIDI-CC |
| **Farbe** (VCColor) | Farb-Kachel | Klick setzt die Farbe | RGB/W/A/UV, mit Helligkeit, **Ziel** (Programmer/Alle/Effekt-Farbe …), Effekt-ID, MIDI |
| **XY Pad** (VCXYPad) | 2D-Feld für Pan/Tilt | Im Feld ziehen = Pan/Tilt (Position) bzw. Bereich/Bahn aufziehen | **Modus** (Position / Feld / Pfad), Pan/Tilt-Attribut, 16-bit, Fixtures, Effekt-ID (Feld/Pfad), MIDI-CC Pan/Tilt |
| **SpeedDial** (VCSpeedDial) | Tempo-Drehrad | Drehen = BPM; Tap/Sync/Faktor-Tasten | **Ziel** (Executor / Funktion·Effekt / Tempo-Bus / **Effekt ×½·×2 Multiplier** / Speed-Knoten), Rolle **Master/Sub**, Tempo-Bus, Parent-Bus, Faktor-Set |
| **Encoder** (VCEncoder) | Relativ-Drehgeber | Drehen = Effekt-Parameter ±  | **Param-Key** (size/hold/speed …), Effekt-ID, Schrittweite, MIDI-Modus |
| **Cueliste** (VCCueList) | Cue-Transport | GO / BACK / STOP schaltet Cues | **Executor-Slot** (welche Cueliste) |
| **Musik** (VCSongInfo) | Musik-Info-Anzeige | nur Anzeige (aktuelles + nächstes Lied) | Schriftgröße |
| **Chase-Liste** (VCColorList) | Live-Farb-Sequenz | Klick = Farbe an/aus, Rechtsklick = entfernen | **Effekt-ID** (zeigt dessen Farb-Sequenz) |
| **Effekt-Farben** (VCEffectColors) | Farb-Sequenz-Editor | Feld klicken = Farbwähler, Rechtsklick = aktiv | **Effekt-ID**, Edit-Slot |
| **BPM** (VCBpmDisplay) | Live-Tempo-Anzeige | nur Anzeige (BPM + Quelle) | **Quelle** („Global (Leader)" oder Bus A–D), Schriftgröße |
| **Tempo-Bus** (VCBusSelector) | Bus-Auswahl (A/B/C/D) | Chip klicken = Bus scharf schalten (ohne Effekt) bzw. die gebundenen Effekte auf diesen Bus legen | **Buses**, **Effekt-IDs** (leer = global) |
| **Label** (VCLabel) | Beschriftung/Titel | nur Anzeige | Text, Schriftgröße |
| **Frame** (VCFrame) | Rahmen/Gruppe | nimmt Kind-Widgets auf, optional Tabs | Seiten-Anzahl, Header anzeigen, Solo |

> **Hinweis zur Bindung:** Ungebunden folgen **Chase-Liste** und **Effekt-Farben** dem gerade
> **aktiven** Effekt; nur wenn keiner aktiv ist, zeigen sie einen Platzhalter. Für einen festen
> Effekt im Dialog die Effekt-ID setzen.

---

## Baukasten-Knöpfe (komplette Blöcke)

> ⚠ **Stand 2026‑07:** Diese drei grünen Baukasten‑Knöpfe wurden aus der VC **entfernt** (weder in der
> Werkzeugleiste noch im Rechtsklick‑Menü „Hinzufügen"). Einzel‑Widgets legst du über die Werkzeugleiste
> bzw. Rechtsklick auf die leere Canvas → „Hinzufügen" an; einen kompletten Effekt‑Aufbau baust du, indem du einen Effekt aus der Bibliothek
> aufs Raster ziehst (Karte „Effekt einrichten") — siehe [ANLEITUNG_VC.md](../anleitung_vc/ANLEITUNG_VC.md).
> Eine **Controller‑Vorlage** lässt sich derzeit nicht in die VC einfügen; der Controller‑Browser
> (E/A → MIDI → „Controller-Profile…") zeigt nur Belegung und Hinweise. Die folgende Beschreibung ist
> historisch.

Drei Knöpfe setzten **nicht** nur ein Einzel-Widget, sondern einen **ganzen Block** inkl.
eigener Effekt-Funktion:

- **⌗ Controller** *(entfernt 2026-07)* — legte ein beschriftetes Pad-/Fader-Raster passend zu einem
  MIDI-Controller (APC mini/mk2 …) an. Pads danach per Rechtsklick belegen.
- **🎨 Color-Chase** *(entfernt 2026-07)* — legte eine **COLORFADE-Funktion + kompletten
  Chase-Baukasten** (Palette, Farb-Liste, Speed/Hold-Fader, Aktions-Tasten) an, alles
  aneinander gebunden. Heute: **Live-Edit-Panel**.
- **🟦 Chase-Bereich** *(entfernt 2026-07)* — wie der Color-Chase, aber man **zog** zuerst
  einen Bereich auf der Canvas auf; der Block wurde hineingelegt. Heute: **Live-Edit-Panel**.

---

## Stand / Nutzbarkeit (Kurz)

- **16 Typen** sind über die Toolbar anlegbar; **Stepper**, **Effekt-Box** (EffectEditor) und
  **Effekt-Vorschau** (EffectDisplay) nur per Rechtsklick auf die leere Canvas → „Hinzufügen"
  (bzw. per Drop/Live-Parameter). Der frühere „Chase Builder"/VCChaseBuilder wurde 2026-07
  komplett entfernt (PR #116).
- **Sofort nutzbar ohne Bindung:** Button, Fader, Farbe, XY Pad, SpeedDial, Encoder, Musik,
  BPM, Tempo-Bus, Label, Frame, Cueliste (mit Executor-Slot).
- **Erst mit Effekt-Bindung sinnvoll:** Chase-Liste, Effekt-Farben — am
  bequemsten über das **Live-Edit-Panel** (Effekt hineinziehen, Ziele ankreuzen);
  der frühere **🎨 Color-Chase**-Baukasten wurde 2026-07 entfernt.
