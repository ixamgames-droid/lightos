ID: BPM-33
Prioritaet: P3
Status: todo
Status-Notiz: entschieden 25.10.2026 — „Aus“ setzt den Takt auf 0; Vorgabe einer frischen App bleibt „PC-Audio“
Nach: BPM-32
Titel: Wechsel der BPM-Quelle auf „Aus“ lässt den zuletzt erkannten Takt stehen — der BPM-32-Hinweis erscheint dann nicht

**Herkunft:** Windows-Gegenprobe von Sitzung D zu BPM-32 (main c7743974), 25.10.2026.
**Befund:** Eine frische App startet mit Quelle „PC-Audio (Systemstandard)“, die sofort den Systemton hört und einen Takt setzt (gemessen 112 → 60 BPM nach 15 s). Umschalten auf „Aus“ stoppt die Erkennung, lässt den Takt aber stehen. Beim Play zeigt die Auto-Show deshalb KEINE Leiste (BPM-32 zeigt sie nur bei Takt 0) und taktet mit dem alten Wert.
**Zu entscheiden:** Soll „Aus“ den Takt auf 0 setzen (dann greift der BPM-32-Hinweis), soll der alte Takt bewusst stehen bleiben (eingefrorener Takt), oder soll die Leiste auch bei stehendem Fremdtakt erscheinen? Außerdem: Ist „PC-Audio“ als Vorgabe einer frischen App gewollt?
**Entscheidung des Projektinhabers (25.10.2026):** Der Wechsel auf „Aus“ setzt den Takt auf 0 — Beat-Effekte stehen, und beim Abspielen erscheint der BPM-32-Hinweis „Takt aus Titel übernehmen“. Die Vorgabe einer frischen App bleibt „PC-Audio (Systemstandard)“.
**Fertig, wenn:** umgesetzt, Test für den Wechsel auf „Aus“ mit vorhandenem Takt.
