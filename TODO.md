# TODO / Next Steps

> Letzte Aktualisierung: 2026-05-31

## 1) Stabilitaet & Qualitaet
- [x] Bestehende Tests automatisiert in CI laufen lassen → `.github/workflows/ci.yml`
- [x] Weitere Unit-Tests fuer Core-Engine ergaenzen → `tests/test_core_engine.py` (93 Tests: Universe, Cue, CueStack/FadeState, ChannelModifier, cmdline Parser, UndoStack)
- [x] Smoke-Test-Checkliste fuer Audio, MIDI, OSC und Web-Remote definieren → `docs/SMOKE_TEST.md`

## 2) Dokumentation aktualisieren
- [x] `README.md` um klaren "Quick Start" fuer neue Nutzer erweitern.
- [x] Feature-Dokus in `docs/` um konkrete Praxisbeispiele pro Bereich erweitern → `docs/WORKFLOWS.md`
- [x] Changelog/Release-Notizen-Struktur einfuehren → `CHANGELOG.md` (Keep-a-Changelog-Format)

## 3) Packaging & Betrieb
- [ ] Installer/Uninstaller (`install.py`, `uninstall.py`) gegen frische Windows-Setups testen.
- [x] Start-Skripte (`start.sh`, `start.bat`, `start.ps1`) auf Konsistenz pruefen und vereinheitlichen → `start.bat` Python-Pfad-Log ergaenzt
- [ ] Abhaengigkeiten in `requirements.txt` auf aktuelle stabile Versionen pruefen.

## 4) Produkt-Backlog (naechste Ausbaustufe)
- [x] Fehlerreporting-Workflow definieren → `.github/ISSUE_TEMPLATE/bug_report.md`
- [x] Preset-/Demo-Shows im Ordner `shows/` bereitstellen → `shows/demo_rgb_par.lshow` (4 PAR, 4 Cues)
- [x] Priorisierte Roadmap fuer UI/Engine/Visualizer festhalten → `ROADMAP.md`

## 5) Optional nice-to-have
- [x] Dev-Setup-Doku fuer Contributor ergaenzen → `CONTRIBUTING.md`
- [ ] Performance-Benchmarks fuer mehrere Universen (z. B. 8/16/32) dokumentieren.

---

## 6) Programmer – Umbau & Matrix-Workflow (NEU 2026-05-31)

