# Tempo & Synchronisierung — Gesamtüberblick (BPM · Buses · Multiplikatoren · Sync)

> **Der rote Faden** durch alles, was mit Geschwindigkeit und „im Takt laufen" zu tun
> hat. Dieser Guide erklärt das **Gedankenmodell** und gibt **Rezepte** — die tiefen
> Details stehen in den verlinkten Detail-Anleitungen am Ende.
>
> Wenn du nur **eine** Sache suchst: „Wie laufen zwei Effekte unterschiedlich schnell,
> aber starten gemeinsam im selben Takt?" → spring zu [Abschnitt 4](#4-synchronisierung--der-wichtige-teil) und [Abschnitt 5](#5-rezept-dimmer-halb-so-schnell-wie-die-farbe-phasengleich).

---

## 0. Das Gedankenmodell in 30 Sekunden

Tempo in LightOS hat **drei Ebenen** — von global nach fein:

| Ebene | Was | Wo |
|---|---|---|
| **1. Globale BPM** | *Eine* Geschwindigkeit für die ganze Show (aus Musik, Tap oder manuell). | BPM-Tab (**Strg+8**) |
| **2. Tempo-Bus** | Eine benannte „Uhr". Jeder Effekt hängt an **genau einem** Bus. Der Standard-Bus heißt **„Global"** und folgt der globalen BPM. | BPM-Tab / VC |
| **3. Pro Effekt** | **Multiplikator** (×½, ×2 …) + **Phase** — wie schnell und wie versetzt *dieser* Effekt relativ zu seinem Bus läuft. | Effekt-Einstellungen / Speed-Dial |

Und quer darüber liegt die **Synchronisierung**: sie sorgt dafür, dass Effekte ihren
Zyklus **gemeinsam auf der Eins** beginnen — nicht „gleich schnell", sondern **im gleichen Takt**.

> 🔑 **Merksatz:** *Geschwindigkeit* (Multiplikator) und *Takt-Start* (Sync) sind zwei
> verschiedene Dinge. Du willst meistens **unterschiedliche Geschwindigkeit + gemeinsamen Start**.

---

## 1. Globale BPM setzen (BPM-Tab, Strg+8)

Der **BPM-Manager** (Tab öffnen mit **Strg+8**) ist die Zentrale. Oben der **Monitor**
(große BPM-Zahl, Takt 1·2·3·4, Beat-Flash), unten die **Einstellungen**.

**BPM-Quelle** wählen:
- **Live-Audio** — BPM wird aus dem PC-Audio/Eingang live erkannt (Standard).
- **Lied-Analyse** — folgt dem Beatgrid eines vorab analysierten Songs.
- **Manuell / Tap** — du gibst die BPM per **TAP** (mehrmals im Takt klicken) oder Zahl vor.

Weitere Stellschrauben: **Genre-Preset** (stellt Grenzen/Empfindlichkeit/Takt passend ein),
**Grenzen** (Höhen/Tiefen), **Empfindlichkeit**, **Glättung**, **Takt-Raster**
(Beats/Takt + Unterteilung), **Nudge** (±1…±10) und **🔒 Lock** (BPM einfrieren, damit
keine Quelle sie mehr verändert).

→ Tiefer: **[BPM-Manager-Anleitung](anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md)** ·
**[Musik-Sync & Auto-Show](anleitung_musik_sync/ANLEITUNG_MUSIK_SYNC.md)**

---

## 2. Tempo-Buses — mehrere Geschwindigkeiten nebeneinander

Du brauchst nicht immer mehrere Buses — für „alles folgt der Musik" reicht der
**Standard-Bus „Global"**. Buses lohnen sich, wenn du **Gruppen unterschiedlich schnell**
laufen lassen willst (z. B. Strobe auf Drums, Farbe auf Bass).

- **Default-Bus „Global"** — folgt der globalen BPM (Abschnitt 1). Aliase: leer / `Global` / `default` meinen alle denselben Bus.
- **Eigene Master** (z. B. „Bass", „Drums") — eigenständiges Tempo per Tap/Zahl/Audio.
- **Sub** — folgt einem Master, läuft **phasen-gekoppelt** mit, aber mit **Faktor**
  (`¼ ½ 1× 2× 4×`). So bleibt alles sauber im Verhältnis, nie „aus dem Takt".
- **Grand-Master** — übertrumpft (wenn scharf) **alle** Master auf seinen Takt; Subs behalten ihr Verhältnis.

Verwaltet wird das im BPM-Tab im Panel **„Tempo-Speeds & Grand-Master"** (Bus-Tabelle,
Master anlegen, Rolle/Folgt/Faktor) oder live per **Speed-Dial** in der Virtuellen Konsole.

→ Tiefer: **[Speed-Dial, Master/Sub & Grand-Master](anleitung_speed/ANLEITUNG_SPEED.md)**

---

