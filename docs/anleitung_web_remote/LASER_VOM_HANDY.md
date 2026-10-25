# Laser vom Handy erlauben — die Bedingungen

> Ab Werk lässt die Handy-Konsole **nichts** bedienen, was einen Laser ansteuert.
> Mit dem Schalter **„Laser vom Handy erlauben"** (Ausgabe → **Web-Remote:
> Verbindung & Token…**) hebst du diese Sperre auf. Vorher fragt LightOS nach
> (vorgewählt ist **„Abbrechen"** — ein versehentliches Enter gibt nichts frei);
> diese Seite erklärt, was du damit zusagst und was LightOS trotzdem sperrt.

Zurück zur Anleitung: [Web-Remote — das Handy als Konsole](ANLEITUNG.md)

---

## Was „Laser-Inhalt" heißt

Gesperrt ist ein Element der Handy-Konsole, wenn es einen Laser ansteuern kann:

- eine **Laser-Muster**-Taste,
- eine Taste, deren Funktion (Szene, Effekt, Chaser, Collection, auch über eine
  Zusatzaktion) ein Gerät enthält, das LightOS als **Laser** erkennt,
- eine Taste für **Bibliothek-Farbe/Snap** oder **Snapshot** mit einem Laser darin,
- eine **Effekt-Aktion** ohne festes Ziel (sie wirkt auf den gerade aktiven Effekt),
- ein **Fader** auf einem DMX-Kanal eines Lasers, auf einer Funktion mit Laser
  (auch Effekt-Tempo und -Parameter), ein **Playback-Fader** auf einem Executor
  mit Laser-Cues, ein **Submaster** oder **Gruppen-Dimmer** über einen Laser, ein
  **Programmer-Fader** für alle, die Auswahl oder eine Gruppe mit Laser, und ein
  **Grand-Master-Fader**,
- eine **Cueliste**, deren Cues einen Laser enthalten.

„Laser" erkennt LightOS genauso wie beim **Laser-NOT-AUS**: dieselben Geräte,
die der NOT-AUS dunkel schaltet. Steht gar kein Laser im Patch, gibt es auch
keine Sperre (außer für Laser-Muster-Tasten).

Geprüft wird **bei jedem Druck neu**. Eine Taste, die du nachträglich auf eine
Laser-Szene umstellst, oder ein Laser, den du später patchst, ist sofort
gesperrt — auch wenn die Taste schon auf dem Handy liegt.

Am Handy erscheinen gesperrte Elemente grau mit **„🔒 Laser – Freigabe am Pult"**.
**„Automatisch füllen"** legt sie nicht aufs Handy, und von Hand lassen sie sich
nicht ablegen, solange der Schalter aus ist.

Auch der **Grand Master** in der festen Leiste unten am Handy gehört dazu: steht
ein Laser im Patch, setzt LightOS ihn bei Grand Master 0 auf „aus". Das Handy
darf den Grand Master deshalb nur dann wieder hochziehen, wenn **es selbst** ihn
heruntergezogen hat — oder wenn der Schalter an ist.

## Die Bedingungen

Mit **„Laser freigeben"** im Bestätigungsfenster sagst du zu:

1. **Sicht:** Wer am Handy bedient, sieht den ganzen Laser-Bereich und das
   Publikum.
2. **NOT-AUS:** Am Pult ist während der ganzen Zeit jemand, der den
   **Laser-NOT-AUS** sofort auslösen kann. (Das Handy kann ihn ebenfalls
   auslösen, aber nie lösen.)
3. **Netz:** Nur im eigenen WLAN. Den Link, den Schlüssel und den QR-Code nicht
   weitergeben; bei Verdacht **„Schlüssel erneuern"**.
4. **Pult behält das letzte Wort:** Scharfschalten und das Lösen des NOT-AUS
   gehen nur am Pult — daran ändert der Schalter nichts.
5. **Danach aus:** Nach der Veranstaltung den Schalter wieder ausschalten.

Geltende Vorschriften für den Laserbetrieb (Anzeige, Laserschutzbeauftragte
Person, Sperrzonen) gelten unverändert — der Schalter ersetzt keine davon.

## Was der Schalter nicht freigibt

Auch eingeschaltet bleibt gesperrt:

- **Scharfschalten** eines Lasers vom Handy (nur „unscharf" geht).
- **NOT-AUS lösen** — nur am Pult, nach der Rückfrage.
- Elemente, die auf **keiner Handy-Seite** liegen.

**Loslassen** einer gehaltenen Taste und **STOP** einer Cueliste gehen dagegen
immer, auch ohne Schalter — sie schalten nichts ein.

## Ausschalten

Haken bei **„Laser vom Handy erlauben"** entfernen. Das wirkt sofort, auch auf
verbundene Handys: die Laser-Elemente werden dort wieder grau, ein schon
gehaltener Flash lässt sich aber noch loslassen.
