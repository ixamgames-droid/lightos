# BPM-Generator — ganzes Lied analysieren (Workflow-Anleitung)

> **Was ist das?** Der **Generator** (BPM-Sektion → Unter-Tab **Generator**) analysiert ein
> **komplettes Lied** offline und erzeugt daraus eine **BPM-Kurve über die Zeit** plus ein
> **echtes Beatgrid** (alle Beats + Taktanfänge). Das Ergebnis kannst du im Editor
> korrigieren und dann als **taktgenaue BPM-Quelle** nutzen, die dem Lied folgt — der
> Profi-Weg (wie VirtualDJ/Serato) für vorbereitete Show-Tracks.
>
> Diese Anleitung beschreibt den **kompletten Workflow** und besonders die neuesten
> Funktionen: Analyse-Engines, Beatgrid-**Editor**, **Wellenform**, **Metronom-Vorhören**,
> **Auto-Genre/Taktart**, **Songstruktur-Marker**, **Cache** und **Ordner-Stapelanalyse**.
> Die Grundlagen der BPM-Quellen stehen in der [BPM-Manager-Anleitung](../anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md).

Stand: 2026-06-21. Verifiziert gegen die laufende App und den Quellcode
(`src/ui/views/bpm_generator_view.py`, `src/core/audio/{offline_timeline,analysis_engines,genre_presets,bpm_cache,music_show}.py`).

**Öffnen:** Sektionsleiste → **BPM** (oder **Strg+8**) → Unter-Tab **Generator**.

---

## In 6 Schritten zum fertigen Beatgrid

