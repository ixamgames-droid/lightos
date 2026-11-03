ID: ENG-37
Prioritaet: P2
Status: review
Status-Notiz: Gemischte Vorschau gebaut — der Matrix-Editor zeigt bei einem Modify-Effekt (Haken „Vorschau gemischt“, Vorgabe an) das Grundbild mit dem Modify verrechnet; der Renderer merkt sich auf Anforderung das Bild vor 4a²b (AppState.grundbild), modify.vorschau_mischen rechnet mit modify_posten + posten_anwenden (eine Regel); Test tests/test_eng37_gemischte_vorschau.py. Alles andere erledigt bzw. ausgelagert: Bewegung -> ENG-43, Bilder -> DOC-73.
