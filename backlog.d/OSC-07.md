ID: OSC-07
Prioritaet: P3
Status: review
Status-Notiz: umgesetzt 26.10.2026 (Zweig fix/bpm33-osc07-befunde-d) — Ziel/Bereich/Funktion feste Breite über `tabellen_spalten.py`, Test `test_osc07_spalten_lesbar.py`; Gegenprobe unter Windows steht aus
Nach: OSC-06
Titel: OSC-Zuordnungen: Spalte „Ziel“ zu schmal — Auswahl zeigt nur „E“/„Ex“ bei 125/150 %

**Herkunft:** Windows-Gegenprobe von Sitzung D zu PR #1149 (OSC-06), 25.10.2026, Windows 11 x64.
**Befund:** Im Dialog „OSC-Zuordnungen & Rückmeldung“, Reiter Eingang, hat das Auswahlfeld der Spalte „Ziel“ nur 10 px Textfläche; „Executor-Fader“ braucht 85 px. Ursache vermutlich wie bei NET-15 (#1138): `ResizeToContents` misst vor `setCellWidget` nur den Kopftext; die Stretch-Spalte „Adresse“ nimmt den Rest. Kleinigkeit: Platzhalter „Name oder Id“ in „Funktion“ wird gekürzt (75 px Feld, 81 px Text).
**Fertig, wenn:** Spaltenbreite aus dem `sizeHint` einer Mess-Combo mit allen Einträgen (wie `dmx_fernsteuerung_box.py` seit #1138), Test der Lesbarkeit bei 12/15/18 px Schrift (ohne Fix rot), Gegenprobe unter Windows.
**Umsetzung (26.10.2026):** Neue gemeinsame Hilfe `src/ui/widgets/tabellen_spalten.py` (`combo_breite`, `lineedit_breite`, `spalte_fest`); `dmx_fernsteuerung_box.py` nutzt sie ebenfalls (gleiches Verhalten). Im OSC-Dialog sind „Ziel“, „Bereich“ und „Funktion“ `Fixed` und werden nach jeder neuen Zeile sowie bei Schrift-/Stiländerung neu gemessen; „Funktion“ aus der Breite des Platzhalters. **Ursache bestätigt (Linux, offscreen):** direkt nach dem Bau stehen die Spalten auf der Kopftext-Breite (Ziel 43 px, Funktion 75 px bei 12 px Schrift — dieselben 75 px wie bei D); unter Linux misst Qt nach dem Zeigen nach, unter Windows offenbar nicht. Der Test prüft deshalb den Stand nach dem Bau (ohne Fix rot) und nach dem Zeigen.
