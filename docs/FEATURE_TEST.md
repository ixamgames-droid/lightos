# Feature-Test-Show — alle Neuerungen 2026-06-12 durchspielen

> **Show:** `shows/Feature_Test.lshow` · **Generator:** `tools/build_feature_test_show.py`
> **Hardware:** Akai APC mini (mk2) + 4× PAR (ZQ01424, 8ch RGBW) + 2× Moving Head (ZQ02001, 11ch)

Eine Test-Show, mit der sich **alle** in dieser Runde gebauten Funktionen gezielt
auf der Hardware ausprobieren lassen. Jede **SCENE-Taste** (rechts am APC) ist
eine Seite mit EINEM Schwerpunkt.

Universell auf jeder Seite:
- **Track-Tasten unten:** Clear · Stop All · Blackout · Tap
- **Fader F6** Dimmer (Submaster) · **F7** Speed global · **F9** Grand Master

---

## Seite 1 — Matrix Builder  (To-Do #3 / #5 / #6)
- **Pad unten links** startet die Builder-Matrix auf den PARs.
- **Form −/+** (Pads 2/3 unten) blättern durch **alle** Matrix-Algorithmen (#3).
- **Richtung · Freeze · Reset · Commit** zum Live-Tunen.
- **Reihe 2 = color1**, **Reihe 3 = color2**, **Reihe 4 = Sequence-Farbe** (#5):
  color1/2 greifen bei Feuer/Plasma/Windrad/Lauflicht, die Sequence-Farbe bei Color-Fade.
- **Rechts:** Feedback-Fenster „Matrix-Farben" — zeigt live die Color-Sequence (#6).
- Fader F1 Speed, F2 Master.

## Seite 2 — Chase bauen  (To-Do #2 — echter Szenen-Chaser, live)
1. Oben eine **Farbe antippen** → legt den Look (Farbe + volle Helligkeit) in den Programmer.
2. **„Schritt+"** (Pad 1 unten) nimmt den aktuellen Programmer als **Schritt** auf.
3. Schritte 1–2 mit anderen Farben wiederholen.
4. **Start** (Pad 4) spielt die aufgenommenen Looks als Chaser ab.
5. **„Letzten −" / „Alle −"** korrigieren, **Clear** leert den Programmer, **Richtung/Ping-Pong** ändern den Ablauf.
- **Rechts:** Feedback zeigt die **Anzahl Schritte**. Fader F1 Tempo.

## Seite 3 — Moving Heads  (To-Do #7 relativ + #8 Feld)
- **LINKS „MH zielen" (XY-Pad):** mit dem Finger die MHs ausrichten (Pan/Tilt live).
- **„Relativ"** einschalten, dann **„MH Acht"** starten → die Acht läuft **relativ um die
  gezielte Position** statt um die feste Mitte (#7). Nach neuem Zielen **„Neustart"** drücken.
- **RECHTS „Feld → Kreis" (XY-Pad):** ein **Rechteck aufziehen** → **„MH Kreis"** fährt
  seinen Kreis in genau diesem Feld (Zentrum + Größe aus dem Feld, #8).

## Seite 4 — Farbe & Kontext  (To-Do #4 + #9)
- **Farb-Kacheln** (oben) färben die PARs (Programmer).
- **Fader F4 „PAR-Dim"** dimmt **fest die PAR-Gruppe** — ohne vorher etwas auszuwählen (#4).
- **„Mtx Regenbogen"** starten → die Farb-Kacheln **grauen aus + zeigen 🔒**, weil der
  Effekt jetzt die Farbe besitzt (#9). Stop All → Kacheln wieder aktiv.

---

*Self-verifizierend: `build_feature_test_show.py` assertet beim Bauen, dass jede
Funktion (capture_step, Form±, Gruppen-Dimmer, Recolor-Kacheln, 2× Feedback-Fenster,
relativ-Toggle, XY-Feld-Pad) in der Show vorhanden ist. Gesamtsuite grün.*
