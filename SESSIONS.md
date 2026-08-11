# SESSIONS.md — wer arbeitet gerade woran

<!-- Gepflegt von tools/session_claim.py. Branch `sessions`, wird NIE nach main
     gemergt. Von Hand editieren ist moeglich, verliert aber die Konflikt-
     erkennung: erst der abgelehnte Push macht sichtbar, dass jemand schneller
     war. Spielregeln: COORDINATION.md -->

## Aktive Claims

| Item | Sitzung | Branch | seit (UTC) | Dateien |
|---|---|---|---|---|
| OUT-51 | A | fix/out51-sendefehler-sichtbar | 2026-08-11T14:52Z | src/core/dmx/output_manager.py · src/core/dmx/sacn.py · src/core/dmx/enttec_pro.py · src/ui/main_window.py · src/ui/widgets/output_config.py |

## Blocker & Fallen

- 2026-08-06T14:18Z (A) PROC-01 gemergt: 4 private Dateien sind aus dem Tracking genommen. Ein git pull in einem Baum, in dem sie liegen, will sie LOESCHEN — Kopien liegen im Projektordner unter archiv/private_untracked_2026-08-06/. Vor dem Pull nachsehen.
- 2026-08-06T14:18Z (A) Volle Suite ist ab jetzt gesperrt (flock): zwei gleichzeitige Laeufe warten aufeinander statt sich gegenseitig rote Segmente zu machen. Gezielte Einzellaeufe laufen wie bisher sofort.
- 2026-08-06T15:06Z (A) Segment-Runner meldet eine falsche Abschlusszahl: '68/69 Segmente gruen', gefahren wurden 584 (gemessen). Rot/Gruen stimmt, nur der Zaehler nicht — er entsteht in der parallelen Spur und erreicht den Elternprozess nicht. Wer die Zahl liest, haelt einen Volllauf fuer einen Teillauf.
- 2026-08-06T15:06Z (A) OUT-50 und PROC-01 sind gemergt (#597, #598). Naechste freie P1: OUT-51, QA-50, QA-51.

## Verlauf

- 2026-08-06T14:08Z A claim PROC-01
- 2026-08-06T15:06Z A done PROC-01
- 2026-08-11T14:52Z A claim OUT-51
