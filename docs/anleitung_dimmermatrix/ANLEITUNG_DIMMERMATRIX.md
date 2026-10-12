# Anleitung: Dimmer-Matrix & Geschwindigkeit (Helligkeit als eigene Ebene)

> Eine **Dimmer-Matrix** treibt nicht die *Farbe*, sondern die **Helligkeit** der Geräte —
> als eigene Lauflicht-/Puls-Ebene **über** einer Farb-Matrix. Im Hardstyle-Look läuft sie
> z. B. **schneller als der Farb-Chase** und lässt sich musik-synchron koppeln (das Koppeln
> stellst du direkt im Matrix-Editor ein — **Tempo-Bus**, Standard „Global" folgt der Musik-BPM;
> die Virtuelle Konsole dient zum Live-Umschalten). Genutzt wird die vorhandene **RGB-Matrix**
> mit **Stil = Dimmer**.

---

## 1. Idee: Farbe und Helligkeit als getrennte Ebenen

- **Farb-Matrix** (Stil RGB/RGBW) setzt nur die **Farbe** der Geräte (siehe Anleitung *Farbchase*).
- **Dimmer-Matrix** (Stil **Dimmer**) setzt nur den **Dimmer-/Helligkeitskanal** — sie schreibt
  Graustufen (an/aus bzw. Verlauf) und lässt die Farbe in Ruhe. Auf Geräten **ohne** eigenen
  Dimmer-Kanal (reine RGB-Geräte) bewirkt sie deshalb nichts.
- Beide laufen **gleichzeitig** über dieselben Geräte: Farbe von der einen, Helligkeit von der
  anderen. So bekommst du z. B. einen **blauen Chase**, dessen Helligkeit zusätzlich pulst.

## 2. Dimmer-Matrix anlegen

Programmer → Tab **Matrix** → **+ Neu** → in **Grundeinstellungen**:

- **Algorithmus: Chase** (Lauflicht; alternativ *Atmen (Puls)* = pulsierend, *Strobe* = hartes An/Aus)
- **Stil: Dimmer**
- **Spalten/Reihen** musst du nicht von Hand setzen: Der eingebettete Editor folgt automatisch
  der **Programmer-Auswahl** (die manuellen Zuweisungs-Buttons sind ausgeblendet). Daraus ergibt
  sich das Geräte-Grid von selbst — bei loser Auswahl als **Spalten = Anzahl der Geräte**
  (hier 10 = PAR + Spider), **Reihen = 1**.
- **💾 Speichern**, dann in der Liste links **▶ Start** — gestartet wird immer die gespeicherte
  Fassung.

Die **Vorschau** zeigt die Helligkeit als Graustufen-Lauflicht (weiße Balken = hell):

![Dimmer-Matrix im Editor (Stil = Dimmer)](img/01_matrix_dimmer.png)

> In **Bewegung & Parameter** steuerst du die **Läufer-Anzahl** (mehr Läufer = voller/dichter),
> die **Läufer-Breite** und **Schweif (%)** (0 % → harte Kante ohne Schweif, höher → langes weiches
> Nachfaden hinter dem Läufer). In der Gruppe **Farben** legst du bei Stil *Dimmer* über den
> **Dimmer-Bereich** (Spinboxen **Min** / **Max**) den Helligkeitsbereich fest — außer wenn
> **„Dimmer pro Runde wechseln"** aktiv ist: dann gilt die Dimmerwert-Folge, Min/Max sind
> ausgeblendet.

## 3. Geschwindigkeit: fest einstellen oder ans Tempo koppeln

Im Matrix-Editor gibt es in der Gruppe **Tempo & Blende** jetzt direkt:
**Geschwindigkeit**, **Tempo-Bus**, **Tempo ×**, **Tempo-Versatz**, **Taktgleich starten**
(diese drei nur bei gewähltem Bus), **Layer-Priorität**, **Einblenden**, **Ausblenden** und
**Hüllkurven-Form**.

