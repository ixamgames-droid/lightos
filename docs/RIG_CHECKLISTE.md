# Rig-Checkliste — die fünf Prüfungen, die nur am Gerät gehen

> **Wofür das hier ist:** `HW-1`…`HW-5` im [BACKLOG](../BACKLOG.md) sind alle
> code-fertig und headless verifiziert. Es fehlt nur noch, dass jemand hinsieht.
> Diese Seite ist zum Mitnehmen ans Rig gedacht: pro Prüfung ein Handgriff, was
> dabei zu sehen sein muss, und was es bedeutet, wenn es anders aussieht.
>
> **Reihenfolge:** 1 → 3 → 2 → 4 → 5. HW-1 und HW-3 gehören zusammen (beide am
> selben Mehrkopf-Gerät), HW-2 braucht laufendes Licht, HW-5 läuft nebenher.
> **Zeitbedarf ohne HW-5: rund 30 Minuten.**

---

## Dein Rig, wie die Software es aktuell sieht

Am 2026-08-02 aus `data/current_show.db` ausgelesen. **Stimmt das nicht mehr,
sind die Adressen unten falsch** — dann erst den Patch prüfen, sonst misst du
etwas anderes als du denkst.

| Gerät | fid | Universe | Adresse | Kanäle | Köpfe |
|---|---|---|---|---|---|
| EventPAR IP65 ×14 | 1–14 | 1 (Art-Net) | 1, 10, 19 … 118 | 9 | 1 |
| ZQ01424 ×8 | 15–22 | 1 (Art-Net) | 127, 135 … 191 | 8 | 1 |
| **HYDRABEAM 4000 · 1** | **23** | **1 (Art-Net)** | **191** | **56** | **4** |
| **HYDRABEAM 4000 · 2** | **24** | **1 (Art-Net)** | **247** | **56** | **4** |
| Conti Moving Head ×2 | 31, 32 | 1 (Art-Net) | 303, 317 | 11 | 1 |
| Spider ×2 | 27, 28 | 1 (Art-Net) | 331, 345 | 14 | Tilt-Bänke |
| Mini Spider ZQ-B20 ×2 | 29, 30 | 1 (Art-Net) | 359, 374 | 15 | Tilt-Bänke |

**Zwei Dinge, die anders sind als in älteren Notizen:**

* Die Hydrabeams hängen **an Art-Net, nicht am Enttec**. HW-1 und HW-3 brauchen
  den Enttec also gar nicht — sie gehen über den Art-Net-Node.
* **Auf dem Enttec-Universe (3) ist nichts gepatcht.** Weder in dieser Show noch
  in einer der 15 gespeicherten oder 47 archivierten. Der Enttec ist angeschlossen
  (`/dev/ttyUSB0`, ENTTEC DMX USB PRO, Seriennr. EN492875) und der Port ist seit
  dem 2026-08-02 korrekt eingetragen — er trägt nur derzeit keine Geräte.

---

## HW-1 ⭐ — Welche Lampe ist „Kopf 2"?

**Die wichtigste Prüfung.** Die ganze Kopf-Kette (Programmer-Kopfwahl, Fächer,
EFX-Kopf-Ziele, Pro-Kopf-Matrix, Kopf-Raster) nimmt an:

> Das **N-te Vorkommen** eines Kanals = der **N-te Kopf in physischer Reihenfolge**.

Bei Pixel-Panels war genau diese Annahme falsch — die ADJ Dotz Matrix nummeriert
ab Werk in Schlangenlinien, ein Lauflicht liefe dort im Zickzack. Ob es bei einem
Mehrkopf-Mover stimmt, kann Software nicht wissen: sie kann Kanäle zählen, aber
nicht sehen, wo die Lampe hängt.

**Vorbereitung:** Hydrabeam 1 (fid 23) muss Strom haben und auf Adresse 191
stehen. Grand-Master auf, Blackout aus.

**Handgriff**

