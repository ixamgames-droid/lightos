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
- **Spalten/Reihen** musst du nicht von Hand setzen: Die mit **+ Neu** angelegte Matrix nimmt
  die **Programmer-Auswahl** und folgt ihr, bis du sie speicherst. Daraus ergibt sich das
  Geräte-Grid von selbst — bei loser Auswahl als **Spalten = Anzahl der Geräte**
  (hier 10 = PAR + Spider), **Reihen = 1**. Eine schon gespeicherte Matrix ändert ihr Raster
  nur über **Auswahl übernehmen**.
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
(diese drei nur bei gewähltem Bus), **Stufe**, **Einblenden**, **Ausblenden** und
**Hüllkurven-Form**.

- **Geschwindigkeit** ist die eigene Rate der Matrix (Schritte pro Sekunde). Sie wirkt nur im
  **Frei-Lauf** — Tempo-Bus *Frei* — bzw. solange der gewählte Bus noch keine BPM hat. Läuft
  eine BPM (Tap oder Musik), bestimmt **Tempo ×** das Tempo: für einen doppelt so schnellen
  Dimmer-Puls also bei der Dimmer-Matrix **Tempo × = 2** einstellen, die Farb-Matrix bleibt
  auf 1.
- Mit der **Stufe** entscheidest du, wer gewinnt, wenn zwei Effekte denselben Kanal
  schreiben (die höhere Stufe gewinnt; bei gleicher Stufe der zuletzt gestartete Effekt).
  Alle Stufen und die ganze Reihenfolge: [Wer gewinnt?](../anleitung_prioritaeten/ANLEITUNG.md).
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
was die Lampe gerade tut. Beispiel: Im Hintergrund funkelt es die ganze Zeit; ein Modify-Lauflicht
legt auf zwei Lampen 100 % obendrauf, wandert weiter — und die Lampen dahinter funkeln wieder
ganz normal.

**Die Regel in einem Satz:** Modify rechnet auf das **fertige Bild** — auf das, was Effekte,
Cuelisten, Snap-Tasten, Programmer und die automatische Grundhelligkeit zusammen ergeben — und
**vor** den Mastern. Wo der Modify-Effekt gerade nichts ausgibt, bleibt alles unverändert.

### Einrichten

1. Matrix wie in Abschnitt 2 anlegen: **Stil Dimmer**, Algorithmus z. B. *Chase*, Lampen zuweisen.
   (Für Farbe statt Helligkeit: **Stil RGB** oder **RGBW** — siehe „Modify im Stil Farbe“ weiter
   unten.)
2. Unter **Stil** den Haken **Modify-Effekt** setzen. Darunter erscheint die Gruppe **Modify** mit
   **Betriebsart** (Addieren / Abziehen / Abdunkeln) und **Stärke** (0–100 %, Vorgabe 100 %).
   Haken raus = wieder ein ganz normaler Effekt; Betriebsart und Stärke bleiben gemerkt.
3. **💾 Speichern** und den Effekt auf eine normale Taste der Virtuellen Konsole legen:
   Taste an = der Modify-Effekt wirkt, Taste aus = alles läuft wie vorher weiter.
4. Wer mag, legt einen Regler auf den Effekt-Parameter **Modify-Stärke**. Der Regler
   **Helligkeit** des Modify-Effekts und seine Ein-/Ausblendzeit wirken ebenfalls nur auf die
   Stärke — das Darunterliegende wird davon nie mitgedimmt.

### Nur per Fader bedienen

Ein Modify-Effekt braucht keine Taste. Ein Fader der Virtuellen Konsole kann ihn allein schalten
und regeln: **Fader auf 0 = Effekt aus, Fader irgendwo darüber = Effekt läuft.**

1. In der Virtuellen Konsole einen **Fader anlegen** und in seinen Eigenschaften als Ziel den
   Modify-Effekt wählen.
2. Als **Modus** *Effekt-Helligkeit* einstellen.
3. Den Haken **„Effekt An/Aus (EFFECT-Modi): bei 0 wirklich stoppen“** setzen.

Was man sieht (Untergrund auf 40 %, Werte der Läufer-Lampen):

| Fader | Effekt | Abziehen | Abdunkeln | Addieren |
|---|---|---|---|---|
| 0 | gestoppt — das Bild ist exakt wie ohne den Effekt | 40 % | 40 % | 40 % |
| 50 % | läuft, halbe Stärke | 0 % | 20 % | 90 % |
| 100 % | läuft, volle Stärke | 0 % | 0 % | 100 % |

