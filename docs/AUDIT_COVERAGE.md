# Audit-Coverage-Tracker (DOC-10)

> **Zweck:** Auf einen Blick sehen, welche Subsysteme wann/womit auditiert wurden —
> damit die nächste sinnvolle Audit-Runde sofort sichtbar ist und **Doppel-Audits
> vermieden** werden. Bisher musste der Loop das aus Backlog/Changelog rekonstruieren.
>
> **Pflege:** Wer ein Subsystem auditiert, trägt hier die Zeile nach (Doc-Link + Datum
> + Status). `tests/test_audit_coverage_docs_exist.py` prüft, dass jede hier verlinkte
> Audit-Doc wirklich existiert (fängt Umbenennungen/Tippfehler).
>
> **Status-Werte:** `auditiert` (dediziertes Audit-Doc, Funde abgearbeitet) ·
> `teilweise` (nur im übergreifenden Sweep oder in Bug-Jagd-Runden mitgeprüft, kein
> dediziertes Doc) · `offen` (noch kein Audit).

**Übergreifend:** Der [Feature-Verifikations-Sweep 2026-07-09](FEATURE_VERIFICATION_2026_07_09.md)
inventarisierte **21 Subsysteme (519 Funktionen, 85 high-risk)** und lieferte einen
priorisierten Live-Test-Plan; er ist die Basis-Abdeckung für alles unten. Der
allgemeine [Projekt-Audit](PROJECT_AUDIT.md) hält den Gesamtstand.

## Ausgabe / Netzwerk / Engine

| Subsystem | Audit-Doc | Datum | Status |
|---|---|---|---|
| DMX-Ausgabe (Universe/Render-Pfad) | [DMX_OUTPUT_AUDIT](DMX_OUTPUT_AUDIT_2026_07_08.md) | 2026-07-08 | auditiert |
| DMX-Eingang | [DMX_INPUT_AUDIT](DMX_INPUT_AUDIT_2026_07_08.md) | 2026-07-08 | auditiert |
| Multi-Universe / Ausgabe-Routing | [MULTI_UNIVERSE_AUDIT](MULTI_UNIVERSE_AUDIT_2026-07-13.md) | 2026-07-13 | auditiert |
| Render-/Engine-Pipeline | [RENDER_AUDIT](RENDER_AUDIT_2026_07_08.md) | 2026-07-08 | auditiert |
| OSC / Timecode | [OSC_TIMECODE_AUDIT](OSC_TIMECODE_AUDIT_2026_07_08.md) | 2026-07-08 | auditiert |
| Web-Remote | [WEB_REMOTE_AUDIT](WEB_REMOTE_AUDIT_2026_07_08.md) | 2026-07-08 | auditiert |
| MIDI | [MIDI_AUDIT](MIDI_AUDIT_2026-07-13.md) | 2026-07-13 | auditiert |
| MIDI ↔ Virtual-Console-Konflikte | [MIDI_VC_CONFLICT_AUDIT](MIDI_VC_CONFLICT_AUDIT_2026-07-13.md) | 2026-07-13 | auditiert |
| Threading / Access-Violation-Sicherheit | [THREADING_AV_AUDIT](THREADING_AV_AUDIT_2026-07-13.md) | 2026-07-13 | auditiert |
| Netzwerk-Egress-Interface (Multi-NIC) | — (NET-04 offen, Produktentscheidung) | — | offen |

## Show / Fixtures / Audio

| Subsystem | Audit-Doc | Datum | Status |
|---|---|---|---|
| Show-Datei (Persistenz / Round-Trip) | [SHOW_FILE_AUDIT](SHOW_FILE_AUDIT_2026_07_08.md) | 2026-07-08 | auditiert |
| Fixture-Import / -Profile | [FIXTURE_IMPORT_AUDIT](FIXTURE_IMPORT_AUDIT_2026-07-13.md) | 2026-07-13 | auditiert |
| Audio / BPM | [AUDIO_BPM_AUDIT](AUDIO_BPM_AUDIT_2026-07-13.md) | 2026-07-13 | auditiert |
| Laser | — (Epic in Arbeit, [LASER_PLAN](LASER_PLAN.md); Hardware-Verifikation offen) | — | teilweise |

## UI / Bedienung

| Subsystem | Audit-Doc | Datum | Status |
|---|---|---|---|
| UI / Visuell (Layout, Lesbarkeit) | [UI_VISUAL_AUDIT](UI_VISUAL_AUDIT_2026_07_02.md) | 2026-07-02 | auditiert |
| UI-Verifikations-Checkliste (laufend) | [UI_VERIFICATION_CHECKLIST](UI_VERIFICATION_CHECKLIST.md) | laufend | teilweise |
| Virtual Console | [VC_AUDIT](VC_AUDIT_2026_06_30.md) | 2026-06-30 | auditiert |
| Anleitungen / Doku | [ANLEITUNGEN_AUDIT](ANLEITUNGEN_AUDIT_2026-07-12.md) | 2026-07-12 | auditiert |
| Programmer / Effekte / Matrix / Chaser | via [FEATURE_VERIFICATION](FEATURE_VERIFICATION_2026_07_09.md) + Bug-Jagd R1/R2 (BACKLOG) | 2026-07-09/12 | teilweise |
| 3D-Visualizer | via Bug-Jagd + VIZ-14-Arbeit (BACKLOG/CHANGELOG); kein dediziertes Doc | 2026-07 | teilweise |

## Nächste sinnvolle Audits (aus den Lücken)

- **3D-Visualizer** — dediziertes Audit-Doc fehlt (bisher nur Bug-Jagd + Feature-Arbeit); nach den VIZ-14-Slices ein guter Kandidat.
- **Programmer/Effekte** — nur übergreifend + in Bug-Jagd mitgeprüft; ein fokussiertes Audit wäre wertvoll (viel high-risk laut Feature-Verifikation).
- **VC-Audit auffrischen** — der letzte dedizierte VC-Audit ist von 2026-06-30 (vor VC3D-01/02/03 + diversen VC-Bug-Fixes).
- **QA-LIVE** — der Live-Klick-Durchlauf der 85 high-risk-Funktionen ist teils erledigt; Rest per Computer-Use (siehe BACKLOG QA-LIVE).
