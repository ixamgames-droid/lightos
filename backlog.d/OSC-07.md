ID: OSC-07
Prioritaet: P3
Status: todo
Status-Notiz: Befund von Sitzung D (Windows, 25.10.2026) zu #1149
Nach: OSC-06
Titel: OSC-Zuordnungen: Spalte „Ziel“ zu schmal — Auswahl zeigt nur „E“/„Ex“ bei 125/150 %

**Herkunft:** Windows-Gegenprobe von Sitzung D zu PR #1149 (OSC-06), 25.10.2026, Windows 11 x64.
**Befund:** Im Dialog „OSC-Zuordnungen & Rückmeldung“, Reiter Eingang, hat das Auswahlfeld der Spalte „Ziel“ nur 10 px Textfläche; „Executor-Fader“ braucht 85 px. Ursache vermutlich wie bei NET-15 (#1138): `ResizeToContents` misst vor `setCellWidget` nur den Kopftext; die Stretch-Spalte „Adresse“ nimmt den Rest. Kleinigkeit: Platzhalter „Name oder Id“ in „Funktion“ wird gekürzt (75 px Feld, 81 px Text).
**Fertig, wenn:** Spaltenbreite aus dem `sizeHint` einer Mess-Combo mit allen Einträgen (wie `dmx_fernsteuerung_box.py` seit #1138), Test der Lesbarkeit bei 12/15/18 px Schrift (ohne Fix rot), Gegenprobe unter Windows.