- Schon der **kleinste Wert über 0** startet den Effekt; zurück auf 0 stoppt ihn wirklich.
- **Ohne den Haken** regelt der Fader nur: an und aus bleibt dann bei der Taste, und Fader 0 heißt
  „läuft mit Stärke 0“.
- **Taste und Fader zusammen** auf demselben Effekt vertragen sich: die Taste leuchtet, sobald der
  Fader den Effekt startet, und geht aus, wenn er ihn stoppt. Schaltet die Taste bei offenem Fader
  aus, startet die nächste Fader-Bewegung wieder.
- Statt *Effekt-Helligkeit* geht auch der Modus *Effekt-Parameter* mit **Modify-Stärke** — gleiches
  Ergebnis, in ganzen Prozent. *Effekt-Tempo* mit dem Haken schaltet ebenfalls, regelt aber das
  Tempo.
- **Ein- und Ausblendzeit** des Effekts gelten auch beim Start und Stopp über den Fader; der
  Untergrund springt dabei nie. Im Modus *Effekt-Helligkeit* ist der Effekt bei Fader 0 sofort
  unsichtbar (Stärke 0); die Taste leuchtet noch für die Dauer der Ausblendzeit. Wer den Fader in
  dieser Zeit wieder aufzieht, startet den Effekt neu.
- **Show laden:** Ein gespeicherter Faderwert über 0 startet nichts. Nach dem Laden ist der Effekt
  aus, der Fader zeigt nur seinen gespeicherten Stand; **erst die erste Bewegung** des Faders
  schaltet ein. So verhält sich jeder Effekt-Fader, nicht nur bei Modify.
- **Bankwechsel mit Pickup:** Der Hardware-Fader wirkt erst, wenn er den angezeigten Wert kreuzt —
  vorher wird nichts gestartet und nichts gestoppt.

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

### Zwei Lampen, dann die nächsten zwei: Schrittweite

Beim Lauflicht (*Chase*) gibt es drei Stellschrauben, die leicht verwechselt werden:

- **Läufer-Anzahl** 2 = zwei Läufer, die auf acht Lampen vier Lampen auseinander stehen (1 + 5,
  dann 2 + 6 …).
- **Läufer-Breite** 2 = ein Läufer, zwei Lampen breit. Er wandert trotzdem nur um **eine** Lampe.
- **Schrittweite** = um wie viele Lampen der Läufer je Schritt weiterspringt. Vorgabe 1 (Lampe für
  Lampe, wie bisher). Auf **„wie Breite“** gestellt (im Feld der Wert unter 1) springt er Block an
  Block.

Für „erst Lampe 1 + 2, dann 3 + 4, dann 5 + 6“ also: **Läufer-Anzahl 1, Läufer-Breite 2,
Schrittweite „wie Breite“** (oder 2), **Schweif 0 %**. Als Modify-Effekt *Addieren* mit Stärke
100 % über einem Funkeln, das gerade auf 40 % steht:

| Lampe | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Schritt 1 | 100 | 100 | 40 | 40 | 40 | 40 | 40 | 40 |
| Schritt 2 | 40 | 40 | 100 | 100 | 40 | 40 | 40 | 40 |
| Schritt 3 | 40 | 40 | 40 | 40 | 100 | 100 | 40 | 40 |
| Schritt 4 | 40 | 40 | 40 | 40 | 40 | 40 | 100 | 100 |

Danach beginnt es wieder bei Lampe 1 + 2. Die Schrittweite gibt es bei **jedem** Lauflicht, nicht
nur bei Modify-Effekten; das Feld steht unter **Bewegung & Parameter**, an der Virtuellen Konsole
heißt der Parameter **Schrittweite**. So spielt sie mit den anderen Einstellungen zusammen:

- Zwischen zwei Schritten steht der Läufer still (bei Schrittweite 1 gleitet ein Schweif weich
  mit, ab Schrittweite 2 springt alles im Takt).
- **Rückwärts:** dieselben Blöcke in umgekehrter Folge — 1 + 2, dann 7 + 8, 5 + 6, 3 + 4.
- **Ping-Pong:** die Blöcke hin und zurück — 1 + 2, 3 + 4, 5 + 6, 7 + 8, 5 + 6, 3 + 4 … Am Rand
  wird ein Block abgeschnitten, er läuft nicht um.
