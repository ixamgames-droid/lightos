# Mini-Anleitung: Farbe pro Gruppe 🔴🔵🟢

> **Lernziel:** Jeder Gerätegruppe **eine eigene Farbe** geben — gleichzeitig.
> Beispiel: **Paarlichter rot · Spider blau · Moving Head grün**. Die Gruppen stören sich nicht.
> Show: `Hochzeit_Komplett_2026.lshow`, **Bank 1 (Farbeffekte)** (`Strg+4`, dann `Strg+Bild↑` bis Bank 1).

![Bank 1 — die drei Gruppen-Bereiche](../img/bank1_farbe.png)

In Bank 1 sind die Muster nach **Gerätegruppe** angeordnet:
- **Reihe 2–3 links:** Paarlichter-Farbe (Feste Farbe, Farbwechsel, Regenbogen, …)
- **Reihe 3 mitte:** Spider-Farbe (Spider Feste Farbe / Farbwechsel / Regenbogen + Spider-Themes)
- **Reihe 4:** Moving-Head-Farbrad (MH Rot/Grün/Blau/Weiß/Gelb/Rotation)

---

### Schritt 1 — Paarlichter rot
**„Feste Farbe"** (erste Paarlichter-Kachel) antippen → dann oben **„Rot"** antippen.
→ Alle Paarlichter leuchten rot.

### Schritt 2 — Spider blau
**„Spider Feste Farbe"** antippen → dann oben **„Blau"** antippen.
→ Die Spider leuchten blau. **Die Paarlichter bleiben rot** (eigene Gruppe!).

### Schritt 3 — Moving Head grün
**„MH Grün"** antippen (Farbrad-Kachel im Moving-Head-Bereich).
→ Der Moving Head wird grün. Paarlichter rot + Spider blau bleiben.

**Fertig:** drei Gruppen, drei Farben, gleichzeitig.

---

### Warum das funktioniert
Jede Gruppe (Paarlichter / Spider / Moving Head) hat ihre **eigene Auswahl-Gruppe** (intern `edit_slot`).
Eine neue Farbe in einer Gruppe ersetzt **nur** die Farbe **dieser** Gruppe — die anderen laufen weiter.
So kannst du jede Gruppe unabhängig einfärben (und in **Bank 2** sogar unabhängig bewegen lassen).

### Sofort weiterprobieren
- **Mit Bewegung kombinieren:** in **Bank 2** je Gruppe eine Dimmer-Bewegung dazu (z. B. Paarlichter „Lauflicht", Spider „Puls") → rotes Lauflicht + blauer Spider-Puls gleichzeitig.
- **Farbwechsel statt fest:** statt „Feste Farbe" das **„Farbwechsel"** der Gruppe → die Gruppe zykelt Farben (auf den Beat, siehe Bank 4).
- **Alles auf einmal:** unten rechts **„Alles"** als Gruppe wählen und eine Farbe tippen → ein gemeinsamer Look.