### ✅ P-01: Reiter "RGB Matrix", "EFX", "Funktionen" in den Programmer umziehen — ERLEDIGT 2026-06-01
**Erledigt:** In `main_window.py` wandern die drei Reiter aus `_build_section_fixtures`
(Sektion „Patchen") in `_build_section_programmer`. Neue Struktur:
- **Patchen** (Sektion 1): Patch · Gruppen
- **Programmer** (Sektion 2): Programmer · Funktionen · EFX · RGB Matrix · Paletten · Snapshots

Alle Daten-Bindungen laufen über `SyncEvent`-Subscriptions in den Views selbst —
der Umzug betrifft nur die UI-Platzierung. View-Referenzen (`_efx_view`,
`_rgb_matrix_view`, `_function_manager_view`) werden ausschließlich in
`main_window.py` benutzt. Verifiziert: 148 Tests grün + Headless-Bau des MainWindow
(Tab-Labels geprüft). Deckt FEATURE_MAP D-3 / C-6 ab.
**Problem:** Diese Reiter befanden sich unter "Geraete & Funktionen", gehoeren aber
logisch in den Programmer (dort wird programmiert, nicht gepatcht).

---

### P-02: Vorschau im RGB-Matrix-Bereich funktioniert nicht zuverlaessig
**Problem:** Die Effekt-Matrix-Vorschau zeigt nicht immer den korrekten Zustand an
(Rendering-Fehler oder kein Live-Update beim Aendern von Parametern).
**Was zu tun:**
1. Fehlerquelle identifizieren: fehlende Repaint-Aufrufe, Event-Disconnects oder
   defekte Daten-Bindung zwischen Engine und Preview-Widget.
2. Sicherstellen, dass die Vorschau bei jeder Parameteraenderung (Farbe, Effekttyp,
   Geschwindigkeit usw.) sofort aktualisiert wird.

---

### P-03: Start-/Stopp-Buttons im RGB-Matrix-Fenster ohne Funktion
**Problem:** Die Steuer-Buttons (Start, Stopp und ggf. weitere) im RGB-Matrix-Fenster
reagieren nicht wie erwartet – Effekte starten/stoppen nicht.
**Was zu tun:**
1. Signal-Slot-Verbindungen der Buttons pruefen.
2. Korrekte Engine-Aufrufe (z. B. `start_effect()`, `stop_effect()`) anhaengen.
3. Button-Zustand (enabled/disabled, Icon) an den tatsaechlichen Laufzustand koppeln.

---

### P-04: Matrix-Style als Standard-Programmier-Ansicht fuer Gruppen
**Problem:** Beim Bearbeiten von Gruppen gibt es keine dedizierte Matrix-Ansicht als
Standard-Einstiegspunkt.
**Was zu tun:**
1. Wenn im Programmer eine Gruppe ausgewaehlt wird, soll automatisch (oder als Standard-Tab)
   die Matrix-Ansicht geoeffnet werden.
2. Ausnahme: Moving Heads und spezielle Fixture-Typen – diese behalten ihre bestehende
   Einzel-Programmierung (spaetere Ausbaustufe, noch nicht umsetzen).

---

### P-05: Matrix-Programmer – Kategorie-Auswahl oben
**Ziel:** Im Matrix-Programmer soll der Nutzer oben zwischen verschiedenen
Programmier-Kategorien waehlen koennen:
- **Farben** – RGB/RGBW-Farbzuweisung pro Zelle
- **Stroke / Lauflicht** – Richtung, Geschwindigkeit, Breite
- **Bewegung** – (Vorbereitung fuer Moving Heads, zunaechst Platzhalter)
- **Effekte** – vordefinierte Effekt-Templates (Chase, Fade, Rainbow usw.)
- **Dimmer** – Helligkeitswerte pro Zelle oder global

**Was zu tun:**
1. Toolbar oder Tab-Leiste oben im Matrix-Programmer mit den fuenf Kategorien anlegen.
2. Jede Kategorie zeigt ein anderes Eingabe-Panel unterhalb der Matrix.
3. Die gewaehlte Kategorie bestimmt, welche DMX-Attribute beim Programmieren beschrieben werden.
4. Gespeicherte Werte je Kategorie koennen spaeter unabhaengig auf Snaps/Cues gelegt werden.

---

### P-06: Live-Vorschau der RGB-Matrix im Programmer (Strob, Farben, Dimmer, Lauflicht)
> **Verortung im neuen Layout (siehe LAYOUT-01):** Dieses Matrix-Vorschau-Widget ist die
> **untere, ausklappbare Matrix-Ansicht** (Zone UNTEN), nicht ein separates Panel.
**Ziel:** Innerhalb des Programmers soll eine kleine visuelle Echtzeit-Vorschau der Matrix
angezeigt werden (nicht der vollstaendige Visualizer).
**Was zu tun:**
1. Kleines Grid-Widget im Programmer einbauen (repraesentiert die Matrix als farbige Kacheln).
2. Kacheln spiegeln live den aktuellen Programmierer-Output wider
   (Farbe, Dimmer-Helligkeit, Strobo-Blinken).
3. Lauflicht-Effekte werden als animierte Bewegung ueber die Kacheln dargestellt.
4. Kein 3D-Rendering – rein 2D, schnell, ressourcenschonend.

---

### P-07: Live-Vorschau "aktive Gruppen & Lampen" (Mini-Uebersicht)
> **Verortung im neuen Layout (siehe LAYOUT-01):** Diese Mini-Uebersicht der aktiven
> Gruppen/Lampen gehoert in die **Zone OBEN RECHTS** (geraete-unabhaengige Effekt-Preview),
> nicht mehr „unten rechts". „Unten" ist jetzt fuer die ausklappbare Matrix-Ansicht (P-06) reserviert.
**Ziel:** Beim Programmieren von Gruppen soll eine Miniaturansicht (oben rechts) zeigen:
- Welche Gruppen aktuell ausgewaehlt sind
- Welche einzelnen Fixtures (Lampen) aktiv sind
- Was gerade per Start/Stopp laeuft

**Was zu tun:**
1. Kleines Overlay- oder Dock-Widget unten rechts im Programmer einbauen.
2. Gruppen werden als beschriftete Bloecke dargestellt, aktive Gruppen farbig hervorgehoben.
3. Aktive Fixtures innerhalb einer Gruppe werden durch ein Icon oder Faerbung markiert.
4. Laufende Effekte/Chaser werden mit einem kleinen Animations-Indikator (z. B. pulsierender Rand)
   dargestellt.

---

### P-08: Hilfe-Popups (Help-Tooltips) fuer Buttons im Programmer
**Ziel:** Jeder Button/Regler im Programmer soll eine erklaerende Hilfe anzeigen koennen.
Ein dezenter "?"-Button oder ein Klick in einem speziellen Hilfe-Modus oeffnet ein
kleines Fenster mit:
- Name des Elements
- Kurzbeschreibung was es tut
- Ggf. ein kurzes Beispiel

**Was zu tun:**
1. Hilfe-Modus-Toggle einfuehren (z. B. "?"-Schaltflaeche in der Programmer-Toolbar).
2. Im Hilfe-Modus wird jeder geklickte Button/Regler anstatt ausgefuehrt durch ein
   `QDialog` mit Hilfetext ersetzt.
3. Hilfetexte als Dictionary oder JSON-Datei verwalten (leicht erweiterbar).
4. Alternativ: Rich-Tooltip mit verlaengerter Verzoegerung als einfachere Variante.

---

## 7) Umbenennung "Geraete & Funktionen" → "Patchen" (NEU 2026-05-31)

### ✅ PA-01: Tab / Fenster umbenennen — ERLEDIGT 2026-06-01
**Erledigt:** Sektions-Label in `main_window.py` von "Geraete & Funktionen" auf
**"Patchen"** umbenannt (Logik laeuft ueber Indizes, keine weiteren Stellen betroffen).
**Problem:** Der Name "Geraete & Funktionen" beschreibt nicht klar, dass es sich um
den Patch-Bereich handelt (Fixture-Zuweisung, DMX-Adressen, Universen).
**Was zu tun:**
1. Alle UI-Labels, Fenster-Titel und Menue-Eintraege von "Geraete & Funktionen" /
   "Geraete und Funktionen" auf **"Patchen"** (oder "Patch") umbenennen.
2. Interne Variablen- und Klassennamen koennen vorerst unveraendert bleiben (kein Refactor
   der Logik, nur UI-Texte anpassen).
3. Strings in Translations-Dateien (falls vorhanden) ebenfalls aktualisieren.

---

### PA-02: Live-Uebersicht unten rechts im Patch-Bereich
**Ziel:** Analog zur Gruppen-Vorschau im Programmer soll auch im Patch-Fenster
eine kleine Live-Ansicht unten rechts angezeigt werden mit:
- Welche Gruppen gerade angeschlossen / definiert sind
- Welche Fixtures aktiv (DMX-Ausgabe > 0) sind
- Aktuellem DMX-Universum-Status (optional)

**Was zu tun:**
1. Kleines Status-Widget unten rechts im Patch-Fenster einbauen.
2. Gruppen-Liste mit Aktivitaets-Indikator (Lampe leuchtet = Gruppe hat DMX-Output).
3. Fixtures in der aktiven Gruppe werden als nummerierte Kacheln dargestellt.
4. Update-Rate: ~10 Hz reicht (kein Echtzeit-DMX-Streaming noetig).


---

## 8) Simple Desk & DMX Monitor – Patch-Kontext anzeigen (NEU 2026-05-31)

### SD-01: Geraete-Label ueber Kanaelen im Simple Desk
**Problem:** Im Simple Desk sind die Kanaele aktuell nur als Nummer dargestellt.
Wenn Fixtures gepatcht sind, ist nicht erkennbar, welches Geraet auf welchem Kanal liegt.
**Was zu tun:**
1. Ueber jedem Kanal-Fader im Simple Desk ein kleines Label einblenden, das
   Geraete-Kurzname + Kanal-Funktion anzeigt (z. B. "PAR 1 – R", "PAR 1 – G", "Dimmer 3").
2. Label wird aus den Patch-Daten (AppState / Fixture-Definition) dynamisch befuellt.
3. Ungepatchte Kanaele zeigen weiterhin nur die DMX-Adresse.
4. Bei Aenderungen im Patch (neu patchen, loeschen) aktualisiert sich das Label automatisch.

---

### SD-02: Kanal-Farbkodierung nach Funktion im Simple Desk
**Ziel:** Auf einen Blick erkennbar machen, welcher Kanal welche Funktion hat.
Farbschema (Vorschlag):
- **Rot** – R-Kanal (Red)
- **Gruen** – G-Kanal (Green)
- **Blau** – B-Kanal (Blue)
- **Weiss / Hellgrau** – W-Kanal (White)
- **Gelb** – Dimmer / Master-Dimmer
- **Lila** – Strobe / Effekt
- **Grau** – ungepatchter / unbekannter Kanal

**Was zu tun:**
1. Farbkodierung als Hintergrundfarbe des Fader-Labels oder als farbiger Balken unter dem Fader.
2. Farb-Map in einer zentralen Konfiguration (z. B. `CHANNEL_COLORS`-Dict) definieren,
   damit sie spaeter leicht anpassbar ist.
3. Sicherstellen, dass auch der Label-Text ("Dimmer", "Effekt", "R", "G", "B" usw.)
   statt nur einer Nummer angezeigt wird.

---

### SD-03: Geraete-Label und Farbkodierung auch im DMX Monitor
**Problem:** Analog zu SD-01/SD-02 fehlt auch im DMX Monitor der Patch-Kontext.
**Was zu tun:**
1. In der DMX-Monitor-Ansicht je Zelle den Geraete-Kurznamen und die Kanal-Funktion
   als zweite Zeile oder Tooltip anzeigen.
2. Optional: Gleiche Farbkodierung wie im Simple Desk verwenden, damit das Schema
   appweit konsistent ist.
3. Ungepatchte Kanaele weiterhin neutral darstellen.

---

## 9) Effekt-Engine – Architektur & Programmier-Modell ueberarbeiten (NEU 2026-05-31)

> **Hinweis:** Dieser Abschnitt beschreibt ein groesseres Redesign. Vor der Umsetzung
> muss die bestehende Effekt-Engine gruendlich analysiert werden (siehe ARC-01).

### ARC-01: Ist-Analyse der Effekt-Engine dokumentieren
**Ziel:** Bevor Aenderungen gemacht werden, den aktuellen Stand verstehen und festhalten:
- Wie werden Effekte intern repraesentiert (Datenstruktur, Klassen)?
- Wie interagieren Effekte mit Dimmer, Farb- und Strobe-Kanaelen?
- Wie laeuft Fade-In/Fade-Out aktuell durch die Engine?
- Wo genau liegt das Problem (Effekte ueberschreiben Dimmer-Werte ungewollt)?

**Was zu tun:**
1. Relevante Quelldateien identifizieren (Effekt-Engine, Cue-Verarbeitung, Channel-Merger).
2. Kurze technische Beschreibung in `docs/EFFECT_ENGINE.md` ablegen.
3. Konkrete Fehler-/Luecken-Liste erstellen, die als Basis fuer ARC-02 bis ARC-05 dient.

---

### ARC-02: Effekte und Dimmer strikt trennen (Attribut-Isolation)
**Problem:** Effekte, die nur Farb-Paletten beschreiben (RGB), beeinflussen aktuell
ungewollt auch den Dimmer-Kanal. Das verhindert unabhaengige Dimmer-Steuerung.
**Was zu tun:**
1. Effekte koennen im Header deklarieren, welche Attribut-Typen sie beschreiben
   (z. B. `attributes: ["R", "G", "B"]` – kein Dimmer).
2. Die Channel-Merge-Logik respektiert diese Deklaration: Ein Farb-Effekt
   schreibt **nie** auf Dimmer-Kanaele, auch nicht mit Wert 0.
3. Dimmer bleibt unabhaengig steuerbar (manuell per Fader oder eigenem Effekt).
4. Test: Farb-Effekt laufen lassen, Dimmer-Fader bewegen → Dimmer aendert sich,
   Farb-Effekt laeuft unveraendert weiter.

---

### ARC-03: Manueller Dimmer neben laufendem Effekt einstellbar machen
**Problem:** Wenn ein Effekt laeuft, ist der Dimmer oft nicht mehr manuell
greifbar (Effekt ueberschreibt oder sperrt den Kanal).
**Was zu tun:**
1. Sicherstellen, dass der Dimmer-Kanal immer als "manueller Override"-Layer
   ueber dem Effekt-Output wirkt (HTP- oder explizites Master-Layer-Konzept).
2. Im Programmer einen permanenten Dimmer-Regler einblenden, der unabhaengig
   vom laufenden Effekt jederzeit bedienbar ist.
3. Verhalten dokumentieren: Dimmer = 0 → Blackout, auch wenn Effekt laeuft.

---

### ARC-04: Fade-In / Fade-Out fuer manuell programmierte Effekte
**Problem:** Fade-In/Out funktioniert zuverlaessig nur bei Effekten aus dem
Effektgenerator. Selbst programmierte Effekte (z. B. eigene Cue-Sequenzen)
haben kein sauberes Fade-Verhalten.
**Was zu tun:**
1. Fade-In/Out als eigenstaendige Engine-Schicht implementieren, die auf
   **jeden** Effekt-Output angewendet werden kann – unabhaengig davon,
   ob der Effekt aus dem Generator oder manuell erstellt wurde.
2. Pro Effekt/Programm: Fade-In-Zeit und Fade-Out-Zeit als Metadaten speicherbar.
3. Fade laeuft als Multiplikator ueber den kombinierten Channel-Output
   (0.0 → 1.0 beim Einblenden, 1.0 → 0.0 beim Ausblenden).

---

### ARC-05: Programme – Effekte und Szenen als aufrufbare Einheiten speichern
**Ziel:** Selbst programmierte Effekte, Farbszenen und Kombinationen daraus
sollen als **Programme** gespeichert werden koennen – nicht nur als Snaps.
Programme sind wiederverwendbare, benannte Ablaeufe, die:
- Im Dateibaum (rechte Seitenleiste) aufgelistet werden
- Auf MIDI-Tasten oder die virtuelle Konsole gelegt werden koennen
- Gleichzeitig / kombiniert mit anderen Programmen ausgefuehrt werden koennen
  (Layer-Betrieb mit definierter Prioritaet)
- Fade-In/Out-Zeiten als eigene Metadaten tragen (siehe ARC-04)

**Was zu tun:**
1. Datenstruktur "Programm" definieren:
   - Name, ID, Typ (Farbe / Effekt / Dimmer / Kombination)
   - Liste der enthaltenen Channel-States oder Effekt-Referenzen
   - Fade-In / Fade-Out / Hold-Zeit
   - Attribut-Maske (welche Attribut-Typen werden beschrieben)
2. Programme in der Show-Datei (`.lshow`) speichern und laden.
3. Dateibaum / Programm-Browser in der rechten Seitenleiste anzeigen.
4. Zuweisung auf MIDI und virtuelle Konsole ermoeglichen.
5. Layer-/Kombinations-Logik: Mehrere gleichzeitig aktive Programme
   werden nach Attribut-Maske und Prioritaet zusammengemischt.

---

### ARC-06: Effektgenerator und manuelle Programmierung vereinheitlichen
**Problem:** Aktuell gibt es zwei getrennte Wege Effekte zu erstellen
(Generator-UI vs. manuelle Cue-Programmierung). Das fuehrt zu zwei
inkonsistenten Daten-Modellen und doppeltem Wartungsaufwand.
**Ziel:** Beide Wege sollen dasselbe interne "Programm"-Format (ARC-05) erzeugen.
**Was zu tun:**
1. Effektgenerator-Output in das neue Programm-Format konvertieren.
2. Manuell erstellte Cue-Sequenzen ebenfalls als Programme speicherbar machen.
3. Mittelfristig: Eine einheitliche "Programm-Editor"-Ansicht, die sowohl
   Generator-Parameter als auch manuelle Kanaelwerte zeigt.


---

## 10) Effekt-Assistent – Erweiterungen (NEU 2026-06-01)

### EA-01: Gruppen-Auswahl im Effekt-Assistenten
**Problem:** Im Effekt-Assistenten koennen aktuell nur einzelne Fixtures ausgewaehlt werden.
Gruppen fehlen als Auswahleinheit.
**Was zu tun:**
1. Auswahl-Dialog im Assistenten um eine "Gruppen"-Ebene erweitern.
2. Wird eine Gruppe gewaehlt, wird sie intern auf die enthaltenen Fixtures aufgeloest
   (oder als Gruppe an die Effekt-Engine weitergegeben, falls unterstuetzt).
3. Mehrfachauswahl: Mischung aus Gruppen und Einzel-Fixtures moeglich.

---

### EA-02: Farb-Schritte mit Zwischenstufen (Color-Step-Interpolation)
**Ziel:** Im Assistenten soll es bei Farbwechsel-Effekten eine Option geben,
automatisch berechnete Zwischenfarben zwischen zwei (oder mehr) Zielfarben einzufuegen.
**Beispiel:** Farbwechsel Rot → Gruen mit 20 Zwischensteps erzeugt
einen sanften Farbverlauf statt eines harten Schnitts.
**Was zu tun:**
1. Im Farb-Schritt-Editor des Assistenten: Checkbox "Zwischenschritte aktivieren".
2. Bei aktivierter Checkbox: Zahlenfeld "Anzahl Zwischensteps" (Bereich 1–255).
3. Engine berechnet die Zwischenfarben via linearer oder HSV-Interpolation.
4. Generierter Cue/Programm-Output enthaelt alle Zwischenschritte als einzelne Frames.
5. Vorschau der interpolierten Farbpalette direkt im Assistenten anzeigen.

---

### EA-03: Effekt-Assistenten um weitere Effekt-Typen erweitern
**Ziel:** Mehr vorgefertigte Effekt-Templates, die haeufig benoetigt werden.
Kandidaten (Prioritaet nach Nutzungswahrscheinlichkeit):
- **Rainbow-Sweep** – Regenbogen laeuft ueber die Fixture-Reihe
- **Fire / Flicker** – zuaellige Helligkeits- und Farbschwankungen (Feuer-Look)
- **Pixel-Chase** – einzelnes Pixel/Fixture laeuft hin und her
- **Twinkle** – zuaellige Fixtures blinken kurz auf
- **Wipe** – einfarbige Welle laeuft von links nach rechts (oder beliebige Richtung)
- **Breathing** – gleichmaessiges Auf- und Abblenden aller Fixtures synchron

**Was zu tun:**
1. Effekt-Template-Struktur so anlegen, dass neue Templates einfach als Python-Klasse
   / Dict ergaenzt werden koennen (Plugin-artiger Ansatz).
2. Jeden neuen Typ im Assistenten als Option eintragen + Parameter-Panel dazu.

---

## 11) Effekt-Engine – Fade & Uebergangs-Bugs (NEU 2026-06-01)

### ✅ EE-01: Hartes Schneiden zwischen Farben – kein Fade — ERLEDIGT 2026-06-01
**Erledigt:** Ursache war der **Chaser** — `step.fade_in` wurde nie an die Scene
durchgereicht, und der Per-Frame-Clear im zentralen Renderer macht ein Snapshotten
des Vorgaengerwerts in der Scene unmoeglich (Scene blendet immer von 0). Loesung:
Der Chaser steuert die Blende jetzt selbst (`chaser.py` `_render_and_blend` /
`_render_child_target`): er rendert das Schritt-Child ueber einen Zwei-Pass-Trick
(Hintergrund 0x00/0xFF) absolut, blendet ueber `step.fade_in` (kurvengeformt) vom
zuletzt ausgegebenen Frame (`_from_values`) zum Ziel und schreibt den Mischwert.
Cue-Executoren (`cue_stack.FadeState`) und `Sequence` (`_prev_values`) faden bereits
korrekt; der Effekt-Assistent erzeugt Chaser → profitiert direkt. Tests:
`tests/test_chaser_crossfade.py` (4).
**Problem:** Beim Wechsel zwischen Farb-Cues / Effekt-Schritten gibt es keinen
weichen Uebergang – die Fixtures springen sofort auf die naechste Farbe,
unabhaengig von der eingestellten Fade-Zeit.
**Betroffene Bereiche:** Manuell programmierte Cue-Sequenzen UND Effekt-Assistent-Output.
**Was zu tun:**
1. Ursache identifizieren: Wird die Fade-Zeit an den Channel-Merger uebergeben?
   Wird sie ignoriert, weil der Effekt-Layer den Cue-Layer ueberschreibt?
2. Sicherstellen, dass Fade-In/Out bei jedem Cue-Uebergang auf DMX-Ebene interpoliert wird
   (Frame-basierter Fade: pro DMX-Tick wird ein Zwischenwert berechnet).
3. Test: Cue A (Rot) → Cue B (Blau), Fade-Zeit 2 s → Fixtures blenden weich durch.

---

### ✅ EE-02: Effekte bleiben auf Maximalhelligkeit (Dimmer wird ignoriert) — ERLEDIGT 2026-06-01
**Erledigt:** Neuer **multiplikativer Dimmer-Master** im zentralen Renderer
(`app_state._render_frame`, Schritt 4b), wirkt NACH dem Effekt-Layer und skaliert
pro Fixture den Dimmer/Intensitaets-Kanal (bzw. ersatzweise die Farbkanaele).
Drei Quellen verdrahtet:
1. **Submaster** — `OutputManager.effective_submaster()` (Produkt aller Slots); der
   VC-Submaster-Fader (`vc_slider.py`) war toter Code und ist jetzt live.
2. **Gruppen-/Fixture-Dimmer** — `state.fixture_dimmers` + API `set_fixture_dimmer`/
   `set_group_dimmer`; UI-Regler "Gruppen-Dimmer" in `fixture_group_view.py`.
3. **Programmer-Dimmer multipliziert** — ein Intensitaets-Wert im Programmer skaliert
   einen laufenden Effekt (effect * prog/255), statt ihn per LTP zu ersetzen; ohne
   laufenden Effekt bleibt der Programmer absolut (Cue-LTP unveraendert).
Tests: `tests/test_dimmer_master.py` (7).
**Problem:** Laufende Effekte ignorieren den Dimmer-Kanal und spielen immer
mit 100 % Helligkeit ab – auch wenn der Master-Dimmer oder Gruppen-Dimmer reduziert ist.
(Verwandt mit ARC-02 / ARC-03, aber konkret als Bug eingestuft.)
**Was zu tun:**
1. Dimmer-Multiplikation im letzten Merge-Schritt sicherstellen:
   `output = effect_value * dimmer_factor`.
2. Dimmer-Faktor muss nach dem Effekt-Layer angewendet werden, nicht davor.
3. Test: Effekt starten, Dimmer auf 50 % → Effekt laeuft mit halber Helligkeit.

---

## 12) Code-Struktur & UI-Aufraeum-Audit (NEU 2026-06-01)

### ✅ AUDIT-01: Funktions-Inventar erstellen (was ist wo, was ist doppelt?) — ERLEDIGT
**Erledigt 2026-06-01:** Inventar aller 44 UI-Module als Tabelle in `docs/FEATURE_MAP.md`
(7 Sektionen + Sub-Tabs, Menüs, Funktions-Editoren, Werkzeuge, VC-Widgets, Visualizer)
inkl. 9 markierter Doppelungen (D-1…D-9, u. a. Snapshots 3-fach, Output vs. DMX-Monitor)
und Konsolidierungs-Empfehlung (C-1…C-9) als Basis für AUDIT-02.

**Ziel:** Vor groesseren Refactoring-Massnahmen einen vollstaendigen Ueberblick gewinnen.
**Was zu tun:**
1. Alle UI-Bereiche / Fenster / Tabs auflisten mit je einer Zeile Beschreibung
   ("was macht dieser Bereich?").
2. Doppelungen markieren (z. B. Effekt-Programmierung gibt es an X Stellen).
3. Ergebnis als Tabelle in `docs/FEATURE_MAP.md` ablegen.
4. Aus der Tabelle eine Konsolidierungs-Empfehlung ableiten:
   - Was zusammenlegen?
   - Was in Untermenüs verpacken?
   - Was entfernen (echtes Duplikat ohne Mehrwert)?

---

### AUDIT-02: UI-Konsolidierung nach Inventar
**Ziel:** Ueberladene Bereiche entschlanken, ohne Funktionen zu verlieren.
Funktionen koennen in Untermenues, ausgeklappte Panels oder Kontextmenues wandern.
**Leitprinzip:** Jede Funktion bleibt erreichbar – sie wird nur besser organisiert.
**Was zu tun:**
1. AUDIT-01 muss vorher abgeschlossen sein.
2. Konsolidierungs-Plan aus `docs/FEATURE_MAP.md` umsetzen (schrittweise, ein Bereich pro PR).
3. Nach jeder Aenderung Smoke-Test: Alle verschobenen Funktionen noch erreichbar?

---

## 13) MIDI – LED-Feedback & Button-Verhalten erweitern (NEU 2026-06-01)

### MIDI-01: Wellen-Effekt bei Button-Druck deaktivierbar machen
**Problem:** Beim Druecken eines MIDI-Buttons breitet sich aktuell immer ein
Wellen-Muster auf den umliegenden Pads aus. Das ist nicht immer erwuenscht.
**Was zu tun:**
1. Pro Button (oder global) eine Option "LED-Wellen-Effekt" als Toggle einfuehren.
2. Standardmaessig aktiviert (bisheriges Verhalten bleibt erhalten).
3. Wenn deaktiviert: Nur der gedrueckte Button leuchtet, keine Ausbreitung.

---

### MIDI-02: LED-Feedback-Konfiguration per UI (visuelles Malen / Effekt-Editor)
**Ziel:** Statt Dropdown-Menüs soll es eine interaktive UI geben, mit der
der Nutzer visuell konfigurieren kann, was beim Button-Druck mit den
umliegenden Pads passiert.
**Was zu tun:**
1. Kleines Pad-Grid (z. B. 8x8 fuer APC Mini) als interaktive UI einblenden.
2. Nutzer kann per Klick / Drag auf Nachbar-Pads festlegen:
   - Farbe die beim Druck erscheint
   - Animationsmuster (Welle, sofort, Fade, Zufall)
   - Verzoegerung pro Pad (fuer gestaffelten Welleneffekt)
3. Vorschau: Beim Hovern ueber einen Button wird die konfigurierte Animation
   in der Mini-Vorschau simuliert.
4. Konfiguration wird pro MIDI-Mapping-Slot gespeichert.

---

### MIDI-03: Momentary-Modus (Halten = aktiv, Loslassen = Stop)
**Ziel:** Buttons koennen als "Momentary"-Taster konfiguriert werden:
- **Taste gedrueckt halten** → Funktion/Effekt ist aktiv
- **Taste loslassen** → Funktion/Effekt stoppt sofort

**Anwendungsbeispiel:** Stroboskop solange aktiv wie die Taste gedrueckt wird.
**Was zu tun:**
1. Im MIDI-Patch-Dialog: Modus-Auswahl "Toggle" (aktuelles Verhalten) vs. "Momentary".
2. Im Momentary-Modus: `note_on` → Effekt starten, `note_off` → Effekt stoppen.
3. LED-Feedback: Pad leuchtet solange die Taste gehalten wird, geht beim Loslassen aus.
4. Kompatibel mit dem bestehenden LED-Feedback-System (MIDI-01/02).

---

### MIDI-04: Bestehende LED-Optionen ueberarbeiten und erweitern
**Problem:** Die vorhandenen Optionen (statische Farbe, Effekt-Feedback,
An/Aus) sind ein guter Anfang, aber noch nicht flexibel genug.
**Was zu tun:**
1. Bestandsaufnahme: Welche LED-Optionen gibt es aktuell, wo sind sie implementiert?
2. Fehlende Modi ergaenzen:
   - **Blink** – Pad blinkt solange Funktion aktiv ist
   - **Puls** – Pad pulsiert (Helligkeit auf/ab) waehrend Effekt laeuft
   - **Farbe aus Effekt** – Pad zeigt die aktuelle Effekt-Ausgabefarbe
3. Alle Modi im MIDI-Patch-Dialog auswaehlbar machen.

---

## 14) Programmer – Gesamt-Layout / Arbeitsflaeche neu aufteilen (NEU 2026-06-01)

### ✅ LAYOUT-01..07 (Grundgeruest + Zonen) — ERLEDIGT 2026-06-01
**Erledigt:** `ProgrammerView` (`src/ui/views/programmer_view.py`) hat jetzt ein
umschaltbares 5-Zonen-Layout neben dem klassischen. Toolbar-Button „Layout:
Klassisch/Zonen" (Default = Klassisch, Wahl persistiert in
`%APPDATA%/LightOS/ui_prefs.json`). Zonen: LINKS Fixture-/Gruppen-Auswahl
(LAYOUT-02), MITTE Kategorie-Leiste Farben/Dimmer/Bewegung/Weitere/Effekte/EFX als
QStackedWidget (LAYOUT-03 / P-05; Farben/Dimmer/Bewegung springen auf den passenden
Attr-Tab, Effekte = Assistent + Funktions-Start/Stop, EFX = eingebettete EfxView),
RECHTS `SnapFilePanel` als Datei-Browser (LAYOUT-04), UNTEN ausklappbare
`FixtureTilePreview` (NEU `src/ui/widgets/fixture_tile_preview.py`, spiegelt live
Farbe/Dimmer der Auswahl, P-06/LAYOUT-05), OBEN-RECHTS geraeteunabhaengige
`EffectMiniPreview` (NEU `src/ui/widgets/effect_mini_preview.py`, Demo-Geometrie ueber
RgbMatrixInstance, P-07/LAYOUT-06). Umschalten baut den Body neu und refresht aus dem
State (kein Datenverlust). Tests `tests/test_programmer_zones.py` (5); 153 Tests gruen
+ Headless-MainWindow-Bau verifiziert.
**Offen (spaeter):** UNTEN Strobo/Lauflicht-Animation; RECHTS echtes „Programme"-Modell
(ARC-05) statt Snaps; AUDIT-02-Konsolidierung der dann doppelten EfxView/SnapFilePanel.

