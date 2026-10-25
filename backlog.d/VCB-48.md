ID: VCB-48
Prioritaet: P2
Status: review
Status-Notiz: Umgesetzt auf feat/vcb48-popup-tasten (Rahmen-Eigenschaft „Pop-up-Feld“ + Tastenaktion „Pop-up-Feld öffnen/schließen“, Sperre gegen Verschachtelung, Kiosk bedienbar); Tests test_vcb48_popup_tasten.py; Gegenpruefung eingearbeitet (Drop ins offene Feld, Bank-Abgleich der Taste, Redo laesst Feld offen, Test der Laufzeit-Sperre); wartet auf Review/Merge durch A.
Titel: Pop-up-Tasten in der Virtual Console — eine Taste öffnet ein Feld mit eigenen Tasten, dieselbe Taste schließt es

**Wunsch (Projektinhaber, 20.10.2026):** Eine VC-Taste öffnet ein Pop-up mit selbst hineingelegten Tasten. Das Pop-up **überlagert** die übrigen VC-Elemente (liegt darüber, nicht als eigenes Fenster). **Dieselbe Taste schließt es wieder.** Es funktioniert auch im **Kiosk**. **Keine Verschachtelung** (kein Pop-up im Pop-up).
**Bausteine:** VCFrame als Container (Kinder, to_dict/from_dict, Undo, Solo-Logik), neue Tastenaktion „Pop-up öffnen/schließen“ in vc_button.py mit Ziel-Feld, Sichtbarkeit wie Bänke/_child_visible, Kiosk-Sperren der Canvas.
**Vorgaben (A, änderbar):** Tasten im geschlossenen Pop-up bleiben über MIDI/Hotkey auslösbar und zeigen ihren Zustand weiter (wie bei Bänken); das Pop-up darf auch Fader enthalten; es steht dort, wo es im Editor platziert ist.
