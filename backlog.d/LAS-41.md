ID: LAS-41
Prioritaet: P2
Status: review
Titel: Kiosk: nach dem Auslösen des Laser-NOT-AUS fehlt die Klartext-Bestätigung (Statusleiste ist ausgeblendet)

**Herkunft:** Sichtprüfung von main im Sandkasten (offscreen, Demo-Show „Showcase Club-Nacht“), 19.10.2026, Sitzung A.
**Befund:** Im normalen Fenster erscheint nach dem Auslösen die rote Bestätigung „LASER NOT-AUS ausgelöst — alle Laser dunkel …“ (UXT-09) in der Statusleiste. Im Kiosk ist die Statusleiste ausgeblendet — der Bediener sieht nur den blinkenden Knopf „LASER NOT-AUS AKTIV“, keine Bestätigung in Worten.
**Fertig, wenn:** im Kiosk dieselbe Bestätigung sichtbar ist (z. B. kurz im Kiosk-Streifen oder als Overlay unter dem Streifen, ohne Sicherheitsknöpfe zu verdecken); Test im Kiosk-Fenster.

**Status-Notiz (19.10.2026, Sitzung A):** umgesetzt auf `fix/las41-kiosk-notaus-bestaetigung`. Im Kiosk erscheint dieselbe rote Bestätigung als Balken unter dem Kiosk-Streifen (überlagert den oberen Rand des Ansichtsstapels wie das Störungsbanner VCB-47, bei stehendem Banner darunter; verdeckt GM/STOP ALL/BLACKOUT/LASER NOT-AUS nicht, verschiebt nichts, schluckt Klicks), gleiche Dauer wie die Statuszeile (6 s, eine gemeinsame Konstante), weg auch beim Lösen. Kommt über `SyncEvent.LASER_ESTOP`, also auch bei Tastenkürzel/VC/MIDI. Normalfenster unverändert. Tests: `tests/test_las41_kiosk_notaus_bestaetigung.py` (Kiosk 1440×900 und 1000×640, Normalfenster). Sichtkontrolle im Sandkasten.
