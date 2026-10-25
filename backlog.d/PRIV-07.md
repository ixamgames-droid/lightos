ID: PRIV-07
Prioritaet: P3
Status: review
Status-Notiz: Doku-Beispiele auf 192.0.2.x/198.51.100.x (RFC 5737), Waechter test_priv07_doku_beispieladressen, keine Warnung in pruefe_oeffentlich (begruendet)
Titel: Beispiel-Netzadressen in Doku und Tests aus dem Dokumentationsbereich (192.0.2.x, RFC 5737)

**Herkunft:** Befund der Verwalter-Sitzung (Laptop), 25.10.2026, niedrig: `docs/anleitung_enttec_artnet/ANLEITUNG_ENTTEC_ARTNET.md` nennt mehrfach eine Adresse aus einem typischen Heimnetz-Bereich. Eine Bestandsaufnahme zeigt weitere private Adressen in Anleitungen und Tests (`192.168.x.y` in rund 15 Dateien) — die meisten sind erkennbare Beispiele, einzelne koennten aus dem echten Aufbau stammen.
**Vorschlag:** In Doku einheitlich Adressen aus 192.0.2.0/24 (TEST-NET-1, RFC 5737) bzw. 198.51.100.0/24 verwenden, Broadcast-Beispiele entsprechend; in Tests nur dort ersetzen, wo die Adresse nicht selbst Gegenstand ist (z. B. Erkennung privater Bereiche, LAN-IP-Ermittlung — dort bleiben private Bereiche noetig). Anleitungsbilder-Szenen und Bilder mit sichtbaren Adressen mitziehen. `pruefe_oeffentlich()` optional um einen Hinweis auf 192.168.178.x erweitern (nur Warnung, typischer Router-Bereich).
**Fertig, wenn:** keine Adresse aus einem echten Heimnetz-Bereich mehr in Doku-Beispielen; Tests unveraendert gruen; Waechter-Entscheidung dokumentiert.
