# SESSIONS.md — wer arbeitet gerade woran

<!-- Gepflegt von tools/session_claim.py. Branch `sessions`, wird NIE nach main
     gemergt. Von Hand editieren ist moeglich, verliert aber die Konflikt-
     erkennung: erst der abgelehnte Push macht sichtbar, dass jemand schneller
     war. Spielregeln: COORDINATION.md -->

## Aktive Claims

| Item | Sitzung | Branch | seit (UTC) | Dateien |
|---|---|---|---|---|
| QA-69 | B | fix/qa69-windows-testannahmen | 2026-08-31T20:02Z | tests/test_fm26_generator_panel_geometrie.py,tests/test_qa60_datenordner_unberuehrt.py,tests/test_qa53_segment_zaehler_ehrlich.py,tests/test_verify_loop_sperre.py,tests/test_zeitbomben_gate.py |

## Blocker & Fallen

- 2026-08-06T14:18Z (A) PROC-01 gemergt: 4 private Dateien sind aus dem Tracking genommen. Ein git pull in einem Baum, in dem sie liegen, will sie LOESCHEN — Kopien liegen im Projektordner unter archiv/private_untracked_2026-08-06/. Vor dem Pull nachsehen.
- 2026-08-06T14:18Z (A) Volle Suite ist ab jetzt gesperrt (flock): zwei gleichzeitige Laeufe warten aufeinander statt sich gegenseitig rote Segmente zu machen. Gezielte Einzellaeufe laufen wie bisher sofort.
- 2026-08-06T15:06Z (A) Segment-Runner meldet eine falsche Abschlusszahl: '68/69 Segmente gruen', gefahren wurden 584 (gemessen). Rot/Gruen stimmt, nur der Zaehler nicht — er entsteht in der parallelen Spur und erreicht den Elternprozess nicht. Wer die Zahl liest, haelt einen Volllauf fuer einen Teillauf.
- 2026-08-06T15:06Z (A) OUT-50 und PROC-01 sind gemergt (#597, #598). Naechste freie P1: OUT-51, QA-50, QA-51.
- 2026-08-11T15:37Z (A) OUT-51 als PR #599 offen. Lokales Segment-Gate war in ZWEI Laeufen rot an je ANDEREN Dateien, alle isoliert gruen: die geteilte fixtures.db (journal_mode=delete, per LIGHTOS_FIXTURE_DB bewusst die echte Bibliothek) gegen drei parallele Segmente. Als QA-53 (P1) erfasst. Wer jetzt ein rotes Segment sieht: erst isoliert nachfahren, bevor der eigene Diff verdaechtigt wird.
- 2026-08-11T15:46Z (A) OUT-51 gemergt (#599). CI-Volllauf gruen (7m28s, segmentiert) — waehrend das LOKALE Gate zweimal an je anderen Dateien riss. Der Unterschied ist die gewachsene lokale fixtures.db; CI startet mit einer frischen. Ist QA-53.
- 2026-08-11T16:32Z (A) QA-53 GEKLAERT und behoben (PR folgt): Ursache war NICHT die fixtures.db, sondern tests/test_verify_loop_sperre.py — es startete den Runner ohne Argumente, also die VOLLE Suite, mitten im Gate. Gemessen 95 pytest-Prozesse auf EINEM geerbten LIGHTOS_SHOW_DB. Schlimmer: der innere Lauf raeumt .pytest_segments per rm -rf, damit verschwinden auch die ROTEN Zeilen -> das Gate konnte GRUEN melden, obwohl Segmente rot waren.
- 2026-08-11T17:05Z (A) QA-50 gemergt (#601). QA-51 im Gate. Neu erfasst: QA-54 (Testsuite schreibt in die echte fixtures.db, Rueckstand TEST-DualTilt) und QA-55 (Doku-Link-Pruefer sieht 20 von 280 Dateien nicht, ignoriert Anker; Backlog-Lint-Guard hat dieselbe Blindstelle wie sein eigenes Muster).
- 2026-08-11T20:37Z (A) Stand 11.08. Abend: OUT-51/52, QA-50/51/53/54/55 gemergt (#599-#605). QA-52 (7 von 9 Test-Umbauten) im Gate. Neu erfasst: QA-56 (Rest aus QA-52), LAS-HW-VERIFY (war eine Backlog-Zeile OHNE ID und damit fuer Queue/Lint unsichtbar). Drei P2/P3-Items laufen parallel in Agenten-Worktrees.
- 2026-08-11T21:13Z (A) NEUER BEFUND (aus TOOL-SMOKEDIM): tools/build_grosses_rig.py erzeugt SECHS Geraete, die nie hell werden — 4 Moving Heads (Master-Dimmer CH56/67/78/89) und 2 Spider (CH96/110). Per Render-Probe bestaetigt: die Dimmer bleiben ueber alle Funktionen der Show auf 0, waehrend Nachbarkanaele arbeiten. Ursache: die Geraete haben ein Farbrad statt RGB, ein faerbender Matrix-Effekt erreicht ihren Dimmer nicht. Wird eigenes Item, sobald der laufende PR durch ist.
- 2026-08-11T21:28Z (A) CI-FLAKE (bestand schon vor heute, auf main reproduziert): tests/test_sacn_loopback.py::test_sequence_number_increments_on_wire faellt sporadisch mit Off-by-one (13!=14, 160!=161). Der Test verlangt LUECKENLOSE UDP-Zustellung (exakt +1 je Frame) — UDP sichert das nicht zu, auch nicht auf Loopback unter Last (CI faehrt 3 Segmente parallel). Sein eigener Kommentar sagt 'streng monoton (mod 256)', die Umsetzung ist strenger als die Absicht. Lokal 3/3 gruen. Wird eigenes Item.
- 2026-08-11T21:34Z (A) Stand Abend 11.08.: 13 Items gemergt (#599-#608). Drei PRs offen und in CI: #609 TOOL-SMOKEDIM, #610 CI-Fix sACN-Flake + UI-50-Nachtrag, #611 DOC-13. Der CI-Flake in test_sacn_loopback ist mit #610 behoben (verlangte lueckenlose UDP-Zustellung; jetzt streng monoton + Puffer leeren, echte Regressionen weiterhin rot). Offen im Backlog: FM-21, FM-22, VIZ-16, VIZ-50, VIZ-52, VCG-02, FM-14, QA-56, LAS-HW-VERIFY (Hardware).
- 2026-08-11T21:43Z (A) PR #609 (TOOL-SMOKEDIM) ist fertig, CI war gruen, Merge-Konflikt geloest und neu gepusht — wartet nur noch auf den CI-Durchlauf und kann dann gemergt werden. Alles andere von heute ist auf main.
- 2026-08-12T09:48Z (A) Lauf 11./12.08. abgeschlossen: 23 Items gemergt (#599-#619). Zuletzt: FM-21 (nach adversarialer Nachbesserung), QA-56, VIZ-52, RIG-DUNKEL, TOOL-SMOKEDIM, UI-50, DOC-13, Konfliktmarker-Waechter. VIZ-16 und VCG-02 stehen als 'decision' (Produktentscheidung noetig, nicht geraten). Neue Items: FM-HEADLAYOUT-B, VIZ-52-TOOLTIP, QA-57, RIG-DUNKEL-Nebenbefunde. Offen: VIZ-50, FM-14, QA-57, FM-HEADLAYOUT-B, VIZ-52-TOOLTIP.
- 2026-08-31T14:30Z (A) VIZ-55 Slice 1 gemergt (#685): das Zielen invertierte Pan ZWEIMAL, der Strahl zeigte nach hinten (86,5 Grad). Zweiter, gekoppelter Fehler: der 3D-Beam kennt invert/swap nicht — beide hoben sich im Bild auf, deshalb war es am Bildschirm unsichtbar. Neu: VIZ-61 (8-Bit-Zielen, Vorbedingung fuer VIZ-55 Stufe A), OUT-55 (nur Kopf 0 wird invertiert), QA-66. ACHTUNG QA-66: tests/test_qa58_bibliothek_schema_unberuehrt.py ist LOKAL rot, sobald shows/Farb_FX_VC_Show.lshow existiert (gitignored) — auf unveraendertem main reproduziert, CI ist gruen. Nicht den eigenen Diff verdaechtigen.
- 2026-08-31T19:10Z (A) STABILITAETS-DURCHLAUF 2026-08-31 ausgewertet: 27 neue Items im BACKLOG (UI-57..60, STAB-23..27, ENG-14..24, NET-11..13, OUT-56, FM-38/39, QA-67). ACHTUNG Pruefstatus: Panik- und Persistenz-Funde sind adversarial gegengeprueft, die aus Programmer/Ausgabe/Effekte/QA-LIVE-Rest NICHT (Gegenprobe lief in ein Session-Limit) — die sind einzeln markiert, vor dem Fix selbst nachmessen. A nimmt UI-57 (P1, Panik-Taster haengt nach Bankwechsel). Frei und gegengeprueft: STAB-23 (P1), UI-58, ENG-18, STAB-24/25/26, FM-38/39. WARNUNG: DOC-10 laeuft ab jetzt mit der ECHTEN App (Computer Use, Davids Vorgabe 31.08.) — wer gleichzeitig ein headless-Gate faehrt, bekommt instabile view-bauende Segmente (XPLAT-14). Vorher hier abstimmen.
- 2026-08-31T19:30Z (B) WINDOWS-SITZUNG (B): der erste Claim von einem Windows-Rechner hat diese Tafel zerstoert - nicht den Inhalt, den DATEINAMEN: im Baum lag 'SESSIONS.md' mit angehaengtem CR, 'git show origin/sessions:SESSIONS.md' meldete 'does not exist'. Lautlos, der Push war erfolgreich. Ursache: text=True ohne encoding in session_claim._git uebersetzt auf Windows den LF der mktree-Zeile nach CRLF. Tafel repariert (Commit 2e540b1), Fix als PR #686 (XPLAT-20). ACHTUNG: encoding='utf-8' allein reicht NICHT - gemessen bleibt CRLF, nur der Byte-Weg hilft. Bis #686 gemergt ist: von Windows aus nur mit gesetztem PYTHONUTF8 claimen ODER die Tafel danach pruefen.

## Verlauf

- 2026-08-11T19:51Z A claim QA-55
- 2026-08-11T20:08Z A claim QA-52
- 2026-08-11T20:17Z A done QA-54
- 2026-08-11T20:26Z A done QA-55
- 2026-08-11T20:43Z A claim VIZ-51
- 2026-08-11T20:50Z A done QA-52
- 2026-08-11T21:09Z A done VIZ-51
- 2026-08-12T07:46Z A claim RIG-DUNKEL
- 2026-08-12T08:09Z A done RIG-DUNKEL
- 2026-08-26T18:16Z B claim STAB-22
- 2026-08-26T18:44Z B done STAB-22
- 2026-08-26T18:48Z B claim VIZ-59
- 2026-08-26T19:14Z B done VIZ-59
- 2026-08-26T20:26Z B claim VIZ-60
- 2026-08-26T20:42Z B claim UI-55
- 2026-08-26T22:46Z B claim OUT-53
- 2026-08-26T23:10Z B done UI-55
- 2026-08-26T23:32Z B done OUT-53
- 2026-08-26T23:44Z B done VIZ-60
- 2026-08-26T23:45Z B claim TOOL-SPOT90
- 2026-08-27T00:31Z B done TOOL-SPOT90
- 2026-08-27T04:35Z B claim OUT-54
- 2026-08-27T04:56Z B done OUT-54
- 2026-08-30T19:39Z A claim VIZ-55
- 2026-08-31T14:30Z A uebergeben VIZ-55
- 2026-08-31T19:10Z A claim UI-57
- 2026-08-31T19:10Z B claim XPLAT-20
- 2026-08-31T20:02Z B done XPLAT-20
- 2026-08-31T20:02Z B claim QA-69
- 2026-08-31T20:16Z A done UI-57
