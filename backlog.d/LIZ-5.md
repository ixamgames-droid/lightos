ID: LIZ-5
Prioritaet: P2
Status: blocked
Titel: LightOS-LICENSE und LGPL-2.1 §6 (FFmpeg, libusb) — vorerst unverändert, vor breiter Weitergabe klären

**Herkunft:** Frage von Sitzung D (19.10.2026, Tafel und #1125); Entscheidung des Projektinhabers 20.10.2026: vorerst so lassen.
**Befund:** LGPL-2.1 §6 verlangt für ein „work that uses the Library“, dass die Bedingungen des Gesamtwerks dem Empfänger erlauben, es für den eigenen Gebrauch zu ändern und zur Fehlersuche an solchen Änderungen zurückzuentwickeln. Die LightOS-LICENSE verbietet Änderungen (§2) und verweist nur allgemein auf die Rechte aus Drittlizenzen (§5). Technisch sind FFmpeg (über Qt Multimedia) und libusb (uDMX) eigene, zur Laufzeit geladene, austauschbare Dateien (THIRD_PARTY_NOTICES.md). Ob §5 die Bedingung erfüllt und ob §6 für ctypes- bzw. Plugin-Laden überhaupt greift, ist eine juristische Auslegung — keine Rechtsauskunft durch die Sitzungen. Dieselbe Frage stellt sich für Qt/PySide6 (LGPL-3.0 §4).
**Entschieden:** vorerst unverändert, solange LightOS nur an Tester geht. Das Risiko wächst mit jeder Weitergabe des Setups.
**Wieder aufnehmen, wenn:** LightOS breiter weitergegeben werden soll — dann Optionen: (a) schmale Ausnahme-Klausel in der LightOS-LICENSE (Änderung für den eigenen Gebrauch und Rückentwicklung zur Fehlersuche nur so weit LGPL-2.1 §6 / LGPL-3.0 §4 es verlangen; Microsoft-Laufzeit ausdrücklich ausgenommen, vgl. LIZ-4) und von einer Fachperson prüfen lassen; (b) Rechtsrat vor jeder Änderung; (c) libusb optional/nachinstallierbar, FFmpeg über ein anderes Qt-Multimedia-Backend (löst Qt-LGPL-3.0 nicht).
