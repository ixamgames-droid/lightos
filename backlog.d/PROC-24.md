ID: PROC-24
Prioritaet: P2
Status: review
Status-Notiz: Dependabot-Sicherheitswarnungen und -PRs eingeschaltet (25.10.2026), Regel in COORDINATION.md §3; keine dependabot.yml
Titel: Dependabot-Sicherheitsupdates einschalten — nur Sicherheits-PRs, Regeln fuer den Merge

**Herkunft:** Entscheidung des Projektinhabers vom 25.10.2026 nach einem Patch-Audit. Das Repo bleibt oeffentlich (CI auf drei Plattformen ist nur oeffentlich kostenlos).
**Umgesetzt:** In den Repo-Einstellungen sind „vulnerability alerts“ und „automated security fixes“ an (`security_and_analysis.dependabot_security_updates = enabled`). Der Abhaengigkeitsgraph erkennt `requirements.txt`, `requirements-dev.txt` und die Actions (18 Pakete). Bewusst keine `.github/dependabot.yml` mit regelmaessigen Versions-Updates. `COORDINATION.md` §3 regelt den Merge: ueber die Warteschlange von A, CI und Privatsphaere-Gate gruen, PySide6-Spruenge erst nach Pruefung unter Linux, Windows x64 und Windows-ARM.
**Fertig, wenn:** Regel gemergt; der erste Dependabot-PR ist nach dieser Regel behandelt.
