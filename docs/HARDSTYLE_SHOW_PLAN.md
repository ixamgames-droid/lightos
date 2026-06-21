# Hardstyle / Frenchcore Show 2026 — Masterplan

> Status: **PLAN** (2026-06-16). Neue, frisch live gebaute Show (nicht Testshow_2026 —
> die dient als Referenz/Steinbruch). Ziel: eine Profi-Lightshow im Hardstyle/Frenchcore/
> Techno-Stil (~150 BPM), **live gebaut und gefilmt**, daraus deutsche Anleitungen mit
> Bildern/GIFs fürs GitHub-Kit.
>
> Verwandt: `SHOW_AUTOBUILD_WORKFLOW.md`, `SHOW_2026_BUGLOG.md`, `BPM_MANAGER_PLAN.md`,
> `TUTORIAL_LICHTSHOW.md` (Anleitungs-Vorbild), `MATRIX_LIVE.md`, `MOVING_HEADS.md`.

---

## 1. Rig (Davids Standard 2026)

Draufsicht: hinten 2 Moving Heads (links/rechts), Mitte eine Reihe aus 8 PAR am Boden,
davor mittig 2 Spider am Boden. Publikum vorne.

| Gerät | Profil (short) | Modus | Universe | DMX-Start |
|---|---|---|---|---|
| PAR 1–8 | `ZQ01424` | 8-Kanal RGBW | 1 | 1 · 9 · 17 · 25 · 33 · 41 · 49 · 57 |
| MH Links / Rechts | `ZQ02001` | 11-Kanal | 1 | 65 / 76 |
| Spider Links / Rechts | `SPIDER14` | 14-Kanal RGBW | 1 | 87 / 101 |

Belegt 114 Kanäle (Universe 1). Kanal-Layouts:
- **PAR (8ch):** 1 Dimmer · 2 R · 3 G · 4 B · 5 W · 6 Strobe · 7 Makro · 8 Funk.-Speed
- **MH (11ch):** 1 Pan · 2 Tilt · 3 Dimmer · 4 R · 5 G · 6 B · 7 Strobe · 8 Farbrad · 9 Gobo · 10 Shutter · 11 Speed
- **Spider (14ch):** Pan/Tilt/Speed/Dimmer/Shutter + 2× RGBW-Bank (beide Köpfe teilen aktuell die Farbattribute — X-6 offen, für die Show ok)

**Gruppen:** Alle PAR · PAR Links (1–4) · PAR Rechts (5–8) · Moving Heads · Spider ·
Alle Mover (MH+Spider, für EFX) · Farb-Matrix (PAR+Spider, alle RGB(W)-Geräte).

**base_levels:** PAR + Spider Intensity = 255 (Farbe sofort sichtbar; Dimmer-Effekte
überschreiben). MH bleiben dunkel bis EFX `open_beam` oder Look sie öffnet.

---

## 2. Musik & Timing