1. **Datei wählen…** → MP3/M4A/FLAC/OGG/WAV auswählen.
2. **Genre** wählen (oder erst „Allgemein" lassen — die Auto-Erkennung schlägt nachher eins vor).
3. **Engine** wählen (Eingebaut / librosa / Beat This! — s. u.).
4. **Analysieren** klicken. Es erscheinen BPM-Kurve, Beatgrid, Wellenform und Kennzahlen.
5. **Prüfen & korrigieren:** Mit **▶ Vorhören** anhören (Klick auf jedem Beat), bei Bedarf mit den **Beatgrid**-Buttons begradigen.
6. **„Im Player laden & als BPM-Quelle nutzen"** → im Musik-Tab abspielen; die BPM folgt jetzt dem Lied.

---

## 1. Quelle, Genre & Engine

* **Genre** — stellt das Tempo-Fenster und den Tempo-Prior passend zum Stil ein (z. B. Hardstyle 145–160). Das ist der **größte Hebel für Treffsicherheit**: ein enges Fenster verhindert den häufigsten Fehler (halbe/doppelte BPM). Neben dem Feld stehen der erkannte Bereich und Prior.
* **Engine** — *wie* analysiert wird:
  | Engine | Stärke | Hinweis |
  |---|---|---|
  | **Eingebaut (numpy)** | immer verfügbar, schnell | gutes Beatgrid per Onset-Analyse |
  | **librosa (DP-Beat)** | sehr robustes Beat-Tracking | optional (`pip install librosa`) |
  | **Beat This! (SOTA/KI)** | beste Qualität, **echte Taktart** | optional (`pip install beat_this`), lädt beim 1. Mal ein Modell |
  > Nicht installierte Engines werden mit Hinweis angezeigt und fallen automatisch auf „Eingebaut" zurück.
* **Fenster (s) / Schritt (s)** — Länge und Abstand der Analyse-Fenster für die BPM-Kurve. Standard 8 / 2 ist meist gut; größer = stabiler, träger bei Tempowechseln.
* **Takt** — Schläge pro Takt fürs Beatgrid (4/4 · 3/4 · 6/8 · 2/4). Die Auto-Erkennung schlägt nach der Analyse einen Wert vor.

---

## 2. Das Ergebnis lesen

Nach **Analysieren** siehst du:

* **Kennzahlen** (gelb): Ø/Median-BPM, Bereich, Anzahl Beats, Länge, Engine.
* **Auto-Erkennung** (grün): „**Erkannt: ~X BPM · Taktart · Empfohlenes Genre**" + Button **„Vorschlag übernehmen"** — setzt Genre + Taktart auf die Erkennung und analysiert neu (genauer). Der Button verschwindet, wenn der Vorschlag schon passt. *Du kannst ihn ignorieren und alles manuell wählen.*
* **BPM-Kurve** (gelbe Linie): das Tempo über das ganze Lied. Einbrüche = Breakdowns/halftime-Stellen.
* **Wellenform** (dim, im Hintergrund): die Lautstärke-Struktur des Songs. **So siehst du, ob die Beats auf den Schlägen sitzen** und wo die lauten/leisen Teile sind.
* **Beatgrid** (unten): **blaue** Striche = Beats, **pinke** = Downbeats (Taktanfänge).
* **Songstruktur-Marker** (gestrichelte, beschriftete Linien): grobe Abschnitte **Intro · Build · Drop · Hook · Breakdown · Ruhig · Outro** aus der Energie je Takt. *Damit baust du deine Looks gegen die Songstruktur.* (Hinweis: echte Cue-Listen erzeugt der Generator bewusst nicht automatisch — die brauchen deine Lichtlooks als Inhalt.)

---

## 3. Vorhören mit Metronom (prüfen, ob das Grid sitzt)

Klick auf **▶ Vorhören**: Der Song wird abgespielt und auf **jedem Beat ein Klick** gesetzt
(der **Downbeat** klingt höher/betont). Ein weißer **Cursor** wandert im Plot mit.

> **Wozu:** So hörst du sofort, ob das Beatgrid stimmt. Klingt der Klick „auf" der Musik →
> passt. Läuft er daneben → korrigieren (s. u.). Die Grid-Buttons wirken **live** während
> des Vorhörens. Erneut auf den Button (jetzt „⏹ Vorhören stoppen") = Stopp.

Das Vorhören nutzt einen eigenen, isolierten Player — deine Playlist bleibt unberührt.

---

## 4. Beatgrid-Editor — garantiert korrekt

Manchmal sitzt das automatische Grid nicht perfekt (live eingespielte Drums, ungerade
Stellen). Mit der **Beatgrid**-Leiste korrigierst du es in Sekunden — wie bei VirtualDJ/Serato:

* **½× / 2×** — Raster halbieren/verdoppeln (wenn die BPM doppelt/halb so hoch erkannt wurde).
* **◀ nudge / nudge ▶** — das ganze Grid minimal nach links/rechts schieben (Phase justieren).
* **Downbeat ◀ / ▶** — welcher Beat der Taktanfang ist, um einen Schlag verschieben.
* **Klick im Plot** — setzt den Downbeat genau auf den angeklickten Beat.

Nach jeder Korrektur wird die BPM-Kurve neu abgeleitet; beim Vorhören hörst du die Wirkung sofort.

---

## 5. Als BPM-Quelle nutzen

**„Im Player laden & als BPM-Quelle nutzen"**: legt den (korrigierten) Song mit seiner Analyse
in den Player und schaltet die Live-Audio-Erkennung ab, damit die Analyse **führt**.

Danach im **Musik-Tab** abspielen: die globale BPM folgt jetzt dem Lied über die Zeit.
Im **Manager-Tab** steht die Quelle dann auf **Lied-Analyse**. Mit **„Taktgenau"** (Manager,
Standard an) treffen die Lichter die **echten Beats** des Songs sample-nah — nicht nur den
BPM-Wert. (Details: [BPM-Manager-Anleitung, Abschnitt „Taktgenau"](../anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md).)

> **Wichtig:** Die Analyse führt nur, wenn **Live-Audio aus** ist (das macht der Button
> automatisch). Live-Audio, OS2L und MANUAL/Lock haben weiterhin Vorrang.

Mit **„Als .json exportieren"** sicherst du die komplette Analyse (BPM-Kurve, Beatgrid,
Struktur) als Datei.

---

## 6. Schneller arbeiten: Cache & Stapelanalyse

* **Analyse-Cache:** Jede Analyse wird gespeichert (`%APPDATA%/LightOS/bpm_analysis_cache.json`,
  je Datei + Genre/Engine/Takt). Lädst du denselben Song mit denselben Einstellungen erneut,
  ist er **sofort** da („✓ Sofort aus Cache geladen") — kein erneutes Dekodieren/Analysieren.
* **Ordner analysieren…** (Stapelanalyse): wählt einen Ordner und analysiert **alle Songs**
  darin im Hintergrund in den Cache (eine Datei nach der anderen, abbrechbar). Danach lädt
  jeder dieser Songs sofort. **Ideal, um ein ganzes Set vorzubereiten.**

---

## Kurz-Spickzettel

| Ziel | So geht's |
|---|---|
| Schnellstes gutes Ergebnis | Datei → Analysieren → **Vorschlag übernehmen** → ggf. Vorhören |
| Beste Qualität (inkl. echter Taktart) | Engine **Beat This!** |
| Grid sitzt nicht | **Vorhören** + ½×/2× / nudge / Downbeat-Buttons / Klick im Plot |
| Lichter exakt auf den Beat | „Im Player laden …" → Musik-Tab abspielen → Manager: **Taktgenau** an |
| Ganzes Set vorbereiten | **Ordner analysieren…** (einmalig), danach laden alle sofort |
| Songstruktur sehen | Marker im Plot (Intro/Drop/Breakdown …) — Looks dagegen bauen |