- **Geschwindigkeit** ist die eigene Rate der Matrix (Schritte pro Sekunde). Sie wirkt nur im
  **Frei-Lauf** — Tempo-Bus *Frei* — bzw. solange der gewählte Bus noch keine BPM hat. Läuft
  eine BPM (Tap oder Musik), bestimmt **Tempo ×** das Tempo: für einen doppelt so schnellen
  Dimmer-Puls also bei der Dimmer-Matrix **Tempo × = 2** einstellen, die Farb-Matrix bleibt
  auf 1.
- Mit **Layer-Priorität** entscheidest du, wer gewinnt, wenn zwei Effekte denselben Kanal
  schreiben (höher gewinnt; bei gleicher Priorität der zuletzt gestartete Effekt).
- **Einblenden / Ausblenden** sind die Ein-/Ausblendzeiten (in Sekunden) beim Start/Stopp; die
  **Hüllkurven-Form** bestimmt deren Verlauf.

Neue Matrix-Effekte stehen standardmäßig auf **Tempo-Bus = Global**,
**Tempo × = 1** und **Tempo-Versatz = 0**. Damit laufen sie automatisch im gemeinsamen
Taktraster. Nur wenn ein Effekt bewusst unabhängig laufen soll, wählst du
**Frei (nicht taktgebunden)**.

### Ans Tempo koppeln (Programmer / Virtuelle Konsole / BPM)

Die dauerhafte Grundkonfiguration stellst du direkt im **Programmer-Matrix-Editor** ein.
Die Virtuelle Konsole dient anschließend zum Live-Umschalten der Faktoren:

- **Effekt per Smart-Drop** auf eine VC-Seite ziehen → im geführten Dialog für musik-synchrones
  Tempo **„Tempo-Multiplikator (×½ ×2)…"** wählen (erzeugt ein Speed-Rad im Multiplier-Modus).
  „Tempo (Geschwindigkeit)" stellt dagegen die *Geschwindigkeit* — mit derselben Einschränkung
  wie oben.
- Ein **SpeedDial** kann als **Tempo-Bus**-Steller, als **Effekt ×½/×2 (Multiplier)** oder als
  **Speed-Knoten (Master/Sub)** arbeiten — hier liegen die Faktoren ¼ ½ 1× 2× 4× und das
  Tap-Tempo.