1. Programmer-Tab → in der Geräteliste **HYDRABEAM 4000 · 1** aufklappen.
2. Zeile **„└ Kopf 2"** anklicken (nicht das Gerät selbst).
3. Farbe Rot auf 255 ziehen.
4. Notieren, **welche Lampe leuchtet** — von vorn gesehen, also aus Publikumssicht.
5. Dasselbe für **Kopf 3** und **Kopf 4**.

**Was du sehen musst**

Kopf 2 leuchtet als **zweite Lampe von links** (Publikumssicht), Kopf 3 als
dritte, Kopf 4 als vierte. Genau eine Lampe pro Schritt.

**Wenn es anders aussieht**

* **Reihenfolge vertauscht** (z. B. Kopf 2 leuchtet rechts außen): wir brauchen
  eine Kopf-Reihenfolge pro Profil, so wie es sie für Pixel-Panels schon gibt.
  Dann stimmen Fächer-, EFX- und Matrix-Verläufe über Köpfe erst wirklich.
* **Mehrere Lampen gleichzeitig:** die Kopf-Auswahl trifft den geteilten
  Master-Kanal statt den Kopf-Kanal — das wäre ein Fehler in der Kopf-Karte.
* **Gar nichts leuchtet:** erst Grand-Master, Blackout und die Adresse prüfen,
  bevor du es als Befund meldest.

**Melde mir:** je Kopf, welche physische Lampe leuchtet. Vier Zeilen reichen.

---

## HW-3 — Bewegt sich wirklich nur ein Kopf?

Direkt im Anschluss an HW-1, am selben Gerät. Der Fix ist im Kanalstreifen
bewiesen (nur CH6/CH7 bewegten sich, die anderen Köpfe blieben auf 128/128) —
aber noch nie an einem echten Motor.

**Handgriff**

1. **Kopf 2** wählen (wie bei HW-1).
2. EFX-Tab → **`+ Neu`**.
3. **`Speichern`** drücken. ⚠️ Ein nicht gespeicherter Entwurf verschwindet beim
   Tab-Wechsel — das ist keine Fehlfunktion, aber es kostet dich sonst den Test.
4. **`▶ Start`**.

**Was du sehen musst**

Nur der eine Kopf fährt die Figur. Die anderen drei stehen still.

**Wenn es anders aussieht**

* **Alle vier fahren:** das Kopf-Ziel greift nicht — dann ist die EFX-Kopf-Zuordnung
  betroffen, nicht die Auswahl (die hat HW-1 ja gerade bewiesen).
* **Der falsche Kopf fährt:** das ist derselbe Befund wie eine vertauschte
  Reihenfolge in HW-1 und gehört dort mit hinein.

**Melde mir:** bewegt sich nur dieser Kopf, stehen die anderen, ist der Strahl
sichtbar.

---

## HW-2 — Blitzt beim Show-Wechsel noch etwas?

Deine ursprüngliche Beobachtung. Der Fix ist gelandet und headless bewiesen:
jeder Null-Schreibvorgang während des Ladens wurde mitgeschnitten — vorher vier,
nachher keiner. Was fehlt, ist der Gegenbeweis am Auge.

**Handgriff**

1. Rig an, **Licht steht** — irgendein Look, Hauptsache es leuchtet sichtbar.
2. Bei laufendem Licht **eine andere Show laden**.
3. Auf den Moment des Ladens achten.

**Was du sehen musst**

Kein Blitzen, kein kurzes Dunkelwerden. Das Licht wechselt vom alten auf den
neuen Zustand, ohne Zwischenschritt über Schwarz.

**Wenn es anders aussieht**

Notiere **bei welchem Gerät** und **auf welchem Universe** es blitzt. Es gibt
einen bekannten Rest-Vektor (`CDX-22b`), der nur per Skript getriebene Roh-Kanäle
betrifft — der wäre daran zu erkennen, dass es ausgerechnet ein Kanal ohne
gepatchtes Gerät ist.

**Melde mir:** blitzt noch etwas — ja/nein, und wenn ja: Gerät und Universe.

---

## HW-4 — Stimmen die Profile am echten Gerät?

