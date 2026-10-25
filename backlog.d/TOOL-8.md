ID: TOOL-8
Prioritaet: P3
Status: done
Status-Notiz: erledigt 2026-10-02 in PR #860; Zeile nachgetragen am 20.10.2026
Nach: TOOL-7
Titel: Anleitungsbilder: `--alle` lief alle Anleitungen im selben Fenster — Zustand wanderte in die nächste

**Herkunft:** Sitzung A, auf der Tafel belegt am 02.10.2026; ohne Backlog-Zeile umgesetzt — nachgetragen beim Abgleich verlorener IDs am 20.10.2026.
**Befund:** `tools/anleitungsbilder.py --alle` lief alle Anleitungen in einem Fenster; Auswahl, BPM und „Wiederholen“ wanderten in die nächste Anleitung, `--pruefen` meldete falsche Abweichungen.
**Geliefert:** [PR #860](https://github.com/ixamgames-droid/lightos/pull/860) — eigener Unterprozess mit eigener Sandbox je Anleitung; Test `AlleFrischTest`.
**Fertig, wenn:** erledigt.
