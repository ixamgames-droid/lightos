# Engine-Zeit je DMX-Frame (ENG-30)

> **Stand: 2026-10-11** · gemessen mit `tools/engine_frame_zeit.py` auf einem Windows-11-Rechner (x64), ohne Fenster, in einer Sandbox.
> Reproduzieren: `venv/Scripts/python.exe tools/engine_frame_zeit.py` (Linux/macOS: `./venv/bin/python`).

LightOS rechnet 44-mal je Sekunde einen DMX-Frame: Funktionen rendern, Programmer und Master anwenden, Masken, senden. Dafür stehen **22,7 ms** zur Verfügung. Diese Seite hält fest, wohin die Zeit bei einem großen Rig geht, was ENG-30 daran geändert hat und was übrig bleibt.

**Messaufbau.** Die Bühnen-Show 2026 (`tools/build_buehnen_show_2026.py`): 80 Geräte (40 PAR, 20 Moving Heads, 10 Laser, 8 Strobes, 2 Hazer) in 3 Universen; 24 Szenen, 12 Matrizen, 7 EFX, 3 Chaser, 5 Looks (Collections). Gemessen wird `OutputManager._send_all` — genau der Aufruf des 44-Hz-Threads. Die Zahl je Fall ist der **kleinste Mittelwert** aus mehreren Runden zu 200 Frames; „vorher" und „nachher" liefen abwechselnd, weil der Rechner nebenher benutzt wurde.

## Ergebnis

| Fall | vorher (ms) | nachher (ms) | Anteil am Budget nachher |
|---|---|---|---|
| nichts läuft | 1,95 | 0,43 | 2 % |
| Look Intro | 8,25 | 3,31 | 15 % |
| Look Aufbau | 9,44 | 3,95 | 17 % |
| Look Drop | 10,25 | 4,22 | 19 % |
| Look Breakdown | 9,19 | 3,47 | 15 % |
| Look Finale | 9,76 | 4,33 | 19 % |
| alle 24 Szenen zugleich | 15,50 | 4,34 | 19 % |
| alle 12 Matrizen zugleich | 11,74 | 8,20 | 36 % |
| alle 7 EFX zugleich | 8,19 | 5,07 | 22 % |
| alle 3 Chaser zugleich | 23,37 | 8,69 | 38 % |
| alle 5 Looks zugleich | 38,45 | 17,27 | 76 % |

Die unteren fünf Zeilen sind keine sinnvollen Bühnenzustände, sondern Belastungsproben je Funktionsart. „Alle 5 Looks zugleich" lag vorher **über** dem Budget (der Thread hätte nur noch 26 statt 44 Frames je Sekunde geschafft), jetzt darunter.

Die **Ausgabe ist unverändert**: über 300 Frames in allen elf Fällen Byte für Byte dieselben Werte wie vorher (`--abdruck 300`), ebenso am gekürzten Rig.

## Verteilung je Funktionsart

Zeit je Frame in ms, ohne die Zeit aufgerufener Kinder; in Klammern die Zahl der `write`-Aufrufe je Frame.

**Vorher:**

| Look | gesamt | Szene | Matrix | EFX | Chaser | Collection | Rest |
|---|---|---|---|---|---|---|---|
| Intro | 8,18 | 3,67 (7) | 0,78 (1) | 1,66 (2) | – | 0,02 (1) | 2,06 |
| Aufbau | 9,28 | 3,67 (8) | 1,62 (2) | 1,65 (2) | 0,29 (2) | 0,02 (1) | 2,04 |
| Drop | 10,28 | 4,95 (9) | 1,98 (3) | 1,00 (1) | 0,29 (2) | 0,02 (1) | 2,04 |
| Breakdown | 9,25 | 4,75 (8) | 0,77 (1) | 1,64 (2) | – | 0,02 (1) | 2,06 |
| Finale | 9,78 | 3,67 (8) | 2,76 (4) | 1,00 (1) | 0,29 (2) | 0,02 (1) | 2,04 |

**Nachher:**

| Look | gesamt | Szene | Matrix | EFX | Chaser | Collection | Rest |
|---|---|---|---|---|---|---|---|
| Intro | 3,31 | 0,94 (7) | 0,60 (1) | 1,24 (2) | – | 0,02 (1) | 0,52 |
| Aufbau | 3,94 | 0,62 (8) | 1,27 (2) | 1,22 (2) | 0,29 (2) | 0,02 (1) | 0,52 |
| Drop | 4,31 | 1,15 (9) | 1,58 (3) | 0,74 (1) | 0,30 (2) | 0,02 (1) | 0,52 |
| Breakdown | 3,49 | 1,13 (8) | 0,61 (1) | 1,22 (2) | – | 0,02 (1) | 0,51 |
| Finale | 4,42 | 0,63 (8) | 2,22 (4) | 0,74 (1) | 0,30 (2) | 0,02 (1) | 0,52 |

„Rest" ist der Frame ohne Funktionen: Programmer, Dimmer-Master, Blackout-/Grand-Master-Masken, Senden.

## Was teuer war