- **Mehrere Läufer:** jeder weitere um „Lampenzahl ÷ Anzahl“ versetzt, alle springen gemeinsam.
- **Schweif:** hängt hinter dem Block über den eben verlassenen Lampen und springt mit. Ist die
  Schrittweite größer als die Breite, liegen auch die übersprungenen Lampen im Schweif.
- Geht die Lampenzahl nicht auf (acht Lampen, Schrittweite 3), beginnt jede Runde wieder bei
  Lampe 1: 1, 4, 7, dann wieder 1.
- Bei den Ring-Bewegungen (von der Mitte nach außen und umgekehrt) wirkt die Schrittweite nicht;
  das Feld ist dort ausgeblendet.

### Modify im Stil Farbe (RGB / RGBW)

Derselbe Haken **Modify-Effekt** gibt es auch bei den Stilen **RGB** und **RGBW**. Dann wird nicht
die Helligkeit verrechnet, sondern die **Farbe** — und zwar **jeder Farbkanal einzeln**: Rot mit
Rot, Grün mit Grün, Blau mit Blau, bei RGBW zusätzlich Weiß mit Weiß. Betriebsart und Stärke
bedeuten dasselbe wie beim Dimmer; der **Betrag** ist die Farbe, die der Modify-Effekt für die
Lampe ausrechnet.

Einrichten wie oben, nur mit **Stil RGB** (oder RGBW) und einer Farbe: z. B. ein rotes Lauflicht
als *Addieren* über einem blauen Hintergrund — unter dem Läufer wird es Magenta, dahinter wieder
Blau.

Durchgerechnet für eine Lampe, die gerade **Rot 200, Grün 100, Blau 50** zeigt (Werte 0–255);
der Modify-Effekt hat an dieser Lampe die Farbe **Rot 100, Grün 200, Blau 0**:

| | Rot | Grün | Blau |
|---|---|---|---|
| darunter | 200 | 100 | 50 |
| Modify-Effekt (Betrag) | 100 | 200 | 0 |
| **Addieren**, Stärke 100 % | 255 | 255 | 50 |
| **Abziehen**, Stärke 100 % | 100 | 0 | 50 |
| **Abdunkeln**, Stärke 100 % | 122 | 22 | 50 |
| Addieren, Stärke 50 % | 250 | 200 | 50 |
| Abziehen, Stärke 50 % | 150 | 0 | 50 |
| Abdunkeln, Stärke 50 % | 161 | 61 | 50 |

- **Gekappt wird je Farbkanal einzeln** bei 0 und 255. Der Farbton kann dabei kippen: Orange
  plus Rot ergibt volles Rot mit unverändertem Grün. Blau bleibt im Beispiel stehen, weil der
  Modify-Effekt dort den Betrag 0 hat.
- **Der Dimmer wird nie angefasst.** Farbe und Dimmer bleiben getrennt: ein Farb-Modify schreibt
  keinen Dimmer und zieht keinen auf. **Eine dunkle Lampe bleibt dunkel** — wer mit einem
  Farb-Modify Licht sehen will, braucht darunter etwas, das die Lampe hell macht (Dimmer-Effekt,
  Dimmer-Taste oder eine Farbe, die über die automatische Grundhelligkeit leuchtet).
- **Automatische Grundhelligkeit:** Ein Farb-Modify löst sie nicht aus und nimmt sie nicht zurück.
  Leuchtet eine Lampe nur wegen ihrer Farbe (Farb-Taste, kein Dimmer) und zieht ein Farb-Modify
  diese Farbe ganz ab, bleibt der Dimmer offen — die Lampe ist dann dunkel, weil keine Farbe mehr
  da ist, nicht weil der Dimmer zu wäre.
- **RGBW:** Im Stil RGBW läuft der Weißanteil der Modify-Farbe über den **Weiß-Kanal**. Reines Weiß
  verrechnet also nur den Weiß-Kanal; Rot, Grün und Blau der Lampe bleiben stehen. Eine Mischfarbe
  teilt sich auf (Rot 255, Grün 128, Blau 128 = Weiß 128 und Rot 127). Im Stil RGB bleibt der
  Weiß-Kanal unberührt.
