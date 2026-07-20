# Anleitung: EFX — Moving-Head-Bewegung (Kreise, Achten …)

> Ein **EFX** bewegt die **Pan/Tilt**-Achsen von Moving Heads (und Spidern) auf einer Bahn —
> Kreis, Acht, Linie, eigene Pfade. Wichtig für die Hardstyle-Show: der EFX **bewegt** die
> Moving Heads, und mit **„Dimmer/Shutter mit öffnen"** **öffnet** er sie auch (Shutter + Dimmer),
> sonst bleiben sie dunkel.

---

## 1. EFX anlegen & an die Geräte binden

Programmer → Tab **EFX** → **+ Neu**. Der eingebettete EFX **folgt der Programmer-Auswahl LIVE**:
Sobald du eine Gruppe bzw. Geräte auswählst (z. B. **Moving Heads (2)** bzw. **Alle Mover**), bindet
sich der gerade angezeigte EFX automatisch an genau diese Geräte. Die Reihenfolge ist dabei egal —
ob du zuerst die **Gruppe wählst** und dann **+ Neu** drückst oder umgekehrt: Der EFX übernimmt die
aktuelle Auswahl in jedem Fall sofort.

Dass der EFX der Auswahl folgt, siehst du an der Geräte-Box im Editor: Sie heißt dynamisch
**„Geräte (folgen der Auswahl)"** und zeigt bei aktiver Auswahl z. B. **„Geräte: 2 Moving Head(s)
(folgen der Auswahl)"** (bzw. **„Geräte: keine Moving Heads in der Auswahl"**, falls nichts
Passendes markiert ist — der EFX bindet nur Geräte mit Pan **und** Tilt).

In der Gruppe **Form & Geometrie** stellst du ein:
- **Algorithmus:** Die Namen erscheinen englisch — *Circle* (Kreis), *Eight* (Acht), *Line* (Linie),
  *Diamond* (Raute), *Square* (Quadrat), *Trapez*, *Lissajous*, *Random* (Zufall), *Triangle*
  (Dreieck) sowie *Custom Path* für eigene, aufgezeichnete Bahnen.
- **Breite (Pan-Hub)** / **Höhe (Tilt-Hub):** wie weit die Bewegung ausschlägt (0–255, DMX-Wert).
- **Geschwindigkeit (Hz)** (Tempo) und **Richtung** (in der Gruppe *Tempo & Richtung*).

![EFX-Editor (Algorithmus Circle, Pan/Tilt-Hub)](img/01_efx_editor.png)

> Merke: Immer der **gerade angezeigte** Effekt bindet sich an die aktuelle Auswahl, und zwar
> sofort. Willst du einen *anderen* Effekt an eine andere Gruppe binden, **erst diesen Effekt in der
> Liste auswählen** (dann ist er der angezeigte) und die gewünschten Geräte markieren — der Effekt
> übernimmt die Auswahl umgehend.

## 2. Die Köpfe „aufmachen" — „Dimmer/Shutter mit öffnen"

Moving Heads haben Shutter + Dimmer. Läuft nur die Bewegung, bleiben sie oft **dunkel**. Lösung:
in der Gruppe **„Sichtbarkeit & Sonstiges"**, Zeile **„Sichtbarkeit:"**, die Checkbox
**„Dimmer/Shutter mit öffnen" AN** — dann öffnet der EFX bei Bewegung **Shutter + Dimmer**
automatisch (setzt sie auf offen/voll). Erst dann sieht man die bewegten Strahlen.

> Farbe bekommen die Moving Heads separat — entweder über eine **Farb-Matrix**, die die MH mit
> abdeckt (siehe *Farbchase*), oder im **Color-Tab**. Bewegung (EFX) + Farbe (Matrix) +
> „Dimmer/Shutter mit öffnen" ergeben den vollen Look.

## 3. Verhältnis mehrerer Geräte

