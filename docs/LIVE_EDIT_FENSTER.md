# Live-Edit-Fenster

> Ein frei schwebendes, größenveränderliches Fenster, in das du Effekte hineinziehst, um ihre Parameter live zu beobachten und zu verändern — ohne die Show zu verändern.

## Wozu & was es steuert

Das Live-Edit-Fenster öffnest du über den Toolbar-Knopf **„Live-Edit"** in der virtuellen Konsole — sowohl im Bearbeiten-Modus als auch im laufenden Betrieb. Es ist ein eigenständiges, frei platzier- und skalierbares Fenster (kein VC-Element auf der Canvas) und ersetzt die früheren Baukasten-Bausteine **Controller-Vorlage**, **Color-Chase** und **Chase-Bereich** (siehe [`docs/anleitung_vc_widgets/21_baukasten.md`](anleitung_vc_widgets/21_baukasten.md)).

**Wichtig: nichts davon wird in der Show gespeichert.** Alle Änderungen im Live-Edit-Fenster wirken sofort auf den laufenden Effekt, sind aber **flüchtig**. Speicherst du die Show, schreibt LightOS die ursprünglichen Preset-Werte — nicht deine Live-Anpassungen. Das Fenster ist damit ein Werkzeug zum **Ausprobieren und Feintunen während der Show**, nicht zum dauerhaften Bearbeiten.

## Effekte zuweisen

- Per **Drag & Drop** ziehst du einen oder mehrere Effekte (Matrix, EFX/Bewegung, Chaser) aus dem Funktions-Baum in das Fenster.
- Oben im Fenster wählt ein **Dropdown** den aktuell angezeigten Effekt; daneben blättern **„−" / „+"** durch alle zugewiesenen Effekte.

## Vorschau je Effekt-Typ

Oben im Fenster zeigt eine Live-Vorschau den gewählten Effekt passend zu seinem Typ:

- **Matrix** — ein **Pixel-Raster** in der echten Geräte-Geometrie.
- **EFX** — der **Bewegungs-Pfad** mit einem darauf laufenden Punkt.
- **Chaser** — eine **Schritt-Leiste** mit dem aktuell aktiven Schritt.

## Parameter-Editor (Anhaken)

Darunter listet das Fenster die **live-steuerbaren Parameter** des Effekts. Du hakst an, was du steuern willst — für jeden angehakten Parameter erscheint ein passender Regler (Auswahl, Zahlenfeld, Slider oder Schalter, je nach Parameter-Typ). Nicht angehakte Parameter bleiben unsichtbar, der Editor bleibt also so aufgeräumt wie nötig.

Beispiele beim Matrix-Chase:

- **Richtung**
- **Bewegung**
- **Läuferzahl**
- **Läuferbreite**
- **Einblenden / Ausblenden**

Bewusst **nicht** steuerbar (weil strukturell, nicht live veränderbar): **Algorithmus**, **Stil**, **Spalten/Reihen**.

## Tempo-Modus

Unten im Fenster legt ein Tempo-Modus fest, wie die Geschwindigkeit des Effekts läuft. Drei Modi stehen zur Wahl:

- **Aus** — freie Geschwindigkeit über einen eigenen **Slider**, wirkt direkt auf den Effekt.
- **BPM** — der Effekt folgt der **Master-BPM**, zusätzlich einstellbar über einen **Tempo-×-Faktor** (z. B. halb/doppelt so schnell).
- **Tap** — der Effekt bekommt einen **eigenen Takt** auf einem festen Tempo-Bus (**A–D**): Du tippst den **TAP**-Knopf im Rhythmus an, eine **BPM-Anzeige** zeigt das errechnete Tempo.

## Nicht gespeichert

Alle Live-Änderungen im Fenster — Parameter-Werte, Tempo-Modus, BPM/Faktor — wirken nur **zur Laufzeit**. Beim Speichern der Show werden weiterhin die **ursprünglichen Preset-Werte** des Effekts geschrieben, nicht deine Live-Anpassungen. Willst du eine Änderung **dauerhaft** übernehmen, bearbeite den Effekt stattdessen im **Programmer**.

## Tipps & Fallen

- **Flüchtig heißt flüchtig:** Schließt du die Show oder lädst neu, sind alle Live-Edit-Anpassungen weg — nur der Programmer-Stand zählt.
- **Mehrere Effekte gleichzeitig:** Du kannst beliebig viele Effekte ins Fenster ziehen und über Dropdown/„−"/„+" zwischen ihnen wechseln, statt mehrere Fenster offen zu halten.
- **Tap-Bus ist gemeinsam:** Der Tap-Modus nutzt einen der vier festen Tempo-Busse (A–D) — Effekte am selben Bus teilen sich dasselbe getappte Tempo.
- **Ersatz für die alten Baukasten-Blöcke:** Brauchst du, was früher Controller-Vorlage/Color-Chase/Chase-Bereich geleistet haben, ist das Live-Edit-Fenster der aktuelle Weg dazu — siehe die Hinweis-Box in [`21_baukasten.md`](anleitung_vc_widgets/21_baukasten.md).