- **Lampen ohne Farbkanäle** (nur Farbrad) bleiben unberührt — eine Rad-Stellung ist keine Menge,
  die sich addieren ließe. Amber-, UV- und CMY-Kanäle fasst die Matrix als normaler Effekt nicht
  an, als Modify mit der Vorgabe also auch nicht. Amber und UV lassen sich über **Wirkt auf**
  (nächster Abschnitt) ausdrücklich ankreuzen.
- **Dimmer- und Farb-Modify zusammen:** beide können gleichzeitig laufen. Jeder rechnet nur auf
  seinen Kanälen, die Reihenfolge ist dieselbe wie unter „Reihenfolge“.
- **Master haben das letzte Wort** — wie beim Dimmer-Modify. Bei Lampen ohne eigenen Dimmer (reine
  RGB-Geräte) dimmen Fader, Grand Master und Blackout die verrechnete Farbe.
- Der Regler **Helligkeit** des Farb-Modify stellt wie beim Dimmer nur die Stärke ein.
- Die Vorschau im Editor zeigt beim Farb-Modify die echten Farben; das Zeichen in der Ecke nennt
  die Betriebsart (+ Addieren, − Abziehen, × Abdunkeln, dann schraffiert).

### Nur bestimmte Kanäle verändern: „Wirkt auf“

In der Gruppe **Modify** steht bei den Stilen **RGB** und **RGBW** die Zeile **Wirkt auf**.

- **Kanäle der Modify-Farbe** (Vorgabe, Haken gesetzt): alles wie oben beschrieben — die Farbe des
  Modify-Effekts bestimmt, welche Farbkanäle er verändert. Shows von vorher verhalten sich
  unverändert.
- Darunter lassen sich **Rot, Grün, Blau, Weiß, Amber** und **UV** einzeln ankreuzen. Dann
  verändert der Modify-Effekt **nur diese Kanäle** — mit der eingestellten Betriebsart und Stärke.
  Alle anderen Kanäle bleiben stehen.
- Der **Betrag** ist dann die **Helligkeit** des Effekts an der Lampe (Läufer an = 100 %, aus = 0 %,
  ein Schweif liegt dazwischen). Der **Farbton** des Effekts zählt nicht mehr: ein rotes und ein
  weißes Lauflicht tun bei „nur Weiß“ dasselbe. Eine halb helle Farbe gibt den halben Betrag.
- **Lampen ohne einen angekreuzten Kanal bleiben unberührt.** Es wird nichts umgerechnet: „nur
  Weiß“ tut an einem RGB-Strahler ohne Weiß-Kanal nichts, es wird nicht auf Rot, Grün und Blau
  verteilt.
- Der Haken **Kanäle der Modify-Farbe** setzt die Auswahl zurück. Wird der letzte Kanal
  abgewählt, steht er von selbst wieder.
- **Der Dimmer steht nicht in der Auswahl.** Farbe und Dimmer bleiben getrennt: „nur den Dimmer“
  verrechnet ein Modify-Effekt im **Stil Dimmer** (siehe oben). Im Stil Dimmer gibt es die Zeile
  nicht; eine dort gemerkte Auswahl wirkt nicht.

Durchgerechnet für eine RGBW-Lampe, die gerade **Rot 30, Grün 60, Blau 250, Weiß 180** zeigt, der
Dimmer steht auf 77 (Werte 0–255). Der Modify-Effekt ist an dieser Lampe voll an:

| | Dimmer | Rot | Grün | Blau | Weiß |
|---|---|---|---|---|---|
| darunter | 77 | 30 | 60 | 250 | 180 |
| nur Weiß, **Abziehen**, Stärke 50 % | 77 | 30 | 60 | 250 | 52 |
| nur Weiß, **Abziehen**, Stärke 100 % | 77 | 30 | 60 | 250 | 0 |
| nur Rot, **Addieren**, Stärke 100 % | 77 | 255 | 60 | 250 | 180 |
| nur Rot, **Addieren**, Stärke 40 % | 77 | 132 | 60 | 250 | 180 |
| Rot und Weiß, **Abdunkeln**, Stärke 50 % | 77 | 15 | 60 | 250 | 90 |

- Die Auswahl wird mit dem Effekt gespeichert und beim Kopieren mitgenommen; **Verwerfen** im
  Editor nimmt sie zurück wie jede andere Änderung.
- **Eigene Weiß-Leiste** (Geräte, deren Weiß-Segmente nicht zu den Farb-Zellen gehören): „Weiß“
  verändert dort die Segmente der **Weiß-Zellen** der Matrix, nicht die Farb-Zellen. Ohne „Weiß“
  in der Auswahl bleiben die Segmente stehen.
