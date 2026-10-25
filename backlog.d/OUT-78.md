ID: OUT-78
Prioritaet: P3
Status: blocked
Status-Notiz: wartet auf Entscheidung des Projektinhabers (Code-Signing-Zertifikat) und einen Test am uDMX unter Windows
Nach: OUT-77
Titel: Treiber im Setup (Stufe 2 nach OUT-76): Klärung — heute keinen Treiber mitliefern, Wege offen

**Herkunft:** Vorschlag von Sitzung D an A, 12.10.2026 („Stufe 2“ zu OUT-76, nur geklärt, nichts gebaut), mit dem Angebot, das als OUT-78 „Treiber im Setup: Klärung“ abzulegen; die Zeile wurde nie angelegt — nachgetragen am 20.10.2026.
**Ergebnis der Klärung:** Empfehlung, heute für keine Adapterfamilie einen Treiber ins Setup zu legen; der Weg „erkennen, erklären, verlinken“ (OUT-76, PR #1063) bleibt der Hauptweg. **uDMX/CYL-6602 (rohes USB):** Treiber ist WinUSB (Teil von Windows); es fehlt nur die Zuordnung (INF + signierter Katalog). Hürde ist die Signatur — ohne gekauftes Code-Signing-Zertifikat (auf ARM64 nur WHQL) geht es nicht; Zadig/libwdi installiert selbstsignierte Zertifikate dauerhaft und ist GPLv3 bzw. LGPLv3, scheidet zum Einbetten aus. Geteilte Kennung 16c0:05dc nicht aufnehmen (würde fremde Bastelgeräte umhängen). **Enttec/Open DMX/DMXking (FTDI):** WHQL-signiert, aber die FTDI-Lizenz erlaubt die Weitergabe nicht ohne Weiteres.
**Offene Wege:** (i) so lassen (Stand OUT-76); (ii) Projektinhaber schafft ein Code-Signing-Zertifikat an — dann INF + Katalog für 2008:1066 signieren (~20 KB im Setup, Installation per pnputil nur mit Häkchen, sauber entfernbar); (iii) Microsoft-Weg ohne Fremdprogramm (Geräte-Manager → „WinUsb Device“) — ob libusb den Adapter dann öffnen kann, muss jemand mit Adapter unter Windows ausprobieren; geht es, ersetzt das Zadig in der Anleitung.
**Fertig, wenn:** der Projektinhaber über (ii) entschieden hat und (iii) am Adapter geprüft ist; Ergebnis in Anleitung „Ausgabe einrichten“ und INSTALL.md.
