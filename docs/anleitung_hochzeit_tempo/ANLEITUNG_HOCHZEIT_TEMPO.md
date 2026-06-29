# Hochzeit-Show: Farbwechsel und Dimmer taktgleich starten

Diese Anleitung gilt für `shows/hochzeit.lshow`. Die drei Effektgruppen bleiben
unterschiedlich schnell einstellbar, beginnen ihre Zyklen aber auf demselben Taktschlag.

> **Umgebaut auf die neuen Tempo-Controller.** Die früheren Multiplikator-SpeedDials
> („Farb Wechsel" / „An Aus") sind durch das **All-in-One Tempo-Controller-Widget** ersetzt —
> ein Panel pro Gruppe, das Bus, Quelle, Tempo **und** die gekoppelten Effekte vereint.
> Allgemeine Bedienung: **[Tempo-Controller-Anleitung](../anleitung_tempo_controller/ANLEITUNG_TEMPO_CONTROLLER.md)**.

## Was bereits eingerichtet ist

Drei **Tempo-Controller** (in der VC, auf der Tempo-Bank — dort, wo zuvor die
Multiplikator-Fenster lagen):

| Controller | Bus | Gekoppelte Effekte |
|---|---|---|
| **Farb Wechsel** | **Bus A** | die drei Farbwechsel-Effekte (Hintergrund / LED-Bar / Strahler) |
| **An Aus** | **Bus B** | die sieben Dimmer-Effekte (An/Aus + Lauflicht von Strahlern, Spider, Moving Heads, LED-Bar, Hintergrund) |
| **Innen Aussen** | **Bus C** | der Innen/Außen-Effekt |

Alle drei stehen auf **Quelle = Sound** (folgen also der Musik) und **Tempo = 1×**.
Weil „Sound" jeden Bus als **Sub der Haupt-BPM** führt, laufen die drei Gruppen
**untereinander taktgleich** — du kannst aber jede Gruppe unabhängig schneller/langsamer
stellen, ohne dass sie aus dem Takt fällt.

## 1. Tempo einer Gruppe ändern

1. **Virtuelle Konsole** öffnen (Bearbeiten **aus** — zum Bedienen).
2. Am gewünschten Controller im **Tempo**-Gitter den Faktor wählen:
   **¼ · ½ · 1× · 2× · 4×** (⟲ = zurück auf 1×).

Beispiel: **Farb Wechsel = 1×**, **An Aus = ½** → bei 128 BPM wechselt die Farbe mit
128 BPM, der Dimmer geht mit 64 BPM an/aus. Beide beginnen trotzdem auf derselben Eins —
es bleibt z. B. sauber **rot/aus/rot/aus**.

## 2. Effekte prüfen / ergänzen

- **Welche Effekte hängen dran?** Klick auf die **Effekt-Zeile** des Controllers →
  Menü listet jeden gekoppelten Effekt (mit **„✕ entfernen"**).
- **Neuen Effekt ankoppeln:** Effekt aus der **Bibliothek** auf den Controller **ziehen** →
  er wird dem Bus **taktgleich** zugewiesen und läuft sofort mit.

Ein neuer Effekt, den du im Editor anlegst, steht ohnehin standardmäßig auf
**Tempo-Bus = Global · Taktgleich an** — er fällt also automatisch ins Raster. Nur für
einen bewusst unabhängigen Effekt nimmst du im Editor den Haken **„Taktgleich starten"**
weg oder wählst **Tempo-Bus = Frei**.

## 3. Quelle umstellen (optional)

Standard ist **Sound** (folgt der Musik). Brauchst du ein **festes** Tempo:
- Am Controller **Fix** wählen, mit dem **Mausrad** die BPM einstellen.
- Oder **Tap** und den Takt mitklicken.

## 4. Gemeinsamen Takt erzwingen

Wirkt etwas verrutscht (z. B. nach manuellem Umstellen):
- Am betroffenen Controller **[ SYNC jetzt ]** drücken → die ganze Gruppe springt
  gemeinsam auf die Eins.
- Alternativ im **BPM-Tab (Strg+8)** das Panel **„Effekte je Bus"** öffnen und dort pro
  Bus **[ Sync jetzt ]** drücken bzw. die **„Taktgleich"**-Häkchen prüfen.

## Wenn etwas nicht synchron läuft

1. **Regler reagieren nicht?** → **Bearbeiten-Modus aus.**
2. Steht der Controller auf dem richtigen **Bus** (A/B/C) und der Effekt **gelistet**
   (Klick auf die Effekt-Zeile)?
3. Im **BPM-Tab → „Effekte je Bus"**: hängt der Effekt am erwarteten Bus, ist das
   **„Taktgleich"**-Häkchen an, stimmt der **Faktor**?
4. **[ SYNC jetzt ]** drücken.
