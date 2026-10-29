ID: ENG-44
Prioritaet: P3
Status: todo
Titel: Speed-Dial-Einstellungsdialog: Gitterwechsel waehlt factors[0] statt des Reset-Ziels

**Herkunft:** Nebenbefund der Gegenpruefung von ENG-32 (29.10.2026). Aendert man im Einstellungsdialog des Speed-Dials (`vc_speedial.py`, Dialog-Uebernahme) das Faktor-Gitter und faellt der aktive Faktor heraus, wird `factors[0]` gewaehlt statt `_reset_target()` (Gitterstufe naechst 1x). Ausserdem setzt der Dialog `_mult` getrennt aus dem eigenen Eingabefeld. Betrifft nur die Einrichtung, nicht die Bedienung in der Show. **Fertig, wenn:** der Dialog bei herausfallendem Faktor auf das Reset-Ziel springt und `_mult` nur aus einer Quelle kommt; Test, rot vor dem Fix.