- Quelle: `C:/Users/David/Desktop/Musik/BP Party` (~183 mp3, „BeachParty"/Bounce/Hardstyle).
- Kuratierte Playlist (Referenz): Mr. Brightside (Bounce), Angels – Jesse Bloch, I Need A Hero,
  Africa – Rayvolt, Major Tom, Gym Hardstyle. Alle ~**150 BPM**.
- Timing-Raster: **Beat 0,40 s · Takt (4) 1,6 s · Phrase (8) 3,2 s**.
- Sync: primär **BPM-Manager AUTO** (Audio-Erkennung) + **Tap** fürs Live-Mixen, live
  umschaltbar. Beat-Effekte (Chaser/Carousel) + Beat-Sync-Cuelisten folgen `_emit_beat()`.

---

## 3. Dramaturgie (6 Phasen, wiederverwendbare „Looks")

1. **Intro/Atmo** — Dimmer-„Breathe", tiefes Blau/Weiß, MH langsame Acht, Spider RGBW gedimmt.
2. **Build-up/Riser** — Dimmer-Matrix beschleunigt (adaptive Speed), Farbe → Weiß, Strobe-Ramp.
3. **Drop/Kick** — harter Strobe, Farbchase Blau-Weiß über PAR-Reihe (L→R), MH-Acht schnell, Spider voll.
4. **Break** — Color-Wash, Plasma/Atmo, MH langsam.
5. **Second Drop** — härter: Police-Blau, Pinwheel-Matrix schnell, Voll-Strobe, MH Counter-Rotate.
6. **Outro** — Ausklang.

Diese Looks werden als VC-Buttons/Cues gebaut, damit sie live mix-/triggerbar sind.

---

## 4. Feature-Arbeit (vor/ während des Baus)

### 4.1 🔴 Blocker zuerst (Phase 0)
- **BUG-01 Reload-Crash:** `load_show()` → `_replace_patch_from_data()` ruft pro Fixture
  `add_fixture()` → emittiert `PATCH_CHANGED` synchron mitten im Laden →
  `programmer_view._sync_refresh` → `_refresh_effects_list` → `QListWidget.clear()` →
  AccessViolation. **Fix:** Emit-Koaleszierung beim Laden (einmal am Ende) **oder**
  `_loading`-Guard in programmer_view (kein `_sync_refresh` bis `singleShot` nach Laden).
- **MH-EFX live:** Engine schreibt Pan/Tilt/Intensity/Shutter korrekt (headless verifiziert),
  reale Mover bewegen sich nicht. Diagnose: Simple Desk Kanäle 65–86 prüfen, physische
  Adresse/Modus (65/76, 11ch) gegen Patch abgleichen, Reset-Haltedauer. (Hardware-abhängig.)
- **Autosave-Kollision** beim Laden prüfen (zweite Emissionsquelle).

### 4.2 Neuer Funktionstyp: **Color-Chaser** (Davids Wunsch)
Eigenständiger Chaser, der **eine `ColorSequence` Schritt für Schritt durchläuft** (nicht
Szenen verkettet). Pro Schritt Fade-In/Hold/Fade-Out; Farbfolge frei editierbar
(z. B. *grün-weiß-blau* oder *grün-rot-blau-rot-weiß*). BPM-/Tap-koppelbar (beats_per_step),
Richtung/Bounce, Ziel = Fixture-Gruppe.
- Engine: neue Klasse neben `Chaser`/`RgbMatrixInstance`, nutzt das kanonische
  `ColorSequence`-Modell aus `rgb_matrix.py`.
- UI: Editor mit `ColorSequenceField` (Add/Remove/Sortieren/Toggle) + Fade/Hold + Speed.
- VC/MIDI: über `effect_live` steuerbar (next_color/add/remove, Speed-Fader).
- Persistenz: in `show.json` + `SHOW_FILE_FORMAT.md` ergänzen, Tests.

### 4.3 Manueller Strobe in der VC
Sauberes Bedienelement (heute nur Matrix-STROBE-Effekt). Variante: dedizierte
ButtonAction „Strobe (gehalten)" auf Shutter/Matrix-STROBE + Speed-Fader (EFFECT_SPEED).

### 4.4 Adaptive / relative Speed (Dimmer ≠ Farbe, phasen-gekoppelt)
Mechanismus = **Tempo-Bus** (`tempo_bus.py`, `TEMPO_SYNC_PLAN.md`). Beide Effekte hängen am
selben Bus (gemeinsame Uhr); per `tempo_multiplier` setzt man feste Verhältnisse ×½/×1/×2 —
„beide gleich schnell, einer halb so schnell", **ohne Drift** (phasen-synchron). Stand 2026-06-16:
Phasen 1–3 (Bus-Kern + Function-Felder + **RGB-Matrix-Bus-Sync**) fertig & getestet → Dimmer-/
Farb-Matrix mit festem Verhältnis läuft engine-seitig bereits. Offen: Bus-Sync für **ColorChaser**
(Phase 4, mein neues File → kollisionsfrei) + **VC-Bedienelemente** (Tempo-Fader/Bus-Auswahl/Sync,
Phase 5 — Koordination mit Parallel-Build). Einfacher Fallback ohne Kopplung: per-Effekt
`Function.speed` auf VC-Fader (driftet → nur Notlösung).

### 4.5 BPM-Manager-Integration (jetzt verfügbar)
Stand 2026-06-16 verifiziert: WP-1 gelandet — `BpmMode`, `request_bpm` (Quellen-Vorrang),
`nudge`, `set_mode`, `use_audio_source` vorhanden; „nur noch Tests laufen". → **Jetzt integrierbar**
(nicht erst am Ende). In der VC nutzen: AUTO-Audio-Detect, Tap, Lock/Mode-Toggle, Nudge ±,
BPM-Anzeige. ColorChaser/Chaser folgen dem Beat bereits (Duck-Typing in `bpm_manager`).
**Wichtig:** Engine-Dateien (`bpm_manager.py`/`tempo_bus.py`/`beat_detector.py`/`capture.py`)
**nicht editieren** (parallel im Test) — nur on-top in VC/Show integrieren.

---

## 5. Phasenplan

- **Phase 0 — Fundament:** BUG-01 fixen · MH-EFX diagnostizieren · Color-Chaser-Typ bauen ·
  manueller Strobe · Tests grün. → Live-Bauen wird crashfrei.
- **Phase 1 — Show live bauen + filmen:** Patch → Gruppen → Looks (Farbchase, Matrix,
  Dimmer adaptive Speed, MH+Spider, Strobe) → Cues/Beat-Sync → VC/APC. Jeder Schritt
  per `lo.ps1`/`_capseries.ps1` als Screenshot/GIF aufgenommen.
- **Phase 2 — Anleitungen:** deutsche Walkthroughs im `TUTORIAL_LICHTSHOW.md`-Format unter
  `docs/anleitung_*/` (Patch · Gruppen · Color-Chaser · Matrix+adaptive Speed · MH+Spider ·
  BPM-Sync · VC+APC). Später ins GitHub-Kit.

Autorisierung: nach Phase 0 direkt mit Phase 1 weiter, **ohne erneute Freigabe** (David).

---

## 6. VC- / APC-Mini-Layout (6 Bänke)

1. **Farben & Color-Chases** — Farb-Tiles (Alle/PAR/Spider) + Color-Chaser-Presets.
2. **Matrix-Effekte** — Blau-Chase, Pinwheel, Wave, Wipe, Plasma.
3. **Dimmer + adaptive Speed** — Dimmer-Matrizen + Speed-Fader (Color vs. Dimmer getrennt).
4. **Moving Heads** — EFX-Figuren (Kreis/Acht/Sweep), XY-Pad Pan/Tilt, MH-Farbe.
5. **Spider** — RGBW (inkl. Weiß), Strobe, Bewegung.
6. **Master / Live** — manueller Strobe, BPM-Toggle (AUTO↔Tap), Nudge ±, Grand Master, Blackout, Media-Transport.

APC mini: Grid 8×8 → Effekt-Buttons; Track-Tasten → Clear/Stop/Blackout/Tap/Musik-BPM;
Scene-Tasten → Bank-Wechsel; Fader → RGBW/Speed/Grand Master. LED-Feedback + Soft-Takeover.

---

## 6b. Live-Show-Modus vs. manuell (Mutual-Exclusion) — David-Anforderung
Zwei Bedienebenen, die sich NICHT überlagern dürfen:
- **(a) manuell** getriggerte Effekte auf den VC-/APC-Bänken — u. a. der **Color-Chaser auf
  Bank 1 / Seite 1** (den ich live programmiere).
- **(b) automatische Live-Show** (musik-/BPM-synchron, ggf. pro Lied hinterlegt).

**Regel:** Beim **Aktivieren der Live-Show** wird der manuelle Color-Chaser (Bank 1/Seite 1)
**automatisch deaktiviert**, damit beide Ebenen nicht kollidieren. Umsetzung: der „Live-Show"-
Button stoppt beim Start die kollidierenden manuellen Funktionen (mind. den Bank-1-Color-Chaser).
**Entschieden (David 2026-06-16):**
- **Reichweite:** Es wird **nur der Color-Chaser auf Bank 1 / Seite 1** deaktiviert; alle anderen
  manuell getriggerten Effekte bleiben bedienbar (David mischt manuell dazu).
- **Auto-Show = pro Lied:** Jedes Lied bekommt eine **eigene komplette Show**, die beim Abspielen
  automatisch startet (`MusicShowDirector` + `Track.autoshow_function_ids`, Per-Song-Handoff —
  war AUTODJ-Open-Point, also noch zu bauen).
- Live-Show-Start = (1) Per-Song-Funktionen des aktuellen Lieds starten **+** (2) Bank-1-Color-Chaser
  stoppen. Umsetzung als Multi-Action am „Live-Show"-Button bzw. im MusicShowDirector-Handoff.

**KONFLIKT + Auflösung (2026-06-16, beim Live-Bau entdeckt):** „Bank-1-Color-Chaser abschalten"
widerspricht „**MH immer farbig**" + „viel Farbe", weil der Farb-Chase (Matrix 1) die **einzige
Farbquelle** ist (er deckt jetzt PAR + Spider **+ MH** ab). Ein Live-Show, das ihn abschaltet, macht
die Show **farblos** — das ist für Hardstyle klar falsch. **Entscheidung (Default):** der
**LIVE-SHOW-Button startet den KOMPLETTEN farbigen Look** (MH-Bewegung + Farb-Chase + Dimmer, alle
`mode=on`), `music_autoshow.function_ids=[1,2,3]`. Alle anderen Tasten bleiben nutzbar.
→ Falls David doch den **strikten Takeover** will (Chaser wirklich aus), brauchen die MH/PAR eine
**feste Grundfarbe** (base color), damit „MH immer farbig" trotzdem gilt — offen, auf Davids Wunsch.

## 7. Aufnahme-/Anleitungs-Pipeline

`lo.ps1 fg` (Fenster topmost) → navigieren/klicken → `lo.ps1 shot` bzw. `_capseries.ps1`
für GIF-Frames → `_makegif.py` (Crop/Scale/FPS) → Assets nach `docs/anleitung_*/img|gif/`.
Bei Crash/Fehler: Bug in `SHOW_2026_BUGLOG.md`, sofort fixen, weiter (autonom).

---

## 8b. Fortschritt (2026-06-16)
- ✅ **BUG-01 Reload-Crash behoben** (Emit-Koaleszierung `AppState._suppress_emits` in
  `_replace_patch_from_data`); deckt auch Autosave-Reload ab. Tests:
  `test_app_state_emit_suppress.py` + `test_show_file.py`.
- ↩️ **Color-Chaser-Typ zurückgebaut** (Scope-Korrektur: nur Vorhandenes nutzen, keine neue
  Feature-Entwicklung). Farb-Chase läuft über die **vorhandene RGB-Matrix-Chase** (Chase-Algo +
  ColorSequence-Editor, bereits in der GUI, Tempo-Bus-/BPM-fähig). `color_chaser.py` + Test entfernt,
  Enum/Manager/Dispatch + `bpm_manager`-Änderung (`isinstance(Chaser)`) zurückgesetzt. **BUG-01-Fix
  bleibt.** Tempo-VC (Phase 5) + Chaser-Tempo-Sync (Phase 4) liefert der Parallel-Build → nur nutzen.
- ✅ **MH-EFX**: Engine-Ausgabe (Pan/Tilt/Intensity/Shutter) bereits headless verifiziert →
  Restproblem rein physisch (Adresse/Modus am Gerät), Check beim Live-Bau am Rig.
- ✅ **VC komplett gebaut (3 Bänke, beschriftet) + live verifiziert** (`shows/Hardstyle_Show.lshow`,
  Builder `tools/build_hardstyle_vc.py`, 33 Widgets):
  - **Bank 1 Performance:** LOOKS (Farbchase/Dimmer 2×/MH-Bewegung) · FARBEN (blau/grün/rot) ·
    STEUERUNG (BLACKOUT/STOP ALL/CLEAR) · LIVE-SHOW (grün, +2 Multi-Aktionen) · MASTER + Effekt-Helligkeit.
  - **Bank 2 Tempo/BPM:** VCBpmDisplay (live „80 AUTO") · TAP · AUTO/MAN · Musik-BPM · BPM ± · BPM-/Effekt-Tempo-Fader.
  - **Bank 3 Strobe/Musik:** STROBE (halten) + Strobe-Tempo · VCSongInfo (Now Playing) · Media ◄◄/▶❙❙/►►.
- ✅ **Manueller Strobe**: neue RGB-Matrix `Strobe` (Algo Strobe, RGBW, drive_intensity) + VCButton
  Funktion-Flash + Effekt-Tempo-Fader (frei, nicht bus-gekoppelt).
- ✅ **Looks brief-konform:** Farb-Chase deckt jetzt **auch die MH** ab (MH farbig); **Dimmer 2×**
  ist ein echter Dimmer (Style Dimmer, drive_intensity) auf PAR+Spider, **×2 phasen-gekoppelt** an
  den Farb-Chase über Tempo-Bus `hardstyle` (source `bpm_global` → music-sync). Live verifiziert:
  Farb-Chase blau + Dimmer-Lauflicht (100%/73%/40%/7% wandernd).
- ✅ **Bugfix EFX `open_beam=true`** (MH waren sonst bei Bewegung dunkel).
- ✅ **Reload mehrfach crashfrei** (BUG-01-Fix hält): Show via Ctrl+O neu geladen, VC/Looks korrekt.
- ✅ **Anleitung VC** aktualisiert (`docs/anleitung_vc/`, Bilder 10–13 der 3 Bänke).
- ✅ **base_levels** PAR(1-8)+Spider(11,12)=255 gesetzt (Plan §1). Dimmer-2× (drive_intensity) überschreibt pro Frame.
- ✅ **Playlist** (5 Hardstyle/Frenchcore/Bounce-Tracks aus `Desktop/Musik/BP Party`, abs. Pfade) in der Show.
- ✅ **Auto-Show live verifiziert:** VC-Media ▶ startet Musik + `music_autoshow=[1,2,3]`; Audio-BPM-Erkennung sprang an (~145–165 zur Musik); Playlist läuft selbsttätig weiter.
- ✅ **GIF** der laufenden Show (`docs/anleitung_vc/gif/hardstyle_show_live.gif`) + **APC-MIDI-Teach-Dialog** bebildert (`img/14`, ANLEITUNG_VC §5: Grid 0–63, Track 64–71, Scene 82–89, Fader CC48–56).
- ⏭️ Zurückgestellt: 3D-Visualizer-GIF (PARs mit laufendem Dimmer zu dunkel) · APC-Hardware-Bindung (Gerät nötig) · ggf. fester MH-Grundton falls strikter Takeover gewünscht (§6b).

### Authoring-Lehren (2026-06-16)
- `.lshow` = **ZIP mit `show.json`** (UTF-8). Komplexe VC/Look-Layouts zuverlässig per Skript bauen
  (Enum-Strings exakt: `FunctionToggle`/`LibrarySnap`/`Tap`/`AudioBpm`/`Blackout`/…, SliderMode
  `GrandMaster`/`BPM`/`EffectSpeed`/…, Bank 0-basiert), dann **in der App neu laden** = Verifikation +
  saubere Anleitungs-Screenshots. Multi-Action: `{"type":"function","function_id":N,"mode":"on|off"}`.
- **Reload zuverlässig:** Ctrl+O → Dateinamen-Feld klicken → Pfad einfügen → Enter (kein Dialog-Klick-Raten).
- **Bank-Wechsel zuverlässig:** **Strg+Bild↑/Bild↓** (Page→Bank-Callback) statt der reflowenden
  FlowLayout-Pfeile.

## 8. Offene Risiken
- MH-EFX-Hardware (physisch) nur am echten Gerät final verifizierbar.
- BPM-Manager-Reife zum Integrationszeitpunkt (parallel im Bau).
- Spider getrennte Kopffarben (X-6) bewusst zurückgestellt.
