ID: STAB-41
Prioritaet: P1
Status: todo
Titel: Nativer Absturz beim n-ten Dialog: Dialoge mit dem Hauptfenster als Eltern bleiben nach exec() liegen

Herkunft: Klick-Test der Oberflaeche durch Sitzung A am 16.11.2026. Beim Aufnehmen stuerzte in drei Laeufen hintereinander jeweils der 5. bzw. 6. modal geoeffnete und per reject() geschlossene Dialog im Konstruktor nativ ab (SIGSEGV): erst der OSC-Einstellungsdialog, nach Umsortieren der Input-Profil-Editor, dann der Gesten-Dialog. Die Stelle wandert mit der Reihenfolge; einzeln oeffnen sich alle drei. Mit deleteLater() nach jedem Dialog, zugestelltem DeferredDelete und gc.collect() ist der Absturz weg (2 Laeufe sauber). Vermutung: `Dialog(self).exec()` ohne deleteLater laesst die Dialoge als Kinder des Hauptfensters liegen, eine spaetere Garbage Collection trifft halb abgebaute native Objekte. Das kann auch in der echten App beim Oeffnen vieler Dialoge hintereinander auftreten.

**Zu tun:** (1) Nachstellen als Test (viele Dialoge nacheinander oeffnen und schliessen, in einem eigenen Prozess, Absturzrate messen, nicht einzelnen Stack-Frames nachjagen). (2) Alle Stellen `…Dialog(self).exec()` in `src/ui/main_window.py` und den Ansichten auf ein gemeinsames Muster umstellen (Hilfsfunktion: exec, danach deleteLater; oder WA_DeleteOnClose), ohne dass Ergebnisse nach dem Schliessen noch gelesen werden, wenn das Objekt weg ist. (3) Nebenbefund pruefen: `RuntimeError: Internal C++ object (QAction) already deleted` in `MainWindow._refresh_undo_labels` nach dem Schliessen des Musik-Fensters bzw. der Neue-Show-Rueckfrage.

**Fertig, wenn:** der Nachstell-Test ohne die Behebung abstuerzt und mit ihr 20 von 20 Laeufen gruen ist, und kein Dialog seine Ergebnisse verliert.
