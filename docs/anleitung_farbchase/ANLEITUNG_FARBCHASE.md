# Anleitung: Farbchase frei zusammenstellen (z. B. Blau-Weiß)

> Ziel: ein **Farb-Chase**, dessen **Farbfolge du frei wählst** —
> z. B. *Blau-Weiß*, *Grün-Rot-Blau* oder *Grün-Weiß-Blau* — der über deine Geräte läuft.
> Gebaut **ohne Generator**, komplett in der Oberfläche. Genutzt wird die vorhandene
> **RGB-Matrix** mit dem Algorithmus **Chase**.
>
> **Beispiel-Show:** `shows/Testshow_2026.lshow` (nicht im Repository). Erzeugen mit
> `./venv/bin/python tools/build_testshow_2026.py` (Windows:
> `venv\Scripts\python.exe tools\build_testshow_2026.py`). Dort gibt es die Gruppe
> „Farb-Matrix" (8 PAR + 2 Spider) aus Schritt 1.

So sieht das Ergebnis aus (Blau-Weiß, läuft über die 10 Farb-Geräte):

![Blau-Weiß-Chase](gif/farbchase_blau_weiss.gif)

---

## 1. Geräte auswählen

Wechsle in die Sektion **Programmer** und wähle links unter **Gruppen** die Gruppe, über die
der Chase laufen soll — hier **„Farb-Matrix (10)"** (8 PAR + 2 Spider).
Oben erscheint „**10 Gerät(e): …**".

> **Tipp:** Ein Klick auf die Gruppe springt automatisch in den Tab **Matrix** und
> übernimmt die Geräte. Du musst den Tab also nicht von Hand öffnen.

## 2. Matrix mit Algorithmus „Chase"

Du bist nach dem Gruppen-Klick bereits im Tab **Matrix**. Wähle eine Matrix (oder lege mit
**+ Neu** eine an) und stelle in **Grundeinstellungen** ein:

- **Algorithmus: Chase**
- **Stil: RGB** (bei Spider/RGBW-PAR auch RGBW)

Die eingebettete Matrix **folgt automatisch der Programmer-Auswahl** (Überschrift „Geräte
(folgen der Programmer-Auswahl)") und setzt **Spalten** und **Reihen** aus der Gruppen-Definition
selbst — du siehst z. B. „**1×10 = 10 Fixtures, 0 Lücken (Gruppe »Farb-Matrix«)**". Ein manuelles Setzen
von **Spalten/Reihen** ist daher meist unnötig und wird beim nächsten Auswahl-Sync ohnehin wieder
überschrieben.

> **Bleibt es dunkel?** Eine **neu angelegte** Matrix setzt nur die **Farbe**, nicht den
> Dimmer. Geräte, deren Dimmer auf 0 steht, bleiben dann schwarz. Abhilfe: im Menü
> **Programmer → „Farbe macht automatisch hell"** einschalten oder eine Dimmer-Ebene
> (Dimmer-Matrix, Fader) dazulegen. Die Beispiel-Show oben stellt die Dimmer der
> Farb-Geräte schon auf voll, dort fällt das nicht auf.

![Matrix-Editor mit Chase/RGB](img/01_matrix_chase.png)

## 3. „Farbe pro Runde wechseln" aktivieren

Scrolle zur Gruppe **Farben** und setze den Haken bei
**„Farbe pro Runde wechseln"**. Erst dadurch nutzt der Chase eine **ganze Farbfolge**
(statt nur einer Einzelfarbe) — und der Farbfolgen-Editor wird sichtbar.

![Farbe pro Runde wechseln](img/02_farbe_pro_runde.png)

## 4. Farbfolge zusammenstellen

In der Gruppe **Farben** steht jetzt **„Color Sequence"**. Klick auf **🎨 Bearbeiten…** — der
Farbfolgen-Editor öffnet sich in einem eigenen Fenster. Oben steht die Kurz-Legende
„**＋ hinzufügen · ✎ ändern · ✕ entfernen · ⊘ aktiv/inaktiv · ◀▶ umsortieren**". Die Aktionen sind
kleine Icon-Buttons unter der Farbliste — von links nach rechts in dieser Reihenfolge
(die Legende oben listet sie nicht in der Anordnungs-Reihenfolge):

- **＋** — Farbe **hinzufügen**,
- **✕** — ausgewählte Farbe **entfernen**,
- **✎** — ausgewählte Farbe **ändern**; öffnet den Farbwähler (exakte Farbe per HTML-Feld, z. B. `#0000ff` = Blau, `#ffffff` = Weiß),
- **⊘** — ausgewählte Farbe **aktiv/inaktiv** schalten (inaktive Einträge zeigt die Liste mit „**(aus)**" und werden im Chase übersprungen),
- **◀ / ▶** — ausgewählte Farbe **umsortieren** (nach links/rechts).

Für *Blau-Weiß* genügen zwei Einträge: **RGB 0,0,255** und **RGB 255,255,255**. Für andere Looks
einfach mehr Farben (z. B. Grün-Rot-Blau).

![Farbfolge Blau-Weiß](img/03_sequenz_blau_weiss.png)

## 5. Speichern & starten

Klick oben rechts im Editor auf **💾 Speichern** (committet die Matrix — „Zurücksetzen"/„Speichern"
werden ausgegraut = gesichert). Mit **▶ Start** läuft der gespeicherte Chase auf den Geräten.
Die **Vorschau** zeigt den aktuellen Entwurf schon vorher, immer im Tempo aus
„Geschwindigkeit".

![Chase läuft](img/04_chase_laeuft.png)

## 6. Tempo & Musik

- Neue Matrizen laufen standardmäßig auf dem Tempo-Bus **„Global (taktgleich, Standard)"**
  (Feld **Tempo-Bus** unter *Tempo & Blende*).
- Solange **keine BPM** läuft, stellt **Geschwindigkeit** die Chase-Rate ein.
- Sobald eine BPM läuft (Tap, Musik), ist **Geschwindigkeit** wirkungslos; dann legt
  **Tempo ×** das Verhältnis zum Takt fest (z. B. 0,5 = halb, 2 = doppelt so schnell). So läuft
  etwa ein Dimmer-Effekt doppelt so schnell wie der Farb-Chase, phasen-gekoppelt — siehe
  Anleitung *Tempo-Sync / relative Geschwindigkeit*.
- Für einen frei laufenden Chase **Tempo-Bus: „Frei (nicht taktgebunden)"** wählen.

---

**Kurz:** Gruppe wählen → Matrix-Tab → Chase/RGB → „Farbe pro Runde wechseln" → Color Sequence
zusammenstellen → Speichern → Start. Die Farbkombination ist damit völlig frei wählbar.
