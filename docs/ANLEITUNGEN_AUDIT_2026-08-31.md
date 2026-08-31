# Anleitungs-Audit 2026-08-31 — `docs/anleitung_vc_widgets/`

**Auftrag:** DOC-10 Teil b (veraltete Anleitungen gegen die aktuelle UI).
**Verfahren, verbindlich seit heute:** die beschriebenen Schritte werden **in der
laufenden App** durchgegangen und per Screenshot belegt — nicht headless und
nicht per Textabgleich gegen den Quelltext.

> **Warum das der Unterschied ist.** DOC-10 hält einen gescheiterten mechanischen
> Anlauf fest: Datumsvergleich markierte praktisch alle 574 Bilder, Textabgleich
> lieferte 208 Treffer wie „nicht", „und", „welche". Beide Verfahren können die
> Frage gar nicht beantworten, um die es geht — *geht der beschriebene Schritt so
> noch?* Ein Bedienelement kann im Quelltext existieren, korrekt beschriftet sein
> und trotzdem verdeckt, deaktiviert oder unerreichbar sein.

## Wie gemessen wurde

Auf diesem Linux-Rig ist **kein** Eingabe-Werkzeug installiert (`xdotool`, `xte`,
`ydotool`, `pyautogui`, `pynput`). Verfahren stattdessen: ein Wegwerf-Launcher
baut die **echte `MainWindow` auf dem echten X-Server** (`DISPLAY=:0`, *nicht*
offscreen), bedient die realen Widgets per `QTest.mouseClick` und fotografiert
über `grabWindow(win.winId())` bzw. `widget.grab()`.

**Vor jeder Live-Runde:** `data/universes.json` auf `[]` — sonst sendet die App
beim Klicken echtes DMX ans Rig. Danach zurückgelegt.

★ **Erste Aufnahme war ein Timing-Artefakt, kein Fund.** Der Screenshot direkt
nach `processEvents()` zeigte noch die vorige Sektion, obwohl
`_stack.currentIndex()` bereits umgeschaltet war. Mit einer echten
Ereignisschleifen-Pause verschwand es. **Wer hier nicht nachmisst, meldet einen
Rendering-Bug, den es nicht gibt.**

## Befunde

Alle fünf am laufenden Programm gemessen.

### 1. Zwei Widget-Typen sind in KEINER Anleitung beschrieben

Die Toolbar im Bearbeiten-Modus bietet **16** Widget-Knöpfe; drei weitere Typen
entstehen über Smart-Drop/Galerie — macht **19 Typen**. Der Index beschrieb
**17**.

Nicht dokumentiert waren:

| Toolbar-Knopf | Klasse | jetzt |
|---|---|---|
| `Tempo-Controller` | `VCTempoBusController` | [22_tempo_controller.md](anleitung_vc_widgets/22_tempo_controller.md) |
| `Live-Edit` | `VCMultiLiveEditor` | [23_live_edit.md](anleitung_vc_widgets/23_live_edit.md) |

Beide wurden in der laufenden App angelegt und einzeln fotografiert.
`Live-Edit` kam in den Anleitungen bis heute nur als *Eigenschaft* anderer
Widgets vor („Live-Edit-Slot" bei Button und Fader) — als eigener Widget-Typ
nirgends.

### 2. Drei verschiedene Zahlen für dieselbe Sache

| Stelle | behauptet | wahr |
|---|---|---|
| `README.md`, Einleitung | Schaukasten zeigt **19** Typen | er legt **17** ab |
| `README.md`, Überschrift | „Die **18** Bedien-Elemente" | die Tabelle listete **17**; es gibt **19** |
| `tools/build_vc_widgets_showcase.py`, Docstring | „JEDEN der **18**" | seine eigene Selbstprüfung meldet „alle **17** Typen vorhanden" |

Gemessen durch Ausführen des Generators (`Widget-Typen: {...}` → 17 Klassen) und
Auszählen der Registry in `virtual_console_view.py:189-205`.

### 3. Der „Baukasten"-Knopf existiert nicht mehr

`README.md` versprach im Bearbeiten-Modus Knöpfe für „alle Widget-Typen,
**Baukasten**, Undo/Redo, Raster". In `src/ui/**` kommt „Baukasten" **0-mal**
vor, und `21_baukasten.md` hält im eigenen Kopf fest, dass die Baukasten-Blöcke
**2026-07 entfernt** wurden. Zwei Anleitungen derselben Sammlung widersprachen
sich also.

Die Aufzählung nennt jetzt, was wirklich da ist — und ein neuer Screenshot der
Werkzeugleiste zeigt es.

### 4. Die Bildunterschrift versprach Vollständigkeit

„**Alle** VC-Widgets in der Übersicht" — das Bild zeigt 17 von 19. Unterschrift
korrigiert; die Lücke steht jetzt ausdrücklich daneben.

### 5. Kein Befund: die „drei ohne Toolbar-Knopf"-Aussage stimmt

Stepper, Effekt-Anzeige und Effekt-Editor-Box haben tatsächlich keinen eigenen
Knopf — nachgezählt an der Registry. Nur präzisiert („drei **der 19**").

## Was NICHT geprüft wurde

Ehrlich benannt, damit der nächste Durchgang weiß, wo er ansetzt:

- Die **21 Einzelseiten** wurden auf ihre Screenshots hin **nicht** einzeln
  durchgeklickt — dieser Durchgang galt dem Index und der Vollständigkeit.
- **Hover-getriebene Oberflächen** (Tooltips) lassen sich mit `QTest` prinzipiell
  nicht prüfen; sie kommen an den Fenstermanager vorbei.
- Die anderen **36 Anleitungs-Ordner** — DOC-10 verlangt ausdrücklich einen
  Bereich pro Runde.

## Mechanische Gates

Beide grün, vor und nach dieser Runde:

```
[doc-images] 258 Bild-Referenzen geprueft, 0 tot
[doc-links]  709 relative Querverweise geprueft, 0 tot
```

## Folge-Item

**DOC-14** — den Schaukasten-Generator auf alle 19 Typen bringen und das
Übersichtsbild neu aufnehmen.