Der Durchgang gegen die dokumentierten Annahmen. Beschreibung im Backlog nennt
noch „4 PAR + 2 Moving Heads" — dein Rig ist inzwischen deutlich größer (Tabelle
oben). Die Prüfung lohnt trotzdem, aber stichprobenartig statt vollständig.

**Handgriff — pro Gerätetyp eine Stichprobe**

1. Ein Gerät auswählen, **Dimmer hoch**. Kommt Licht?
2. **Farbe** setzen (Rot, dann Grün, dann Blau). Kommt die richtige Farbe?
3. Bei Movern: **Pan und Tilt** je einmal von Anschlag zu Anschlag. Fährt es in
   die erwartete Richtung, und bleibt es in den Grenzen?
4. Bei Geräten mit Shutter: **Shutter zu und auf.** Wird es wirklich dunkel?

Interessant sind vor allem die Typen, die noch nie am Gerät geprüft wurden:
**ZQ01424** (8ch), **Spider** (14ch), **Mini Spider ZQ-B20** (15ch).

**Was es bedeutet, wenn etwas nicht stimmt**

* **Falsche Farbe** (Rot kommt als Grün): Kanalreihenfolge im Profil vertauscht.
* **Bewegung invertiert:** dafür gibt es im Patch die Schalter `invert_pan` /
  `invert_tilt` — das ist eine Einstellung, kein Fehler.
* **Ein Mover bleibt stehen, der fahren soll:** das ist der alte Punkt
  „MH-Stillstand". Dann bitte notieren, **ob er gar nicht** oder **nur manchmal**
  steht — das unterscheidet ein Profil-Problem von einem Ausgabe-Problem.

**Melde mir:** je geprüftem Typ eine Zeile „passt" oder was abweicht.

---

## HW-5 🔬 — Hält der Enttec über Stunden?

**Die Software-Hälfte ist beantwortet:** zwei Läufe über `/dev/ttyUSB0`, der
zweite über **10,21 Stunden** mit 1.456.939 Frames und **null Schreibfehlern**.
Der Schreibpfad bricht nicht weg.

**Was noch fehlt, ist der *stille* Tod:** der Adapter nimmt Bytes an, legt aber
kein gültiges DMX mehr auf die Leitung. Von Software aus ist das unsichtbar —
dafür braucht es ein Gerät an der Enttec-Leitung und deinen Blick.

**Vorbereitung:** ⚠️ Auf dem Enttec-Universe ist derzeit **nichts gepatcht**.
Für diese Prüfung muss also mindestens ein Gerät an die Enttec-Leitung und auf
eine bekannte Adresse gepatcht werden.

**Handgriff**

```
venv/bin/python tools/hw5_longrun.py --probe --heartbeat-channel <N>
```

`<N>` ist der Kanal, auf dem das Gerät reagiert (z. B. sein Dimmer).

* `--probe` = kurzer Sichttest statt Langlauf.
* `--heartbeat-channel` legt ein **Dreieck** auf den Kanal — bewusst kein
  fester Pegel: DMX hält den letzten Wert, ein toter Ausgang sähe bei statischem
  Pegel exakt aus wie ein lebender.

**Was du sehen musst**

Das Gerät **atmet** — heller, dunkler, heller, im Takt. Nicht: steht auf einem
Wert.

**Für den Langlauf** dasselbe ohne `--probe`, Zwischenstand jederzeit mit
`--status`. Der Lauf überlebt das Session-Ende, aber keinen Neustart.

**Melde mir:** kommt der Ramp am Gerät an — ja/nein.

---

## Wenn du fertig bist

Auch ein „passt überall" ist ein Ergebnis: dann werden die Punkte geschlossen und
die Annahmen gelten als belegt. Bei einer Abweichung wird daraus ein
Umsetzungs-Item — bei HW-1 zum Beispiel „Kopf-Reihenfolge pro Profil".

Vollfassung mit Historie: [BACKLOG.md](../BACKLOG.md), Abschnitt
„🔌 Braucht Davids Hardware".
