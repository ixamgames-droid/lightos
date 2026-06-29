# Mini-Anleitung: Grünes Lauflicht 💚➡️

> **Lernziel:** Eine **Farbe** und eine **Bewegung** kombinieren. Merksatz:
> **Bank 1 sagt, WELCHE Farbe. Bank 2 macht die BEWEGUNG.** Zusammen = z. B. ein grünes Lauflicht.
> Dauert 20 Sekunden. Show: `Hochzeit_Komplett_2026.lshow`.

---

### Schritt 1 — Bank 1 „Farbeffekte" öffnen
Geh in die **Virtual Console** (`Strg+4`) und blättere mit `Strg+Bild↑` auf **Bank 1**
(oben steht „BANK 1 FARBEFFEKTE"). Mit APC: **SCENE-Taste 1**.

![Bank 1 Farbeffekte](img/mini_gruenes_lauflicht/01_bank1.png)

### Schritt 2 — Muster „Feste Farbe" antippen
In der Reihe der Paarlichter-Muster die **erste Kachel „Feste Farbe"** antippen.
Jetzt leuchten alle Paarlichter (zunächst weiß).

### Schritt 3 — Farbe „Grün" antippen
In der **obersten Reihe** (die bunten Farb-Kacheln) **„Grün"** antippen.
→ Alle Paarlichter leuchten **voll grün**. (Die Farb-Kacheln färben immer den **gerade laufenden** Effekt um.)

![Alle Paarlichter voll grün](img/mini_gruenes_lauflicht/04_solid_gruen.png)

### Schritt 4 — Bank 2 „Dimmereffekte" öffnen
Mit `Strg+Bild↓` auf **Bank 2** (oben steht „BANK 2 DIMMEREFFEKTE"). Mit APC: **SCENE-Taste 2**.

![Bank 2 Dimmereffekte](img/mini_gruenes_lauflicht/05_bank2.png)

### Schritt 5 — Bewegung „Lauflicht" antippen
Die **erste Dimmer-Kachel „Lauflicht"** antippen.
→ Das Grün **läuft jetzt durch** — die Lampen gehen nacheinander an. Fertig: **grünes Lauflicht!**

![Grünes Lauflicht läuft](img/mini_gruenes_lauflicht/06_chase_frame.png)

![Animation: grünes Lauflicht](img/mini_gruenes_lauflicht/gruenes_lauflicht.gif)

---

### Warum das funktioniert
- **Bank 1 (Farbe)** schreibt nur auf die **Farbkanäle** → bestimmt die Farbe (hier konstant grün).
- **Bank 2 (Dimmer)** schreibt nur auf die **Dimmerkanäle** → macht die **Bewegung** (Lauflicht).
- Beide stören sich nicht (sie schreiben verschiedene Kanäle) und **kombinieren** sich automatisch.

### Sofort weiterprobieren
- **Andere Farbe:** einfach eine andere Farb-Kachel tippen (Rot, Blau, …) → die Bewegung läuft sofort in der neuen Farbe.
- **Andere Bewegung:** in Bank 2 statt „Lauflicht" z. B. **„Innen→Außen"**, **„Puls"** oder **„Welle"** tippen.
- **Regenbogen-Lauflicht:** in Bank 1 statt „Feste Farbe" das **„Regenbogen"** starten, dann in Bank 2 „Lauflicht" → die Lampen gehen nacheinander an, jede in ihrer Regenbogenfarbe.
- **Pro Gerätegruppe:** das Gleiche geht getrennt für **Spider** und **Moving Head** (eigene Kacheln in Bank 1/2) — z. B. Paarlichter grünes Lauflicht **und** Spider blauer Puls gleichzeitig.
