# Tempo-Controller — das All-in-One-Tempo-Widget für die Virtuelle Konsole

> **Ein Widget für alles, was ein Effekt-Tempo braucht:** welcher Bus, woher der Takt
> kommt (Sound/Tap/feste BPM), wie schnell (×¼…×4) und **welche Effekte mitlaufen** —
> alles in einem grafisch verschachtelten Panel. Ersetzt das frühere Gefummel mit
> mehreren getrennten Widgets (SpeedDial-Multiplikator **+** Bus-Selector **+** Speed-Knoten).
>
> Die SpeedDials bleiben für manuelle Fein-/Sonderkontrolle erhalten — siehe
> [Wann SpeedDial, wann Controller?](#wann-speeddial-wann-controller).

---

## Das Panel auf einen Blick

```
┌─────────────────────────────────────────────┐
│  <Name>            128→256        [ Bus A ▾ ] │  Kopf: Name · Live-BPM (Bus→Effekt) · Bus-Wahl
├─────────────────────────────────────────────┤
│  Quelle:   [ Sound ]  [ Tap ]  [ Fix 128 ]    │  woher der Bus seinen Takt nimmt
├─────────────────────────────────────────────┤
│  Tempo:    ¼  ½  [1×]  2×  4×            ⟲    │  Geschwindigkeit der Effekte (×Faktor)
├─────────────────────────────────────────────┤
│  Effekte (3): Farb, An, Innen            ＋   │  gekoppelte Effekte · Drop-Ziel
│  [            SYNC jetzt              ]       │  alle gemeinsam auf die Eins
└─────────────────────────────────────────────┘
```

**Live-BPM `128→256`** heißt: der Bus läuft mit **128 BPM**, die gekoppelten Effekte
laufen bei Faktor **×2** also mit **256** — du siehst sofort Ergebnis und Verhältnis.

---

## In 5 Schritten einsatzbereit

1. **Virtuelle Konsole** öffnen → **Bearbeiten** einschalten.
2. In der Werkzeugleiste **„Tempo-Controller"** klicken → das Widget erscheint auf dem Canvas.
   (Größe/Position wie gewohnt im Bearbeiten-Modus ziehen.)
3. **Bearbeiten** wieder ausschalten → jetzt sind die Regler bedienbar.
4. **Bus** oben wählen, **Quelle** und **Tempo** einstellen.
5. **Effekte draufziehen** (aus der Bibliothek) → sie folgen dem Bus taktgleich.

> ⚠️ **Wichtig:** Im **Bearbeiten-Modus** verschiebt/selektiert ein Klick das Widget.
> Zum **Bedienen** (Quelle/Faktor/Bus klicken) den Bearbeiten-Modus **ausschalten**.

---

## Die Regler im Detail

### Bus (Kopf, oben rechts)
Klick auf **`Bus A ▾`** → Menü mit **Haupt-BPM · Bus A · B · C · D**.
- **Haupt-BPM** = der globale Standard-Bus (folgt der globalen BPM aus dem BPM-Tab).
- **Bus A–D** = vier eigene, unabhängige Tempo-Busse für Gruppen mit eigenem Tempo.

Das Widget steuert **genau einen** Bus. Mehrere Gruppen mit eigenem Tempo → mehrere
Tempo-Controller (je einer pro Bus).

### Quelle — woher der Bus seinen Takt nimmt
| Button | Bedeutung |
|---|---|
| **Sound** | Der Bus **folgt der Musik** (der audio-/global erkannten Haupt-BPM). Standard. |
| **Tap** | Du gibst den Takt per **Antippen** vor (mehrmals im Beat klicken). |
| **Fix 128** | **Feste BPM.** Mit dem **Mausrad** über dem Widget fein justierbar (im Run-Modus). |

> „Sound" für einen eigenen Bus (A–D) hängt ihn intern als **Sub** an die Haupt-BPM —
> er läuft also exakt zur Musik, bleibt aber ein eigener Bus, den du jederzeit auf
> Tap/Fix umstellen kannst.

### Tempo — die Geschwindigkeit der Effekte
**¼ · ½ · 1× · 2× · 4×** setzt den **Multiplikator** der gekoppelten Effekte (wie schnell
sie *relativ zum Bus* laufen). **⟲** (orange) setzt zurück auf **1×**.

- Bus 128 BPM, Faktor **½** → Effekte laufen mit **64** („halb so schnell").
- Bus 128 BPM, Faktor **2×** → Effekte laufen mit **256** („doppelt").

Alle Effekte am Controller teilen sich diesen einen Faktor (Gruppen-Tempo). Sollen
einzelne Effekte **unterschiedlich** schnell sein, leg sie auf eigene Controller/Busse
oder nutz pro Effekt einen SpeedDial.

### Effekte — koppeln & auswählen
- **Koppeln:** Effekt aus der **Bibliothek** auf das Widget **ziehen** → er wird dem Bus
  **taktgleich** zugewiesen und läuft sofort mit. (Grüner Rahmen beim Ziehen = gültiges Ziel.)
- **Einzeln verwalten:** **Klick auf die Effekt-Zeile** → Menü mit **„✕ <Effekt> entfernen"**
  pro Effekt + **„＋ hinzufügen / Parameter…"**.
- **Was pro Effekt gesteuert wird:** im **＋/Eigenschaften**-Dialog je Effekt wählbar —
  Standard ist **Tempo** (der Faktor steuert die Geschwindigkeit), optional ein anderer
  Parameter (z. B. Helligkeit). Steht dann als `[parameter]` hinter dem Namen.

### SYNC jetzt
Setzt den **Downbeat** dieses Bus neu auf „jetzt" und zieht **alle** gekoppelten Effekte
gemeinsam auf die **Eins**. Gut, um nach manuellem Gefummel alles in einem Schlag sauber
zusammenzuziehen.

---

## Rezepte

**A — Eine Effektgruppe folgt der Musik, halb so schnell:**
1. Controller anlegen, **Bus = Bus A**, **Quelle = Sound**.
2. Deine Dimmer-/Farbeffekte draufziehen.
3. **Tempo = ½**. → Die Gruppe läuft halb so schnell wie die Musik, alle taktgleich.

**B — Eine Gruppe auf festem Tempo, unabhängig von der Musik:**
1. Controller, **Bus = Bus B**, **Quelle = Fix**, Mausrad bis z. B. **140**.
2. Effekte draufziehen, **Tempo** nach Geschmack.

**C — Zwei Gruppen, unterschiedlich schnell, aber gemeinsam im Takt:**
- Controller 1: Bus A, Sound, **1×** — Farbeffekte.
- Controller 2: Bus B, Sound, **½** — Dimmereffekte.
- Beide folgen der Musik (Sound = Sub der Haupt-BPM) → sie bleiben **untereinander
  taktgleich**, laufen aber unterschiedlich schnell. Verrutscht? **SYNC jetzt**.

---

## Wann SpeedDial, wann Controller?

| Du willst … | Nimm |
|---|---|
| **Eine Gruppe** auf einen Bus legen + Quelle + Gruppen-Tempo, alles an einem Ort | **Tempo-Controller** |
| **Einen einzelnen** Effekt fein per Rad/Tap steuern, oder pro Effekt **eigene** Faktoren | **SpeedDial** |
| Nur den **Bus eines/mehrerer** Effekte live umschalten (ohne Tempo-Panel) | **Tempo-Bus** (VCBusSelector) |
| Nur die **BPM eines Bus** als Zahl/Fader setzen | **SpeedDial** (Modus „Tempo-Bus") / **Fader** |

> Alle drei wirken auf **dasselbe** Bussystem — du kannst sie mischen. Der Controller ist
> der bequeme „Standard"; die anderen sind die Spezialwerkzeuge.

---

## Wenn etwas nicht stimmt

- **Regler reagieren nicht?** → **Bearbeiten-Modus aus.** Im Bearbeiten-Modus wird das
  Widget verschoben statt bedient.
- **Anzeige `0→0`?** → Der Bus hat (noch) keine BPM. **Quelle = Fix** setzen oder im
  BPM-Tab/per Tap eine Haupt-BPM erzeugen (bei Quelle **Sound**).
- **Effekt läuft nicht mit?** → Klick auf die Effekt-Zeile und prüfen, ob er gelistet ist;
  sonst neu draufziehen. (Beim Draufziehen wird er automatisch taktgleich angekoppelt.)
- **Nach Show-Reload verrutscht?** → Einmal **SYNC jetzt**. Frisch gestartete Gruppen
  rasten ohnehin auf einen sauberen Downbeat ein.

---

## Verwandte Anleitungen

- **[Tempo & Synchronisierung — Gesamtüberblick](../ANLEITUNG_TEMPO_SYNC.md)** — das große Bild (BPM · Buses · Multiplikatoren · Sync).
- **[BPM-Manager](../anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md)** — Quelle, Presets, Takt-Raster, und das Panel **„Effekte je Bus"** (Häkchen „taktgleich" pro Effekt).
- **[Speed-Dial, Master/Sub & Grand-Master](../anleitung_speed/ANLEITUNG_SPEED.md)** — die Spezialwerkzeuge.
- **[Hochzeit-Show: taktgleich starten](../anleitung_hochzeit_tempo/ANLEITUNG_HOCHZEIT_TEMPO.md)** — konkretes Beispiel mit drei Tempo-Controllern.
