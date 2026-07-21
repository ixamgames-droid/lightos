# Anleitungen-Audit 2026-07-21 (Phase 4) — offene Guides code-verifiziert

Fortsetzung des Anleitungen-Audits (nach Phasen 1–3, PRs #380–#387). Ziel: die bis
dahin **noch nicht einzeln auditierten** Nutzer-Guides gegen den aktuellen Code prüfen
und nur echte Drift korrigieren.

## Methode

- **34 offene Guides** (14 `vc_widgets/*`-Widget-Docs + 16 Cluster-Guides + 4 Einzeldateien)
  je von einem eigenen Audit-Agenten gegen `src/` geprüft (Multi-Agent-Workflow).
- **Jeder gemeldete Drift-Fund** wurde von einem zweiten Agenten **adversarial gegengeprüft**
  (unabhängige Code-Recherche, Ziel: den Fund widerlegen) → nur bestätigte, nutzer-irreführende,
  fixbare Funde wurden übernommen.
- Ergebnis: **31 bestätigte Funde in 15 Guides**, **19 Guides CLEAN**, **3 Funde als
  False Positive verworfen**. Plus **1 nachträglicher Fund** (farbmatrix „Style:"→„Stil:",
  vom Auditor übersehen, per Sanity-Grep gefunden).

## Bestätigte Fixes (16 Dateien)

| Guide | Funde | Kern der Korrektur |
|---|---|---|
| `vc_widgets/02_fader` | 5 | Modus **Feature-Dimmer (Gruppe)** fehlte ganz (13 statt 12 Modi); Reichweite gilt auch für *Submaster*; Programmer-Attribut-/Wert-Teilband-Felder + eigenes **Playback Executor-Slot**-Feld ergänzt |
| `vc_widgets/06_encoder` | 2 | 60 px = voller Wertebereich (nicht „eine Schrittweite"); Bodenzeile zeigt Parameter-**Label** (z. B. „Geschwindigkeit"), nicht den Roh-Key |
| `vc_widgets/07_stepper` | 1 | Stepper unterstützt **diskrete** Parameter (int/select/bool), nicht nur Ganzzahlen |
| `vc_widgets/09_chase_liste` | 1 | Hat inzwischen einen eigenen Toolbar-Knopf „Chase-Liste" |
| `vc_widgets/20_bpm_manager` | 2 | Sichtbarer Umschalter heißt **BPM-Quelle** (Live-Audio/Lied-Analyse/Manuell), nicht AUTO/MANUAL; Genre-Preset sitzt unter BPM-Quelle/Analyse-Song |
| `anleitung_vc_elemente` | 2 | Toolbar bietet **16** Typen (inkl. Tempo-Controller, Live-Edit); Drop-Karten-Text aktualisiert |
| `anleitung_vc_workflow` | 2 | Drop-Karten-Text; Feld heißt „Funktion / Chase (Name):" |
| `anleitung_efx` | 2 | Geräte-Box: „Gerät(e)"/„Spider"/„keine beweglichen Geräte" statt „Moving Head(s)" |
| `anleitung_colorfade_vc` | 7 | COLORFADE-Parameter heißt **Übergangs-Pause** (`crossfade_hold`), nicht „Halte-Zeit"; „Programme→Programmer"; „Fade ein+aus (s)" |
| `anleitung_farbchase` | 2 | Checkbox „Farbe pro Runde wechseln" liegt in Gruppe **Farben**; Feld heißt **Stil:** |
| `anleitung_musik_sync` | 1 | **BPM-Quelle „Live-Audio" / Audio-Eingang PC-Audio** statt „Modus AUTO (Audio) + Quelle" |
| `anleitung_3d_buehne` | 1 | Falle VIZ-FIX-DECIMAL ist **behoben** — Positions-/Ausrichtungsfelder akzeptieren Punkt UND Komma |
| `ANLEITUNG_TEMPO_SYNC` | 1 | Speed-Dial-Ziel heißt „Effekt ×½/×2 (Multiplier)" |
| `MULTIPLIKATOR_DIAL` | 1 | Effektwahl über die **„Steuert"-Liste** (+ Funktion/Effekt hinzufügen), nicht über ein „Funktion/Chase (Name)"-Dropdown |
| `LIVE_EDIT_FENSTER` | 1 | Labels „Läufer-Anzahl / Läufer-Breite" |
| `anleitung_farbmatrix` | 1* | Feld heißt **Stil:** (nachträglich per Grep gefunden) |

## CLEAN (19 Guides, keine Änderung nötig)

`vc_widgets` 03_farbe · 04_xy_pad · 08_cue_liste · 11_effekt_farben · 12_bpm_anzeige ·
14_musik_info · 15_text_label · 16_effekt_anzeige · 17_container · `anleitung_vc` ·
`anleitung_vc_smartbuild` · `anleitung_speed_bpm` · `anleitung_speed` ·
`anleitung_dimmermatrix` · `anleitung_patch_gruppen` · `anleitung_apc_mapping` ·
`anleitung_bpm_generator` · `LIVE_EDIT` (+ `anleitung_farbmatrix` sonst sauber).

## Verworfene Funde (3, False Positives)

Drei gemeldete Funde (je 1 in colorfade_vc, bpm_generator, live_edit_fenster) hielten der
adversarialen Gegenprüfung nicht stand (Guide-Aussage war vertretbar/bewusst) und wurden
**nicht** geändert.

## Offen / nachgelagert

- Der **show-spezifische** Cluster `anleitung_komplettshow_2026/*` war nicht im Audit-Umfang;
  in `06_efx_bewegung/ANLEITUNG.md` steckt vermutlich Drift (alte EFX-Meldung + womöglich
  überholte „EFX gilt nicht für Spider"-Aussage). → als eigene Aufgabe geflaggt.