> **Leitidee (vom Nutzer):** Der Programmer wird komplett ueberarbeitet und bekommt ein
> festes 5-Zonen-Layout. Statt vieler verstreuter Reiter und Panels gibt es klar getrennte
> Bereiche: **links waehlen, was programmiert wird → in der Mitte programmieren → rechts die
> Ordnerstruktur → unten die ausklappbare Matrix-Vorschau der Lampen → oben rechts eine
> geraete-unabhaengige Mini-Preview des gewaehlten Effekts.**
>
> Dieser Abschnitt ist die **Dachvorgabe**. Die Einzelpunkte P-02 bis P-08 ordnen sich hier ein
> (P-06 = Zone UNTEN, P-07 = Zone OBEN RECHTS, P-05 = Kategorie-Tabs in Zone MITTE).

### Zonen-Skizze (Soll-Zustand)

```
┌──────────┬─────────────────────────────┬──────────────┐
│  LINKS   │            MITTE             │   OBEN-RE.   │
│          │                             ├──────────────┤
│ Auswahl  │  Programmieren / Effekte    │              │
│ WAS pro- │  generieren – mit Reitern   │   RECHTS     │
│ gram-    │  (Farben · Effekte · EFX ·  │              │
│ miert    │  Dimmer · Bewegung …)       │  Ordner-     │
│ wird     │                             │  struktur    │
│          │                             │  (Programme/ │
│ (Gruppen,│                             │   Dateien)   │
│ Fixtures,│                             │              │
│ Ziel)    │                             │              │
├──────────┴─────────────────────────────┴──────────────┤
│  UNTEN: ausklappbare Matrix-Ansicht (Effekt-Vorschau   │
│         der Lampen, 2D-Kacheln)                        │
└────────────────────────────────────────────────────────┘
   (OBEN RECHTS = kleine, geraete-unabhaengige Effekt-Preview)
```

