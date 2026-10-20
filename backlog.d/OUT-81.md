ID: OUT-81
Prioritaet: P3
Status: todo
Titel: by-id-Namen im Port-Feld anbieten, sobald OUT-64 sie normalisiert

**Herkunft:** zweite Gegenprüfung zu OUT-80 (Befund 1). OUT-80 bot unter Linux im Reiter Enttec Pro USB zusätzlich die stabilen Namen aus `/dev/serial/by-id` an; die NOT-AUS-Sperre je Ausgabeweg (OUT-64) hielt einen by-id-Namen und `ttyUSB1` desselben Anschlusses für zwei Wege — Laser-Universum am by-id-Namen, danach ein anderes Universum an `ttyUSB1` → Laser-Adresse 255 statt 0 (Wegwerf-Test). Entscheidung A: in OUT-80 zurückgenommen.
**Stand:** seit OUT-80 nimmt `OutputManager._wege_enttec` zu jedem Portnamen zusätzlich den normalisierten Schlüssel (`enttec_pro._port_key`: Symlink aufgelöst, Windows Großschreibung) — ein von Hand eingetippter by-id-Name trifft dieselbe Sperre wie `ttyUSB1`. Noch nicht auf denselben Anschluss normalisiert: die Doppel-Prüfung der Adapter-Zeilen (OUT-74, `adapter_zeilen.schluessel`), `close_enttec_on_port`/`_enttec_belegt_port`, `output_config._gleicher_port` (Portwechsel = neue Seriennummer) und die Zuordnung „Verbinden“ → Seriennummer.
**Vorschlag:** diese Stellen auf `_port_key` umstellen (je mit Test: by-id und tty desselben Anschlusses in zwei Zeilen, Umzug, NOT-AUS bleibt 0), dann `/dev/serial/by-id` im Port-Feld anbieten (Klasse des Anschlusses erben, vorgewählt bleibt der Anschluss selbst; im Test auf einen leeren Ordner umlenken, damit ein echter Adapter am Testrechner nichts ändert). Diagnosepaket kürzt by-id-Namen schon (OUT-80).
**Fertig, wenn:** by-id-Namen im Port-Feld stehen und jede Stelle, die zwei Portnamen vergleicht, sie als denselben Anschluss erkennt; NOT-AUS je Ausgabeweg nirgends schwächer (Test).
