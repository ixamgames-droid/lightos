ID: PROC-26
Prioritaet: P2
Status: review
Status-Notiz: Zeitlimit des Linux-CI-Jobs 45 -> 60 min (Freigabe Projektinhaber 27.10.2026)
Titel: Linux-CI-Job läuft ins 45-min-Zeitlimit — ein komplett grüner Lauf wurde abgebrochen

**Herkunft:** PR #1040 am 27.10.2026: „Linux — volle Suite“ meldete `1124/1124 Segmente gruen`, danach „The operation was canceled“ bei 45 min 8 s. Die Linux-Jobs auf main brauchten in den letzten Läufen 26, 45, 28, 41 und 42 Minuten — die Suite wächst, und parallele Läufe teilen sich die Runner.
**Umgesetzt:** `.github/workflows/ci.yml`, Job `linux`: `timeout-minutes` von 45 auf 60, mit Begründung im Kommentar. Keine weitere Änderung an Workflow-Rechten, Actions oder Secrets.
**Später zu prüfen:** Laufzeit der Suite senken (langsamste Segmente, Parallelität), bevor auch 60 min knapp werden.
