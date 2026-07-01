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

Die Vorschau ist reine Anzeige und verändert den laufenden Effekt nicht.

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

Bewusst **nicht** steuerbar (weil strukturell, nicht live veränderbar): **Algorithmus**, **Stil**, **Spalten/Reihen**.

## Tempo-Modus

Unten im Panel legt ein Tempo-Modus fest, wie die Geschwindigkeit des Effekts läuft. Drei Modi stehen zur Wahl:

- **Aus** — freie Geschwindigkeit über einen eigenen **Slider**, der die Geschwindigkeit **direkt** setzt (kein Faktor).
- **BPM** — der Effekt folgt der **Master-BPM**, zusätzlich einstellbar über einen **Tempo-×-Faktor** (z. B. halb/doppelt so schnell).
- **Tap** — der Effekt bekommt einen **eigenen Takt** auf einem festen Tempo-Bus (**A–D**): Du tippst den **TAP**-Knopf im Rhythmus an, eine **BPM-Anzeige** zeigt das errechnete Tempo.

## Was flüchtig bleibt

Alle Live-Änderungen im Panel — Parameter-Werte, Tempo-Modus, BPM/Faktor — wirken nur **zur Laufzeit**. Beim Speichern der Show werden weiterhin die **ursprünglichen Preset-Werte** des Effekts geschrieben, nicht deine Live-Anpassungen. Gespeichert bleiben nur das Panel und seine Effekt-Zuweisung. Willst du eine Änderung **dauerhaft** übernehmen, bearbeite den Effekt stattdessen im **Programmer**.

## Tipps & Fallen

- **Flüchtig heißt flüchtig:** Lädst du die Show neu, sind alle Live-Edit-Parameterwerte weg — nur der Programmer-Stand zählt. Das Panel und die Liste der zugewiesenen Effekte kommen aber wieder.
- **Mehrere Effekte gleichzeitig:** Du kannst beliebig viele Effekte in ein Panel ziehen und über Dropdown/„−"/„+" zwischen ihnen wechseln.
- **Tap-Bus ist gemeinsam:** Der Tap-Modus nutzt einen der vier festen Tempo-Busse (A–D) — Effekte am selben Bus teilen sich dasselbe getappte Tempo.
- **Ersatz für die alten Baukasten-Blöcke:** Brauchst du, was früher Controller-Vorlage/Color-Chase/Chase-Bereich geleistet haben, ist das Live-Edit-Panel der aktuelle Weg dazu — siehe die Hinweis-Box in [`21_baukasten.md`](anleitung_vc_widgets/21_baukasten.md).
