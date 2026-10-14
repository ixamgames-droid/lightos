ID: XPLAT-23
Status: review
Status-Notiz: alle vier Windows-Scheiben erledigt 2026-09-02/03; die zwei Angleichungen auf der .sh-Seite gebaut 2026-10-14 (verify_loop.sh: lauter Abbruch bei unbrauchbarer Sperrdatei, Hinweise UNGESPERRT/umgelenkt), Tests tests/test_xplat23_sh_angleichung.py

**Entscheidung der Leitung (2026-10-14): beide Angleichungen gebaut, keine abgelehnt.**

(i) `verify_loop.sh` oeffnet die Voll-Suiten-Sperrdatei nicht mehr per `exec 9>… 2>/dev/null` mit stillem Rueckfall auf `return 0`. Ist sie nicht benutzbar (Ordner fehlt, Pfad ist ein Ordner, kein Schreibrecht), bricht der Volllauf mit Exit 2 ab, nennt Pfad und Grund und wartet nicht — wie `verify_loop.ps1` seit Scheibe 1. Begruendung: der Normalpfad (`--git-common-dir`) ist immer beschreibbar, der Abbruch trifft also nur eine Fehlbedienung; eine still nicht greifende Sperre ist schlimmer als keine (QA-53 „im Zweifel rot"). Gezielte Laeufe nehmen weiterhin keine Sperre und brechen darum auch nicht ab. Der Fall „kein flock" bleibt beim Hinweis (fehlendes Werkzeug, keine Fehlbedienung).

(ii) `LIGHTOS_VERIFY_NOLOCK` meldet „die volle Suite laeuft UNGESPERRT", ein gesetzter `LIGHTOS_LOCKFILE` meldet die Umlenkung — nur Ausgabe, kein anderes Verhalten.

**Nebenbefund, mitrepariert:** `exec 9>"$LOCKFILE" 2>/dev/null` machte auch die stderr-Umlenkung dauerhaft — jeder gesperrte Volllauf schrieb ab der Sperrnahme stderr ins Leere (betraf u. a. den Ein-Prozess-Lauf `LIGHTOS_VERIFY_SINGLE`). Jetzt wird das Oeffnen in einer Unterschale geprobt und danach ohne Umlenkung belegt.

Keine Laufzeitaenderung, keine neue Abhaengigkeit. 7 Verhaltenstests am echten Runner (DRYRUN, eigene Sperrdatei); Mutationsprobe mit dem alten Runner: 5 von 7 rot, die zwei Gegenproben gruen.

**Messblindheit heute (nur gezaehlt):** in den vier urspruenglich gezaehlten Dateien weiterhin 40 Methoden, die auf Windows still skippen (proc02c 22, proc02d 7, verify_loop_sperre 7, gate_webengine_lane 4); mit der neuen Datei 47; ueber alle Gate-Tests mit `os.name`-Guard 54 (zusaetzlich qa53 3, xplat43 2, cdx50 1, proc19 1). Die Windows-Seite pruefen weiterhin die 16 Verhaltenstests aus Scheibe 1–3.
