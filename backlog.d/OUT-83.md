ID: OUT-83
Prioritaet: P3
Status: review
Status-Notiz: Gegenprobe unter Windows offen
Titel: Belegter COM-Port: Banner schickt den Bediener zum USB-Kabel, Verdachtsliste nennt den eigenen Starter

**Herkunft:** HW-6-Probe am echten Enttec unter Windows (Sitzung D mit dem Projektinhaber, 22.11.2026). Die Port-Warnung selbst funktioniert (Fehlercode 5, Meldung „ist bereits von einem anderen Prozess geoeffnet“ samt Verdachtsliste). Zwei Ungereimtheiten: (a) Die zweite Instanz zeigt zusaetzlich das Banner „Ausgabe gestoert: U1 Enttec (COMx) — Adapter nicht verbunden (USB-Kabel/Port pruefen)“; der Bediener sucht dann am Kabel, obwohl der Port nur belegt ist. Die Warnzeile behauptet ausserdem, es erscheine kein Fehler im Bild — das stimmt so nicht mehr. (b) Die Verdachtsliste enthaelt den python.exe-Starter des venv (Elternprozess der eigenen Instanz); `eigene_pid` filtert nur den App-Prozess selbst.

**Erledigt, wenn:** bei belegtem Port das Banner „Port von einem anderen Programm belegt“ (mit Hinweis auf die Liste) statt „Adapter nicht verbunden“ zeigt, die Warnzeile zum Bild passt und der eigene Starter/Elternprozess nicht in der Verdachtsliste steht; Tests unter Windows-Bedingungen nachgestellt (Fehlercode 5/32), Gegenprobe auf D.

**Geliefert:** (a) `port_check` merkt sich einen beim Anlegen als belegt erkannten Port samt Verdachtsliste; `OutputManager.ausgabe_status` nennt fuer einen nicht sendenden Enttec dann den Grund „Port von einem anderen Programm belegt — Verdacht: PID … (Verdachtsliste im Sitzungs-Log)“ statt „Adapter nicht verbunden“; sendet der Ausgang wieder, ist der Befund verworfen. Die Warnzeile im Log verweist jetzt auf dieses Banner. (b) `verdaechtige_aus_liste` nimmt die Elternkette der eigenen Instanz (venv-Starter, Startskript) aus, mit Kreis-Schutz gegen PID-Wiederverwendung; Kinder (eigene Worker) bleiben Verdacht. Test `tests/test_out83_port_belegt_meldung.py` stellt Fehlercode 5/32 unter Linux nach.
