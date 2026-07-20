# Anleitungen-Audit — 2026-07-20 · Phase 3 Batch 3 (große Guides)

Fortsetzung von Batch 1 (#382) / Batch 2 (#383). Batch 3 prüft die **gehaltvollen
Übersichts-/Feature-Guides** gegen den Code.

## Ergebnis (Batch 3)

| Doc | Ergebnis |
|---|---|
| EFFEKTE.md | ⚠️→✅ §8-„Drop"-Rezept „+ Collection" (Button gibt's nicht) → „gemeinsam starten per VC-Mehrfach-Aktion"; §-Tab „Hilfe" → **„Assistent"**. §3 (18 Algorithmen inkl. Schachbrett) korrekt. |
| ANLEITUNG.md | ⚠️→✅ Programmer-Tab „Helper" → **„Assistent"** (7 Stellen). 8 Sektionen/Shortcuts/„✖ Clear ▾"/GM/TAP sonst aktuell. |
| anleitung_laser | ⚠️→✅ „Hilfe-Tab" → **„Assistent"-Tab**. |
| tutorial_matrix/TUTORIAL_LICHTSHOW.md | ✅ aktuell — Matrix-Styles/EFX/Chaser/VC-Drop-Karte exakt; live-generiertes Exemplar. |

## Zwei Fund-Cluster (korrigiert)

1. **Programmer-Tab heißt „Assistent"** (nicht „Helper"/„Hilfe"): per QOL-04 umbenannt
   (`programmer_view.py:445`; Kommentar :443-444: intern „Helper" → früher „Hilfe" beschriftet →
   irreführend → „Assistent"). ANLEITUNG.md sagte „Helper" (7×), EFFEKTE.md „Hilfe" (10×),
   anleitung_laser „Hilfe-Tab" (1×) → alle auf **„Assistent"** korrigiert (EFFEKTE.md-Intro behält
   die Historie). → Commit `dbfc913`.
2. **EFFEKTE.md §8 „+ Collection"**: der Funktionstyp Collection hat keinen sichtbaren „+"-Button
   (§5 sagt es korrekt; `programmer_view.py:578-589` bestätigt) → Rezept auf „gemeinsam starten per
   VC-Mehrfach-Aktion" umgestellt. → Commit `5db6e24`.

## Naming-Notiz (bewusst kein Fix)

ANLEITUNG.md §1 nennt Sektion 1 „Live View" — das ist der interne Code-Name
(`main_window.py:941/991`); der sichtbare Button ist „Bühne". „Live View" wird docs-weit
einheitlich als Term genutzt und ist kein klarer Fehler → gelassen.

## Offen (weitere Batches)

18_effekt_editor + restliche Widget-Docs (05-12,14-17,20); speed_bpm, vc_smartbuild/workflow,
3d_buehne; Show-Walkthroughs (komplettshow_2026/*, hochzeit_komplett/*).
