# Farb-/Effekt-VC-Show — Bedienung

Show-Datei: `shows/Farb_FX_VC_Show.lshow` · Generator: `tools/build_farb_fx_vc_show.py`
Rig: 8 PAR (RGBW) · 2 Moving Heads (Farbrad+Gobo+Pan/Tilt) · 2 Spider (RGBW, 2 Tilt-Köpfe).

Laden: App starten → **Strg+O** → `shows/Farb_FX_VC_Show.lshow`. Bank wechseln: **Strg+Bild↓ / Bild↑**
(oder ◀ / ▶ in der VC-Leiste). APC-Pads sind vorab gebunden (mk2 wird automatisch erkannt).

## Master-Tempo
Oben in jeder Bank: **MASTER BPM** + **Tap** + **Musik-BPM**. Das ist der eine Master-Takt.
Jeder Effekt hängt daran und hat einen **eigenen Multiplikator** (Speed-Dial-Gitter
`¼ ½ 1 2 3 4`). Ohne BPM laufen die Effekte in ihrem Eigentempo; sobald BPM da ist (Tap/Musik),
rasten sie taktsynchron ein — jeder mit seinem Faktor (z. B. PAR-Farbe ×1, Spider ×2, MH ×½).

## Synchronisation — gleicher Schlag trotz verschiedener Tempi
Oben (auf jeder Bank): **◆ SYNC** und **Auto-Sync**.
- **Auto-Sync** (standardmäßig AN): neu gestartete Effekte übernehmen automatisch den
  gemeinsamen Beat-Raster-Ursprung. Ein ×1- und ein ×0.5-Effekt liegen damit immer auf
  demselben Schlag — **egal wann** du sie drückst. Besonders für Farb- + Dimmer-Effekt auf
  denselben Strahlern: beide beginnen ihren Zyklus zusammen, obwohl sie unterschiedlich schnell sind.
- **◆ SYNC**: re-basiert das Raster auf **jetzt** — alle laufenden Effekte beginnen ihren Zyklus
  gemeinsam auf dem aktuellen Schlag. Drück es, wenn etwas „auseinandergelaufen" ist oder du
  bewusst auf einen Downbeat neu setzen willst.
- Auto-Sync-Knopf schaltet die Automatik an/aus; ◆ SYNC wirkt immer (Knopfdruck).

## Helligkeit — Farbe und Dimmer sind strikt getrennt
**Die Farb-Seite (Bank 1) rührt den Dimmer NICHT an.** Eine reine Farbe macht also noch **kein
Licht** — sie legt nur die Farbe fest. Die Helligkeit kommt ausschließlich von:
- **Bank 2 „Dimmer Voll"** (stetig volle Helligkeit pro Gruppe) bzw. den animierten Dimmer-Effekten
  (Lauflicht/Blink/Aufbau), und/oder
- den **Master-Dimmer-Fadern** auf Bank 4 (Grand/PAR/MH/Spider — regeln die Helligkeit live).

Typischer Ablauf: erst auf Bank 1 Farbe + Farb-Effekt wählen → dann auf Bank 2 „Dimmer Voll" (oder
einen Dimmer-Effekt) starten → mit dem Master-Fader (Bank 4) die Helligkeit einstellen. So bleiben
Farbe und Helligkeit komplett unabhängig (z. B. Farb-Wechsel langsam, Dimmer-Blink schnell).
*(Technisch: alle Farb-Effekte sind RGB-Matrizen ohne Dimmer-Ansteuerung; `implicit_brightness=False`
schaltet das automatische „Farbe = sichtbar" ab.)*

## Bank 1 — FARBE  (nur RGB/RGBW; Dimmer/Shutter werden NICHT angesteuert)
- **PAR** (Reihe 0–1): 4 Effekt-Tasten **Solid · Wechsel · Lauflicht · Farbwechsel** (es ist immer
  nur einer aktiv) + 6 **Farb-Kacheln** (färben den gerade aktiven PAR-Effekt — nur Farbe, kein Dimmer).
- **MH** (Reihe 2–3): 6 **Farb-Tasten** (Rot/Grün/Blau/Gelb/Weiß/Rosa = Solid in dieser Farbe, über
  das Farbrad) + **Wechsel** / **Farbwechsel** (Chaser).
- **Spider** (Reihe 4–5): wie PAR.
- Rechts: **Multiplikator-Dials** (PAR/MH/Spider) · **Farb-Editor** (für Wechsel/Farbwechsel die 2–4
  Farben wählen) · **Fade-Fader** (Ein-/Ausblendzeit, APC-Fader CC48/49).
- „Wechsel" = Schachbrett rot-blau bzw. rot-aus (pro Beat umschaltend). „Farbwechsel" = Crossfade
  durch die im Farb-Editor gewählten Farben.

## Bank 2 — DIMMER & GOBO  (die Helligkeit; legt sich über die Farbe von Bank 1)
- Pro Gruppe (PAR/MH/Spider, Reihe 0–3): **Dimmer Voll · Dim-Lauflicht · Dim-Blink · Dim-Aufbau**
  (single-select). „Dimmer Voll" = stetig hell (die Grundhelligkeit, damit die Farbe sichtbar wird;
  per Master-Fader dimmbar). + Multiplikator-Dial. Der **Fade-Fader** setzt die **Ein-/Ausblend-ZEIT**
  (wirkt beim Start/Stopp des Effekts, nicht live während er läuft).