---

### LAYOUT-01: 5-Zonen-Grundgeruest des Programmers anlegen
**Ziel:** Den Programmer-Bereich auf ein festes Layout mit fuenf Zonen umstellen.
**Was zu tun:**
1. Programmer-Sektion als Splitter-Layout aufbauen:
   - Aeusserer horizontaler Splitter: **LINKS | MITTE | RECHTS**
   - Vertikaler Splitter um MITTE: **MITTE oben | UNTEN (Matrix-Vorschau)**
   - **OBEN RECHTS** als kompaktes Preview-Dock ueber/neben der rechten Spalte.
2. Zonen-Groessen frei ziehbar (QSplitter), sinnvolle Startbreiten setzen.
3. UNTEN ein- und ausklappbar (Toggle-Button oder Splitter-Griff), Zustand merken.
4. Bestehende Programmer-Inhalte den Zonen zuordnen (siehe LAYOUT-02…06).

---

### LAYOUT-02: Zone LINKS – Auswahl "Was wird programmiert?"
**Ziel:** Linke Spalte = Einstiegspunkt. Hier waehlt der Nutzer das Ziel der Programmierung.
**Was zu tun:**
1. Liste/Baum mit:
   - **Gruppen** (oben, primaer)
   - **Einzel-Fixtures** (aufklappbar unter der jeweiligen Gruppe)
   - optional **Programm-Ziel** (neues Programm vs. bestehendes bearbeiten)
