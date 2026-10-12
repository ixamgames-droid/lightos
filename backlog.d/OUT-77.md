ID: OUT-77
Prioritaet: P2
Status: review
Titel: Diagnosepaket nennt die Seriennummer eines uDMX-Adapters nicht mehr im Klartext

**Herkunft:** großer Bedientest QA-96 (Sitzung A), Block „Kleinkram“; umgesetzt von Sitzung D am 12.10.2026, sobald OUT-68 auf main war.
**Befund:** der Schlüssel eines uDMX-Adapters trägt seine Seriennummer (`16c0:05dc#Seriennummer`). Das Diagnosepaket schrieb ihn unverändert hinein — in die Zeilen „DMX-Ausgabe“ und „uDMX (USB)“ der Systeminfo und mit jeder Log-Zeile des Senders. Eine Seriennummer gehört zu genau einem Gerät; das Paket ist dafür gemacht, weitergegeben zu werden.
**Geliefert:** alle Texte des Pakets laufen durch `diagnose_log.anonymisiere`; dort werden Seriennummern jetzt gekürzt (`16c0:05dc#…8isP`): höchstens die letzten vier Zeichen bleiben und nie mehr als die halbe Nummer — genug, um zwei Adapter im selben Paket auseinanderzuhalten. Erfasst sind der Adapter-Schlüssel mit `#` und die Beschriftung „Seriennr. …“. Ein Schlüssel mit Anschluss (`2008:1066@1-2`) nennt keine Seriennummer und bleibt. Die Kürzung ist wiederholbar (die Systeminfo läuft zweimal hindurch). Der Dialog „Diagnosepaket erstellen“, `LIESMICH.txt` im Paket und INSTALL.md sagen es.
**Nicht geändert:** die Konfiguration (`universes.json`), der Dialog und das laufende Log nennen den Schlüssel weiter ganz — gekürzt wird beim Packen.
**Tests:** `tests/test_out77_diagnose_seriennummer.py` (18 Fälle; mit abgeschalteter Kürzung 7 rot), darunter das gepackte Paket als Ganzes.
