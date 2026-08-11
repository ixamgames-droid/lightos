# SESSIONS.md — wer arbeitet gerade woran

<!-- Gepflegt von tools/session_claim.py. Branch `sessions`, wird NIE nach main
     gemergt. Von Hand editieren ist moeglich, verliert aber die Konflikt-
     erkennung: erst der abgelehnte Push macht sichtbar, dass jemand schneller
     war. Spielregeln: COORDINATION.md -->

## Aktive Claims

| Item | Sitzung | Branch | seit (UTC) | Dateien |
|---|---|---|---|---|
| _(frei)_ |  |  |  |  |

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

## Verlauf

- 2026-08-06T14:08Z A claim PROC-01
- 2026-08-06T15:06Z A done PROC-01
- 2026-08-11T14:52Z A claim OUT-51
- 2026-08-11T15:44Z A claim QA-53
- 2026-08-11T15:46Z A done OUT-51
- 2026-08-11T16:35Z A done QA-53
- 2026-08-11T16:35Z A claim QA-50
- 2026-08-11T16:56Z A claim QA-51
- 2026-08-11T17:02Z A done QA-50
- 2026-08-11T17:21Z A done QA-51
- 2026-08-11T17:21Z A claim OUT-52
- 2026-08-11T19:44Z A done OUT-52
- 2026-08-11T19:44Z A claim QA-54
- 2026-08-11T19:51Z A claim QA-55
- 2026-08-11T20:08Z A claim QA-52
- 2026-08-11T20:17Z A done QA-54
- 2026-08-11T20:26Z A done QA-55
- 2026-08-11T20:43Z A claim VIZ-51
- 2026-08-11T20:50Z A done QA-52
- 2026-08-11T21:09Z A done VIZ-51
