ID: CDX-77
Prioritaet: P3
Status: review
Titel: Codex-Ernte: Handy-Gruppe — absolute Freeze-Taste bleibt an, neue Taste wird trotzdem aktiviert

**Herkunft:** Kommentar des automatischen Reviewers Codex zu PR #1288; Neuheiten-Audit von Sitzung A am 15.11.2026 bestaetigt.

**Befund:** Liegt eine Effekt-Aktions-Taste „Einfrieren" (absolute Aktion `freeze`, ENG-23) in einer Handy-Gruppe und ist ihr Effekt eingefroren, leuchtet sie. Ein Tipp vom Handy auf eine andere Taste der Gruppe versuchte sie per Tipp auszuschalten — das friert nur erneut ein, die Taste bleibt an. `_gruppe_ausfuehren` (src/ui/virtualconsole/vc_fernbedienung.py) meldete das nur im Log und loeste die neue Taste trotzdem aus: zwei Kacheln der Gruppe leuchteten. Am Stand nach der WEB-14-Nachbesserung und WEB-15 per eigener Probe noch vorhanden.

**Behebung:** `_ausschaltbar` lehnt Effekt-Aktions-Tasten mit absolutem Einschalt-Schluessel (`freeze`) als nicht ausschaltbar ab — der Druck wird mit `GRUPPE_BLOCKIERT` abgelehnt, bevor irgendeine Taste angefasst wird. Rueckfallnetz: leuchtet eine Gruppen-Taste nach dem Ausschalteversuch weiter, wird der neue Druck ebenfalls mit `GRUPPE_BLOCKIERT` abgelehnt statt ausgeloest. `toggle_freeze`/`unfreeze` bleiben normal ausschaltbar. Laser-Sperre, Halten, Blackout-Regeln (WEB-12/14/15) unveraendert. Test: tests/test_cdx77_handy_gruppe_freeze.py.

**Nachbesserung nach Pruefung:** Eine „Einfrieren an/aus"-Taste mit mehreren Effekten, von denen nur ein Teil eingefroren ist, leuchtet („einer reicht"), ein Tipp kehrt aber jeden Effekt einzeln um — sie bliebe an. Bisher fing das erst das Rueckfallnetz, nachdem die Effekte schon umgeschaltet waren. Jetzt gilt sie in der Vorpruefung als nicht ausschaltbar, solange nicht alle ihre Effekte stehen; der Druck wird abgelehnt, ohne etwas umzuschalten. Test: `test_gemischt_gefrorene_umschalt_taste_blockiert_vorher`.