- **MH-Gobo** (Reihe 4): offen/G1/G3/G5/G7 (Auswahl) + **Gobo-Wechsel** (wechselt taktsynchron
  zwischen 2 Gobos) + Gobo-Multiplikator.

## Bank 3 — BEWEGUNG  (nur Pan/Tilt)
- **MH-Formen** (Reihe 0–2): Kreis · Acht · welliger Kreis · Dreieck · Quadrat · Herz · **Eigener Pfad**.
- **XY-Feld „Bahn zeichnen"**: mit der Maus eine Bahn zeichnen → schreibt sie auf **„MH Eigener Pfad"**;
  diesen dann (wie Kreis/Acht) per Knopf auswählen → die MH fahren die gezeichnete Bahn **im Loop** ab.
- **XY-Feld „Bereich aufziehen"**: Rechteck ziehen → die MH bewegen sich nur in diesem Bereich.
- **Spider** (Reihe 3–4): Ineinander · Auseinander · Wackeln · Außen · Innen · Zufall-3-Positionen.
- Rechts: Multiplikator-Dials (MH / Spider).

## Bank 4 — ÜBERSICHT / STROBE / MASTER
- **Strobe** (Reihe 0, gehalten): Alle · nur PAR · nur MH · nur Spider.
- **Aktionen** (Reihe 2): **All White** (gehalten = alles weiß 100 %, hochprior) · **Blackout** ·
  **Effekt-Stop** (Effekte aus, Tempo bleibt) · **Pause** (= Effekt-Stop) · **Freeze** (BPM → 0,
  alle taktgekoppelten Effekte frieren ein; nochmal drücken taut auf).
- **Übersicht**: Master-BPM + Multiplikator-Dials „Farbe ×" / „Bewegung ×" — dieselben Effekte wie
  Bank 1–3, also **live synchron** (hier ändern = überall geändert).
- **4 Master-Dimmer** ganz rechts (APC-Fader CC53–56): **Spider · MH · PAR · GRAND**.

## APC mini mk2
- **Pads (Grid)**: lösen die Effekt-/Farb-Tasten der jeweils aktiven Bank aus (vorab gebunden).
- **Fader**: CC48/49 = Fade · CC53–56 = Spider-/MH-/PAR-Master/Grand-Master.
- Bank wechseln am Rechner (Strg+Bild↑↓); die Pads folgen der aktiven Bank.

## Technik (für Entwickler)
Masking ist echt: Farb-Effekte sind `RgbMatrix` mit `style=RGB, drive_intensity=False` (nur
color_r/g/b/w), Dimmer-Effekte `style=DIMMER` (nur Intensity), Bewegung `EFX` (nur Pan/Tilt).
Tempo-Kopplung über `tempo_bus_id="Global"` (= Default-Bus, spiegelt die Master-BPM) +
`tempo_multiplier` pro Effekt. Neue Features dieser Show: `RgbAlgorithm.CHECKER`, Fade-Params
`env_fade_in/out`, ButtonActions `ALL_WHITE/FREEZE/STOP_EFFECTS`, `VCXYPad`-Modus `path`,
Bus-Freeze-Hold (Effekte halten bei BPM 0 wenn `toggle_freeze` aktiv), Tempo-Bus-Option „Global".