2. Auswahl hier steuert, was in der MITTE programmiert wird (Kontext-Bindung).
3. Mehrfachauswahl moeglich (mehrere Gruppen/Fixtures gleichzeitig).
4. Aktive Auswahl optisch hervorheben; spiegelt sich in der Preview (OBEN RECHTS).

---

### LAYOUT-03: Zone MITTE – Programmieren & Effekte generieren (mit Reitern)
**Ziel:** Mittlere Spalte = eigentliche Arbeitsflaeche zum Programmieren und
Effekte-Generieren, organisiert in Reitern.
**Was zu tun:**
1. Reiter (Tabs) oben in der MITTE, z. B.:
   - **Farben** · **Effekte (Generator/Assistent)** · **EFX** · **Dimmer** · **Bewegung**
     (siehe Kategorie-Liste in P-05).
2. Der gewaehlte Reiter zeigt das passende Eingabe-Panel.
3. Inhalt bezieht sich immer auf die Auswahl aus Zone LINKS.
4. Bestehende Programmer-/EFX-/Funktionen-Views hier einbetten (Umzug aus P-01 fortfuehren).

---

### LAYOUT-04: Zone RECHTS – Ordnerstruktur (Programm-/Datei-Browser)
**Ziel:** Rechte Spalte = Datei-/Ordnerbaum fuer gespeicherte Programme, Effekte, Szenen.
**Was zu tun:**
1. Baum-Ansicht der gespeicherten Programme/Effekte (knuepft an ARC-05 „Programme" an).
2. Doppelklick laedt ein Programm zur Bearbeitung in die MITTE.
3. Drag/Drop oder Kontextmenue zum Zuweisen auf MIDI / virtuelle Konsole.
4. Ordner anlegen/umbenennen/loeschen fuer eigene Sortierung.

---

### LAYOUT-05: Zone UNTEN – ausklappbare Matrix-Ansicht (Lampen-Vorschau)
**Ziel:** Untere, ausklappbare Leiste zeigt die **Matrix-Vorschau der echten Lampen** –
also was der Effekt auf den ausgewaehlten Fixtures macht.
**Setzt um:** P-06 (Live-Vorschau der RGB-Matrix), hier als Zone verankert.
**Was zu tun:**
1. 2D-Kachel-Grid, das die aktuell ausgewaehlten Fixtures/Gruppen abbildet.
2. Live-Spiegelung des Programmierer-Outputs (Farbe, Dimmer, Strobo, Lauflicht).
3. Ein-/ausklappbar; eingeklappt nur als schmale Leiste mit Toggle.
4. Kein 3D – rein 2D, ressourcenschonend.

---

### LAYOUT-06: Zone OBEN RECHTS – geraete-unabhaengige Mini-Effekt-Preview
**Ziel:** Kleine Vorschau oben rechts, die **unabhaengig von den real gepatchten Strahlern**
zeigt, was ein Effekt tun wuerde, sobald man ihn auswaehlt – eine Art neutrale
„So sieht der Effekt aus"-Anzeige.
**Abgrenzung:** UNTEN (LAYOUT-05) zeigt die echten ausgewaehlten Lampen; OBEN RECHTS zeigt
den Effekt generisch (z. B. eine Standard-Reihe/Matrix von Demo-Pixeln), zum Vergleichen
und Aussuchen von Effekten – auch ohne Fixtures.
**Knuepft an:** P-07 (Mini-Uebersicht), hier neu oben rechts statt unten rechts verortet.
**Was zu tun:**
1. Kompaktes Preview-Widget oben rechts (feste Demo-Geometrie, z. B. 1×8 oder kleine Matrix).
2. Beim Auswaehlen/Hovern eines Effekts (in Zone MITTE oder RECHTS) spielt die Preview
   den Effekt sofort generisch ab.
3. Voellig entkoppelt vom realen Patch/Output – nur Anschauung, keine DMX-Ausgabe.
4. Optional: laeuft als Endlosschleife, damit man Effekte in Ruhe vergleichen kann.

---

### LAYOUT-07: Bestehende Einzel-Tasks ins Zonen-Layout einordnen
**Ziel:** Sicherstellen, dass die alten Programmer-Tasks nicht doppelt/widerspruechlich umgesetzt werden.
**Zuordnung:**
- **P-01** (Reiter-Umzug) → MITTE (LAYOUT-03)
- **P-02/P-03** (Matrix-Vorschau-Bugs, Start/Stopp) → relevant fuer UNTEN (LAYOUT-05)
- **P-04** (Matrix-Standard fuer Gruppen) → Auswahl LINKS + Tab-Default MITTE
- **P-05** (Kategorie-Auswahl) → Reiter in MITTE (LAYOUT-03)
- **P-06** (RGB-Matrix-Preview) → UNTEN (LAYOUT-05)
- **P-07** (aktive Gruppen/Lampen) → OBEN RECHTS (LAYOUT-06)
- **P-08** (Hilfe-Popups) → gilt zonenuebergreifend
**Was zu tun:** Beim Umsetzen jeweils auf den zugehoerigen LAYOUT-Punkt verweisen,
damit Platzierung und Bug-Fix zusammenpassen.