- **Amber und UV** erreicht ein Modify-Effekt nur über diese Auswahl — als Vorgabe (Modify-Farbe)
  schreibt die Matrix sie nicht.
- Die Vorschau im Editor malt die Lampen in der Mischfarbe der angekreuzten Kanäle; neben dem
  Zeichen der Betriebsart steht z. B. „− nur Weiß“.
- An der Virtuellen Konsole gibt es für die Kanalwahl keinen eigenen Regler; sie wird im Editor
  eingestellt. **Modify-Stärke** und **Modify-Art** wirken wie gewohnt.

### Was mit Snaps, Grundhelligkeit und Mastern gilt

- **Snap-Tasten und Programmer:** Steht der Dimmer über eine Snap-Taste auf 40 %, legt *Addieren*
  unter dem Läufer obendrauf, *Abziehen* und *Abdunkeln* nehmen dort weg — alle anderen Lampen
  bleiben exakt bei 40 %. Dasselbe gilt für Cuelisten.
- **Nur Farbe, kein Dimmer** (Farb-Snap oder Farb-Effekt): die Lampen leuchten über die
  automatische Grundhelligkeit mit 100 %. Ein Modify-Effekt schaltet sie **nicht** ab.
  *Abziehen* und *Abdunkeln* machen die Lampen unter dem Läufer dunkler; *Addieren* sieht man
  dann nicht, weil mehr als 100 % nicht geht.
- **Gar nichts darunter:** *Addieren* rechnet auf 0 — es leuchtet dort, wo der Läufer ist.
  *Abziehen* und *Abdunkeln* tun nichts.
- **Master haben das letzte Wort.** Gruppen-Fader und Submaster, der DMX-Eingang, der Grand Master,
  Blackout, gezielte Blackouts und der Laser-NOT-AUS greifen **nach** dem Modify-Effekt. Ein
  Modify-Effekt kann einen zugezogenen Fader, einen Blackout oder einen NOT-AUS nie aufhellen.
- Ein Modify-Effekt **besitzt** den Dimmer nicht. Ein normaler Dimmer-Effekt übernimmt den Dimmer
  seiner Lampen (ein Snap-Dimmer zählt dann nicht mehr) — ein Modify-Effekt lässt ihn, wo er ist.

### Reihenfolge

- Ein Modify-Effekt rechnet immer **nach** allen normalen Effekten — egal, was zuerst gestartet
  wurde und in welcher **Stufe** sie liegen. Er wirkt also auch auf einen normalen Effekt
  in einer höheren Stufe: verrechnet wird mit dem, was am Ende gewinnt.
- Mehrere Modify-Effekte wirken **nacheinander**, jeder kappt für sich: zuerst nach
  Stufe (die niedrige zuerst), bei gleicher Stufe in **Start-Reihenfolge**.
  Beispiel auf 40 %: erst Addieren 50 %, dann Abziehen 100 % ergibt 0 %; umgekehrt gestartet
  ergibt es 50 %.

### Grenzen

- Modify gibt es im **Stil Dimmer** und in den Farb-Stilen **RGB** und **RGBW**. Beim Stil
  **Shutter** ist der Haken gesperrt (eine Shutter-Stellung ist keine Menge); ein dort noch
  gesetzter Haken hat keine Wirkung. Farbe und Dimmer bleiben getrennt — ein Dimmer-Modify fasst
  nie eine Farbe an, ein Farb-Modify nie den Dimmer.
- Ein Dimmer-Modify wirkt auf die **Dimmer-Kanäle seiner eigenen Lampen**. Lampen ohne
  Dimmer-Kanal (reine RGB-Geräte, deren Helligkeit in der Farbe steckt) erreicht er nicht — dort
  hilft ein Farb-Modify (weißes *Abdunkeln* oder *Abziehen* im Stil RGB).
- Der Regler **Helligkeit** einer Sammlung (Collection) oder Show und ihre Ein-/Ausblendzeit
  stellen bei einem Modify-Effekt darin nur ein, wie kräftig er zugreift — das Darunterliegende
  wird nicht mitgedimmt.
- Als **Chaser-Schritt** ist ein Modify-Effekt gesperrt: der Schritt gibt nichts aus. Ein Chaser
  blendet feste Bilder ineinander; ein Modify-Effekt hätte dort alle Lampen außerhalb des Läufers
  überschrieben. Direkt gestartet, in einer Sammlung und in der Show-Zeitleiste funktioniert er.
