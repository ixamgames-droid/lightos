ID: IMP-3
Prioritaet: P2
Status: review
Nach: IMP-1
Titel: Tabellen-Import des Patch -- doppelte Namen nummerieren, Spaltenkopf lesbar, ein Neuaufbau je Import

**Herkunft:** Nachtrag zu IMP-1 (Abnahme der Vorschau und Laufzeitmessung). Drei Befunde: (1) doppelte Namen waren nur ein Hinweis, beide Geraete wurden gleich benannt angelegt -- Entscheidung der Leitung: automatisch nummerieren. (2) Der Spaltenkopf „In der Tabelle“ stand bei 900 px Dialogbreite als „n der Tabell“ da; der Knopf „Tabellen-Import ▾“ liess sich im Hauptfenster nicht per Tastatur oeffnen (Leertaste = GO). (3) `wende_an` rief je Geraet `state.add_fixture`; jeder Aufruf baute Kanal-Cache, Laser-Profile und Render-Plan neu und sendete `patch_changed` -- alle Ansichten bauten sich N-mal neu auf.

**Geliefert:**

- **Namen** (`src/core/patch_tabelle.py`): `_vergib_namen` ersetzt `_pruefe_namen`. Zwei Durchgaenge -- erst behaelt jeder noch freie Name seinen Platz (auch ein ausdruecklich so genanntes „PAR 2“ weiter unten in der Tabelle), dann bekommen die Doppelten ueber `naechster_freier_name` die naechste freie Nummer, auch gegen vorhandene „PAR links 2“. Regel fuer Namen mit Zahl am Ende: eine ABGESETZTE Zahl ist ein Zaehler und wird weitergezaehlt („PAR 3“ -> „PAR 4“, „Spot 01“ -> „Spot 02“) -- „PAR 3 2“ laese sich wie eine Unternummer; eine am Wort KLEBENDE Zahl („PAR64“, „ZQ01424“) ist Typbezeichnung und bleibt („PAR64 2“). Gross/Klein unterscheidet nicht. `PlanZeile.umbenannt`, `anzeige_name`, Vermerk vorn im `status_text`, `Plan.zaehler()["umbenannt"]` und Zaehlerzeile, `Ergebnis.umbenannt` und ein Satz in der Meldung nach dem Import. `wende_an` rechnet weiter gegen den JETZIGEN Patch neu, also auch die Namen.
- **Vorschau** (`src/ui/widgets/patch_import_dialog.py`): Spalte „Name“ zeigt den neuen Namen fett in der Hinweisfarbe, Tooltip nennt alten und neuen. Kopf „Tabelle“ statt „In der Tabelle“, `SPALTEN_TIPP` je Spaltenkopf, `_kleinste_breite` bindet die kleinste Spaltenbreite an den Kopftext.
- **Tastatur** (`src/ui/widgets/menue_knopf.py`): `MenueKnopf.keyPressEvent` nimmt Return/Enter an (ein QPushButton tut das ausserhalb eines Dialogs nicht). Die Leertaste bleibt GO und wird nicht umbelegt; Tooltip und Anleitung nennen die Eingabetaste.
- **Sammelweg** (`src/core/app_state.py`): `AppState.patch_sammeln()` -- Kontextmanager, verschachtelbar (Tiefenzaehler), nur fuer den oeffnenden Thread. Im Block laedt `_reload_patch_cache` nur Geraeteliste und Universen; Kanal-Cache, Laser-Profile und Render-Plan werden beim Verlassen EINMAL neu gebaut (`finally`, also auch nach einer Ausnahme). `_emit` merkt im Block `patch_changed` und `group_changed` ohne Daten und sendet sie am Ende je einmal, nach dem Neuaufbau. Alles andere bleibt: Kopf-Gruppen je Geraet, Laser-Hinweis (`hinweis`) sofort je Geraet, Einzelschritte fuers Rueckgaengig. `_suppress_emits` wird NICHT benutzt. `UndoStack.gruppe(label, rahmen=...)` (`src/core/undo.py`) legt denselben Kontext um das Rueckgaengig und Wiederholen des ganzen Schritts.

**Sicherheit:** Beim Verlassen des Blocks ist der Render-Plan aktuell -- ein importierter Laser steht in `_laser_fids`/`_laser_estop_addrs` (Test). Waehrend des Blocks gilt der alte Plan: ein neues Geraet gibt noch nichts aus, ein gerade entferntes wird bis zum Ende weiter gerendert und dann freigegeben. Der Block laeuft im UI-Thread am Stueck.

**Gemessen:** 60 Geraete ohne Fenster 2,75 s einzeln gegen 0,24 s gesammelt (`tests/test_imp3_buendeln.py`, Vergleich im selben Lauf).

**Offen / bewusst nicht gebaut:** Jedes Geraet macht weiter seinen eigenen DB-Commit (der Einzelweg `add_fixture` bleibt die einzige Wahrheit); bei sehr langen Listen waere das der naechste Hebel. Bei einer Zeile mit Anzahl > 1, deren erste Nummern schon vergeben sind, stehen die Namen nicht in aufsteigender Reihenfolge („PAR 4, PAR 5, PAR 3“) -- eindeutig, aber unschoen. `patch_sammeln()` wird bisher nur vom Tabellen-Import benutzt; „Mit Offset kopieren“ und das Loeschen mehrerer Geraete koennten ihn ebenfalls nehmen. Abnahme im sichtbaren Fenster (Eingabetaste am Knopf, Vorschau bei 900 px) steht aus.

**Tests:** `tests/test_imp3_namen.py`, `tests/test_imp3_dialog_und_patch.py`, `tests/test_imp3_buendeln.py`; angepasst `tests/test_imp1_patch_tabelle_kern.py`.