## 3. Einen Effekt ans Tempo hängen (Multiplikator + Phase)

**Jeder** zeitbasierte Effekt (RGB-Matrix, EFX-Bewegung, Chaser, Sequence) trägt drei
Tempo-Einstellungen:

- **Tempo-Bus** — an welcher Uhr der Effekt hängt (`Global`, ein Master/Sub, oder *kein* Bus = **Free-Run**).
- **Multiplikator** — wie schnell relativ zum Bus: **¼ · ½ · 1× · 2× · 4×** (bis ×16 fein einstellbar).
- **Phase** — Versatz in Beats (0…1), um den Effekt gegen andere zu „verschieben".

Du setzt das an drei Stellen:
1. **Direkt im Effekt-Editor** (RGB-Matrix, EFX, Chaser, Sequence): **Tempo-Bus /
   Multiplikator / Phase** und die Checkbox **„Taktgleich starten"**. Neue Effekte stehen
   standardmäßig auf **Global · 1× · Phase 0 · Taktgleich an** — sie starten also direkt
   im gemeinsamen Raster. Nur für einen bewusst frei laufenden Effekt den Haken weg
   (oder **Tempo-Bus = Frei**).
2. **Tempo-Controller-Widget** in der VC — der bequeme Weg: **ein Bus + Quelle
   (Sound/Tap/Fix) + Faktor + gekoppelte Effekte** in einem Panel. Effekt einfach
   drauf­ziehen. → **[Tempo-Controller-Anleitung](anleitung_tempo_controller/ANLEITUNG_TEMPO_CONTROLLER.md)**.
3. **Live aus der VC** über einen **Speed-Dial** mit Ziel **„Tempo-Bus-Multiplikator"** —
   das „Multiplikator-Fenster", mit dem du den Faktor eines Effekts (oder mehrerer,
   per Komma-Liste) im Betrieb auf **Half/Double** ziehst.

> ⚠️ **Falle:** Der **Multiplikator wirkt nur, wenn der Effekt an einem Bus hängt.** Bei
> Free-Run (`Tempo-Bus = kein/leer`) wird er ignoriert — dann zählt die effekteigene
> „Speed". Wenn dein ×½ „nichts tut", hängt der Effekt vermutlich nicht am Bus.

→ Tiefer: **[Effekte bauen & mit Tempo steuern (EFFEKTE.md)](EFFEKTE.md)** ·
**[Dimmer-Matrix & relative Geschwindigkeit](anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md)**

---

## 4. Synchronisierung — der wichtige Teil

Hier verlieren sich die meisten. Es gibt **zwei** Bedeutungen von „synchron", und du
willst fast immer die zweite:

| Gemeint ist … | Heißt | Brauchst du? |
|---|---|---|
| „Beide laufen **gleich schnell**" | gleiche BPM / Faktor 1× | meistens **nicht** — dann sieht alles gleich aus |
| „Beide **starten ihren Zyklus gemeinsam** auf der Eins" | **Phasen-Sync** | **JA** — das hält ×½ und ×1 im selben Takt |

**Ohne Sync** driften zwei Effekte auseinander, sobald du sie zu verschiedenen Zeiten
einschaltest — selbst wenn die Faktoren stimmen. **Mit Sync** beginnen sie gemeinsam und
bleiben dauerhaft im Raster.

Du hast **drei Werkzeuge** dafür:

### a) Auto-Sync (Dauer-Toggle) — *Standard*
**BPM-Tab (Strg+8) → Panel „Tempo-Speeds & Grand-Master" → ☑ Auto-Sync.**
Bei neuen Shows ist Auto-Sync bereits aktiv. Solange aktiv, übernimmt
**jeder neu (oder erneut) gestartete** bus-gekoppelte Effekt
denselben Beat-Raster-Ursprung → er fällt automatisch in den gemeinsamen Takt, **egal wann**
du ihn auslöst. Einmal anhaken und vergessen. (Wird mit der Show gespeichert.)

### b) Jetzt synchronisieren (Einmal-Reset)
Direkt daneben der Button **[ Jetzt synchronisieren ]**. Re-ankert **alle** laufenden
Effekte auf **„jetzt"** (Downbeat = die Eins) — gut, um nach manuellem Gefummel alles in
einem Schlag wieder sauber zusammenzuziehen.

