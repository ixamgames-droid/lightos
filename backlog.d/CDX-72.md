ID: CDX-72
Prioritaet: P2
Status: review
Titel: Codex-Ernte PRs 1255-1294: Befunde in der Virtuellen Konsole (Motorfader, Pult-LEDs, Cueliste, Halten+Antippen-Gruppe, Raum-Pad, XY-Pad)

**Herkunft:** Kommentare des automatischen Reviewers Codex zu den PRs 1255-1294, von Sitzung A am 15.11.2026 einzeln gegen den aktuellen Stand bestaetigt. Sieben Befunde, je ein Test in tests/test_cdx72_vc_codex_ernte.py (erst rot, dann gruen).

**Motorfader, Bankwechsel bei gehaltenem Fader (PR 1271):** Befund: die Beruehrungs-Note ging nur an den Fader der damals aktiven Bank; nach dem Wechsel fuhr der Fader der neuen Bank sofort gegen die Hand. Behebung: VCCanvas merkt Beruehrungs-Noten bankunabhaengig (motor_beruehrt, mit Ablauf nach MOTOR_BERUEHRT_MAX_S); arm_pickup uebernimmt die Sperre auf den Fader der neuen Bank, das Loslassen traegt seinen Wert nach. Test: zwei Fader auf Kanal 2 (Bank 0/1), Beruehrung, Bankwechsel, nichts gesendet, nach dem Loslassen der Wert der neuen Bank; Gegenproben ohne Hand und mit Hand an einem anderen Fader.

**Pickup nach Motorfahrt (PR 1271):** Befund: arm_pickup armierte Soft-Takeover auch, wenn der Motor den Fader schon auf den VC-Wert gefahren hatte; ein Handsprung ueber die Toleranz wurde dann ignoriert. Behebung: zuerst armieren, eine erfolgreiche Motorsendung (_motor_senden) entschaerft den Pickup; ohne Motor oder ohne offenen Ausgang bleibt er armiert. Test: Motor-Fader uebernimmt nach dem Bankwechsel sofort 200; Gegenproben ohne Motor und mit geschlossenem Ausgang; Nachtrag beim Loslassen entschaerft ebenfalls.

**Pult-LEDs beim Beenden (PR 1272):** Befund: MainWindow.closeEvent rief close_all() vor dem Abbau der Canvas, die Note-Offs gingen ins Leere. Behebung: neue Methode VCCanvas.led_abschalten (Timer stoppen, alle_aus), _teardown_midi nutzt sie, MainWindow._vc_leds_abschalten laeuft vor close_all(). Test: LED an, led_abschalten schickt Note-Off und stoppt den Timer; Reihenfolge in closeEvent per AST geprueft.

**VC-Cueliste nach Seitenwechsel (PR 1277):** Befund: neu aufgebaut wurde nur bei anderer Cue-Anzahl; bei gleicher Anzahl blieben alte Eintraege stehen und der Doppeltipp sprang auf dem neuen Stapel an eine andere Cue. Behebung: Signatur aus Stapel, Nummern und Namen; der Doppeltipp gleicht vorher ab und springt bei veraltetem Eintrag nicht (keine Rueckfrage); _gehe_zu springt nur zu vorhandenen Nummern. Test: zwei Seiten mit je zwei Cues, Umbenennen, veralteter Eintrag, unbekannte Nummer.

**Halten + Antippen mit Gruppe (PR 1285):** Befund: halten_antippen_start stellte nur das gehaltene Widget zurueck; vom Zittern mitgezogene Gruppenmitglieder blieben verschoben, ohne Rueckgaengig-Schritt. Behebung: alle (Widget, Ausgangsrechteck) der Gruppe zuruecksetzen, dann die Gruppe leeren. Test: drei gewaehlte Widgets, 3 px Zittern, alle wieder an der Ausgangslage, kein Undo-Eintrag.

**Raum-Pad beim Loeschen/Neuladen (PR 1294):** Befund: mit Lock AN blieben Pan/Tilt des Pads im Programmer stehen, wenn es geloescht oder die Konsole neu geladen wurde. Behebung: neuer Hook vor_entfernen, den _gehaltene_loslassen fuer das Widget und alle Kinder aufruft (Loeschen, Kasten loeschen, _clear fuer Undo/Redo und Show laden); das Raum-Pad gibt dort frei, fremd ueberschriebene Werte bleiben. Der Bankwechsel (hideEvent) behaelt ein eingerastetes Ziel weiter. Test: Loeschen, Loeschen im Kasten, _clear mit fremdem Wert, hide() behaelt.

**XY-Pad, Pfad loeschen (PR 1294):** Befund: pfad_loeschen setzte den alten Algorithmus auch dann zurueck, wenn er nach dem Zeichnen umgestellt worden war. Behebung: der vom Pad gesetzte Algorithmus wird gemerkt (eigener_algo); weicht der aktuelle ab, werden nur Pfad-ID, Pfaddaten und eingebetteter Pfad zurueckgenommen. Test: Zeichnen, auf Kreis umstellen, Kreis bleibt; ohne Fremdaenderung kommt die Acht zurueck.

**Nachpruefung (16.11.2026):** (a) Motorfader ohne Beruehrungssensor: schob die Hand beim Bankwechsel, fuhr der Fader der neuen Bank sofort gegen sie. VCCanvas merkt jetzt auch die letzte Pitchbend-Eingabe je Kanal (`motor_hand_vor`), der Fader der neuen Bank wartet die Hand-Ruhe ab (`MotorFader.hand_gesehen`) und traegt danach nach. (b) Cueliste: wechselt die Seite waehrend der modalen Rueckfrage, springt die bestaetigte Zeile nicht auf den neuen Stapel (auch nicht bei gleicher Nummer). Tests `tests/test_cdx72_nachpruefung.py`.
