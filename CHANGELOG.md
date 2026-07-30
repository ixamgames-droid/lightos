# Changelog

Alle nennenswerten Aenderungen an LightOS werden hier dokumentiert.
Format: [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)

---

## [Unreleased]

### 2026-07-31 — Der Galerie-Generator schrieb Bilder um, die sich nicht geändert hatten

#### Behoben

- **`tools/gen_vc_gallery.py` churnte bei jedem Lauf sechs GIFs im Diff
  (GDS-6).** Der Docstring versprach eine deterministische Ausgabe — und auf
  einem Rechner stimmt das: zwei Laeufe in getrennten Prozessen liefern
  byte-identische Dateien. Verschieden werden sie **zwischen Umgebungen**: die
  committeten GIFs stammen vom alten Windows-ARM-Rechner und sind gegenueber
  der frischen Linux-Ausgabe **Frame fuer Frame pixelgleich, aber anders
  kodiert** (die adaptive Palette des GIF-Writers haengt an der Pillow-Version).

  Der Riegel sitzt jetzt beim Schreiben, nicht beim Kodieren: verglichen werden
  **Pixel statt Bytes**, und die Datei wird nur bei echter Bildaenderung
  angefasst. Eine feste Palette haette das nicht geloest — auch der Rest des
  Writers kann sich zwischen Versionen aendern. PNG- und GIF-Pfad laufen ueber
  denselben Vergleich.

  Wirkung: ein Lauf ohne inhaltliche Aenderung laesst `git status` leer, statt
  sechs Binaerdateien anzufassen.
### 2026-07-31 — Die eingebettete 3D-Ansicht rechnete nach einem Qualitätswechsel weiter in alter Stufe

#### Behoben

- **Wer die Render-Qualität umstellt, während die eingebettete
  Live-View-3D-Ansicht gerade nicht sichtbar ist, bekam sie danach in der ALTEN
  Stufe zurueck (A3D-23).** „Szene neu laden" faehrt nur die **aktiven** Targets
  neu, und der angedockte Spiegel ist im 2D-Modus bzw. auf einem anderen Tab
  inaktiv. Beim Wiedereinblenden wurde er zwar reaktiviert und resynct, die
  Seite aber nicht neu geladen — und die Stufe reist als `gputier`-Query in der
  Seiten-URL, ist also eine Konstruktor-Entscheidung des Renderers und nicht
  nachpushbar. Die alte Stufe blieb bis zum naechsten Reload aus anderem Grund
  (Crash, aktiver Reload, App-Neustart).

  `load_stage_html` merkt sich jetzt, mit welcher Stufe es eine Seite geladen
  hat; beim Einblenden wird verglichen und bei Abweichung neu geladen.

### 2026-07-31 — Die F-Taste im Visualizer tat nie, was das Menü versprach

#### Behoben

- **„⛶ Fit Auswahl  (F)" stand im Kamera-Menü, die Taste sprang aber immer nur
  auf den Fixtures-Tab (A3D-29).** Der Qt-Shortcut haengt mit
  WindowShortcut-Kontext am Fenster und gewann jedes Mal; die WebEngine-Canvas
  bekam die Taste gar nicht erst zu sehen, ihr in-page-Handler lief also nie.

  Aufgeloest wird der Konflikt **nach dem Fokus** statt durch Wegnehmen — beide
  Bedeutungen waren dokumentiert: liegt der Tastaturfokus auf der 3D-Ansicht,
  heisst F jetzt „Fit Auswahl", sonst weiterhin Fixtures-Tab.

  Die Fokus-Pruefung geht dabei ueber die Elternkette des `focusWidget()`:
  `QWebEngineView.hasFocus()` allein meldet `False`, weil der Fokus in einem
  internen Kind-Widget liegt — die Weiche haette also genau in dem Fall falsch
  abgebogen, fuer den sie da ist.

### 2026-07-30 — Gespeicherte Kamera schaltete die Ansicht um, die Toolbar merkte es nicht

#### Behoben

- **Eine gespeicherte 2D-Kamera brachte die Szene in den Top-Down-Modus, die
  Ansicht-Combo der Toolbar blieb aber auf „3D Perspective" stehen (A3D-32).**
  `applyNamedCamera` stellt drueben zuerst den gespeicherten View-Modus wieder
  her — sonst mutierte das Anwenden nur die *inaktive* Kamera und sichtbar
  passierte nichts. Einen JS→Python-Rueckkanal fuer den Modus gibt es aber
  nicht, also lief die Combo aus dem tatsaechlichen Szenen-Modus. Der naechste
  Python-seitige `push_view_mode` — z. B. nach einem Seiten-Reload, der den
  **Combo-Stand** pusht — schaltete die Szene dann unerwartet zurueck.

  Gefixt ohne neues Signal: jeder Weg in `applyNamedCamera` kommt ohnehin ueber
  die Bridge aus Python, der Modus ist dort also bereits bekannt. Die Combo
  wird beim Anwenden mitgezogen (ohne Rueckschlag an JS), die Hoehen-Zeile
  folgt mit — im 2D-Modus ist der Y-Spinner wirkungslos.

### 2026-07-30 — Die Geräteliste im Visualizer zeigte etwas anderes als die Szene daneben

#### Behoben

- **Wählt man Geräte im Programmer (oder per Marquee im 3D), leuchteten zwar die
  Outlines in der Szene — die Geräteliste im Visualizer blieb aber auf dem alten
  Eintrag stehen.** Zwei Anzeigen derselben Auswahl, nebeneinander, mit
  verschiedenem Inhalt. Der offen gebliebene Review-Fund aus VIZ-14 Slice 1b ist
  damit erledigt: `_mark_patch_list` zieht die gemeinsame Auswahl in die Liste
  nach — beim Auswahl-Ereignis **und** nach jedem Neuaufbau der Liste.

  Die Liste steht dafuer auf Mehrfachauswahl (vorher der Single-Default, mit dem
  sich von drei gewaehlten Geraeten nur eines zeigen liess), und die
  Gegenrichtung meldet seither **alle** markierten Geraete statt nur des
  aktuellen — sonst hiesse dieselbe Liste in der einen Richtung „diese drei" und
  in der anderen „das eine".

  Zwei Fallen dabei, beide vom Test gefangen: `blockSignals` ist hier der
  Clobber-Riegel (ohne ihn schriebe jeder markierte Eintrag einzeln zurueck, und
  die Zwischenstaende waeren fuer Programmer/EFX/Matrix echte
  Auswahl-Aenderungen), und `setCurrentItem` raeumt im Mehrfachmodus die eben
  gesetzte Markierung wieder ab (Default-Kommando `ClearAndSelect`) — es braucht
  `NoUpdate`. Das aktuelle Element wandert nur, wenn es aus der Auswahl faellt:
  an ihm haengen die Positions-/Rotationsfelder.

### 2026-07-30 — Der zweite Spider-Arm war weg, sobald ein Mover danebenstand

#### Behoben

- **Position-Tab, gemischte Auswahl: die zweite Tilt-Bar eines Spiders war
  ueberhaupt nicht mehr erreichbar (A3D-36).** Der Tab schaltet auf die
  Spider-Bedienung (SpiderPositionTool statt Pan/Tilt-Regler) nur um, wenn
  **alle** gewaehlten Geraete Dual-Tilter sind. Stand daneben ein gewoehnlicher
  Moving Head, fiel der Tab in den generischen Regler-Loop — und der baut aus
  dem **pro Attribut deduplizierten** Template genau EINEN `tilt`-Regler fuer
  beide Geraete. Am echten Bau gemessen (ZQ-B20 Mini Spider [15 Channel] +
  HYDRABEAM 4000 RGBW [19-Kanal]):

  ```
  vorher   tilt head=0 -> [1, 2]     pan head=0 -> [1, 2]
  nachher  tilt head=0 -> [1]        tilt head=1 -> [1]      (Spider: je Bar)
           tilt head=0 -> [2]        pan  head=0 -> [2]      (Mover)
  ```

  Nebenbefund derselben Zeile: der `pan`-Regler zielte auch auf den Spider —
  ein Geraet **ohne Pan-Kanal**.

  Gebaut ist die Zwei-Eimer-Aufteilung, die `_add_color_head_sliders` seit
  FM-HEADLAYOUT Slice 2 vormacht. **Bewusst nicht** der naheliegende
  `(attribute, head)`-Schluessel fuer das ganze Template: ueber die Library
  gezaehlt kommt `raw` in 831 Modi mehrfach vor, `macro` in 822, Spitzenwerte
  bis 24 Vorkommen — das erzeugte dort Hunderte Regler. Die beiden reinen
  Faelle (nur Spider / nur Mover) bleiben unveraendert.

### 2026-07-30 — Den Kopf endlich auch tippen können (FM-9 vollständig)

#### Neu

- **Kopf-Syntax in der Kommandozeile: `1:2 @ 50` spricht genau einen Kopf an.**
  Bisher folgte die Kommandozeile zwar der *geklickten* Kopf-Auswahl (A7),
  aber `1:2` selbst war ein einziges Wort-Token — der Lexer brach Worte nur an
  `+ - @` und Leerzeichen — und endete in „Unbekannter Befehl". Jetzt:

  ```
  1:2 @ 50       # nur Kopf 2 von Geraet 1
  1:2 pan 128    # derselbe Kopf ueber den Attribut-Pfad
  2 + 1:3        # ganzes Geraet 2 und Kopf 3 von Geraet 1
  ```

  **Gezaehlt wird, wie beschriftet wird:** `1:1` ist der erste Kopf — so wie
  das `K1` im Programmer, EFX-Editor, Faecher-Werkzeug und Gruppen-Raster
  (alle `f"K{head + 1}"`). Intern bleibt das Zellformat `"fid:head"`
  0-basiert; die Umrechnung passiert an genau einer Stelle. `1:0` wird
  ausdruecklich abgewiesen, statt still auf Kopf 1 zu zeigen.

#### Behoben

- **Ein getippter Kopf, den es fuer dieses Attribut nicht gibt, faellt nicht
  mehr still auf „alle Koepfe" zurueck.** Die Kopfzahl haengt am Attribut,
  nicht am Geraet: eine HYDRABEAM 4000 RGBW [19-Kanal] hat 4 Pan, 5 Intensity
  und **eine** Farbbank. `1:2 red 200` meldet dort jetzt „Gerät 1 hat für
  'color_r' nur einen Kopf" und schreibt **nichts** — vorher waere daraus
  entweder ein `color_r#1` ohne Kanal geworden (der Kopf faellt auf seinen
  Default) oder, bei stillem Rueckfall, volle Farbe auf allen Koepfen. Eine
  *geklickte* Auswahl darf still zurueckfallen, weil sie implizit ist; eine
  getippte ist eine Ansage.

- **Ein Kopf-Ziel, dessen Kanalzahl der Kopfzahl widerspricht, wird abgelehnt
  statt geraten.** Die Hydrabeam legt ihre fuenf Intensity-Kanaele als
  `CH1 Master Dimmer` + `CH9/12/15/18 Kopf 1..4 Dimmer` an — das
  `attr#N`-Vokabular zaehlt aber Vorkommen, `1:2 @ 50` waere dort also CH9 =
  „Kopf 1 Dimmer", ein Kopf daneben. Ueber die Library ausgezaehlt betrifft das
  **123 von 5116 Modi**. Die Kommandozeile sagt jetzt, dass sie es nicht
  aufloesen kann; die dahinterliegende Sache (auch die *geklickten* Wege sind
  betroffen) ist als **FM-17** erfasst — sie beruehrt gespeicherte Shows und
  ist keine Nebenbei-Aenderung.

- **Drei Grammatik-Stellen haetten eine Kopf-Zelle kommentarlos geschluckt** —
  eine davon kehrte sich sogar um: bei `1 thru 4 - 2:1` lieferte
  `consume_number()` fuer die Zelle `None`, die Zelle blieb im Strom stehen und
  der naechste Schleifendurchlauf haette sie **addiert** statt abgezogen.
  Ebenso `all 1:2 @ 50` (haette alle Geraete voll aufgezogen) und `1:2 thru 4`
  (Zelle verloren). Alle drei sind jetzt klare Fehlermeldungen.

### 2026-07-30 — Die Statustabellen hinkten dem eigenen Tag hinterher

#### Behoben

- **Die README-Statustabelle beschrieb einen Stand, den derselbe Tag dreimal
  überholt hatte.** Sie sagte „GitHub-CI faehrt bisher nur Windows" (seit
  [#486](https://github.com/ixamgames-droid/lightos/pull/486) fährt sie auf
  `ubuntu-latest` die **volle** segmentierte Suite, 6 min 55 s) und bei den
  Mehrkopf-Geräten „**Offen:** Kommandozeile und MIDI-Mapping schreiben noch
  geraeteweit" — beides ist mit FM-9/A6 und A7 erledigt, offen ist dort nur noch
  eine *getippte* Kopf-Syntax (`1:2 @ 50`).

  Die Plattform-Tabelle weiter oben war mit
  [#484](https://github.com/ixamgames-droid/lightos/pull/484) korrekt gezogen
  worden — die Statustabelle am Dateiende nicht. Zwei Tabellen über dasselbe
  Thema in einer Datei, von denen nur eine gepflegt wird, sind schlimmer als
  eine ungenaue: der Leser findet zuerst die falsche.

- **`docs/OPEN_POINTS_OVERVIEW.md` verlangte für `F-8` (Enttec-Langzeit) einen
  Auto-Reconnect/Health-Check, den es längst gibt** — Fehler-Watchdog
  (`FAIL_LIMIT=20` → Auto-Disable, OUT-02) und gedrosselter Reconnect samt
  VID/PID-Neusuche (SERIAL-02) sind seit Langem im `EnttecPro`. Der Eintrag
  nennt jetzt die verbliebene, rein empirische Frage und das Messergebnis des
  ersten Laufs (3,8 h, 540.225 Frames, 0 Schreibfehler) samt seiner Grenze: der
  *stille* Tod ist ohne Gerät an der Leitung nicht messbar.

### 2026-07-30 — Der Statusbalken log weiter, und das Verifikations-Werkzeug auch

#### Behoben

- **HW-5b war unvollständig: der Statusbalken meldete im echten Betrieb weiter
  grün „Enttec: COM_FAKE aktiv (1 Universe)".** `add_enttec` legt nämlich auch
  für einen unmöglichen Port ein Gerät an — der Subprozess-Proxy scheitert nicht
  sofort —, also war `_enttec_outputs` gefüllt und der `if offene:`-Zweig gewann
  über den Problem-Hinweis. Genau die Lüge, die HW-5b beseitigen sollte, nur mit
  neuem Text.

  Der Befund schlägt jetzt die Registrierung: ein registrierter Adapter auf
  einem unmöglichen Port **ist** der stille Fehlerfall. Verifiziert am laufenden
  Programm — Statusbalken steht bernsteinfarben auf „Enttec: falsch
  konfiguriert", Grund im Tooltip.

  **Headless nicht aufgefallen**, weil die Tests für den Problemfall
  `offene={}` annahmen. Der neue Test fährt den realen Fall (Hinweis **und**
  registriertes Gerät).

- **Das App-Steuerskript für UI-Verifikationen fotografierte still das falsche
  Fenster — und `restart` war ein No-op.** Drei Fehler auf einmal:

  1. `_win_id` suchte per `grep -F "LightOS"` über die Fenstertitel und traf
     damit **Firefox** („Second Brain — LightOS Backlog — Mozilla Firefox").
     `shot -w` lieferte einen perfekt aussehenden Screenshot des
     Backlog-Dashboards statt der App.
  2. Das PID-File hält die PID von `start.sh`, die sich sofort beendet →
     `stop` meldete „läuft nicht", **während die App lief**, und `restart` wurde
     still zum No-op. Man screenshottet dann den alten Build.
  3. Der Fallback in `cmd_stop` suchte den **absoluten** Pfad, die echte
     Kommandozeile ist aber relativ — er konnte nie greifen.

  Fenstersuche läuft jetzt über den **Prozessbaum** der App (der Fensterprozess
  ist ein Kind von `start.sh`), Titel-Fallback nur noch **exakt**; die
  Prozesssuche gleicht über das **Arbeitsverzeichnis** ab statt über die
  Pfad-Schreibweise.

- **`bin/app.sh` → `tools/app.sh` (im Repo).** Es lag draußen mit der Begründung
  „wie `run_tests.ps1` auf Windows" — derselbe falsche Vergleich wie bei
  XPLAT-11: `run_tests.ps1` serialisiert parallele Windows-Sessions und ist
  maschinenspezifisch, an der App-Steuerung ist nichts rechnerspezifisch, und ihr
  Gegenstück `tools/app.ps1` liegt ohnehin im Repo. Die Folge war dieselbe wie
  damals: ein frischer Checkout hatte kein Werkzeug, und drei Fehler blieben
  ungetestet und unreviewed liegen. `bin/app.sh` bleibt als Weiterleitung.

  **Lehre:** ein Verifikations-Werkzeug, das still das Falsche misst, ist
  schlimmer als keines — es erzeugt Belege, die keine sind.

### 2026-07-30 — Ein überholtes Bühnen-Echo rollte Positionen zurück (A3D-31)

#### Behoben

- **Ein Echo mit älterem Sequenz-Token konnte Position, Größe, Rotation und
  Farbe eines Bühnenelements zurückrollen.** `_on_stage_list_from_js` prüfte
  `is_stale` nur im **Create**-Zweig; der Update-Zweig für bereits vorhandene
  Elemente wandte die Werte aus dem Echo **unbedingt** an. Der Docstring nannte
  das „idempotent-harmlos".

  Das stimmt aber nur, wenn der überholte Snapshot zufällig dieselben Werte
  trägt. Trug er ALTE Werte für eine id, die inzwischen verschoben, gedreht oder
  umgefärbt wurde, dann landeten sie im autoritativen Modell, `_stage_dirty`
  wurde gesetzt, und `_sync_stage_node_to_scene` + `_push_stage_rotation_to_children`
  schoben sie an JS **und an gedockte Fixtures** weiter — ein **Rollback** statt
  eines No-op, bis in die gespeicherte Bühne hinein.

  Der Guard steht jetzt vor **beiden** Zweigen: ein überholtes Echo schreibt gar
  nichts. Die Reparatur-Teile derselben Funktion (Nachsenden fehlender Elemente,
  Pending-Gate) laufen unberührt weiter — die kümmern sich darum, was JS fehlt,
  nicht darum, was Python glauben soll.

  `tests/test_a3d31_stale_echo_no_rollback.py` (8), **gegengeprüft**: mit der
  alten Guard-Position fallen genau die vier Rollback-Tests, während die Tests
  für frische Echos grün bleiben — der Fix macht das Drag-Ende also nicht kaputt.

### 2026-07-30 — Gelöschte Bühnenobjekte kamen zurück (A3D-30 + A3D-12)

#### Behoben

- **Ein im 3D gelöschtes Bühnenobjekt konnte wieder auferstehen.**
  `_on_stage_object_deleted_from_js` verwarf eine Löschung, sobald **irgendein**
  `addStageData` für dieselbe id in der Poll-Queue hing. Gerechtfertigt war das
  nur mit Undo/Redo-Interleaving — aber genau dieselbe Event-Form entsteht bei
  der **automatischen** Wiederherstellung: der 1200-ms-Reassert nach jedem
  Stage-Load und der ≤3×-Nachsende-Mechanismus bei einem Teil-Snapshot füllen
  die Queue mit `addStageData` für *jedes* Element.

  Der Guard konnte beides nicht unterscheiden — es gab kein Token. Folgen, beide
  still: die Löschung erreichte das autoritative `_current_stage` nie, und das
  noch eingereihte Add baute das Objekt in JS wieder auf.

  Es gibt vier Sender von `addStageData`, und sie teilen sich sauber:

  | Sender | Art |
  |---|---|
  | `_reassert_current_stage_after_load` (+1200 ms) | automatisch |
  | `_on_stage_list_from_js` (≤3× Nachsenden) | automatisch |
  | `_on_add_change` (Nutzer legt an / Redo) | Nutzergeste |
  | `_on_delete_change` else-Zweig (Undo) | Nutzergeste |

  Genau diese Unterscheidung trägt jetzt das Flag `reassert` — **in der
  Payload**, weil die JS-Seite es auch braucht (s. u.); ohne Flag bleibt die
  Payload byte-identisch zum Bestand. Der Guard prüft nur noch auf echte
  Nutzer-Re-Adds, und beim Anwenden einer Löschung werden eingereihte
  Reassert-Adds für dieses Element aus der Queue geworfen — sonst stellt der
  nächste Poll genau das wieder her, was gerade gelöscht wurde.

- **A3D-12, gemeinsam gelöst wie 2026-07-27 vorgezeichnet:** der inkrementelle
  Add-Kanal in JS respektiert jetzt den Lösch-Tombstone. `loadStageJson`s
  Repair-Loop tat das schon immer, `jsAddStageObjectData` nicht — ein verspätet
  zugestelltes `addStageData` baute das Objekt neu auf **und** hob per
  `createStageObject` seinen Tombstone auf. Neu exportiert
  `stage_objects.isUserRemoved(id)`, bewusst ein Prädikat statt des Sets.

  **Nur `reassert`-Adds werden abgewiesen:** ein echtes Undo/Redo-Re-Add ist eine
  bewusste Nutzergeste und muss den Tombstone aufheben dürfen. Der Szenentest
  hält beide Richtungen fest.

#### Geprüft und ausgeschlossen

Das Flag hätte an zwei Stellen lecken können — beides nachgesehen statt
angenommen: `StageElement.to_js_dict()` liefert ein **frisches Literal** (das
Element selbst kann nicht korrumpiert werden), und `getStageJson()` baut eine
**explizite Whitelist**, `updateStageObjectProps` übernimmt keine fremden Keys —
`reassert` kann also nicht in eine gespeicherte Bühne gelangen.

#### Tests

`tests/test_a3d30_stage_delete_vs_reassert.py` (10) für die Python-Guards, plus
ein Szenentest in `test_viz13_scene_modules_smoke.py` mit echtem QtWebEngine.
Beide **gegengeprüft**: ohne den jeweiligen Fix schlagen sie fehl — der
Python-Test hält den alten Guard wörtlich daneben, der JS-Test wurde mit
entferntem Guard rot gesehen.

### 2026-07-30 — Die Kommandozeile hielt sich nicht an den Auswahl-Vertrag (FM-9/A7)

#### Behoben

- **Nach `1 thru 3` in der Kommandozeile erfuhr kein einziger Konsument davon —
  und eine vorherige Kopf-Auswahl überlebte still.** Die Kommandozeile war der
  letzte Schreiber, der `state.selected_fids` **roh als Attribut** setzte, also
  an `set_selected_fids` vorbei. Genau die Fehlerklasse, die FM-9 beseitigen
  sollte („zweites Feld, das ein Schreiber vergisst"): `set_selected_fids`
  **delegiert** an `set_selected_cells` und pflegt damit die feine Kopf-Auswahl
  mit — eine rohe Zuweisung tut das nicht.

  An einem echten `AppState` mit drei Hydrabeams gemessen, nach `1 thru 3`:

  | | |
  |---|---|
  | `selected_fids` | `[1, 2, 3]` — richtig |
  | `selected_cells` | `['2:1']` — die **alte** Kopf-Auswahl, unverändert |
  | `SELECTION_CHANGED` | **0 Events** |

  Zwei Folgen, beide still: Programmer, EFX, Matrix, Live-View, Laser und
  Visualizer bekamen von der neuen Auswahl nichts mit, und eine spätere Aktion
  (Fächer, Snap, EFX, XY-Pad) blieb auf „Kopf 2 von Gerät 2" eingeschränkt,
  obwohl der Nutzer gerade drei ganze Geräte gewählt hatte.

  Alle sechs Zugriffsstellen (`SetValueCommand`, `SelectionCommand`,
  `ClearCommand`, `HighlightCommand`, `LowlightCommand`) laufen jetzt über zwei
  Helfer `_set_selection` / `_get_selection`. Der Fallback auf die rohe Zuweisung
  bleibt bewusst bestehen: die Kommandozeile wird auch gegen Minimal-States
  gefahren, die kein `set_selected_fids` mitbringen — ohne Fallback verschwände
  dort eine `AttributeError` im `except` des Aufrufers, also in genau der
  Fehlerklasse, die hier behoben wird.

- **Und damit die letzte Programmer-Fläche aus FM-9:** ein `@ 50` ohne genannte
  Selektion respektiert jetzt die Kopf-Auswahl. Die Kopfzahl folgt dabei dem
  **Attribut** (`head_counter_for_attr`, A6) — bei einer `HYDRABEAM [19-Kanal]`
  landet `pan 128` auf `pan#1`, `red 200` dagegen geräteweit, weil es dort nur
  eine Farbbank gibt und `color_r#1` ein Schlüssel ohne Kanal wäre.

  **Bewusste Abgrenzung:** wer eine Selektion *tippt* (`2 @ 50`), meint das
  ganze Gerät — nicht den zuletzt gewählten Kopf. Nur der Fallback auf die
  gespeicherte Auswahl kann kopf-fein sein.

  `tests/test_fm9_cmdline_selection_contract.py` (9) fährt die Messung oben
  gegen den **echten** `AppState`; ein Fake hätte den Bug nicht zeigen können,
  weil er die Delegation gar nicht hat.

### 2026-07-30 — MIDI-„Programmer Attribut" fasste alle 30 Geräte an (FM-9/A6)

#### Behoben

- **Ein MIDI-Fader mit der Aktion „Programmer Attribut" schrieb auf *jedes*
  gepatchte Gerät — unabhängig davon, was gewählt war.** `_execute_continuous`
  lief stur über `get_patched_fixtures()`. Auf keinem Lichtpult ist das das
  erwartete Verhalten eines so beschrifteten Reglers.

  Die Reichweite folgt jetzt dem im Projekt etablierten Muster von
  `VCXYPad._resolve_fids`: **Auswahl, sonst alle gepatchten.** Der Alt-Fall
  „nichts gewählt" bleibt damit byte-identisch — wer den Fader als globalen
  Attribut-Regler benutzt hat, merkt keinen Unterschied, solange er nichts
  selektiert.

- **Und damit auch die Kopf-Auswahl** (letzte Programmer-Fläche außer der
  Kommandozeile): „Kopf 2" gewählt → der Regler schreibt nur auf diesen Kopf.

#### Der interessante Teil: die Kopfzahl hängt am Attribut

Bei FM-9/A5 war die Erkenntnis, dass Farb- und Bewegungsköpfe verschiedene
Zahlen sind. Hier zeigt sich, dass das noch zu grob war: eine
`HYDRABEAM 4000 RGBW [19-Kanal]` hat **4 Pan, 4 Tilt, 5 Intensity und 1
Farbbank**. „Wie viele Köpfe hat dieses Gerät" hat dort drei verschiedene
richtige Antworten — je nachdem, was man schreibt.

Neu `app_state.attr_head_count_for_channels()` plus `head_counter_for_attr()`:
die allgemeinste der drei Zählungen, von der Farb- und Bewegungs-Zählung
Spezialfälle sind. Sie spiegelt schlicht `channel_occurrence_keys`, das jedes
Attribut für sich zählt (`A#N` = N-tes Vorkommen von `A`).

`tests/test_fm9_midi_programmer_scope.py` (13) fährt **dasselbe Gerät mit
derselben Auswahl** und prüft, dass Pan die Kopf-Einschränkung behält, Farbe sie
fallen lässt (sonst `color_r#2` — ein Schlüssel ohne Kanal, der Kopf fiele auf
seinen Default) und Intensity wieder anders zählt.

### 2026-07-30 — Der Enttec-Ausgang war tot und der Statusbalken sagte „OK" (HW-5b)

#### Behoben

- **Nach dem Linux-Umzug ging gar kein DMX über den Enttec — und nichts sagte es.**
  `data/universes.json` trug für das Enttec-Universe noch `"patch": "COM_FAKE"`,
  einen Windows-Rest; auf Linux heißt dasselbe Gerät `/dev/ttyUSB0`.
  `EnttecPro("COM_FAKE")` konnte nur werfen, und die Exception verschwand im
  `except` von `apply_output_config`.

  **Die eigentliche Bosheit war der Statusbalken.** `_check_hardware` fragte nur
  `find_enttec_port()` — also ob per VID/PID *irgendein* Enttec am Rechner hängt.
  Ob ein Universe ihn auch benutzt, interessierte ihn nicht. Also stand dort
  grün „Enttec: /dev/ttyUSB0 OK", während nichts rausging. Ein Fehler, der sich
  als Erfolg meldet, ist schlimmer als ein lauter Fehler.

  Neu `enttec_pro.diagnose_port()` (plus `port_is_foreign()`) unterscheidet drei
  Fälle mit je eigenem Klartext und nennt den konkreten Vorschlag aus der
  VID/PID-Suche:

  | Fall | Meldung |
  |---|---|
  | Portname von einer **anderen Plattform** (`COM*` auf Linux) | „…die Konfiguration stammt vermutlich von einem anderen Rechner. Vorschlag: auf `/dev/ttyUSB0` umstellen." |
  | Port **existiert nicht mehr** | „…existiert auf diesem System nicht." |
  | **gar keiner konfiguriert** | „Für dieses Universe ist kein Enttec-Port konfiguriert." |

  `apply_output_config` hält den Befund je Universe in `enttec_port_notes` fest.
  Der Statusbalken kennt jetzt vier Zustände: aktiv (grün, mit den wirklich
  benutzten Ports), falsch konfiguriert (amber, Grund im Tooltip), Adapter da
  aber keinem Universe zugewiesen (amber), nicht gefunden (rot).

  **Bewusst NICHT automatisch umgebogen.** An einem Rechner können mehrere
  FTDI-Geräte hängen; DMX auf ein nie konfiguriertes Gerät zu schicken wäre
  schlimmer als der ehrliche Hinweis — und der Aufbau hinge sonst davon ab, was
  gerade eingesteckt ist, bis in die Tests hinein. Der Öffnungsversuch bleibt
  exakt wie vorher. (Das automatische Nachfinden per VID/PID gibt es weiterhin
  in `EnttecPro._try_reconnect`, dort aber für einen Port, der vorher schon
  funktioniert hat und mitten im Betrieb wegbricht — anderer Fall, SERIAL-02.)

  **Fallenklasse mitgenommen:** `apply_output_config` wird in Bestandstests auf
  einem `SimpleNamespace`-Stub aufgerufen, der laut eigener Doku nur
  `output_manager` und `universes` mitbringt. Sowohl ein neues Pflichtfeld als
  auch eine Hilfsmethode auf `self` schlugen dort mit `AttributeError` zu — und
  wären im `except` des Aufrufers verschwunden, also genau in der Fehlerklasse
  gelandet, die dieses Item behebt. Beides von den eigenen Tests gefangen,
  jetzt `getattr`/Lazy-Init.

  `tests/test_hw5b_enttec_port_resolve.py` (19) — darunter der erste Test für
  `_check_hardware` überhaupt.

### 2026-07-30 — Die GitHub-Seite sagt wieder, was LightOS wirklich ist

#### Geändert

- **README, INSTALL, ROADMAP, AGENTS und die Issue-Vorlage nannten LightOS
  „Software fuer Windows x64 und ARM64" — Linux kam als „sekundaer" vor oder gar
  nicht.** Seit dem Linux-Umzug (alle XPLAT-Items, PR #431) ist Linux die
  tägliche Entwicklungs- und Testplattform; die komplette Suite läuft dort grün.
  Beide Plattformen stehen jetzt gleichberechtigt da, mit Linux-Installationsweg,
  Systempaketen und Startbefehlen an jeder Stelle, wo bisher nur `cmd`-Zeilen
  standen.

  **Bewusst mit Ehrlichkeits-Tabelle statt Häkchen:** die README schlüsselt auf,
  was auf welcher Plattform wirklich geprüft ist — die GitHub-CI fährt nämlich
  weiterhin nur `windows-latest`. Dieses Loch ist als `XPLAT-CI-LINUX` erfasst,
  statt es hinter einem „unterstützt" verschwinden zu lassen.

- **Der Feature-Überblick war Jahre hinter dem Code.** Ergänzt: die
  **Fixture-Bibliothek** (1.786 Geräte in 5.116 Modi von 162 Herstellern), die
  komplette **Laser-Sektion** (DMX-Laser, Not-Aus, Figuren, Bild-Trace,
  Ether Dream/IDN) — die vorher überhaupt nicht vorkam —, die **Kopf-Auswahl bei
  Mehrkopf-Geräten**, die 19 VC-Widget-Typen statt der alten acht, das
  Sicherheitsmodell des Web-Remote (127.0.0.1 per Default, LAN als Opt-in mit
  Token-Gate) und der aktuelle Stand des 3D-Visualizers. Kennzahlen-Tabelle
  oben, damit man den Umfang sieht, ohne die Feature-Liste zu lesen.

- **Der `Status`-Abschnitt sagt jetzt auch, was NICHT fertig ist:** Ether Dream
  und IDN sind nur gegen Fakes getestet, Kommandozeile und MIDI-Mapping kennen
  die Kopf-Auswahl noch nicht, macOS ist ungetestet, ARM-Linux ebenso.

- **Die GitHub-Repo-Seite selbst hatte weder Beschreibung noch Topics.** Beides
  gesetzt (12 Topics: `dmx`, `dmx512`, `art-net`, `sacn`, `enttec`,
  `lighting-control`, `lighting-console`, `stage-lighting`, `laser`, `pyside6`,
  `qt`, `python`).

### 2026-07-30 — Das VC-XY-Pad respektiert die Kopf-Auswahl (FM-9/A5)

#### Behoben

- **„Kopf 2" gewählt, XY-Pad gezogen — und trotzdem fuhren alle vier Köpfe.**
  Programmer-Regler (A1), Fächer und Snaps (A2), EFX (A3) und der VC-Submaster
  (A4) waren längst kopf-fähig; das XY-Pad war die letzte VC-Fläche, die Pan/Tilt
  weiterhin geräteweit schrieb. Es holte seine Ziele über `get_selected_fids()`
  statt über die Zell-Auswahl und rief `set_programmer_value` ohne `head=`.

  Jetzt liest `VCXYPad._resolve_heads` die Zellen (`get_selected_cells` →
  `group_cells.head_restrictions` → `validate_head_restrictions`) und `_apply`
  schreibt je gewähltem Kopf — dieselbe Kette wie beim VC-Submaster. Ein fest
  zugewiesenes Pad (`_fixture_ids`) ignoriert die Auswahl weiterhin: eine
  ausdrückliche Zuweisung darf die Selektion nicht überstimmen (Vorrang-Regel
  aus A4). 16-bit-Betrieb zieht den Fine-Kanal mit demselben Kopf-Index mit
  (`pan#2` / `pan_fine#2`).

#### Der eigentliche Fund — er reicht weit über das XY-Pad hinaus

- **Farbköpfe und Bewegungsköpfe eines Geräts sind nicht dieselbe Zahl** — und
  `validate_head_restrictions` zählte bisher hart die Farbköpfe (`color_r`).
  **Über die eingebaute Library ausgezählt (5116 Modi) gehen beide Zählungen bei
  831 Modi auseinander, und zwar in beide Richtungen:**

  - **108 Modi** haben ≥2 Bewegungs-, aber <2 Farbköpfe — darunter die gängigen
    Moving-Bars: `Event Bar LED`, `Event Bar Pro`, `Event Bar Q4`,
    `HYDRABEAM 4000 RGBW` in `19-Kanal`/`32-Kanal`, `Hydrabeam 400 Series`
    `15-CH`/`28-CH`. Mit der Farb-Zählung wird die Kopf-Einschränkung
    **verworfen** → „Kopf 2" gewählt, und trotzdem fahren alle vier Köpfe.
  - **723 Modi** haben ≥2 Farb-, aber <2 Bewegungsköpfe — Pixel-Bars sowie die
    vier Spider aus Davids Patch (`Speider 14ch`, `Mini Spider ZQ-B20 15ch`).
    Dort wird die Einschränkung fälschlich **behalten** und erzeugt `pan#1`.

  Was `pan#1` auf einem Ein-Pan-Gerät wirklich anrichtet, ist gemessen statt
  vermutet: `_flush_programmer_to_dmx` läuft über die **Kanäle**, der einzige
  Pan-Kanal fragt also nach `"pan"` — `pan#1` liest niemand. Der Kanal fällt auf
  seinen `default_value` zurück, der Kopf **springt auf Default-Position und
  folgt dem Pad nicht mehr** (gemessen: Default 128, geschrieben 200, Kanal blieb
  128). Kein Fehler, keine Meldung.

  Deshalb nimmt `validate_head_restrictions` die Zähl-Quelle jetzt als Parameter
  (`count_heads`); Default bleibt die Farb-Zählung, der Submaster-Pfad ist
  byte-identisch. Neu daneben: `move_head_count_for_channels` als Gegenstück zu
  `color_head_count_for_channels`.

  `tests/test_fm_head_selection_a5_xypad.py` (14) fährt **beide** Richtungen als
  Wächter — jeweils mit Gegenprobe, dass die alte Farb-Zählung den Fehler
  wirklich produziert hätte.

### 2026-07-30 — HW-5 messbar gemacht: Enttec-Langzeitlauf (`tools/hw5_longrun.py`)

#### Neu

- **`tools/hw5_longrun.py` — der Enttec-Langzeittest läuft jetzt als Messung statt
  als Bauchgefühl.** HW-5 fragt: *bricht der Ausgang irgendwann weg, nach wie vielen
  Stunden, und kommt er von selbst zurück?* Das Werkzeug fährt dafür denselben
  Codepfad wie die App (`EnttecPro.send_dmx` → `serial.write`, 40 Hz) über Stunden
  und protokolliert minütlich: Schreibfehler, das OUT-02-Auto-Disable, die
  Selbstheilung danach, den SERIAL-02-Portwechsel nach USB-Replug, das Hochwasser
  des Sendepuffers und den größten Frame-Abstand. Zwischenstand jederzeit per
  `--status` (atomar geschriebenes JSON), Abschlussbericht am Ende.

  **Blackout ist Default, sichtbares Licht ist Opt-in.** Im aktuellen Show-Patch
  liegen alle 30 Fixtures auf Universe 1 (Art-Net), das Enttec-Universe ist leer —
  was physisch an der Enttec-Leitung hängt, weiß das Werkzeug nicht. Acht Stunden
  unbeaufsichtigt blind Kanäle zu bespielen kann bei Movern, Spidern oder Lasern
  reale Folgen haben, also sendet der Lauf 512 Nullen: gleiche Paketgröße, gleiche
  Rate, gleiche Dauer, kein Licht. Ein sichtbarer Ramp kommt nur auf ausdrückliche
  Ansage (`--heartbeat-channel`), der Sichttest per `--probe`.

  **Der Bericht nennt seine eigene Grenze.** Was hier nicht messbar ist: der *stille*
  Tod, bei dem der FTDI weiter Bytes annimmt, aber keine gültigen DMX-Frames mehr
  auf die Leitung legt. Der Abschlusstext sagt das ausdrücklich, statt Grün zu
  melden, was er nicht geprüft hat.

  Der Heartbeat ist bewusst ein *Dreieck*, kein fester Pegel: DMX hält den letzten
  Wert, ein toter Ausgang sähe bei statischem Pegel exakt aus wie ein lebender.

  `tests/test_hw5_longrun.py` (14) prüft Frame-Bau und Zustandserkennung gegen ein
  Fake-Gerät — denn das Ergebnis eines Zwölf-Stunden-Laufs ist nicht der Lauf,
  sondern sein Bericht: übersieht `observe` einen Aussetzer, ist die Nacht verloren
  und niemand merkt es.

#### Nebenbefund

- **Die Enttec-Universe-Konfiguration ist seit dem Linux-Umzug tot** (neu als
  `HW-5b` im Backlog): `data/universes.json` trägt für Universe 3 noch
  `"patch": "COM_FAKE"`, einen Windows-Rest. Auf Linux heißt das reale Gerät
  `/dev/ttyUSB0` und wäre per `find_enttec_port()` auffindbar — `EnttecPro("COM_FAKE")`
  kann dagegen nur scheitern. Die App sendet damit aktuell nichts an den Enttec,
  ohne dass es irgendwo auffällt.

### 2026-07-30 — Crash-Intake: die vergiftete Alt-Historie abgeschnitten (QA-CRASHLOG-CUT)

#### Behoben

- **Das Crash-Intake meldete bei jedem Sessionstart „5 neue Abstürze" — alle fünf
  stammten aus der Testsuite.** Der Vortag hatte die *Schreibseite* dichtgemacht
  (`LIGHTOS_CRASH_LOG` + conftest-Umlenkung nach `/tmp`, QA-CRASHLOG-TESTS), aber die
  bereits geschriebenen 25 KB blieben in `crash.log` liegen. `collect_crash_report.py`
  las sie weiter und stufte sie als echte App-Signaturen ein.

  Herkunft jeder Signatur einzeln nachgewiesen statt vermutet:
  `TypeError`/`ValueError @ visualizer_window.py:727` und `:731` kommen aus
  `tests/test_a3d_gesture_batch.py`, das absichtlich `None`/`nan`/`inf`/`"abc"` durch
  die Bridge schickt — der echte Bug dahinter ist A3D-41 und war bereits gefixt.
  `RuntimeError: status=CrashedTerminationStatus` (17×, **ohne jeden Traceback-Frame**
  und damit für den Test-Filter strukturell unerreichbar) kommt aus
  `tests/test_viz10_stability.py`: ein Einzellauf erzeugt gemessen **exakt einen**
  Eintrag, und die neun Einträge vom Vorabend liegen minutengenau auf den
  Gate-Läufen in `logs/gate_*.txt` (17:32 / 17:39 / 17:50 / 18:12 / 18:36 / 18:55 /
  19:04 / 19:18). Ein „Absturz", der nur auftritt, während die Suite läuft, ist keiner.

  **Behoben als Schnitt, nicht als Löschung:** die Historie liegt byte-identisch in
  `crash.log.archiv-2026-07-30-testrueckstaende` und bleibt per
  `collect_crash_report.py --log <datei>` auswertbar; die neue `crash.log` trägt einen
  `#`-Kopf mit Grund und Archivpfad (die Blockerkennung des Parsers reagiert nur auf
  `=== `-Zeilen). `crash_report_seen.json` gehört zum Schnitt dazu und wurde
  mitarchiviert und geleert — sonst wäre ein *echtes* Wiederauftreten einer der vier
  bereits quittierten Signaturen als „schon gesehen" durchgerutscht.

  Kein Code-Fix nötig: der Wächter
  `test_app_data_dir.py::test_suite_never_writes_into_the_real_crash_log` verhindert
  die Neuverschmutzung bereits. Nachweis: `--count-only` gegen die neue Datei → `0`,
  gegen das Archiv → weiterhin `5`.

### 2026-07-29 — Linux-Test-Gate: QtWebEngine-Tests laufen wieder grün zu Ende

#### Behoben

- **Das Linux-Gate `tools/verify_loop.sh` setzte `LIGHTOS_HARDEN_EXIT` nicht.**
  Die Exit-Härtung in `tests/conftest.py` ist bewusst an diese Variable gekoppelt
  („nur vom Lock-Runner im Gate"), auf Windows setzt sie `run_tests.ps1 -Isolate`.
  Das Linux-Pendant tat das nie — dort starb jede QtWebEngine-Testdatei beim
  finalen Interpreter-Exit mit SIGSEGV, **nachdem** alle Assertions bestanden
  hatten. Im Segment-Gate zählte das als Crash: 12 Dateien liefen nie grün
  zu Ende.

- **Die Auto-Erkennung der WebEngine-Sessions griff zu kurz.** Sie prüfte nur
  `hasattr(mod, "QWebEngineView")`, also den direkten Top-Level-Import unter
  genau diesem Namen. `test_viz_labels_popout` importiert aber nur
  `src.ui.visualizer.visualizer_service` und erzeugt den View indirekt — der
  Name taucht im Modul-Namespace nie auf, die Härtung blieb aus.

  Entscheidend ist zusätzlich der **Zeitpunkt**: zur Kollektionszeit ist
  QtWebEngine oft noch gar nicht geladen (gemessen: 0 Module bei der Kollektion,
  2 bei `sessionfinish`), weil `visualizer_service` es erst beim Erzeugen des
  Views importiert. Die Prüfung sitzt deshalb jetzt in `pytest_sessionfinish`
  und sieht in `sys.modules` nach — das trifft jeden Importweg.

  Ergebnis auf Linux: **10 von 12 viz-Dateien laufen jetzt grün zu Ende** (vorher
  keine einzige). `test_viz13_scene_modules_smoke` und `test_viz_shadow_dispose`
  crashen weiterhin reproduzierbar (SIGSEGV/SIGABRT) — dort schlägt der Chromium-
  Abbau schon **vor** `sessionfinish` zu, die Härtung kann nicht mehr greifen.
  Beides ist als eigener Punkt im Backlog vermerkt; die QA-24-Regel
  (nativer Crash ≠ Failure) deckt sie im Gate weiterhin ab.

### 2026-07-29 — Crash-Signaturen sind wieder plattformunabhängig

#### Behoben

- **Crash-Intake verstümmelte Signaturen, sobald das Log auf Linux ausgewertet
  wurde.** `tools/collect_crash_report.py` kürzt den Dateipfad eines Frames auf
  den reinen Dateinamen, benutzte dafür an einer Stelle aber `os.path.basename()`
  auf dem **rohen** Pfad. Das ist plattformabhängig: auf Windows trennt es an
  `\` und `/`, auf Linux nur an `/`. Ein Windows-Pfad im crash.log — und davon
  gibt es viele, das Log wandert zwischen den Rechnern mit — ergab dort statt
  `AttributeError@live_view.py:42` die Signatur
  `AttributeError@C:\repo\lightos-main\src\ui\views\live_view.py:42`.

  Folge: **derselbe Absturz bekam je nach auswertender Plattform einen anderen
  Schlüssel.** Dedup zählte ihn doppelt, und der `seen`-Zustand aus
  `.crash_seen.json` griff nicht mehr — jeder alte Absturz meldete sich auf dem
  jeweils anderen Rechner erneut als „🆕".

  Der Fix führt `_basename()` ein, das an beiden Separatoren trennt, und benutzt
  es überall. Die vier Tests, die das schon immer geprüft haben
  (`tests/test_crash_intake.py`), waren auf Windows grün und schlugen beim
  ersten Linux-Lauf fehl — sie sind der Regressionsschutz, es braucht keine neuen.

### 2026-07-28 — Matrix-Vorschau zeigt auf Wunsch, welche Zelle zu welchem Gerät/Kopf gehört

#### Neu

- **Neuer Schalter „Zuordnung zeigen" unter der Matrix-Vorschau.** Bei einer
  Matrix über mehrere Geräte — erst recht über einzelne Köpfe — war nicht zu
  erkennen, welcher Vorschau-Pixel zu welchem Gerät gehört. Der Schalter legt
  einen dünnen Rahmen je Zelle darüber: **Farbton = Gerät, Helligkeit = Kopf**,
  exakt dieselben Farben wie im Fixture-Gruppen-Editor, dazu die Legende
  „Farbe → Gerät" und bei Kopf-Zellen die Kopfnummer (nur wenn die Zelle groß
  genug ist, damit aus einer 32×32-Matrix kein Textmatsch wird).

  Die **Effektfarben bleiben sichtbar** — der Rahmen liegt nur obendrauf. Das
  ist Absicht: die Vorschau zeigt, was der Effekt macht, und das darf ihr nichts
  nehmen. Der Schalter ist standardmäßig **aus**, die Vorschau sieht also
  unverändert aus, bis du ihn einschaltest.

- **Beim Überfahren einer Zelle** steht jetzt in der Sprechblase, welches Gerät
  und welcher Kopf dort sitzt (bzw. „Lücke") — unabhängig vom Schalter.

- **Hinweis bei widersprüchlicher Einstellung:** Steht ein Gerät im Patch-Dialog
  auf „als eine Lampe", wird aber im Raster in einzelne Kopf-Zellen zerlegt,
  sagt das die Matrix-Ansicht jetzt als sichtbaren Text — statt es stillschweigend
  zu übergehen. Aufgelöst wird der Widerspruch bewusst **nicht** automatisch: das
  Raster hast du von Hand gebaut, das Zusammenlegen würde dein Layout zerstören.

#### Intern

- Palette und Zellfarb-Funktion liegen jetzt in `src/ui/head_cell_colors.py` —
  eine Quelle für Gruppen-Editor **und** Matrix-Vorschau statt zweier Kopien,
  die auseinanderlaufen können.

### 2026-07-28 — Submaster pro Kopf: einzelne Köpfe eines Mehrkopf-Geräts dimmen

#### Neu

- **Ein Submaster-Fader kann jetzt einen einzelnen Kopf dimmen**, nicht mehr nur
  ganze Geräte. Damit ist der letzte Baustein von „jeder Kopf ist eine eigene
  Lampe" da: Auswahl, Fächer, Snaps und EFX konnten schon kopfweise arbeiten, die
  Helligkeit am Fader nicht.

  Ein neues Feld gibt es dafür nicht — es zählt die **Reichweite**, die der Fader
  ohnehin hat. Enthält sie Köpfe statt ganzer Geräte, wirkt er auf genau diese
  Köpfe. Fest und in der Show gespeichert geht das über eine Gruppe mit
  Kopf-Zellen (Gruppen-Editor → „Köpfe einzeln → Raster"); spontan über
  Reichweite „Nur Auswahl" mit ausgewählten Köpfen. Kopf-, Geräte- und globale
  Submaster multiplizieren sich wie gewohnt: Gerät auf 50 % und dessen Kopf 2
  zusätzlich auf 50 % ergibt für diesen Kopf 25 %, für die anderen 50 %.

  Angefasst werden nur Kanäle, die es **je Kopf wirklich gibt**: der eigene
  Dimmer des Kopfes, sonst dessen eigene Farbkanäle — der häufige Fall eines
  Geräts mit einem Master-Dimmer und vier RGB-Bänken wird also kopfweise über die
  Farbe gedimmt. Ein von allen Köpfen **geteilter** Master-Dimmer bleibt bewusst
  unangetastet: würde „Kopf 2" ihn herunterziehen, ginge das ganze Gerät dunkel.
  Ebenso wenig angefasst werden **Zonen-Dimmer** — Profile wie `Frost FX Bar W`
  (14 Pixel, aber nur zwei Dimmer für „alle weißen" und „alle farbigen") haben
  Kanäle, die zwar mehrfach vorkommen, aber trotzdem keine Kopf-Kanäle sind; als
  „je Kopf" zählt ein Kanaltyp nur, wenn er genau so oft vorkommt wie es Köpfe
  gibt. Hat ein Gerät gar keine kopf-eigenen Helligkeits- oder Farbkanäle, tut
  der Fader dort ehrlich nichts, statt ersatzweise das ganze Gerät zu dimmen.
  Pan, Tilt und Gobo werden nie gedimmt.

  **„Alle Köpfe" bleibt das ganze Gerät.** Deckt die Reichweite sämtliche Köpfe
  ab — wie es die beim Patchen automatisch angelegte Gruppe „… · Köpfe" tut —,
  arbeitet der Fader unverändert als Geräte-Submaster und dimmt weiterhin den
  gemeinsamen Master-Dimmer. Ein bestehender Fader auf dieser Gruppe verhält sich
  also exakt wie vorher. Kopf-Angaben, die es nach einem Kanal-Modus-Wechsel
  nicht mehr gibt, werden verworfen (Rückfall auf „ganzes Gerät") statt den
  falschen Kopf zu dimmen.

  Ohne Kopf-Zellen verhält sich jeder bestehende Submaster **unverändert**; an
  gespeicherten Shows ändert sich nichts.

### 2026-07-28 — Ein Gerät patchen fror die Oberfläche sekundenlang ein

#### Behoben

- **Beim Patchen stand die Bedienung 11–12 Sekunden still.** Jede Änderung am
  Patch liess den Simple Desk seine Kanalübersicht komplett neu einfärben: erst
  wurden alle 512 Kanalzüge auf neutral zurückgesetzt, danach die belegten wieder
  eingefärbt. Für jeden belegten Kanal hiess das zweimal ein Stil-Neuaufbau —
  pro Gerät, das du hinzufügst. Der Absturzbericht hat es als „Oberfläche
  reagiert nicht" mitgeschrieben (3. und 10. Juli), ohne dass die Ursache
  sichtbar war: der oberste Eintrag im Bericht zeigte auf die Tastatur-Kürzel,
  die nur zufällig gerade mitliefen.

  Jetzt wird zuerst der Zielzustand berechnet und **nur die Differenz** gesetzt;
  Färbung, Kürzel und Tooltip eines Kanalzugs, an dem sich nichts ändert, kosten
  gar nichts mehr. Gemessen an zwölf nacheinander gepatchten Geräten:
  **3510 ms → 55 ms**, also 294 ms → 4 ms pro Gerät (headless gemessen; auf dem
  Desktop mit echtem Stil-Aufbau war es entsprechend mehr).

### 2026-07-28 — Drei echte Abstürze aus dem Crash-Log behoben, einer davon am Laser-Scharfschalter

#### Behoben

- **Der Scharfschalt-Knopf des Lasers erreichte die Ausgabe nie.** Er war so
  verdrahtet, dass der An/Aus-Zustand des Knopfes unterwegs verworfen wurde —
  der Aufruf kam ohne ihn an und brach mit einem Fehler ab, *bevor* das
  Scharfschalten überhaupt ausgelöst wurde. Der Knopf sah aus, als täte er
  etwas. **Das stand in keinem Absturzbericht** (Laser-Hardware fehlt, der Knopf
  wird kaum gedrückt) — gefunden hat es eine neue Prüfung, die alle rund 70
  Stellen dieser Bauart auf denselben Fehler abklopft.
- **Der Wechsel der Laser-Figur stürzte bei jedem Umschalten ab** — dieselbe
  Ursache, hier aber im Absturzbericht vom 6. Juli belegt. Die Figur wurde
  dadurch nie übernommen.
- **Beim Schliessen des Visualizer-Fensters konnte ein Fehler auf dem
  Aufräumpfad hochkommen** (`Internal C++ object already deleted`, zuletzt am
  21. Juli). Qt zerstört beim Beenden die interne Seite des Taktgebers, während
  die Python-Seite noch existiert — jeder Zugriff wirft dann. Ein toter Taktgeber
  wird jetzt als „nicht vorhanden" behandelt und beim nächsten Bedarf neu gebaut.

#### Geändert

- **Der Absturz-Bericht sortiert nach „zuletzt gesehen" statt nach Häufigkeit**
  und markiert Signaturen, die seit über 30 Tagen nicht mehr auftraten, als kalt.
  Neu: `--since JJJJ-MM-TT`. Grund: nach Häufigkeit sortiert stand ein 159×
  aufgetretener, seit Wochen toter Testlauf-Absturz ganz oben, während der
  einzige noch lebende Fehler unterging — und die daraus abgeleitete Priorität
  war falsch.

### 2026-07-28 — Amber und UV leuchten jetzt auch in der Anzeige

#### Behoben

- **Amber- und UV-LEDs fielen aus der Anzeigefarbe komplett heraus.** Der
  Visualizer rechnete nur Rot/Grün/Blau plus Weiss zusammen; ein RGBA-PAR, an dem
  nur Amber aufgedreht ist, blieb im 3D **und** im 2D-Bühnenplan schwarz, obwohl
  er real leuchtet. Beide werden jetzt — wie Weiss — additiv eingerechnet: Amber
  in seinem Bernsteinton, UV als tiefes Violett (so nimmt das Auge es wahr).
  Ein Gerät, das *nur* Amber hat, zeigt entsprechend Amber statt der
  Ersatzfarbe Weiss.
- Auch **einzelne Köpfe** einer Mehrkopf-Leiste rechnen Amber/UV jetzt mit; ihre
  Farbe kommt aus derselben Ableitung wie die des ganzen Geräts, statt die
  Rot/Grün/Blau-Rechnung ein zweites Mal zu führen.

#### Intern

- Die Farbwort-Liste steht zweimal im Code (der Kern darf nicht aus der
  Oberfläche importieren) und wurde laut Kommentar „von Hand synchron gehalten".
  Ein Test hält beide Listen jetzt Wort für Wort gleich.
### 2026-07-28 — Abstürze und Freezes aus deinen Sitzungen landen endlich im Backlog

#### Hinzugefügt

- **Neues Werkzeug `tools/collect_crash_report.py`.** LightOS schreibt seit jeher
  jeden ungefangenen Fehler und jeden erkannten UI-Freeze nach
  `%APPDATA%/LightOS/crash.log` — nur hat diese Datei nie jemand gelesen. Sie war
  auf 1,3 MB gewachsen. Das Werkzeug liest sie entlang der Sitzungs-Marker,
  fasst gleiche Fehler zu einer Signatur zusammen (mit Anzahl, Zeitraum und
  betroffenen Sitzungen) und gibt einen fertigen Bug-Report aus.
- **Die Sitzungs-Statuszeile meldet neue Signaturen**, sobald welche dazukommen —
  eine Zahl, kein Textblock; den Report holt man sich bei Bedarf.

#### Bemerkenswert am ersten Lauf gegen das echte Log

Drei Dinge wären ohne Gegenprobe still falsch geblieben:

- **Freeze-Stacks haben ein anderes Frame-Format als Tracebacks** (`line 12 in f`
  statt `line 12, in f`). Wer nur eines kennt, verliert die halbe Auswertung,
  ohne dass etwas fehlschlägt.
- **Der eingefrorene Thread ist der namenlose.** Nimmt man einfach den ersten
  passenden Eintrag, zeigt der Bericht auf den Wächter, der den Freeze *meldet* —
  statt auf die Stelle, die ihn verursacht. Richtig zugeordnet zeigen deine
  echten Freezes u. a. auf `live_view.paintEvent`, `enttec_pro.close` und
  `output_manager.stop`.
- **Die Testsuite schreibt in dasselbe Log** und wirft dort absichtlich Fehler.
  Ungefiltert bestand der Bericht überwiegend aus diesen gewollten Fehlern;
  sie bleiben jetzt draussen (`--include-tests` holt sie zurück).

### 2026-07-28 — Fixture-Gruppen: das Rastergrößen-Panel verdeckt keine Zelle mehr

#### Behoben

- **Das schwebende „Rastergröße"-Panel im Fixture-Gruppen-Editor lag über der
  obersten rechten Rasterzelle** und verdeckte deren Beschriftung — aufgefallen,
  als eine Zelle beim Prüfen eines Kopf-Layouts schlicht nicht lesbar war.
  Zuklappen half, war aber nicht offensichtlich. Das Panel bleibt jetzt, wo man
  es sucht; stattdessen wird oben genau seine Höhe freigehalten, sodass das
  Raster darunter beginnt. Klappt man es zu, gibt es den Platz sofort wieder her.
### 2026-07-28 — Bedienflächen und 2D-Anzeige: Touch-Floor hält, Info-Box schweigt nicht mehr

#### Behoben

- **Die Sektions-Tabs konnten unter ihre eigene Touch-Klickfläche schrumpfen.**
  Das Stylesheet sichert 56 px zu, die Breitenverteilung setzte aber eine feste
  Breite und hebelte damit die Mindestbreite aus — bei schmalen Titeln (andere
  Schrift oder Bildschirmauflösung; für Linux wurde das Innenabstand-Maß auf 7 px
  gesenkt) landeten „E/A" und „BPM" darunter. Der Floor wird jetzt durchgesetzt,
  solange der Platz reicht; bei echtem Platzmangel hat weiterhin Vorrang, dass
  nichts in die Grand-Master-Gruppe überläuft.
- **Die Info-Box im 2D-Bühnenplan zeigte Scannern und Mover-Bars kein Pan/Tilt.**
  Das Symbol zeichnet für diese Geräte einen sichtbar gedrehten Strahl, die Box
  entschied aber anhand des Gerätetyp-Namens und schwieg — Symbol und Text
  liefen auseinander. Beide nutzen jetzt dieselbe Quelle; zusätzlich zeigt die
  Box Pan/Tilt auch dann, wenn ein Gerät die Kanäle real hat, sein Symbol aber
  keinen Strahl dreht.

### 2026-07-28 — 3D-Visualizer: Strobes, Blinder und Farbrad-Mover sind nicht mehr unsichtbar

#### Behoben

- **Geräte ohne RGB-Kanäle wurden im 3D-Visualizer schwarz gerendert — also gar
  nicht.** Der Visualizer las die Farbe ausschliesslich aus `color_r/g/b` und
  nahm 0 an, wenn es diese Kanäle nicht gibt. Betroffen waren unter anderem der
  **Martin Atomic 3000** (Xenon-Strobe/Blinder, hat nur Shutter/Rate/Dauer), die
  **Robe Pointe** und **MegaPointe** (Dimmer + Farbrad, kein RGB) und jeder reine
  **Dimmer-PAR**: auf dem echten Rig blitzten sie, im 3D passierte nichts.
  Die Farbe wird jetzt in dieser Reihenfolge bestimmt: RGB(W) → CMY (subtraktiv)
  → Farbrad-Slot unter dem aktuellen DMX-Wert → Lampenfarbe Weiss. Geräte **mit**
  RGB-Kanälen verhalten sich unverändert; eine bewusst auf 0 gesetzte RGB-Farbe
  bleibt schwarz.
- **Geräte ohne Dimmer-Kanal galten als dauerhaft voll aufgedreht.** Ein Xenon-
  Strobe mit geschlossenem Shutter leuchtete im 3D weiter. Die Helligkeit kommt
  jetzt vom echten Dimmer (`intensity`, `dimmer` oder `master`) und — nur bei
  Geräten ganz ohne Dimmer — ersatzweise vom Shutter, ausgewertet über die
  hinterlegte Kanal-Semantik (`zu` = dunkel).
- **Köpfe ohne eigene Farbkanäle** (z. B. eine Mover-Bar ohne Farbe) erben jetzt
  die Gerätefarbe, statt als schwarze Einzelstrahlen zu verschwinden.
- **Die 2D-Bühnenansicht hatte denselben Fehler** und zieht ihre Farbe und
  Helligkeit jetzt aus derselben Quelle wie der 3D-Visualizer — beide Ansichten
  können damit nicht mehr auseinanderlaufen.

#### Geändert

- **Dunkel-Culling misst jetzt die tatsächliche Leuchtdichte** (A3D-25/A3D-28).
  Bisher entschied allein der Dimmer, ob Lichtkegel, SpotLight und Bodenspot
  sichtbar sind. Ein Gerät mit offenem Dimmer und Farbe 0/0/0 blieb dadurch ein
  „sichtbares" Licht: three.js wertet es in jedem beleuchteten Pixel aus und es
  belegt einen Schatten-Slot, obwohl es nichts abstrahlt — genau der Kostenblock,
  den das Culling einsparen soll. Auf schwachen GPUs (Davids Surface) zählt das.
- **Der Bodenlichtpunkt wird ab dem Kopf gerechnet, nicht ab dem Fuß des Geräts**
  (A3D-26). Die Strahlrichtung kam schon aus dem Kopf, der Auftreffpunkt aber vom
  Sockel — bei einem gekippten Moving Head oder Scanner lag der Bodenpool damit
  sichtbar neben dem Lichtkegel, der am Kopf hängt.

### 2026-07-27 — Backlog-Hygiene: Status-Drift beseitigt, Datei halbiert, Queue ehrlich

Reine Buchhaltung, kein Verhalten der App betroffen.

#### Behoben

- **Vier Zeilen in `BACKLOG.md` behaupteten einen falschen Stand.** `FM-9` stand
  auf `todo`, obwohl der Kern (Kopf als selektierbares Ziel, #448), Fächer/Snaps
  (#451) und EFX-auf-einem-Kopf (#454) längst gemergt sind — es war damit das
  oberste P1 der Loop-Queue. `FM-HEADLAYOUT` meldete „Slices 4+ offen", obwohl
  Slice 4/5 und A2/A3 landeten (offen ist nur noch A4). `FM-13` versprach seit
  dem Merge von #438 weiter „PR folgt". `CDX-24` trug seinen gesamten
  Umsetzungsbericht in der Status-Zelle; das Wort „Review" darin liess das Item
  als laufende Arbeit gelten.
- **Neuer Lint (QA-18b, `tests/test_backlog_lint.py`):** Status `todo` und
  „GELANDET" in derselben Zeile sind ab jetzt ein Testfehler — der Widerspruch
  schickt die nächste Loop-Runde auf ein Item, das grösstenteils erledigt ist
  (zuletzt `FM-9`, das oberste P1). Bewertet wird nur der **Status-Kopf** vor der
  ersten Klammer: `todo (Slice 1 done)` entwertet die Regel nicht mehr, und ein
  zitiertes Wort im Fliesstext löst sie nicht mehr fälschlich aus.
- **Neuer Lint (QA-18c): doppelte IDs sind ein Testfehler.** Vorgefunden: zwei
  völlig verschiedene Items trugen beide `DOC-10` (Anleitungs-/Bild-Audit und der
  AUDIT_COVERAGE-Tracker). Jede Auswertung, die per ID zusammenführt — Verdichten,
  Zurückholen aus dem Archiv, Queue — greift dann die falsche Zeile. Der Tracker
  heisst jetzt `DOC-10b`.
- **Halb erledigte Zeilen wandern nicht mehr ins Archiv.** `DOC-10` stand auf
  „✅ Bild-Links done · Screenshots offen" — die Zelle meldet Erledigtes UND
  offene Arbeit im selben Atemzug. Die Verdichtung sah nur das Wort `done` und
  schob die Zeile samt offenem Rest ins Archiv, wo keine Queue und kein Report
  sie je wieder zeigt. Solche gemischten Staten gelten jetzt als `teils`.
- **Kurztitel schneiden keine Links mehr an.** Die Kürzung auf 90 Zeichen lief
  stumpf über die Zeichenzahl und zerhackte dabei Markdown-Links — 21 Kurzzeilen
  trugen eine abgeschnittene, tote URL. Links werden jetzt auf ihren Text
  reduziert (die kanonische PR-Adresse hängt ohnehin separat an) und es wird nur
  an Wortgrenzen gekürzt. Alle betroffenen Zeilen sind neu erzeugt.
- **Neun Zeilen waren für sämtliche Backlog-Werkzeuge unsichtbar.** Unterpunkte
  mit Kleinbuchstaben-Suffix (`LAS-18b`, `LAS-18c`, `UXT-11a/b`, `CDX-14b`,
  `CDX-22b`, `STAB-19a/b`, `A3D-17b`) fielen durch das ID-Muster — sie tauchten
  in Queue, Statistik, Verdichtung und Lint schlicht nicht auf, darunter ein
  offenes `todo` und ein `blocked`. Das Muster erfasst die Konvention jetzt, und
  ein neuer Lint (QA-18d) meldet jede Zeile, die wie ein Item aussieht, aber
  nicht erfasst wird.
- **Das Doku-Link-Gate (QA-17) prüft jetzt auch `BACKLOG_ARCHIVE.md`.** Die
  Verdichtung schiebt laufend Doku-Verweise dorthin; ohne Eintrag im Gate wären
  ausgerechnet die Links ungeprüft geblieben, für die es das Gate gibt.

#### Verbessert

- **`BACKLOG.md` 375 KB → 197 KB.** 283 reine `done`-Zeilen sind per
  `tools/backlog_compact.py --archive --apply` als Volltext nach
  `BACKLOG_ARCHIVE.md` gewandert; in der Arbeitsdatei bleibt je eine Kurzzeile
  mit ID, Titel und PR-Link. Damit ist die Datei wieder in einer Loop-Runde
  ladbar. Nachgerechnet: 339 IDs vorher, 340 nachher (der aufgelöste Doppel-Name),
  keine einzige verloren, jede Kurzzeile hat ihren Volltext im Archiv.
- **`--queue` zeigt liegengebliebene Items in eigenen Blöcken.** `teils`-Items
  sind weder `done` noch in Arbeit und fielen bisher aus jeder Ansicht heraus;
  real sind es sieben (`QA-LIVE`, `LAS-07`, `VIZ-15`, `DOC-10`, `LAS-08`,
  `NET-04`, `OUT-06`). Dazu ein Block für Zeilen mit **freiem Status-Text**, den
  keine Vokabel der Legende trifft (`VIZ-05` „✅ verifiziert → 🎨 Design",
  `UXT-02` „⏳ nicht reproduzierbar") — die waren bislang genauso unsichtbar.
- **`--archive` warnt vor dem Schreiben**, wenn eine als erledigt eingestufte
  Zeile im Kommentar noch nach offener Arbeit klingt. Bewusst nur eine Warnung:
  „offen" steht auch als blosse Prosa in echten `done`-Zeilen, das entscheidet
  ein Mensch.

### 2026-07-27 — Web-Remote: Token und LAN-Zugriff endlich bedienbar (CDX-24)

#### Hinzugefügt

- **Neuer Dialog „Web-Remote: Verbindung & Token…" im Menü *Ausgabe*.** Er zeigt
  Adresse, Token und den Direkt-Link fürs Handy (mit „Link kopieren") und
  enthält die beiden Sicherheits-Bedienelemente, die die Anleitung schon lange
  beschreibt, die es aber nie zu klicken gab:
  - **„Token neu erzeugen"** macht alle bisherigen Links und angemeldeten Geräte
    sofort ungültig — auch am **laufenden** Server, ohne Neustart. Bereits
    verbundene Geräte werden dabei aktiv getrennt: ein schon offener Draht zum
    Handy lief bisher nicht mehr durch die Zugangsprüfung und hätte sonst
    weitergesteuert, obwohl gerade „alle Geräte ungültig" gedrückt wurde.
  - **„LAN-/Handy-Remote"** schaltet zwischen „im WLAN erreichbar" und „nur
    dieser PC" um. Läuft das Web-Interface gerade, startet LightOS es dabei
    automatisch neu, damit „aus" auch wirklich sofort „aus" heisst.
- Der Dialog ersetzt die bisherige Info-Box beim Einschalten und ist zusätzlich
  jederzeit über das Menü erreichbar — ein kompromittiertes Token liess sich
  während einer laufenden Show sonst praktisch nicht wechseln.


### 2026-07-27 — Ein EFX kann auf einem einzelnen Kopf laufen (FM-HEADLAYOUT A3)

#### Hinzugefügt

- **Ein Bewegungseffekt kann jetzt einen einzelnen Kopf als Ziel haben.** Ist im
  Programmer „Kopf 2" gewählt, bewegt der Effekt ausschließlich dessen Pan/Tilt —
  die übrigen Köpfe bleiben stehen. Ohne Kopf-Auswahl arbeitet er unverändert auf
  ganzen Geräten inklusive der Kopfwelle über alle Köpfe.
- Mehrere Kopf-Ziele desselben Geräts sind erlaubt und tragen je ihren eigenen
  Phasen-Offset — damit lässt sich ein Fächer über die Köpfe eines Movers fahren.
- Die Zielliste im EFX-Editor benennt Kopf-Ziele als „Fixture #1 · K3"; alle drei
  Zuweisungswege (Auto-Zuweisung, Neuanlage, „Auswahl hinzufügen") laufen über
  denselben Ziel-Bauer, und „Auswahl hinzufügen" unterscheidet Ziele jetzt nach
  Gerät **und** Kopf.
- Ein gemeinsamer Master-Dimmer bleibt bei einem Kopf-Ziel geteilt (sonst wäre der
  Kopf bei „Beam öffnen" dunkel geblieben), pro Kopf vorhandene Dimmer gehören dem
  Kopf — dieselbe Regel wie bei der Pro-Kopf-Matrix.

#### Show-Format

- Das Kopf-Feld wird **nur bei echten Kopf-Zielen** in die Show geschrieben. Alte
  Shows laden unverändert, und ihr erster Speichervorgang ändert die Datei nicht
  (Save→Load→Save bleibt ein Fixpunkt). Ein kaputtes oder negatives Kopf-Feld
  verliert nicht das Ziel, sondern fällt auf „ganzes Gerät" bzw. Kopf 1 zurück.
- Tests `tests/test_fm_head_selection_a3_efx.py` (15).
### 2026-07-27 — Ein Strg+Z macht die ganze 3D-Geste rückgängig (A3D-06/09/10/27)

#### Behoben

- **Ein Strg+Z nimmt jetzt die komplette Geste zurück, nicht ein Gerät davon.**
  Wer zehn Lampen gemeinsam verschob oder drehte, musste bisher zehnmal
  rückgängig machen — jedes Gerät war ein eigener Schritt. Dasselbe beim Bewegen
  einer Traverse mit angedockten Lampen. Beides ist jetzt ein einziger Schritt.
- **Grosse Auswahlen zerstören die Rückgängig-Liste nicht mehr.** Da der Verlauf
  auf 100 Schritte begrenzt ist, löschte das Verschieben von mehr als hundert
  Geräten in einem Zug die gesamte bisherige Rückgängig-Historie der Sitzung.
- **Rückgängig aktualisiert die 3D-Ansicht wieder.** Bisher änderte es nur den
  internen Zustand: die Geräte blieben im Bild an der neuen Stelle stehen,
  obwohl der Zustand schon der alte war — Ansicht und Wahrheit liefen
  auseinander, bis irgendetwas anderes ein Neuzeichnen auslöste. Auch die
  Andock-Beziehung wird jetzt mit zurückgerollt.
- **Positionen aus den Zahlenfeldern markieren die Show wieder als geändert.**
  Der Eingabe-Pfad meldete überhaupt keine Änderung, weshalb die automatische
  Speicherung solche Positionen still überging.


### 2026-07-27 — Fächer und Snap-Aufnahme verstehen Köpfe (FM-HEADLAYOUT A2)

#### Hinzugefügt

- **Das Fächer-Werkzeug fächert jetzt über die gewählten Köpfe.** Sind die vier
  Köpfe einer PAR-Bar ausgewählt, bekommen sie einen echten Verlauf statt vier
  gleicher Werte; die Vorschau weist jede Zeile als „PARBAR4 · K2" aus, damit
  sichtbar ist, welcher Wert auf welchen Kopf geht. Ohne Kopf-Auswahl arbeitet es
  unverändert über ganze Geräte.
- **Die Snap-Aufnahme respektiert die Kopf-Auswahl.** Ist im Programmer nur Kopf 2
  gewählt, landet auch nur dessen Wert im Snap — vorher nahm der Geräte-Scope die
  übrigen Köpfe still mit. Der Speicher-Scope kennt dafür eine Kopf-Ebene
  (`active_scope_heads`), die alle drei Aufrufer des Kanal-Auswahl-Dialogs über
  denselben Helfer nutzen.
- Tests `tests/test_fm_head_selection_a2.py` (15).

#### Noch nicht kopf-fähig

- **EFX** speichert seine Ziel-Geräte in der Show-Datei; eine Umstellung auf
  Kopf-Ziele ist eine Formatänderung mit Migration für Altshows und bekommt
  deshalb eine eigene Runde.
- **VC-Submaster** wirkt über eine Geräte-Maske im DMX-Ausgang, nicht über den
  Programmer; pro Kopf hieße Adress-Maske im Ausgabepfad — ebenfalls eigene Runde.
### 2026-07-27 — 3D-Visualizer: keine verlorenen Fixture-Updates, keine verlorenen Andockungen (A3D-04/08)

#### Behoben

- **Ein Auswahl-Klick im 3D löscht keine Andockungen mehr.** Bisher schrieb jede
  Geste die Andock-Beziehung fest — auch eine, die das Gerät gar nicht bewegt
  hatte. Da „Andocken" standardmässig aus ist, hiess „festschreiben" dort
  **lösen**: ein einfacher Klick zum Auswählen entfernte die gespeicherte
  Andockung, und weil die Schleife über die ganze Auswahl läuft, gleich für alle
  markierten Geräte. Der Commit läuft jetzt nur noch, wenn sich die Position
  tatsächlich geändert hat.
- **Ein weggedrehtes Gerät hängt nicht mehr an der alten Traverse (A3D-08).**
  Beim Drehen mehrerer Geräte um den gemeinsamen Mittelpunkt wanderten sie aus
  der Traverse heraus, behielten aber ihre Bindung — und wurden beim nächsten
  Bewegen des Bühnenelements dorthin zurückgerissen. Die Bindung wird jetzt
  gelöst, sobald die Drehung das Gerät wirklich versetzt hat. (Bewusst lösen
  statt neu andocken: der Boden ist ein Andock-Ziel, ein weggedrehtes Gerät wäre
  sonst „auf dem Boden stehend" in sieben Metern Höhe gelandet.)
- **Der 3D-Visualizer verliert keine Fixture-Updates mehr (A3D-04).** Die
  DMX-Zustellung sammelte zwischen zwei Abrufen nur das jeweils letzte Paket ein
  und verwarf alle vorherigen. Da jedes Paket nur die *geänderten* Geräte enthält
  und nie erneut geschickt wird, blieb ein Gerät, dessen einzige Änderung in
  einem verworfenen Paket lag, dauerhaft auf altem Stand — bei rund vier Paketen
  pro Abruf-Intervall traf das regelmässig. Die Pakete werden jetzt pro Gerät
  zusammengeführt.


### 2026-07-27 — Ein einzelner Kopf lässt sich im Programmer auswählen (FM-HEADLAYOUT Slice 5 / FM-9)

#### Hinzugefügt

- **In der Geräteliste des Programmers steht unter jedem Mehrkopf-Gerät jetzt eine
  Zeile je Kopf.** Wählst du „Kopf 2", zeigt der Color-Tab nur dessen Regler, und
  Schreiben trifft ausschließlich diesen Kopf — „jeden Kopf einzeln programmieren"
  ohne Umweg über Matrix- oder EFX-Pfade. Einzelkopf-Geräte bekommen keine
  Kopf-Zeilen, und Geräte, die im Patch-Dialog auf „Als eine Lampe" stehen, auch
  nicht (sonst widerspräche die Liste dieser Einstellung).
- Die gemeinsame Auswahl kennt dafür eine **feinere Ebene**: neben der bisherigen
  Geräte-Auswahl gibt es jetzt eine Zell-Auswahl (`"7"` = ganzes Gerät, `"7:2"` =
  Kopf 3, dieselbe Schreibweise wie Gruppen-Zellen). Für alle bestehenden
  Ansichten ändert sich nichts: die Auswahl-Benachrichtigung trägt weiterhin genau
  die Geräteliste. Ist ein Gerät sowohl als Ganzes als auch per Kopf gewählt, gilt
  „alle Köpfe".
- Eine aktive Kopf-Auswahl **schlägt** den Synchron/Getrennt-Umschalter — sie ist
  eine ausdrückliche Ansage. Damit das nicht in Widerspruch zur Anzeige gerät,
  wird der Umschalter dann abgeblendet und mit „↳ Kopf gewählt — Regler folgen der
  Auswahl" begründet, und die Kopfzeile nennt den Kopf (`[1] PARBAR4 · K2`).
- Tests `tests/test_fm_head_selection_a1.py` (21).

#### Behoben

- Die Gruppen- und Preset-Auswahl markiert weiterhin die Geräte-Zeilen. Ohne
  Nachziehen hätten die neuen Kopf-Zeilen sie ins Leere laufen lassen — dieselbe
  Falle wie damals bei den Kopf-Zellen in Fixture-Gruppen.
### 2026-07-27 — Button-Anleitung nennt den Pflicht-Selektor für „Laser-Muster abrufen" (CDX-16/26/27)

#### Geändert

- **Die Button-Anleitung erklärt jetzt, warum „Laser-Muster abrufen" scheinbar
  nichts tut.** Die Einstellungs-Tabelle in `docs/anleitung_vc_widgets/01_button.md`
  hatte keine Zeile für den Selektor **Laser-Muster (Palette)** — man konnte die
  Aktion also anlegen, ohne das dafür zwingend nötige Feld zu finden, und der
  Button blieb beim Drücken still wirkungslos. Die Zeile steht jetzt an der
  echten Dialog-Position und ist als Pflichtfeld markiert, mit Verweis darauf,
  wo Muster angelegt werden.

_Ausserdem Backlog-/Report-Pflege ohne Verhaltensänderung: die A3D-Zeilen im
BACKLOG waren bei fester Breite mitten im Satz abgeschnitten und dadurch nicht
als Arbeitsauftrag nutzbar (aus der Audit-Quelle regeneriert), und ein
nachträglich als falsch erkanntes Verdikt im Anleitungen-Audit vom 2026-07-20
wurde als „revidiert" markiert statt still überschrieben._


### 2026-07-27 — Rasterzellen zeigen, zu welchem Gerät und Kopf sie gehören (FM-HEADLAYOUT Slice 4)

#### Geändert

- **Im Fixture-Gruppen-Raster hat jetzt jedes Gerät seinen eigenen Farbton, jeder
  Kopf seine eigene Helligkeit.** Vorher waren alle Zellen gleich blau — in einer
  zusammengelegten Kopf-Matrix (z. B. 2× Hydrabeam = 8 Kopf-Zellen) ließ sich
  nicht ablesen, welche Zelle zu welchem Gerät gehört. Köpfe eines Geräts teilen
  den Farbton und werden von K1 aufwärts aufgehellt, sodass auch die
  Kopf-Reihenfolge sichtbar ist.
- Der Farb-Index ist die **Position des Geräts in der Raster-Reihenfolge**, nicht
  die Geräte-Nummer: damit sind die Geräte *einer* Gruppe garantiert
  unterschiedlich gefärbt (bei „Nummer modulo Palette" hätten z. B. Gerät 1 und
  Gerät 9 denselben Ton bekommen). Der erste Ton ist das bisherige Blau, also
  sehen Gruppen mit einem Gerät genauso aus wie vorher.
- Die Aufhellung ist gedeckelt, damit die weiße Zellbeschriftung auch bei
  vielköpfigen Panels lesbar bleibt.
- **Neue Legende „Farbe → Gerät"** unter dem Raster (Farbfeld, Label, Kopfzahl) —
  sie zieht ihre Farben aus derselben Funktion wie die Zellen, kann also nicht
  auseinanderdriften. Bei nur einem Gerät im Raster bleibt sie ausgeblendet.
- Tests `tests/test_fm_headlayout_slice4_cell_colors.py` (16 Fälle: eigene Töne je
  Gerät, gleicher Ton mit monotoner Kopf-Rampe, Helligkeits-Deckel,
  Abgrenzung aufgehellter Kopf gegen Nachbargerät, Palette-Umlauf, Paint-Durchlauf
  mit gemischten Zellen, Legende sichtbar/versteckt/aktualisiert).
### 2026-07-27 — Laser-NOT-AUS verriegelt DMX-Laser sofort, nicht erst nach dem Netzwerk (CDX-25)

#### Behoben

- **Der NOT-AUS legt DMX-Laser jetzt augenblicklich still — auch wenn ein
  Netzwerk-Laser nicht erreichbar ist.** Bisher setzte `estop_all()` die
  DMX-Verriegelung erst NACH dem Durchlauf aller Netzwerk-Verbindungen. Da jeder
  dieser Aufrufe ein Socket-Roundtrip mit 0,5 s Zeitlimit ist, blieb ein
  DMX-Muster-Laser (z. B. L2600) bei einem hängenden oder abgezogenen DAC pro
  Gerät bis zu eine halbe Sekunde weiter hell, obwohl der NOT-AUS schon gedrückt
  war. Die Verriegelung läuft jetzt zuerst, die Netzwerk-Zustellung danach —
  dieselbe fail-safe Reihenfolge wie bei CDX-12.
- **Ein fehlgeschlagener NOT-AUS ist nicht mehr unsichtbar.** Ein stilles
  `except: pass` um genau diese Verriegelung liess einen misslungenen NOT-AUS wie
  einen erfolgreichen aussehen; der Fehler wird jetzt protokolliert (die
  Netzwerk-Ebene verriegelt unabhängig davon weiter).

_Der ursprünglich gemeldete Befund („der VC-Button latcht DMX-Laser gar nicht")
war ein Fehlalarm — `estop_all()` ruft `set_laser_estop(True)` selbst, und
`clear_estop_all()` hebt den Latch nicht auf. Neue Tests nageln beides fest._

### 2026-07-27 — Köpfe im Gruppen-Raster selbst anordnen (FM-HEADLAYOUT Slice 3)

#### Hinzugefügt

- **Die Köpfe eines Mehrkopf-Strahlers lassen sich jetzt von Hand ins Raster
  legen — waagerecht oder hochkant.** Neuer Button **„Köpfe einzeln → Raster ▾"**
  im Fixture-Gruppen-Editor mit „als Zeile (waagerecht)", „als Spalte
  (hochkant)" und „Köpfe zusammenfassen (eine Zelle)". Bisher konnte man ein
  Mehrkopf-Gerät nur als **eine** ganze Zelle aufs Raster ziehen; Kopf-Zellen
  entstanden ausschließlich automatisch beim Patchen als 1×N-Reihe. Damit folgt
  das Raster jetzt dem realen Rig-Aufbau (Hydrabeam hochkant an der Traverse vs.
  Spider-Bar waagerecht), und die Köpfe bleiben einzeln verschiebbar (Drag),
  tauschbar und entfernbar (Rechtsklick).
- Der Streifen bleibt **zusammenhängend**: passt er ab der Startzelle nicht mehr
  ins Raster, rutscht der Start zurück statt hinten abzuschneiden. Ist das Raster
  für die gewünschte Richtung zu klein (die Auto-Kopf-Matrix hat nur **eine**
  Reihe), **wachsen Reihen bzw. Spalten mit** — sonst wäre ein „hochkant"-Wunsch
  über die Ausweichregel wieder als Reihe gelandet, also das Gegenteil der
  Anweisung.
- Die Raster-Invarianten bleiben: kein stilles Überschreiben fremder Zellen (ein
  Kopf weicht auf die nächste freie aus), kein Duplikat desselben Geräts, und bei
  vollem Raster wird nichts zerstört (mit Angabe, wie viele Köpfe gesetzt wurden).
  Kopfzahl kommt aus derselben Quelle wie die automatische Kopf-Matrix
  (`color_head_count`), damit Hand- und Auto-Anlage nicht auseinanderdriften.

#### Behoben

- **Ein Mehrkopf-Gerät konnte sich beim Ablegen selbst blockieren.** Füllten
  seine eigenen Kopf-Zellen das Raster komplett (genau die Form der 1×N-Auto-
  Kopf-Matrix), scheiterte der Drop des ganzen Geräts still — die Zielsuche
  zählte die eigenen Zellen als belegt, obwohl der Drop sie ohnehin freigibt.
  Eigene Zellen gelten jetzt als frei; fremde blockieren weiterhin. Drop-Vorschau
  und tatsächliche Platzierung bleiben dabei deckungsgleich.
- Tests `tests/test_fm_headlayout_slice3_head_cells.py` (24 Fälle: Streifen-
  Geometrie in beiden Richtungen, Start-Rückschub, Raster-Wachstum,
  Kollisionsschutz, Duplikat-Freiheit, Teilplatzierung, Zusammenfassen in
  Raster-Reihenfolge, Selbstblockade-Regression, View-Verdrahtung mit echtem
  Spider vs. Einzelkopf-PAR).

### 2026-07-27 — „Mehrkopf-Programmierung" steuert die Programmer-Farbregler (FM-HEADLAYOUT Slice 2)

#### Geändert

- **Die Wahl am Gerät entscheidet jetzt, ob Köpfe einzeln oder als eine Lampe
  programmiert werden.** Die per-Fixture-Option „Mehrkopf-Programmierung" aus
  Slice 1 wirkte bisher nur auf die automatische Kopf-Matrix-Gruppe beim
  Patchen — die Farbregler im Programmer hingen allein am globalen Umschalter
  „Köpfe: Synchron / Getrennt". Neu gilt: **`Köpfe einzeln` → Regler pro Kopf,
  `Als eine Lampe` → ein Regler je Farbe für alle Köpfe, `Automatisch` → wie
  bisher die globale Voreinstellung.** Die Vorrang-Regel liegt als reine
  Funktion `effective_color_head_mode` im Leaf-Modul `core/head_mode.py` (eine
  Quelle für UI, Tests und spätere Kopf-Auswahl in Matrix/EFX/VC).
- **Gemischte Auswahl zeigt beide Blöcke.** Sind ein „Köpfe einzeln"- und ein
  „Als eine Lampe"-Gerät gleichzeitig ausgewählt, entstehen beide Regler-Sätze
  mit Zwischen-Überschrift (welches Gerät zu welchem Block gehört) — vorher
  überstimmte eine globale Einstellung beide Geräte. Ein Pro-Kopf-Regler kann
  dabei nie mehr einen `attr#N`-Wert auf einem „eine Lampe"-Gerät anlegen (die
  Zuordnung läuft pro Block statt über die ganze Auswahl).
- **Der globale Umschalter plättet keine gewollten Pro-Kopf-Farben mehr:** beim
  Wechsel auf „Synchron" bleiben Geräte auf „Köpfe einzeln" unangetastet (für
  „Automatisch" räumt er weiter auf wie bisher). Stehen alle ausgewählten
  Mehrkopf-Geräte auf einer festen Wahl, ist der Umschalter deaktiviert statt
  wirkungslos bedienbar — mit Hinweis auf den Patch-Dialog.
- Ein Gerät, das nach früherem Pro-Kopf-Programmieren auf „Als eine Lampe"
  gestellt wird, wird beim ersten Regler-Zug wieder einheitlich (der
  Synchron-Regler räumt die `attr#N`-Abweichungen weg) — sonst hätte der Regler
  auf der zweiten Bank tot gewirkt.
- Tests `tests/test_fm_headlayout_slice2_programmer_head_mode.py` (15 Fälle:
  Vorrang-Tabelle, beide Richtungen gegen die globale Wahl, `auto`-Regressions-
  schutz, Wiedervereinigung getrennter Köpfe, gemischte Auswahl inkl. Prüfung
  beider DMX-Bänke, Schalter-Gate).
- Bei der Live-Abnahme nachgezogen: ist der globale Umschalter wirkungslos
  (alle ausgewählten Mehrkopf-Geräte haben eine feste Wahl), wird er jetzt
  sichtbar abgeblendet und mit „pro Gerät gesetzt (Patch-Dialog)" erklärt —
  vorher sah er bedienbar aus und ein Klick tat einfach nichts.

### 2026-07-27 — Zwei echte Pixel-Panels in der Geräte-Bibliothek (FM-13)

#### Hinzugefügt

- **ADJ Dotz Matrix** und **Stairville Pixel Panel 144 RGB** sind jetzt fertige
  Geräte in der Bibliothek — bisher gab es für Pixel-Panels nur das generische
  „LED Matrix Panel". Beide lassen sich patchen wie jedes andere Gerät und
  erscheinen im 3D-Visualizer mit ihrem echten Raster: die Dotz Matrix als 4×4
  (16 Pixel), das Stairville-Panel als 12×12 (144 Pixel), jeder Pixel einzeln
  färbbar. Die schmalen Modi der Geräte (bei denen das ganze Panel eine Farbe
  bekommt) zeigen entsprechend eine Fläche.
- Alle Kanal-Zuordnungen stammen aus den Hersteller-Anleitungen und wurden
  zusätzlich gegen eine unabhängige Fixture-Datenbank geprüft. Strobe steht
  beim Patchen auf „aus", die Farb-Makros auf „manuelle Steuerung" — ein frisch
  gepatchtes Panel blitzt also nicht und läuft kein Automatikprogramm.

#### Gut zu wissen

- **Dotz Matrix: „Pixel Flip" am Gerät auf `Flip 4` stellen.** Ab Werk zählt das
  Gerät seine Pixel in Schlangenlinien (erste Reihe von links, zweite von
  rechts), LightOS zeigt sie dagegen zeilenweise an. Ein Lauflicht liefe sonst
  auf dem echten Panel im Zickzack. `Flip 4` stellt die zeilenweise Reihenfolge
  her, danach stimmt 3D-Ansicht und Realität überein.

### 2026-07-26 — Kein Blackout-Puls mehr beim Live-Show-Load (CDX-22)

#### Behoben

- **Jeder Show-Load im laufenden Betrieb blitzte das Rig kurz schwarz.** Der
  `reset-first`-Pfad von `load_show` (STAB-19b) ruft `_reset_state` bewusst mit
  `blackout_output=False`, um genau das zu vermeiden — der Guard überspringt aber
  nur den expliziten `universe.clear()`/`_flush_all_to_dmx()`. Zwei andere
  Schritte nullten die alten Adressen trotzdem, und der 44-Hz-Output-Thread
  sendete diese Nullen physisch, bis der neue Patch geladen **und** gerendert war:
  1. Der leere Zwischen-Patch (`replace_patch([])`) ließ die A3D-18-Freigabe
     **jede** bisher gepatchte Adresse als „jetzt frei" sofort auf 0 setzen. Neu
     bündelt `AppState.deferred_unpatched_release()` die Freigabe über den
     gesamten, mehrstufigen Patch-Tausch: im Fenster wird nur gemerkt, am Ende
     einmal gegen den dann gültigen Patch freigegeben. Adressen, die die neue
     Show weiter belegt, bleiben unberührt; genuin entpatchte Adressen werden
     weiter deterministisch freigegeben (A3D-18/CDX-17 unverändert, auch wenn der
     Patch-Tausch mitten drin wirft).
  2. Der Programmer-Clear im Patch-Replace flushte, **während der alte Patch noch
     geladen war**, jedes alte Fixture auf seine Kanal-Defaults (Dimmer 0).
     `clear_programmer(flush=False)` unterdrückt jetzt genau diesen DMX-Flush im
     Ladepfad; der Loader flusht unmittelbar danach ohnehin erneut — dann gegen
     den neuen Patch. In-Memory-Clear und WEB-01-Release laufen unverändert.
  **Safety-Ausnahme:** Adressen bisheriger DMX-Laser werden auch im Ladefenster
  sofort freigegeben. Solange der Render-Plan sie nicht kennt, greift an ihnen
  weder die Renderer-Nullung noch die OutputManager-Maske eines *dann*
  ausgelösten NOT-AUS — ein Laser darf im Ladefenster nicht unerreichbar
  weiterstrahlen, ein kurzer Dunkel-Dip ist dort das sichere Verhalten.
  Regressionstest `tests/test_cdx22_load_no_blackout_pulse.py` (11 Fälle, u. a.
  Ende-zu-Ende über `load_show`: kein einziger 0-Schreibvorgang auf einer weiter
  gepatchten Adresse; Gegenproben, dass eine entpatchte Adresse trotzdem
  freigegeben wird und dass Laser-Adressen nie aufgeschoben werden).
  [Codex #386]

### 2026-07-26 — BPM „0/aus" hält auch gegen in-flight Auto-Quellen (CDX-23)

#### Behoben

- **„BPM = 0/aus" sprang unter Last doch zurück.** Die automatischen
  Tempo-Quellen (Audio-Detektor, OS2L/VirtualDJ, Timeline, Datei, TempoBus)
  prüften „läuft der Leader noch auf AUTO?" und schrieben die BPM danach in
  einem zweiten Schritt. Drückte man im BPM-Dialog genau dazwischen die `0`,
  war die Prüfung schon durch und der Wert landete trotzdem — der Zähler sprang
  von 0 wieder auf die erkannte BPM. Prüfung und Schreiben laufen jetzt in
  einem Zug (`set_bpm(..., only_if_auto=True)`), sodass ein manuelles „aus"
  (und ebenso der Lock) auch eine bereits angelaufene Quelle sicher überstimmt.
  Manuelles Setzen, Tap/Nudge und das Auftauen nach Freeze sind unverändert.

### 2026-07-26 — Bergung aus den Alt-Branches

Beim Aufräumen der 24 nie gemergten Branches wurden 18 als überholt verifiziert und
gelöscht; aus vier steckte noch echte Arbeit drin, die hier landet.

#### Behoben

- **Mapped-Channel-Regeln erreichten bei Mehrkopf-Geräten nur den ersten Kopf.**
  `MappedChannelChange.write` gattete den Basiswert-Fallback auf `head == 0`. Eine
  Regel mit `per_head=False` — dem **Default** jeder neuen Regel — schrieb damit auf
  einem 4-Kopf-Gerät (Hydrabeam 4000, MOVBAR4, Spider, LED-Bar) nur die erste
  RGB-Bank: gemessen `[73, 0, 0, 0]` statt `[73, 73, 73, 73]`. Jetzt spiegelt Kopf>0
  den Basiswert, wie es `efx.py`/`resolve_attr_channels` längst tun. Der Pfad hatte
  bis dahin **null** Testabdeckung — ENG-11 hatte ihn beim attr#N-Sweep übersehen.
  Test: `tests/test_mapped_channel_multihead.py`.
- **Show-Dateien waren nach dem ersten Speichern nicht stabil.** Der Dump schrieb ein
  leeres Label als `""`, der Loader machte daraus `"Fixture 7"` — der erste
  save→load→save änderte die Datei also still (Diff-Rauschen in Git). Beide
  Dump-Zweige kanonisieren jetzt wie der Loader.
  Tests: `tests/test_show_roundtrip_fixpoint.py` (Fixpunkt über alle committeten
  Shows + gezielte Label-Regression).
- **Audio-Ansicht meldete ihre Worker-Callbacks nie ab.** `AudioCapture`/
  `BeatDetector` halten die gebundene Methode stark; ohne `closeEvent`-Teardown pinnt
  jede gebaute View sich an den Singleton und `process_chunk` läuft mehrfach. Gleiches
  Muster wie `MidiView.closeEvent`, idempotent.

#### Tests

- `tests/test_effect_layer_chain.py` — der Ausgabepfad `LayeredEffect.write` (Layer-Kette
  → Clamp → DMX-Adresse) lief bisher in **keinem** Test gegen ein echtes Universe;
  dazu die Listenoperationen des Editors (`_add_layer`/`_move_up`/`_delete`).

### 2026-07-26 — Alt-Shows auf das aktuelle Format gehoben (Davids Entscheidung)

Die committeten Demo-Shows lagen noch auf `version "1.1"` (aktuell: `1.2`). Sie luden
zwar weiter — der Loader ergänzt fehlende Felder mit Defaults — aber die **Dateien**
blieben alt, bis sie einmal gespeichert wurden. David: „die kannst du upgraden auf die
neueste Version."

#### Neu

- **`tools/upgrade_shows.py`** — hebt `.lshow`-Dateien per `load_show` → `save_show` auf
  `SHOW_VERSION`. Mit `--check` nur prüfen (Exit 1, wenn etwas veraltet ist). Vier
  Sicherheitsnetze pro Datei, sonst wird aus dem Backup zurückgerollt: kein verlorener
  Top-Level-Block (`layout` wird durchgereicht — `save_show` schreibt es nur, wenn es
  übergeben wird), unveränderte Anzahl Fixtures/Funktionen/VC-Widgets/Cuelisten/Paletten,
  Version danach wirklich aktuell, und **Fixpunkt** (ein weiterer load→save ändert nichts
  mehr). Fremdformate werden erkannt und nicht angefasst.
- **`tools/build_demo_rgb_par.py`** — baut `shows/demo_rgb_par.lshow` als echte Show.

#### Behoben

- **Eine Fremdformat-Datei „lud" still als LEERE Show.** `shows/demo_rgb_par.lshow` war
  keine Alt-Show, sondern ein nie implementierter Format-Entwurf (Commit 4a90339,
  2026-05-27): eigene `show.json` mit `format_version`/`universes` plus separate
  ZIP-Einträge `patch.json`, `sequences/seq_001.json`, `groups.json`, … `load_show` kennt
  nur `show.json` im heutigen Schema, fand darin **keinen einzigen** Block und meldete
  trotzdem `ok=True` samt „Show 'Demo RGB PAR Show' geladen." — der Nutzer stand vor einer
  leeren Bühne, ohne eine Warnung. Zwei Monate unbemerkt. **Fix:** `load_show` lehnt eine
  `show.json` ohne `version` UND ohne jeden bekannten Block jetzt ab; das Gate greift VOR
  dem reset-first, die offene Show bleibt also erhalten. Ein von `save_show` geschriebenes
  Show kann dort nie hängenbleiben (Gegenprobe im Test).
- **Die Datei selbst neu gebaut** — mit demselben Inhalt wie der Entwurf: 4× `PAR3`
  („LED PAR RGB 3ch", R/G/B) auf Universe 1 Adressen 1/4/7/10 als „PAR 1".."PAR 4",
  Gruppe „Alle PAR" (4×1), Cueliste „Demo-Show" mit den vier Original-Cues inkl.
  Fade-Zeiten (Blackout · Warm White · Rot · Blau), Executor 1 gebunden, Palette
  „Warm White". Statt 639 Byte Leershow lädt sie jetzt echte 4 Geräte.

#### Geändert

- Alle fünf committeten Shows liegen auf `v1.2` — inhaltlich unverändert (nachgewiesen:
  gleiche Anzahl Fixtures/Funktionen/VC-Widgets, kein verlorener Block). Der Upgrade
  schreibt nur die additiven Defaults neuer Features (`tempo_bus_id`, `env_curve`,
  `priority`, `head_grid`, `scene_graph`, `laser_figures`, …) in die Datei. Ausnahme mit
  Absicht: `Demo_Show_Full` hatte veraltete 2D-Positionen im `live_view`-Block — der
  Loader leitet 2D seit VIZ-11 aus den 3D-Weltpositionen ab (3D ist führend), die Datei
  hält jetzt also das, was die App ohnehin anzeigt.
- `tests/test_viz11_migration_gate.py` überspringt Dateien, die der Loader als
  Fremdformat ablehnt (kein Migrations-Regress) — jeder andere Ladefehler bleibt hart.

#### Tests

- `tests/test_show_format_upgrade.py` — Fremdformat wird abgelehnt (mit Marker in der
  Meldung) · die offene Show überlebt eine abgelehnte Datei · Gegenprobe: eine von
  `save_show` geschriebene und eine Alt-Show ohne `version` laden weiter · jede committete
  Show trägt `SHOW_VERSION` (fällt nach dem nächsten Bump um → `tools/upgrade_shows.py`) ·
  `--check` des Werkzeugs ist grün · `demo_rgb_par.lshow` lädt mit 4 PARs auf 1/4/7/10 und
  der 4-Cue-Cueliste.

### 2026-07-26 — Cross-Platform-Härtung des Linux-Audits

Nachzug vor dem Merge: der Linux-Stabilitätsbranch wurde gegen Windows
gegengeprüft (CI-identische Umgebung Python 3.11 + PySide6 6.11.1, adversariale
Review). Die Linux-Verbesserungen bleiben vollständig erhalten.

#### Behoben

- **Windows-Heap-Corruption im Qt-Abbau.** Die VC-Arbeitsfläche wuchs über
  `QScrollArea.setWidgetResizable(True)` mit. Da die VC denselben `VCCanvas` per
  `takeWidget()`/`setWidget()` zwischen Haupt- und Popout-Fenster reicht,
  destabilisierte das den nativen Widget-Abbau: gemessen 7 von 8 Läufen rot
  (`STATUS_HEAP_CORRUPTION`, 0xc0000374) gegenüber 1 von 8 auf `main`. Ersetzt
  durch `GrowingScrollArea`, die den Inhalt selbst auf
  `max(Mindestgröße, Viewport)` zieht — gleiches Bild auf breiten Touchscreens,
  wieder 0 von 8 rot.
- **VC-Layout bleibt portabel.** Die Canvas-Mindestgröße wächst jetzt mit dem
  Inhalt (`_update_content_extent`). Ein auf dem 1920-px-Touchscreen jenseits
  von 1200 px abgelegtes Widget ist auf einem kleineren Bildschirm bzw. im
  Popout wieder erscrollbar statt unsichtbar und unerreichbar.
- **MIDI-Ausgang stirbt nicht mehr still.** Ein nicht auflösbarer Portname
  schloss den LAUFENDEN Ausgang, ließ `_output`/`_output_name` aber gesetzt —
  der Manager meldete weiter „offen", es ging nie wieder ein Byte raus, und der
  Frühausstieg verhinderte jedes Wiederöffnen bis zum Neustart. Ausgelöst vom
  Mapping-Feedback bei einem plattformfremden Portnamen aus der Show.
- **Explizite Portauswahl ist wieder exakt** (`open_output(..., allow_hint=False)`
  aus der MIDI-Ansicht). Der Teilstring-Vergleich schluckte sonst die Auswahl
  „APC mini mk2", solange „MIDIOUT2 (APC mini mk2)" offen war, und meldete
  trotzdem grün Erfolg. Portable Profil-Hinweise wie `APC` lösen weiterhin
  unscharf auf.
- **APC-LED-Feedback kapert keinen fremden Ausgang mehr** und sendet nur, solange
  der geteilte Ausgang noch auf den APC zeigt. Sonst gingen die Pad-Noten an das
  zuletzt gewählte Gerät (unter Windows hörbar auf dem GS Wavetable Synth).
- **Ein gescheiterter MIDI-Ausgang legt die Eingänge nicht mehr lahm.** Der
  Circuit-Breaker galt für beide Richtungen; nach einem Ausgangsfehler fand der
  Autoconnect keine Eingänge mehr und der APC war bis zum Neustart taub.
- **Gehaltene Flash-Taste bleibt nicht mehr hängen.** Der fokusgebundene
  Hotkey-Filter verwarf beim Fokuswechsel die aktiven Tasten, ohne das Release
  zuzustellen — das Licht blieb an. Zusätzlich weicht der Filter jetzt auf das
  Fenster aus, wenn der Fokus im Chromium-Baum des 3D-Visualizers liegt oder gar
  kein Widget ihn hält; VC-Hotkeys bleiben damit auch dort erreichbar, ohne je am
  Chromium-Renderbaum zu hängen (das war die Linux-Absturzursache).
- **Nicht anlegbare Einzelinstanz-Sperre verhindert den Start nicht mehr.**
  Rechteproblem oder Netz-/Cloud-Ordner galten als „läuft schon"; LightOS ließ
  sich dann gar nicht mehr starten. Jetzt läuft es ohne Mehrfachstart-Schutz
  weiter. Ein echter Zweitstart meldet sich unter Windows sichtbar per Dialog
  statt nur mit einer Konsolenzeile, die niemand sieht.
- **`--help` und Argumentfehler funktionieren wieder**, während LightOS läuft
  (argparse läuft jetzt vor der Sperre).
- **Kein stiller Datenverlust beim Beenden.** Die „Show speichern?"-Abfrage hing
  am Schalter `LIGHTOS_NO_RECOVERY_PROMPT`, der laut Doku nur den
  Autosave-Dialog beim Start abschaltet. Sie nutzt jetzt einen eigenen Guard und
  greift auf einem echten Desktop immer.
- **VC-Bibliothek verliert die Auswahl nicht mehr bei jedem Tabwechsel** — der
  Baum wird nur bei tatsächlicher Änderung neu aufgebaut.
- **MIDI-Robustheitstests laufen ohne `python-rtmidi`** (CI und frische venvs);
  sie scheiterten dort mit `AttributeError`.
- **Linux-Audioeingang bleibt auf der belegten Buchse.**
  `tools/linux_audio_input_guard.sh` korrigiert bei kompatiblen Realtek-Codecs
  den Capture-MUX automatisch auf die per Jack-Sense erkannte zweite
  Mikrofonbuchse, falls PipeWire ihn auf den leeren Eingang zurücksetzt.

### 2026-07-23 — Linux-Stabilitätsaudit

#### Behoben

- Mehrfachstarts werden vor der Initialisierung von Qt, ALSA und WebEngine über
  eine betriebssystemweite Einzelinstanz-Sperre abgefangen.
- Audio und MIDI starten auch bei nicht erreichbarem PulseAudio/ALSA-Sequencer
  weiter; MIDI-Portscans sind serialisiert und besitzen einen
  10-Sekunden-Circuit-Breaker gegen native Client-Stürme.
- Show-Dateien validieren Fixture-Profil-IDs gegen Hersteller/Modell und mappen
  abweichende lokale Datenbank-IDs automatisch nach Namen.
- 2D-Bühnenvorschau auf 10 FPS begrenzt, ohne DMX- oder Playback-Timing zu
  verändern; Tab-Titel bleiben bei 1440 px vollständig lesbar.
- Headless-Schließen, MIDI-Ansicht und plattformübergreifende Janitor-Pfade
  gegen reproduzierte Fehler gehärtet.
- Der App-Exit stoppt und joint Audio-Capture und deaktiviert MIDI-Autoconnect
  vor dem nativen Backend-Abbau; damit tritt der reproduzierte PulseAudio-
  `SIGSEGV` nach bereits gemeldetem sauberem Exit nicht mehr auf.
- Qt-WebEngine erhält `AA_ShareOpenGLContexts` vor `QApplication`; der
  Produktionsabschluss führt alle Finalizer aus und überspringt anschließend
  den bekannten fehlerhaften QtWebEngine-Interpreterabbau.
- Der app-weite Python-Eventfilter für VC-Tastatur-Hotkeys wird nicht mehr in
  den Chromium-Renderbaum des 3D-Visualizers eingehängt. Ein fokusgebundener
  Filter erhält Press/Release- und Flash-Hotkeys, verhindert aber den unter
  Linux reproduzierbaren nativen Segmentation Fault von Virtual Console + 3D.
- Die Virtual-Console-Arbeitsfläche wächst auf breiten Touchscreens nun bis zur
  vollständigen Viewportgröße, statt starr bei 1200 px zu enden und rechts eine
  große unbenutzbare Fläche zu lassen. Kleine Fenster bleiben scrollbar; das
  gespeicherte Layout und das Snapraster ändern sich nicht.
- Die Bibliothek der Virtual Console aktualisiert sich beim Öffnen der Ansicht
  sowie bei Änderungen an ID, Name, Ordner oder Typ einer Funktion. Effekte,
  die nach dem Erstellen umbenannt oder etwa nach `Hintergrund/Dimmer`
  verschoben werden, erscheinen damit ohne manuelles Neuladen in der VC.
- RtMidi-Hotplug-Scans verwenden unter ALSA je einen langlebigen Discovery-
  Client für Ein- und Ausgänge. Dadurch sammeln sich bei wiederholten Scans
  keine leeren Sequencer-Clients mehr an, die nach längerer Laufzeit MIDI mit
  `Cannot allocate memory` blockieren.
- Linux/ALSA: APC-Ausgänge verwenden einen einzigen zentralen RtMidi-Client.
  Portable Profil-Hinweise wie `APC` werden auf den realen mk2-Control-Port
  aufgelöst; wiederholte Scans, LED-Feedback und Mapping erzeugen keine
  Sequencer-Client-Flut mehr. Fehler beim Öffnen bleiben in der MIDI-Ansicht
  sichtbar, statt als unbehandelte Qt-Slot-Exception im Crashlog zu landen.
- Die Audio-Input-Ansicht bietet neben PC-Loopback nun auch echte Mikrofon-/
  Line-In-Geräte an und schaltet Quelle plus Gerät gemeinsam um.
- Prozessisolierte ENTTEC-Worker werden beim Beenden auch dann explizit
  geschlossen, wenn der DMX-Output-Thread sein Join-Timeout überschreitet.
  Dadurch bleibt nach dem App-Ende kein verwaister Prozess zurück, der den
  USB-Port belegt. Direkte serielle Geräte behalten den Windows-Schutz gegen
  paralleles `CloseHandle`/`WriteFile`.

Details und Prüfergebnisse:
`docs/LINUX_STABILITY_FULL_CHECK_2026-07-23.md`.

### 2026-07-23 — FM-HEADLAYOUT (Slice 1): Mehrkopf-Programmierung pro Fixture + Kopf-Matrix wiederherstellen

#### Hinzugefügt

- **Die beim Patchen automatisch erzeugte Pro-Kopf-Matrix-Gruppe („… · Köpfe") lässt sich jetzt wiederherstellen** — ohne das Gerät neu patchen zu müssen (David-Wunsch 2026-07-22: bei einer Hydrabeam 4000 in einer Produktiv-Show gelöscht, danach kein Weg zurück). Im Patch-Dialog (Gerät doppelklicken) zeigt eine neue Zeile **„Kopf-Matrix-Gruppe"** den ehrlichen Status **„vorhanden" / „fehlt" / „über andere Gruppe abgedeckt"** plus einen **„Wiederherstellen"**-Button (wirkt sofort, idempotent, nicht-destruktiv).
- **Neue per-Fixture-Option „Mehrkopf-Programmierung"** (`PatchedFixture.head_mode`: `auto` | `heads` | `single`) — bewusst **an derselben Stelle wie Invert Pan/Tilt & Swap**, sichtbar nur bei echten Mehrkopf-Geräten (≥2 pro-Kopf färbbare Bänke). `auto` (Default) = Bestandsverhalten (Auto-Anlage beim Patchen), `heads` = die Kopf-Matrix soll existieren (wird beim Speichern angelegt), `single` = als EINE Lampe (keine automatische Kopf-Matrix). **Der Modus löscht NIE eine bestehende Gruppe** — zusammengelegte/bearbeitete Matrizen bleiben unangetastet; `single` unterdrückt nur das automatische Neuanlegen.
- **Rückwärtskompatibel (Fallenklasse #3):** additive `ALTER TABLE`-Migration mit `PRAGMA`-Guard (wie seinerzeit `spider_dual_tilt`), Persistenz über `d.get(…, "auto")` → **Alt-Shows ohne den Schlüssel laden unverändert** und verhalten sich exakt wie bisher. Kanonischer Normalisierer `models.normalize_head_mode` als EINE Quelle für Show-Persistenz, Live-Schreibpfad und Undo (klemmt Garbage aus Skript-/Remote-Pfaden auf `auto`).
- Neue read-only `AppState.find_head_matrix_group(fid, *, dedicated=False)` — **breit** (irgendeine Gruppe adressiert das fid kopfweise) für die Idempotenz von `create_head_matrix_group`, **eng** (die dedizierte „Multi-Head"-Auto-Gruppe) für die Statusanzeige.

#### Behoben (adversariale Review, 13 bestätigte Funde — vor Merge gefixt)

- **HIGH:** `head_mode` fehlte in der `allowed`-Whitelist von `AppState.update_fixture` → die Modus-Wahl aus dem Dialog wurde **still verworfen** (Feature-Hälfte tot). Jetzt in der Whitelist + normalisiert.
- **MEDIUM:** Der Undo-Snapshot (`AppState._fixture_to_dict`/`_restore_fixture_dict`) kannte das Feld nicht → Löschen + Rückgängig setzte den Modus auf `auto` **und legte die per `single` unterdrückte Gruppe wieder an**.
- **MEDIUM:** Die Statusanzeige meldete „vorhanden", sobald **irgendeine** Gruppe eine `fid:head`-Zelle hatte (z. B. eine zusammengelegte Matrix) → „Wiederherstellen" wäre ein stiller No-Op gewesen. Jetzt enges Prädikat + dritter Status „über andere Gruppe abgedeckt".
- **MEDIUM:** Die Gruppe wurde in `_on_accept` **vor** dem Persistieren gebaut (stale Label/Kanalzahl). Jetzt setzt der Dialog nur ein Flag; der Aufrufer legt sie **nach** `update_fixture` aus dem frischen Patch-Objekt an.
- **LOW:** Ein fehlgeschlagener Idempotenz-Scan galt als „nicht vorhanden" → hätte ein **Duplikat** angelegt; der Scan wirft jetzt und `create` bricht sauber ab. Button-Tooltip weist darauf hin, dass „Wiederherstellen" sofort wirkt.

Tests `tests/test_head_mode_option.py` (21) — u. a. echter Alt-DB-`ALTER TABLE`-Zweig mit Bestandszeile, `update_fixture`-Round-Trip, Undo-Erhalt inkl. Unterdrückung, Gate für alle drei Modi, eng-vs-breit-Prädikat. _(Nächste Slices: Programmer-UI passt sich am Modus an, freies Pro-Kopf-Platzieren im Grid-Editor — brauchen Davids visuelle Abnahme.)_

### 2026-07-22 — FM-15: Robe MegaPointe als Builtin (namhafter Beam/Spot/Wash-Hybrid, 39ch)

#### Hinzugefügt

- **Neues Builtin „Robe MegaPointe" (`MEGAPNT`, 39-Kanal Standard-16-bit-Modus, `moving_head`).** Namhafter Profi-Beam/Spot/Wash-Hybrid mit dem vollen Feature-Set (CMY-Farbmischung + Farbrad, 2 Gobo-Räder + Rotation, 2 Prismen, Effektrad, Frost, Zoom, Fokus, Shutter/Strobe, Dimmer). **Chart doppelt verifiziert:** offizielles Robe-DMX-Protokoll v1.5 + unabhängige Blizzard-Lighting-Fixture-Library (`.fix`, Brand Robe) — kanal-für-kanal deckungsgleich. _(QLC+ und OFL enthalten die MegaPointe **nicht** — nur die ältere, andere Pointe; daher Robe-Protokoll + Blizzard-Lib als Doppelquelle.)_
- **Korrektheits-Details:** Farbe über echtes **CMY** (`cmy_c/m/y`, FLA-2-Kanonik) + Farbrad — **kein** RGB. **Keine Iris** (die MegaPointe hat keinen Iris-Kanal; fehlerhafte Community-Charts erfinden eine — Beam-Verkleinerung läuft über Zoom + Beam-Reducer im statischen Gobo-Rad). Kern-Beam-Features über kanonische Attribute (exact-match, keine Vokabular-Änderung nötig); Spezial-/Fine-Kanäle ohne kanonisches Attribut (virtuelles Farbrad, Effektrad, Pattern, Beam-Shaper, Hotspot, 2. Prisma, alle Fine-Kanäle) → `raw` (etablierte Konvention, vgl. L2600-Fines). **Single-Head** trotz der wiederholten `raw`-Kanäle (0 `color_r`, 1 Pan / 1 Tilt → `is_spider_fixture` False, `moving_head`/`buildMovingHead` wiederverwendet). **Safety-Defaults:** Shutter 32 = offen (0-31 zu; dunkel via Dimmer 0), Dimmer 0, Power/Special 0 = keine Funktion (kein versehentlicher Reset / keine Lampe-aus).

Tests `tests/test_robe_megapointe_profile.py` (8: verifizierte 39ch-Sequenz, Single-Head-trotz-`raw`, keine Iris, CMY→Color, Safety-Defaults, Shutter-/Power-Range-Sicherheit). _(Der reduzierte 34ch-8-bit-Modus ist eine triviale spätere Ergänzung.)_

### 2026-07-22 — FM16E-HEADCOUNT: Kopf-Matrix-Gruppen zeigen ihre Geräte statt „(0)" (eine Zell-Parse-Quelle)

#### Behoben

- **Eine per `create_head_matrix_group` entstandene Kopf-Matrix-Gruppe („… · Köpfe") zeigte „(0) Geräte" und selektierte nichts im Attribut-Editor.** Mehrere fid-Resolver parsten den `positions_json`-Zellwert je für sich per `int(v)` — das warf bei einer Kopf-Zelle `"5:2"` (`ValueError`) und liess die Zelle **still fallen**. Ein Teilfix in nur einer View hätte eine Cross-View-Inkonsistenz erzeugt, daher **alle** Sites über **eine** Quelle vereinheitlicht.
- **Neues Leaf-Modul `src/core/group_cells.py`** (`parse_group_cell(v)→(fid,head)` + `base_fids_in_grid_order(positions)→[fid]`, dedupliziert, Rasterreihenfolge; dependency-frei → kein Import-Zyklus). Darauf umgestellt: die Kern-Resolver `AppState._group_lookup` (speist `group_fids_by_name`/`select_group_by_name` → VC-Slider/Buttons/Effect-Wizard/Preset-Browser) + `list_fixture_groups`, dazu `ProgrammerView._group_fids` und `EfxView._active_group_fids`. Die beiden schon korrekten Parser (`rgb_matrix._parse_cell`, `fixture_group_view._split_cell`) **delegieren** jetzt an `parse_group_cell` → **keine Parser-Drift** mehr. Kopf-Matrix-Gruppen liefern damit ihre deduplizierten Basis-fids (Count > 0, korrekt selektierbar); reine-fid-Alt-Gruppen unverändert; Matrix-Render (`grids_from_positions`) unverändert.
- **live_view-Gruppen-Panel (adversariale Review, MEDIUM):** dieselbe Klasse, anderes Fehlermodell — die Anzeige reichte den Roh-Zellwert durch, sodass Auswahl einer Kopf-Matrix-Gruppe im Live-Canvas **nichts** hervorhob (Strings in ein `set[int]`), der Zähler „(4)" statt Geräte zeigte und die Detail-Box auf `f"{fid:03d}"` warf. Count + Highlight + Detail laufen jetzt ebenfalls über `base_fids_in_grid_order`. _(Die Add-/Remove-Editierpfade des Simple-Panels reshapen eine Kopf-Matrix wie gehabt auf 1×N — Encoding bleibt erhalten; interaktives 2D-Editieren gehört zu FM-HEADLAYOUT.)_

Tests `tests/test_fm16e_headcount.py` (20: Parser · Delegation-Identität · alle 5 Resolver E2E gegen echte Show-DB · live_view-Panel). Adversariale Review (3 Linsen × Skeptiker, Opus): int()-Skip-Muster vollständig gefixt bestätigt; 1 MEDIUM (live_view) vor Merge gefixt; 2 Kandidaten widerlegt (Exception-Granularität unverändert; Float-Zellwerte kommen real nie vor).

### 2026-07-22 — FM-16 (b) Preview-Nachtrag: EFX-Vorschau zeigt Pro-Kopf-Punkte (FM-16 abgeschlossen)

#### Hinzugefügt / Geändert

- **Die EFX-Vorschau (`EfxPreviewWidget`) zeichnet für Mehrkopf-Mover jetzt N phasenversetzte Kopf-Punkte** (+ transluzente Wellenlinie in Fixture-Farbe + Kopf-Nummern) statt eines einzigen Punkts pro Gerät — genau die Pro-Kopf-Pan+Tilt-Welle, die `efx.write()` seit FM-16 (b) ans DMX gibt (schließt den offenen Preview-Nachtrag; **FM-16 damit komplett**). Single-Head-Geräte, Spider (`SpiderEfxPreview`) und der Platzhalter ohne Gerät bleiben unverändert.
- **Neue state-freie Positions-Quelle `EfxInstance.head_phase_points(i, n, phase, rand_progress, head_count)`** — berechnet die (pan, tilt) ALLER Köpfe eines Geräts bei einer ÜBERGEBENEN Phase (die Vorschau hat ihre eigene Phase, getrennt vom Render). `_head_pan_tilts` delegiert jetzt reine an diese Funktion → **eine einzige Positions-Quelle** für Render UND Vorschau (keine Drift). Der `write()`-DMX-Output ist bit-identisch (bestehende `test_efx_perhead_pan.py` + 329 EFX/Spider-Tests grün); adversarial verifiziert, dass Kopf 0 aus `head_phase_points` == Render-Kopf-0 aus `_values` für **alle** Kombinationen (random/mirror/counter/offset/sync).
- **Neuer kanonischer Kopfzähler `app_state.pan_tilt_head_count(fixture)`** = `max(#pan, #tilt)` — EINE Quelle für den `write()`-Gate (`head_count ≥ 2`) UND die Vorschau. `efx.write()` nutzt ihn statt der Inline-Zählung.
- Die Kopfzahl je Fixture wird in der Vorschau **pro Paint frisch** aus dem Patch aufgelöst (ein `get_patched_fixtures()`-Snapshot/Frame; `get_channels_for_patched` ist ohnehin gecacht) — **kein persistenter Cache**, damit ein Re-Patch sofort greift und kein transienter Fehlwert einfriert (adversariale Review, Fallenklasse #6b). Status-Zeile zeigt „· Kopf-Welle X%".

Tests `tests/test_efx_preview_perhead.py` (18: Kopfzähler, `head_phase_points`↔Render-Äquivalenz, Multi-Head- vs Single-Head-Paint-Pfad). Adversariale Review (5 Linsen × Skeptiker, Opus): Bit-Identität + Kopf-Mathematik bestätigt sauber; 1 MEDIUM (Fallback-Cache) vor Merge gefixt; Rest-LOWs kosmetisch/vorbestehend. _Computer-Use-Folgeschritt (interaktives Pro-Kopf-Platzieren im Editor, Live-UX-Abnahme) läuft als eigenständiges **FM-HEADLAYOUT** (P1)._

### 2026-07-21 — FM-16 (e): Kopf-Matrizen zusammenlegen + Gruppen-Editor versteht Kopf-Zellen

#### Hinzugefügt

- **Mehrere (Kopf-)Matrix-Gruppen lassen sich zu EINER größeren Matrix zusammenlegen** (David-Wunsch, schließt FM-16 funktional ab). Neuer Button „⧉ Matrizen zusammenlegen…" im Gruppen-Editor (Mehrfach-Auswahl-Dialog) → `AppState.merge_head_matrix_groups` stapelt die N Raster vertikal zu einem größeren (`_stack_group_grids`, rein/getestet; Spalten auf Max-Breite, Zeilen summiert) — z. B. **2× Hydrabeam (je 1×4 Köpfe) → eine 4×2-Matrix**. Jede Zelle behält ihr `fid:head`-Encoding, sodass die zusammengelegte Matrix im Matrix-Programmer **pro Kopf** ansprechbar bleibt (`grids_from_positions`/`head_grid`). Nicht-destruktiv (Quell-Gruppen bleiben); neue Gruppe im Ordner „Matrizen" (wird von `remove_fixture` nicht mit weggeräumt).
- **Gruppen-Editor versteht jetzt Kopf-Zellen `"fid:head"`** (`_split_cell`). Zuvor warf `_load_group` bei `int("5:0")` und die Zellen fielen **still weg** → eine auto-erzeugte Kopf-Matrix-Gruppe erschien im Editor komplett **leer**. Jetzt bleiben Kopf-Zellen erhalten, werden als „fid·K{n}" (1-basiert, leicht abgesetzt) gezeichnet, `_group_fids` liefert die Basis-fids fürs Member-Highlight. Ganze-Fixture-Zellen (int) unverändert.

Tests `tests/test_fm16e_head_matrix_merge.py` (15). _Computer-Use-Folgeschritt offen: interaktives Pro-Kopf-Platzieren (Drag einzelner Köpfe) + Live-UX-Abnahme._

### 2026-07-21 — FM-16 (b): EFX fährt bei Mehrkopf-Movern eine echte pro-Kopf-Pan+Tilt-Welle

#### Hinzugefügt / Geändert

- **Voll-Mehrkopf-Mover (MOVBAR4, Hydrabeam 4000, …) bekommen im EFX jetzt einen echten Pan+Tilt-Chase über ihre Köpfe.** Bisher fuhr nur ein Dual-Tilt-Spider eine pro-Kopf-**Tilt**-Welle; ein Voll-Mover mit `pan#k`/`tilt#k` erhielt nur Kopf-0-Pan/Tilt, alle weiteren Köpfe spiegelten Kopf 0 (`resolve_attr_channels`-Fallback) → alle 4 Köpfe bewegten sich identisch. Die tilt-only Spider-Kopf-Welle `_spider_head_tilts` wurde zu `_head_pan_tilts` verallgemeinert (Pan **und** Tilt, `(k/head_count)*head_spread` phasenversetzt); der `write()`-Gate feuert auf `pan_heads≥2` **oder** `tilt_heads≥2` und bespielt pro Kopf nur die Achse(n) mit ≥2 Kanälen. **Reine Dual-Tilt-Spider (0 Pan) bleiben exakt tilt-only** (unverändert, `test_efx_swings_bars_counter` grün). `invert_pan`/`invert_tilt`/`swap_pan_tilt` je Kopf über **dieselbe** `apply_pan_tilt_orientation` wie Kopf 0 (koppelt das 16-bit-Paar bitidentisch — Float-Invert vor `_split16` wäre um bis zu 256 daneben, per Test abgesichert); Geräte-Mirror/Counter/Fan/RANDOM/16-bit mitgetragen. **Keine neue Persistenz** (nutzt bestehendes `head_spread`), **keine Änderung der Ziel-Zuweisung** (1 `EfxFixture`/fid, Kopf-Expansion im `write()` — bewusst kein invasives N-`EfxFixture`-Split). Tests `tests/test_efx_perhead_pan.py` (12). _Nachtrag offen: `EfxPreviewWidget` zeigt weiter 1 Punkt/Gerät (die pro-Kopf-Streuung wurde nie visualisiert — analog `head_spread` bei Spidern nur in `SpiderEfxPreview`)._

### 2026-07-21 — Salvage-Runde: 3 bestätigte Fixes + Palette-Coverage aus Pre-Konsolidierungs-QA-Branches geborgen

_Beim Repo-Aufräumen (≈130→8 lokale Branches, primärer Worktree zurück auf `main`) enthielten 6 „stale" Branches echt-ungelandeten Inhalt. Gegen den aktuellen `main` verifiziert (parallele Analyse): 3 Fixes + 1 Test-Coverage sind real noch nötig und hier geborgen; die überholten Branches verworfen (Worker-Callback-Teardown ist in `main` anders + getestet gelandet, der CI-Meta-Test war brüchig)._

#### Behoben

- **Scene-Editor „Vorschau senden" läuft jetzt über den Render-Pfad statt roh ins Universe (Safety).** Der direkte `universe.set_channel()`-Write umging Grand-Master/Blackout **und** die Laser-NOT-AUS-Maske → eine Scene-Vorschau konnte einen DMX-Laser trotz NOT-AUS kurz ansteuern. Jetzt `AppState.queue_scene_preview()` = Ein-Frame-Renderschicht (nach Funktionen/Programmer, **vor** allen Mastern, one-shot + selbst-freigebend, Nicht-DMX-Fixtures via `fixture_uses_dmx` übersprungen). `scene_editor._send_preview` ruft nur noch das. Test `tests/test_scene_preview.py`.
- **Fixture-Editor verliert beim Öffnen→Bearbeiten→Speichern keine Metadaten mehr.** Modus-`description`, Kanal-`invert`, `resolution` und alle `ranges` (Gobo/Shutter-Slots) wurden still verworfen (nur die sichtbaren Tabellenfelder überlebten). Jetzt vollständig durchgereicht (inkl. `ChannelRange`-Rebuild). Test `tests/test_fixture_editor_roundtrip.py`.
- **Show-Manager-Timeline: Blöcke lassen sich über Track-Grenzen ziehen** (QA-LIVE-Offenpunkt). Vertikales Ziehen weist den Block dem Ziel-Track zu; beim Loslassen wird der Ziel-Track nach `start_time` sortiert + `recalc_duration()` gegen eine stale Gesamtlänge gerufen. Test `tests/test_show_manager_timeline_drag.py`.

#### Tests

- **Palette-UI-Roundtrip-Coverage** (`tests/test_palette_roundtrip.py`, QA-LIVE-Offenpunkt „Palettes"): Color-Palette aus Auswahl aufnehmen → Button im echten Qt-Workflow klicken → Werte einer 2. Spider-Farb-Bank überleben Save/Load.

### 2026-07-21 — „Grosse Demo Show 2026": konkurrierende PAR-Looks lösen sich ab + Farbwähler wirkt (GDS-4, GDS-5)

#### Behoben

- **GDS-4 — Effekt-Buttons stapeln nicht mehr auf denselben Geräten.** Die vier konkurrierenden PAR-Voll-Looks (Rainbow / Chase / ColorFade / Lauflicht) sind jetzt `solo_fixtures` — ein neuer Look löst den alten auf denselben PARs ab, statt gleichzeitig zu laufen. PAR Strobe (Shutter) bleibt bewusst komplementär (mit einem Farb-Look kombinierbar). Nur der Demo-Generator (`tools/build_grosse_demo_show_2026.py`); Show neu erzeugt.
- **GDS-5 — Der VC-Farbwähler „Farbe" wirkt jetzt zuverlässig.** Er zielte auf `Programmer/Selektion`; die Demo-VC bietet aber kein Auswahl-Pad → der Picker hing am (leeren) Programmer-Zustand (der Empty-Fallback färbte zwar alle, aber nur solange nichts anderes selektiert war). Jetzt `target='Alle Fixtures'` → färbt explizit + robust immer alle Geräte, unabhängig vom Programmer-Zustand.

### 2026-07-21 — „STOP ALL" ist jetzt ein echter Panik-Knopf (stoppt auch VC-Szenen/Matrizen)

#### Behoben

- **„STOP ALL" (VC-Button, Toolbar-Knopf und cmdline `stop`) stoppt jetzt AUCH FunctionManager-Funktionen — nicht mehr nur Playback-Cuestacks.** Bisher rief `STOP_ALL` nur `playback_engine.stop_all()` (Executor-Cuestacks/Chaser); **VC-getriggerte Szenen, EFX und im Programmer gestartete RGB-Matrizen** (die in `FunctionManager._running_ids` leben) liefen einfach WEITER — der Banner „Aktiver Effekt" blieb stehen und DMX floss weiter, bis man die Show neu lud. Der Panik-Knopf war also keiner (live beim Hardware-Test aufgefallen: „STOP ALL gedrückt, Licht blieb an"). **Fix:** `STOP ALL` ist jetzt das **Superset** — nach `playback_engine.stop_all()` wird zusätzlich `function_manager.stop_all()` gerufen (genau der Call, den der „Effekte stoppen (Tempo bleibt)"-Button `STOP_EFFECTS` schon nutzt), an **allen vier** Aufrufstellen (VC-Button-Primäraktion, Multi-Action-Liste, Toolbar-`_stop_all`, cmdline-`StopCommand`). Der **Programmer bleibt bewusst unberührt** (manuelle Farben/Snaps/Snapshots — das ist `CLEAR`s Aufgabe, kein überraschender Panik-Datenverlust); Blackout/Laser-NOT-AUS bleiben ebenfalls eigene Knöpfe. Regressionstests `tests/test_stop_all_stops_functions.py` (VC-Button, Multi-Action, cmdline + `STOP_EFFECTS`-Gegenprobe; verifiziert diskriminierend gegen den alten Codepfad).

### 2026-07-20 — Fixture-DB-Robustheit: QXF-Import-Kanalnummern + eindeutiger Profil-Lookup (A3D-34, A3D-35)

#### Behoben

- **A3D-34 — QXF-Import: kaputte `Number`-Attribute korrumpieren die Kanalbelegung nicht mehr.** Der Kern (ein *fehlendes* `Number` durfte nie den echten Kanal 1 verdrängen) war bereits durch den CDX-03-Zwei-Pass gelöst; geschlossen sind jetzt die zwei vom Finding genannten Rest-Kanten: ein **leeres** `Number=""` wird wie „keine Angabe" behandelt (Pass 2 legt den Kanal auf die nächste *wirklich freie* Nummer, statt ihn per `int("")`→`ValueError` still zu droppen), und eine **negative** `Number` (`int("-1")+1 == 0`, `"-2"` → `-1`) wird sichtbar verworfen, statt eine ungültige `channel_number ≤ 0` zu patchen. Betrifft hand-editierte/ältere `.qxf`-Dateien. Tests `tests/test_qxf_import_missing_number.py` (+leerer/negativer Fall).
- **A3D-35 — Show-Builder patcht bei doppeltem `short_name` nicht mehr stumm das falsche Profil.** `FixtureProfile.short_name` hat keine Unique-Constraint (Builtins und Importe — `source` `qlcplus`/`user` — können kollidieren); das frühere `.first()` **ohne `ORDER BY`** lieferte einen rowid-abhängigen Zufallstreffer → mal das falsche Profil (falsche `channel_count`/`fixture_type`/DMX-Abbildung), nicht reproduzierbar. **Fix (Entwurf via 3-Agent-Design-Debatte → „C_hybrid"):** `_lookup_profile` wählt jetzt **total-deterministisch** — `ORDER BY` builtin-vor-Import, dann kleinste `id` (PK ist unique → keine Rest-Ties, reproduzierbar unabhängig von SQLite-Storage/Insert-Reihenfolge). Bei Mehrdeutigkeit **laut** warnen (`[showbuilder] WARN` mit voller Kandidatenliste `id=…/source`, 1× pro `short_name` pro Builder — kein Rauschen über `patch()`+`profile_id()`), statt still zu picken. Für CI/strenge Autoren ein **opt-in-Strict-Modus** (`ShowBuilder(strict_profiles=True)` oder env `LIGHTOS_STRICT_PROFILES=1`), der dieselbe Meldung zu einem harten `BuildError` macht — der Raise sitzt **außerhalb** des DB-`try/except`, wird also nicht als „Fixture-DB nicht lesbar" fehl-umgewickelt. Der Default bleibt grün+reproduzierbar für alle `build_*.py`-Skripte. Tests `tests/test_a3d35_lookup_profile_dedup.py` (10, inkl. diskriminierendem Order-Unabhängigkeits-Test aus der adversarialen Review). Adversariale Review über beide Fixes: 2 von 3 Reviewern ohne Befund; ein LOW (vakuöser Order-Test) gefunden **und behoben**.

### 2026-07-20 — BPM „0/aus" überstimmt laufende Auto-Tempo-Quellen (A3D-17b)

#### Behoben

- **Wenn du im „BPM einstellen"-Dialog `0` = „aus" eingibst, springt der Wert nicht mehr sofort zurück.** Bisher nullte `reset()` nur `_bpm`, ließ aber den Modus auf AUTO → die nächste Nachricht einer laufenden Auto-Quelle (Audio-Detektor, OS2L/VirtualDJ, Timeline, File, TempoBus) setzte `_bpm` sofort wieder. **Entscheidung (David):** „0/aus" soll alle Live-Quellen überstimmen und in MANUAL wechseln. **Fix:** neue `BPMManager.turn_off()` (nur der Dialog ruft sie) flippt in MANUAL — das blockt `request_bpm` und `_apply_detected_bpm` — schaltet den Audio-Sync mit ab und bleibt aus bis zur nächsten expliziten Aktion (symmetrisch zu `set_manual_bpm(>0)`, das ebenfalls MANUAL setzt). `reset()` bleibt bewusst der Low-Level-Clean-Slate, der den Modus lässt (Test-Setup). Der „Drive-BPM"-Haken im Audio-Input-View zieht den Zustand jetzt nach (UI-Thread-sicher im 30-Hz-Refresh). `turn_off()` setzt MANUAL **zuerst** (unter Lock, aus der adversarialen Review), damit eine bereits im Audio-Thread laufende, verspätete Beat-Invocation `_bpm` nicht doch noch setzt und keinen Phantom-Timer startet. Regressionstests `tests/test_a3d17b_bpm_turn_off.py` (inkl. injiziertem in-flight-Beat).

### 2026-07-20 — `load_show` ist reset-first: kein halb-alter (Frankenstein) Zustand bei Ladefehler (STAB-19b)

#### Behoben

- **Bricht das Laden einer Show an einer der wenigen ungefangenen Zeilen ab, bleibt kein inkonsistenter „Frankenstein"-Zustand (neuer Patch + Rest der alten Show) zurück.** Bisher ersetzte `load_show` den Patch zuerst und setzte die übrigen State-Felder erst *inline* pro Block zurück — ein Absturz mittendrin ließ die noch nicht geladenen Blöcke auf ALTEN Werten stehen. **Fix (Entwurf via 3-Agent-Design-Debatte → Option A+C):** `load_show` ist jetzt **reset-first** — es setzt über die neue, mit `reset_show` geteilte Funktion `_reset_state(state, emit_events=False)` den **gesamten** State auf leer, **bevor** ein Block geladen wird. Stürzt danach etwas ab, sind die noch nicht geladenen Blöcke LEER statt ALT. Ergänzend sind die zwei realen ungefangenen Zeilen (`_replace_patch_from_data`, `clear_feature_dimmers`) in `_lenient` gekapselt.
  - **`_reset_state` als SSOT:** `reset_show()` ruft es mit `emit_events=True` (verhaltensgleich zu vorher, inkl. der Listener-Benachrichtigung). Beim reset-first (`emit_events=False`) bleibt der komplette Tail-Emit-Block aus — **wichtig für `state.sync.refresh_all()`, das als direkter Bus-Call `_suppress_emits` umgeht** und sonst ein Doppel-Refresh (leer→voll) samt re-entrantem Rebuild (BUG-01) mitten im Laden ausgelöst hätte.
  - Snapshot+Rollback (Alternative) wurde verworfen: der Patch ist seit STAB-CURSHOW bereits atomar in `current_show.db` committet, ein In-Memory-Rollback könnte ihn nicht zurücknehmen.
  - **Kein neuer Nebeneffekt beim normalen Laden** (aus der adversarialen Review): das reset-first blankt **nicht** die laufende DMX-Ausgabe (neuer Parameter `blackout_output=False` — nur `reset_show`/„Neue Show" blendet hart, sonst gäbe es bei jedem Laden einen physischen Blackout-Puls) und feuert **keine** Media-Player-Qt-Signale mitten im Laden (`blockSignals`, da diese `_suppress_emits` umgehen); die bare Zeilen in `_reset_state` (`clear_feature_dimmers`, Scene-Replace) sind gekapselt, damit ein Fehler dort den Reset nicht abbricht.
- Regressionstests in `tests/test_stab19b_load_atomic.py`: „Crash im Block N → kein Feld der vorigen Show überlebt" (STRICT-Modus + injizierter Crash vor dem cue_stacks-Block), Mirror-Guard (`_reset_state` leert die geladenen Felder) und Normal-Load-Regression.

### 2026-07-20 — EURON10-Fog: Lüfter folgt nach dem fan-Split wieder alten Shows (CDX-18)

#### Behoben

- **Der Lüfter einer Eurolite N-10 Nebelmaschine (EURON10, 2-Kanal-Modus) bleibt nicht mehr aus, wenn eine vor dem `fan`-Split (CDX-07) gespeicherte Show geladen wird.** Vor dem Split waren beide Kanäle `dimmer`; der Programmer deduplizierte sie zu einem Regler, sodass der Lüfter den Nebelwert still spiegelte. Nach dem Split (Kanal 2 = `fan`) enthielten die davor aufgezeichneten, attr-gekeyten Playback-Daten nur `dimmer` → `fan` blieb auf Default 0 (Lüfter aus). **Fix (Entwurf via 3-Agent-Design-Debatte):** `load_show` zieht `fan=dimmer` **einmalig** nach — pro Playback-Container **inline direkt am jeweiligen Ladepunkt** (kritisch: Programmer VOR `_flush_all_to_dmx`, base_levels VOR `_rebuild_render_plan`, sonst zeigte der Lüfter unmittelbar nach dem Laden weiter 0). Abgedeckt sind alle 7 attr-gekeyten Container: Programmer, base_levels, `Palette.fixture_values` (nie die generischen `values`), Cue-Werte, Sequence-Schritte (str-fid), Snaps und die rohen Snapshot-Dicts. **Streng gegatet** auf das Builtin-EURON10 (`short_name=='EURON10'` + `source=='builtin'` + `channel_count==2` + Kanalform `[dimmer,fan]`) — ein Custom-Fixture mit echtem, unabhängigem Lüfter-Kanal wird nie getroffen. **Nie überschreibend:** ein bereits gesetztes `fan` (auch 0) gilt als bewusst editiert. Self-healing (der nächste Save persistiert die reparierten Werte), kein `SHOW_VERSION`-Bump. Scene/Chaser/EFX/Executor sind kanal-/referenzbasiert bzw. live-berechnet und daher immun. Regressionstests in `tests/test_cdx18_euron10_fan_migration.py` (alle 7 Container + DMX-Timing-Beweis + Kontrollen fan-schon-gesetzt/Nicht-EURON10 + Idempotenz).

### 2026-07-20 — Patch-Loader gegen geteilte `current_show.db` gehärtet (STAB-CURSHOW b)

#### Behoben

- **Eine saubere 32-Fixture-Show lädt nicht mehr nichtdeterministisch 22–35 Fixtures, wenn mehrere Prozesse dieselbe `data/current_show.db` teilen** (Davids zwei laufende App-Instanzen + parallele Build-/Test-Läufe). Ursache war ein **nicht-atomarer** Patch-Replace: `_replace_patch_from_data` committete das `clear_patch()`-DELETE separat und danach jedes `add_fixture()` einzeln (N+1 Commits). Ein Parallelprozess sah den leeren/halben Zwischenzustand oder INSERTete hinein; der FLD-FID-Guard wich auf `next_fid()` aus → Adress-Überlapp-Zeilen (zwei distinkte fids auf derselben `universe:address`). **Fix (aus einer adversarialen 3-Wege-Design-Debatte, einstimmig):**
  - **Atomarer Voll-Replace:** neue `AppState.replace_patch(fixtures)` ersetzt den gesamten Patch in **einer** Transaktion — **Core**-`delete(PatchedFixture)` + `add_all` + **genau ein** Commit + **genau ein** `_reload_patch_cache`. Kein persistierter Zwischenzustand mehr; Absturz vor dem Commit → Rollback → alter Patch intakt. `_replace_patch_from_data` ruft dies (mit Fallback auf den alten Pfad für ältere APIs/Test-Fakes). fid-Kollisionen in der Show-Datei werden **reassigned** (nie verworfen).
  - **Concurrency-PRAGMAs:** `busy_timeout=5000` pro Show-DB-Connection (`_set_sqlite_pragmas` als `connect`-Listener in `open_show`) verwandelt sofortiges `SQLITE_BUSY` in kurzes Warten → zwei echte App-Prozesse serialisieren ihre Loads. `journal_mode=WAL` best-effort, aber nur auf lokalem Fixed-Laufwerk (`_is_local_writable_path` sperrt UNC/Netz- und Cloud-Sync-Ordner wie OneDrive/Dropbox, wo WAL-Sidecars korrumpieren); alles `try/except`, bricht `open_show` nie.
- **Adress-Konflikte werden präziser gemeldet** (`validate_and_repair` Check 5): beide kollidierenden fids + volle Adressbereiche + Universe. **Bewusst weiterhin report-only** — kein Auto-Löschen überlappender Fixtures (`fid` ist UNIQUE, ein Überlapp ist am Startzeitpunkt nicht von einem legitimen Nutzer-Stapel unterscheidbar → Auto-Delete wäre stiller Datenverlust). Der atomare Replace heilt verwaiste Zeilen ohnehin beim nächsten sauberen Load.

#### Tests

- `tests/test_stab_curshow_loader_hardening.py` — T1 Zwei-Writer-Contention (eigene Engine je Thread auf dieselbe FILE-DB, Barrier, K Iterationen → exakt 32, null Überlappung), T2 Atomizität (genau 1 Commit), T3 Überlapp-Überleben/kein stiller Verlust, T4 Einzelprozess-Regression + `replace_patch` legt keine Gruppen an, T5 `busy_timeout`-Serialisierung, + WAL-Guard-Unit-Tests.

### 2026-07-19 — Blackout/Grand Master hellt CMY-Mover nicht mehr auf (A3D-37)

#### Behoben

- **Ein Moving Head mit reiner CMY-Farbmischung (ohne eigenen Dimmer) wird beim Blackout / bei sinkendem Grand Master nicht mehr *heller* statt dunkler.** Fixtures ohne echten Dimmer-Kanal nutzen ihre Farbkanäle als virtuellen Dimmer — der Dimmer-Master/GM/Blackout skaliert diese Adressen multiplikativ Richtung 0. Bei **additivem** RGB(W) ist das korrekt (0 = dunkel), bei **subtraktivem CMY** aber invertiert: CMY Richtung 0 = Farbe *öffnen* = heller/weiß. Ein CMY-only-Mover fuhr beim Blackout also auf **Weiß** statt aus. **Fix:** `_fixture_intensity_addrs` nimmt die subtraktiven CMY-Kanäle (`cmy_c/m/y`, `cyan/magenta/yellow`) vom Intensitäts-/Dimm-Fallback aus (neue `_SUBTRACTIVE_COLOR_ATTRS`) — ein CMY-only-Fixture trägt damit nichts zur GM-/Blackout-Dimmmaske bei und wird nicht mehr invertiert. CMY bleibt in `_DIM_COLOR_ATTRS` (die Farb-Feature-Dimmung / GM-Farbmaske braucht CMY weiterhin als Farbe); additives RGB(W) bleibt unverändert virtueller Dimmer. Regressionstests in `tests/test_grandmaster_mask_universe.py` (CMY-only → leere Dimmmaske; RGB-only → weiter gedimmt).

### 2026-07-19 — VC-Slider: bewusst gelöster Playback-Slot bleibt nach dem Laden gelöst (A3D-39)

#### Behoben

- **Ein Playback-Slider, dessen Executor-Slot bewusst geleert wurde, bekommt beim erneuten Laden nicht mehr einen veralteten Slot untergeschoben.** `apply_dict` migrierte Alt-Shows (die den Slot früher in `function_id` ablegten), indem es bei `playback_slot is None` auf `function_id` zurückfiel. `d.get("playback_slot")` liefert aber `None` **sowohl** bei fehlendem Key (echte Alt-Show) **als auch** bei explizitem `null` — und `to_dict` schreibt den Key **immer** mit. Ein in einer **neuen** Show bewusst geleerter Slot (`playback_slot: null`) wurde so fälschlich aus der (oft veralteten) `function_id` zurückmigriert → der gelöschte Executor tauchte wieder auf. **Fix:** die Legacy-Migration greift jetzt nur noch, wenn der Key **ganz fehlt** (`"playback_slot" not in d`); ein explizites `null` bleibt `None`. Regressionstests in `tests/test_vc_slider_playback_slot.py` (explizites null wird nicht migriert; fehlender Key migriert weiter).
### 2026-07-19 — Werkzeug-Audit-Runde: DB-Isolation, Archiv, neue Loop-Werkzeuge

#### Hinzugefügt

- **`tools/backlog_compact.py`** — Backlog-Verdichter + Queue-View: `--queue N` listet die nächsten offenen Items kompakt (BACKLOG.md ist mit ~290 KB nicht mehr am Stück ladbar), `--stats` zählt Status/Prio, `--archive [--apply]` verdichtet reine done-Tabellenzeilen nach `BACKLOG_ARCHIVE.md` (Kurzzeile mit ID+PR-Link bleibt, QA-18-lint-konform). Tests: `tests/test_backlog_compact.py`.
- **`tools/janitor.py`** — Worktree-/Branch-/Artefakt-Hygiene, report-first: erkennt verwaiste `wt-*`-Ordner, vollständig gemergte inaktive Branches und alte `artifacts_*.png`-/Log-Leichen; aufgeräumt wird nur mit `--apply` (Artefakte wandern nach `_trash/`, nie hartes Löschen; pytest-Lock-Halter, dirty Trees, `main` und der eigene Worktree sind tabu). Tests: `tests/test_janitor.py`.
- **`tools/_showpath.py`** — `find_show(name)` löst Show-Dateien mit Fallback `shows/` → `shows/_archiv/` auf (viele historische Shows sind seit 2026-07-19 archiviert) und bricht sonst mit klarer Meldung ab.
- **`tools/gen_tools_index.py` + `tools/README.md`** — generierter Werkzeug-Index (erste Docstring-/Synopsis-Zeile je Skript); Frische-Gate `tests/test_tools_index.py`.
- **Lint-Gate `tests/test_tools_db_isolation.py`** (STAB-CURSHOW a): jedes tools/-Skript, das State-/Show-DB-APIs referenziert, muss `import _gen_env` nutzen oder `LIGHTOS_SHOW_DB` setzen (Whitelist nur mit Begründung).

#### Geändert

- **`tools/_gen_env.py` setzt jetzt zusätzlich eine isolierte Wegwerf-`LIGHTOS_SHOW_DB`** (`<tmp>/lightos_gen_<skript>_<pid>.db`, `setdefault`): alle `_gen_env`-basierten Generatoren/Captures arbeiten nie mehr auf Davids geteilter `data/current_show.db` (STAB-CURSHOW (a); Muster aus `build_mega_arena_2026.py` verallgemeinert). `build_demo_show.py`/`build_full_show.py` (bauen bewusst auf dem Bestands-Patch auf) brechen auf leerer Wegwerf-DB jetzt mit klarer Anleitung ab statt mit IndexError.
- **11 überholte Einmal-Skripte nach `tools/_archiv/` verschoben** (Begründungen in `tools/_archiv/README.md`): `verify_matrix_group_scope`, `_shot_matrix_group_scope(_live)`, `verify_efx_group_scope`, `verify_komplett_demo`, `patch_stage_show_pages`+`build_stage_show`, `build_hardstyle_vc`, `build_snaps_show`, `diag_hardstyle`, `diag_movers` — Prüflogik lebt in pytest-Tests weiter bzw. Ziel-Shows sind archiviert.
- Capture-/Render-Skripte (`capture_hochzeit_tempo_guide`, `capture_test123_tempo_guide`, `render_apc_pages`, `render_neue_demo_pages`) nutzen `find_show` (Archiv-Fallback) und `_gen_env`-Isolation; `benchmark_universes.py` und `check_demo_show_full.py` laufen ebenfalls DB-isoliert.

#### Behoben

- **`tools/build_full_show.py` überschreibt nicht mehr die Crash-Recovery-Autosave** `%APPDATA%/LightOS/auto_save.lshow` (löste beim nächsten App-Start einen irreführenden Recovery-Dialog aus und zerstörte die echte Autosave).
- `tools/vc_click_targets.py`: Usage-Zeile statt nacktem IndexError ohne Argument; `tools/gallery_server.py`-Docstring (kein `?type=`-Filter), `verify_color_dimmer_separation.py`-Zeilenverweise (`live_view.py:1069`), `start.ps1`/`install.py`/`INSTALL.md` ARM64-Hinweis auf Python **3.14** aktualisiert.

### 2026-07-19 — Test-Gate auch auf Linux/macOS lauffähig (XPLAT-02)

#### Geändert

- **Der Loop-Test-Gate lässt sich jetzt auch auf einem Linux-/macOS-Checkout ausführen.** Bisher suchte `tools/verify_loop.ps1` ausschließlich `venv\Scripts\python.exe` (Windows) → auf Linux (`venv/bin/python`) Exit 2, bevor ein Test lief; zudem delegiert es an den PowerShell-only-Lock-Runner `../run_tests.ps1` (liegt ausserhalb des Repos, fehlt einem frischen Checkout). **Fix:** (a) die Interpreter-Suche in `verify_loop.ps1` prüft jetzt eine Kandidatenliste — **Windows-Pfade zuerst (erster Treffer gewinnt → auf Windows byte-identisch)**, danach `venv/bin/python(3)`; (b) neuer eingecheckter, plattformneutraler Runner `tools/verify_loop.sh` (Syntax-Check `compileall src` + direktes `pytest`, `QT_QPA_PLATFORM=offscreen`) für Linux/macOS, wo Davids Multi-Session-Parallelität (und damit der serialisierende Lock-Runner) nicht existiert; (c) Linux-Weg in `WORKFLOW.md` dokumentiert. Windows/WinARM-Verhalten unverändert.

### 2026-07-19 — Wählbare Ausgangs-NIC für DMX/Laser-Broadcast (XPLAT-06)

#### Neu

- **Die Ausgangs-Netzwerkkarte für Art-Net-Broadcast, sACN-Multicast und IDN-Laser-Discovery ist jetzt wählbar** (`LIGHTOS_OUTPUT_IFACE=<iface-IP>`). Bisher gingen `ArtNetSender` (`255.255.255.255`), `SACNSender`-Multicast und `idn.discover()` über die OS-Default-Route. Windows sendet Limited-Broadcast historisch auf ALLEN Interfaces, **Linux nur über die Route-NIC** → auf einem Rig, dessen Lichtnetz an einer 2./USB-Ethernet-NIC (≠ Default-Route) hängt, erreichte die Ausgabe unter Linux die Nodes evtl. nicht. **Fix:** neuer Helfer `src/core/dmx/output_iface.py` bindet die Sende-Sockets an die gewählte NIC (Art-Net/IDN: Quell-Bind; sACN-Multicast: zusätzlich `IP_MULTICAST_IF`). **Opt-in — ohne `LIGHTOS_OUTPUT_IFACE` bleibt alles beim bisherigen OS-Routing (Windows/WinARM unverändert)**; eine falsche/verschwundene IP wird geschluckt (Fallback aufs Routing). Neue Tests `tests/test_output_iface.py`.

### 2026-07-19 — Zentraler, XDG-konformer App-Datenordner (XPLAT-04)

#### Geändert

- **Der App-Datenordner wird jetzt zentral über `src/core/paths.py:app_data_dir()` aufgelöst** statt an ~19 Fundstellen einzeln. Vorher hatte jede Stelle `os.path.join(os.environ.get("APPDATA", expanduser("~")), "LightOS", …)` — auf Linux/macOS ist `APPDATA` nicht gesetzt, also landeten **alle** Nutzerdaten (Show-DB, Snaps, Stages, `vc_assets`, BPM-Cache, Prefs, Crash-Log …) im sichtbaren, nicht-XDG-konformen `~/LightOS/`. Neu: `app_data_dir()` mit `sys.platform`-Weiche — **Windows unverändert `%APPDATA%/LightOS` (byte-identisch, kein Datenumzug)**, Linux `$XDG_DATA_HOME/LightOS` bzw. `~/.local/share/LightOS`, macOS `~/Library/Application Support/LightOS`. Alle Fundstellen (`bpm_cache`, `bpm_settings`, `controller_library`, `fixture_db`, `snap_library`, `input/profile`, `vc_assets`, `stage_definition`, `web/remote_settings`, `main_window`, `live_view`, `programmer_view`, `snap_file_panel`, `snapshots_view`, `vc_button`, `visualizer_window`, `collapsible_section`) darauf umgestellt. Neue Tests `tests/test_app_data_dir.py`. **Keine Migration** bestehender Linux-Daten (Linux-Support ist frisch, keine Alt-Daten); auf Windows/WinARM bleibt alles am selben Ort. Die Fixture-Definitions-DB folgt ebenfalls `app_data_dir()`, akzeptiert aber neu einen `LIGHTOS_FIXTURE_DB`-Override (analog `LIGHTOS_SHOW_DB`) — die Test-Suite pinnt darüber die reale, geseedete `fixtures.db`, obwohl sie `APPDATA` sonst isoliert.
### 2026-07-19 — Web-/OSC-Remote: GO/BACK/STOP crasht nicht mehr beim Laden während der Bedienung (A3D-40)

#### Behoben

- **Ein GO/BACK/STOP vom Web- oder OSC-Remote fällt nicht mehr aus, wenn zeitgleich eine Show geladen wird.** Die Handler prüften `if cue_stacks: cue_stacks[0].go()` — aber die lokale Variable hielt nur eine **Referenz auf dieselbe Live-Liste**, die der Show-Loader beim Laden per `cue_stacks.clear()` **in-place leert**. Traf ein Remote-Kommando genau zwischen `if` und Index-Zugriff auf ein solches Leeren, warf `cue_stacks[0]` einen `IndexError` — im Web-Remote ein **HTTP 500** (Kommando verloren, Fehler beim Bediener), in den OSC-Handlern ein still verschlucktes Kommando. Der Kommentar „WEB-04: TOCTOU-sicher (lokale Ref)" war also irreführend. **Fix:** alle sechs Web-Endpunkte (`/api/go` `/back` `/stop` + die Socket.IO-Pendants) und die beiden OSC-Handler ziehen jetzt einen **echten Snapshot** `list(cue_stacks)` (identisches Muster wie `/api/status` schon nutzte) — der Index trifft die kopierte Liste, nie die vom Loader geleerte Live-Liste. Neue Regressionstests in `tests/test_web_app.py` (nebenläufiges `clear()` zwischen Prüfung und Index → kein Crash, Kommando landet auf dem Snapshot).

### 2026-07-19 — DMX: neu-gepatchtes Fixture blitzt nicht mehr 1 Frame schwarz (CDX-17)

#### Behoben

- **Wird ein Fixture entfernt und dieselbe DMX-Adresse sofort wieder gepatcht (Bulk-Show-Load, schnelles Undo/Redo), blitzt das neue Fixture nicht mehr für einen Frame auf 0.** Beim Entfernen merkt LightOS die verlassene Adresse in `_pending_release` vor, damit ein nachlaufender Alt-Plan-Commit sie nicht wiederbelebt; der nächste Render-Frame nullt sie dann final. Wurde die Adresse aber **vor** diesem Frame wieder gepatcht, stand sie noch aus dem früheren Rebuild in `_pending_release` und wurde bedingungslos auf 0 gezwungen — das gerade neu-gepatchte Fixture wurde für genau diesen einen Frame dunkel getastet (bei Dimmer/Beam sichtbares Aufblitzen). **Fix:** die finale Nullung schreibt jetzt nur noch auf Adressen, die aktuell **nicht** gepatcht sind (`a not in patched_set[univ]`); der `pop`-Konsum bleibt unbedingt (weiter race-fest gegen Alt-Plan-Commits), genuin entpatchte Adressen werden weiterhin deterministisch freigegeben. Regressionstest in `tests/test_zombie_channel_release.py` (re-gepatchte Adresse behält ihren Wert, genuin entpatchte wird 0). Ergänzt A3D-18.

### 2026-07-19 — BPM: Beat-Timer läuft nicht mehr bei Anzeige „aus" (CDX-14b)

#### Behoben

- **Ein „aus"-angezeigtes Tempo lässt keinen versteckten Beat-Takt mehr laufen.** Nach CDX-14 setzte `set_bpm()` Quelle und Wert atomar, aber drei Aufrufer gaben aus dem Off-Zustand einen positiven Wert **ohne** Quelle weiter — `set_bpm()` leitet „aus" nur aus `BPM<=0` ab, nie umgekehrt, sodass `BPM>0` bei Quelle „aus" zurückblieb und der Beat-Timer lief, obwohl die UI „aus" zeigte (Chaser/Effekte triggerten gegen einen unsichtbaren Takt). Betroffen: der audio-getriggerte Chaser-Default (120 BPM), der OS2L-Fallback-Pfad und das Auftauen aus dem Tempo-Freeze (F3). **Fix:** alle drei geben die Quelle jetzt explizit mit (`set_bpm(bpm, source=…)`) — Chaser-Default → „manual", OS2L → „os2l"; der Tempo-Freeze **sichert die Quelle beim Einfrieren mit und restauriert sie treu** beim Auftauen. Bewusst **ohne** Umleitung über `request_bpm`/`set_manual_bpm` (deren Präzedenz-Guards MANUAL/Lock/Audio würden das Verhalten der Aufrufer ändern). Deterministische Regressionstests `tests/test_bpm_cdx14b_source_invariant.py` (Invariante je Aufrufer + Freeze/Unfreeze-Roundtrip erhält die Quelle). Schließt die von CDX-14 offen dokumentierte Rest-Lücke.
### 2026-07-19 — Linux-Installations-/Laufzeit-Doku (XPLAT-07)

#### Dokumentation

- **`INSTALL.md` hat jetzt einen Linux-Abschnitt (x86_64, sekundäre Plattform).** Dokumentiert die auf Linux nötigen Systempakete und Laufzeit-Voraussetzungen, die vorher fehlten: `build-essential` + `libasound2-dev` für `python-rtmidi` (C-Extension — **ohne die gibt es auf Linux gar kein MIDI**, der WinMM-Fallback ist Windows-only), `libpulse0` + eine PulseAudio/PipeWire-**Monitor-Quelle** für Loopback-BPM (WASAPI-Semantik → auf Linux sonst stumm), `fonts-noto`/`fonts-dejavu` für saubere UI-Fonts. Dazu der manuelle venv-Installationsweg, eine Plattform-Hinweis-Tabelle mit den bereits im Code umgesetzten Linux-Anpassungen (QtWebEngine-Sandbox XPLAT-01, Art-Net-`SO_REUSEPORT` XPLAT-03, Font-Fallbacks XPLAT-05, `~/LightOS`-Datenordner) und Linux-Zeilen in der Troubleshooting-Tabelle. Reine Doku, kein Code/Verhalten geändert.

### 2026-07-19 — Referenz-Demoshow „animierte Buttons": erreichbare Buttons + sichtbarer Strobe (CDX-19/20)

#### Behoben

- **CDX-19 — „Nebel an"/„BLACKOUT" (und „PAR Strobe") lagen außerhalb der erreichbaren VC-Canvas.** Der Generator `tools/build_komplette_animierte_show.py` platzierte diese Buttons bei x=1070/1220/1370, die `VCCanvas` ist aber nur 1200 px breit (Scroll-Area nicht resizable) → die Buttons waren im normalen VC-View nicht anklickbar. Jetzt in die zweite/dritte Reihe umgebrochen (alle Widgets enden bei x ≤ 1180); Reihe 1 endet sauber bei x=1060.
- **CDX-20 — „PAR Strobe" blitzte physisch schwarz.** Der Strobe-Chaser alternierte nur den Dimmer 255↔0, die RGBW-Farbkanäle der ZQ01424-PARs starten bei 0 → der PAR blieb dunkel, obwohl der Dimmer blitzte. Der An-Schritt setzt jetzt zusätzlich Weiß (`color_w`=255) → sichtbarer weißer Strobe (der Aus-Schritt bleibt über Dimmer=0 dunkel). Show mit `build_and_verify` neu erzeugt + validiert (16 Widgets, 0 Off-Canvas).

#### Behoben

- **Hart gesetzte Windows-Fontfamilien haben auf Linux jetzt definierte Fallbacks.** Dutzende Widgets setzen `QFont("Segoe UI")` (76×), `"Arial"` (8×), `"Consolas"`/`"Courier New"` (je 3×). Auf Linux existieren diese Familien nicht → Qt substituierte still eine beliebige Default-Familie, wodurch die fein austarierten kleinen Punktgrößen (6–17 px) breiter werden und enge Labels/Ziffern (BPM, Slider) clippen konnten. **Fix:** ein zentraler `QFont.insertSubstitutions`-Eintrag pro Familie beim App-Start (`_install_font_substitutions` in `main.py`, direkt nach der `QApplication`) mappt sie auf verbreitete Linux-Äquivalente (`Segoe UI`/`Arial` → Noto Sans/DejaVu Sans/sans-serif; `Consolas`/`Courier New` → DejaVu Sans Mono/Liberation Mono/monospace) — die 90 `QFont(...)`-Aufrufstellen bleiben unangetastet. **Windows/macOS unberührt:** dort werden die Originale zuerst gefunden, die Substitution ist registriert, greift aber nie. Neue Tests `tests/test_font_substitutions.py`.

### 2026-07-19 — Art-Net-Input teilt den Port auf Linux (SO_REUSEPORT, XPLAT-03)

#### Behoben

- **Der Art-Net-Input bindet auf Linux nicht mehr fehl, wenn schon eine andere Art-Net-App auf Port 6454 lauscht.** `artnet_input.py` setzte nur `SO_REUSEADDR` — das teilt den UDP-Port auf Linux (anders als auf Windows) NICHT. Lief parallel eine zweite Art-Net-Anwendung (QLC+ o. Ä.), warf `bind()` „Address already in use", der `except`-Block schluckte es, und der Art-Net-Input blieb still. **Fix:** wie beim sACN-Input wird jetzt zusätzlich `SO_REUSEPORT` gesetzt (guarded — auf Windows/altem Kernel fällt es per `AttributeError`/`OSError` sauber durch, `bind()` läuft trotzdem). Windows unberührt. Neue Tests `tests/test_artnet_reuseport.py`.

### 2026-07-19 — 3D-Visualizer startet auf Linux (QtWebEngine-Sandbox-Fallback, XPLAT-01)

#### Behoben

- **Der 3D-Visualizer bleibt auf Linux nicht mehr schwarz.** `_setup_webengine_diagnostics()` (`main.py`) setzte nur Anti-Drossel-Flags, aber keine Chromium-Sandbox-Flags. Auf verbreiteten Linux-Setups (pip-PySide6-Wheels ohne setuid `chrome-sandbox`, Container/Docker, root) startet der Chromium-Renderprozess von QtWebEngine dann nicht → die eingebettete `QWebEngineView` bleibt schwarz (`renderProcessTerminated`, der Auto-Reload-Guard loopt nur). **Fix:** auf Linux werden jetzt `--no-sandbox --disable-gpu-sandbox` an die WebEngine-Flags angehängt (neue reine Helfer-Funktion `_webengine_sandbox_flags`). **Abwahl für korrekt aufgesetzte Distros** (setuid `chrome-sandbox` vorhanden): `LIGHTOS_WEBENGINE_NO_SANDBOX` auf einen falsy-Wert (`0`/`false`/`no`/`off`) setzen, oder selbst ein `sandbox`-Flag über `LIGHTOS_WEBENGINE_FLAGS` setzen (eigene Wahl hat Vorrang). **Windows/macOS bleiben komplett unberührt** (hinter `sys.platform`-Weiche — WinARM-Regression: keine). Neue Tests `tests/test_webengine_linux_sandbox.py`.

### 2026-07-18 — BPM-Manager: Quelle & Wert werden atomar gesetzt (CDX-14)

#### Behoben

- **Ein `reset()` kann zwischen einer BPM-Quelle und ihrem Wert-Schreiben keinen inkonsistenten Zustand `BPM>0` bei Quelle=„aus" mehr hinterlassen.** Die drei quellen­tragenden Aufrufer (manueller Tap/Nudge/Fader, OS2L-/Datei-Anfrage und der Audio-Detektor) setzten die Quelle (`_source`) und den Wert (`_bpm`) in ZWEI getrennten Lock-Fenstern: erst die Quelle, dann — über `set_bpm()` — den Wert. Ein `reset()` genau dazwischen (nullt beide unter dem Lock) wurde vom nachfolgenden Wert-Schreiben überholt, sodass ein positiver BPM-Wert mit Quelle „aus" zurückblieb (z. B. ein weiterlaufender Beat-Timer trotz angezeigtem „aus"). `set_bpm()` nimmt jetzt eine optionale Quelle und schreibt Quelle **und** Wert unter EINEM Lock-Hold; die drei internen Aufrufer (`_set_manual`, `request_bpm`, `_apply_detected_bpm` — inkl. des häufigsten Gegenspielers, des Audio-Pfads) reichen die Quelle atomar durch. Externe Low-Level-Aufrufer (`chaser`, `tempo_bus`-Unfreeze, OS2L-Fallback), die `set_bpm(bpm)` **ohne** Quelle nutzen, verhalten sich **exakt wie bisher** — dass diese aus dem Off-Zustand heraus die Quelle nicht mitziehen, ist unverändertes Alt-Verhalten und als eigenes Follow-up **CDX-14b** notiert (kein Regressions-Effekt dieses PRs). Deterministischer Regressionstest `tests/test_bpm_manager_source_race.py` (injiziert ein `reset()` in das alte Fenster und prüft die Invariante für die quellen­tragenden Aufrufer). Ergänzt A3D-17, das die andere Hälfte (reset() vs. set_bpm) schloss.
### 2026-07-18 — Playback: Cue-Umnummerieren desynct keine laufende Cueliste mehr (ENG-13)

#### Behoben

- **Das Ändern einer Cue-Nummer im Playback-Editor bringt eine *laufende* Cueliste nicht mehr aus dem Tritt.** `playback_view._on_cue_edited` setzte `cue.number` und rief `stack.cues.sort(...)` **direkt von außen** auf — das umging `CueStack._reindex_after_mutation` (die einzige Stelle, die `_current_idx`/`_manual_target` einer laufenden Liste identitätstreu nachführt) **und lief ohne `_lock`** gegen den Engine-Tick-Thread. Wer während des Abspielens eine Cue-Nummer editierte, dessen `_current_idx` zeigte nach dem Re-Sort auf die falsche Cue (Replay/Skip der nächsten Cue). **Fix:** neue `CueStack.renumber_cue(cue, new_number)`-API mutiert die Nummer, sortiert und reindiziert **unter `_lock`** (identisches Muster wie `add_cue`/`remove_cue`); der View ruft nur noch diese API. Neue Tests in `tests/test_cue_stack_live_mutation.py` (aktive Cue bleibt identitätstreu aktiv; Index folgt beim Umsortieren; armiertes Manual-Crossfade-Ziel wird nachgeführt).

### 2026-07-18 — DMX-Ausgabe: Art-Net-Startuniversum ist jetzt einstellbar (A3D-15)

#### Behoben

- **Das „Art-Net Startuniversum"-Feld im Ausgabe-Dialog wirkt jetzt tatsächlich** — bisher war es komplett tot: man konnte die externe Art-Net-Universe-Nummer nicht einstellen, LightOS sendete immer hart auf „internes Universum − 1". Jetzt reicht „Übernehmen" den eingestellten Wert an den Sender durch und speichert ihn (überlebt einen Neustart). Das Feld folgt standardmäßig dem internen Universum (− 1), sodass bestehende Setups sich **exakt wie bisher** verhalten, solange man nichts ändert — und eine gespeicherte Wahl wird beim Wiederöffnen angezeigt. Regressionstest `tests/test_a3d15_artnet_start_universe.py`.

### 2026-07-18 — VC-Asset-Cache gegen Poisoning gehärtet (CDX-15)

#### Behoben

- **Eine manipulierte/korrupte `.lshow` kann den globalen VC-Asset-Cache nicht mehr vergiften.** `vc_assets.store_extracted` legte beim Laden die aus dem ZIP entpackten Bytes unter dem im **ZIP-Eintragsnamen** genannten Content-Hash-Key ab, **ohne zu prüfen, ob die Bytes wirklich diesen Hash haben** — und `_write_atomic` überschreibt eine bestehende Datei nicht. Eine Show mit `assets/vc/<sha1-eines-guten-Bildes>.png` = **anderer Inhalt** konnte so den legitimen Key im geteilten Cache (`%APPDATA%/LightOS/vc_assets/`) **dauerhaft mit Fremdinhalt belegen**; spätere echte Shows mit demselben Key hätten das falsche Bild gerendert und beim Speichern wieder eingebettet. **Fix:** `store_extracted` verwirft Bytes, deren `sha1` nicht zum Key-Präfix passt (neue reine Prüf-Funktion `content_matches_key`) — nur zum Key passender Inhalt wird je abgelegt. Der sichere Import-Pfad `store_bytes` (bildet den Key selbst aus den Bytes) war nie betroffen. Neue Tests `tests/test_vc_asset_poison.py`.

### 2026-07-18 — VC-Asset-Cache wächst nicht mehr unbegrenzt (VC-IMG-GC)

#### Behoben

- **Der lokale Cache für VC-Button-Hintergrundbilder/GIFs (`%APPDATA%/LightOS/vc_assets/`) wird jetzt gedeckelt.** Bisher entpackte `load_show` die eingebetteten Assets jeder geladenen Show dorthin, räumte aber nie etwas lokal weg — über viele Shows (oder eine bösartig große `.lshow`) wuchs der Ordner unbegrenzt (reine Disk-Hygiene, kein Absturz/Traversal). Neu räumt `vc_assets.prune` verwaiste Assets per LRU (ältestes Änderungsdatum zuerst) weg, sobald der Cache den weichen Deckel (Default 256 MB, per `LIGHTOS_VC_ASSET_CACHE_MB` einstellbar) überschreitet — aufgerufen aus `load_show`. **Sicherheits-Invarianten:** die vom aktuell geladenen Show referenzierten Assets werden nie gelöscht (live sichtbare Buttons behalten ihr Bild); frisch geschriebene Dateien (< 5 min) werden nie evictet, damit eine **parallele** LightOS-/Test-Session, die sich denselben Cache teilt, ihre gerade entpackten Assets nicht verliert; ein Windows-Dateilock (laufendes QMovie/QPixmap) oder eine parallel schon gelöschte Datei bricht den Lauf per Pro-Datei-`try/except` nicht ab; verwaiste `.tmp`-Reste abgebrochener Schreibvorgänge werden mitentsorgt. Löschen ist verlustfrei — ein wieder geöffnetes Show entpackt seine Assets ohnehin erneut aus dem ZIP. Neue Tests `tests/test_vc_asset_gc.py`.
- **Zugleich abgesichert (adversariale Review dieses PRs, Cross-Session-Fokus):** (1) **`save_show` ist jetzt ein verlustfreier Round-Trip** — fehlt ein referenziertes Asset im Cache (z. B. weil eine parallele Session es gerade evictet hat), übernimmt der Save die Bytes aus der bestehenden `.lshow`, statt es still fallenzulassen und die Datei zu überschreiben (schließt einen **permanenten, stillen Bild-Verlust**); ist ein Asset wirklich unrettbar, gibt es eine laute Warnung statt stiller Löschung. (2) Der Dedup-Pfad (`_write_atomic`) frischt die mtime auf, sodass ein erneut referenziertes Asset nicht unter das `min_age`-Fenster altert. (3) `LIGHTOS_VC_ASSET_CACHE_MB=inf`/riesige Werte deaktivieren die GC nicht mehr still (kein `OverflowError` mehr). (4) Parallele `prune`-Läufe über-evicten nicht mehr unter den Deckel hinaus (`FileNotFoundError` zählt korrekt als „schon geräumt"). (5) Ein gültiger `<sha1>.tmp`-Key wird nicht mehr über den Scratch-`.tmp`-Sonderpfad an der keep-Prüfung vorbei gelöscht.

### 2026-07-18 — Neuer Strahler: Clay Paky Sharpy (Beam Moving Head)

#### Neu

- **Clay Paky Sharpy als eingebautes Geräteprofil** — der erste **Beam**-Strahler der Library (bisher waren alle Moving Heads Spot oder Wash): enger, im Nebel sichtbarer Aerial-Beam mit Farbrad, statischem Gobo-Rad, 8-fach-Prisma, Frost und Focus (kein Zoom). 16-Kanal-Standardmodus, Kanal-Chart gegen die Open Fixture Library + Web-Gegencheck verifiziert. Sicherheits-Defaults: Dimmer aus, Shutter offen (der Beam bleibt über den Dimmer dunkel), Reset/Lampe/Funktion auf „keine Funktion" (kein versehentlicher Reset / keine Lampe-aus beim Patchen). Rendert im 3D-Visualizer als Moving Head. Regressionstest `tests/test_claypaky_sharpy_profile.py`.
- **Die Master-Demo-Show („Komplette Show mit animierten Buttons") enthält jetzt 4 Sharpys** als eigene Beam-Gruppe an einer Mittel-Traverse, mit „Beam an"-Szene, Fan-Bewegungseffekt und Farbrad-Chaser (mit eingelegtem Prisma) sowie passenden Konsolen-Buttons — für den scharfen Strahl-Look neben den weichen Gobo-Spots.

### 2026-07-18 — Laser-Sicherheit: NOT-AUS schließt sein letztes Sub-Frame-Fenster (CDX-12)

#### Behoben

- **Der DMX-Laser-NOT-AUS lässt keinen einzelnen Frame mehr durch, in dem ein Kanal-Modifier den Laser wieder öffnen könnte.** Beim Aktivieren des NOT-AUS wurde bisher erst das Flag gesetzt und dann die Output-seitige Sicherheitsmaske installiert — ein Bildframe genau dazwischen sah den NOT-AUS als aktiv (Renderer stellt den Laser dunkel), fand die zweite Sicherheitsebene aber noch nicht installiert, sodass ein auf einer Laser-Adresse konfigurierter INVERSE-/Range-Lock-Modifier den Laser für diesen einen Frame wieder aufmachte. Der NOT-AUS installiert die Ausgangs-Sicherheitsmaske jetzt **vor** dem Setzen des Flags (Deaktivieren bleibt fail-safe: Flag zuerst, dann Maske leeren — der Laser bleibt lieber einen Frame länger dunkel). Damit ist an jedem Zeitpunkt entweder die Maske aktiv oder der NOT-AUS noch gar nicht scharf — nie ein offenes Fenster. Zusätzlich (aus der adversarialen Safety-Review) wird dieselbe Lücke beim **Umadressieren eines Lasers während aktivem NOT-AUS** geschlossen: die Ausgangs-Sicherheitsmaske deckt jetzt schon die neue Adresse ab, bevor der Renderer auf sie umschaltet. Regressionstests in `tests/test_laser_estop_modifier_bypass.py`.

### 2026-07-18 — 3D-Visualizer: GPU-Shadow-Map-Leak beim Fixture-Löschen (A3D-07)

#### Behoben

- **Beim Entfernen eines Fixtures (Show-Reload) wird jetzt auch die GPU-Shadow-Map seines Scheinwerfers freigegeben.** `removeFixture` löste die Fixture über `f.group.traverse(disposeObj)` auf, aber `disposeObj` (scene/grid_floor.js) gab nur Geometrie + Material frei, nicht `light.shadow` — das Shadow-RenderTarget des Per-Fixture-`SpotLight` leckte pro Show-Reload und wuchs auf schwachen GPUs (z. B. der Surface-Adreno) bis zum WebGL-Context-Loss. `disposeObj` gibt jetzt zusätzlich `light.shadow` frei (deckt den Scheinwerfer über den bestehenden Traverse ab, an einer Stelle). Regressionstest `tests/test_viz_shadow_dispose.py`.

### 2026-07-18 — 3D-Visualizer: Namens-Labels ein/aus + Pop-out-Fenster (VIZ-LABELS-POPOUT, #342)

#### Neu

- **Fixture-Namens-Labels im 3D lassen sich per Button aus-/einblenden** — Toolbar-Button „🏷 Labels" in der eingebetteten Live-View-3D und Checkbox „Fixture-Namen (Labels) anzeigen" im Einstellungen-Tab des Visualizer-Fensters; beide steuern denselben app-weiten Schalter (`AppState.show_fixture_labels`, Default an).
- **Der 3D-Visualizer lässt sich in ein eigenes, frei verschiebbares Fenster ausklinken** („⧉ Ausklinken" in der Live-View-3D) — für einen zweiten Monitor. Das Fenster öffnet auf einem Nebenschirm; die eingebettete Ansicht fällt solange auf 2D zurück (nie zwei 3D-Szenen gleichzeitig, GPU-schonend). Fenster schließen oder „⇲ Zurückholen" dockt wieder an.

### 2026-07-17 — 3D-Visualizer: benannte Kameras nach Show-Wechsel (A3D-13 / A3D-22)

#### Behoben

- **Benannte Kameras + das Kamera-Menü übernehmen jetzt beim Laden einer Show den Stand der NEUEN Show, auch wenn das 3D-Fenster schon offen ist.** Vorher lief dieser Abgleich nur beim ersten Öffnen des Visualizers (`_push_initial_state`) — wer das Fenster offen ließ und eine andere Show lud, sah weiter die gespeicherten Kameras/Menü-Einträge der alten Show. Der `show_loaded`-Handler (`visualizer_window.py`) pusht die Kameras jetzt neu an die 3D-Ansicht und baut das Toolbar-Kamera-Menü neu auf (eine Show ohne gespeicherte Kameras räumt die alten Einträge weg). Regressionstest `tests/test_a3d13_show_loaded_camera_resync.py`. Schließt A3D-13 (P2) und den Duplikat-Befund A3D-22 (P3, selber Codex-157-Fund).

### 2026-07-16 — Demo-Show „Komplette Show mit animierten Buttons" (Tooling)

#### Neu

- **Neuer Demo-Show-Generator `tools/build_komplette_animierte_show.py`** — baut eine komplette Test-Show (8 PAR, 4 Gobo-Moving-Heads, 4 Laser, 2 Nebelmaschinen, Effekte für Farbe/Bewegung/Gobo/Strobe/Nebel, virtuelle Konsole, 2D+3D-Rig), deren VC-Buttons durchgehend die neue Galerie nutzen: jeder Effekt-Button trägt eine passende animierte Grafik (`bg_image=`). Lint `--strict` sauber, alle 9 Galerie-Grafiken portabel in die `.lshow` eingebettet. Live per Computer-Use verifiziert: Grafiken skalieren auf die Buttons, die GIFs animieren auf der Konsole, die Buttons lösen ihre Effekte real aus (sichtbar in 2D-FX-Badges + 3D-Lichtkegeln). Erste Referenz-Show für das animierte-Buttons-Feature.

### 2026-07-16 — Virtual Console: grafischer Galerie-Auswähler auf dem Button (VC-IMG Galerie, Teil 2)

#### Neu

- **Der Button-Hintergrund lässt sich jetzt aus einem grafischen Auswähler picken** — Rechtsklick auf einen VC-Button → „Hintergrundbild wählen…" öffnet ein Fenster mit einem Raster aller eingebauten Effekt-Grafiken (die GIFs animieren direkt in der Vorschau). Ein Klick übernimmt die Grafik sofort auf den Button — kein Dateisuchen nötig. Wer doch ein eigenes Bild will, nimmt im selben Fenster „Eigene Datei…" (wie bisher). Ersetzt den bisherigen direkten Datei-Dialog. Tests: `tests/test_vc_gallery_dialog.py`.

### 2026-07-16 — Virtual Console: eingebaute Galerie fertiger Button-Grafiken (VC-IMG Galerie)

#### Neu

- **LightOS bringt jetzt eine Galerie fertiger Button-Grafiken mit** — animierte GIFs und Bilder, die wie Licht-Effekte aussehen (u. a. Puls, Strobe, Regenbogen-Lauf, Farb-Chase, Farbrad, VU-Meter, Funkeln, Gobo-Dreh, Beam-Sweep, Atem-RGB, Spektrum, Heiß-Weiß). Damit kann man einem VC-Button sofort einen passenden Effekt-Look geben, ohne selbst eine Datei zu suchen. Die Grafiken liegen unter `assets/vc_gallery/` und werden — wie eigene Bilder — beim Verwenden portabel in die `.lshow` eingebettet. Zugriff im Show-Builder über `b.button(..., bg_image="<name>")` (ungültiger Name → klarer Fehler mit Vorschlag); das Demoshow-Werkzeug nutzt die Galerie ab jetzt automatisch. Der Show-Lint warnt (`VC-BGIMAGE`), falls in einer hand-editierten Show statt eines eingebetteten Asset-Keys ein roher Galerie-Name steht. Tests: `tests/test_vc_gallery.py`. *(Der grafische Galerie-Auswähler auf der Konsole folgt separat.)*

### 2026-07-16 — Virtual Console: eigenes Hintergrundbild/GIF pro Button (VC-IMG)

#### Neu

- **Ein VC-Button kann jetzt ein eigenes Bild oder animiertes GIF als Hintergrund tragen** — Rechtsklick auf den Button → „Hintergrundbild wählen…" (PNG/JPG/GIF/WEBP/BMP) bzw. „Hintergrundbild entfernen". Das Bild füllt die Tastenfläche, skaliert automatisch mit, wenn man den Button größer/kleiner zieht, und liegt unter der (weiterhin möglichen) Beschriftung; ein dezenter Schleier hält den Text lesbar. GIFs animieren live auf der Konsole (und pausieren, wenn die Bank nicht sichtbar ist → keine Extra-Last). So baut man eigene, individuell aussehende Effekt-Buttons. **Portabel:** das gewählte Bild wird in die `.lshow`-Datei eingebettet — die Show funktioniert mit ihren Button-Bildern auch auf einem anderen PC. Der plastische 3D-Look der Taste (Wölbung, Druck-Feedback, Aktiv-Glow) bleibt erhalten. Tests: `tests/test_vc_button_bg_image.py`.

### 2026-07-16 — Codex-Funde CDX-08..11 (Auto-Fit-Feinschliff + Dev-Härtung)

#### Behoben / Verbessert

- **2D-Bühne Auto-Fit** greift jetzt nur noch bei einem echten kompakten Klumpen: ein bereits gut gespreiztes Rig, das schon EINE Achse (Breite oder Höhe) ausfüllt, wird beim Laden nicht mehr eingepasst/geschrumpft (CDX-09).
- Dev/intern: Demoshow-Generatoren treiben die PAR-Intensität mit, sodass die Farb-Pads eigenständig leuchten (CDX-08); AGENTS.md-CHANGELOG-Konvention an den gelebten Stil angeglichen (CDX-10); UI-25-Fairness-Test härtet, dass auch der kurze Tab nie zu „…" kollabiert (CDX-11). Alle aus dem Codex-Review-Harvest.

### 2026-07-16 — Behoben: Nebelmaschine mit Lüfter — Lüfter jetzt getrennt regelbar (CDX-07)

#### Behoben

- **Bei der Nebelmaschine im Modus „2-Kanal (Nebel + Lüfter)" lässt sich der Lüfter jetzt unabhängig vom Nebelausstoß regeln.** Vorher trugen beide Kanäle dieselbe Kennung („Dimmer"), sodass der Programmer sie zu **einem** Regler zusammenfasste und der Lüfter still dem Nebelwert folgte. Der Lüfter hat nun eine eigene Kennung („Lüfter") und einen eigenen Regler; der Nebelausstoß bleibt vom Grand Master/Blackout gedimmt (Sicherheit), der Lüfter läuft davon unabhängig. Bestehende Shows werden beim Start automatisch mit-korrigiert. Gefunden im Codex-Review-Harvest (CDX-07). Tests in `tests/test_fog_hazer_profile.py`.

### 2026-07-16 — Test-Show „Laser Gobo Test 2026" + Anleitung

#### Neu

- **Neue komplette Test-Show mit Laser, Gobo-Moving-Heads, PARs und Nebel** — 18 Geräte über 2 Universen, damit sich Laser-, Gobo-, Bewegungs-, Farb-, Dimmer- und Nebel-Steuerung an einem Rig prüfen lassen. Reproduzierbar über den Generator `tools/build_laser_gobo_test.py` (Show-Lint `--strict` sauber). Live per Computer-Use durch alle UI-Bereiche verifiziert (2D/3D-Darstellung inkl. Fixture-Labels + Modus-Indikator, Virtuelle Konsole, Laser-Panel, Gobo-Kacheln). Anleitung: [`docs/ANLEITUNG_LASER_GOBO_TEST_2026.md`](docs/ANLEITUNG_LASER_GOBO_TEST_2026.md). (Die `.lshow`-Datei ist git-ignoriert; über den Generator jederzeit neu erzeugbar.)

### 2026-07-16 — Doku: Audit-Coverage-Tracker (DOC-10)

#### Neu / Tests

- **Neuer Überblick, welche Teile der Software wann geprüft wurden:** [`docs/AUDIT_COVERAGE.md`](docs/AUDIT_COVERAGE.md) listet pro Subsystem (DMX, MIDI, Show-Datei, Fixtures, Audio, Virtual Console, UI, …) das letzte Audit-Dokument, das Datum und den Status (geprüft / teilweise / offen). Macht die nächste sinnvolle Prüf-Runde sofort sichtbar und verhindert Doppel-Prüfungen. Ein Test (`tests/test_audit_coverage_docs_exist.py`) stellt sicher, dass jedes verlinkte Dokument wirklich existiert.

### 2026-07-16 — Virtual Console: plastische Fader & Speed-Dials (VC3D-02)

#### Neu / Tests

- **Fader-Griffe und Speed-Dials wirken jetzt plastisch wie die VC-Tasten:** Der Fader-Griff ist nicht mehr ein flacher Balken, sondern eine leicht gewölbte Taste mit Licht-/Schattenkante und mittiger Griff-Rille; die Speed-Dials (BPM/Tempo) sitzen auf einer erhabenen Dreh-Knopf-Fläche, sodass Wertanzeige und Zeiger auf einem „echten" Knopf liegen. Konsistenter, griffiger Pad-/Fader-Look über die ganze Virtual Console (gleicher `vc_style`-Helfer wie die Buttons, rein QPainter — keine Assets, touch-freundlich). Tests: `tests/test_vc_style_3d.py` (Crash-Sicherheit bei jeder Größe + Wölbungs-Nachweis für `paint_slider_handle`/`paint_dial_knob`).

### 2026-07-16 — 3D-Visualizer: Gerätenamen direkt im 3D-Bild + Modus-Indikator (VIZ-14)

#### Neu / Tests

- **Jedes Gerät trägt jetzt sein Namensschild im 3D-Visualizer:** Über jedem Gerät schwebt ein kleines Label mit `#<Nummer> <Kurzname>` (z. B. `#12 MH LINKS`) — so sieht man auf einen Blick, welches Gerät welches ist, ohne erst klicken zu müssen. Das Schild folgt dem Gerät beim Verschieben/Drehen und verschwindet im 2D-Modus automatisch. **Gegen Unübersichtlichkeit:** die Schilder schrumpfen beim Rauszoomen (feste Weltgröße) und blenden sich ab einer gewissen Kamera-Entfernung ganz aus — dichte, weit entfernte Rigs bleiben sauber. Bewusst schlank gehalten (kein separater Ein/Aus-Schalter in v1); erzeugt keine zusätzliche Grafiklast (der Zoom-Check hängt sich an die ohnehin vorhandene Kamera-Aktualisierung, kein Dauer-Rendern). Tests: `tests/test_viz14_labels_scene.py` (Aufbau/Anhängen/Text/Aufräumen ohne Dauer-Render + Kamera-Distanz-Gate).

- **Man sieht jetzt immer, in welchem Modus der 3D-Visualizer ist:** Ein ruhiger Rahmen um das 3D-Bild zeigt permanent den Modus an — dezent kühl im **Ansehen**-Modus (nichts kann kaputtgehen), deutlich orange im **Bauen**-Modus (Geräte platzieren/bewegen), mit einer kleinen Ecken-Beschriftung („ANSEHEN" bzw. „BAUEN · Fixtures"/„BAUEN · Bühne"). Das ist das direkte Gegenmittel gegen das bisherige „Modus-Wirrwarr" (man wusste oft nicht, warum ein Klick nichts tat — weil man im falschen Modus war). Erster kleiner Schritt hin zu den zwei klaren Hauptmodi; die volle Modus-Umstellung folgt.
- Der Rahmen ist reine Anzeige (fängt keine Klicks ab) und erzeugt keine zusätzliche Grafiklast (kein Dauer-Rendern). Tests: `tests/test_viz14_mode_frame_scene.py` (Existenz + Default „Ansehen", Umschalten per `setEditMode` und über den echten Poll-Pfad, kein Dauer-Render, nicht interaktiv).

### 2026-07-15 — Quality-of-Life-Phase: Bedienbarkeit & Lesbarkeit (QOL-01..04, UI-19/25/26, VC3D-01/03)

#### Neu / Verbessert / Tests

- **2D-Bühne aufgeräumt (UI-26 / QOL-01):** Fixture-Namen überlappen nicht mehr unlesbar bei dichter Platzierung — die 2D-Live-View zeichnet Labels jetzt nach Bildschirm-Nachbarabstand (voll → nur Nummer → aus), Auswahl/Hover immer voll. Neue Patches ohne gespeicherte Positionen erscheinen als aufgeräumtes Raster statt gedrängtem Bogen; die Icon-Größe ist per Voreinstellung (`fixture_size`) einstellbar. (PR #304)
- **„Zuletzt verwendet" unterscheidet gleichnamige Shows (QOL-02):** Zwei Shows mit gleichem Dateinamen (z. B. in AppData vs. Projektordner) bekommen das kürzeste unterscheidende Ordner-Suffix (`… — …/LightOS/shows`); dieselbe Datei in anderer Schreibweise zählt als ein Eintrag. Voller Pfad weiter im Tooltip. (PR #305)
- **Fixture-Namen in der Geräte-Liste lesbar (QOL-03):** Lange Namen werden mittig gekürzt (der unterscheidende Schwanz bleibt sichtbar: `[009] … Links`) und jeder Eintrag hat einen Tooltip mit dem Vollnamen. (PR #306)
- **Programmer-Tab korrekt benannt (QOL-04):** Der Attribut-Tab „Hilfe" heißt jetzt „Assistent" — er enthält die Effekt-/Funktionsverwaltung, keine Hilfe. (PR #303)
- **Deutsche Options-Labels app-weit (UI-19):** Programmer-Matrix-Auswahlfelder und VCStepper/VCEncoder-Beschriftungen zeigen deutsche Labels (z. B. „Läufer-Anzahl", „Rückwärts leeren") statt roher Tokens (`runner_count`, `reverse`); der gespeicherte Wert bleibt unverändert. (PR #308)
- **Faire Sektions-Tab-Breiten (UI-25):** Bei knappem Fensterplatz kollabiert kein Tab mehr zu reinem „…" — kurze Titel (z. B. „E/A") bleiben lesbar, nur lange Titel werden gekürzt. (PR #309)
- **Plastische Virtual-Console-Buttons (VC3D-01/03):** VC-Tasten wirken erhaben mit Licht-/Schattenkante und Druck-Feedback; auf voll gesättigten Farben liest die Wölbung jetzt ebenfalls, und der Farb-Badge überlappt den Tastentext nicht mehr. (PRs #296, #307)
- **Tests:** `test_live_view_declutter`, `test_recent_menu`, `test_fixture_list_tooltip`, `test_ui19_option_labels`, `test_ui25_tab_allocation`, `test_vc_style_3d` (jeweils reine Funktionen + Widget-/Render-Contracts, headless). Jede Änderung mit vollem Test-Gate + adversarialer Sub-Agent-Review; UI-relevante Punkte zusätzlich per Computer-Use auf dem echten Screen bestätigt.

### 2026-07-15 — 3D-Visualizer: Auswahl folgt dem Programmer — beidseitig + Identify-Flash (VIZ-14, Teil 1+2+3)

#### Neu / Tests

- **Ein Gerät im 3D-Visualizer (oder seiner Geräteliste) anklicken wählt es jetzt auch im Programmer aus:** Die 3D-Selektion und die Liste im Visualizer-Fenster treiben die gemeinsame Auswahl (die u. a. Programmer, Matrix, Effekte und Paletten steuert). So beantwortet ein Klick „welches Gerät ist das?" und man kann es direkt weiterbearbeiten. (Slice 1a der 3D-Bedien-UX.)
- **Und umgekehrt (neu, Slice 1b): eine Auswahl im Programmer (oder in jeder anderen Ansicht) markiert die betroffenen Geräte jetzt auch im 3D-Visualizer.** Wählt man z. B. im Programmer „alle Moving Heads", heben sich genau diese im 3D-Bild hervor — die Auswahl ist in beide Richtungen synchron. Echo-sicher gebaut: die aus Python gesetzte Auswahl meldet sich NICHT wieder an Python zurück (kein Rückkopplungs-Loop).
- **Und jetzt blinken ausgewählte Geräte kurz auf (Slice 1c „Identify"):** Wählt man Geräte (im Programmer oder im 3D), blitzen ihre Auswahl-Ringe im 3D-Visualizer ~1,5 s lang auf — so findet man sofort, „wo ist das Gerät?", danach beruhigt sich die Anzeige zum statischen Rahmen. Bewusst als kurzes Aufblitzen (nicht als Dauer-Pulsieren) gebaut, damit der sparsame On-Demand-Renderer danach wieder in den Ruhezustand fällt (keine Dauerlast auf schwacher Grafik).
- Tests: `tests/test_viz14_selection_sync.py` (3D→Auswahl, Liste→Auswahl, leere 3D-Auswahl löscht nicht, Mehrfachauswahl-Guard, Rückrichtung→Bridge-Poll, Signal/Poll-Mirror); `tests/test_viz14_selection_scene.py` (End-to-End in echter QWebEngine: Python-Poll → JS wendet Auswahl an, ohne Echo, idempotent; **Identify-Flash rendert im Fenster und fällt danach in Idle zurück, obwohl die Auswahl bestehen bleibt**).

### 2026-07-15 — 2D-Bühne: Auto-Fit-Zoom beim Laden (QOL-05)

#### Neu / Tests

- **Die 2D-Bühne passt die Ansicht beim Laden automatisch auf die Geräte an:** Kompakte Rigs (deren Positionen aus dem 3D-Visualizer projiziert wurden) lagen vorher als überlappender Klumpen im Weltraum. Jetzt zoomt und zentriert die 2D-Ansicht beim Öffnen einer Show so, dass die Fixtures die Fläche mit etwas Rand füllen — die Positionen selbst bleiben unverändert (nur die Ansicht skaliert). Ein neuer **„⤢ Einpassen"-Knopf** neben dem Zoom-Regler ruft das jederzeit manuell auf. Eine bewusst gewählte Zoom-Stufe bleibt erhalten (der Auto-Fit greift nur, wenn das Rig das Sichtfeld schlecht ausfüllt).
- Tests: `tests/test_live_view_fit.py` (Fit-Zoom-Berechnung inkl. Klemmung + Grenzfälle, Klumpen wird hineingezoomt, gut gefüllte Ansicht bleibt).

### 2026-07-15 — Nebelmaschine als eingebautes Fixture (FIX-FOG)

#### Neu / Tests

- **Nebelmaschine/Hazer jetzt in der Fixture-Library:** Neues Builtin-Profil **„N-10 Nebelmaschine"** (`EURON10`, Typ Hazer) mit zwei Modi (1-Kanal „Nebel" · 2-Kanal „Nebel + Lüfter"). Der Nebel-Ausstoß ist ein Intensitäts-Kanal (Grand Master/Blackout skalieren mit). Damit lassen sich Nebel-/Smoke-Maschinen ohne selbst angelegtes Profil patchen — sie rendern als Hazer im 3D-Visualizer und mit Fog-Icon in der 2D-Ansicht. Bestehende Fixture-Datenbanken bekommen das Profil idempotent nachgerüstet.
- Tests: `tests/test_fog_hazer_profile.py` (Seed als Hazer, beide Modi + Nebel-Kanal, Idempotenz der Migration).

### 2026-07-12 — Fixture-Generator: 3D-Modell wählbar mit Automatik-Vorschlag (FM-12)

#### Neu / Verbessert / Tests

- **„3D-Modell"-Auswahl im Fixture-Generator:** Beim Anlegen (oder QLC+-Import) eines Geräteprofils lässt sich jetzt explizit wählen, welches Visualizer-Modell das Gerät bekommt — 13 Modelle von PAR-Dose über Mover-Bar bis Hazer. Der Standardeintrag „Automatisch" zeigt live in Klammern, was die Kanal-Heuristik für den gerade bearbeiteten Modus vorschlagen würde (z. B. „Mover-Bar" bei zwei Pan-Köpfen); die Heuristik ist dafür als DB-freie Funktion `suggest_viz_model()` ausgekoppelt und bleibt die EINE gemeinsame Quelle mit dem Visualizer.
- **Profil-Override wirkt überall gleichzeitig:** Die Wahl wird als neues Feld `FixtureProfile.viz_model` gespeichert (idempotente ALTER-TABLE-Migration für bestehende `fixtures.db`; leer = Automatik, Bestandsprofile unverändert). `viz_model_for` liefert den Override vor der Heuristik — 3D-Modell, 2D-Live-View-Symbol, Listen-Icon und die Spider-Spiegel-Option im Patch-Dialog schalten gemeinsam um. Der neue Override-Cache wird zusammen mit dem Channel-Cache invalidiert (auch direkt nach dem Speichern im Generator).
- **Adversariale Review vor Merge (3 Linsen × 2 Skeptiker), 3 Funde bestätigt + gefixt:** Ein `spider`-Override auf Geräten ohne Multihead-Banks blieb dauerhaft dunkel → `updateSpiderDmx` fällt ohne Head-Daten auf die Top-Level-Farbe/Basis-Tilt zurück (QtWebEngine-Regressionstest); der Override-Cache wird beim Patch-Neuaufbau vorgewärmt (kein synchroner DB-Roundtrip pro Profil im 20-FPS-Paint-Pfad der Live-View); transiente DB-Fehler beim Lookup werden nicht mehr dauerhaft als „kein Override" gecacht.
- Tests: `tests/test_viz_model_override.py` (17) — Heuristik-Regeln inkl. Laser-Gate, Migration einer Alt-DB, Payload-/Speicher-Roundtrip, Override-Routing mit Cache-Invalidierung + Fehlerfall + Prewarm, Dialog-Vorschlag + explizite Wahl; dazu die Spider-Fallback-Regression in `test_viz13_scene_modules_smoke.py`.

### 2026-07-12 — Realismus-Pass: 3D-Fixture-Modelle auf echte Datenblatt-Maße (FM-11)

#### Neu / Verbessert / Tests

- **Alle prozeduralen Fixture-Modelle folgen jetzt echten Geräteabmessungen** (Referenzen als Kommentar am jeweiligen Builder in `builders.js`): PAR-64-Dose Ø 0,23 m statt Ø 0,44 (neu mit Doppelbügel); Moving Head der Intimidator-260-Klasse ~0,48 m hoch statt 0,85; 8×10W-Spider 0,40 × 0,25 × 0,20 m statt 0,88 × 0,54 m Grundfläche; 4er-PAR-Bar in Dotz-TPar-Maßen (~1,05 m statt 1,82 m); 4-Kopf-Mover-Bar ~1,05 m mit Ø-0,10-m-Köpfen statt 2,05 m; LED-Pixel-Bar 1,07 × 0,088 × 0,065 m; Strobe 0,46 × 0,14 × 0,24 m; Dimmerpack als kompakter 4-Kanal-Truss-Kasten mit Ausgangs-Dosen statt Torblenden; Scanner mit **Spiegel am Gehäuse-Ende** (Dynamo-Klasse) statt mittig; Laser in Ehaho-L2600-Maßen (201 × 66 × 160 mm, flaches Alu-Gehäuse mit Bügel, Frontfenster, Lüftungsgitter); Nebelmaschine der N-10-Klasse mit vorstehender Düse und Hängebügel; Hazer der Antari-HZ-100-Klasse (hochkant, Tragegriff, Ausblasgitter vorn oben).
- **LowRes-Anschluss der Modelle:** Neuer `segs()`-Helfer in `builders.js` — auf Low-Tier-GPUs halbieren alle Gehäuse-Rundkörper ihre Radial-Segmente (Boden 6), analog zur bestehenden Beam-Kegel-Reduktion; High-Tier bleibt unverändert. Der Mover-Bar-Beam hängt jetzt an der Linsen-Position statt an einem hart kodierten Offset (überlebt künftige Maß-Änderungen).
- Tests: `test_fixture_models_have_realistic_dimensions` (Bounding-Box-Abnahme von PAR/MH/Spider/Bars/Nebel in echtem QtWebEngine, Beams ausgenommen); Low-/High-Tier-Tests prüfen zusätzlich die Gehäuse-Segmente (`mh-head-body` 14 vs. `par-body` 16).

### 2026-07-09 — sACN sendet Stream-Termination beim Adapter-Wechsel (OUT-06 Teil, aus AUD-03)

#### Geaendert / Fixes

- **sACN-Ausgabe verwirft sich beim Schließen sofort:** `SACNSender.close()` schloss bisher nur den Socket. Empfänger mussten die Quelle dann über den E1.31-Timeout (~2,5 s Network Data Loss) verwerfen — beim Adapter-Wechsel blieben kurz zwei Quellen aktiv (Merge-Fenster). Jetzt sendet `close()` je zuletzt bespieltem Universum **3 Pakete mit gesetztem `Stream_Terminated`-Options-Bit** (E1.31-2018 6.2.6), sodass Empfänger die Quelle **sofort** freigeben. `_pack_framing` nimmt dafür ein optionales `options`-Byte; normale Datenpakete bleiben unverändert (Options = 0). Der sACN-CID ist weiterhin pro Instanz zufällig (Persistenz braucht einen Config-Speicherort → OUT-06-Rest offen).
- **Tests:** `tests/test_sacn_loopback.py` (3 neu, Fake-Socket) — `close()` sendet 3× je Universe mit `Stream_Terminated`-Bit auf die korrekten Multicast-Ziele; normale Pakete haben das Bit nicht; `close()` ohne bespielte Universen ist sicher. Herkunft: AUD-03 (`docs/DMX_OUTPUT_AUDIT_2026_07_08.md`).

### 2026-07-12 — Fehlendes Other-Modell ergänzt, Truss-Geometrie entzerrt

#### Neu / Verbessert / Tests

- **Eigene 3D-Darstellung für importierte Geräte der Klasse `other` (FLA-4):** Fan/Effect/Other-Profile fallen nicht länger auf die runde PAR-Geometrie zurück, sondern erhalten ein neutrales technisches Gehäuse mit Haltebügel, Statusfeld, Ident-Glyph und Lüftungsdetails. Der bestehende Single-Head-/DMX-Vertrag bleibt bewusst erhalten; beliebige Legacy-Typstrings wie `color` nutzen weiterhin den kompatiblen PAR-Fallback. Das Modell ist auf höchstens 16 Drawables inklusive Beam begrenzt. Dieselbe Klasse hat jetzt ein eigenes quadratisches Fragezeichen-Symbol im 3D-Top-Down-Plan, in der nativen 2D-Live-View und in Listen/Bäumen. Runtime-Regression in `test_viz13c1_topdown_polish.py`, Symbol-Smoke in `test_viz_model_routing.py`/`test_mini_icons.py`.
- **Traversen behalten ihre echte Geometrie:** `truss_square_2m.obj` ist mit der 2-m-Längsachse auf lokal Z modelliert (nicht X). Horizontal und vertikal wird das Kind jetzt zuerst Z→X beziehungsweise Z→Y orientiert und anschließend über einen äußeren Wrapper in Weltachsen skaliert. Dadurch stimmen die Zielmaße weiterhin exakt (`4 × 0,3 × 0,3 m` bzw. `0,3 × 4 × 0,3 m`), ohne den 30-cm-Querschnitt um Faktor ~13 zur Länge zu verzerren und die echten Gurte/Diagonalen zusammenzustauchen. Der echte QtWebEngine-/OBJ-Test prüft Bounds, Quell-/Zielachse, Rotation und einen moderaten Skalierungsquotienten (`test_truss_obj_uses_its_real_z_long_axis`).

### 2026-07-11 — Render-Qualität wählbar: Automatik + manueller Override (VIZ-15 Teil)

#### Neu / Tests

- **Einstellungen-Tab „Render-Qualität":** Stufe `Automatisch (empfohlen)` / `Hoch` / `Niedrig`. Automatisch = die GPU-Probe beim Szenen-Start entscheidet (schwache Chips wie das Surface-Adreno → Niedrig); die manuelle Wahl übersteuert sie, falls die Erkennung danebenliegt. Ein Label zeigt die **aktive** Stufe der laufenden Szene (JS meldet sie beim Channel-Connect über den neuen Slot `reportGpuTier`). Die Wahl ist **geräte-gebunden** (`ui_prefs.json`, nicht in der Show) und reist als `gputier`-Query mit jedem `load_stage_html` — sie greift damit für alle Targets (Vollfenster, eingebettete 3D-View, Crash-Guard-Selbstheilung, „Szene neu laden"); ein Stufenwechsel lädt die Szene automatisch neu. `tests/test_viz_quality_tier.py` (11 Tests: Pref-Roundtrip/Fallbacks, URL-Query, Combo-Handler, Bridge-Slot, Label).


### 2026-07-11 — Low-Spec-Modus: Visualizer läuft flüssig auf schwachen GPUs (Surface)

#### Verbessert / Tests

- **Automatische GPU-Tier-Erkennung (`renderer.js`):** Eine Wegwerf-Canvas probt vor dem Renderer-Bau `MAX_TEXTURE_IMAGE_UNITS` und den Chip-Namen (Adreno/Mali/PowerVR/SwiftShader). Auf Low-Spec-Geräten: **kein MSAA** (Antialias ist eine Konstruktor-Entscheidung), **Pixel-Ratio-Deckel 1,25** statt 2 (Fragment-Last ist quadratisch — auf dem High-DPI-Surface bis zu ~2,5× weniger Pixel), **PCF statt PCFSoft-Schatten**, **256er statt 512er Shadow-Maps** und **12 statt 24 Kegel-Segmente**. Der `pixelRatioSignal`-Handler (Monitor-Wechsel) respektiert denselben Deckel. Override für Tests/Debug: `?gputier=low|high`; Tier als `window.__lightos.gpuTier` exponiert. Desktop-GPUs behalten die volle Optik.
- **Dunkle Lampen kosten nichts mehr (alle Tiers):** Ein `SpotLight` mit Intensität 0 wurde bisher trotzdem in jedem beleuchteten Pixel mitgerechnet — bei 48 Fixtures der größte laufende Kostenblock. `applyGenericColor` nimmt dunkle Spots jetzt komplett aus der Licht-Auswertung (`visible=false`, analog zu Beam/FloorSpot) und aktiviert sie beim Aufdrehen wieder; auch der Initial-Build startet dunkel-unsichtbar. QtWebEngine-Smoke prüft Tier-Erkennung, Kegel-Geometrie und das Culling über den echten `dmxBatch`-Pfad in beide Richtungen.

### 2026-07-11 — 3D-Visualizer rendert große Rigs wieder (Shader-Texture-Limit)

#### Behoben / Tests

- **Bühne blieb bei großen Rigs komplett unsichtbar (nur Beam-Kegel zeichneten):** Jede schattenwerfende SpotLight kostet im Fragment-Shader jedes beleuchteten Materials eine Texture-Unit (Shadow-Map). Beim 48-Fixture-Demo-Rig überschritt das auf GPUs mit `MAX_TEXTURE_IMAGE_UNITS=16` (z. B. Adreno im Surface) das Limit — kein beleuchteter Shader kompilierte mehr (`FRAGMENT shader texture image units count exceeds MAX_TEXTURE_IMAGE_UNITS(16)` + Dauer-Spam `useProgram: program not valid` im crash.log). Jetzt vergeben `addFixture`/`removeFixture` ein deterministisches Shadow-Budget (`maxTextures − 6 Reserve`, fid-Reihenfolge): die ersten N Spots werfen Schatten, alle weiteren leuchten ohne; Entfernen verteilt frei gewordenes Budget zurück. QtWebEngine-Smoke `test_shadow_spot_budget_respects_texture_units` prüft Kappung und Rückverteilung mit 30 echten Fixtures.
- **Bühnen-Sync gegen GPU-Stress gehärtet (adversariale Review der Fixes vom 10./11.07.):** (1) Ein Element-Build-Throw (z. B. bei WebGL-Context-Loss) reißt den restlichen Bulk-Bau nicht mehr ab — vorher blieb von einer 15-Element-Bühne exakt Element #0 übrig und das Qt-Panel fror bei „1 Element" ein. (2) Der lokale Repair-Loop ist token-aware und respektiert Lösch-Tombstones — er kann keine gelöschten oder zur vorherigen Bühne gehörenden Elemente mehr reanimieren. (3) `stageObjectDeleted` (die einzige Tür, durch die das autoritative Python-Modell schrumpfen kann) trägt jetzt dieselben Guards wie der Snapshot-Reconcile: Lösch-Echos aus Reload-Churn, zu Elementen eines laufenden Reloads oder mit bereits eingereihtem Re-Add werden ignoriert. (4) Das Nachsenden fehlender Elemente gibt nach 3 Versuchen auf, statt Selektion und Positions-Sync für den Rest der Session einzufrieren (Python behält die Elemente autoritativ); ein 6-s-Backstop öffnet das Pending-Gate auch bei völliger Echo-Stille. (5) Ein überholtes (stale) Echo darf keine Elemente mehr ins Modell zurücklegen — nur Updates bestehender. (6) Panel-Löschen/Undo laufen inkrementell statt als Full-Reload (Gegenstück zum Add-Pfad vom 10.07.). (7) Die Poll-Event-Queue ist auf 512 gedeckelt und wird beim Page-Reload geleert (kein Stale-Burst in frische Seiten). Regressionstests in `test_visualizer_bauraum_ui.py`, `test_viz11_bridge_fixes.py` und QtWebEngine-Smoke (`test_explicit_delete_survives_repair_chain`).
- **`state.js` blieb nach dem Test-Gate als CRLF-Geisteränderung dirty:** Der Cache-Buster-Smoke-Test las/schrieb das Modul ohne `newline=""` und konvertierte dabei die Zeilenenden. Roundtrip ist jetzt byte-treu.
- `.gitignore`: Computer-Use-Debug-Screenshots (`artifacts_*.png`) werden nicht mehr als untracked Dateien angezeigt.

### 2026-07-10 — Bühnen-Editor hält die Auswahl beim Parameter-Edit stabil

#### Behoben / Tests

- **Kein Springen bzw. Flackern der Bühnen-Auswahl mehr beim Ändern von Eigenschaften:** Die lokal im Baum gewählte Element-ID wird sofort als maßgeblich gespeichert. Unvollständige asynchrone 3D-Reload-Echos dürfen die Bühnenliste nicht teilweise zurückdrehen. Während ein Bühnenfeld bearbeitet wird, kann ein nachlaufendes WebGL-Auswahlecho die Qt-Auswahl nicht überschreiben; jede Änderung bestätigt die aktuelle Auswahl gezielt im 3D-View. `tests/test_visualizer_bauraum_ui.py` deckt Baum-ID, partielle Echos und den aktiven Eingabefokus ab. Reale Desktop-Prüfung: Publikumsfläche ausgewählt, X geändert — 3D-Markierung, Tabellenzeile und Eigenschaftsfeld blieben synchron.
- **Neues Fixture ohne Dimmer erzeugt keinen sichtbaren Rest-Lichtkegel mehr:** Der initiale Beam-Opacity-Wert darf bei Intensität 0 exakt 0 sein. Damit summieren sich beim Aufbau großer Rigs keine erzwungenen 2%-Kegel zu einem scheinbar flackernden Schleier. Der echte QtWebEngine-Szenen-Smoke prüft das mit einem ungedimmten Moving Head.
- **Bühnen-Elemente werden beim Hinzufügen nicht mehr per Full-Reload gebaut:** Der neue inkrementelle Bridge-Pfad übergibt die Python-ID direkt an den 3D-View und behandelt die erwartete Direkt-/Poll-Doppelzustellung idempotent. Dadurch bleiben bestehende Bühnenelemente und die Auswahl bei schnellen Add-/Undo-Operationen erhalten. Der QtWebEngine-Smoke prüft den direkten Add-Pfad sowie vollständige 9-Element-Bulk-Ladungen über Signal und Poll. Ein separater Live-Befund zur Synchronisation sehr großer gespeicherter Bühnen bleibt offen und ist im Backlog vermerkt.
- **Große gespeicherte Bühnen verlieren ihre Trussen nicht mehr durch Teil-Snapshots:** Python bleibt für die geladene Bühne autoritativ; unvollständige 3D-Echos werden mit den fehlenden, stabilen IDs ergänzt statt als Löschauftrag behandelt. Echte Löschungen aus dem 3D-Editor haben einen eigenen Bridge-Rückweg. Zusätzlich prüft der Renderer nach einer Bulk-Ladung seine erwarteten Objekt-IDs und baut unmittelbar fehlende Elemente lokal nach. Regressionstests decken den expliziten Löschpfad und die Renderer-Selbstheilung ab.

### 2026-07-10 — Render-p95 ist als 44-Hz-Regression-Gate geschützt (QA-20)

- Der Benchmark-Test verlangt für ein kleines 1-Universum-Rig p95 unter 20 ms; das liegt unter dem 44-Hz-Framebudget von 22,7 ms und lässt normalen CI-Jitter zu.

### 2026-07-09 — UI-View-/VC-Widget-Smoke vollständig (QA-09 + QA-10)

#### Tests

- **Neue `tests/test_ui_smoke_enumerated.py` (34 Tests):** inventarisiert alle öffentlichen no-arg Views in `src/ui/views` per `pkgutil`/`importlib`/`inspect`; neue oder umbenannte Views lassen den Test rot werden. Jede View wird headless gebaut, alle 19 VC-Widgets durchlaufen ihren Serialisierungs-Roundtrip. Die acht bislang komplett ungetesteten Editoren bauen mit minimalen echten Engine-Objekten und beweisen je ein zentrales Kind-Widget.
- **Reale Browser-Abnahme des Web-Remote:** gegen die laufende lokale Anwendung verbinden, STOP sowie Blackout AN/AUS bedienen; WebSocket-ACK und sichtbares Log wurden bestätigt. Der restliche Desktop-/Hardware-Teil von QA-LIVE bleibt im Verifikationsplan.
### 2026-07-10 — Output-Monitor erreicht alle gültigen Universen (QA-10)

#### Behoben / Tests

- **Universe 17–32 waren im Output-Monitor nicht auswählbar:** `OutputView` begrenzte seinen Universe-Spinbox auf 16, während Patch, Validierung und Output-Konfiguration bis 32 arbeiten. Der Monitor akzeptiert jetzt U1–32. `tests/test_output_view.py` baut die View headless, steuert die Spinbox mit echten Tastaturereignissen bis U32 und prüft die 512 Zellen inklusive DMX-Refresh.
### 2026-07-10 — MIDI-Ansicht räumt ihre Hintergrund-Subscriber auf (QA-10)

#### Behoben / Tests

- **`MidiView` hinterließ Callbacks nach dem Schliessen:** Nachrichten-, Log- und MTC-Subscriber blieben beim jeweiligen Manager registriert und konnten in eine geschlossene Qt-View senden. Die View behält ihre Callbacks jetzt explizit, stoppt ihren Port-Refresh-Timer und meldet alle beim `closeEvent` ab. `MidiManager` kann Log-Subscriber gezielt entfernen und iteriert sie mutationssicher. `tests/test_midi_view.py` prüft den echten Qt-Monitor-/Toggle-Pfad mit isolierten MIDI-/MTC-Fakes sowie den vollständigen Teardown.
### 2026-07-10 — Audio-Editor: Editieren und wiederholtes Popout abgesichert (QA-10)

#### Tests

- `tests/test_audio_editor.py` baut den `AudioEditor` mit einer Minimal-`AudioFunction`, steuert Lautstärke, Loop und Name über echte Qt-Ereignisse und führt drei Popout-/Andock-Zyklen aus. Der Editor-Körper bleibt dabei vollständig bedienbar und wird zuverlässig zurückgedockt.
### 2026-07-10 — Carousel-Editor kann feste Eigenfarbe bewusst aktivieren (QA-10)

#### Behoben / Tests

- **Die `paint_color`-Option war im Carousel-Editor unsichtbar:** Die Engine unterstützt bewusstes Opt-in für eine feste Carousel-Farbe, damit Pulse/Wave/Chase standardmäßig die Programmer-/Look-Farbe nicht überschreiben. Der Editor bietet nun „Eigene Farbe ausgeben“ mit erklärendem Tooltip. `tests/test_carousel_editor.py` prüft die Option, Pattern, robuste Fixture-ID-Eingabe sowie drei Popout-/Andock-Zyklen.
### 2026-07-10 — Collection-Editor als UI-Workflow abgesichert (QA-10)

#### Tests

- `tests/test_collection_editor.py` baut den Editor gegen einen isolierten Function-Manager und prüft die zentrale Listenbearbeitung: beschriftete Minimal-Funktionen, Umbenennen, Umordnen, Entfernen und Play/Stop der Collection samt verbleibendem Member.
### 2026-07-10 — Effect-Layer-Editor verhindert widersprüchliche Clamp-Grenzen (QA-10)

#### Behoben / Tests

- **Clamp-Layer konnten `min > max` erhalten:** Der Editor akzeptierte beide Werte unabhängig und speicherte dadurch einen widersprüchlichen Bereich. Beim Überschreiten zieht er die jeweilige Gegen-Grenze nach; `tests/test_effect_layer_editor.py` prüft beide Richtungen sowie drei Popout-/Andock-Zyklen.
### 2026-07-10 — Scene-Editor-Minimalworkflow abgesichert (QA-10)

#### Tests

- `tests/test_scene_editor.py` baut den SceneEditor mit einer Minimal-Szene und leerem Patch, prüft Name, Timing, Leeren der Kanalwerte sowie drei Popout-/Andock-Zyklen.
### 2026-07-10 — Script-Editor-Minimalworkflow abgesichert (QA-10)

#### Tests

- `tests/test_script_editor.py` baut den ScriptEditor gegen einen isolierten Function-Manager, prüft Name-/Textbindung und Syntax-Highlighter sowie Run/Stop der Minimal-`ScriptFunction`.

### 2026-07-09 — Backlog-Arbeitswarteschlange und Roadmap bereinigt

#### Doku / Prozess

- **Der autonome Loop hat jetzt eine kanonische Arbeitswarteschlange:** `BACKLOG.md` trennt ausführbare Arbeit, notwendige Produktentscheidungen und externe Hardware-Blocker von den detaillierten Befundregistern. Veraltete Status wurden korrigiert (u. a. VIZ-PULL/#201, LAS-03, QA-16), die doppelte STAB-11-ID auf STAB-21 aufgelöst und QA-10 auf die tatsächlich noch acht ungetesteten Views präzisiert.
- **Die Roadmap spiegelt umgesetzte Funktionen:** Preset-Browser, Quick-Recording und sACN-Ausgabe sind als erledigt markiert; Hardware-Abnahmen bleiben im Backlog.

### 2026-07-09 — Audio-Input-Startfehler sichtbar (AUDIO-START-WARN)

#### Behoben / Geändert

- **Audio-Input-Tab scheitert nicht mehr still bei fehlendem/ungültigem Loopback-Gerät:** `AudioCapture.start()` setzt jetzt `last_error()` auch bei fehlendem `soundcard`-Backend oder fehlendem Default-Gerät, und `AudioInputView` zeigt diese Meldung direkt im Statuslabel. Stirbt der Capture-Thread erst nach einem zunächst erfolgreichen Start (z. B. Geräte-ID-Mismatch: „no device with id …"), bleibt der Tab nicht mehr stumm auf „Status: gestoppt", sondern zeigt den konkreten Capture-Fehler wie der BPM-Manager. Test: `tests/test_audio_input_view.py`.

### 2026-07-08 — OSC-Blackout & MTC-Frame robuster (OSC-04 + MTC-02, aus AUD-08)

#### Geaendert / Fixes

- **OSC `/lightos/blackout` invertiert nicht mehr bei String-Argumenten (OSC-04):** `val = bool(args[0])` machte aus einem String-Typetag „0"/„off" ein `True` (jeder nicht-leere String ist truthy) → Blackout **AN** statt AUS. Neu: `OscServer._as_on()` interpretiert typ-tolerant — numerische Args über die Schwelle `>= 0.5`, Strings gegen die Aus-Token `{"","0","off","false","no"}`. Getypte int/float von TouchOSC/Lemur (0/1) verhalten sich unverändert korrekt.
- **MTC feuert nur bei vollständigem Quarter-Frame-Satz (MTC-02):** `_handle_quarter_frame` feuerte bedingungslos bei `piece==7` → bei Mid-Stream-Attach oder einem verlorenen Piece wurde ein Frame aus **gemischten** alten+neuen Nibbles zusammengesetzt (kurz falscher Timecode). Neu: eine Bitmaske `_qf_seen` verfolgt die empfangenen Pieces; gefeuert wird nur, wenn alle 8 (`0xFF`) seit dem letzten Feuern kamen — ein unvollständiges Fenster wird verworfen, der nächste komplette 0..7-Satz feuert mit frischem Puffer.
- **Tests:** NEU `tests/test_osc_mtc_robustness.py` (8) — Blackout-Coercion für String-/typed-Args; MTC feuert nicht bei unvollständigem/lückenhaftem Satz, feuert genau einmal bei vollständigem (Sekunden korrekt dekodiert), erholt sich nach einem unvollständigen Fenster. Herkunft: AUD-08 (`docs/OSC_TIMECODE_AUDIT_2026_07_08.md`). MTC-01 (Frame-Wrap, Drop-Frame) + MTC-03 (Torn-Read) bleiben als dokumentierte P3.

### 2026-07-08 — OSC- & Timecode/MTC-Remote-Eingang-Audit (AUD-08)

#### Doku / Audit

- **Verifizierter Audit des OSC- und MTC-Eingangs** (`osc_server.py`, `mtc_reader.py`, beide 0 Tests): NEU [`docs/OSC_TIMECODE_AUDIT_2026_07_08.md`](docs/OSC_TIMECODE_AUDIT_2026_07_08.md). 4-Dimensionen-Workflow, jedes Finding adversarial verifiziert — **22 Agenten, 7 CONFIRMED**.
- **Positiv bestätigt (kein Bug, kein neuer P1/P2):** OSC-Handler robust gekapselt (int/float-Guards, geklemmt); Cross-Thread sauber (alle mutierten Ziele gelockt); MTC-Dekodierung spec-konform; MTC-Lifecycle sauber.
- **Die 2 P2 sind Parität** zu bekannten Web-Items: OSC-01 = **WEB-01** (`/lightos/ch` schreibt am 44-Hz-Renderer vorbei), OSC-02 = **NET-01** (`0.0.0.0:7770` ohne Auth) — beide dort als querschnittliche externe-Eingang-Themen vermerkt (gemeinsamer Fix, Produkt-Entscheidung).
- **Neu nur P3:** OSC-04 (`_handle_blackout` `bool()`-Inversion bei String-Args), MTC-01 (`+2`-Frame ohne Wrap), MTC-02 (Feuern ohne Vollständigkeitsprüfung), MTC-03 (Torn-Read, latent). Reine Doku-Änderung.

### 2026-07-08 — DMX-Eingang: RX-Thread erholt sich nach Netz-Blip (NET-06, aus AUD-06)

#### Geaendert / Fixes

- **Kein dauerhaft stummer DMX-Eingang mehr nach einem transienten Netzwerkfehler:** Starb der RX-`_loop` eines Receivers über einen `break` (transienter `OSError` aus `recvfrom` — Adapter-Reset, VPN-Toggle, Kabel raus/rein — oder ein unerwarteter Fehler), wurde `self._running` **nicht** zurückgesetzt. `is_running()` (das nur das Flag las) log daraufhin dauerhaft `True` → der UI-Auto-Restart-Guard `if not rx.is_running(): rx.start()` feuerte nie und `start()` no-oppte → der Eingang blieb **permanent stumm**, obwohl das Status-Label „Aktiv" zeigte (Erholung nur durch manuelles Ab-/Wieder-Anhaken). Jetzt setzen **beide** `break`-Pfade `self._running = False`, und `is_running()` prüft zusätzlich `self._thread.is_alive()` → nach einem Blip meldet der Receiver ehrlich „nicht laufend" und der UI-Guard startet ihn (inkl. Multicast-Re-Join) neu. Betrifft `artnet_input.py` **und** `sacn_input.py`.
- **Tests:** NEU `tests/test_dmx_input_rx_lifecycle.py` (6) — `is_running()` ist nur mit lebendem Thread True; der `_loop` setzt `_running=False` bei `OSError` und bei unerwartetem Fehler (beide Receiver). Herkunft: AUD-06 (`docs/DMX_INPUT_AUDIT_2026_07_08.md`).

### 2026-07-08 — DMX-Eingang: verlorene Quelle friert Kanäle nicht mehr ein (NET-05, aus AUD-06)

#### Geaendert / Fixes

- **Source-Timeout für Art-Net/sACN-Eingang:** Hörte eine externe Konsole auf zu senden (abgezogen/abgestürzt), blieben ihre zuletzt empfangenen Werte in `input_layer` und der 44-Hz-Renderer mischte sie **für immer** weiter → betroffene Kanäle hingen dauerhaft (bei HTP als Boden, bei REPLACE eingefroren) und ließen sich **nicht per Blackout** herunterziehen (der externe Eingang wird nicht vom Submaster/Blackout skaliert). `apply_input_merge` stempelt jetzt pro `out_univ` den Empfangszeitpunkt (`time.monotonic()`), und `_render_frame` (Schritt 4b-Input) verwirft Quellen, die länger als `INPUT_SOURCE_TIMEOUT_S` (2,5 s, E1.31 Network Data Loss) nichts mehr gesendet haben — der Kanal fällt dann auf Default/0 zurück. `clear_input_merge` räumt den Zeitstempel mit auf. `clear_input_merge` war bereits für genau diesen Zweck dokumentiert, wurde aber nie produktiv aufgerufen.
- **Tests:** `tests/test_input_layer.py` (2 neu) — eine backdatierte Quelle wird verworfen (Kanal fällt auf 0, Universe aus `input_layer` entfernt); eine frische Quelle bleibt. Herkunft: AUD-06 (`docs/DMX_INPUT_AUDIT_2026_07_08.md`).

### 2026-07-08 — DMX-Eingang- & RX-Thread-Audit (AUD-06)

#### Doku / Audit

- **Verifizierter Audit des DMX-Eingangs** (Art-Net/sACN-RX-Threads + Merge): NEU [`docs/DMX_INPUT_AUDIT_2026_07_08.md`](docs/DMX_INPUT_AUDIT_2026_07_08.md). 5-Dimensionen-Workflow, jedes Finding adversarial verifiziert — **15 Agenten, 5 CONFIRMED**.
- **Positiv bestätigt (kein Bug):** beide RX-Parser robust gegen manipulierte/zu kurze/lange Pakete (kein Crash/Thread-Tod); Lock-Disziplin sauber (RX liest GIL-atomar); Multicast-Join korrekt (die UI joint immer das konfigurierte In-Universe).
- **Echte Defekte** als Backlog-Items abgeleitet: **NET-05** (P1, kein Source-Timeout → verlorene externe Quelle friert Kanäle dauerhaft ein; Blackout greift dort nicht — sicherheitsrelevant), **NET-06** (P2, RX-Thread-Tod ohne `_running`-Reset → Eingang bleibt nach Netz-Blip stumm, `is_running()` lügt), **NET-07/08** (P3, Merge in nicht-konfiguriertes Universe / alte Merge-Config bleibt beim Umkonfigurieren). Reine Doku-Änderung.

### 2026-07-08 — Output-Typ-Wechsel & „Disabled" schließen den Alt-Adapter (OUT-05, aus AUD-03)

#### Geaendert / Fixes

- **Kein Phantom-/Doppel-Output mehr nach einem Output-Typ-Wechsel, „Disabled" schaltet ein Universe wirklich stumm:** `add_enttec/add_artnet/add_sacn` schrieben nur in ihre **eigene** Adapter-Registry; es gab **kein** Remove/Disable und `apply_output_config` keinen „Disabled"-Zweig. Wer ein Universe von ArtNet auf sACN umstellte, dessen alter ArtNet-Sender blieb offen → `_send_all` sendete dasselbe DMX über **beide** Adapter (und flutete das alte Ziel weiter); ein als „Disabled" markiertes Universe gab **weiter Licht** aus (nur per App-Neustart stoppbar); das Alt-Handle (Socket/Serial) wurde nie geschlossen (Leak). Neu: `OutputManager.remove_output(universe)` popt alle drei Registries unter `_io_lock` und schließt die Geräte (Muster wie `_swap_device`); `apply_output_config` ruft es **vor** dem Einrichten des neuen Typs → pro Universe genau ein (oder bei „Disabled" kein) aktiver Adapter.
- **Tests:** `tests/test_output_manager.py` (2 neu) — `remove_output` popt+schließt alle Adapter eines Universums (andere unberührt); Typ-Wechsel (ArtNet→sACN via remove+add) lässt genau einen Adapter zurück. Herkunft: AUD-03 (`docs/DMX_OUTPUT_AUDIT_2026_07_08.md`).

### 2026-07-08 — DMX-Output-/Netzwerk-Sender-Audit (AUD-03)

#### Doku / Audit

- **Verifizierter Audit des DMX-Output-Pfads** (ArtNet/sACN/Serial/OutputManager): NEU [`docs/DMX_OUTPUT_AUDIT_2026_07_08.md`](docs/DMX_OUTPUT_AUDIT_2026_07_08.md). 5-Dimensionen-Workflow, jedes Finding adversarial verifiziert — **19 Agenten, 6 CONFIRMED + 1 PLAUSIBLE**.
- **Positiv bestätigt (kein Bug):** Bytes beider Protokolle spec-konform; der 44-Hz-Output-Loop ist **doppelt** gegen Sende-Fehler abgesichert (kein Loop-Tod — Hypothese adversarial widerlegt); Lock-Disziplin robust; Universe→Wire-Abbildung korrekt.
- **Echte Defekte** als Backlog-Items abgeleitet: **OUT-05** (P2, kein Remove/Disable pro Universe → Typ-Wechsel/„Disabled" sendet weiter + Handle-Leak), **NET-04** (P3, kein explizites Egress-Interface/Broadcast-Default), **SERIAL-01/02** (P3, Port-Diagnose/Reconnect), **OUT-06** (P3, sACN-CID/Stream-Termination). Reine Doku-Änderung.

### 2026-07-08 — Show-Laden: Farbpaletten bleeden nicht mehr aus der Vorshow (STAB-19a, aus AUD-04)

#### Geaendert / Fixes

- **Paletten einer palettes-losen Show überschreiben nicht mehr still die vorherigen:** `load_show` lud den `palettes`-Block nur, wenn der Key vorhanden war (`if "palettes" in data`) — **ohne** `else`-Zweig. Beim Laden einer Show ohne `palettes`-Key blieben so die Farbpaletten der **vorigen** Show hängen (Bleed; `palettes` war der einzige Manager mit diesem Muster). Jetzt wird bei fehlendem Key `pm.from_dict({})` aufgerufen (wie in `reset_show`).
- **Tests:** `tests/test_show_file.py` (2 neu) — Show ohne palettes-Key → Paletten geleert; mit Key → genau diese geladen. Herkunft: AUD-04 (`docs/SHOW_FILE_AUDIT_2026_07_08.md`). Der reset-first/Rollback-Aspekt (STAB-19b) bleibt als P3 mit geringem Restrisiko dokumentiert offen (`load_show` setzt bereits alle State-Felder inline zurück).

### 2026-07-08 — Show-Laden: robuster gegen alte/korrupte `.lshow` (STAB-20, aus AUD-04)

#### Geaendert / Fixes

- **Non-Object-JSON liefert eine saubere Fehlermeldung** statt eines Absturzes: ein gültiges JSON, das kein Objekt ist (Liste/Zahl/String/`null` — korrupte oder fremde Datei), führte beim ersten `data.get(...)` zu einem ungefangenen `AttributeError`. `load_show` prüft jetzt `isinstance(data, dict)` und gibt sonst `(False, "…kein Objekt")` zurück.
- **Versions-Gate:** Ist die Datei-`version` **neuer** als das unterstützte Format (`SHOW_VERSION`), wird jetzt gewarnt und best-effort weitergeladen (statt die Datei still als aktuelles Format zu deuten). Robuste Tupel-Vergleich (`"1.10" > "1.2"`).
- **Legacy-EFX/RGB-Migration pro Eintrag isoliert:** Die einmalige Migration alter `efx`/`rgb_matrix`-Blöcke in Funktionen brach beim **ersten** kaputten Eintrag ab und verlor **alle folgenden**. Jetzt ist jeder Eintrag in ein eigenes `try/except` gekapselt — nur der kaputte fällt weg.
- **Tests:** `tests/test_show_file.py` (3 neu) — Non-Object-JSON → saubere Fehlermeldung; zu neue Version → lädt best-effort; kaputter Legacy-EFX-Eintrag → der gute danach wird weiter migriert. Herkunft: AUD-04 (`docs/SHOW_FILE_AUDIT_2026_07_08.md`).

### 2026-07-08 — Show-Laden: ein kaputter Wert löscht nicht mehr ganze Blöcke (STAB-18, aus AUD-04)

#### Geaendert / Fixes

- **Ein einzelner falsch-typisierter Wert verwirft nicht mehr den GESAMTEN programmer/base_levels-Block:** Beim Laden wandelten `{str(a): int(v) for …}`-Comprehensions die Werte um — ein einziger `None`/Listen-/nicht-numerischer Wert (z. B. aus hand-editierter oder alter `.lshow`) warf und der äußere `except` setzte `state.programmer = {}` bzw. `state.base_levels = {}` → **alle** Fixtures verloren (still). Jetzt ist `int(v)` **pro Wert** gekapselt (analog zur schon vorhandenen fid-/attrs-Isolation): nur der kaputte Wert fällt weg, der Rest bleibt.
- **Ein Render-Plan-Fehler verwirft nicht mehr die geladenen base_levels:** `state._rebuild_render_plan()` stand **innerhalb** des `base_levels`-`try` (nach der Zuweisung) → ein aus **unabhängigem** Grund werfender Rebuild landete im `except` und löschte die eben geladenen `base_levels` + kippte `implicit_brightness` auf True. Der Rebuild ist jetzt **aus dem `try` gezogen** (eigener, separat behandelter Aufruf).
- **Tests:** `tests/test_show_file.py` (3 neu) — kaputter Programmer-/base_levels-Wert lässt die guten Werte/Fixtures stehen; ein werfender `_rebuild_render_plan` lässt `base_levels`/`implicit_brightness` unangetastet. Herkunft: AUD-04 (`docs/SHOW_FILE_AUDIT_2026_07_08.md`).

### 2026-07-08 — Show-Speichern: atomar + kein stiller Funktions-Verlust (STAB-16/17, aus AUD-04)

#### Geaendert / Fixes

- **Speichern zerstört bei einem Fehler nicht mehr die vorhandene Show (STAB-16):** `save_show` öffnete bisher die Ziel-`.lshow` direkt (`zipfile.ZipFile(path,"w")` — truncatet sofort auf 0 Byte) und serialisierte `json.dumps` **erst danach** im offenen Handle. Ein Absturz, ein voller Datenträger oder ein Serialisierungsfehler hinterließ eine **korrupte** Datei und die vorherige Show war weg. Jetzt wird **zuerst serialisiert**, dann in eine **Temp-Datei im selben Verzeichnis** geschrieben und per **`os.replace()` atomar** über den Zielpfad gezogen; bei jedem Fehler bleibt die vorhandene Datei unangetastet und die Temp-Datei wird entfernt. `programmer`/`base_levels` werden zudem vor der Serialisierung unter `_prog_lock` defensiv gesnapshottet (kein „dict changed size" durch nebenläufiges Live-Editing).
- **Ein kaputter Effekt löscht nicht mehr still alle Funktionen (STAB-17):** Der `functions`-Block (in dem seit dem Programmer-Umbau auch **alle EFX-/RGB-Matrix-Instanzen** leben) wurde bei einem `to_dict()`-Fehler still auf `{"functions": []}` gesetzt und leer gespeichert → Totalverlust beim nächsten Laden. Der Fehler wird jetzt **nicht mehr geschluckt**: die Serialisierung darf abbrechen (dank STAB-16 bleibt die alte Datei dabei erhalten), statt eine leere Show zu schreiben.
- **Tests:** `tests/test_show_file.py` — Serialisierungsfehler lässt die vorhandene `.lshow` byte-identisch + ohne Temp-Leiche; normaler Save hinterlässt keine `.tmp`; `functions`-Block wird nicht still geleert. Herkunft: AUD-04 (`docs/SHOW_FILE_AUDIT_2026_07_08.md`).

### 2026-07-08 — Show-Datei-Persistenz-Audit `.lshow` (AUD-04)

#### Doku / Audit

- **Verifizierter Audit der `.lshow`-Persistenz** (`save_show`/`load_show`/`reset_show`, Datenverlust-Fokus): NEU [`docs/SHOW_FILE_AUDIT_2026_07_08.md`](docs/SHOW_FILE_AUDIT_2026_07_08.md). 5-Dimensionen-Workflow (Round-Trip · `_lenient`-Ganzblock-Verlust · Reset/Stale-State · Schema/Migration · Save-Integrität), jedes Finding adversarial verifiziert — **33 Agenten, 12 CONFIRMED, 2 zurückgewiesen → 9 distinkte Defekte**.
- **Positiv bestätigt (kein Bug):** der **Round-Trip ist vollständig** (alle 29 Keys + Feld-Ebenen symmetrisch, kein stiller Verlust), `reset_show` leert sauber; das „leer speichern bei to_dict-Fehler"-Muster ist bei `executors`/`tempo_buses` toter Defensiv-Code (kein erreichbarer Wurf).
- **Echte Defekte** als Backlog-Items abgeleitet: **STAB-16** (P1, nicht-atomarer Save korrumpiert die vorige Show), **STAB-17** (P1, `functions`-Block leer gespeichert bei `to_dict()`-Fehler → Totalverlust inkl. EFX/Matrix), **STAB-18** (P2, ein kaputter Wert löscht ganzen programmer/base_levels-Block), **STAB-19** (P2, `load_show` nicht reset-first/atomar + palettes-Bleed), **STAB-20** (P3, Robustheit gegen alt/korrupt). Reine Doku-Änderung.

### 2026-07-08 — Render-Thread: Engine-Extra-Roh-Kanal beim Repatch freigeben (STAB-14, aus AUD-02)

#### Geaendert / Fixes

- **Kein Roh-Kanal-Zombie mehr nach Patch-Change:** Schreibt eine `ScriptFunction` per `setdmx` einen **nicht gepatchten** Roh-Kanal, committet der Renderer ihn und merkt ihn in `_engine_extra_prev`, um ihn später (wenn das Skript stoppt) wieder auf 0 freizugeben. Ein Patch-Rebuild (`_rebuild_render_plan`, `app_state.py`) setzte dieses Tracking bisher **hart auf `{}`** — ohne die Live-Werte zu nullen. Stoppte das Skript danach, blieb `prev` leer, die `prev-cur`-Freigabe feuerte nie → der Roh-Kanal blieb **dauerhaft an** (bei Strobe/Shutter/Beam sicht- und sicherheitsrelevant). **Fix:** neuer Helfer `_release_engine_extra()` gibt die gemerkten Roh-Adressen im Live-Universe aktiv auf 0 frei, bevor das Tracking geleert wird (`list()`-Snapshot gegen den Render-Thread; `set_channel` per Universe-Lock thread-safe). Wird die Adresse jetzt gepatcht/weiter beschrieben, setzt der nächste Frame sie neu — höchstens 1 Frame Dip.
- **Tests:** `tests/test_render_frame.py::test_engine_extra_released_on_repatch` — Roh-Kanal committen → Repatch → Skript stoppt → Adresse wird auf 0 freigegeben (und bleibt es). Herkunft: AUD-02 (`docs/RENDER_AUDIT_2026_07_08.md`).


#### Geaendert / Fixes

- **Kein Dropped-Frame-Stutter mehr durch Feature-Dimmer:** Der Per-Frame-Renderer (Schritt 4b², `app_state.py`) iterierte `feature_dimmers` als **einzige** Ebene über die live `.values()`-View (ohne Lock-Snapshot, anders als Programmer/Simple-Desk/Input). Änderte ein UI-Thread währenddessen die dict-**Größe** (Slider-Slot anlegen/entfernen beim Schwellen-Crossing, `clear_feature_dimmers` beim Show-Load), warf CPython `RuntimeError: dictionary changed size during iteration` → der Block war nicht gekapselt, die Exception verwarf den ganzen Frame (Commit entfiel, alle Universen behielten den Vorframe) → sichtbarer Micro-Stutter. **Fix:** neuer `_fd_lock`; `set_feature_dimmer`/`clear_feature_dimmers` schreiben darunter, der Renderer zieht davor **einen** Snapshot (`list(feature_dimmers.values())`) — die Slot-Objekte sind unveränderlich, der Snapshot also stabil.
- **Tests:** `tests/test_feature_dimmer.py` — neuer `FeatureDimmerConcurrencyTest` (Writer-Thread oszilliert die Slot-Größe, 400 Render-Frames laufen fehlerfrei durch; + Positiv-Test, dass der Snapshot weiterhin korrekt dimmt). Herkunft: AUD-02 (`docs/RENDER_AUDIT_2026_07_08.md`).

### 2026-07-08 — Render-Pfad-Audit `_render_frame` (AUD-02)

#### Doku / Audit

- **Verifizierter Audit des heißesten Threads** (Per-Frame-Renderer, historische AV-Quelle STAB-07): NEU [`docs/RENDER_AUDIT_2026_07_08.md`](docs/RENDER_AUDIT_2026_07_08.md). 6-Dimensionen-Workflow (Concurrency/Lock · Exception-Isolation · Clamp/Overflow · Merge-Reihenfolge · Commit/Freigabe · Coverage), jedes Finding adversarial gegen den echten Code verifiziert — **36 Agenten, 6 CONFIRMED, 2 PLAUSIBLE, 7 zurückgewiesen**.
- **Positiv bestätigt (kein Bug):** Clamp lückenlos (`set_channel` zentral), kein Thread-Death (Callback-Isolation), Grand-Master/WP-6-Merge **by design** (2× adversarial widerlegt), und die Test-Coverage ist **breit** (≥8 dedizierte Suiten — die Backlog-Annahme „nur test_render_frame.py" war veraltet; fünf gemeldete „Lücken" waren bereits abgedeckt).
- **Echte Defekte** als Backlog-Items abgeleitet: **STAB-13** (P2, `feature_dimmers` ungelockt iteriert → Dropped-Frame), **STAB-14** (P2, Engine-Extra-Zombie beim Repatch), **STAB-15** (P3, nicht-atomarer Plan-Swap), **QA-25** (P3, kleine Coverage-Ergänzung). Reine Doku-Änderung.

### 2026-07-08 — Programmer-Leerzustand: eine Meldung mit Handlungsanweisung (UI-20)

#### Geaendert / Fixes

- **Kein doppeltes „Kein Gerät ausgewählt" mehr:** Im leeren Programmer stand derselbe Text 2× übereinander (Kopf-Label + je aktivem Attribut-Tab ein gleichlautender Platzhalter), ohne Hinweis, was zu tun ist. Der Kopf ist jetzt eine Status-/Handlungszeile („Kein Gerät ausgewählt — links ein Gerät oder eine Gruppe wählen"), der Tab-Platzhalter ein bewusst anders formulierter, beschreibender Hinweis („Attribute erscheinen hier, sobald ein Gerät gewählt ist."). Beide Texte liegen als Konstanten (`_EMPTY_SELECTION_MSG`/`_EMPTY_TAB_HINT`) vor, damit Init und Rebuild synchron bleiben.
- **Tests:** NEU `tests/test_programmer_empty_state.py` (2 Tests) — Kopf trägt die Handlungsanweisung, kein Tab-Platzhalter wiederholt den Kopf-Text wortgleich.
- Datei: `src/ui/views/programmer_view.py`. Herkunft: BACKLOG UI-20.

### 2026-07-08 — Web-Remote: robuster gegen fehlerhafte Requests + Tests (WEB-02/03/04/05, aus AUD-05)

#### Geaendert / Fixes

- **Kaputte Remote-Requests werfen keinen HTTP 500 / Handler-Crash mehr:** Die Web-Remote-Endpunkte konvertierten `level`/`value` aus dem JSON-Body ungeschützt per `float()`/`int()` — ein nicht-numerischer (oder `Infinity`/`NaN`) Wert erzeugte eine ungefangene Exception (WEB-02). Neuer Helfer `_num(...)` fängt das ab und nutzt den Default; verdrahtet in `api_fader`, `api_channel`, `on_fader`. Die SocketIO-Handler `on_fader`/`on_blackout` crashten zudem bei einem Emit **ohne** Payload (`data=None`) — jetzt `data=None`-Default + `data = data or {}` (WEB-03).
- **Nebenläufigkeit gehärtet:** `/api/go`, `/api/back` und die SocketIO-Pendants greifen die Cue-Stack-Liste über eine lokale Referenz statt `if …: …[0]` (kein TOCTOU-`IndexError`, wenn eine Show währenddessen geladen wird; WEB-04). `/api/status` iteriert die Cue-Stacks über eine Snapshot-Kopie (kein „changed size during iteration"; WEB-05).
- **Tests:** NEU `tests/test_web_app.py` (17 Tests) — der bislang komplett ungetestete externe Steuer-Eingang ist jetzt gegen Clamping, Bereichs-Guards, Payload-Fehlertoleranz und Routing abgesichert.
- Datei: `src/web/app.py`. Herkunft: AUD-05-Audit (`docs/WEB_REMOTE_AUDIT_2026_07_08.md`); die Security-Befunde NET-01/02/03 + WEB-01 bleiben als offene Items (brauchen Produkt-Entscheidungen).

### 2026-07-08 — Ausgabe: Art-Net/sACN „Übernehmen" zerschießt nicht mehr andere Universen (OUT-04)

#### Geaendert / Fixes

- **„Übernehmen" wirkt jetzt nur auf das gewählte Universum:** In der Ausgabe-Konfiguration überschrieben die Art-Net- und sACN-„Übernehmen"-Buttons bisher **alle** Universen — sie liefen in einer Schleife über `state.universes` und setzten für jedes den Adapter (live UND in `universes.json`). Wer z. B. einen Enttec auf Universe 1 und dann Art-Net auf Universe 2 einrichten wollte, dessen Enttec-Zuweisung (und jede andere) wurde beim Art-Net-„Übernehmen" mit überschrieben. Neu: Art-Net- und sACN-Tab haben je ein **„Universe:"-Feld** (wie der Enttec-Tab); `_apply_artnet`/`_apply_sacn` belegen nur dieses eine Universum (legen es bei Bedarf an), und `_persist_output` aktualisiert nur dessen Zeile in `universes.json` — bestehende Zuweisungen anderer Universen bleiben erhalten.
- Datei: `src/ui/widgets/output_config.py`; Test NEU `tests/test_output_config.py` (4 Tests: Art-Net/sACN nur ein Universum, deaktiviert = No-op, fehlendes Zieluniversum wird angelegt).

### 2026-07-08 — Tests: Multi-Universe-Output abgesichert (QA-07 + QA-08)

#### Tests / QA

- **Der zentrale Multi-Universe-Send-Pfad ist gegen Regression gesichert (QA-07):** neuer `tests/test_output_manager.py::TestOutputManagerMixedSend` patcht einen Fake-Enttec auf Universe 1 und einen Fake-Art-Net-Sender auf Universe 2, setzt unterschiedliche Kanalwerte und prüft nach einem `_send_all()`-Durchlauf, dass jeder Adapter **genau seine** Universe-Daten bekommt (keiner die fremden) und der Art-Net-Sender die erwartete externe Universe-Nummer (`univ_num - 1`) sieht. Nagelt das Routing in `output_manager._send_all` (Enttec/Art-Net/sACN je Universum) fest.
- **Die Start-Rekonstruktion aus `universes.json` ist abgesichert (QA-08):** `tests/test_output_manager.py::TestApplyOutputConfigRoundtrip` schreibt eine temporäre `universes.json` (Enttec/Art-Net/sACN auf U1/U2/U3) und prüft, dass `AppState.apply_output_config` jeden Adapter im **richtigen** Registry-Dict für sein Universum einrichtet (keine Kreuz-Einträge); ein zweiter Test belegt, dass ein Adapterfehler (Enttec ohne Port) den Loop **nicht abbricht** (die folgenden Adapter werden weiter eingerichtet). Deckt die zuvor ungetestete „Output kommt nach Neustart nicht"-Klasse ab.
- Kein Produktcode geändert (reine Regressions-Wächter).

### 2026-07-08 — Tests: Regressions-Wächter für VC-Widget-Drag (VC-WIDGET-DRAG)

#### Tests / QA

- **Kern-Drag-Interaktion der Virtual Console abgesichert:** Zum live gemeldeten (aber headless nicht reproduzierbaren) Effekt „VC-Widgets lassen sich im Bearbeiten-Modus nicht ziehen" nagelt ein neuer Guard-Test `tests/test_vc_widget_drag.py` das korrekte Verhalten fest — Fader, Button und SpeedDial (jeweils selbst-gezeichnet, im Edit-Modus an die Basis-`VCWidget`-Drag-Logik delegierend) verschieben sich per simuliertem Press+Move, **auch als Kind eines VCFrame**. Kein Produktcode geändert; der ursprünglich gemeldete Live-Effekt bleibt offen für eine Live-/Computer-Use-Repro (vermutlich szenario-spezifische Event-Zustellung im echten Fenster).

### 2026-07-08 — 3D-Panel: Zahlenfelder akzeptieren Punkt und Komma (VIZ-FIX-DECIMAL)

#### Geaendert / Fixes

- **Kein Dezimal-Datenverlust mehr in den 3D-Panels:** Die Zahlenfelder im 3D-Visualizer (Fixture „Position & Ausrichtung", Bühnen-Element-Größe/-Position, Raster) waren Standard-`QDoubleSpinBox` und damit an das System-Locale gebunden. Auf deutschem Locale erwartet die Spinbox das Komma als Dezimaltrenner; tippte man „5.7" mit Punkt, war die Eingabe ungültig und wurde verworfen bzw. geklemmt (stiller Verlust der Nachkommastellen). Neu: ein wiederverwendbares `LocaleTolerantDoubleSpinBox` (`src/ui/widgets/decimal_spinbox.py`) läuft intern auf C-Locale und normalisiert Komma→Punkt beim Validieren und Auslesen — beide Schreibweisen (`5.7` und `5,7`) werden korrekt übernommen. Alle 14 betroffenen Felder in `visualizer_window.py` sind umgestellt.
- Nebeneffekt: behebt den Dezimal-Aspekt der Stage-Größenfelder aus **VIZ-STAGE-PANEL** (Teilpunkt a); dessen übrige Punkte (ENTER-Commit, Panel-Sync, Resize-Toggle) bleiben offen.
- Dateien: `src/ui/widgets/decimal_spinbox.py` (NEU), `src/ui/visualizer/visualizer_window.py`; Test NEU `tests/test_decimal_spinbox.py` (5 Tests, deutsches Locale erzwungen, inkl. Regressionsbeleg gegen die Standard-Spinbox).

### 2026-07-08 — Live-View: Gerätezähler stimmt sofort beim Öffnen (UI-21)

#### Geaendert / Fixes

- **Kopfzeilen-Gerätezähler wird beim Bau initial gefüllt:** Der Zähler „N Geräte im Patch" oben in der Bühnen-/Live-Ansicht wurde ausschließlich über einen 500 ms-Timer (`_info_timer`) aktualisiert — `LiveView.__init__` rief `_refresh_info()` nie selbst. Öffnete man die Ansicht mit einer bereits gepatchten Show, zeigte die Kopfzeile bis zum ersten Timer-Tick „0 Geräte im Patch". Fix: `__init__` ruft `_refresh_info()` am Ende einmal aktiv auf (Initial-Pull) — der Zähler (und das Auswahl-Label) stimmen ab dem ersten Frame. Gleiche Bug-Klasse wie UI-05/UI-09 (fehlender Initial-Pull nach `__init__`).
- Datei: `src/ui/views/live_view.py`; Test NEU `tests/test_live_view_fixes.py::test_info_label_initial_pull`.

### 2026-07-08 — ShowBuilder: Skript-gepatchte Fixtures erben den fixture_type des Profils (VIZ-BUILDER-FIXTYPE)

#### Geaendert / Fixes

- **3D-Visualizer färbt/bewegt Skript-gebaute Shows jetzt korrekt:** `ShowBuilder.patch()` ließ `fixture_type` auf dem Model-Default `'other'` — der 3D-Visualizer (`registry.js`) fällt für `'other'` auf den PAR-Builder zurück und mappt DMX **nicht** auf Farbe/Pan/Tilt, sodass Effekte in per-Skript gebauten Shows die Geräte weder färbten noch bewegten. Fix: `patch()` liest über den neuen Helfer `_lookup_profile()` neben der Profil-ID auch den `fixture_type` des `FixtureProfile` und setzt ihn direkt beim Anlegen der `PatchedFixture`. Das spiegelt die bereits existierende `sync.py`-Auto-Fix-Semantik (generischer Typ → Profil-Typ übernehmen), nur schon beim Patchen statt erst bei einer Validierungs-/Sync-Runde.
- **Aufräumen:** Der dadurch redundante manuelle Nachzieh-Block in `tools/build_grosses_rig.py` (loopte nach `patch()` über alle Fixtures und setzte den Typ per `update_fixture`) wurde entfernt.
- Dateien: `src/core/show/showbuilder/builder.py`, `tools/build_grosses_rig.py`; Test NEU `tests/test_showbuilder.py::test_patch_inherits_fixture_type_from_profile` (querabgesichert gegen den echten Profil-Typ aus der Bibliothek, unabhängig von der Implementierung).

### 2026-07-08 — VC-Fader „Playback": dediziertes playback_slot-Feld statt function_id-Zweckentfremdung (DQ-2)

#### Geaendert / Fixes

- **Sauberere Datenhaltung für Playback-Fader:** Ein VC-Fader im Modus „Playback (Executor)" speicherte den Ziel-Executor-Slot bisher in `function_id` — demselben Feld, das alle anderen Modi als echte Funktions-ID nutzen (Zweckentfremdung). Jetzt gibt es ein dediziertes `playback_slot`: eine eigene Spinbox „Playback Executor-Slot" im Eigenschaften-Dialog (nur im Playback-Modus sichtbar, „nicht gesetzt" = leer) mit eigenem Persistenz-Schlüssel. Der `_apply()`-Pfad routet Playback jetzt über `playback_slot` — inkl. Guard `0 <= slot < len(executors)` gegen negative/zu große Slots (vorher nur obere Grenze).
- **Rückwärtskompatibel:** Alt-Shows, die den Slot noch in `function_id` (im Playback-Modus) hielten, migrieren beim Laden automatisch nach `playback_slot`, falls der neue Schlüssel fehlt. Nicht-Playback-Fader bleiben unberührt (keine Slot-Migration); ein explizit gesetztes `playback_slot` gewinnt immer.
- Datei: `src/ui/virtualconsole/vc_slider.py`; Test NEU `tests/test_vc_slider_playback_slot.py` (7 Tests: Roundtrip, Migration, Nicht-Playback-unberührt, explizit-gewinnt, Apply-Ziel korrekt, None-/Out-of-Range-Slot safe).
- _Hinweis: löst die geparkte Design-Entscheidung **DQ-2** zugunsten der sauberen Trennung auf (vorheriger Default war „nur dokumentieren"); trivial revertierbar._

### 2026-07-07 — Patch → Fixture-Gruppen (Grid-Editor): Auswahl bleibt stabil, Drop rastet ein (PATCH-GRP-01)

#### Geaendert / Fixes

- **Gewählte Gruppe springt nicht mehr zurück:** `_reload_group_list` setzte die aktive Gruppe bei jedem Neuaufbau hart auf die alphabetisch **erste** (`groups[0]`). Da jedes „Speichern" über `GROUP_CHANGED` genau dort landet und `+ Neu` ebenfalls neu lud, wechselte die Auswahl unbemerkt (z. B. von „Spiders" zurück auf „MovingHeads") — folgende Drags/Speichern trafen dann die **falsche** Gruppe und überschrieben sie. Fix: die gewählte Gruppe wird per **ID** erhalten (`select_gid`), `+ Neu` selektiert gezielt die **frisch angelegte** Gruppe. Damit bleibt die Auswahl über „+ Neu"/Drag/„Speichern" hinweg stabil.
- **Drag-Drop aufs Raster rastet ein statt still zu überschreiben:** ein externer Drop landet jetzt in einer **freien** Zelle — die Zielzelle unter dem Cursor, oder bei Belegung die per Distanz **nächste freie** (`place_fixture`/`_nearest_free_cell`), statt die vorhandene Belegung lautlos zu ersetzen. Randnahe Drops werden auf die Randzelle **geklemmt** (verpuffen nicht mehr). Ein grünes Live-**Ziel-Highlight** (`resolve_drop_cell`, identisch für Vorschau und echten Drop) zeigt beim Ziehen exakt, wohin es einrastet. Ein einzelner fehlender PAR lässt sich so ohne Überschreiben nachtragen.
- **Neuer Shortcut „Alle → Raster":** übernimmt alle gepatchten Fixtures in Patch-Reihenfolge ins Raster (freie Zellen zuerst, Reihen wachsen bei Bedarf; bereits platzierte bleiben) — „alle auswählen → in Gruppe übernehmen" mit einem Klick (danach „Speichern").
- Datei: `src/ui/views/fixture_group_view.py`; Test NEU `tests/test_fixture_group_grid_ux.py` (16 Tests: Zielfindung/Nearest-Free/Clamp/Full-Grid, Auswahl-Stabilität inkl. End-to-End-Save, „Alle → Raster").

### 2026-07-07 — Tests: Autosave-Recovery-Dialog blockte headless nicht mehr (QA-23)

#### Geaendert / Fixes

- **Grüne Test-Baseline wiederhergestellt:** Lag auf dem Rechner eine `%APPDATA%/LightOS/auto_save.lshow` neuer als alle zuletzt geöffneten Shows, öffnete der Wiederherstellungs-Check beim Start des Hauptfensters ein modales Dialogfeld — headless (offscreen) beantwortet das niemand, sodass die zwei Tests, die das Hauptfenster bauen, in den Timeout liefen (zustandsabhängiger Bruch, unabhängig vom eigentlichen Testinhalt). Fix: `main_window._recovery_prompt_suppressed()` (Env `LIGHTOS_NO_RECOVERY_PROMPT`, von `conftest.py` gesetzt, oder `QT_QPA_PLATFORM=offscreen`) unterdrückt den Prompt in Tests/Tools **vor jedem Dateizugriff** und plant den Start-Timer gar nicht erst. In der echten App ist beides nie aktiv → die Absturz-Wiederherstellung funktioniert unverändert. Neuer Regressionstest `tests/test_autosave_recovery_headless.py` nagelt beides fest (headless fragt nie; Live-Logik fragt genau einmal und stellt bei „Ja" wieder her); die echte Autosave-Datei des Nutzers wird von den Tests nie angefasst.
- Dateien: `src/ui/main_window.py`, `tests/conftest.py`; Test NEU `tests/test_autosave_recovery_headless.py`.

### 2026-07-07 — 3D-Visualizer: On-Demand-Rendering (VIZ-13 3c-2 — Phase 3 damit komplett)

#### Geaendert / Fixes

- **Der 3D-Visualizer rendert nur noch bei Änderung** statt bedingungslos ~60×/s: neues Modul `scene_src/scene/render_loop.js` mit `requestRender()`-Dirty-Flag und `hasLiveAnimation()`-Proben; die rAF-Kette läuft weiter (Absturz-Selbstheilung aus VIZ-10 bleibt), aber `renderer.render()` feuert nur bei Dirty oder aktiver Dauer-Animation (Stage-Selektions-Puls, FPS-Overlay). Bei statischer Szene fällt die Render-Last damit auf ~0 — passend zur Python-Seite, die seit VIZ-12 nur noch geänderte Fixtures pusht.
- **Alle Änderungsquellen verdrahtet** (an Wurzel-Flaschenhälsen: `updateCamera`/`resizeOrtho`, `updateOutlines`, `applyBrightness`, dmxBatch-Handler, Stage-CRUD/Resize, View-Mode, Settings, Drag-Zweige, Docking-Highlight, Resize/PixelRatio) inkl. Setter-Sicherheitsnetz; Verdrahtungs-Karte + dokumentierte fragile Deckungspfade (D1–D3) als Kommentarblock in `render_loop.js`.
- **Beweis-Test** `tests/test_viz13c2_ondemand.py` (11 Tests, echte Page offscreen): Idle rendert nicht, DMX/Kamera/Selektion/Brightness/Settings/Edit-Mode/Stage-Update/Transform/2D-Pan-Drag triggern sofort, Selektions-Puls hält den Loop live, `requestRender` koalesziert. 5 Trigger-Tests stammen aus der Parallel-Session „3D Visualizer placement/movement", die den Zwischenstand-Bug (3D-Editing kurzzeitig eingefroren, Schritt 2 vor Schritt 3) unabhängig diagnostiziert und den Fix verifiziert hat.
- Dateien (18, +714/−47): NEU `scene_src/scene/render_loop.js`; `app.js`, `bridge/bridge.js`, `state.js`, `camera/cameras.js`+`presets.js`, `fixtures/fixtures.js`, `interaction/pointer.js`+`tools.js`+`touch.js`+`gizmo.js`, `scene/renderer.js`+`lights.js`+`model_loader.js`, `stage/stage_objects.js`+`view_mode.js`+`docking.js`; Tests NEU `tests/test_viz13c2_ondemand.py`.

### 2026-07-06 — 3D-Visualizer: DMX-Update-Pfad in die FixtureType-Registry zerlegt (VIZ-13 3c Registry Teil 2)

#### Geaendert / Fixes

- **`updateFixture`-Monolith aufgelöst (reiner Refactor, verhaltens-identisch):** der ~190-Zeilen-DMX-Update-Pfad in `scene_src/fixtures/fixtures.js` ist in **pro-Typ-`updateDmx`-Handler der FixtureType-Registry** zerlegt — `updateSpiderDmx`/`updateParBarDmx`/`updateMoverBarDmx`/`updateMovingHeadDmx` (auch Scanner)/`updateGenericDmx` plus geteilte Helfer (`applyGenericColor`/`applyPanTilt`/`applyFloorAim`/`syncIconPos`) in `builders.js`. Alle 12 Registry-Einträge tragen jetzt `build` **und** `updateDmx`; unbekannte Typen fallen wie bisher auf den PAR-Pfad zurück. Die Fassade `updateFixture(fid, r, g, b, …)` und beide Aufrufer (dmxBatch-Handler, `addFixture`) bleiben unverändert.
- **Verhaltensgleichheit festgenagelt:** neuer Golden-Parity-Test `tests/test_viz13c_updatedmx_registry.py` (echte Page, offscreen QWebEngine) — 14-Fixture-Rig über alle Typen inkl. Multihead, Pixel-Bar und unbekanntem Fallback-Typ; Beam/Spot/FloorSpot/Lens/Lamp/Laser-Linien, Pan/Tilt-Rotationen, `_lastPanRad` und Icon-Färbung werden gegen die **vor dem Umbau eingefrorenen** Referenzwerte (`tests/test_viz13c_updatedmx_golden.json`) verglichen; gelöschte Golden-Datei friert nie still neu ein (Pflicht-Fail).
- Vorarbeit für 3c-2 (On-Demand-Render) und die restlichen Registry-Felder (`dispose`/`icon`); Design laut `docs/VIZ3D_OVERHAUL_PLAN.md` §e.
- Dateien: `scene_src/fixtures/builders.js` (+245), `fixtures/fixtures.js` (−210), `fixtures/registry.js`; Tests neu `tests/test_viz13c_updatedmx_registry.py` + `tests/test_viz13c_updatedmx_golden.json`.

### 2026-07-05 — 3D-Visualizer: 2D-Plan poliert (VIZ-13 3c-1 Ortho-2D-Polish)

#### Neu / Hinzugefuegt

- **2D-Icons überall klar sichtbar:** jede Icon-Form trägt jetzt eine permanente helle Umriss-Linie und unbelichtete Geräte füllen heller (vorher Dunkelgrau auf dunklem Boden = fast unsichtbar). Umrisse/Glyphen zeichnen zuverlässig über den durchscheinenden Bühnenflächen.
- **Eigene 2D-Symbole für PAR-Bar & Mover-Bar:** Balken mit N Einzel-Zellen (Mover-Bar zusätzlich mit Richtungs-Pfeil), die Zellen färben **pro Kopf** mit dem Live-DMX (Paritaet zu den FM-6-Symbolen der 2D-Live-View; vorher fielen beide auf den namenlosen Default-Kreis). Spider-Icon färbt seine zwei Bars einzeln; PAR bekommt einen Linsen-Ring. Zentrales `tintTopDownIcon()` ersetzt vier kopierte Farb-Blöcke.
- **Bühnen-Grundriss:** Boden/Plattformen/Trassen/Wände zeigen im 2D-Plan eine klare Footprint-Umriss-Linie in ihrer Typ-Farbe (folgt Position/Rotation live, vom Raycast ausgenommen — Picking/Docking bleiben präzise).

#### Geaendert / Fixes

- **Footer-Gesten-Hint folgt dem Modus:** im 2D-Plan stehen jetzt die 2D-Gesten (Schwenken/Zoom/Verschieben/Reset) statt dauerhaft des 3D-Texts.
- Selektionsring der Bar-Icons ist größer als die Bar (vorher komplett von der Form überdeckt) und vom Raycast ausgenommen (der unsichtbare Ring stahl Klicks neben dem Icon).
- Glyph-Linien rendern im Transparent-Pass — vorher übermalte der Body-Fill die Glyphen bei voller Intensität (vorbestehend, in der adversarialen Review gefunden).
- Icons übernehmen ihre Y-Rotation schon beim Erzeugen — längliche Icons (Bars/Spider) lagen nach dem Show-Reload quer, bis zur ersten Rotations-Geste (vorbestehend).
- `scene_src/three/three.js`-Wrapper exportiert zusätzlich `EdgesGeometry`/`LineLoop`.
- Dateien: `scene_src/fixtures/topdown_icons.js`, `fixtures/fixtures.js`, `stage/view_mode.js`, `stage/stage_objects.js`, `three/three.js`; Tests `tests/test_viz13c1_topdown_polish.py` (echte Page, offscreen QWebEngine).

### 2026-07-04 — Laser-Support: Werksmuster-Picker für DMX-Muster-Laser (LAS-18b)

#### Neu / Hinzugefuegt

- **Werksmuster als Kacheln:** neue Box „Werksmuster (Gerät)" in der Laser-Steuerseite (nur für reine DMX-Muster-Laser wie den Ehaho L2600, Klassen-Gate über `laser_capability`). „➕ Muster merken…" nimmt die aktuellen Bank-/Muster-Programmerwerte, fragt einen Namen und optional ein **Foto vom realen Laser-Output** (die Werksmuster sind herstellerseitig unbenannt — die Vorschau-Bibliothek baut sich der Nutzer selbst). Kacheln zeigen das Foto oder eine B/M-Nummer; Linksklick ruft das Muster ab (kopf-korrekt Gruppe A/B), Rechtsklick löscht den Slot. Show-persistent als additiver `.lshow`-Block. NEU `src/core/laser/pattern_slots.py`; `app_state.py`, `show_file.py`, `laser_view.py`; Tests `tests/test_laser_pattern_picker.py` + Show-Roundtrip.

### 2026-07-04 — Laser-Support: Zeichen-Studio komplett + L2600-Bedienung (LAS-11…LAS-19, Sammel-Eintrag)

#### Neu / Hinzugefuegt

- **Laser-Steuerseite aufgeräumt (LAS-11, PR #160):** Regler nach Bedeutung gruppiert (Muster/Farbe/Bewegung & Geschwindigkeit/Zeichnen + einklappbare „Weitere Kanäle"), Shutter nur noch als „Betriebsart"-Kacheln.
- **Fähigkeits-Klassifikator (LAS-12, PR #161):** `laser_capability()` entscheidet je Laser ehrlich, ob eine gemalte Figur exakt ausgebbar ist (Netz/ILDA) oder nur Werksmuster gehen (L2600) — eine Wahrheitsquelle für alle Laser-UIs.
- **Laser-Zeichen-Studio (LAS-13…LAS-17, PRs #162/#163/#166/#167/#171/#173):** Vollbild-Popout mit Ehrlichkeits-Banner, Formwerkzeuge (Kreis/Rechteck/Linie/Polygon/Stern) per Aufziehen mit Live-Vorschau, Freihand mit RDP-Glätten, Undo/Redo (Strg+Z/Y) + Raster-Einrasten, Figuren-Bibliothek mit Vorschau-Kacheln.
- **VC-Muster-Abruf (LAS-18, PR #169):** ButtonAction „Laser-Muster abrufen" ruft eine gespeicherte Laser-Palette auf Knopfdruck (Sicherheits-Härtung: nur die aufgenommenen Fixtures).
- **VC-Laser-Speed (PR #175):** der „Programmer-Attribut"-Fader mappt 0–100 % auf ein Wert-Teilband (z. B. `gobo_rotation` 192–223) — hält den L2600 im Dreh-Modus und regelt nur das Tempo.
- **Bild-Import → Vektor (LAS-19, PR #178):** „🖼️ Bild importieren…" im Studio vektorisiert ein Bild (Komponenten + Moore-Tracing + RDP) zur editierbaren Figur.

#### Geaendert / Verifiziert

- **L2600-Profil vollständig am Handbuch verifiziert (PRs #179/#181):** 34 Kanäle bestätigt (Herstellerseite „32ch" falsch), CH18-Semantik geklärt (Shutter-Default 0 korrekt), CH20 leer bestätigt, `laser_y`-Bewegungs-Labels ans Handbuch angeglichen.

### 2026-07-04 — Laser-Support: Sicherheit von der Virtual Console bedienbar (LAS-10)

#### Neu / Hinzugefuegt

- **Laser Scharfschalten + Not-Aus als VC-Buttons:** zwei neue Aktionen für Virtual-Console-Tasten (auch per MIDI-Pad auslösbar) — „Laser scharf/unscharf" (`LASER_ARM`, Toggle; Farbbalken lila wenn scharf) und „Laser NOT-AUS" (`LASER_ESTOP`, roter Balken). Der Not-Aus verriegelt, entwaffnet und öffnet die Session wieder (dieselbe sichere Reihenfolge wie in der Laser-Steuerseite). Damit lässt sich der Laser-Not-Aus auf eine feste, immer erreichbare Taste legen. Die Laser-Steuerseite spiegelt Scharf/Unscharf-Änderungen von der Konsole (`_sync_arm_from_manager`). `src/ui/virtualconsole/vc_button.py`, `src/ui/views/laser_view.py`, Tests `tests/test_laser_vc_safety.py`.

### 2026-07-04 — Laser-Support: Interaktiver Zeichen-Editor + Muster-Persistenz (LAS-07b)

#### Neu / Hinzugefuegt

- **Laser-Muster zeichnen:** neuer XY-Zeichen-Editor (`src/ui/widgets/laser_draw_editor.py`) — über den „✏️ Zeichnen…"-Knopf in der Laser-Steuerseite. Punkte per Klick setzen, ziehen zum Verschieben, aus einer 7-Farb-Palette einfärben, einzelne Punkte als „unsichtbaren Sprung" (Blank) markieren, offene Linie oder geschlossenes Polygon. Normierte −1..+1-Zeichenfläche (0,0 = Mitte, +y = oben) mit Live-Vorschau der Linien in Punktfarbe. **Beim Zeichnen wird das Muster live an scharf geschaltete Netzwerk-Laser gestreamt** — sichtbar nur, wenn der Laser über die Sicherheits-Sektion bewusst scharf ist (das Arming aus LAS-07a bleibt die alleinige Licht-Freigabe).
- **Gezeichnete Muster sind Show-persistent:** gespeicherte Figuren (`AppState.laser_figures`) landen in der `.lshow` (save/load/reset in `show_file.py`) und erscheinen mit ★ in der Ausgabe-Auswahl der Laser-Steuerseite — abrufbar wie die eingebauten Grundfiguren. Tests `tests/test_laser_draw_editor.py` + Show-Roundtrip in `test_show_file.py`.

### 2026-07-04 — Laser-Support: Zeichenmodus-Fundament — Arming-Safety + Figuren (LAS-07a)

#### Neu / Hinzugefuegt

- **Laser-Scharfschalten (Safety-Ebene):** Die Netzwerk-Laser-Ausgabe startet jetzt **unscharf** — solange nicht bewusst scharf geschaltet, wird jeder Streaming-Frame geblankt (Vorschau ohne Lichtaustritt). Umgesetzt im `LaserOutputManager` (`armed`/`set_armed`, im `_tick`-`dark`-Flag neben BLACKOUT und Not-Aus). In der Laser-Steuerseite gibt es dafür eine **Sicherheits-Sektion** (nur bei Netzwerk-Lasern): großer Scharf/Unscharf-Umschalter mit Warnfarbe, prominenter **Not-Aus-Button** (löst `estop_all` aus und schaltet zurück auf unscharf) und ein Warnhinweis. Ein Show-Load entwaffnet automatisch. `src/core/laser/laser_output.py`, `src/ui/views/laser_view.py`.
- **Laser-Zeichenfiguren (`LaserFigure`):** neues Modell `src/core/laser/figure.py` — eine benannte, normierte Punktliste (Position −1..+1, Farbe je Punkt, Blank-Segmente, offen/geschlossen) mit `to_frame`-Resampling (gleichmäßige Abtastung + Offset/Scale aus den Programmer-Werten), Serialisierung und eingebauten Startfiguren (Kreis/Dreieck/Quadrat/Linie). Der `LaserOutputManager` kann per `set_figure(fid, …)` eine Figur als Framequelle setzen (statt des Kreis-Testmusters); die Laser-Steuerseite bietet die Auswahl an. Grundlage für den interaktiven Zeichen-Canvas (LAS-07b). Tests `tests/test_laser_figure.py`.

### 2026-07-03 — Laser-Support: IDN-Stream-Backend (LAS-06)

#### Neu / Hinzugefuegt

- **IDN-Netzwerk-Laser (ILDA Digital Network):** zweites Punkt-Streaming-Backend neben Ether Dream, `src/core/laser/idn.py`. Voller IDN-Stream/-Hello-Treiber in reinem `struct`/`socket`-Python, Wire-Format gegen die offizielle ILDA-Spezifikation (IDN-Stream Rev001/Rev002) **und** die DexLogic-Referenzimplementierung (helios_openidn) verifiziert: UDP-Port 7255, 4-Byte-IDN-Hello-Header + Channel-Message-Header + Channel-Configuration mit dem Standard-Tag-Dictionary für X:16/Y:16/R:8/G:8/B:8 + Sample-Chunk, durchgehend Big-Endian; session-freies Streaming (Realtime-Channel-Message 0x40 mit hochzählender Sequence), Graceful Close (0x44) und Abort (0x46) als Not-Aus, optionale Geräte-Discovery per Scan (0x10/0x11). `IDNConnection` teilt die Connection-Schnittstelle mit Ether Dream, sodass der **`LaserOutputManager` beide Backends über eine Protokoll-Weiche** (`_factory_for`) bedient — Safety (BLACKOUT-Blanking, E-Stop, Backoff) und Framequelle bleiben backend-neutral. Der Patch-Dialog bietet Laser nun drei Protokolle (DMX / Ether Dream / **IDN**). v1: ein Frame = ein UDP-Paket; zu punktreiche Frames werden geometrie-erhaltend heruntergerechnet (App-Fragmentierung folgt mit dem Zeichenmodus). Tests `tests/test_laser_idn.py` (Wire-Format-Golden-Bytes, Fake-UDP-Empfänger, Manager-Protokoll-Weiche).

### 2026-07-03 — Laser-Support: Ether-Dream-Punkt-Streaming (LAS-05)

#### Neu / Hinzugefuegt

- **Netzwerk-Laser-Streaming (Ether Dream):** neues Paket `src/core/laser/` — `frame.py` (neutrales `LaserFrame`/`LaserPoint`-Modell + **Safety-Clamping** `clamp_frame`/`LaserLimits`: Scan-Ausschlag-, Punktraten- und Helligkeits-Limits, Mindest-Punktzahl gegen stehende Strahlen), `etherdream.py` (vollständiger Treiber für das offene Ether-Dream-Protokoll: TCP-Befehle prepare/begin/data/stop/**E-Stop/Clear**, UDP-Discovery, reine struct/socket-Implementierung, ohne Hardware testbar) und `laser_output.py` (`LaserOutputManager`: eigener 30-fps-Streaming-Thread getrennt von der 44-Hz-DMX-Pipeline; v1-Framequelle = Kreis-Testmuster aus den Programmer-Werten mit **Shutter-Gate**; **BLACKOUT blankt jeden Frame**, `estop_all()` verriegelt; Reconnect-Backoff je Gerät).
- **`PatchedFixture.net_host`** (IP/Hostname der DAC) mit Migration, `.lshow`-Serialisierung und Undo-Integration; **Protokoll-Auswahl im Patch-Dialog** für Laser (DMX ↔ Ether Dream): bei Netzwerk werden Universe/Adresse deaktiviert, das IP-Feld aktiviert und Adress-Konfliktwarnungen unterdrückt. Lifecycle: Start in `AppState.start_playback` (Env-Gate `LIGHTOS_NO_OUTPUT_THREAD`), Stop im MainWindow-Shutdown. Tests `tests/test_laser_etherdream.py` (Fake-DAC-Server, Clamping, Blackout/E-Stop/Backoff, net_host-Roundtrip).

### 2026-07-03 — Laser-Support: Pangolin-FB4-Profile (LAS-08-Teil 1)

#### Neu / Hinzugefuegt

- **Pangolin FB4 als Builtin-Fixture** (`PANGFB4`, Hersteller Pangolin, Typ laser): offizielles **16-Kanal-„FB3"-Profil** (Moduswahl auf Ch1, Seiten/Cues, Dimmer/Zoom/Größe/Position, Scan-Rate, Cue-Freigabe, Farbscrollen) und **39-Kanal-Profil** (Setup-Block Ch2-13 mit 16-bit-Paaren + Playback-Block Ch14-39 inkl. RGB-Override, Punkt-Trimming und Strobe) — Charts aus dem Pangolin-Wiki (`hardware:fb4:dmx16`/`dmx39`). Setup/Playback-Duplikate laufen als Mehrkopf (Kopf 1/2), Feinkanäle als `raw`. **Safety-Defaults:** Ch1 = Blackout/Safe, Dimmer = 0, kontinuierliche Z-Rotation = Stillstand. Damit sind Profi-Laser hinter FB4/QuickShow/BEYOND ab sofort über die bestehende DMX/Art-Net-Pipeline fernsteuerbar (inkl. Laser-Tab). Neues Kanal-Attribut `laser_scan_rate`. `src/core/database/fixture_db.py`, Vokabular-Dateien, Tests `tests/test_pangolin_fb4_profile.py`.

### 2026-07-03 — Stabilität: Repo-weiter GC-Teardown-Sweep über src/ui (STAB-10)

#### Behoben / Geändert

- **Owner-Zyklen gebrochen (native-AV-Klasse aus STAB-09):** starke Kind→Owner-Referenzen zykelten Top-Level-Views über Shibokens GC-sichtbare Parent→Kind-Wrapper-Kante — der Owner starb dann nur in der zyklischen GC (PySide6 6.11/Py 3.14: Access Violation beim GC-Teardown, faulthandler „Garbage-collecting"). Per weakref + Property + None-Guards gefixt: `EfxPopoutDialog._view` (+ alle internen Slots/Preview-Callback), `AttributeSlider._owner` (programmer_view), `_AspectRow._parent` (vc_drop_panel), `EfxView`-Preview-Geometrie-Callback sowie `status_cb` des RenderCrashGuard (visualizer_view/-window).
- **Lambda-Slot-Sweep (`src/ui/`):** self-fangende Lambda-Slots in langlebigen, nicht-modalen Widgets werden von der C++-Connection STARK und GC-unsichtbar gehalten (Wrapper-Pin → Leak + Use-after-free-Fenster). Repo-weit durch Bound-Method-Slots (bindet PySide6 schwach), sender()-Adapter bzw. die neuen Helfer `weak_slot`/`weak_slot_fwd` ersetzt (~90 Sites in 38 Dateien; `functools.partial` pinnt übrigens genauso — empirisch verifiziert). Bewusst unangetastet: transiente Kontextmenü-Lambdas (menu.exec), modale exec()-Dialoge und `self.destroyed`-Teardown-Slots (dort ist der Pin gewollt und funktional nötig).
- **Neu:** `src/ui/weak_slots.py` (Slot-Adapter mit weakref-Receiver, inkl. Fallback für Qt-Builtin-Methoden ohne `__func__`) + Regressionstests `tests/test_ui_teardown_gc.py` (Refcount-Tod von EfxView/Popout und AttributeSlider-Owner per gc.disable-Probe, None-Guards nach View-Tod, weak_slot-Semantik; der EfxView-Test crashte auf dem Stand VOR dem Preview-Callback-Fix nativ und beißt damit nachweislich).
- **Canary-Verifikation:** Die 6 unter dem weak-sync-Zwischenstand (#142, per #145 zurückgestellt) nativ crashenden Testdateien (Matrix-Views + Programmer-Editor) laufen mit dem Sweep zu 5/6 sogar auf dem weak-sync-Stand grün; `test_matrix_dirty_save` deckt eine verbleibende Zerstörungs-Fragilität der RgbMatrixView auf (unter dem aktuellen starken Bus nicht erreichbar) — dokumentiert als Blocker für das künftige sync-Re-Landing.

### 2026-07-02 — Laser-Support: Netzwerk-Laser-Grundlagen (LAS-04)

#### Neu / Hinzugefuegt

- **`PatchedFixture.protocol`** (`'dmx'` Default | `'etherdream'` | `'idn'`): Fundament für die zweite Laser-Klasse (Netzwerk-Laser ohne DMX-Adressraum). Idempotente ALTER-TABLE-Migration, `.lshow`-Serialisierung beidseitig (Alt-Shows laden als `'dmx'`), Undo-/`update_fixture`-Integration. Neuer Helper **`fixture_uses_dmx()`** gated ALLE vier Adress-Schreibstellen (`_rebuild_render_plan` Defaults/Spans/GM-Maske, `_flush_programmer_to_dmx`, `_apply_fixture_map`, Executor-`_flush_to_dmx`): Die Platzhalter-Adresse eines Netzwerk-Lasers kann nie in die DMX-Spans echter Geräte schreiben; seine Programmer-Werte bleiben erhalten und werden später vom `LaserOutputManager` (LAS-05) gelesen. `src/core/database/models.py`, `src/core/app_state.py`, `src/core/show/show_file.py`, `src/core/engine/executor.py`, Tests `tests/test_laser_protocol_field.py`.

### 2026-07-02 — Laser-Support: Laser-Tab im Programmer (LAS-02 + LAS-03-Grundlage)

#### Neu / Hinzugefuegt

- **Laser-Tab im Programmer (`LaserView`):** neue Steuerseite `src/ui/views/laser_view.py`, eingebettet als Programmer-Tab nach dem EFX/Matrix-Muster (`follow_selection=True`), sichtbar nur wenn die Auswahl Laser enthält (`fixture_type='laser'` oder `laser_*`-Kanäle). Inhalt: **Mustergruppe A/B/A+B**-Umschalter (Mehrkopf `attr#N`, Kopf-B-Schreibschutz für Einzel-Attribute nach ENG-03-Muster), **Modus-Schnellwahl** (Shutter-Ranges Aus/Auto/Sound/Muster als Kacheln), **Range-beschriftete Regler** je Laser-Kanal (Slider + Spin + Bereichs-Combo aus den ChannelRanges) und **Muster-Paletten**. `src/ui/views/programmer_view.py` (Tab + Sichtbarkeit in `_rebuild_attr_editor`), Tests `tests/test_laser_view.py`.
- **Laser-Muster-Paletten (`PaletteType.LASER`):** neuer Paletten-Typ in der Palette-Engine (erfasst `laser_*` + Shutter/Muster/Zoom/Rotation/Farbrad/Makro/Speed), eigener „Laser"-Tab in der Paletten-View, „💾 Muster speichern…" direkt in der LaserView (speichert pro Mustergruppe/Kopf). `src/core/engine/palette.py`, `src/ui/views/palette_view.py`.

### 2026-07-02 — Laser-Support: Ehaho-L2600-Builtin + Laser-Vokabular (LAS-01)

#### Neu / Hinzugefuegt

- **Ehaho L2600 („3D Partylight") als Builtin-Fixture:** Modi „6-Kanal (Simple DMX)" und „34-Kanal (Professional DMX)" mit allen Wertebereichen aus dem offiziellen Manual (ManualsLib #3494357; DMXControl-DDF als Gegenprobe). Im 34ch-Modus sind Mustergruppe A (Ch1-17) und B (Ch18-34) über die Mehrkopf-Konvention als Kopf 1/Kopf 2 getrennt steuerbar. **Laser-Safety-Default:** On/Off-Kanäle defaulten auf 0 (aus) — ein frisch gepatchter Laser feuert nicht. `src/core/database/fixture_db.py` (Seed + idempotentes `ensure_builtins`), Tests `tests/test_ehaho_l2600_profile.py`.
- **Laser-Attribut-Vokabular:** 13 neue Kanal-Attribute (`laser_boundary`, `laser_bank`, `laser_x/y`, `laser_zoom_x/y`, `laser_color`, `laser_color_change`, `laser_dots`, `laser_draw`, `laser_draw_mode`, `laser_twist`, `laser_grating`) in `CHANNEL_ATTRS`, exakt in `ATTR_GROUPS['Effect']` (Schutz vor Color-Substring-Fehlklassifikation → kein Feature-Dimmer auf Range-Select-Kanälen) und mit deutschen Labels. `src/ui/widgets/fixture_editor.py`, `src/core/attr_groups.py`.
- **Fixture-Klassen-Audit festgenagelt:** Test sichert, dass jedes Builtin eine echte Klasse trägt (nie `other`) und Schlüsselgeräte (PAR/Moving-Head/LED-Bar/Laser) korrekt klassifiziert sind.
- **Laser-Fahrplan:** `docs/LASER_PLAN.md` (L2600-Recherche, Netzwerk-Protokoll-Marktlage Ether Dream/IDN/Pangolin/ShowNET, Zwei-Klassen-Architektur DMX vs. Punkt-Streaming, Safety-Konzept) + Backlog-Epic LAS-01…LAS-09.

### 2026-07-01 — Live-Edit-Fenster + VC-Aufräumen (Davids VC-Umbau)

#### Neu / Hinzugefuegt

- **Live-Edit-Fenster (`VCMultiLiveEditor`):** ein frei schwebendes, größenveränderliches, **nicht in der Show gespeichertes** Fenster (Toolbar-Knopf „Live-Edit", auch im Live-Betrieb), in das man mehrere Effekte (Matrix / EFX-Bewegung / Chaser) per Drag&Drop zieht und mit Dropdown + „– / +" durchblättert. Pro Effekt: **Vorschau je Typ** (Matrix-Pixel / EFX-Bewegungspfad mit laufendem Punkt / Chaser-Schrittleiste), ein **Checkbox-Parameter-Editor** (anhaken → nur dafür erscheint ein Regler; live über `effect_live`, baseline-geschützt = flüchtig) und ein **Tempo-Modus** (Aus = freie Geschwindigkeit direkt, BPM = Master-Bus + Tempo-×-Faktor, Tap = eigener Takt pro Effekt auf festem Bus A–D). Alle Änderungen sind LIVE, aber **nicht persistent** (Show-Speichern schreibt die Preset-Werte). 4 PRs: [#119](https://github.com/ixamgames-droid/lightos/pull/119), [#120](https://github.com/ixamgames-droid/lightos/pull/120), [#121](https://github.com/ixamgames-droid/lightos/pull/121), [#122](https://github.com/ixamgames-droid/lightos/pull/122). Doku `docs/LIVE_EDIT_FENSTER.md`. `src/ui/virtualconsole/vc_multi_live_editor.py`.

#### Entfernt

- **Chase Builder (`VCChaseBuilder`):** das All-in-One-Chase-Widget komplett entfernt (Widget + Registry + Toolbar-Quick-Add + Inspector-Label + 10 Show-Generatoren + Doku). Alte Shows laden tolerant (unbekannter Widget-Typ wird beim Laden übersprungen). [#116](https://github.com/ixamgames-droid/lightos/pull/116)
- **Editor-Bausteine „⌗ Controller / 🎨 Color-Chase / 🟦 Chase-Bereich":** die drei edit-only Toolbar-Knöpfe oben rechts + ihre Handler und das Canvas-Aufzieh-Werkzeug (Rubber-Band/`area_selected`) entfernt; `controller_templates.py` auf das APC-Pad-Panel reduziert (Color-Chase-Baukasten gestrippt). [#118](https://github.com/ixamgames-droid/lightos/pull/118)

### 2026-06-30 — Neu

#### Neu / Hinzugefuegt

- **Feature-Dimmer-Master (F-26 + F-26b):** Ein effekt-**unabhängiger** per-Slot-Submaster, der die gewählte **Feature-Gruppe** (Intensity/Color/Gobo/Beam/Position/Effect) einer festen Fixture-Gruppe multiplikativ am fertig gerenderten Output skaliert (Render-Schritt 4b², NACH allen Effekten/Programmer). Mehrere Slots stapeln (Produkt) mit eigener Identität — anders als der flache `fixture_dimmers` („last writer wins"). **Backend** (`FeatureDimmer`-Dataclass, `AppState.feature_dimmers`, `set_feature_dimmer`/`clear_feature_dimmers`, Render 4b²) koordiniert von einem parallelen Branch übernommen. **VC-Bindung (F-26b):** neuer `SliderMode.FEATURE_DIMMER` (Fader-Modus „Feature-Dimmer (Gruppe)") mit Gruppen- + **Feature-ComboBox aus den Fixture-Capabilities** der gewählten Gruppe; Slot-Sync beim Properties-Dialog (enter/leave), Re-Apply beim Show-Laden (analog VCB-32), Slot-Räumung beim Löschen des Faders und `clear_feature_dimmers()` bei Show reset/load. +13 Backend- +9 VC-Tests (`tests/test_feature_dimmer.py`, `tests/test_feature_dimmer_vc.py`). `src/core/app_state.py`, `src/ui/virtualconsole/vc_slider.py`, `src/core/show/show_file.py`.

- **VC-Button: quadratische Standard-Größe (UI-13):** Neu hinzugefügte Buttons sind jetzt **quadratisch** (72×72, grid-aligned) statt länglich (120×60) — der Pad-Look, den der Demo-Show-Generator schon immer baut, ist damit die Standardgröße beim Hand-Platzieren. Bestehende Shows laden ihre eigene Geometrie und bleiben unverändert (nur die Neuanlage betroffen). `src/ui/virtualconsole/vc_button.py`.
- **VC-Button: Farb-/Effekt-Vorschau-Badge oben rechts (UI-13):** Ein Button mit gebundenem Farb-Effekt oder Farb-Snap zeigt jetzt — analog zum Gobo-Icon — oben rechts einen kleinen Farb-Kreis. Steuert der Effekt **mehrere Farben** (Farbwechsel), **wechselt das Eck-Icon zyklisch** durch die Farben (animiert, Timer nur aktiv solange das Widget sichtbar UND mehrfarbig ist → keine Off-Bank-CPU). Nicht-farbige Effekte (Dimmer-/Shutter-Style → `has_colors=False`) bekommen bewusst kein Badge. `src/ui/virtualconsole/vc_button.py`, `tests/test_vc_button_color_badge.py`.

#### Behoben

- **Show-Generatoren bauen den Patch wieder vollständig (DEMO-02):** Auf Windows re-importierte ein vom OutputManager via `multiprocessing`-`spawn` gestarteter Serial-Worker-Kindprozess das ungeschützte Generator-Skript als `__mp_main__` → der Build-Code lief ein zweites Mal, zwei Prozesse bauten auf derselben Show-DB, der FLD-FID-Guard wich aus → **nur ein Teil der Fixtures** landete im Patch (Symptom: `python -c` baut sauber, `python tools/build_x.py` nur teilweise). Neues Single-Point-Bootstrap `tools/_gen_env.py` setzt beim Import — vor `app_state`/`output_manager` — `LIGHTOS_SERIAL_INPROC=1` (kein Spawn, In-Prozess-Enttec) + `LIGHTOS_NO_OUTPUT_THREAD=1` + `LIGHTOS_NO_AUDIO_AUTOSTART=1` (wie die Test-conftest), `import _gen_env` in alle 30 bauenden `tools/build_*.py` ergänzt (`_builder`-basierte Generatoren über `tools/_builder.py` automatisch; `build_hardstyle_vc.py` ist per `__main__`-Guard schon sicher). `tools/_gen_env.py`, `tools/_builder.py`, `tools/build_*.py`, `tests/test_generator_spawn_safe.py`.
- **`reset_show()` räumt verwaiste Patch-Zeilen jetzt hart (DEMO-03):** Nach einem abgestürzten Generator-Lauf konnten Patch-Zeilen in `current_show.db` liegen bleiben; `reset_show()` (via `_replace_patch_from_data(state, [])`) löschte sie nicht garantiert hart — schlug das interne `clear_patch()` fehl, räumte der Fallback nur über den Cache auf, sodass verwaiste DB-Zeilen den FLD-FID-Guard auf `next_fid()` ausweichen ließen (überraschend verschobene fids). `reset_show()` ruft jetzt zusätzlich explizit `state.clear_patch()` (hartes `DELETE` der Patch-Tabelle), wie `load_show` es schon tut. `src/core/show/show_file.py`, `tests/test_reset_show_clear_patch.py`.
- **`ColorSequence` ist iterierbar/indexierbar (DEMO-05):** `for c in matrix.colors` / `list(matrix.colors)` / `matrix.colors[i]` warf `TypeError` (nur `len()`/`set_color` gingen) — erschwerte Tools/Debugging. Neue `__iter__`/`__getitem__` liefern die `(r,g,b)`-Tupel (rein additiv, kein bestehender Code verlässt sich auf „nicht iterierbar"). `src/core/engine/rgb_matrix.py`, `tests/test_color_sequence_iter.py`.
- **Bus-gekoppelte Matrix friert nicht mehr dunkel ein (DEMO-04):** Ein an einen Tempo-Bus gekoppelter Matrix-Effekt fror auf der (statischen) Bus-Position ein, wenn der Bus zwar eine BPM>0 hatte, seine Position aber nicht vorrückte — z. B. in Render-Pfaden **ohne** laufende `advance_frame`-Schleife (Effekt-Vorschauen, Capability-`render_probe`, Show-Validierung, Generatoren, Headless-Selbsttests) oder bei pausierter Bus-Uhr. Bei **Dimmer-Style** bedeutet „eingefroren" = Intensität 0 = **Fixtures dunkel**. `RgbMatrixInstance._advance_step` erkennt den stehenden Bus jetzt am Positions-Delta über einen echten Zeitschritt (`dt>0`, Position unverändert) und fällt auf **Free-Run** (`matrix_speed`) zurück statt einzufrieren; bei Bus-Wiederanlauf snappt der nächste Frame zurück auf Bus-Sync. Live (Render-Thread tickt jeden Frame) bleibt die Position in Bewegung → **byte-identisch**; `dt==0`-Re-Evaluationen (z. B. direkt nach „Jetzt synchronisieren") rechnen weiter sauber den Bus-Sync-Wert. Globaler Freeze (F5) hält bewusst weiter an. `src/core/engine/rgb_matrix.py`, `tests/test_demo04_bus_freerun.py`.
- **Weiß-Erkennung bei RGBW (UI-13):** Reines RGBW-Weiß (W-Kanal=255, RGB=0) wurde als **schwarzer Knopf** dargestellt, weil die Kachel-/Swatch-Farbe nur `color_r/g/b` las und den Weiß-Kanal ignorierte. Neuer zentraler Qt-freier Helfer `color_utils.rgbw_to_display`/`display_rgb_from_attrs` faltet den Weißanteil additiv zurück in die Anzeige-RGB → Weiß erscheint als Weiß (Snap-Swatch + neues Badge). Zusätzlich faltet die **VC-Farbkachel beim Senden an Effekt-Farb-Ziele** (`add_color`/`set_selected_color`/`color1..3`) den Weiß-Kanal ein — eine als RGBW-Weiß definierte Kachel landete sonst als Schwarz in der Color-Sequence (Wurzel von „weißer Effekt = schwarzer Knopf"). `src/core/color_utils.py`, `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_color.py`, `tests/test_vc_button_color_badge.py`.
- **GROUP_DIMMER/SUBMASTER-Fader beim Show-Laden wieder wirksam (VCB-32):** Die `apply_dict`-Direktzuweisung an `_value` umging den `@value.setter` (der `_apply()` ruft) — ein gespeicherter Gruppen-Dimmer/Submaster unter 100 % wurde beim Laden nicht angewendet (`fixture_dimmers` wird seit VCB-05 bei load/reset geleert), die Show kam **zu hell** hoch, bis der Nutzer den Fader bewegte. `apply_dict` ruft jetzt für GROUP_DIMMER/SUBMASTER nach dem Laden `_apply()` nach. Codex-Folgebefund auf [PR #100]. `src/ui/virtualconsole/vc_slider.py`, `tests/test_vc_codex_followups_101.py`.
- **`range_max=0` bleibt erhalten (VCB-33):** Ein bewusst auf `range_max=0` gesetzter Fader (Kappung/Stummschaltung; `_effective_value` erlaubt min==max) wurde vom `or 255`-Fallback als „fehlt" gewertet und beim Reload auf 255 gesetzt → Ausgabe statt Stille. Nur noch echtes `None`/Fehlen fällt auf 255 zurück. Codex-Folgebefund auf [PR #101]. `src/ui/virtualconsole/vc_slider.py`, `tests/test_vc_codex_followups_101.py`.
- **GROUP_DIMMER-Retarget lässt keine Geister-Gruppe zurück (VCB-34):** Wird ein Gruppen-Dimmer-Fader von Gruppe A auf B umgehängt (beide bleiben GROUP_DIMMER), blieb A weiter gedimmt — das VCB-19-`elif` traf den Retarget-Fall nicht. Die Slot-Synchronisierung nach dem Properties-Dialog wurde in `_post_dialog_mode_sync` ausgelagert (testbar) und setzt die alte Gruppe vor dem Anwenden der neuen zurück. Codex-Folgebefund auf [PR #101]. `src/ui/virtualconsole/vc_slider.py`, `tests/test_vc_codex_followups_101.py`.
- **Effekt-Farb-Badge im Aktiv-Effekt-Modus repaintet (UI-14c):** VCColor/VCEffectColors ohne feste `function_id` (Aktiv-Effekt-Modus) riefen `refresh_effect_badges(None)`, was am `int(None)`-Guard scheiterte → das UI-14b-Badge des gebundenen Buttons aktualisierte sich nach einem Live-Color-Edit nicht. `refresh_effect_badges` löst `None` jetzt zentral auf den aktiven Effekt auf (fixt VCColor **und** VCEffectColors). Codex-Folgebefund auf [PR #101]. `src/ui/virtualconsole/vc_canvas.py`, `tests/test_vc_codex_followups_101.py`.
- **Test-Gate: `create_all` idempotent gegen vorhandenes Schema (QA-06):** `test_vc_tempo_live_coupling` errorte (zuletzt deterministisch) im `reset_show`-Teardown mit `OperationalError: table manufacturers already exists`. `Base.metadata.create_all(checkfirst=True)` reflektiert vor jedem `CREATE` das `sqlite_master`; greifen zwei Verbindungen/Läufe auf dieselbe SQLite-Datei zu (neu aufgebaute Engine bei noch offener alter Verbindung, paralleler Lauf), liegt zwischen Reflexion und `CREATE` ein TOCTOU-Fenster, in dem der eigene `CREATE` mit „already exists" kollidiert. Neuer Helfer `create_all_idempotent` schluckt genau diesen harmlosen Fall (die Tabellen sind dann bereits da) und lässt jeden anderen `OperationalError` weiterfliegen; verdrahtet in `app_state.open_show`, `models.create_db` und `fixture_db.get_engine`. `src/core/database/models.py`, `src/core/app_state.py`, `src/core/database/fixture_db.py`, `tests/test_qa06_create_all_idempotent.py`.
- **XY-Pad: 8-bit-Ausgabe rundet statt abzuschneiden (VCB-11):** `VCXYPad._write_axis` schrieb im 8-bit-Pfad `int(frac*255)` (Abschneiden) → systematischer -0,5-LSB-Bias über den ganzen Pad-Bereich; jetzt `int(round(...))` wie der 16-bit-Pfad. `src/ui/virtualconsole/vc_xypad.py`.
- **Speed-Dial: BPM-Bereich wird persistiert (VCB-12):** `_min_bpm`/`_max_bpm` wurden weder in `to_dict` geschrieben noch in `apply_dict` gelesen → ein konfigurierter BPM-Bereich fiel beim Show-Reload still auf 20–600 zurück. Beide Felder werden jetzt serialisiert/deserialisiert. `src/ui/virtualconsole/vc_speedial.py`.
- **Speed-Dial: Live-Anzeige invert-korrekt (VCB-13):** Im `TEMPO_BUS_MULT`-Modus zeigte `_live_bpm_probe` `bus.bpm × _active_factor` (roh), während `_apply()` den invert-bewussten `_effective_mult()` als `tempo_multiplier` schreibt → bei aktivem Invert wich die angezeigte BPM vom tatsächlich geschriebenen Wert ab. Die Anzeige nutzt jetzt denselben `_effective_mult()` (ohne Invert unverändert). `src/ui/virtualconsole/vc_speedial.py`.
- **Stepper: Label zeigt per-Fixture-Wert (VCB-14):** `VCStepper._current_value` las den Parameter mit dem generischen `param_key` statt mit dem per-Fixture-Key (`_key_for(_fid())`, wie `step_by`/`_spec`) → bei Multi-Fixture-Bindungen mit eigenem Key je Effekt zeigte das Label den falschen Wert. `src/ui/virtualconsole/vc_stepper.py`.
- **Slider: kein Crash bei winziger Höhe (VCB-15):** `VCSlider.mouseMoveEvent` teilte durch `_track_rect().height()` (= Höhe − 40); ein auf ≤ 40 px geschrumpfter Fader führte beim Ziehen zu `ZeroDivisionError`. Jetzt mit `> 0`-Guard. `src/ui/virtualconsole/vc_slider.py`.
- **VC-Farbkachel: Live-Edit-Baseline für Effekt-Pfade (VCB-16):** `VCColor._apply` rief in den `EFFECT`/`EFFECT_ADD`/`color1..3`-Pfaden — anders als das symmetrische `VCEffectColors` — kein `effect_live.begin_live_edit()` → inkonsistenter Live-Edit-Zustand. Jetzt wird die Baseline vor jeder Mutation gesetzt. `src/ui/virtualconsole/vc_color.py`.
- **VC-Farbkachel: negative function_id abgelehnt (VCB-17):** Das Eingabefeld parste über `lstrip("-").isdigit()` → „-5" ging als gültige (negative) Bindung durch. Neuer Helfer `_parse_function_id` akzeptiert nur nicht-negative Ganzzahlen (leer/negativ → None), symmetrisch zu `VCEffectColors`. `src/ui/virtualconsole/vc_color.py`.
- **Slider-Effekt-Master: function_id nicht mehr verworfen (VCB-20):** `VCSlider._effect_targets`/`_autostart_targets` ignorierten das einzelne `function_id`, sobald `function_ids` gesetzt war (anders als `_all_target_fids()`, das beide vereint). Beide nutzen jetzt `_all_target_fids()` → die Einzel-Bindung geht nicht verloren. `src/ui/virtualconsole/vc_slider.py`.
- **MIDI-Teach: Sentinel statt None beim Entfernen (VCB-24):** `VCWidget._teach_midi` übergab beim Löschen einer Bindung `None` als `msg_type`; die Overrides räumen zwar am `data1<0`-Guard, aber ein None-`msg_type` ist eine stille Falle für künftige/`super()`-aufrufende Overrides. Jetzt Sentinel `"none"`. `src/ui/virtualconsole/vc_widget.py`.
- **Effekt-Param-Spec robust (VCB-25):** `effect_live._spec_for` fing eine Exception aus `fn.list_params()` nicht ab → konnte VC-Parametersteuerungen mitreißen. Jetzt `try/except` → `None`. `src/core/engine/effect_live.py`.
- **VC-Farbliste: Klick trifft den sichtbaren Swatch (VCB-26):** `VCColorList._hit_swatch` nutzte eine gleichförmige Float-Division, während `paintEvent` pro Swatch `int(round(x))` rundet → Klicks an Rändern trafen den Nachbar-Swatch. Der Hit-Test spiegelt jetzt exakt die gerundeten Paint-Grenzen. `src/ui/virtualconsole/vc_color_list.py`.
- **Speed-Dial: BPM robust deserialisiert (VCB-28):** `VCSpeedDial.apply_dict` wandelt `_bpm` jetzt defensiv nach `float` (ältere Shows konnten den Wert als String speichern → späterer `TypeError` in der Dial-Arithmetik). `src/ui/virtualconsole/vc_speedial.py`.
- **Live-Controls: Button-Reihe dynamisch positioniert (VCB-29):** `VCCanvas.add_live_controls` legte die Aktions-Buttons fix 200 px unter die Fader → Überlappung (hohe Fader) bzw. Leerraum (kleine Stepper, 72 px). Jetzt unter die tatsächliche Höhe der erzeugten Regler. `src/ui/virtualconsole/vc_canvas.py`.
- **Widget-Typ-Tausch: kein Phantom-Undo bei Fehlschlag (VCB-30):** `VCCanvas.replace_widget_type` pushte den Undo-Snapshot vor `_add_widget`; schlug das Anlegen fehl (`new is None`), blieb ein leerer Undo-Schritt zurück. Der Snapshot wird jetzt erst nach erfolgreichem `_add_widget` gepusht. `src/ui/virtualconsole/vc_canvas.py`.
- **VC-Button: kein stale snap_id beim Action-Wechsel (VCB-31):** `apply()` leerte beim Wechsel weg von `LIBRARY_SNAP` nur `snap_ids`, nicht `snap_id` → eine Phantom-Snap-ID wanderte in `to_dict` (Show-Korruption). Neuer Helfer `_snap_binding_for_action` leitet beide zentral aus der Aktion ab. `src/ui/virtualconsole/vc_button.py`.

#### Verbessert (VC-Audit)

- **Tempo-Toggle-Pads zeigen ihren Zustand (VCI-01):** `FREEZE`/`AUTO_SYNC`/`BPM_MODE_TOGGLE`-Buttons bekommen — wie `AUDIO_BPM` — einen Aktiv-Indikator (amber Rahmen + aufgehellter Hintergrund), abgeleitet aus `is_frozen()`/`auto_sync`/`mode==MANUAL`. `src/ui/virtualconsole/vc_button.py`.
- **Assign-Modus-Hinweise vervollständigt (VCI-02):** Der Canvas zeigt jetzt auch im **Funktions-** und **Bibliothek-Snap-Assign** einen Overlay-Hinweis („Klicke einen Button an…"), bisher nur bei MIDI-Learn/Snapshot. `src/ui/virtualconsole/vc_canvas.py`.
- **`normalize_color_target` meldet Unbekanntes (VCI-03):** ein nicht auflösbarer Ziel-String wird jetzt geloggt (statt still tote Kachel) und fällt sicher auf den Default-RGB-Pfad. `src/ui/virtualconsole/vc_color.py`.
- **Encoder `midi_mode` validiert (VCI-04):** ein korrupter/zukünftiger Wert fällt auf `RELATIVE` zurück statt undefiniertes Verhalten zu aktivieren. `src/ui/virtualconsole/vc_encoder.py`.
- **Slider: unbekannter Modus sichtbar (VCI-05):** `apply_dict` meldet einen unbekannten `mode` und fällt auf `LEVEL` zurück, statt ein wirkungsloses Widget zu erzeugen. `src/ui/virtualconsole/vc_slider.py`.
- **`mappable_param_choices` konsistent (VCI-06):** schließt `tempo_multiplier`/`phase_offset` aus (haben dedizierte Tempo-Controls), wie `control_options`. `src/ui/virtualconsole/vc_effect_meta.py`.
- **Toter Code entfernt (VCI-07):** das nie gelesene `VCButton._lp_fired` ist raus. `src/ui/virtualconsole/vc_button.py`.
- **`aspect_caption`: konsistenter Präfix-Check (VCI-08):** `in`-Prüfung nutzt denselben Token (`"Parameter: "`/`"Aktion: "`) wie der Split. `src/ui/virtualconsole/vc_effect_meta.py`.
- **VCColor-Swatch faltet Weiß (VCI-10):** `color()` faltet den W-Kanal additiv in die Anzeige-RGB → reines RGBW-Weiß erscheint im Picker/Swatch nicht mehr schwarz. `src/ui/virtualconsole/vc_color.py`.
- **Kommentar + Guard (VCI-11/VCI-12):** `VCCanvas.to_dict` erklärt das `FindDirectChildrenOnly` (kein Doppel-Serialisieren von Frame-Kindern); `VCWidget._notify_effect_highlight` prüft `_effect_ids_of` explizit per `hasattr`. `src/ui/virtualconsole/vc_canvas.py`, `src/ui/virtualconsole/vc_widget.py`.
- **`snap_ids` auch beim Speichern dedupliziert (VCI-14):** `VCButton.to_dict` entfernt Duplikate + die `snap_id` selbst, konsistent zum Lade-Pfad. `src/ui/virtualconsole/vc_button.py`.
- _Nicht umgesetzt:_ **VCI-09** (gegen den Code als False-Positive verifiziert — `set_param_normalized` hat keine Loop-Closure) und **VCI-13** (bewusst ausgelassen: `_result_for` ist Instanz-Methode mit vielen Test-/internen Callern; ein statischer Umbau wäre unverhältnismäßig riskant für eine vernachlässigbare Einsparung).

### 2026-06-29 — Neu

#### Neu / Hinzugefuegt

- **Cue-Verzögerung pro Attribut jetzt auch beim Ausfaden (ENG-01):** Cues hatten bereits eine Pro-Attribut-Verzögerung beim Hineinfaden (`attr_delays`); neu ist das symmetrische Gegenstück `attr_delays_out` für den Rückwärts-/Ausfade-Pfad (BACK). `CueStack._fade_to` wählt jetzt **richtungsabhängig** Fade-Zeit, Cue-Delay-Basis **und** die Pro-Attribut-Delays: GO nutzt `fade_in`/`delay_in`/`attr_delays`, BACK nutzt `fade_out`/`delay_out`/`attr_delays_out`. Die Attribut-Ebene ergänzt sich damit spiegelbildlich zu den schon vorhandenen Cue-Delays `delay_in`/`delay_out`. Nebenbei behoben: der BACK-Fade nahm bisher fälschlich `delay_in` (statt `delay_out`) als Verzögerungs-Basis. Alt-Shows ohne den neuen Schlüssel verhalten sich unverändert (defensive Deserialisierung). `src/core/engine/cue.py`, `src/core/engine/cue_stack.py`, `tests/test_cue_substack_and_attrdelay.py`.

### 2026-06-28 — Neu

#### Neu / Hinzugefuegt

- **Tempo standardmäßig taktgleich + direkt im Programmer:** Neue RGB-/Dimmer-Matrizen, EFX-Bewegungen, Chaser und Sequenzen folgen standardmäßig dem globalen Tempo-Bus; Auto-Sync ist bei neuen bzw. nicht ausdrücklich anders gespeicherten Shows aktiv. Matrix- und EFX-Programmer zeigen Tempo-Bus, Multiplikator und Phasenversatz direkt. Bewusste Abwahl bleibt über „Frei (nicht taktgebunden)" möglich.
- **Tempo-Bedienfeld jetzt auch im Chaser- und Sequence-Editor:** Beide Editoren bekommen — wie Matrix/EFX — **Tempo-Bus**, **Tempo-Multiplikator (×)** und **Phasenversatz** direkt im Editor. Damit lässt sich pro Chaser/Sequenz bewusst zwischen **beatgenau** (an einen Tempo-Bus gekoppelt) und **Free-Run** (zeitbasierter Crossfade zwischen den Schritten) umschalten. Default neuer Funktionen bleibt „Global". `src/ui/views/chaser_editor.py`, `src/ui/views/sequence_editor.py`, `tests/test_chaser_sequence_tempo_editor.py`.

#### Behoben

- **Speed-Dial „Jetzt synchronisieren" greift auch bei bus-gekoppelten Effekten:** `RgbMatrixInstance.sync_phase()` setzt die Animationsphase (`_step`) jetzt auch im Bus-Zweig auf 0 zurück — vorher übersprang der Bus-Re-Anchor das Reset, sodass bus-synchrone Effekte beim Sync nicht auf den gemeinsamen Startpunkt sprangen. `src/core/engine/rgb_matrix.py`, `tests/test_speed_dial.py`.
- **Chaser crossfadet wieder verlässlich im Free-Run:** Der Render-Probe-Diagnosehelfer (`render_probe.render_diff`) gibt den nur für die Probe gesetzten Tempo (`request_bpm(..., "diag")`) wieder frei, statt ihn in Folge-Tests/-Läufe leaken zu lassen; der Crossfade-Test ist zusätzlich explizit auf Free-Run gepinnt. `src/core/capability/render_probe.py`, `tests/test_chaser_crossfade.py`.
- **Capability-Manifest neu erzeugt:** `docs/capability_manifest.json` + `docs/CAPABILITIES.md` an die geänderte Tempo-Bus-Optionsreihenfolge angeglichen (`tools/gen_capabilities.py`).
- **Fixture-Kopieren überträgt `spider_dual_tilt`:** `_copy_fixture` kopiert das Dual-Tilt-Flag mit (ging beim Kopieren bisher verloren). `src/ui/views/patch_view.py`, `tests/test_patch_copy_offset.py`.

### 2026-06-25 — Neu

#### Neu / Hinzugefuegt

- **ADJ Dotz TPar System in der Fixture-Library:** Das komplette 4-fach RGB-COB-T-Bar-System ist als Builtin-Profil mit allen offiziellen DMX-Modi hinterlegt: **3, 5, 9, 12 und 18 Kanaele**. Die Pixel-Modi steuern alle vier PAR-Koepfe einzeln; Vollmodi enthalten zusaetzlich Farbmakros/Programme, Master-Dimmer/Programm-Speed, Strobe, Dimmerkurven und die zwei schaltbaren Zusatzlicht-Ausgaenge. Bestehende Fixture-Datenbanken werden durch `ensure_builtins()` idempotent nachgeruestet. `src/core/database/fixture_db.py`, `tests/test_adj_dotz_tpar_profile.py`.

- **ADJ Flat Par QWH12X in der Fixture-Library:** Der 12×5 W RGBW-PAR von ADJ (Art.-Nr. 1226100244) ist jetzt als Builtin-Profil hinterlegt. DMX-Layout faithful aus dem ADJ-Handbuch der baugleichen QA12X-Serie (gleiche Platine, Amber→Weiß) verifiziert. Modelliert sind die für die Software-Farbmischung nutzbaren Direkt-RGBW-Modi: **4-Kanal** (RGBW), **5-Kanal** (RGBW+Dimmer), **7-Kanal** (RGBW+Dimmer+Strobe+Farb-Makros) und **8-Kanal Voll** (zusätzlich Modus-Wahl + Programme). Strobe 0–15 = aus (Dauerlicht, kind `open`), 16–255 = langsam→schnell; 16 Farb-Makros als `color_wheel`-Slots → Farbrad-Kacheln im Programmer. Registriert in `_seed()` und `ensure_builtins()` (rüstet bestehende DBs idempotent nach). `src/core/database/fixture_db.py`, `tests/test_adj_flatpar_profile.py`.

#### Behoben

- **Solo-Frame schaltet wirklich auf genau einen aktiven Button um:** Der Container wertet nicht mehr nur den kurzzeitigen Tastendruck (`_pressed`) aus, sondern deaktiviert laufende Funktions-Toggles und aktive Bibliothek-Snaps gezielt. Beim Wechsel Rot → Grün wird Rot sofort beendet/zurückgenommen und nur Grün bleibt aktiv; ein erneuter Druck auf Grün schaltet es weiterhin aus. Gilt zentral für alle Shows, Banks sowie Maus-, MIDI- und Tastaturauslösung. Multi-Effekt-Buttons werden vollständig gestoppt. `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_frame.py`, `tests/test_vc_frame_solo.py`.

### 2026-06-24 — Neu

#### Neu / Hinzugefuegt

- **Dimmer-Sequenz für den Dimmer-Chase (ENG-08):** Ein Dimmer-Chase kann jetzt durch **explizite Dimmerwerte** (z. B. 255, 50, 100) schalten — pro Runde die nächste Stufe, genau wie die Color-Sequence pro Runde die Farbe wechselt. Neue Engine-Klasse `DimmerSequence` (Liste `[level 0–255, an/aus]`, `active_index`, `enabled_levels/next/prev/toggle/move`), eine Checkbox „Dimmer pro Runde wechseln" (`dimmer_cycle`) mit `dimmer_order` (normal/random/pingpong) + `dimmer_interval`, und ein neues Graustufen-Widget `DimmerSequenceField` (Popout, Eingabe 0–255) in der Farben-Gruppe — nur beim Dimmer-Chase sichtbar; bei aktiver Sequenz wird der feste Min/Max-Bereich ausgeblendet. Im Cycle-Modus werden die Stufen **direkt** auf den Dimmer geschrieben (kein Min/Max-Remap, kein Doppel-Dimmen); ohne Cycle bleibt exakt das alte Verhalten → abwärtskompatibel. Persistenz über `dimmer_sequence`/`dimmer_active`. `src/core/engine/rgb_matrix.py`, `src/core/engine/rgb_matrix_meta.py`, `src/ui/widgets/dimmer_sequence_editor.py`, `src/ui/views/rgb_matrix_view.py`, `tests/test_matrix_dimmer_sequence.py` (PR #60).

#### Geaendert

- **„Farbe pro Runde wechseln" in die Farben-Gruppe (UI-12):** Die `color_cycle`-Checkbox sitzt jetzt fest direkt beim Color-Sequence-Editor (statt ganz unten im dynamischen Param-Block „Bewegung & Parameter") und ist auf Farb-Styles (RGB/RGBW) gegated. Wirkt identisch im eingebetteten Tab und im „großen Fenster". `src/ui/views/rgb_matrix_view.py`, `tests/test_matrix_meta_view.py` (PR #60).

### 2026-06-23 — Neu

#### Neu / Hinzugefuegt

- **Preset-Browser: Paletten & Gruppen durchsuchen (UI-01):** Neuer Sub-Tab „Preset-Browser" in der Programmer-Sektion mit einem Suchfeld über **Paletten UND Fixture-Gruppen** zugleich. Live-Filter über Name, Typ (Color/Position/…), Ordner und Tags (mehrere Begriffe = UND, case-insensitiv); Doppelklick oder Enter wendet den Treffer an — eine Palette geht in den Programmer (aktuelle Auswahl, sonst alle Geräte), eine Gruppe wählt ihre Fixtures aus. Die Filterlogik liegt Qt-frei in `preset_search.py` und ist mit 14 Tests headless abgedeckt. `src/core/engine/preset_search.py`, `src/core/app_state.py` (`list_fixture_groups`), `src/ui/views/preset_browser_view.py`, `src/ui/main_window.py`, `tests/test_preset_browser.py`.

### 2026-06-22 — Fixes

#### Behoben

- **Dimmer-Matrix wirkt ohne Master-Hochziehen (ENG-02):** Treibt eine Funktion (Dimmer-Matrix/EFX) einen Intensitaets-/Dimmer-Kanal DIREKT, besitzt sie ihn jetzt wert-unabhaengig (Write-Log) — der per-Fixture Programmer-Intensity-Wert greift nicht mehr ein. Vorher wurde eine reine Dimmer-Matrix unsichtbar, sobald der Programmer (oft beim Auswaehlen auto-gesetzt) `intensity=0` hielt, und ein hochgezogener Master invertierte den Chase (gerade dunkle Pixel leuchteten voll). „Aktiver Tab gewinnt": nur wenn der **Intensity-Tab** aktiv UND die Lampe **selektiert** ist, gewinnt die manuelle Intensitaet absolut. Globaler Submaster/Grand-Master/Fixture-Dimmer bleiben echte Master; reine Farb-Effekte unveraendert (EE-02-Multiply dort erhalten). Bewusste Semantik-Aenderung: das alte EE-02 „Programmer-Dimmer multipliziert einen intensitaets-treibenden Effekt" entfaellt zugunsten der Tab-Regel. `src/core/app_state.py`, `src/ui/views/programmer_view.py`, `tests/test_matrix_dimmer_master.py`, `tests/test_dimmer_master.py` (PR #9).
- **EFX-Tab: „▶ Start" lief stumm ohne Geräte (UI-04):** Eine im Standalone-EFX-Tab neu angelegte Bewegung (z. B. Kreis/Circle) hatte keine Geräte zugewiesen; `EfxInstance.write()` bricht bei leerer Fixture-Liste sofort ab → **null DMX-Output, nichts im Simple Desk, keine Bewegung** (Symptom in „Test 1 2 3": Circle erzeugte keine Ausgabe). Neu: `_add_efx` befüllt eine frische Bewegung sofort mit Geräten (aktuelle Auswahl, sonst alle gepatchten Movingheads mit Pan+Tilt bzw. Dual-Tilt-Spider), und `_start_efx` weist vor dem Start sicherheitshalber nach; sind gar keine beweglichen Geräte gepatcht/ausgewählt, erscheint eine klare Warnung statt eines stummen No-Ops. `src/ui/views/efx_view.py`, `tests/test_efx_autoassign.py`.

### 2026-06-21 — Grosses Update: zentraler BPM-Leader & Tempo-Buses, BPM-Generator mit Beatgrid, geführte Virtuelle Konsole, Effekt-Sync & Multikopf, Capability-Validierung, neues Anleitungs-Kit

Dieses Update überarbeitet das Tempo/BPM-Subsystem von Grund auf (zentraler Leader, Tempo-Buses, Offline-Beatgrid-Analyse), baut die Virtuelle Konsole zu einem geführten Drag&Drop-Werkzeug mit Multi-Effekt-Steuerung aus und führt eine neue Capability-Ebene ein, die Shows vor stillen Lade-Fehlern schützt. Dazu kommen tiefgreifende Engine-Erweiterungen (Tempo-Sync, Layer-Priorität, Hüllkurven, Mehrkopf-Geräte), zahlreiche Robustheits- und Touch-Fixes sowie ein komplett neues bebildertes Anleitungs-Kit.

#### Neu / Hinzugefuegt

- **Zentraler BPM-Leader mit AUTO/MANUAL und Live-Monitor:** Der BPMManager ist jetzt ein zentraler Tempo-Leader mit klarer Quellen-Praezedenz — MANUAL (Tap/Nudge/Fader/Eingabe) und ein Lock blocken alles, im AUTO-Modus treibt der Audio-Detektor die BPM (OS2L/Datei nur als Fallback). Neuer Tab mit Live-Monitor (grosse BPM, Takt 1-2-3-4, Beat-Flash, Confidence, Spektrum, aktive Quelle) und Einstellungen. `src/core/engine/bpm_manager.py`, `src/ui/views/bpm_manager_view.py`, `src/core/audio/bpm_settings.py`.
- **BPM-Generator: ganzes Lied offline analysieren:** Neuer Generator-Tab analysiert komplette Dateien (MP3/M4A/FLAC/OGG/WAV via Qt-Decoder) zu einer zeitgestuetzten BPM-Kurve und einem phasen-genauen Beatgrid mit Downbeats. Auswaehlbare Engines (eingebaut/numpy, librosa, Beat This!) degradieren sauber, wenn nicht installiert; Ergebnis als BPM-Quelle nutzbar oder als JSON exportierbar. `src/ui/views/bpm_generator_view.py`, `src/core/audio/offline_timeline.py`, `src/core/audio/analysis_engines.py`.
- **Beatgrid-Editor mit Vorhoeren und Ordner-Stapelanalyse:** Das erkannte Grid laesst sich wie bei VirtualDJ/Serato korrigieren (½×/2×, Beats nudgen, Downbeat per Klick setzen); "Vorhoeren" spielt den Song mit Metronom-Klick auf jedem Beat. Eine Stapelanalyse verarbeitet ganze Ordner und legt die Ergebnisse im Cache ab. `src/ui/views/bpm_generator_view.py`, `src/core/audio/bpm_cache.py`.
- **Taktgenaue Beat-Wiedergabe aus dem Beatgrid:** Spielt der In-App-Player einen analysierten Track, feuert ein neuer Grid-Treiber (15-ms-Timer, Wall-Clock-interpoliert) taktgenaue Beats samt echten Downbeats; der globale Timer pausiert dann (genau eine Beat-Quelle). MANUAL/Lock und Live-Audio behalten Vorrang; per `phase_accurate_beats` abschaltbar. `src/core/audio/music_show.py`, `src/core/engine/bpm_manager.py`.
- **Genre-Presets fuer treffsichere BPM-Erkennung:** Pro Stil (House, Techno, Trance, Hardstyle, Frenchcore, DnB, Dubstep, Trap, Pop, Allgemein) ein Parametersatz aus Tempo-Fenster, Tempo-Prior, Empfindlichkeit, Glaettung und Taktart — behebt den haeufigsten Fehler (75 statt 150 BPM). Wirkt auf Live-Detektor und Offline-Generator. `src/core/audio/genre_presets.py`, `src/core/audio/offline_timeline.py`.
- **Tempo-Bus-System mit Master/Sub und Grand-Master:** Benannte, unabhaengige Tempo-Uhren liefern eine kontinuierliche Beat-Position (statt nur diskreter Beats), sodass Effekte phasenkohaerent koppeln (×2/×½). Default-Bus spiegelt den globalen Leader, feste Buses A/B/C/D fuer die VC, Master/Sub-Hierarchie, Grand-Master-Override mit eigenem Tap, Auto-Sync, Freeze-Toggle und Persistenz in der Show. `src/core/engine/tempo_bus.py`, `src/ui/views/bpm_manager_view.py`.
- **BPM aus eingebetteten Datei-Tags (ID3/MP4):** Neuer Tag-Reader (reines stdlib) liest die gespeicherte BPM aus ID3v2-TBPM bzw. iTunes-tmpo-Atom; in der Music View per Knopf "BPM aus Datei-Tags" nachziehbar und mit Etikett markiert. Greift nicht in den BPM-Manager ein. `src/core/audio/tag_reader.py`, `src/core/audio/media_player.py`, `src/ui/views/music_view.py`.
- **Per-Song-Auto-Show und Spektrum in der Music View:** Jedem Lied lassen sich Funktionen zuweisen, die beim Abspielen automatisch starten und bei Track-/Pause-Wechsel sauber getauscht werden (neue Spalte "Auto-Show"); die Now-Playing-Box zeigt ein 8-Band-Spektrum/VU. `src/ui/views/music_view.py`, `src/core/audio/music_show.py`, `src/ui/views/spectrum_bars.py`.
- **Konfigurierbares Takt-Raster:** Der BPMManager kennt nun `beats_per_bar` (1..64) mit Downbeat-/Bar-Events (`subscribe_bar`) und eine `subdivision` (1..16 Sub-Ticks pro Beat, opt-in `subscribe_tick`) fuer feinere Effekt-Aufloesung, plus Helfer `is_downbeat()`/`beat_phase_in_bar()`. `src/core/engine/bpm_manager.py`, `src/core/audio/bpm_settings.py`.
- **Tempo-Bus-Synchronisation fuer alle zeitbasierten Effekte:** EFX, RGB-Matrix, Chaser und Sequence koennen an einen gemeinsamen Bus (Global/A-D) gekoppelt werden und leiten ihre Phase/ihr Stepping aus der Bus-Position ab (`effect_pos = (bus.position - anchor) × tempo_multiplier + phase_offset`) statt aus dt zu akkumulieren — phasenkohaerent, mit freien Verhaeltnissen (×0.0625..16) und Beat-Versatz. "Sync" re-ankert eine sync_group, Freeze (F5) haelt die Position an. `src/core/engine/function.py`, `src/core/engine/efx.py`, `src/core/engine/rgb_matrix.py`, `src/core/engine/chaser.py`, `src/core/engine/sequence.py`.
- **Layer-Prioritaet beim Engine-Merge:** Funktionen haben ein neues Feld `priority` — hoehere Prioritaet tickt zuletzt und gewinnt bei Kanal-Ueberschneidung (LTP). Der FunctionManager sortiert stabil und erfasst geschriebene Kanaele ueber ein Write-Log (statt Wert-Diff), damit eine hoeher priorisierte Funktion auch mit identischem Rohwert gewinnt. Einstellbar im EFX- und Matrix-Editor. `src/core/engine/function.py`, `src/core/engine/function_manager.py`.
- **Ein-/Ausblend-Huellkurve (Fade) fuer Effekte:** Optionale `env_fade_in`/`env_fade_out` plus Kurvenform (`env_curve`: linear/scurve/ease/snap) wirken als Output-Multiplikator ueber ALLE Kanaele; beim Stoppen blendet die Funktion aus (release) statt hart zu stoppen, Blackout bleibt Sofort-Stopp. `src/core/engine/function.py`, `src/core/engine/function_manager.py`.
- **Neuer Matrix-Algorithmus "Schachbrett" (Checker):** Benachbarte Zellen abwechselnd Farbe A/B mit einstellbarer Kachelgroesse (`tile`) und optionalem Umschalten pro Beat (`blink`). `src/core/engine/rgb_matrix.py`, `src/core/engine/rgb_matrix_meta.py`.
- **Sequence-in-Sequence und Pro-Attribut-Verzoegerung in Cues:** Cues koennen ueber `sub_stack_ref`/`sub_stack_mode` eine andere Cueliste mitlaufen lassen (LTP-Merge, zyklensicher), und ueber `attr_delays` einzelne Attribute zusaetzlich zeitversetzt einfaden (`_blend_per_attr`). `src/core/engine/cue.py`, `src/core/engine/cue_stack.py`.
- **Neuer Snap-Editor:** Bibliotheks-Snaps lassen sich tabellarisch bearbeiten (aufgeloester Kanalname + DMX-Adresse, Werte 0..255 aendern, Eintraege entfernen, "Vorschau senden") ueber die neue SnapLibrary-API `set_snap_value`/`remove_snap_attr`/`set_snap_values`. `src/ui/views/snap_editor.py`, `src/core/engine/snap_library.py`.
- **Fade-Kurven-Bibliotheks-Ansicht:** Die show-weite Kurven-Bibliothek erhaelt eine eigene Verwaltung (Liste mit Vorschau, Neu/Bearbeiten/Duplizieren/Umbenennen/Loeschen); Presets sind schreibgeschuetzt, ein Edit legt eine User-Kurve an. `src/ui/views/curve_library_view.py`.
- **Geführter Smart-Drop in der VC statt stummem Toggle-Button:** Zieht man einen Effekt auf das Canvas, oeffnet eine Ankreuz-Karte (VCDropPanel) mit je einer Checkbox pro steuerbarem Aspekt (An/Aus, Tempo, Helligkeit, Farben, Bewegung, Tempo-Bus, Parameter, Aktionen). Mehrere Haken erzeugen mehrere vorverdrahtete Widgets in EINEM Undo-Schritt; die sinnvollen Aspekte leitet `vc_effect_meta` Qt-frei aus den Live-Faehigkeiten ab. `src/ui/virtualconsole/vc_drop_panel.py`, `src/ui/virtualconsole/vc_effect_meta.py`, `src/ui/virtualconsole/vc_canvas.py`.
- **Grafische Widget-Galerie und Widget-Typ-Tausch:** Wo mehrere Bedien-Elemente passen, zeigt eine Kachel-Galerie mit gemalter Vorschau (VCWidgetGallery) die Auswahl; ueber "↔ Widget ändern…" laesst sich der Typ eines vorhandenen Widgets bindungserhaltend tauschen (function_id(s), param_key(s), Caption, Position bleiben). `src/ui/virtualconsole/vc_widget_gallery.py`, `src/ui/virtualconsole/vc_widget.py`.
- **Undo/Redo fuer das Konsolen-Layout:** Hinzufuegen, Loeschen, Verschieben, Skalieren und Eigenschafts-Aenderungen von VC-Widgets sind rueckgaengig machbar (Snapshot-Verlauf, max. 50), mit Toolbar-Pfeilen und Strg+Z / Strg+Y / Strg+Umschalt+Z; Kit-Aufbauten zaehlen als ein Undo. `src/ui/virtualconsole/vc_canvas.py`, `src/ui/views/virtual_console_view.py`.
- **Doppelbelegungs-Schutz beim Drop auf belegte Regler:** Zieht man einen Effekt auf einen schon belegten Fader/Speed-Rad, erscheint eine Erklaer-Karte (VCConflictCard) mit drei Wegen: "Ersetzen", "Dazu koppeln" oder "Neues Widget daneben". `src/ui/virtualconsole/vc_conflict_card.py`, `src/ui/virtualconsole/vc_canvas.py`.
- **Multi-Effekt-Kopplung an einem Regler:** Fader, Speed-Rad, Encoder, Stepper und Buttons koennen mehrere Effekte gleichzeitig steuern (`function_ids`), je gekoppeltem Effekt mit eigenem Parameter (`param_keys_per_id`); eine nach Namen gefuehrte "Steuert"-Liste (TargetListEditor) ersetzt die rohen ID-Felder. `src/ui/virtualconsole/target_list_editor.py`, `src/ui/virtualconsole/vc_slider.py`, `src/ui/virtualconsole/vc_speedial.py`.
- **Effekt-Gruppen-Hervorhebung (oranger Glow):** Im Bearbeiten-Modus leuchten alle Widgets, die denselben Effekt steuern, gemeinsam in Amber auf — sichtbar "was beeinflusst diesen Effekt"; Container leuchten als Einheit, im Betrieb ist es aus. `src/ui/virtualconsole/vc_widget.py`, `src/ui/virtualconsole/vc_canvas.py`, `src/ui/virtualconsole/vc_frame.py`.
- **Neue VC-Bedien-Widgets — Stepper, Effekt-Farben, Effekt-Vorschau:** VCStepper (+/− fuer ganzzahlige Parameter wie Laeufer-Anzahl, mit relativem MIDI-CC), VCEffectColors (Swatch-Reihe der lebenden ColorSequence, Klick = Farbe waehlen, Rechtsklick = Slot an/aus) und VCEffectDisplay (Live-Pixel-Render des gebundenen Effekts). `src/ui/virtualconsole/vc_stepper.py`, `src/ui/virtualconsole/vc_effect_colors.py`, `src/ui/virtualconsole/vc_effect_display.py`.
- **Beweglicher Effekt-Editor-Container mit Live-Vorschau:** Beim Smart-Drop kann "Als Effekt-Box gruppieren" gewaehlt werden — alle erzeugten Regler landen in einer verschiebbaren VCEffectEditor-Box mit eingebetteter Vorschau und automatisch beschrifteten Reglern (Speed/Intensität/Size). `src/ui/virtualconsole/vc_effect_editor.py`, `src/ui/virtualconsole/vc_frame.py`.
- **VC-Tempo-Sync: Bus-Auswahl, BPM-Anzeige und Speed-Knoten:** VCBusSelector schaltet den aktiven Bus (A/B/C/D) scharf und zeigt die Bus-BPM, VCBpmDisplay zeigt globale oder Bus-BPM gross plus Quelle/Modus; das Speed-Rad ist ein vollwertiger Speed-Knoten mit QLC+-Paritaet (Master oder Sub mit Faktor ¼..×4, Sync/Downbeat, einstellbarem Erscheinungsbild). `src/ui/virtualconsole/vc_bus_selector.py`, `src/ui/virtualconsole/vc_bpm_display.py`, `src/ui/virtualconsole/vc_speedial.py`.
- **Neue Button- und Fader-Aktionen fuer Tempo und Show-Steuerung:** VCButton kennt BPM ±1 nudgen, AUTO/MANUAL umschalten, Tap/Sync/Arm pro Bus sowie globale Aktionen "Alles Weiß", "Freeze", "Effekte stoppen" und "Auto-Sync"; der BPM-Fader erzwingt beim Ziehen MANUAL, ein neuer Modus "Tempo-Bus (BPM)" steuert die BPM eines benannten Bus. `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_slider.py`.
- **Live-Mini-Editor und Pfad-Zeichnen:** Langes Druecken auf einen Effekt-Button im Live-Modus oeffnet einen kompakten Editor (VCLiveEditor) mit DEFERRED APPLY (Aenderungen wirken erst beim "Anwenden"); das XY-Feld hat einen "Pfad"-Modus, der eine live gezeichnete Bahn als Custom-EfxPath auf den Ziel-EFX legt. `src/ui/virtualconsole/vc_live_editor.py`, `src/ui/virtualconsole/vc_xypad.py`.
- **Capability-Validierung gegen stille Lade-Fehler:** Neue Ebene `src/core/capability/` reflektiert die wirklich existierenden Bausteine (Widget-Typen, Matrix-/EFX-Algorithmen, Param-Keys, Funktionstypen, Carousel-Pattern, Kurven) direkt aus dem Code und lintet ein show.json dagegen — jeder Punkt, den der tolerante Loader sonst verschluckt, wird als Finding mit difflib-Vorschlag und echter file:line laut. `assert_lshow` wirft vor `save_show`, `validate_show_live` prueft bindungsgenau gegen die laufende Engine. `src/core/capability/reflect.py`, `src/core/capability/validate.py`, `src/core/capability/render_probe.py`.
- **Strict-Modus fuer Show-Laden (LIGHTOS_STRICT):** Opt-in `src/core/strict.py` — mit gesetzter Umgebungsvariable re-raisen Loader und FunctionManager kaputte Subsysteme/Funktionen mit vollem Traceback statt sie still zu ueberspringen; standardmaessig aus. `src/core/strict.py`.
- **ShowBuilder-DSL: Shows per Skript bauen, die nur echte Bausteine nutzen koennen:** Neues Paket `src/core/show/showbuilder/` prueft jeden Algorithmus/Action/Param/Style/Fixture at call time gegen die reflektierten Capabilities und wirft bei Halluzination sofort BuildError (mit "meintest du"-Vorschlag); Funktions-Builder geben Handles zurueck, die man direkt an Widget-Builder uebergibt, sodass ein Widget nie an eine nicht-existente Funktion binden kann. `save()` validiert doppelt (statischer + Live-Lint). `src/core/show/showbuilder/builder.py`, `src/core/show/showbuilder/errors.py`.
- **Strikte Trennung Farbe/Dimmer als Show-Option (implicit_brightness):** Neues Flag (Default True) — True setzt eine aktive Farbe ohne getriebenen Dimmer automatisch auf voll (Alt-Verhalten), False haelt reine Farbe dunkel, Helligkeit kommt nur aus Dimmer-Effekten. Wird in `_render_frame` ausgewertet und mit der Show gespeichert. `src/core/app_state.py`, `src/core/show/show_file.py`.
- **Mehrkopf-Geraete (Spider) im Programmer einzeln ansteuerbar:** `set_programmer_value`/`get_programmer_value` akzeptieren jetzt `head>0` und adressieren ueber `attr#N` das N-te Vorkommen eines Attributs (z.B. die 2. Tilt-Bank eines Spiders); head=0 bleibt byte-genau, nicht gesetzte Koepfe spiegeln Kopf 0. `src/core/app_state.py`.
- **BPM-Sektion mit AUTO/MANUAL/Lock-Badge in der Top-Bar:** Neue Hauptsektion "BPM" (Tabs Manager + Generator); die Top-Bar zeigt ein klickbares Modus-Badge, Modus-/Quellenwechsel werden thread-sicher aus dem Audio-Thread in die UI marshallt, AUTO ist per `bpm_settings.boot()` standardmaessig an. `src/ui/main_window.py`, `src/core/midi/apc_mk2_feedback.py`.
- **DMX-Monitor zeigt Kanalfunktion:** Gepatchte Zellen toenen dezent in der Kanal-Funktionsfarbe und zeigen ein Geraete-Kuerzel + Kanal-Funktion (z.B. "PAR 1 R") plus Tooltip mit vollem Namen und aktuellem Wert. `src/ui/views/dmx_monitor_view.py`.
- **Quick-Rec und Kurven-Tab im Playback-View:** Ein "Quick-Rec"-Button nimmt dialogfrei sofort als neue Cue auf der aktuellen Cueliste auf (Auto-Nummer/-Label); die Playback-Sektion bekam zusaetzlich einen "Kurven"-Tab. `src/ui/views/playback_view.py`, `src/ui/main_window.py`.
- **Programmer: Gruppensuche und direkter Sprung in die Matrix-Ansicht:** Eine Such-/Filterleiste filtert die Gruppenliste nach Name/Ordner (flache Trefferliste), ein Gruppenklick springt direkt in den Matrix-Tab; dieselbe Suchleiste kam in den Paletten-Editor. `src/ui/views/programmer_view.py`, `src/ui/views/palette_view.py`.
- **Effekt-Assistent: neue Presets, Gruppen-Schnellauswahl und Farbverlaeufe:** Vier neue Presets (Wipe, Komet, Random-Strobe, VU-Meter), additive Gruppen-Buttons und optionale Farb-Zwischenstufen (N interpolierte Zwischenfarben) fuer sanfte Verlaeufe; die Mini-Vorschau passt ihr Raster an die echte Geraetegeometrie an. `src/ui/widgets/effect_wizard.py`, `src/ui/widgets/effect_mini_preview.py`.
- **Umbrechendes FlowLayout fuer Toolbars:** Neues `src/ui/widgets/flow_layout.py` — Widgets fliessen links nach rechts und brechen bei Platzmangel sauber um (statt Text-Abschneiden), u.a. fuer die VC-Toolbar bei 200%-Skalierung. `src/ui/widgets/flow_layout.py`.
- **Audio-Quellenwahl Loopback/Mikrofon:** AudioCapture unterstuetzt explizit "loopback" (PC-Wiedergabe) oder "input" (Mikro/Line-In) inkl. Liste echter Eingaenge; der Aufnahme-Loop gibt nach ~2 s durchgehender Fehler auf und meldet `last_error` statt stumm "laeuft" anzuzeigen. `src/core/audio/capture.py`, `src/ui/views/audio_input_view.py`.
- **Auskoppelbare Editoren in grosse, scrollbare Fenster:** Audio-Editor und ColorPicker lassen sich per "Grosses Fenster" in ein eigenes scrollbares Fenster auskoppeln und wieder andocken; jede Farb-Tab-Seite scrollt fuer sich, Zahlenfelder haben eine Mindestbreite (92px). `src/ui/views/audio_editor.py`, `src/ui/widgets/color_picker.py`.

#### Geaendert / Verbessert

- **Genau eine Beat-Quelle statt konkurrierender BPM-Writer:** OS2L, Media-Player und MusicShowDirector setzen die BPM nicht mehr direkt (`set_bpm`), sondern via `request_bpm()` mit Quellen-Kennung — der Leader entscheidet zentral nach Praezedenz; `_sync_emitter()` stellt unter Lock sicher, dass immer genau eine Beat-Quelle laeuft (Timer XOR Audio XOR Grid), der Timer-Thread prueft per Identitaet gegen Doppel-Beats. `src/core/engine/bpm_manager.py`, `src/core/audio/os2l.py`, `src/core/audio/media_player.py`.
- **Art-Net/sACN-Eingang als eigene Render-Schicht (F-20):** Die Empfaenger schreiben ihre gemergten Werte nicht mehr direkt ins Live-Universe (das ueberschrieb der Renderer auf gepatchten Kanaelen), sondern via `apply_input_merge` in einen eigenen Puffer; `_render_frame` mischt diesen pro Frame je Universe mit dem konfigurierten Modus (HTP/LTP/REPLACE), nach dem Dimmer-Master und vor Simple Desk. `src/core/app_state.py`, `src/core/dmx/artnet_input.py`, `src/core/dmx/sacn_input.py`.
- **Tempo-Buses mit der Show gespeichert und pro Frame fortgeschrieben:** `save_show`/`load_show`/`reset_show` sichern benannte Buses und den Grandmaster (Default-Bus nicht persistiert, alt-kompatibel); `_render_frame` schreibt die Buses einmal pro Frame (`advance_frame`) fort, bevor Funktionen rendern, sodass alle beat-synchronen Effekte im selben Frame dieselbe Bus-Position lesen. `src/core/show/show_file.py`, `src/core/app_state.py`.
- **Tolerantes Show-Laden mit optionalem Strict-Modus:** Alle strukturellen Schluck-Punkte laufen jetzt ueber `_lenient()` — standardmaessig tolerant, im Strict-Modus laut re-raised; eine einzelne kaputte Cueliste verwirft nicht mehr ALLE Cuelisten, die Show-DB ist per `LIGHTOS_SHOW_DB` umlenkbar. `src/core/show/show_file.py`, `src/core/app_state.py`.
- **RGBW-Matrix: echtes Weiss statt doppeltem Weissanteil:** Bei Style RGBW wird der Weissanteil `cw=min(r,g,b)` automatisch auf den W-Kanal gelegt und vom RGB-Anteil abgezogen — pures Weiss laeuft rein ueber den weissen Chip; der manuelle `white_amount`-Slider entfaellt. Carousel macht dieselbe Subtraktion (`adapt_color_payload`). `src/core/engine/rgb_matrix.py`, `src/core/engine/carousel.py`.
- **EFX: gegenphasiger 2. Kopf und Mehrkopf-Kanalverteilung:** Fixtures mit zwei Tilt-Kanaelen (Spider) schwenken den zweiten Kopf gegenphasig (`tilt#1 = 255-tilt`), sodass die Bars zu-/voneinander weg fahren; generell verteilt der EFX-Output Werte korrekt auf mehrfach vorhandene Attribute (`attr`, `attr#1`, `attr#2`). `src/core/engine/efx.py`.
- **QXF-Import deutlich genauer:** Der QLC+-Importer kennt viele weitere Channel-Presets (Fine als raw, CMY, HSV, CTO/CTB, Zoom/Focus/Iris-Richtungen, Speed-Varianten), vergibt jedem Capability-Bereich ein maschinenlesbares `kind` (open/closed/strobe/color/gobo/shake/rotate/reset), setzt sinnvolle Defaults (Pan/Tilt mittig 128, Shutter auf "offen") und ist ueber savepoint-basierte Nested-Transactions duplikat- und fehlerrobust. `src/core/database/qxf_import.py`, `src/core/database/fixture_db.py`.
- **Editoren gruppiert, scrollbar und auskoppelbar:** EFX-, Matrix-, Chaser-, Sequence-, Szenen-, Carousel- und Effekt-Layer-Editor wurden gegen das Platzproblem umgebaut — thematische QGroupBox-Gruppen in EINEM Scrollbereich plus Knopf "Grosses Fenster", der den ganzen Editor auskoppelt. `src/ui/views/rgb_matrix_view.py`, `src/ui/views/efx_view.py`, `src/ui/views/chaser_editor.py`, `src/ui/views/sequence_editor.py`.
- **Matrix-Editor: Folgemodus und Gruppen-Scope:** Beim ersten Wechsel auf den Matrix-Tab leitet sich das Grid sofort aus der aktiven Auswahl/Gruppe ab; die Auto-Zuweisung nutzt bevorzugt `active_scope_fids` und faellt nur ohne Auswahl auf den ganzen Patch zurueck. Beim CHASE-Algorithmus werden Laeufer-Anzahl/After-Fade nur bei `movement=normal` angezeigt. `src/ui/views/rgb_matrix_view.py`, `src/core/engine/rgb_matrix_meta.py`.
- **Sequence-Editor: Schritt-Name statt Roh-Werte:** Die Step-Tabelle zeigt den Step-Namen statt des Roh-Werte-Dumps (Werte im Tooltip und ueber einen "Werte..."-Dialog); der Chaser-Editor bekam einen Inline-Funktions-Picker, der die Selbstreferenz ausschliesst. `src/ui/views/sequence_editor.py`, `src/ui/views/chaser_editor.py`.
- **Color-Chase-Baukasten mit Zielgruppen-Auswahl:** Der Baukasten fragt die Ziel-Gruppe ab ("Alle Fixtures" oder eine Fixture-Gruppe) statt immer ueber alle gepatchten Fixtures zu laufen; die COLORFADE-Matrix wird explizit auf `MatrixStyle.RGB` gesetzt und traegt den Gruppennamen. `src/ui/views/virtual_console_view.py`.
- **Umbrechende VC-Toolbar und entdoppelte Bibliothek-Sidebar:** Die VC-Toolbar nutzt das FlowLayout und bricht bei schmalem Fenster um, mit neuen Schnell-Zugriff-Buttons (Effekt-Farben, Musik, BPM, Tempo-Bus); die Bibliothek-Sidebar unterdrueckt den doppelten Panel-Header. `src/ui/views/virtual_console_view.py`.
- **Snapshot speichern: nur aktive Auswahl und gewaehlte Attribut-Gruppen:** Der Snap-Speicherdialog beruecksichtigt jetzt einen Geraete-Scope (`active_scope_fids`), damit liegengebliebene Programmer-Werte zuvor gewaehlter Gruppen nicht mitgespeichert werden; der Quick-Snapshot fragt ebenfalls die Attribut-Gruppen ab. `src/ui/views/snap_file_panel.py`, `src/ui/main_window.py`.
- **Sub-Cuelisten-Aufloesung nach Show-Laden verdrahtet (F-16):** AppState bietet `_resolve_cue_stack` und `wire_cue_stack_resolvers`, die allen Cuelisten den Sub-Cuelisten-Resolver geben — aufgerufen in `new_cue_stack` und nach jedem `load_show`, sodass Verweise auch nach Reloads gueltig bleiben. `src/core/app_state.py`, `src/core/show/show_file.py`.
- **Visualizer: leere Buehne als einziger Start, nicht-modaler Farb-Picker:** Die fest verdrahteten Buehnen-Presets wurden entfernt — der Visualizer startet immer mit leerer Buehne; der Element-Farbdialog ist jetzt nicht-modal mit Live-Vorschau (Abbrechen stellt die Ausgangsfarbe wieder her). `src/ui/visualizer/stage_scene.html`, `src/ui/visualizer/visualizer_window.py`.
- **Function-Manager: hilfreiche Hinweise statt "Editor kommt bald":** Fuer EFX- und RGB-Matrix-Funktionen zeigt der Function-Manager jetzt konkret, wo sie zu bearbeiten sind (Programmer → Tab EFX bzw. Matrix); der generische Fallback bleibt nur fuer unbekannte Funktionstypen. `src/ui/views/function_manager_view.py`.
- **Stabilere Live-BPM-Erkennung:** Der BeatDetector liefert die BPM aufbereitet — rohe BPM via Median und Ausreisser-Verwerfung ueber ein kurzes Fenster, Oktav-Faltung in die Ziel-Range mit Kontinuitaet (kein Half/Double-Springen) und EMA-Glaettung; neu sind `set_bounds`/`set_smoothing`, eine Confidence-Schaetzung und ein Stille-Reset, der nach ~3 s ohne Beat den Lock verwirft. `src/core/audio/beat_detector.py`.
- **Touch-/Skalierungs-feste Buttons und durchgaengige Umlaut-Beschriftung:** Transport-Buttons und STOP ALL/BLACKOUT nutzen Mindestbreiten statt Festbreiten; Tab-Namen wurden geschaerft und durchgaengig ASCII-Ersatzschreibungen in echte Umlaute korrigiert. `src/ui/views/show_manager_view.py`, `src/ui/main_window.py`, `src/core/sync.py`, `src/core/stage/stage_definition.py`.
- **APC Mini Feedback vereinfacht:** Der nie sinnvoll genutzte `exclude_note`/`include_note`-Mechanismus wurde aus dem Feedback-Loop entfernt; Executor-/Seiten-LEDs werden jetzt unbedingt gesetzt, was eingefrorene LED-Zustaende vermeidet. `src/core/midi/apc_mini_feedback.py`.

#### Behoben

- **Crash beim Laden/Zuruecksetzen von Shows mit Patch (BUG-01):** Beim Bulk-Ersatz des Patches feuerte jedes `clear_patch()`/`add_fixture()` synchron ein `patch_changed`-Event, woraufhin Views re-entrant im inkonsistenten Zustand refreshten und ueber `QListWidget.clear()` eine Access Violation ausloesten. AppState hat jetzt ein `_suppress_emits`-Flag und macht nach dem Umbau EINEN gebuendelten Refresh. `src/core/app_state.py`, `src/core/show/show_file.py`, Test `tests/test_show_file.py`.
- **U-King Spider: zwei separate Tilt-Motoren statt Pan/Tilt:** Das 14-Kanal-Layout (CH1/CH2) ist auf zwei separate Tilt-Motoren (Bar links = Kopf 0, Bar rechts = Kopf 1) umgestellt, da die zwei Lichtleisten getrennt schwenken; aeltere Datenbanken werden ueber die neue `_SPIDER14_SIGNATURE` beim Start in-place migriert (Tippfehler "Großer Straler" → "Großer Strahler" korrigiert). `src/core/database/fixture_db.py`, Test `tests/test_spider_profile.py`.
- **Attribut-Gruppen-Klassifikation aus einer Quelle (Strobe-Fehlbeschriftung, Bug E):** Die Attribut-zu-Gruppe-Zuordnung liegt jetzt zentral in `src/core/attr_groups.py` und wird von Programmer-Tabs und Speichern-Dialog gemeinsam genutzt — vorher fuehrten zwei abweichende Maps dazu, dass ein im Intensity-Tab geschobener Strobe-Kanal beim Speichern faelschlich als "Beam" beschriftet wurde. `src/core/attr_groups.py`, `src/ui/views/programmer_view.py`.
- **EFX-View: Zombie-Sync-Subscriber beseitigt:** Die View abonniert Sync-Events jetzt ueber `subscribe_widget` statt `subscribe`, sodass sich die Handler beim Zerstoeren automatisch abmelden — vorher sammelten sich bei jedem Programmer-Rebuild Zombie-Subscriber an, was jede `FUNCTION_CHANGED`-Aktualisierung mit der Zeit verlangsamte. `src/ui/views/efx_view.py`.
- **Cue-Laden robuster und Draft-Roundtrip erhaelt Basisfelder:** `Cue.from_dict` liest `values`/`attr_delays` defensiv (kaputte Eintraege werden uebersprungen statt die ganze Cuelisten-Sektion zu verlieren); `RgbMatrix.apply_dict` erhaelt nun `priority` und die Huellkurven-Zeiten, die sonst beim Draft-Roundtrip verloren gingen. `src/core/engine/cue.py`, `src/core/engine/rgb_matrix.py`, `src/core/engine/function_manager.py`.
- **VC: robusteres Laden und Migration alter Farb-Ziele:** Beim Laden bricht ein einzelnes defektes Widget nicht mehr das Laden der restlichen Konsole ab (uebersprungen und protokolliert); alte ASCII-geschriebene ColorTarget-Werte (z.B. "hinzufuegen") werden per ASCII-Faltung auf den kanonischen Wert gemappt, sonst fiele die Farb-Kachel still auf den Default zurueck. `src/ui/virtualconsole/vc_canvas.py`, `src/ui/virtualconsole/vc_color.py`.
- **VC: Frame-Delete-Ownership und uebersichtlicher Farb-Dialog:** In einen VCFrame gelegte Widgets gehoeren nun der Box (`delete_requested` korrekt verdrahtet, Entfernen ist undobar) — vorher blieben sie an der Canvas haengen; der Eigenschaften-Dialog des Farb-Widgets gruppiert die vielen Zeilen in einem Scrollbereich und unterstuetzt Mehrkopf-Geraete. `src/ui/virtualconsole/vc_frame.py`, `src/ui/virtualconsole/vc_color.py`.
- **Doppelbelegungs-Fix am Speed-Dial:** Der Konflikt-Schutz behebt nebenbei einen latenten Bug am Speed-Rad, dessen Kopplungs-Rueckgabewert frueher ignoriert wurde. `src/ui/virtualconsole/vc_canvas.py`.
- **Beat-Indikator Off-by-one behoben:** Der manuelle BPM-Dialog nutzt jetzt `set_manual_bpm`/`reset` statt `set_bpm`, und der Beat-Indikator nimmt den Beat-Index direkt aus dem Callback (frueherer Off-by-one im Takt-1-Akzent behoben). `src/ui/main_window.py`.
- **Programmer: Attribut-Tabs scrollen vollstaendig:** Der gesamte Tab-Inhalt (Schnellwahl, Auto-Bar, Position-Tool, Slider) liegt jetzt in einem gemeinsamen aeusseren Scrollbereich — vorher konnten Schnellwahl/Auto-Bar unter `--touch` abgeschnitten werden. `src/ui/views/programmer_view.py`.
- **Touch-Layout-Korrekturen in Auto-Farbwechsel und Geraete-Gruppen:** In der ColorWheelAutoBar liegen Hardware-Rotation und Software-Simulation in eigenen beschrifteten Gruppen mit gestapelten Von/Bis-Combos (QFormLayout); in den Kanal-/Fixture-Gruppen-Views ersetzt eine Mindestbreite plus kompakteres Stylesheet die feste 60px-Apply-Button-Breite. `src/ui/widgets/preset_tile.py`, `src/ui/views/channel_groups_view.py`, `src/ui/views/fixture_group_view.py`.

#### Tests & Werkzeuge

- **Test-Isolation in conftest.py gehaertet:** Tests laufen jetzt gegen eine separate Wegwerf-Show-DB (`LIGHTOS_SHOW_DB` im Temp-Verzeichnis), der Audio-BPM-Autostart ist unterdrueckt (`LIGHTOS_NO_AUDIO_AUTOSTART`), und nach jedem Test werden MIDI-Threads, der globale BPM-Beat-Timer, geleakter Qt-Fokus und offene modale Dialoge abgeraeumt — das beseitigt sporadische native Access-Violations und Hotkey-Flakies. `tests/conftest.py`.
- **CLI-Linter und Manifest-Generator fuer Shows:** `tools/lint_show.py` prueft eine oder mehrere .lshow/show.json gegen die echten Bauteil-Saetze (Glob, `--strict`, Exit-Code 1, CI-tauglich); `tools/gen_capabilities.py` erzeugt `docs/CAPABILITIES.md` + `docs/capability_manifest.json`, ein Diff-Test erzwingt die Uebereinstimmung mit dem reflektierten Code. `tools/lint_show.py`, `tools/gen_capabilities.py`, Tests `tests/test_show_lint.py`, `tests/test_capability_manifest.py`, `tests/test_capability_live.py`.
- **Gemeinsames Build-Boilerplate und Verifikations-Werkzeuge:** `tools/_builder.py` kapselt den Boilerplate der `build_*`-Skripte hinter der ShowBuilder-DSL plus `build_and_verify()` (statischer + Live-Lint, optionaler Render-Smoke); `tools/verify_color_dimmer_separation.py` und `tools/benchmark_universes.py` belegen die Farbe/Dimmer-Trennung bzw. messen die `_render_frame`-Zeit ueber 8/16/32 Universen. `tools/_builder.py`, `tools/verify_color_dimmer_separation.py`, `tools/benchmark_universes.py`, Tests `tests/test_strict_dimmer_render.py`, `tests/test_benchmark_universes.py`.
- **Grossflaechiger Ausbau der Testabdeckung (rund 75 neue Testdateien):** Neue Suiten ueber alle Subsysteme — Tempo/BPM (Beatgrid, Leader, Bus, Grandmaster, Persistenz, Timeline), Virtuelle Konsole (XY-Pad/MIDI, Speed-Node, Effekt-Editor, Undo/Redo, Drop-Panel, Conflict/Swap), Matrix-RGBW-Weiss, Mehrkopf-Spider, ShowBuilder-DSL, Show-Lint, strikter Loader, gruppen-gescopter Save, Offline-BPM-Analyse und APC-Mini-Feedback. `tests/test_showbuilder.py`, `tests/test_tempo_bus.py`, `tests/test_multihead_spider.py`, `tests/test_offline_analysis.py`, `tests/test_carousel_color.py`, `tests/test_implicit_intensity.py`.
- **Bestehende Tests an API-/UI-Aenderungen angeglichen:** `test_matrix_meta_view` prueft jetzt das Auskoppeln/Andocken des ganzen Editors, `test_chaser_live_build` nutzt einen Subset-Check, damit neue Tempo-Bus-Params den Test nicht brechen, und das Spider-Profil-Test prueft zwei eigenstaendige Tilt-Kanaele. `tests/test_matrix_meta_view.py`, `tests/test_chaser_live_build.py`, `tests/test_spider_profile.py`.

#### Dokumentation & Anleitungen

- **Neues bebildertes Anleitungs-Kit (Hardstyle-Show + Event-Demo 2026):** Umfangreiche deutsche, bebilderte Tutorials entlang zweier roter Faeden mit ~20 Themenordnern (Patchen & Gruppen, Farb-/Dimmer-Matrix, Farbchase, EFX, Moving Heads, Spider, Virtuelle Konsole, APC-Mapping, Musik-Sync, Speed-Dial); die README verlinkt das Kit prominent als Einstieg. `docs/ANLEITUNGEN.md`, `docs/ANLEITUNGEN_EVENT_DEMO.md`, `docs/anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md`, `README.md`.
- **Kern-Anleitungen auf die umgebaute Oberflaeche umgeschrieben:** `docs/ANLEITUNG.md` spiegelt die neue UI (8 Hauptsektionen statt 7; EFX/Matrix/Funktionen/Paletten in den Programmer gewandert, "Patchen" nur noch Patch + Fixture-Gruppen); `docs/EFFEKTE.md` aktualisiert Matrix-/EFX-Effekte und Helper-Tab und konsolidiert die RGB-Matrix-Liste auf 18 Algorithmen. `docs/ANLEITUNG.md`, `docs/EFFEKTE.md`.
- **Neue BPM-/Tempo-Dokumentation:** `docs/EFFEKTE.md` (Abschnitt 9) und `docs/ANLEITUNG.md` (Sektion 8) beschreiben das QLC+-artige Tempo-System (Speed-Dial Master/Sub, Grand-Master, mehrere Tempo-Master); dazu Detailguides zu Speed-Dial, BPM-Manager und BPM-Generator (ganzes Lied → Beatgrid, Analyse-Engines, Beatgrid-Editor). `docs/anleitung_speed/ANLEITUNG_SPEED.md`, `docs/anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md`, `docs/anleitung_bpm_generator/ANLEITUNG_BPM_GENERATOR.md`.
- **Capability-Manifest als Agenten-Vertrag:** Neues generiertes `docs/CAPABILITIES.md` + `docs/capability_manifest.json` listet alle real existierenden Bausteine (VC-Widget-Typen, ButtonActions, SliderModes, Matrix-/EFX-Algorithmen mit gueltigen Parametern, Tempo-Buses, Kurven) und warnt vor den zwei Asymmetrien beim Laden (falscher Matrix-Algo → still PLAIN; falscher EFX-Algo/Style → ganze Funktion faellt weg). `docs/CAPABILITIES.md`, `docs/capability_manifest.json`.
- **VC-Widget-Referenz und Smart-Build-Flow dokumentiert:** Neue Referenz aller VC-Bau-Elemente (~21 Einzeldateien) sowie Anleitungen zum anfaengerfreundlichen Aufbau-Flow (Effekt reinziehen → Drop-Karte ankreuzen, Widget-Galerie, Konfliktschutz, Widget-Typ-Wechsel). `docs/anleitung_vc_widgets/README.md`, `docs/anleitung_vc_smartbuild/ANLEITUNG.md`, `docs/tutorial_matrix/TUTORIAL_LICHTSHOW.md`.
- **Show-Dateiformat-Spezifikation erweitert:** `docs/SHOW_FILE_FORMAT.md` dokumentiert die neuen/erweiterten .lshow-Bloecke (playlist, music_autoshow, efx_paths, Function-Param `priority`, Visualizer-Andock-Beziehungen + active_stage, live_view-Meta). `docs/SHOW_FILE_FORMAT.md`.
- **Performance-Benchmark und Programmier-Notizen:** Neue `docs/PERFORMANCE.md` mit Render-Pipeline-Benchmark ueber 8/16/32 Universen (p50/p95/FPS) und Hinweis auf super-lineares Wachstum oberhalb des 44-Hz-Budgets; neue `docs/PROGRAMMING_NOTES.md` buendelt nicht-offensichtliche Fakten fuer Show-/Engine-Arbeit. `docs/PERFORMANCE.md`, `docs/PROGRAMMING_NOTES.md`.
- **Optionale BPM-Engines und Status-Dokumente fortgeschrieben:** `requirements.txt` listet (auskommentiert, nicht erforderlich) die optionalen Analyse-Engines librosa, soundfile, torch und beat_this; `docs/OPEN_POINTS_OVERVIEW.md` wurde mit umgesetzten Punkten fortgeschrieben und `MIDI_CRASH_DEBUG_NOTES.md` als historisch markiert (Crash-Hypothesen durch die Thread-Safety-Fixes adressiert). `requirements.txt`, `docs/OPEN_POINTS_OVERVIEW.md`, `MIDI_CRASH_DEBUG_NOTES.md`.

### Behoben/Hinzugefuegt (2026-06-15 — EFX-Formen, Anzeige-Sync, Geräte-Solo)
- **EFX-Formen mit harten Kanten:** `SQUARE` und `DIAMOND` waren trigonometrische
  Näherungen, die die Ecken diagonal *abschnitten* (ein „Quadrat" erreichte die
  echte Ecke nie → wirkte verschliffen). Jetzt sind Quadrat/Raute/Dreieck **echte
  Polygone** mit scharfen Ecken (gemeinsamer `_polygon`-Helfer, lineare Kanten,
  jede Kante 1/n der Phase). Neue Form **`TRAPEZ`** (schmal oben, breit unten);
  erscheint automatisch im EFX-Editor-Dropdown. `TRIANGLE` bit-identisch zum
  bestehenden Test. Für freie harte Kanten gibt es zusätzlich den Custom-Path
  (Modus „linear"). `src/core/engine/efx.py`, Tests `tests/test_efx_hard_edges.py`.
- **VC-Button spiegelt Laufzustand:** ein FUNCTION_TOGGLE-Pad leuchtete nur
  während des Drucks (`_pressed`), nicht solange seine Funktion lief — es sah aus,
  als liefe nichts mehr, obwohl sich die Moving Heads noch bewegten. Jetzt grüner
  „aktiv"-Rahmen, solange der Effekt läuft (`_function_running`); die VC-View
  zeichnet funktionsgebundene Pads bei jedem Laufzustands-Wechsel neu (UI-Thread-
  Timer, thread-sicher). `vc_button.py`, `virtual_console_view.py`, Test
  `tests/test_vc_button_running_feedback.py`.
- **Geräte-Solo (gegen Bank-übergreifendes Überschreiben):** neue VC-Pad-Option
  **„Andere Effekte auf denselben Geräten stoppen"** — beim Start ersetzt der
  Effekt nur die laufenden Effekte, die DIESELBEN Strahler benutzen (auch aus
  einer anderen Bank), Effekte auf anderen Geräten laufen weiter. Chirurgischer
  als „Exklusiv" (= alles stoppen). Engine: `FunctionManager.affected_fids()`
  (alle Typen, rekursiv über Chaser/Collection/Sequence) +
  `stop_others_sharing_fixtures()`. `function_manager.py`, `vc_button.py`, Test
  `tests/test_function_solo_fixtures.py`.
- **Live-View-Info-Box zeigt EFX/Matrix:** laufende EFX-/RGB-Matrix-Effekte
  wurden nie als „aktiv" am Gerät gelistet (`hasattr(func,'_values')` traf bei
  EFX die gleichnamige *Methode* → Exception). Jetzt korrekt per isinstance-Guard
  über alle Typen (EFX `fixtures`, Matrix `fixture_grid`, Carousel/LayeredEffect
  `fixture_ids`, Scene `_values`). `src/ui/views/live_view.py`.

### Hinzugefuegt (2026-06-14 — Fixture Generator, F-23/X-4)
- **Fixture Generator** (grafisches Anlegen eigener Geraete-Profile, an QLC+ 5
  orientiert): `src/ui/widgets/fixture_generator.py` (`FixtureGeneratorDialog`),
  Start im **Patch-Tab → „Gerät erstellen…"**. Kopf (Hersteller/Modell/Typ/
  Leistung/Notizen), mehrere Modi, gefuehrter Kanal-Editor (Attribut-Combo +
  Freitext, **mehrfache gleiche Attribute** wie zwei Pan/zwei Tilt, Default/
  Highlight, Invert, **8/16-bit mit Fine-Kanal-Kopplung**), Bereichs-Editor je
  Kanal (range_from/to, Name, `kind`, „Art aus Namen", Schnellwahl-Vorschau),
  **nicht-blockierende Live-Validierung** (0–255, Ueberlappung, Luecke,
  doppelte Attribute, Dimmer↔Strobe-Plausibilitaet, fehlender open-Bereich,
  Modus-Vergleich), **echter Live-Test** (Universe + Startadresse, ein Fader pro
  Kanal schreibt direkt ins Universe des OutputManagers, „Wackeln" rampt einen
  Kanal, „Blackout" + sauberes Restore beim Stop/Schliessen), **`.qxf`-Import**
  als Startpunkt und **Markdown-Export** des Kanal-Layouts. Speichert als
  `source="user"` via `fixture_db.create_user_profile` und emittiert
  `REFRESH_ALL`. Kernlogik UI-unabhaengig/testbar
  (`build_profile_payload`/`validate_model`/`LiveTester`/`model_to_markdown`).
  Tests: `tests/test_fixture_generator.py` (18). Doku:
  `docs/FUTURE_FIXTURE_GENERATOR.md`.

### Hinzugefuegt (2026-06-11 — Details: docs/UPDATE_2026-06-11.md)
- **EFX Custom Paths:** eigene Pan/Tilt-Bewegungen im Popout-Editor aufzeichnen
  (Punkte tippen/ziehen/umsortieren, Linear oder Spline, Vorschau), Pfad-
  Bibliothek pro Show (`efx_paths`), Auswahl im EFX-Hauptfenster, Loop/One-Shot
  als EFX-Eigenschaft. Engine: `efx_path.py` (bogenlaengen-parametrisiertes
  Sampling), `EfxAlgorithm.CUSTOM`. Tests: `tests/test_efx_path.py`.
- **EFX ueber VC/MIDI:** `EfxInstance` traegt jetzt die Live-API
  (`list_params`/`set_param`/`do_action`/`list_actions`) — Speed/Groesse/Fan/
  Richtung/Loop/Pfad/Form auf Fader & Tasten mappbar, gleiche Mechanik wie
  Matrix/Chaser; Live-Editor-Dialog zeigt funktionsspezifische Aktionen.
- **Patchen → Gruppenansicht → "Bearbeiten…":** Mitglieder hinzufuegen/
  entfernen, Reihenfolge (Fan/Chase) per ▲▼, Name aendern — touch-tauglich
  ohne Drag&Drop. Tests: `tests/test_group_edit_dialog.py`.
- **Live View Touch:** Mehrfachauswahl-Modus toggelt jetzt auch die linke
  Liste per Antippen (MultiSelection), groessere zoom-unabhaengige
  Trefferflaechen, Naechster-gewinnt-Hit-Test.
- **Programmer-Ordner klappbar:** Gruppen-Ordner-Kopfzeilen antippbar (▾/▸,
  persistiert); Bibliotheks-Ordnerzustand ueberlebt Rebuilds + Neustart.
- **Controller-Datenbank:** JSON-Profil-Bibliothek (`data/controller_library/`
  + Nutzer-Importe) mit 8 Seed-Geraeten (APC mini/mk2, nanoKONTROL2, X-Touch
  Mini, Launchpad Mini MK3, Enttec DMX USB Pro, Art-Net-Node, Makro-Tastatur),
  QLC+-.qxi-Import (CLI + UI), Browser in der MIDI-Konsole. Quellen/Lizenzen:
  `data/controller_library/README.md`. Tests: `tests/test_controller_library.py`.
- **VC-Keyboard-Mapping:** Tasten/Kombinationen auf VC-Buttons lernen
  (Rechtsklick → "Taste zuweisen…"), Konfliktpruefung, Blackout-Warnung,
  Textfeld-/Modal-/AutoRepeat-Schutz, Press/Release wie MIDI-Note, Persistenz
  im VC-Layout. Doku: `docs/KEYBOARD_MAPPING.md`. Tests:
  `tests/test_keyboard_mapping.py`.
- **Demo:** `tools/build_custom_path_demo.py` → `shows/CustomPath_Demo.lshow`
  (selbst-verifizierend; MIDI- + Tastatur-Bindungen, One-Shot + Loop-Pfad).
- **Fixture-Quellen-Doku:** `docs/FIXTURE_SOURCES.md` (OFL/QLC+ legal nutzen).

### Behoben
- **Zombie-Subscriber im Event-Bus (Crash-Klasse aus crash.log, 2026-06-10).**
  Eingebettete Views (EFX-/Matrix-/Paletten-Seite, SnapFilePanel) werden bei jedem
  Programmer-Layout-Wechsel neu gebaut, blieben aber im StateSync registriert —
  der naechste Emit lief in geloeschte Qt-Objekte (RuntimeError bis Access
  Violation, siehe %APPDATA%/LightOS/crash.log). Neu: `StateSync.subscribe_widget`
  (auto-unsubscribe bei `destroyed`) fuer diese Views + Selbstheilung in
  `StateSync.emit` ("already deleted"-Subscriber werden entfernt).
  Tests: `tests/test_sync_safe_subscribe.py`.
- **EFX "Bounce" sprang am oberen Umkehrpunkt auf den Anfang.** Nach dem Klemmen
  der Phase auf 1.0 lief noch das gemeinsame `%= 1.0` -> Phase 0.0 (Saegezahn statt
  Pendel). Betroffen u. a. "MH Bounce" in `Komplett_Demo.lshow`.
  Tests: `tests/test_moving_head_efx.py::EfxBounceTest`.

### Hinzugefuegt
- **UI-Freeze-Watchdog (main.py).** Freezes ("Keine Rueckmeldung") hinterliessen
  bisher keinen crash.log-Eintrag. Ein 1-s-Herzschlag-Timer im UI-Thread + Daemon-
  Watchdog dumpt nach >10 s Stillstand die Stacks ALLER Threads nach crash.log —
  der naechste Freeze ist damit diagnostizierbar.
- **Headless-Verifier fuer die Komplett-Demo** (`tools/verify_komplett_demo.py`):
  laedt die Show ohne UI, prueft Referenz-Integritaet (Timeline/Chaser/VC), tickt
  die AUTO-SHOW >1 Loop durch den echten Renderer und assertet, dass sich die
  Moving-Head-Kanaele in den EFX-Abschnitten bewegen.
- **ZQ02001-Profil: Dimmer/Strobe waren vertauscht (2026-06-10).** Nach realen
  Gerätedaten korrigiert: Strobe liegt VOR dem Dimmer (9ch: CH5/CH6, 11ch: CH7/CH8);
  der 9-Kanal-Modus hatte fälschlich Pan/Tilt-fein statt Pan/Tilt-Speed, Gobo-FX und
  Reset. Farbrad (15 Slots inkl. 6 Split-Farben + Auto), Gobo (7 statisch + 7 Shake +
  Wechsel 128–255) und Strobe (0–9 offen / 10–249 langsam→schnell / 250–255 aus) sind
  jetzt als exakte `ChannelRange`-Bereiche mit `kind` hinterlegt. `ensure_builtins()`
  aktualisiert veraltete builtin-Profile **in-place** (Profil-ID stabil — bestehende
  Patches überleben). Der Reset-Kanal war zudem als zweiter `macro`-Kanal im
  Programmer unsichtbar (Attribut-Dedup) → neue Attribute `gobo_fx` und `reset`.
  Doku: `docs/MOVING_HEADS.md`. Tests: `tests/test_zq02001_profile.py`.
- **Test-Suite-Stabilität:** erzeugte `VCCanvas`-Instanzen blieben beim globalen
  MIDI-Manager registriert (Abmeldung nur bei Zerstörung); über viele Tests häuften sich
  tote Callbacks bis zu einem harten Crash. Neue Autouse-Fixture (`tests/conftest.py`)
  meldet nach jedem Test alle noch lebenden Canvases ab.
- **Simple Desk Roh-Bypass (ISO-03):** Die 512 Fader schrieben direkt ins Live-Universe,
  **am zentralen Renderer vorbei**. Folge: auf gepatchten Kanaelen ueberschrieb der Renderer
  den Wert Frame fuer Frame (Flackern/wirkungslos), auf freien Kanaelen blieb er als
  **unsichtbarer „Zombie"** dauerhaft stehen. Simple Desk ist jetzt eine deterministische
  **Override-Schicht** im `_render_frame` (oberste Ebene): kein Flackern, kein Zombie, und
  die Werte sind sicht- (ISO-01) und loeschbar (ISO-02). Test: `tests/test_iso_simple_desk.py`.
  **Standard = reine Anzeige (Monitor):** die Fader spiegeln die Ausgabe und wirken nicht;
  erst die Checkbox **„Manueller Override"** gibt ihnen absolute Oberhand (im Anzeige-Modus
  sind Fader + „Alles auf …"-Buttons gesperrt).
- Effekt-Layering (LAYER-01): Laufende Funktionen wurden in **ungeordneter** Reihenfolge
  (Set) getickt. Schrieben zwei Effekte denselben DMX-Kanal (z. B. Farb-Matrix mit
  `drive_intensity` + Dimmer-Matrix), gewann ein **zufaelliger** Writer statt der zuletzt
  gestarteten Funktion → Werte wurden unvorhersehbar ueberschrieben. `FunctionManager.tick()`
  laeuft jetzt in Start-Reihenfolge (LTP: zuletzt gestartet gewinnt). Test:
  `tests/test_function_layer_order.py`.
- Virtual Console: Absturz (`KeyError: 0`) beim Bewegen eines Level-Faders. Ursache war
  eine fehlerhafte Universe-Pruefung (`< len()` auf einem dict mit 1-basierten Keys).
  Der Fader legt das Ziel-Universe nun bei Bedarf an; das Universe ist im
  Fader-Eigenschaften-Dialog einstellbar (Default 1).

### Hinzugefuegt
- **Moving-Head-Bedienung im Programmer (2026-06-10):** Strobe liegt jetzt im
  **Intensity-Tab** neben dem Dimmer (Status-Kacheln „Kein Strobe/Strobe aus" +
  stufenloser Speed-Slider + DMX-Bereichslegende; Grand Master fasst den Strobe-Kanal
  weiterhin nicht an). **Color-Wheel-Direktwahl**: farbige Kacheln für alle Voll- und
  Split-Farben (zweifarbig dargestellt) + **Auto-Farbwechsel** als Hardware-Rotation
  (Tempo-Slider) und **Software-Simulation** mit wählbarem Bereich (Von/Bis, „Nur
  Split-Farben"). **Gobo-Tab**: Kacheln mit **grafischer Gobo-Vorschau** (neues
  wiederverwendbares Modul `src/ui/widgets/gobo_icons.py`, 7 QPainter-Muster),
  Shake-Kacheln mit einstellbarer Geschwindigkeit, Gobo-Wechsel-Slider (128–255) mit
  Stopp, Gobo-FX-Fader. **Reset-Button** („Weitere") mit Sicherheitsabfrage und
  automatischem Rücksetzen nach 4 s — bewusst kein Dauer-Slider. Alles generisch aus
  den `ChannelRange`-Daten (kein Raten ohne Capability-Daten). Neue Doku:
  `docs/MOVING_HEADS.md`, `docs/FIXTURE_LIBRARY.md`,
  `docs/FUTURE_FIXTURE_GENERATOR.md` (Idee, bewusst nicht gebaut) und
  `docs/OPEN_POINTS_OVERVIEW.md` (repo-weite Übersicht offener Punkte).
- **Phase-6-Feinschliff:** Matrix-**Versatz**-Parameter (`offset`) + Dimmer/Shutter-Min/Max
  und Weissanteil **live steuerbar** (MXP-02/03); **Simple-Desk-Fader nach Fixture eingefärbt**
  (SDK-01); **Fader-Reichweite „nur Auswahl/Gruppe"** im Programmer-Modus (FDR-01); VC-Toolbar
  entschlackt (UIC-02..05: „⊞ Raster", „Canvas exportieren/importieren", „Aktiver Effekt"-Zeile
  nur bei laufendem Effekt, Canvas-Kontextmenü ohne Save/Load-Dopplung). Tests:
  `test_matrix_offset_style_params.py`, `test_fader_scope.py`, `test_simple_desk_tint.py`.
- **Demo-/Bühnen-Show (DMO-01):** `tools/build_demo_zq_show.py` → `shows/Demo_ZQ_Buehne.lshow`
  mit **4× ZQ01424 (PAR)** + **2× ZQ02001 (Moving Head)**: Farben/Looks, Dimmer-Lauflicht,
  RGB-Matrix, Moving-Head-Positionen/Beam + Sweep-Chaser, **Speed-Dial (Multiplikator)**,
  zwei **VC-Frames** (PARs / Moving Heads) und ein **Multi-Action-Button** „▶ Showtime".
  (Die ursprünglich als „Horhin" bezeichneten Strahler sind ZQ01424, der Moving Head ist ZQ02001.)
- **Paletten + Kurven: Unterordner (FLD-01c):** Paletten und Fade-Kurven haben jetzt ein
  verschachtelbares `folder`-Feld (in der Show gespeichert, rückwärtskompatibel). Die
  Paletten-Ansicht gruppiert nach Ordner (Überschriften) und bietet „In Ordner verschieben…".
  Damit ist FLD-01 („Unterordner überall") abgeschlossen. Test: `tests/test_palette_curve_folders.py`.
- **Fixture-Gruppen: Unterordner (FLD-01b):** Gruppen lassen sich einem verschachtelten
  Ordner zuordnen („Ordner…"-Button, Pfad mit `/`, z. B. „Front/Wash"); die Gruppen-Auswahl
  zeigt den Ordnerpfad und sortiert danach. Neue, **idempotente DB-Migration**
  (`migrate_show_db`) ergänzt die `folder`-Spalte in bestehenden Show-DBs ohne Datenverlust.
  Test: `tests/test_fixture_group_folders.py`.
- **Funktions-Manager zeigt Ordner (FLD-01a):** die rechte Funktionsliste bildet jetzt die
  vorhandene, verschachtelte Ordner-Hierarchie der Funktionen (`folder`-Pfad, z. B.
  „Blau/Sommer") innerhalb jeder Typ-Gruppe ab — erster Schritt von „Unterordner überall".
  Test: `tests/test_function_folders.py`.
- **Snapshots: Kanäle nachträglich ignorieren (SNP-01):** pro Snapshot lassen sich
  einzelne (Fixture, Attribut)-Kanäle vom Anwenden ausschließen — der gespeicherte Wert
  bleibt erhalten, wird aber nicht in den Programmer geschrieben. Editor über „Kanäle
  ignorieren…" (Alle/Keine/Invertieren); rückwärtskompatibel. Test: `tests/test_snapshot_ignore.py`.
- **Kanal-Gruppen pro Show (SDK-02):** Channel Groups werden jetzt in der `.lshow`
  gespeichert/geladen (statt nur global in `data/channel_groups.json`). Test:
  `tests/test_channel_groups_show.py`.
- **Widgets per Drag in Frames ziehen (FRM-01):** ein vorhandenes VC-Widget lässt sich in
  einen Frame ziehen (wird dessen Kind, Position relativ) und wieder heraus auf den Canvas;
  die Zuordnung bleibt beim Speichern erhalten. Frames werden nicht verschachtelt. Test:
  `tests/test_frame_drag.py`.
- **Multi-Actions auf VC-Buttons (BTN-01):** ein Button kann beim Druck — nach seiner
  Primär-Aktion — eine Liste weiterer Aktionen der Reihe nach ausführen (Funktion
  start/stop/toggle, Effekt-Aktion, Snapshot, Bibliothek-Snap, Blackout, Stop-All,
  Programmer/Non-VC leeren, Tap), je mit optionaler Verzögerung. Editor über
  „Mehrfach-Aktionen…" im Button-Dialog; ein „+n"-Marker zeigt die Anzahl. Vollständig
  rückwärtskompatibel (ohne Liste = klassischer Ein-Aktions-Button). Test:
  `tests/test_button_multi_action.py`.
- **Speed Dial: Multiplikator-Modus, Sync, Multi-Ziele, Invertierung (SPD-01/02/03/04):**
  optionaler **Multiplikator-Modus** (Dial als Faktor 0.5/1/2/4× auf die Effekt-Speed statt
  absoluter BPM), **SYNC-Button** (gleicht die Phase aller Ziel-Effekte an), **mehrere
  Ziel-Effekte** (weitere Function-IDs) und eine **Invert-Option** (höher = langsamer).
  Persistiert, rückwärtskompatibel. Test: `tests/test_speed_dial.py`.
- **Matrix-Live-Editor in der Virtual Console (MLV-01/02):** Rechtsklick auf einen an
  einen Effekt gebundenen VC-Button/-Fader zeigt „⚡ Live-Parameter…". Der Dialog listet
  die live steuerbaren Parameter (→ Fader) und Aktionen (→ Tasten) des Effekts; die Auswahl
  wird **automatisch** als korrekt gebundene VC-Bedienelemente erzeugt (EFFECT_PARAM /
  EFFECT_ACTION, an die `function_id` des Effekts). Bearbeiten/Entfernen über die normalen
  Widget-Menüs. Test: `tests/test_matrix_live_vc.py`.
- **Fixture U King ZQ02001 (LIB-01):** Mini-Gobo Moving Head (11-Kanal + 9-Kanal) zur
  Fixture-Library hinzugefügt — `examples/add_zq02001.py`. Kanal-Layout aus dem
  Hersteller-Handbuch; feine Farb-/Gobo-Wertbereiche sind genähert und im Skript markiert.
- **Matrix-Chase „Farbwechsel-Intervall" (MXP-01):** neuer Parameter `color_interval`
  (sichtbar bei aktivem „Farbe pro Runde wechseln") — die Farbe wechselt erst alle N
  Durchläufe (1 = jeder Durchlauf wie bisher, 2/4/8 = langsamer). Live über VC/MIDI
  steuerbar, persistiert, Default 1 für Alt-Shows. Test: `tests/test_matrix_color_interval.py`.
- **Color-Sequence: Swatch-Einzelklick öffnet den Color-Picker (MXP-04):** im kompakten
  Farbstreifen (Matrix-Programmer) öffnet ein Klick auf ein Farbquadrat direkt den Picker
  für diese Farbe (live), ohne erst den Editor öffnen zu müssen.
  Test: `tests/test_color_sequence_swatch.py`.
- **Anzeige aktiver Fremdwerte (ISO-01):** Die obere Leiste zeigt jetzt ein Badge
  „● Programmer n · Simple Desk n", sobald manuelle Werte aktiv sind — damit faellt nichts
  mehr unbemerkt in die Live-Ausgabe.
- **Zentrales Clear (ISO-02):** Button „✖ Clear ▾" in der oberen Leiste mit
  *Programmer leeren · Simple Desk leeren · Alle Nicht-VC-Werte leeren*. Setzt nur aktive
  manuelle Werte zurueck — laufende Funktionen/Effekte/Cues, gespeicherte Effekte, Shows,
  Patches und Fixtures bleiben unangetastet. API: `clear_simple_desk()`, `clear_all_non_vc()`.
- Virtual Console: pro Effekt-Fader einstellbar, ob er **bei 0 den Effekt stoppt** oder
  **nur runterregelt** (Eigenschaft `effect_autostart`, Checkbox im Fader-Dialog). An:
  Wert > 0 startet den gebundenen Effekt, Wert 0 stoppt ihn (wie ein Playback-Fader);
  aus (Default): Fader regelt nur. Gilt fuer *EffectIntensity/EffectSpeed/EffectParam*.
- Visualizer-Persistenz: Fixture-Positionen und die aktive Buehne werden mit der Show
  (`.lshow`) gespeichert und beim Laden wiederhergestellt (T-VIZ-01, T-VIZ-02).
- Unit-Tests fuer Core-Engine: `tests/test_core_engine.py`
  - `Universe` (DMX-Kanalverwaltung, Thread-Safety, Boundaries)
  - `Cue` (Datenmodell, Serialisierung-Roundtrip)
  - `FadeState` / `CueStack` (Fade-Interpolation, Go/Back/Stop/Loop, Callbacks)
  - `ChannelModifier` / `ChannelModifierManager` (alle Kurventypen, apply_to_universe, Save/Load)
  - `SelectionExpr` (Fixture-Selektion, Ranges, Excludes)
  - Command-Line Parser (`parse()` fuer alle Befehle)
  - `UndoStack` (Push/Undo/Redo, MAX_SIZE-Cap, Listener)
- `README.md` um "Quick Start"-Abschnitt erweitert (5-Minuten-Guide fuer neue Nutzer)
- `.github/workflows/ci.yml` — automatisierte Test-Pipeline (Python 3.11 + 3.12)
- `CHANGELOG.md` — diese Datei (Keep-a-Changelog-Format)

### Entfernt
- **Redundanter „Snap"-Button (UIC-01)** aus der oberen Leiste. Die Schnell-Snapshot-Funktion
  bleibt vollstaendig erreichbar ueber Menue *Programmer → Snapshot aufnehmen* (`Strg+Shift+S`),
  die *Snapshots*-Ansicht und die VC-Seitenleiste.

---

## [0.1.0] — 2026-05-26

### Hinzugefuegt
- Vollstaendige DMX-Steuerungs-Engine
  - Enttec DMX USB Pro, Art-Net 4, sACN / E1.31 (bis zu 32 Universen)
  - OutputManager mit 44-Hz-Loop, Grand Master, Blackout, Submasters
  - Channel-Modifier mit 7 Kurventypen + Custom LUT
- Engine (10 Function-Typen)
  - Scene, Chaser, Collection, Show (Timeline), EFX, RGB-Matrix,
    Sequence, Audio, Script, LayeredEffect, Carousel
  - Multi-Page-Playback: 10 Pages × 20 Executors = 200 Slots
  - Cue-System mit Fade-In/Out, Delay, Auto-Follow, Loop
  - Undo/Redo (unbegrenzt, 100er-Cap)
- Programmer
  - Attribut-Gruppen: Intensity, Color, Position, Beam, Gobo, Effect
  - Color Picker (RGB/HSB/CMY, 27 Lee-Rosco Gel-Filter)
  - Position Tool (2D-Pad, 13 Presets)
  - Fan Tool (5 Kurven, Symmetric/Asymmetric)
  - Snapshots (12×4 Quick-Recall)
  - Paletten (Color / Position / Beam)
- Audio / BPM
  - WASAPI Loopback Audio-Capture
  - Beat-Detection (Bass-Energy adaptive Threshold)
  - Tap-Tempo BPM-Manager
  - OS2L Server (VirtualDJ Integration)
  - MIDI Time Code Reader
- Virtual Console
  - Button, Slider, XY-Pad, Cue-List, Speed-Dial, Frame, Label, Solo-Frame
  - Save/Load Layouts pro Show
- 3D Visualizer (Three.js / QtWebEngine)
  - 2D Top-Down + 3D Perspektive, 4 Bühnen-Presets + Custom Stage Builder
  - Echte 3D-Modelle, volumetrische Beam-Cones
- Eingaben
  - MIDI Input mit Profil-Editor (Akai APC mini Default)
  - OSC Server (Port 7770)
  - Keyboard-Hotkeys
  - Web-Remote (Flask + Socket.IO)
- Command-Line (MA-/Avolites-Style)
  - `1 thru 5 @ 80`, `all @ full`, `go 1`, `record cue 2.5`, `page 3`, `blackout`
- Installer/Uninstaller (`install.py`, `uninstall.py`)
  - ARM64/Snapdragon-Erkennung, venv-Management, Desktop-Verknuepfung
- Start-Skripte fuer CMD (`.bat`), PowerShell (`.ps1`), Bash (`.sh`)
- Fixture-Datenbank (SQLAlchemy/SQLite), GDTF-Import
- Show-File-Format `.lshow` (ZIP + JSON, Version 1.1, Legacy-1.0-Support)
- Vollstaendige Dokumentation in `docs/`

---

<!-- Verlinkung fuer die Versionen -->
[Unreleased]: https://github.com/OWNER/lightos/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OWNER/lightos/releases/tag/v0.1.0