- Das Element **Tempo-Bus** (Werkzeugleiste der VC; Einstellungsfenster „Bus-Auswahl") schaltet
  mit einem Tipp den aktiven Bus scharf; **Buttons** mit den Aktionen **„Tap-Tempo (Bus)"**,
  **„Sync (Bus)"** bzw. **„Bus scharf schalten"** geben Tap-Tempo, gleichen die Phase an bzw.
  schalten einen Bus scharf.
- Die **Bus-Auswahl** im SpeedDial-/Slider-Dialog bietet *(aktiver/Default-Bus)*, **Bus A**,
  **Bus B**, **Bus C** und **Bus D**; die **BPM-Anzeige** nennt den Leerwert (globaler Leader)
  **Global (Leader)**. Das Element **Tempo-Bus** zeigt dagegen die Buses aus seinem
  Eigenschaften-Dialog (Feld **Buses:** als Komma-Liste, z. B. `A, B, C, D`).
- Der **Default-/Leader-Bus** spiegelt die **Master-/Sound-BPM** (`bpm_global`), die der **Musik**
  folgt: legst du Farb- und Dimmer-Matrix auf den Default-Bus, laufen beide automatisch im
  Lied-Tempo (siehe Anleitung *Musik-Sync*).

![SpeedDial und Tempo-Bus in der Virtuellen Konsole](img/02_vc_tempo_bus.png)

## 4. Ergebnis

So sieht ein Dimmer-Layer (hier grün-weiß, atmend) über den Geräten aus:

![Dimmer-Layer (atmend)](gif/layering_gruenweiss_atmen.gif)

Im Hardstyle-Look kombiniert: blauer Farb-Chase + schnellerer Dimmer-Puls, per VC auf den
**Default-/Leader-Bus** gelegt und damit musik-synchron — zu sehen in der laufenden Show
(siehe *Virtuelle Konsole*, GIF „Hardstyle-Show läuft").

## 5. Modify-Effekt: auf laufende Effekte addieren, abziehen, abdunkeln

Ein normaler Dimmer-Effekt **setzt** die Helligkeit seiner Lampen — läuft ein zweiter darüber,
gewinnt der zuletzt gestartete. Ein **Modify-Effekt** setzt nichts: er wird mit dem **verrechnet**,
was darunter gerade läuft. Beispiel: Im Hintergrund funkelt es die ganze Zeit; ein Modify-Lauflicht
legt auf zwei Lampen 100 % obendrauf, wandert weiter — und die Lampen dahinter funkeln wieder
ganz normal.

### Einrichten

1. Matrix wie in Abschnitt 2 anlegen: **Stil Dimmer**, Algorithmus z. B. *Chase*, Lampen zuweisen.
2. Unter **Stil** den Haken **Modify-Effekt** setzen. Darunter erscheint die Gruppe **Modify** mit
   **Betriebsart** (Addieren / Abziehen / Abdunkeln) und **Stärke** (0–100 %, Vorgabe 100 %).
   Haken raus = wieder ein ganz normaler Effekt; Betriebsart und Stärke bleiben gemerkt.
3. **💾 Speichern** und den Effekt auf eine normale Taste der Virtuellen Konsole legen:
   Taste an = der Modify-Effekt wirkt, Taste aus = alles läuft wie vorher weiter.
4. Wer mag, legt einen Regler auf den Effekt-Parameter **Modify-Stärke**. Der Regler
   **Helligkeit** des Modify-Effekts und seine Ein-/Ausblendzeit wirken ebenfalls nur auf die
   Stärke — das Darunterliegende wird davon nie mitgedimmt.

### Die drei Betriebsarten

| Betriebsart | Rechnung je Lampe | Lampe im Modify-Effekt gerade nicht dran |
|---|---|---|
| **Addieren** | unten + Betrag × Stärke | bleibt unverändert |
| **Abziehen** | unten − Betrag × Stärke | bleibt unverändert |
| **Abdunkeln** | unten × (1 − Betrag × Stärke) | bleibt unverändert |

**Betrag** ist das, was der Modify-Effekt für die Lampe ausrechnet (Läufer an = 100 %, aus = 0 %,
ein Schweif liegt dazwischen). Gekappt wird bei 0 % und 100 %. *Abdunkeln* heißt „um so viel
Prozent dunkler" — 50 % halbiert die Helligkeit, egal wie hell es darunter gerade ist. Das ist der
Unterschied zu *Abziehen*, das einen festen Betrag wegnimmt.

### Durchgerechnet

Darunter steht ein Dimmer-Effekt gerade auf 40 %. Das Modify-Lauflicht hat zwei Läufer auf acht
Lampen, im Moment auf Lampe 3 und 7:

| Lampe | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Effekt darunter | 40 | 40 | 40 | 40 | 40 | 40 | 40 | 40 |
| Modify-Lauflicht (Betrag) | 0 | 0 | 100 | 0 | 0 | 0 | 100 | 0 |
| Addieren, Stärke 100 % | 40 | 40 | 100 | 40 | 40 | 40 | 100 | 40 |
| Abziehen, Stärke 100 % | 40 | 40 | 0 | 40 | 40 | 40 | 0 | 40 |
| Abdunkeln, Stärke 100 % | 40 | 40 | 0 | 40 | 40 | 40 | 0 | 40 |
| Addieren, Stärke 50 % | 40 | 40 | 90 | 40 | 40 | 40 | 90 | 40 |
| Abziehen, Stärke 50 % | 40 | 40 | 0 | 40 | 40 | 40 | 0 | 40 |
| Abdunkeln, Stärke 50 % | 40 | 40 | 20 | 40 | 40 | 40 | 20 | 40 |

(40 + 100 = 140 → gekappt auf 100. 40 − 50 = −10 → gekappt auf 0.) Im nächsten Schritt stehen die
Läufer auf Lampe 4 und 8 — Lampe 3 und 7 sind dann wieder exakt bei den 40 % des Effekts darunter.

### Reihenfolge

- Ein Modify-Effekt rechnet immer **nach** den normalen Effekten seiner **Layer-Priorität** und
  aller niedrigeren — egal, was zuerst gestartet wurde.
- Mehrere Modify-Effekte wirken **nacheinander in Start-Reihenfolge**, jeder kappt für sich.
  Beispiel auf 40 %: erst Addieren 50 %, dann Abziehen 100 % ergibt 0 %; umgekehrt gestartet
  ergibt es 50 %.
- Ein normaler Effekt mit **höherer** Priorität überschreibt alles darunter, auch das Verrechnete.

### Grenzen (Stand Schritt 1)

- Modify gibt es bisher nur im **Stil Dimmer**. Bei RGB, RGBW und Shutter ist der Haken gesperrt;
  ein dort noch gesetzter Haken hat keine Wirkung. Farbe und Dimmer bleiben getrennt — ein
  Dimmer-Modify fasst nie eine Farbe an.
- Verrechnet wird mit **laufenden Effekten**. **Snap-Tasten, Programmer und Cuelisten** liegen in
  LightOS darüber und werden nicht verrechnet.
- **Addieren ohne Effekt darunter** arbeitet auf 0 und sieht aus wie ein normaler Dimmer-Effekt.
  Ihm gehört dann der Dimmer der Lampe; ein Programmer- oder Snap-Dimmer zählt währenddessen
  nicht — genau wie bei jedem anderen Dimmer-Effekt.
- **Abziehen und Abdunkeln ohne Effekt darunter** tun nichts. Sie greifen nur dort, wo ein Effekt
  den Dimmer gerade treibt; Grundwerte, Snaps und Programmer-Helligkeit werden nie abgedunkelt.
- Steht **Dimmer-Bereich Min** im Modify-Effekt über 0, bekommt **jede** Lampe diesen Grundbetrag
  ab (der Editor weist darauf hin).
- Als **Chaser-Schritt** läuft ein Modify-Effekt wie ein normaler Effekt. In einer Collection wird
  er mit dem verrechnet, was bis dahin geschrieben ist (also auch mit den Effekten, die in der
  Collection vor ihm stehen).
- Die Vorschau im Editor zeigt den Modify-Effekt allein, eingefärbt nach Betriebsart
  (Bernstein = Addieren, Blau = Abziehen, schraffiert = Abdunkeln).

### Noch aufzunehmende Bilder

Für diesen Abschnitt gibt es noch keine Bilder. Aufzunehmen sind:

1. Matrix-Editor, Stil Dimmer, Haken **Modify-Effekt** aus.
2. Matrix-Editor mit gesetztem Haken und der Gruppe **Modify**.
3. Lampenreihe: Effekt darunter allein / Modify-Lauflicht allein / Ergebnis mit Addieren.
4. Dieselbe Reihe mit Abziehen und Abdunkeln nebeneinander.
5. Virtuelle Konsole: Taste für den Modify-Effekt und Regler **Modify-Stärke**.
6. Kurzes GIF: Taste an/aus über einem laufenden Funkeln.

---

**Kurz:** Gruppe wählen → Matrix-Tab → **+ Neu** → **Stil Dimmer** + Algorithmus *Chase* (Raster
folgt der Auswahl) → Helligkeit über **Dimmer-Bereich** (Min/Max) → **💾 Speichern** →
**▶ Start**. Tempo: neue Matrizen hängen am Bus **Global** (folgt der Musik-BPM); schneller als
die Farb-Matrix wird der Puls über **Tempo ×** — **Geschwindigkeit** wirkt nur ohne laufende BPM.
Live umschalten in der **Virtuellen Konsole** (Speed-Rad, Element **Tempo-Bus**, Buttons
„Tap-Tempo (Bus)" / „Sync (Bus)" / „Bus scharf schalten"). Farbe und Helligkeit bleiben
getrennte, kombinierbare Ebenen.