- Steht **Dimmer-Bereich Min** im Modify-Effekt über 0, bekommt **jede** Lampe diesen Grundbetrag
  ab (der Editor weist darauf hin).
- **Der Schweif gehört zum Effekt und wird mit verrechnet.** Der Haken **Modify-Effekt** stellt
  ihn nicht um: bei einem Modify-Effekt zieht auch der Schweif die Veränderung nach, die Lampen
  hinter dem Läufer bekommen einen Anteil ab. Die Vorgabe des Lauflichts ist 30 %. Für einen
  scharfen Läufer den **Schweif auf 0 %** stellen — der Hinweis steht auch am Haken und, solange
  er gesetzt ist, am Feld **Schweif (%)**.
- „Alles Weiß“ und die Szenen-Vorschau liegen über dem Modify-Effekt und werden nicht verrechnet.
- Die Vorschau im Editor zeigt den Modify-Effekt allein, im Stil Dimmer eingefärbt nach
  Betriebsart (Bernstein = Addieren, Blau = Abziehen, schraffiert = Abdunkeln).

### Modify oder echter Läufer? „Dunkle Lampen durchlassen“

Modify **ersetzt nichts**, es verrechnet: über 40 % Untergrund macht ein Läufer mit 70 % im
Modus *Addieren* 100 %. Soll der Läufer **genau** 70 % zeigen und der Rest bei 40 % bleiben,
nimm einen **normalen** Dimmer-Effekt (kein Modify) in einer höheren Stufe und setze den Haken
**Dunkle Lampen durchlassen** (unter „Modify-Effekt“, nur im Stil Dimmer). Dann schreibt der
Effekt nur Lampen mit einem Wert über 0 — Schweif-Lampen zählen als hell —, die dunklen bleiben
beim Effekt darunter, bei Cueliste, Snap oder Grundhelligkeit. Einblendzeit und Helligkeit wirken
wie bei jedem Effekt, aber nur auf die hellen Lampen. Steht **Min** über 0, ist keine Lampe dunkel.

### Noch aufzunehmende Bilder

Für diesen Abschnitt gibt es noch keine Bilder. Aufzunehmen sind:

1. Matrix-Editor, Stil Dimmer, Haken **Modify-Effekt** aus.
2. Matrix-Editor mit gesetztem Haken und der Gruppe **Modify**.
3. Lampenreihe: Effekt darunter allein / Modify-Lauflicht allein / Ergebnis mit Addieren.
4. Dieselbe Reihe mit Abziehen und Abdunkeln nebeneinander.
5. Virtuelle Konsole: Taste für den Modify-Effekt und Regler **Modify-Stärke**.
6. Kurzes GIF: Taste an/aus über einem laufenden Funkeln.
7. Matrix-Editor, **Bewegung & Parameter** mit dem Feld **Schrittweite** auf „wie Breite“.
8. Lampenreihe: Farb-Taste und Dimmer-Taste auf 40 %, darüber das Modify-Lauflicht in Zweierblöcken.
9. Matrix-Editor, Stil RGB, Haken **Modify-Effekt** gesetzt, Gruppe **Modify** mit dem Hinweis zum Dimmer.
10. Lampenreihe in Farbe: blauer Hintergrund / rotes Modify-Lauflicht allein / Ergebnis mit Addieren.
11. Gruppe **Modify** mit der Zeile **Wirkt auf**, „Weiß“ angekreuzt, Vorschau mit „− nur Weiß“.

---

**Kurz:** Gruppe wählen → Matrix-Tab → **+ Neu** → **Stil Dimmer** + Algorithmus *Chase* (Raster
kommt aus der Auswahl) → Helligkeit über **Dimmer-Bereich** (Min/Max) → **💾 Speichern** →
**▶ Start**. Tempo: neue Matrizen hängen am Bus **Global** (folgt der Musik-BPM); schneller als
die Farb-Matrix wird der Puls über **Tempo ×** — **Geschwindigkeit** wirkt nur ohne laufende BPM.
Live umschalten in der **Virtuellen Konsole** (Speed-Rad, Element **Tempo-Bus**, Buttons
„Tap-Tempo (Bus)" / „Sync (Bus)" / „Bus scharf schalten"). Farbe und Helligkeit bleiben
getrennte, kombinierbare Ebenen.
