ID: BPM-29
Prioritaet: P3
Status: review
Status-Notiz: Cueliste hat jetzt `tempo_bus` ("" = global wie bisher, sonst Bus A-D); Auswahl "Takt:" in den Optionen der Cueliste, mit der Show gespeichert (Feld fehlt bei global, Alt-Shows unveraendert). Gekoppelte Listen schaltet der Bus pro ganzem Beat (Render-Thread nach advance_frame), der BPMManager laesst sie aus. Test tests/test_bpm29_cueliste_tempo_bus.py.