### c) SYNC am Speed-Dial / VC-Button „Sync (Bus)"
Pro Bus: das **SYNC**-Feld eines Speed-Dials bzw. ein VC-Button mit Aktion **„Sync (Bus)"**
setzt den Downbeat dieses Bus neu („jetzt ist die Eins"). Für Live-Performance auf eine
Taste/ein Pad legbar (auch **„Auto-Sync an/aus"** gibt es als VC-Button-Aktion).

### d) „Effekte je Bus" im BPM-Tab — Übersicht + Häkchen pro Effekt
**BPM-Tab (Strg+8) → Panel „Effekte je Bus — taktgleich".** Listet **alle** Effekte,
gruppiert nach ihrem Bus (Haupt-BPM · A–D · Frei). Pro Effekt-Zeile: **Typ**, ein
**Bus-Dropdown** (verschiebt den Effekt taktgleich auf einen anderen Bus), **Tempo ×**
und das Häkchen **„Taktgleich"** (= startet auf dem gemeinsamen Raster). Pro Bus ein
**[ Sync jetzt ]**. Hier siehst und reparierst du **auf einen Blick**, warum etwas „nicht
im Takt" läuft — falscher Bus, Häkchen aus oder abweichender Faktor.

> ✅ **Zuverlässig taktgleich:** Eine frisch gestartete Gruppe rastet automatisch auf
> einen **sauberen Downbeat** ein (kein „auf zufälligem Schritt" mehr nach Stop/Neustart),
> und auf **Bus A–D** gespeicherte Zuordnungen greifen auch direkt nach dem Show-Reload.

> 🔑 **Die eine Voraussetzung, die alles entscheidet:** Sync re-ankert **nur Effekte, die
> am SELBEN Bus hängen.** Dimmer und Farbe müssen also beide auf **„Global"** (oder beide
> auf demselben Master) liegen. Liegen sie auf verschiedenen Buses, passiert beim Sync nichts.

---

## 5. Rezept: Dimmer halb so schnell wie die Farbe, phasengleich

Genau dein Fall — Farbe wechselt rot/blau/rot/blau, Dimmer geht an/aus **halb so schnell**,
und beides startet im selben Takt, sodass z. B. nur **rot/aus/rot/aus** übrig bleibt.

1. **Globale BPM** setzen (Strg+8) — Quelle Live-Audio oder Tap, bis die Zahl stimmt.
2. **Farb-Effekt** (RGB-Matrix/Chase) auf **Tempo-Bus = „Global"**, **Multiplikator = 1×**.
3. **Dimmer-Effekt** (Dimmer-Matrix/Chase) ebenfalls auf **Tempo-Bus = „Global"**,
   aber **Multiplikator = ½**.
4. **BPM-Tab → ☑ Auto-Sync** **einschalten** (vor dem Starten).
5. Beide Effekte starten. Dank Auto-Sync beginnen sie ihren Zyklus gemeinsam auf der Eins —
   die Farbe macht zwei Wechsel, während der Dimmer einen Zyklus macht → **rot/aus/rot/aus**.
6. Verrutscht? Einmal **[ Jetzt synchronisieren ]** drücken — alles springt wieder zusammen.

> Variante: Dimmer **×2** (doppelt so schnell) für „blinkt zweimal pro Farbe". Über die
> **Phase** (0…1 Beat) kannst du den Dimmer zusätzlich gegen die Farbe versetzen.

Eine ausführlich bebilderte Variante steht in
**[Dimmer-Matrix & relative Geschwindigkeit](anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md)**.

---

## 6. Live-Tipps

- **Freeze** (VC-Aktion „Freeze (BPM einfrieren)", Standard-Taste **F3**): friert alle Buses
  + globalen Leader auf 0 ein — bus-gekoppelte Effekte **halten** die Pose. Toggle.
- **Tap** mitklatschen, wenn die Audio-Erkennung mal danebenliegt; danach ggf. **🔒 Lock**.
- **APC mini / MIDI**: Tap, Sync, Auto-Sync, Freeze und Speed-Dials lassen sich auf Pads/Fader
  legen → **[APC mappen](anleitung_apc_mapping/ANLEITUNG_APC.md)**.
- **App neu starten**, wenn neue Schalter (z. B. der Auto-Sync-Toggle) nach einem Update nicht
  erscheinen — die laufende App lädt Code nicht heiß nach.

---

## Verwandte Anleitungen

- **[Tempo-Controller-Widget](anleitung_tempo_controller/ANLEITUNG_TEMPO_CONTROLLER.md)** — das All-in-One-Tempo-Widget (Bus + Quelle + Faktor + gekoppelte Effekte) in der VC.
- **[BPM-Manager](anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md)** — Quelle, Genre-Presets, Takt-Raster, Generator (Lied → Beatgrid), Beatgrid-Editor, Panel „Effekte je Bus".
- **[Speed-Dial, Master/Sub & Grand-Master](anleitung_speed/ANLEITUNG_SPEED.md)** — Tempo aus der VC, Verhältnisse koppeln.
- **[Dimmer-Matrix & relative Geschwindigkeit](anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md)** — phasen-gekoppeltes ×2/×½ in der Praxis.
- **[Musik-Sync & Auto-Show](anleitung_musik_sync/ANLEITUNG_MUSIK_SYNC.md)** — Playlist → Play startet die Show, Tempo folgt der Musik.
- **[EFFEKTE.md](EFFEKTE.md)** — Effekte bauen und mit Tempo steuern (Hintergrund).
