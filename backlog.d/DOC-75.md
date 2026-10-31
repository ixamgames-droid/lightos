ID: DOC-75
Prioritaet: P2
Status: review
Titel: Bilder/GIFs: Laser-Reiter und Kiosk-Streifen

Herkunft: Restliste aus DOC-74 (neu beschriebene Oberflächen ohne Bild) und Auftrag des Projektinhabers vom 29.10.: alle neuen Anleitungen bebildert und mit GIFs für Abläufe. Die Bilder entstehen reproduzierbar mit `tools/anleitungsbilder.py` in der Sandbox (neue Szenen-Datei `tools/anleitungsbilder/szenen_laser.py`, Szene `10_kiosk_streifen` in `szenen_vc.py`). Die Doku-Demo hat keinen Laser: die Szenen patchen den Laserworld EL-400RGB MK2 aus der LightOS-Bibliothek und für „Scharf“ einen zweiten als Ether-Dream-Laser (192.0.2.10); ohne Ausgabe-Thread wird nichts gesendet. Am Ende werden beide wieder entpatcht und der NOT-AUS gelöst.
- `docs/anleitung_laser/img/01_laser_reiter.png` — Laser-Reiter im Überblick (Sicherheitsleiste, Betriebsart mit Unterzeilen, Vorschau & Position, Mitte, Musterkacheln, Farbfelder), §2.
- `docs/anleitung_laser/img/02_statische_muster.png` — Statische Muster mit angeklickter Kachel, Nahaufnahme, §4.
- `docs/anleitung_laser/img/03_musik_hinweis.png` — gelber Hinweis neben „Betriebsart“ bei Musik, ausgegraute Bausteine, §3.
- `docs/anleitung_laser/img/04_notaus_ablauf.gif` — NOT-AUS auslösen, Kopfleiste „LASER NOT-AUS AKTIV“, „Scharf“ verweigert, Rückfrage „Laser-NOT-AUS lösen?“, gelöst (§8 Blackout, Ziel-Blackout und NOT-AUS).
- `docs/anleitung_vc/img/10_kiosk_streifen.png` — Kiosk-Streifen (GM, STOP ALL, BLACKOUT, LASER NOT-AUS) mit rotem NOT-AUS-Balken (LAS-41), VC-Anleitung Abschnitt Kiosk.
