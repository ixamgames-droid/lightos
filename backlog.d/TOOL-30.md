ID: TOOL-30
Prioritaet: P3
Status: review
Titel: tools/app.ps1 gibt im Probelauf die Lizenz nur lesend mit (wie app.sh)

Aus einer Claude-Code-Shell ist ein App-Start ein Probelauf mit leerem Wegwerf-Datenordner (STAB-39). `tools/app.sh` gibt dafuer die Lizenzdatei des Rechners nur lesend mit (`LIGHTOS_LIZENZ`, gefunden ueber `paths.regulaerer_app_data_dir`); `tools/app.ps1` tat das nicht (aufgefallen am 01.11.2026 beim STAB-39-Test unter Windows 11 x64: ein `python main.py` aus der Agent-Shell braucht `LIGHTOS_LIZENZ`, sonst kommt statt des Hauptfensters der Dialog „Testlizenz erforderlich“). Jetzt `Set-ProbelaufLizenz` in `Start-App` (nur bei `CLAUDECODE=1`, eine gesetzte `LIGHTOS_LIZENZ` gewinnt, ohne Datei ein Hinweis) und der Unterbefehl `lizenz`, der die Entscheidung zeigt, ohne zu starten. Test `tests/test_tool30_app_ps1_lizenz.py` (Platzhalter-Datei, nie eine echte Lizenz; ohne Fix 5/5 rot).
