ID: LAS-39
Prioritaet: P1
Status: todo
Titel: Fällt die Geräte-Datenbank beim Patchen aus, gilt ein Kombigerät im Kurz-Modus bei einem danach ausgelösten Laser-NOT-AUS nicht als Laser

**Herkunft:** offene Grenze aus dem Entwurf zu LAS-38 („nein, ohne zu merken“), als eigenes Item abgelegt am 14.10.2026. Sicherheitsrelevant.
**Befund:** LAS-38 erkennt Kombigeräte im Kurz-Modus ohne eigenen Laserkanal über die Auskunft des Profils (ein anderer Modus hat einen Laserkanal, oder das Profil hat den Typ `laser`). Ist die Geräte-Datenbank beim Patchen nicht erreichbar, fehlt diese Auskunft. Wird der LASER NOT-AUS erst DANACH frisch ausgelöst, zählt das Gerät nicht als Laser: Es läuft weiter, und der Zähler am Knopf nennt es nicht. Stand der NOT-AUS beim Patchen bereits, hält die klebrige Maske das Gerät dunkel — betroffen ist also nur der frisch ausgelöste Fall.
**Nachstellen:** In einer Sandbox ein Kombigerät im Kurz-Modus patchen (z. B. Chauvet GigBAR 2 im Modus „3-channel“), während die Profil-Abfrage scheitert (Abfrage im Test durch einen Fehler ersetzen). Danach den LASER NOT-AUS auslösen und das gerenderte Bild sowie den Zähler prüfen: Das Gerät bleibt an und wird nicht gezählt.
**Fertig, wenn:** ein Gerät, dessen Profil-Auskunft fehlt, im Zweifel als Laser behandelt wird, ODER die Auskunft nachgeholt wird, sobald die Datenbank wieder erreichbar ist, und das Gerät spätestens beim nächsten NOT-AUS dunkel bleibt. Die fehlende Auskunft ist für den Betreiber sichtbar (Hinweis beim Patchen oder im Log). Ein Test deckt den Fall „Datenbank fällt beim Patchen aus, NOT-AUS danach“ ab und ist ohne die Änderung rot.
