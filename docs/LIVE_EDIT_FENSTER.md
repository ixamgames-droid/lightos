# Live-Edit-Panel

> Ein größenveränderliches Bedien-Panel **auf der Fläche der virtuellen Konsole**, in das du Effekte hineinziehst, um ihre Parameter live zu beobachten und zu verändern — ohne die Show dauerhaft zu verändern.

## Wozu & was es steuert

Das Live-Edit-Panel fügst du wie jedes andere VC-Element über den Schnell-Button **„Live-Edit"** in der virtuellen Konsole hinzu. Es ist **ein Widget auf der Canvas** (kein separates Fenster): Du platzierst und skalierst es im Bearbeiten-Modus wie einen Fader oder Button, und es bleibt dort verankert. Du kannst mehrere Panels anlegen. Es ersetzt die früheren Baukasten-Bausteine **Controller-Vorlage**, **Color-Chase** und **Chase-Bereich** (siehe [`docs/anleitung_vc_widgets/21_baukasten.md`](anleitung_vc_widgets/21_baukasten.md)).

**Wichtig — was gespeichert wird und was nicht:** Das Panel selbst (Größe, Position) und **welche Effekte** du ihm zugewiesen hast, werden mit der Show gespeichert. Die **konkreten Parameter-Änderungen** dagegen sind **flüchtig**: Sie wirken sofort auf den laufenden Effekt, werden aber **nicht** in die Show geschrieben. Speicherst du die Show, sichert LightOS die ursprünglichen Preset-Werte der Effekte — nicht deine Live-Anpassungen. Das Panel ist damit ein Werkzeug zum **Ausprobieren und Feintunen während der Show**, nicht zum dauerhaften Bearbeiten.

## Effekte zuweisen

- Per **Drag & Drop** ziehst du einen oder mehrere Effekte (Matrix, EFX/Bewegung, Chaser) aus dem Funktions-Baum in das Panel.
- Oben im Panel wählt ein **Dropdown** den aktuell angezeigten Effekt; daneben blättern **„−" / „+"** durch alle zugewiesenen Effekte.
- Welche Effekte einem Panel zugewiesen sind, bleibt beim Speichern/Laden der Show erhalten — nur die daran vorgenommenen Live-Werte fallen beim Neuladen auf das Preset zurück.

## Bearbeiten- vs. Betriebs-Modus

- Im **Bearbeiten-Modus** zeigt das Panel die **Häkchen-Auswahl** (welche Regler du steuern willst). Verschieben/Skalieren des Panels läuft über die **Kopfleiste** und den **Rand**.
- Im **laufenden Betrieb** zeigt das Panel **nur die angehakten Regler** — Dropdown, Regler und Tempo-Bereich sind live bedienbar.

## Vorschau je Effekt-Typ

Oben im Panel zeigt eine Live-Vorschau den gewählten Effekt passend zu seinem Typ:

- **Matrix** — ein **Pixel-Raster** in der echten Geräte-Geometrie.
- **EFX** — der **Bewegungs-Pfad** mit einem darauf laufenden Punkt.
- **Chaser** — eine **Schritt-Leiste** mit dem aktuell aktiven Schritt.

Die Vorschau ist reine Anzeige und verändert den laufenden Effekt nicht. Sie **animiert immer** — auch wenn der Effekt (noch) nicht gestartet ist, dreht die Matrix-Vorschau leise weiter, damit du das Muster schon vor dem Start beurteilen kannst. Läuft der Effekt bereits, zeigt die Vorschau ganz normal seinen echten, laufenden Zustand.

## Farben und Dimmer-Stufen wählen

Bei einer Matrix mit Farbwechsel (RGB/RGBW) bekommst du im Bearbeiten-Modus eine Häkchen-Zeile **„Farben"**: aktivierst du sie, erscheint ein Farbfeld, in dem du die Farben der Wechsel-Sequenz **auswählst, änderst oder einzeln an-/abschaltest** (z. B. nur Rot und Blau aktiv lassen) — Klick auf ein Farbfeld öffnet die Farbauswahl, „Bearbeiten…" öffnet den vollen Editor mit Hinzufügen/Entfernen/Verschieben.

