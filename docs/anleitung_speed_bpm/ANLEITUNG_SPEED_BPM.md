# Anleitung: Tempo steuern — Speed · BPM · Master/Sub · Tempo-Buses

> **Lernziel:** Alles rund ums **Tempo** verstehen und bedienen — den globalen
> **Speed-Fader**, die **BPM-Erkennung** (Tap/Musik/Nudge), die **Tempo-Buses A–D**,
> die **Master/Sub-Geschwindigkeiten** (ein Master-Takt, abgeleitete Sub-Tempi) und wie
> **mehrere Effekte auf derselben BPM** laufen.
>
> Show: `shows/Event_Demo_2026.lshow`, **Bank 6 „BPM & Tempo"** (SCENE-Taste 6). Die Datei
> liegt nicht im Repo — sie entsteht mit `./venv/bin/python tools/build_event_demo_2026.py`
> (Windows: `venv\Scripts\python.exe tools\build_event_demo_2026.py`).

![Bank 6 Übersicht](img/01_bank6_uebersicht.png)

---

## Das 3-Ebenen-Tempo-Modell (kurz)

```
  Grand-Master-Takt  ─►  Master-Bus (A, D…)  ─►  Sub-Bus (B=½, C=×2 …)  ─►  Effekt
        (BPM)               (eigene BPM)          (Parent × Faktor)
```