Bei mehreren Movern stellst du in der Gruppe **„Verhältnis der Geräte zueinander"** ein, wie sie
zueinander durch die Figur laufen. Die echten Bedienelemente sind:

- **Verhältnis:** (Auswahlfeld) — bestimmt das Grundmuster:
  - *Synchron (alle Köpfe gleich)* — alle fahren dieselbe Figur gleichzeitig.
  - *Gleichmäßig verteilt (Fächer)* — die Köpfe sind über die Figur gefächert (2 Köpfe = 180°
    auseinander).
  - *Fester Versatz pro Gerät (°)* — jeder weitere Kopf läuft um die eingestellten Grad später.
- **Fächer-Streuung:** (Drehfeld) — nur aktiv bei **Gleichmäßig verteilt (Fächer)**: wie weit die
  Köpfe gefächert sind (0 = praktisch synchron, 1 = voller Fächer).
- **Versatz pro Gerät:** (Drehfeld, in °) — nur aktiv bei **Fester Versatz pro Gerät (°)**: um wie
  viel Grad jeder weitere Kopf nachläuft (z. B. 15° leichter Nachlauf, 180° gegenphasig).
- **Gegenläufig:** Checkbox *„jedes 2. Gerät entgegengesetzt"* — jeder zweite Kopf durchläuft die
  Figur rückwärts (z. B. zwei Köpfe gegenläufig im Kreis: einer cw, einer ccw).
- **Spiegeln:** Checkbox *„jedes 2. Gerät spiegeln (Pan)"* — spiegelt bei jedem zweiten Kopf die
  Pan-Achse → symmetrische (spiegelbildliche) statt versetzter Bewegung.

So laufen z. B. die beiden Hardstyle-MH gegenläufige Kreise: **Verhältnis** = *Synchron* und
**Gegenläufig** anhaken.

## 4. Tempo & Musik-Sync

- **Geschwindigkeit (Hz)** stellt die Bahn-Rate als festen Wert ein. Die Gruppe *Tempo & Richtung*
  enthält außerdem **Tempo-Bus**, **Tempo ×**, **Tempo-Versatz**, **Taktgleich starten**,
  **Richtung** und **Loop**.
- Für **musiksynchron** stellst du **Tempo-Bus** direkt im EFX-Editor auf **Global (taktgleich,
  Standard)** — dann folgt die Bewegung der Master-/Musik-BPM und startet mit **Taktgleich starten**
  auf dem gemeinsamen Beat-Raster. **Tempo ×** läuft relativ dazu (z. B. ×2 = doppelt so schnell),
  **Tempo-Versatz** verschiebt die Phase; für bewusst freien Lauf **Frei (nicht taktgebunden)**.
- In der **Virtuellen Konsole** lässt sich die Bus-/Faktor-Umschaltung zusätzlich **live** steuern
  (SpeedDial / Tempo-Bus-Selektor — siehe *Musik-Sync* / *Dimmer-Matrix*).

## 5. Starten

Den EFX mit **▶ Start** starten (**■ Stop** daneben). So sieht eine Kreis-Bewegung aus:

![Moving-Head-Kreis](../tutorial_matrix/gif/mh_kreis.gif)

---

**Kurz:** EFX-Tab → **+ Neu** und Gruppe (Moving Heads) wählen (Reihenfolge egal — der EFX folgt der
Auswahl live) → Algorithmus (Circle …) + Pan/Tilt-Hub (0–255) + Geschwindigkeit →
**„Dimmer/Shutter mit öffnen" AN** (sonst dunkel) → Verhältnis der Geräte zueinander (Verhältnis:
Synchron/Fächer/Versatz, dazu Gegenläufig/Spiegeln) → **▶ Start**. Musik-Sync per **Tempo-Bus**
direkt im EFX-Editor (Global/Bus A–D + Tempo ×), zusätzlich live über die Virtuelle Konsole. Farbe
der MH separat über eine Farb-Matrix oder den Color-Tab.
