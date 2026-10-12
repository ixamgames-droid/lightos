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
> **Dimmer-Bereich** (Feld **Max**) fest, wie hell der Läufer wird — außer wenn
> **„Dimmer pro Runde wechseln"** aktiv ist: dann gilt die Dimmerwert-Folge, das Feld ist
> ausgeblendet. Was die Lampen **ohne** Läufer tun, stellst du in der Gruppe **Untergrund**
> ein (Abschnitt 4) — dorthin ist das frühere Feld **Min** gewandert.

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

## 4. Untergrund: was die anderen Lampen tun

Beim Lauflicht stehen die Lampen, auf denen gerade kein Läufer liegt, normalerweise auf 0.
In der Gruppe **Untergrund** (nur bei **Stil: Dimmer**, unter der Gruppe **Farben**) legst du
fest, was sie stattdessen tun. Der Untergrund wirkt **nur auf den Dimmer** — die Farbe kommt
weiter von deinem getrennten Farb-Effekt und wird nie angefasst.

| **Art:** | Was passiert | Felder |
|---|---|---|
| **Aus** | Wie bisher: Lampen ohne Läufer sind dunkel. | – |
| **Fester Wert** | Lampen ohne Läufer stehen auf einer festen Helligkeit. | **Helligkeit** (in %) |
| **Atmen** | Lampen ohne Läufer pulsieren gemeinsam weich zwischen **Tiefpunkt** und **Helligkeit**. | **Helligkeit**, **Tiefpunkt**, **Tempo ×** |

- Der **Läufer** bleibt, wie er ist; seine Helligkeit bestimmt weiter **Dimmer-Bereich → Max**.
- Der **Schweif** blendet auf den Untergrund aus, nicht mehr auf 0.
- **Atmen** läuft mit dem Tempo des Effekts: bei **Tempo × = 1** dauert ein Atemzug vier
  Schritte, am Tempo-Bus also einen Takt; **2** ist doppelt so schnell, **0,5** halb so
  schnell. Der Faktor gilt zusätzlich zum **Tempo ×** des Effekts in **Tempo & Blende**.
- Der Untergrund gilt für alle Dimmer-Algorithmen (Chase, Wipe, Wave, Random …) und auch bei
  **„Dimmer pro Runde wechseln"** — dort musst du die Art einmal ausdrücklich wählen.
- Der Fader **Helligkeit** des Effekts, Gruppen-Fader und Master dimmen Läufer und Untergrund
  gemeinsam. Stoppst du den Effekt, ist auch der Untergrund aus.
- **Invertieren** dreht das Bild um: dann ist der Läufer die Stelle, die auf dem Untergrund
  steht.
- In der **Virtuellen Konsole** ist die Helligkeit des Untergrunds der Effekt-Parameter
  **„Dimmer min"** (Regler 20 % = Untergrund 20 %). Beim Atmen kommen **„Untergrund Tempo ×"**
  und **„Untergrund Tiefpunkt"** dazu.
- Bei Geräten mit mehreren Köpfen und **einem gemeinsamen Dimmer** zählt der hellste Kopf:
  liegt ein Läufer auf einem der Köpfe, ist das ganze Gerät hell, sonst steht es auf dem
  Untergrund.

**Alte Shows** bleiben, wie sie sind: ein früher eingetragenes **Min** über 0 erscheint als
**Fester Wert** mit der passenden Prozentzahl.

> **Bilder folgen.** Für diesen Abschnitt sind noch aufzunehmen: (1) Editor mit Gruppe
> **Untergrund**, Art **Fester Wert**; (2) Vorschau vorher/nachher — Läufer auf Schwarz gegen
> Läufer auf 20 %; (3) bewegtes Bild **Atmen** mit Läufer und Schweif; (4) Virtuelle Konsole:
> Taste plus Regler **„Dimmer min"**.

## 5. Ergebnis

So sieht ein Dimmer-Layer (hier grün-weiß, atmend) über den Geräten aus:

![Dimmer-Layer (atmend)](gif/layering_gruenweiss_atmen.gif)

Im Hardstyle-Look kombiniert: blauer Farb-Chase + schnellerer Dimmer-Puls, per VC auf den
**Default-/Leader-Bus** gelegt und damit musik-synchron — zu sehen in der laufenden Show
(siehe *Virtuelle Konsole*, GIF „Hardstyle-Show läuft").

---

**Kurz:** Gruppe wählen → Matrix-Tab → **+ Neu** → **Stil Dimmer** + Algorithmus *Chase* (Raster
folgt der Auswahl) → Läufer-Helligkeit über **Dimmer-Bereich** (Max), die übrigen Lampen über
**Untergrund** → **💾 Speichern** →
**▶ Start**. Tempo: neue Matrizen hängen am Bus **Global** (folgt der Musik-BPM); schneller als
die Farb-Matrix wird der Puls über **Tempo ×** — **Geschwindigkeit** wirkt nur ohne laufende BPM.
Live umschalten in der **Virtuellen Konsole** (Speed-Rad, Element **Tempo-Bus**, Buttons
„Tap-Tempo (Bus)" / „Sync (Bus)" / „Bus scharf schalten"). Farbe und Helligkeit bleiben
getrennte, kombinierbare Ebenen.
