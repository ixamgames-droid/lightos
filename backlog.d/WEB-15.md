ID: WEB-15
Prioritaet: P1
Status: review
Titel: Handy-Konsole: Befunde aus dem Neuheiten-Audit (Laser-Sperre bei Executor-Tasten, Teil-Ausfuehrung vc_pult, Sperre waehrend UI-Rundlauf, NaN in handy_seiten)

**Herkunft:** Neuheiten-Audit von Sitzung A am 15.11.2026, vier Funde (von einem zweiten Pruefer bestaetigt). Test: `tests/test_web15_handy_audit.py`.

**Befund 1 (hoch, Laser):** Tasten mit „Executor: Umschalten (Go)“ (TOGGLE, die Standardaktion einer neuen Taste) und „Executor: Flash“ (FLASH) tragen in `function_id` den Executor-Slot. `_taste_laser` schlug ihn als Funktions-ID im FunctionManager nach, fand dort nichts und hielt die Taste fuer laserfrei. Ein Handy startete so ohne den Schalter „Laser vom Handy erlauben“ eine Laser-Cueliste. **Behebung:** eigener Zweig fuer TOGGLE/FLASH: geprueft wird die Cueliste auf dem Slot (`_slot_laser`, derselbe Weg wie der Playback-Fader); ohne gueltigen Slot tut die Taste nichts und ist frei, eine Slot-Nummer gleich der ID einer Laser-Funktion sperrt nicht mehr falsch. Die Zusatzaktionen `clear_non_vc` und `tap` gelten jetzt ausdruecklich als harmlos (vorher falsche Sperre, wenn ein alter Funktions-Wert im Eintrag stand).

**Systematische Pruefung, Aktionsart -> geprueft durch** (je Zeile ein Fall in `AktionsartTabelleTest` bzw. `ExecutorTasteLaserTest`; eine neue ButtonAction laesst `test_jede_tastenaktion_ist_eingeordnet` rot werden, bis sie eingeordnet ist):
- Taste TOGGLE, FLASH (Executor-Slot) -> `_slot_laser` / `executor_trifft_laser` (neu)
- Taste FUNCTION_TOGGLE, FUNCTION_FLASH, ALL_WHITE (gebundene Funktionen) -> `funktion_trifft_laser` ueber `_all_function_ids`; ALL_WHITE ohne Bindung laesst Laser ohnehin aus (`all_white`, LAS-37)
- Taste EFFECT_ACTION -> `funktion_trifft_laser`, ohne Ziel immer Laser
- Taste SNAPSHOT -> `_snapshot_fids` + `fids_treffen_laser` (unlesbar = Laser)
- Taste LIBRARY_SNAP -> `_snap_fids` + `fids_treffen_laser` (unlesbar = Laser)
- Taste LASER_PATTERN -> immer Laser
- Taste LASER_ARM -> harmlos fuer die Sperre, Scharfschalten aber nur am Pult (`nur_am_pult`)
- Taste BLACKOUT, STOP_ALL, CLEAR, STOP_EFFECTS, FREEZE, LASER_ESTOP, TAP, AUDIO_BPM, BPM_NUDGE_UP/DOWN, BPM_MODE_TOGGLE, TAP_BUS, SYNC_BUS, ARM_BUS, AUTO_SYNC, SELECT_GROUP, MEDIA_PLAY_PAUSE/NEXT/PREV -> `_harmlose_tastenaktionen` (dunkel, stoppen, Tempo, Auswahl, Musik)
- Taste POPUP_TOGGLE -> reine Oberflaeche, ohne Bindung frei (eine alte Funktions-ID sperrt im Zweifel)
- Zusatzaktionen function, effect_action, snapshot, library_snap -> `_eintrag_laser`, beim Druck und verzoegert (`verzoegert_erlaubt`); blackout, stop_all, clear, clear_non_vc, tap -> harmlos
- Fader LEVEL -> `adresse_ist_laser`; PLAYBACK -> `_slot_laser`; SUBMASTER -> `_submaster_targets`; GROUP_DIMMER, FEATURE_DIMMER, PROGRAMMER (Gruppe) -> `_group_fids`; EFFECT_INTENSITY/SPEED/PARAM -> `funktion_trifft_laser`, ohne Ziel Laser; GRANDMASTER, PROGRAMMER (alle) -> immer Laser; BPM, SPEED, TEMPO_BUS -> frei (nur Tempo)
- Cueliste GO, BACK -> `executor_trifft_laser`; STOP geht immer
- Handy-Gruppe (WEB-14): Ausschalten der anderen Tasten nur ueber `_ausschaltbar` (Laser gesperrt = blockiert) bzw. `ausfuehren`

**Befund 2 (niedrig):** `vc_pult` mit `{blackout, gm}` setzte zuerst den Blackout und lehnte danach den GM mit `laser_gesperrt` ab — Teil-Ausfuehrung mit Fehlermeldung (bzw. ein eigener Blackout wurde aufgehoben, obwohl der Aufruf scheiterte). **Behebung:** `fern_pult.pult_setzen` prueft beide Werte und setzt sie dann, alles unter demselben Lock; `blackout_setzen`/`gm_setzen` nutzen dieselben Pruef- und Setz-Teile.

**Befund 3 (niedrig):** `vc_remote.halten` hielt den globalen `_halte_lock` waehrend des UI-Rundlaufs (bis 2 s); Loslassen und Verbindungsabbau aller anderen Handys warteten dahinter. Dazu keine Grenze fuer Socket-Aktionen. **Behebung:** kein globaler Lock mehr; ein laufender Druck/Loslassen traegt sich je Taste ein (`_im_lauf`), nur ein zweiter Druck auf DIESELBE Taste wartet. Loslassen/Abbau warten nie: waehrend des eigenen Drucks wird das Loslassen danach nachgeholt; laesst der letzte Halter los, waehrend ein anderes Handy dieselbe Taste drueckt, uebernimmt dieses (oder laesst los, wenn sein Druck abgelehnt wird). Neues Modul `src/web/vc_grenze.py`: je Verbindung hoechstens 4 gleichzeitige Aktionen und 200 je Sekunde (Vorrat 400); ein Fader-Wert, der ankommt, waehrend der vorige noch laeuft, wird zusammengefasst und nachgeholt statt abgewiesen. Loslassen, STOP und Blackout AN sind ausgenommen. Darueber `zu_viele` (HTTP 429), am Handy „Zu viele Befehle auf einmal – kurz warten“.

**Befund 4 (niedrig):** NaN/Infinity als Zellenwert in `handy_seiten` liess `_ganzzahl` werfen; `VCCanvas.from_dict` verwarf dann den ganzen Abschnitt still. **Behebung:** `_ganzzahl` prueft `math.isfinite` und `is_integer`; nur der kaputte Eintrag faellt weg. Scheitert das Lesen trotzdem, steht es in `uebersprungene_widgets()`.

**Offen:** Die HTTP-Routen `/api/vc/...` haben noch keine Grenze je Geraet (nur der Socket); Bestaetigung am echten Handy.