1. **Szenen: 38–52 % der Frame-Zeit.** Eine Szene speichert je Wert die Gerätenummer (fid). Beim Schreiben suchte sie zu jedem Wert das Gerät — mit einem Durchlauf durch die ganze Patch-Liste. Ein Look aus neun Szenen sind rund 450 Durchläufe je Frame über 80 Geräte, und jeder Vergleich ist ein Attributzugriff auf ein Datenbank-Objekt (SQLAlchemy). Im Look Drop waren es insgesamt rund 34 000 solcher Zugriffe je Frame, gut 20 000 davon allein aus dieser Suche. Matrizen, EFX und gemappte Kanäle suchten genauso, nur seltener.
   **Jetzt:** der `FunctionManager` reicht den Funktionen eine Patch-Liste mit Tabelle `fid → Gerät` (`src/core/engine/patch_index.py`). Gebaut wird sie nur, wenn sich die Liste ändert. Wer eine gewöhnliche Liste hereingibt (Vorschau, Tests), bekommt die bisherige Suche.
2. **Grundlast: rund 2 ms je Frame, auch wenn nichts läuft.** `_render_frame` leitete in jedem Frame für jedes Gerät neu ab, welche Adressen Intensität, Dimmer und Farbe sind — rund 5 700 Attributzugriffe je Frame für eine Auskunft, die nur vom Patch abhängt.
   **Jetzt:** die Listen stehen im Render-Plan (`_adress_plan`, gebaut in `_rebuild_render_plan`, getauscht unter demselben Lock wie der übrige Plan). Der Frame nimmt einen Eintrag nur, wenn er noch genau zu Gerät, Adresse und Universum passt; sonst rechnet er wie bisher.

## Was bleibt

- **Matrix: 0,55–0,6 ms je laufender Matrix** (40 Zellen). `RgbMatrixInstance.write` fragt je Zelle und Frame erneut, ob das Gerät einen Dimmer hat, ob es RGB hat und welche Kanäle zur Zelle gehören (rund 6 000 Attributzugriffe je Frame bei vier Matrizen). Das ließe sich je Matrix und Patch-Stand einmal ableiten. Nicht in ENG-30 gebaut: der Schreibpfad trägt viele Sonderfälle (Kopf-Zellen, eigene Weiß-Achse, Farbrad), jeder mit eigener Vorgeschichte; das ist ein eigenes Item mit eigenem Bildvergleich.
- **EFX: 0,6–0,75 ms je laufendem EFX** (20 Köpfe). Je Kopf und Frame werden die Pan-/Tilt-Kanäle neu aufgelöst (`resolve_attr_channels`, `pan_tilt_head_count`, `channel_occurrence_keys`). Gleiche Art Gewinn, gleiche Vorsicht.
- **Szenen: 0,08–0,14 ms je laufender Szene.** Der Rest ist die Adressprüfung je Wert (Netzwerk-Laser, Kanal über dem Geräteende — ENG-20).
- **Rest 0,5 ms**: Universen anlegen, Schreibprotokoll, Masken, Senden.

Mit dem Stand nach ENG-30 trägt ein Look der Bühnen-Show 15–19 % des Budgets. Bei gleichem Aufbau wäre rechnerisch erst bei rund fünfmal so vielen gleichzeitig laufenden Matrizen und EFX die Grenze erreicht.

## Schlankeres Rig zum Vergleich

Dieselbe Show, der Patch auf **16 Moving Heads und 32 PAR** gekürzt (`--schlank 16,32`; Laser, Strobes und Hazer entfernt). Funktionen, die entfernte Geräte ansprechen, laufen weiter und überspringen sie.

| Fall | vorher (ms) | nachher (ms) |
|---|---|---|
| nichts läuft | 1,21 | 0,34 |
| Look Intro | 5,79 | 2,20 |
| Look Aufbau | 6,42 | 2,70 |
| Look Drop | 7,05 | 2,58 |
| Look Breakdown | 6,57 | 2,32 |
| Look Finale | 6,38 | 2,64 |

Vorher sparte das kleinere Rig nur rund ein Drittel, obwohl 40 % der Geräte fehlten: eine Szene, deren Gerät es nicht mehr gibt, durchlief die Liste bis zum Ende — der teuerste Fall der Suche. Nachher skaliert die Zeit etwa mit der Zahl der Geräte, die tatsächlich etwas tun.

## Mehr Universen

`tools/benchmark_universes.py` (synthetisches Rig: je Universum 12 PAR mit Matrix und 2 Moving Heads mit EFX) auf demselben Rechner, p50 je Frame:

| Universen | Geräte | vorher (ms) | nachher (ms) |
|---|---|---|---|
| 8 | 112 | 5,6 | 3,1 |
| 16 | 224 | 14,1 | 6,0 |
| 32 | 448 | 39,9 | 12,0 |

Vorher wuchs die Zeit schneller als das Rig (Faktor 7 bei vierfacher Größe) und lag bei 32 Universen über dem Budget; nachher wächst sie etwa linear und bleibt darunter. Die aktuelle Tabelle steht in [PERFORMANCE.md](PERFORMANCE.md).

## Grenzen der Messung

- Ohne Fenster und ohne echte Ausgabe-Hardware. In der laufenden App teilt sich der Render-Thread den Interpreter mit der Oberfläche; die Zeiten dort sind höher (bei der 2D-Ansicht gemessen: Faktor 1,6, siehe UI-88). Die **Verhältnisse** gelten, die Absolutwerte nicht.
- Ein Rechner, nebenher benutzt. Zwei Läufe desselben Stands lagen bis zu 10 % auseinander; deshalb der kleinste Mittelwert und abwechselnde Läufe.
- Die Verteilung misst mit Hüllen um `write`; die Summe liegt wenige Prozent über der ungestörten Messung.