- **Grand-Master**: ein übergeordneter Takt, der (wenn „scharf") alle Master-Buses treibt.
  Scharf schalten: Sektion **BPM** → Reiter **„Tempo-Buses"** → **„Grand-Master scharf"**
  (mit eigener **Tap**-Taste). In dieser Show ist er aus. Nicht verwechseln mit dem
  **GM**-Regler oben in der Section-Bar — der ist der Helligkeits-Master.
- **Master-Bus**: hat eine eigene BPM (Tap/Sync/Zahl).
- **Sub-Bus**: hat **keine** eigene BPM — er folgt seinem Parent-Master **× Faktor**
  (¼ ½ 1 2 4). In dieser Show: **Bus B = ½ × A**, **Bus C = 2 × A**.
- Jeder **Effekt** kann an einen Bus gebunden werden (Feld **„Tempo-Bus:"** im EFX-,
  Matrix-, Chaser- und Sequenz-Editor) → läuft dann exakt im Bus-Takt, phasensynchron mit
  allen anderen Effekten am selben Bus. Neue Effekte stehen auf **„Global"** — das ist der
  Bus der globalen BPM (Tap, Musik-BPM, BPM-Fader).

Daneben gibt es den **globalen Speed-Fader** (im **Alle-Banks-Frame** der Virtual Console,
also immer sichtbar, Modus **„Speed (alle Effekte)"**, stufenlos 0,1×…4×). Er setzt beim
Ziehen die Geschwindigkeit der **gerade laufenden** zeitbasierten Effekte. Das wirkt aber
**nur bei Effekten ohne laufenden Bus-Takt**: Ein Effekt an einem Bus, dessen BPM läuft —
in dieser Show Bus A–D, und **„Global"**, sobald eine BPM anliegt —, folgt dem Takt × seinem
**Tempo ×** und ignoriert den Speed-Fader. Für solche Effekte stellst du das Tempo am Bus
(Tap/Fader/Dial) oder über **Tempo ×** ein. Das Faktor-Gitter (¼ ½ 1 2 4) gehört zum
SpeedDial bzw. zum Sub-Bus.

---

## 1. BPM-Erkennung & -Eingabe (Reihe 0)

| Taste | Funktion |
|---|---|
| **Tap Tempo** | mehrfach im Takt tippen → **globale** BPM (Bus „Global") wird aus dem Mittel der Schläge berechnet — Bus A–D bleiben davon unberührt |
| **Musik-BPM** | BPM-Erkennung aus dem Audio-Eingang an/aus (Auto-Modus) |
| **BPM +** / **BPM -** | BPM um 1 nach oben/unten nudgen (Feinkorrektur) |
| **BPM-Modus** | zwischen AUTO (Audio) und MANUAL umschalten |

Die aktuelle globale BPM steht rechts oben in der Anzeige **„GLOBAL BPM"**.

## 2. Tempo-Buses bedienen (Reihe 1)

| Taste | Funktion |
|---|---|
| **Tap Bus A** | Tap-Tempo **nur** für Bus A |
| **Sync Bus A** | Bus A auf den nächsten Downbeat re-synchronisieren |
| **Arm Bus** | Bus A „scharf" schalten (VC-Regler ohne eigenen Bus nehmen dann ihn als Ziel) |

Rechts daneben:
- **Bus-Wähler (A B C D)** — Chips, um den aktiven/scharfen Bus zu wählen (`VCBusSelector`).
- **BPM-Anzeige „BUS A (Master)"** — zeigt live die BPM von Bus A (hier 150).

## 3. Master/Sub-Geschwindigkeiten (Speed-Knoten, rechts)

Drei **Speed-Dials** zeigen die Hierarchie direkt:

| Dial | Rolle |
|---|---|
| **Master A** | Master-Knoten auf Bus A — zeigt ein Dreh-Rad mit eigener BPM und Tap (keine Faktor-Tasten) |
| **Sub B (½)** | Sub-Knoten, Parent = A, läuft mit **halbem** Tempo |
| **Sub C (×2)** | Sub-Knoten, Parent = A, läuft mit **doppeltem** Tempo |

Drehst du **Master A**, ziehen **B und C automatisch mit** (halb bzw. doppelt) — das ist das
Master/Sub-Prinzip. Das Faktor-Gitter (¼ ½ 1 2 4) sitzt nur an den **Sub-Dials (B/C)**; dort
schaltest du das Verhältnis zum Master um.

## 4. Mehrere Effekte auf einer BPM (Reihe 2)

Diese vier Tasten starten Effekte, die **fest an einen Bus gebunden** sind — so siehst/hörst
du die Synchronität sofort:

| Taste | Effekt | Bus |
|---|---|---|
| **Sync Chase >Bus A** | Farb-Lauflicht | Bus A (voll) |
| **Sync Atmen >Bus B (1/2)** | Dimmer-Puls | Bus B (½ → halb so schnell) |
| **Sync Blitz >Bus C (x2)** | Strobe | Bus C (×2 → doppelt so schnell) |
| **Sync MH-Kreis >Bus A** | MH-Bewegung | Bus A (¼ → ein Kreis je Takt) |

> Die Tastennamen tragen den Bus-Suffix (z. B. **„>Bus A"**), damit du die Bindung direkt
> auf der Taste siehst.

Starte mehrere davon gleichzeitig: alle laufen **im selben Grund-Takt**, B halb, C doppelt —
und bleiben phasensynchron. Änderst du Bus A (Tap/Fader), folgen alle.

> **Eigene Effekte an einen Bus hängen:** am direktesten im **EFX-, Matrix-, Chaser- oder
> Sequenz-Editor** über das Feld **„Tempo-Bus:"** (z. B. „Bus A"). Auf der VC geht es auch:
> Effekt aus der Bibliothek auf die VC **ziehen** und in der Drop-Karte den Aspekt
> **„Tempo-Bus zuweisen…"** ankreuzen — **oder** per **Rechtsklick** auf ein schon gebundenes
> Widget → **„⚡ Live-Parameter…"** das Feld **„Tempo-Bus"** auf den gewünschten Bus stellen.
> Den Bus selbst regelst du per VC-Fader im Modus **„Tempo-Bus (BPM)"** (siehe
> [VC-Workflow-Anleitung](../anleitung_vc_workflow/ANLEITUNG_VC_WORKFLOW.md), Abschnitt 6).

## 5. Die Tempo-Fader & der Alle-Banks-Frame

In **Bank 6** liegen die bank-eigenen Tempo-Fader:

| Fader | Funktion |
|---|---|
| **Tempo Bus A** | regelt die BPM von Bus A (Modus „Tempo-Bus (BPM)") |
| **Tempo Bus D** | regelt Bus D (zweiter freier Master, hier 128 BPM) |
| **BPM global** | regelt die globale Leader-BPM |

Darunter liegen die **immer sichtbaren** Fader des **Alle-Banks-Frames** (sie bleiben in
jeder Bank stehen):

| Fader | Funktion |
|---|---|
| **Speed** | Geschwindigkeit der laufenden Effekte, stufenlos (0,1×…4×) — **nur** bei Effekten ohne laufenden Bus-Takt (siehe oben) |
| **Dimmer** | Submaster (Gesamthelligkeit) |
| **Master** | Grand-Master (Gesamthelligkeit, Override) |

> Den globalen Takt steuerst du außerdem oben in der **Section-Bar**: Die **TAP**-Taste und
> die **BPM**-Anzeige sitzen dort und sind immer erreichbar. Der **GM**-Regler daneben ist
> der Helligkeits-Grand-Master, kein Takt.

---

## Typische Abläufe

**A) Auf die Musik einrasten (ohne Audio-Erkennung):**
1. „BPM-Modus" auf MANUAL.
2. Für die Effekte aus Reihe 2 im Takt auf **Tap Bus A** tippen → Bus A steht; B (½) und
   C (×2) folgen mit. (**Tap Tempo** setzt dagegen die globale BPM — die treibt alle Effekte
   auf Bus **„Global"**, also neu angelegte, nicht aber Bus A–D.)
3. Bus-gebundene Effekte starten (Reihe 2) – sie laufen jetzt im getappten Takt.

**B) Master/Sub vorführen:**
1. „Sync Chase >Bus A", „Sync Atmen >Bus B (1/2)", „Sync Blitz >Bus C (x2)" gleichzeitig starten.
2. **Master A**-Dial drehen → Chase folgt 1:1, Atmen halb, Blitz doppelt — alles im Lock.

**C) Schnell beschleunigen:**
- Effekte an einem Bus mit laufendem Takt: den Bus schneller stellen (**Tempo Bus A**,
  **Master A**-Dial, **BPM global** für Bus „Global") oder **Tempo ×** am Effekt erhöhen.
- Frei laufende Effekte (Tempo-Bus „Frei (nicht taktgebunden)"): den **Speed-Fader** im
  Alle-Banks-Frame hochziehen.

> **Hinweis Audio-BPM:** Die echte Audio-Erkennung braucht ein anliegendes Eingangssignal.
> Beim ▶ im Musik-Player wird die BPM des Tracks als globaler Takt übernommen — aber nur,
> wenn in Sektion **BPM** → **„Erkennung"** die Quelle **„Lied-Analyse (Player)"** gewählt ist
> (und weder Audio-Erkennung noch OS2L gerade eine BPM liefern).