Bei einer **Dimmer**-Matrix mit Wechsel-Algorithmus („Farbe pro Runde wechseln"-Pendant für Helligkeit) erscheint analog eine Zeile **„Dimmer-Stufen"** mit einem Stufen-Feld (z. B. 100 %, 50 %, …), das du genauso an-/abwählen und bearbeiten kannst.

## Parameter-Editor — Bearbeiten vs. Bedienen

Welche Regler ein Effekt zeigt, wählst du im **Bearbeiten-Modus der virtuellen Konsole** aus — pro Effekt einzeln:

- **Konsole im Bearbeiten-Modus** → das Panel zeigt die **Häkchen-Auswahl** aller live-steuerbaren Parameter. Du hakst an, was du steuern willst. Diese Auswahl wird mit der Show gespeichert.
- **Bearbeiten-Modus aus (Betrieb)** → das Panel zeigt **nur noch die angehakten Regler**, aufgeräumt, ohne die Häkchen-Liste.

Brauchst du später einen Regler mehr, gehst du kurz zurück in den Bearbeiten-Modus, hakst ihn an und wieder raus.

Die Regler sind **visuell** und passen zum Parameter-Typ:

- **Helligkeit, Ein-/Ausblenden, Schweif** → **Slider**
- **Läuferzahl, Läuferbreite** → **−/+ ‑Stepper**
- **Richtung** → **Pfeil-Buttons** (`→ vorwärts`, `← rückwärts`, `↔ Ping-Pong`, `Mitte↔außen`)
- **Bewegung / andere Auswahl** → **Segment-Buttons** (bei vielen Optionen ein Dropdown)
- **An/Aus-Parameter** → **Schalter**
- **Farben / Dimmer-Stufen** → das Sequenz-Feld (siehe oben)

Bewusst **nicht** steuerbar (weil strukturell, nicht live veränderbar): **Algorithmus**, **Stil**, **Spalten/Reihen**.

## Vorschau und Tempo an-/abwählen

Ganz oben im Bearbeiten-Modus zeigt eine muted Zeile **„Anzeige:"** zwei zusätzliche Häkchen — **„Vorschau"** und **„Tempo-Kontrolle"** — mit denen du **pro Effekt** festlegst, ob die Live-Vorschau bzw. der Tempo-Bereich im Betriebs-Modus überhaupt angezeigt werden sollen. Standardmäßig sind beide angehakt (alles sichtbar). Brauchst du bei einem bestimmten Effekt z. B. keine Vorschau, hakst du sie hier ab — die Auswahl wird wie die Regler-Häkchen mit der Show gespeichert.

## Tempo-Modus

Unten im Panel legt ein Tempo-Modus fest, wie die Geschwindigkeit des Effekts läuft — die Beschriftung **„Tempo (dieser Effekt)"** macht klar (mit Tooltip-Erklärung), dass Modus, Bus und Multiplikator **nur für den gerade gewählten Effekt** gelten, nicht global. Drei Modi stehen zur Wahl:

- **Aus** — freie Geschwindigkeit über einen eigenen **Slider**, der die Geschwindigkeit **direkt** setzt (kein Faktor).
- **BPM** — der Effekt folgt der **Master-BPM**, zusätzlich einstellbar über einen **Tempo-×-Faktor** (z. B. halb/doppelt so schnell).
- **Tap** — der Effekt bekommt einen **eigenen Takt** auf einem festen Tempo-Bus (**A–D**): Du tippst den **TAP**-Knopf im Rhythmus an, eine **BPM-Anzeige** zeigt das errechnete Tempo.

## Responsives Layout

Das Panel passt seine Anordnung an die Größe an, mit der du es auf die Canvas gezogen hast:

- **Schmal** (Standard) — Vorschau über dem Regler-Bereich, Tempo-Zeile zweizeilig (Aus/BPM/Tap-Knöpfe oben, Multiplikator/Bus-Zeile darunter).
- **Breit** (Panel entsprechend größer skaliert) — die Vorschau rückt **neben** den Regler-Bereich (links, fest ~260 px breit), und die Tempo-Zeile wird **einzeilig**: Multiplikator bzw. Bus/Tap-Anzeige stehen direkt neben den Aus/BPM/Tap-Knöpfen statt darunter. So nutzt ein groß gezogenes Panel die Breite sinnvoll aus, statt nur in die Höhe zu wachsen.

Der Regler-Bereich selbst ist **rahmenlos** — die Regler wirken „einfach darunter geclustert" statt in einer umrandeten Box zu stecken.

## Auto-Refresh bei Fremd-Änderungen

Ändert eine **andere Fläche** denselben Effekt — z. B. der VC-Bus-Selector, MIDI oder die Kommandozeile — zieht das Panel Tempo-Modus und angezeigte Regler automatisch nach: Beim Zurückkehren auf die Bank/den Tab (oder Wiedersichtbarwerden) wird der Stand sofort neu geladen, zusätzlich läuft im Hintergrund ein leiser Abgleich (alle 500 ms, nur solange das Panel sichtbar ist). Ein laufender Slider-/Maus-Vorgang wird dabei nie unterbrochen — der Abgleich wartet, bis keine Maustaste mehr gedrückt ist.

## Touch-Griffe am Rand

Verweilst du im Bearbeiten-Modus kurz mit dem Finger/der Maus auf dem Panel, klappen sich am Rand größere Touch-Greifzonen zum Skalieren auf — der Innenbereich (Content) rückt dabei automatisch mit ein, damit die vergrößerten Griffe nicht unter den Reglern verschwinden und weiterhin erreichbar bleiben.

## Was flüchtig bleibt

Alle Live-Änderungen im Panel — Parameter-Werte, Tempo-Modus, BPM/Faktor — wirken nur **zur Laufzeit**. Beim Speichern der Show werden weiterhin die **ursprünglichen Preset-Werte** des Effekts geschrieben, nicht deine Live-Anpassungen. Gespeichert bleiben nur das Panel und seine Effekt-Zuweisung. Willst du eine Änderung **dauerhaft** übernehmen, bearbeite den Effekt stattdessen im **Programmer**.

## Tipps & Fallen

- **Flüchtig heißt flüchtig:** Lädst du die Show neu, sind alle Live-Edit-Parameterwerte weg — nur der Programmer-Stand zählt. Das Panel und die Liste der zugewiesenen Effekte kommen aber wieder.
- **Mehrere Effekte gleichzeitig:** Du kannst beliebig viele Effekte in ein Panel ziehen und über Dropdown/„−"/„+" zwischen ihnen wechseln.
- **Tap-Bus ist gemeinsam:** Der Tap-Modus nutzt einen der vier festen Tempo-Busse (A–D) — Effekte am selben Bus teilen sich dasselbe getappte Tempo.
- **Ersatz für die alten Baukasten-Blöcke:** Brauchst du, was früher Controller-Vorlage/Color-Chase/Chase-Bereich geleistet haben, ist das Live-Edit-Panel der aktuelle Weg dazu — siehe die Hinweis-Box in [`21_baukasten.md`](anleitung_vc_widgets/21_baukasten.md).
