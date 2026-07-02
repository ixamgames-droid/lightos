# Laser-Support in LightOS — Plan (Stand 2026-07-02)

> Davids Auftrag (Chat 2026-07-02): Laser steuerbar machen — konkret der eigene
> „3D Partylight L2600" (identifiziert als **Ehaho L2600**), perspektivisch auch
> professionelle Laser über Netzwerkschnittstellen. Dazu Fixture-Klassen prüfen,
> Laser-Fixtures anlegen, eigene Programmer-UI (Paletten + freier Zeichenmodus,
> gut abgesichert). **3D-Viewer ist ausgeklammert** (läuft parallel als eigene
> Überarbeitung, wt-viz10/11).

## 1. Rechercheergebnis (verifiziert)

### 1.1 Der Laser: Ehaho L2600

- Amazon-/OEM-Gerät „3D Animation RGB Laserlight L2600", Hersteller **Ehaho**.
- Offizielles Manual: ManualsLib #3494357 (S. 6-11); Gegenprobe: DMXControl-DDF
  ([Forum-Thread](https://forum.dmxcontrol-projects.org/thread/17319-3d-animation-rgb-laserlight-l2600-etwas-unterst%C3%BCtzung/)).
- **Es gibt am Gerät nur ZWEI DMX-Modi:** „Simple DMX" (**6 Kanäle**) und
  „Professional DMX512" (**34 Kanäle**). 10/19-Kanal-Varianten existieren laut
  Manual/Community nicht (Davids Beobachtung am Gerät bestätigt das).
- **6ch ist ein EIGENES Layout** (On/Off, Auto-/Sound-Programm, Musterbank,
  Farbe, Feinwahl, Speed) — NICHT die ersten 6 Kanäle des 34ch-Charts.
- **34ch = zwei identische Mustergruppen:** Ch1-17 Gruppe A, Ch18-34 Gruppe B
  (Ch20 leer). Pro Gruppe: On/Off/Auto/Sound, Grenzverhalten, Bank (nur A),
  Musterauswahl, Zoom, Rotation, X/Y-Bewegung (0-127 = statische Position!),
  X/Y-Zoom/Verzerrung, Punktfarbe, Muster-Farbwechsel (mit 8 festen Farb-Slots),
  Punkte/Sweep, Zeichnen-Anteil + Zeichenmodus (manuell Sinus/Cosinus!),
  Twist (255 = neutral), Raster/Grating.
- Community-Warnungen (DMXControl-Forum): kein Not-Aus am Gerät, teils stehende
  Strahlen, nicht dimmbar → Safety muss softwareseitig kommen.
- **Am Gerät noch zu verifizieren (LAS-09):** Semantik Ch18=0 („B aus" vs.
  „alles aus"), Ch1/Ch18-255-Bedeutung im Zusammenspiel, 6ch-Ch5.

### 1.2 Netzwerk-Laser-Protokolle (Marktlage)

| Protokoll | Art | Offenheit | Fazit für LightOS |
|---|---|---|---|
| ILDA analog (DB25) | Analogsignal an Galvos | offener HW-Standard | Nur Kontext — erreicht man immer über einen DAC davor |
| **Ether Dream** | XY+RGB-Punkt-Streaming, TCP:7765 + UDP-Discovery | **offen dokumentiert**, Referenz-Impl. in Rust/Go | **Erster Streaming-Kandidat** — kleiner, klarer Scope inkl. E-Stop im Protokoll |
| **IDN / ILDA Digital Network** (IDN-Stream Rev. 002/2025 + IDN-Hello) | Punkt-Streaming über UDP, herstellerübergreifend | **offener ILDA-Standard**, PDF-Spec | **Strategisches Ziel** — ein Treiber für viele Hersteller (DexLogic, Helios OpenIDN, …); kein fertiges Python-Paket, Eigenimplementierung nach Spec |
| Helios DAC | USB-SDK (offiziell, Python-fähig), Netzwerk via IDN | offen | USB-Sonderfall; Netzwerkpfad = IDN → deckt sich mit Zeile drüber |
| Pangolin FB3/FB4, QuickShow/BEYOND | proprietäre Engine; Fernsteuerung via **DMX/Art-Net-Profil** (FB3 16ch, FB4 39ch) | geschlossen | Als normales DMX-Fixture-Profil abdecken — kein neues Protokoll nötig |
| LaserWorld ShowNET | „ILDA Streaming" über LAN (proprietär) + Art-Net-Trigger | geschlossen | Nur Art-Net-Trigger-Profil sinnvoll |
| Moncha.NET (Showtacle/KVANT) | SD-Cue-Trigger via Art-Net/DMX | geschlossen | dito |
| LaserCube (Wicked) | UDP-Punktformat, reverse-engineered | inoffiziell | später optional (Community-Klasse) |

**Empfehlung:** Zwei Laser-Klassen — (1) **DMX-Laser** (China-Laser, Pangolin-
FB-Profile, ShowNET/Moncha-Trigger) laufen JETZT über die bestehende
DMX/Art-Net/sACN-Pipeline, nur Profile nötig. (2) **Punkt-Streaming-Laser**
(Netzwerk): zuerst **Ether Dream** (kleiner Scope, sauberste Doku), danach
**IDN** (größte Reichweite). Neutrale Abstraktion `LaserFrame`/`LaserPoint`
(x, y, r, g, b, blank; normiert), NIE protokollspezifische Structs in der UI.

## 2. Ist-Analyse Code (Kernpunkte)

- `fixture_type='laser'` existiert bereits vollständig: `FIXTURE_TYPES`,
  QXF-`TYPE_MAP['Laser']`, `TYPE_COLORS` (patch_view), `fx_laser`-Icon.
  Alle Builtins sind korrekt klassifiziert (Audit-Test nagelt das jetzt fest).
- Grand-Master-Maske skaliert nur exakte Intensity-/RGB-Attribute → `laser_*`-
  und `color_wheel`-Kanäle bleiben unberührt (gewollt: Range-Select-Kanäle
  dürfen nicht „gedimmt" werden). **BLACKOUT wirkt als harter Not-Aus** (alle
  512 Byte → 0 ⇒ L2600-Ch1=0 = Laser aus) — Muster für den späteren
  Streaming-Not-Aus.
- Fixtures ohne DMX-Adresse gibt es strukturell nicht (`PatchedFixture.universe/
  address` Pflicht, `executor.py` rechnet zwingend `dmx_addr`) → Netzwerk-Laser
  brauchen ein neues `protocol`-Feld + eigenen Ausgabepfad.
- 44-Hz-`OutputManager` ist auf 512-Byte-Universen zugeschnitten → Punkt-
  Streaming (~30 kpps) bekommt einen EIGENEN Output-Thread/Manager, der nur
  Lifecycle + Safety-Gates (Blackout/E-Stop) mit dem DMX-Pfad teilt.
- Programmer: EFX/Matrix sind als eingebettete Views (`follow_selection=True`)
  in `programmer_view.py` angedockt, Tabs erscheinen capability-abhängig —
  exakt das Integrationsmuster für den künftigen **Laser-Tab**. Die XY-
  Zeichenfläche existiert als Vorbild: `_PathCanvas` in
  `src/ui/widgets/efx_path_editor.py` (normierte 0..1-Punkte).

## 3. Umsetzung in diesem PR (LAS-01)

1. **Builtin `L2600LASER`** (Hersteller Ehaho): Modi „6-Kanal (Simple DMX)" +
   „34-Kanal (Professional DMX)", alle Wertebereiche aus dem Manual, Farb- und
   Muster-Slots als `ChannelRange.kind` (`color`/`gobo`/`sound`/`open`/`closed`).
   Gruppe B = zweites Vorkommen derselben Attribute → Mehrkopf-Konvention
   (`attr#1`), d. h. A/B sind im Programmer als Kopf 1/Kopf 2 getrennt steuerbar.
   **Safety-Default: Shutter/On-Off = 0 (aus)** — ein frisch gepatchter Laser
   feuert nicht los (bewusst anders als der Offen-Default bei Scheinwerfern).
2. **Laser-Attribut-Vokabular** (`laser_boundary`, `laser_bank`, `laser_x/y`,
   `laser_zoom_x/y`, `laser_color`, `laser_color_change`, `laser_dots`,
   `laser_draw`, `laser_draw_mode`, `laser_twist`, `laser_grating`): registriert
   in `CHANNEL_ATTRS` (Fixture-Editor), exakt in `ATTR_GROUPS['Effect']`
   (verhindert Color-Substring-Fehlklassifikation → kein Feature-Dimmer-Zugriff
   auf Range-Select-Kanäle) und mit deutschen `ATTR_LABELS`.
3. **Klassen-Audit-Test**: jedes Builtin hat eine echte Klasse (nie `other`),
   Schlüsselgeräte explizit festgenagelt (PAR/MH/LED-Bar/Laser).

Damit ist der L2600 sofort patchbar und über die generischen Attribut-Tabs
(Intensity→Shutter, Gobo→Muster, Beam→Zoom, Weitere→Laser-Kanäle,
Color→6ch-Farbrad) komplett steuerbar — die komfortable Laser-UI folgt.

## 4. Fahrplan (Backlog-Epic, IDs LAS-xx)

| ID | Inhalt | Kern |
|----|--------|------|
| LAS-01 | ✅ dieser PR | L2600-Builtin + Vokabular + Audit |
| LAS-02 | Laser-Tab im Programmer | `LaserView(follow_selection=True)` analog EFX/Matrix; sichtbar nur bei `laser_*`-Kanälen bzw. `fixture_type=='laser'`. Inhalt: A/B-Gruppen-Umschalter (Kopf 0/1), Muster-Palette (Kacheln je Bank/Muster-Slot, `PresetTile`-Muster), Regler-Sektionen Zoom/Rotation/Bewegung/Farbe/Zeichnen mit Range-beschrifteten Slidern |
| LAS-03 | Muster-Paletten & Presets | feste, benennbare Muster-Buttons (speichern = Snapshot der `laser_*`-Werte), Integration in Snaps/Szenen/VC-Buttons |
| LAS-04 | Netzwerk-Laser-Grundlagen | `PatchedFixture.protocol` (`'dmx'` Default \| `'etherdream'` \| `'idn'`), ALTER-TABLE-Migration, `.lshow`-Serialisierung, Patch-UI blendet Universum/Adresse bei Netzwerk-Protokollen aus, `executor.py` überspringt Nicht-DMX-Fixtures |
| LAS-05 | Ether-Dream-Backend | eigener `LaserOutputManager`-Thread (Punktraten ≫ 44 Hz), TCP-Streaming + UDP-Discovery, E-Stop/Clear als First-Class-Aktion, gekoppelt an BLACKOUT |
| LAS-06 | IDN-Stream-Backend | zweites Backend hinter derselben `LaserFrame`-Abstraktion |
| LAS-07 | Freier Zeichenmodus | XY-Canvas (Vorbild `_PathCanvas`) → für DMX-Laser: Ch14/15-Ansteuerung (manuell Sinus/Cosinus); für Streaming-Laser: Punktlisten. **Safety-Gates Pflicht** (s. u.) |
| LAS-08 | Profi-DMX-Profile | Pangolin FB4 (39ch) / FB3 (16ch), ShowNET-Art-Net-Trigger, Moncha — als weitere Builtins/Profile |
| LAS-09 | Hardware-Verifikation L2600 | David am Gerät: Ch18-0/255-Semantik, 6ch-Ch5, Bank-Grenzen; Profil ggf. per Signatur-Migration nachziehen |

### Safety-Konzept (gilt ab LAS-02, hart ab LAS-05/07)

1. **Aus-Default:** Laser-Shutter defaulten auf 0 (umgesetzt in LAS-01).
2. **Not-Aus:** BLACKOUT bleibt der harte Kill (DMX: 512×0; Streaming: E-Stop
   VOR jedem Send geprüft, Vorbild `OutputManager._send_all`).
3. **Arming:** Der freie Zeichenmodus (LAS-07) ist zweistufig — erst explizit
   „scharf schalten" (UI-Toggle mit Warnfarbe), sonst nur Vorschau.
4. **Limits:** für Streaming-Laser eine Clamping-Stufe zwischen Muster-
   Berechnung und Send (Scan-Winkel-/Größen-Limit, Punktraten-Limit,
   Mindest-Punktzahl gegen stehende Strahlen) — unabhängig von Programmer-Werten.
5. **Klassen-Sammelzugriff:** Helper `laser_fids()` (analog `mover_fids()`) für
   „alle Laser aus" — Grundlage für einen VC-Not-Aus-Button.

### Bewusst NICHT in diesem Schritt

- **3D-Viewer/Visualizer** (Beam-Darstellung, Montagehöhe `coords.py`): läuft
  parallel als eigene Überarbeitung — Laser-Darstellung dort erst nach deren
  Abschluss (sonst Merge-Konflikte in wt-viz10/11).
- 10/19-Kanal-Modi: existieren am Gerät nicht (Manual + Davids Beobachtung).
