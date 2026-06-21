# Geschwindigkeits-Umbau — QLC+-Speed-Dial + Master/Submaster-Hierarchie

> **Status (2026-06-16): KOMPLETT — Phasen A–E umgesetzt, getestet & (UI) live verifiziert.** Architektur: Bus-Ebene, Grand-Master-Override, Faktor-Default ¼ ½ 1 2 4, Speed-Dial im Beat-Modus.
> Baut auf [TEMPO_SYNC_PLAN.md](TEMPO_SYNC_PLAN.md) (Phasen 1–5 fertig) und [BPM_MANAGER_PLAN.md](BPM_MANAGER_PLAN.md) auf.
> Ziel: die Geschwindigkeitsregelung so verhalten lassen wie der **QLC+ Speed Dial** (Multiplikator-Gitter,
> umschaltbare Anzeige-Teile, mehrere Funktionen je Regler) und sie um eine **explizite Master/Sub-Hierarchie**
> erweitern (Sound-Master, mehrere Tap-Master, Sub-Speeds mit Faktor, ein Grand-Master-Override).

---

## 1. Was du willst (verstanden)

1. **QLC+-Speed-Dial-Verhalten** als Basis: ein Geschwindigkeitsregler mit
   - **Multiplikator-Gitter** (in QLC+: `1/16 1/8 1/4 1/2` zum Teilen, `2 4 8 16` zum Multiplizieren, Mitte = aktueller Faktor `Nx`, `-`/`+` schrittweise, `X` = Reset auf `1x`),
   - **TAP**, optionalem **Rad** (Drehknopf), optionalem **Anwenden**-Button,
   - **umschaltbaren Anzeige-Teilen** (QLC+ „Erscheinungsbild": `Rad`, `Tap`, `Multiplikatoren`, `Anwenden`, und Zeit-Modus `Stunden/Minuten/Sekunden/Millisekunden` **oder** Beat-Modus `Takte`).
2. **Behalten:** die digitale **BPM-Anzeige** aus der jetzigen Software (`VCBpmDisplay`) — die ist gut.
3. **Master vs. Sub-Speed (neu, pro Speed-Knoten einstellbar):**
   - **Master-Speed** = eigenständiges Tempo (eigene BPM via Tap/Zahl/Audio).
   - **Sub-Speed** (Nicht-Master) = läuft erst **synchron** mit einem Master, lässt sich dann aber per Faktor (`½`, `¼`, `×2`, `×4`, …) **relativ** zum Master verlangsamen/beschleunigen. Effekte, die am Sub hängen, laufen entsprechend langsamer/schneller.
   - Die **Faktor-Buttons** (`½ ¼ ×2 ×4` …) sind konfigurierbar; bei mehr Komplexität eine eigene **GUI** zum Einstellen.
4. **Tempo-Quellen-Hierarchie (neu):**
   - **Ein** Master-**Sound-BPM**, das auf Audio reagiert (= heutiger `BPMManager` Audio/AUTO).
   - **Mehrere** manuelle **Master-Tap-BPMs**, gesetzt per Zahlenfeld oder Tap, frei anlegbar.
   - Sub-Speeds können von **jedem** dieser Master abhängig gemacht werden.
   - **Ein übergreifender Grand-Master**, der — wenn aktiviert — am Ende **alle übertrumpfen** kann.
5. **VC-Patching vereinfachen (eigener Arbeitsstrang / Subagent):**
   - Speed-Dial in die VC ziehen, dann **mehrere Effekte draufziehen** → werden an den Regler **gekoppelt**.
   - Wie QLC+ „Funktionen"-Tabelle: je angehängtem Effekt **auswählen, welcher Teil gesteuert** wird (Tempo / welcher Parameter).
   - Im **Long-Press-/Einstellungs-Menü** eines Bedienelements die Liste der gekoppelten Effekte + Parameter-Auswahl zeigen.

---

## 2. Wie QLC+ es macht (live inspiziert, 2026-06-16)

QLC+ hat **genau einen** globalen Takt (oben rechts `BPM: 120`). Ein **Speed Dial** editiert eine Zeit —
entweder in `ms` (Zeit-Modus) **oder** in `Takte` (Beat-Modus, an den globalen BPM gekoppelt). Das
**Multiplikator-Gitter** skaliert diese Zeit (`×2` = doppelt so schnell, `1/2` = halb so schnell);
der aktuelle Faktor steht in der Mitte (`1x`), `X` setzt zurück.

Eine **Funktionen-Tabelle** im Editor hängt **mehrere** Funktionen an den Dial; je Funktion ist wählbar,
**welche** Zeit der Dial steuert (`Einblenden` / `Ausblenden` / `Dauer`). Das **Erscheinungsbild**-Panel
schaltet die sichtbaren Teile (Rad / Tap / Multiplikatoren / Anwenden / Zeit-Felder / Takte) an/ab.

→ Das deckt sich fast 1:1 mit dem, was LightOS bereits hat (Bus + `tempo_multiplier` + Beat-Position) —
**fehlt** nur die UI-Parität (Faktor-Gitter, Anzeige-Schalter) und die **Hierarchie über dem einen globalen Takt**.

---

## 3. Was schon da ist (kartiert) — und was fehlt

### Vorhanden (TEMPO_SYNC Phasen 1–5, BPM-Manager)
- `BPMManager` (`src/core/engine/bpm_manager.py`) — **globaler Leader**, AUTO(Audio)/MANUAL, Tap/Nudge/Lock, Präzedenz `MANUAL > OS2L > Audio > Datei`. **= unser „Sound-BPM-Master" + Kandidat fürs „Grand-Master"-Konzept.**
- `TempoBus` / `TempoBusManager` (`src/core/engine/tempo_bus.py`) — benannte Uhren mit kontinuierlicher `position()`; `source ∈ {manual, tap, bpm_global, external}`; `default`-Bus proxyt `BPMManager`; feste Buses `A/B/C/D`; `armed_bus_id`; `attach_source(TempoSource)`. **= unsere „mehreren Tempi".**
- `Function`-Felder (`function.py`): `tempo_bus_id`, `tempo_multiplier` (0.0625–16), `phase_offset`, `sync_group`, privat `_beat_anchor`. Generisch geladen in `function_manager.from_dict`, persistiert in `show_file.py` (`tempo_buses`-Block). **= unsere „Effekt folgt Knoten × Faktor"-Bindung.**
- Effekt-Sync: `RgbMatrixInstance._advance_step`, `EfxInstance._sync_from_bus`, `Chaser._advance_from_bus`, `Sequence._bus_steps_to_advance` — alle leiten Phase/Step aus der Bus-Position × Multiplier ab.
- VC: `VCSpeedDial` (`SpeedTarget.TEMPO_BUS` setzt Bus-BPM, `TEMPO_BUS_MULT` setzt `tempo_multiplier`, Tap/Sync), `VCBusSelector` (setzt `armed_bus_id`), `VCBpmDisplay` (digital, pro Bus), `SliderMode.TEMPO_BUS`, `ButtonAction.TAP_BUS/SYNC_BUS/ARM_BUS`.
- Smart-Drop: `smart_drop_dialog.py` (3-Schritt-Dialog), `vc_effect_meta.py` (`Capabilities`/`ControlOption`/`ControlKind`), `apply_drop(interactive=…)`, `_build_from_smart_result`. `VCSlider` **und** `VCSpeedDial` halten bereits `function_ids: list[int]` (Multi-Effekt!).

### Lücken (das, was dieser Plan baut)
- **L1 — Hierarchie ist flach.** Buses sind unabhängig; es gibt kein „dieser Bus folgt jenem Master × Faktor". → Master/Sub-Beziehung **auf Bus-Ebene** fehlt.
- **L2 — Kein Grand-Master-Override.** Kein globaler Schalter „alle Master folgen jetzt dem Grand-Master".
- **L3 — Buses sind fix (A/B/C/D).** Kein UI zum **Anlegen/Benennen** beliebig vieler Tap-Master.
- **L4 — Speed-Dial hat keine QLC+-Parität.** Kein Multiplikator-**Gitter** (nur ein Multiplikator-Modus übers Rad), keine `-/+/X`-Faktor-Schaltflächen, keine **Anzeige-Schalter** (Rad/Tap/Multiplikatoren/Anwenden/Zeit vs. Takte).
- **L5 — Master/Sub-Konfig-GUI fehlt.** Kein Dialog, in dem ein Speed-Knoten als Master/Sub deklariert, der Parent gewählt und das Faktor-Button-Set konfiguriert wird.
- **L6 — Smart-Drop koppelt nur 1 Effekt.** Mehrfach-Drop auf denselben Regler **ersetzt** statt **anzuhängen**; im Einstellungs-Menü fehlt die **Effekt-Liste + Parameter-Auswahl je Effekt** (QLC+ „Funktionen"-Tabelle).

---

## 4. Zielmodell — der Tempo-Baum

```
GRAND-MASTER (Override)              optionaler globaler Takt; "scharf" => alle Master folgen ihm
        │  (nur wenn aktiviert)
        ▼
MASTER-EBENE                          eigenständige Tempi (eigene BPM)
   ├─ Sound-BPM     (Audio)           = BPMManager (AUTO/Audio)
   ├─ Tap-Master 1  (Tap/Zahl)        = TempoBus(source=manual/tap)
   ├─ Tap-Master 2  (Tap/Zahl)        = TempoBus(...)
   └─ … beliebig viele, frei benennbar
        │
        ▼
SUB-SPEED-EBENE                       folgt EINEM Master, eigene effektive BPM = parent.bpm * bus_multiplier
   └─ Sub "× ½", parent = Sound-BPM    (Faktor-Gitter ½ ¼ ×2 ×4 …)
        │
        ▼
EFFEKTE                                gebunden an einen Speed-Knoten (Master ODER Sub)
   └─ effektive Rate = node.bpm * Function.tempo_multiplier   (Function-Multiplier = Fein-Verhältnis)
```

**Designentscheidung (D-A): Master/Sub lebt auf der Bus-Ebene.** Ein `TempoBus` bekommt:
- `role: "master" | "sub"` (Default `master` — rückwärtskompatibel),
- `parent_id: str` (bei `sub`: ID des Masters, dem gefolgt wird; `""`/`bpm_global` = Sound-BPM),
- `bus_multiplier: float` (Faktor zum Parent; `1.0` Default; UI-Buttons setzen `½ ¼ ×2 ×4 …`).

Ein **Sub-Bus** rechnet seine effektive BPM **abgeleitet**: `effective_bpm = parent.effective_bpm * bus_multiplier`,
und seine **Phase bleibt am Parent verankert** (gleicher `position`-Bezug → echte Phasen-Kopplung wie im Tempo-Sync-Plan,
nur eben zwischen Bussen statt nur zwischen Effekten). Ein **Master-Bus** verhält sich wie heute (eigene Quelle).

**Designentscheidung (D-B): Function-`tempo_multiplier` bleibt** als *zusätzliche* Fein-Stufe pro Effekt
(z. B. zwei Effekte auf demselben Sub, einer ×1, einer ×2). Bus-Multiplier (grob, „dieser Speed") × Function-Multiplier (fein, „dieser Effekt").

**Designentscheidung (D-C): Grand-Master = Manager-Flag.** `TempoBusManager.grandmaster_armed: bool` +
`grandmaster_bpm` (gespeist aus Tap/Audio). Wenn scharf, liefert `effective_bpm()` jedes **Master**-Busses
den Grand-Master-Takt (Subs bleiben relativ über ihren Parent). „Übertrumpft alles" = ein einziger Schalter.
Quelle des Grand-Masters wählbar (eigener Tap **oder** ein bestehender Master als Referenz).

---

## 5. Umbau in Phasen (jede einzeln testbar)

> Reihenfolge: erst die **Engine-Hierarchie** (headless, testbar), dann die **Speed-Dial-UI** (QLC+-Parität),
> dann die **Konfig-GUI**, zuletzt das **Smart-Drop/Multi-Effekt-Patching** (eigener Subagent).

### Phase A — Bus-Hierarchie in der Engine ✅ FERTIG (2026-06-16, grün)
Umgesetzt in `tempo_bus.py`: `role`/`parent_id`/`bus_multiplier` + Anker (`_sub_local_origin`/`_sub_parent_origin`); Sub-Position/BPM lazy aus dem Parent abgeleitet (stetig über Anker); `set_role`/`set_parent`/`set_bus_multiplier`/`reanchor_to_parent`; `_would_cycle`-Schutz; `to_dict` emittiert Hierarchie-Keys nur bei Abweichung (rückwärtskompatibel); `load_dict` re-ankert Subs. Tests: `tests/test_tempo_master_sub.py` (14, grün). Effekte brauchten KEINE Änderung (lesen `bus.snapshot()`).

### Phase A (Original-Skizze) — Bus-Hierarchie in der Engine (Risiko: mittel)
`tempo_bus.py`: Felder `role`/`parent_id`/`bus_multiplier`; `effective_bpm()` rechnet Sub = parent × multiplier;
Phase eines Subs aus der Parent-`position()` ableiten (kein eigener Free-Run, solange Parent läuft);
Zyklus-Schutz (Sub darf nicht sich selbst/ringförmig folgen); `to_dict/from_dict` erweitern; `load_dict` defaultet alte Buses auf `role=master`.
*Tests: Master 120 + Sub ×½ → Sub-position halb so schnell, phasengleich; Parent-BPM-Änderung zieht Sub mit; Zyklus wird abgefangen; alte `.lshow` laden unverändert.*

### Phase B — Grand-Master-Override ✅ FERTIG (2026-06-16, grün)
Umgesetzt in `tempo_bus.py`: `TempoBusManager.grandmaster_armed/grandmaster_bpm` (Properties) + `set_grandmaster_armed`/`set_grandmaster_bpm` (Clamp) + `tap_grandmaster()`. `TempoBus._grandmaster_drive()` (lockfreier Manager-Read) übertrumpft in `advance_frame`/`_eff_bpm`/`bpm` die eigene Quelle (auch external/bpm_global), ohne `_bpm` zu überschreiben → beim Entschärfen kehrt die eigene BPM zurück. Subs bleiben relativ (Grand × Faktor über den Parent). Tests: `tests/test_tempo_grandmaster.py` (8, grün). **Offen:** Persistenz des Grand-Master-Zustands (bewusst zurückgestellt — Default „aus" ist der sichere Lade-Zustand; wird beim Anfassen von `show_file.py` in Phase C/D ergänzt).

### Phase C — QLC+-Speed-Dial-Parität ✅ FERTIG (2026-06-16, grün)
Umgesetzt in `vc_speedial.py`: neuer Modus `SpeedTarget.SPEED_NODE` (der Dial konfiguriert direkt einen Tempo-Bus). Rolle **Master** = klassisches Rad/Tap setzt Bus-BPM (`bus.set_role("master")`/`set_bpm`). Rolle **Sub** = neues **Faktor-Gitter** `¼ ½ 1 2 4` (konfigurierbares Set via `_parse_factor_token`/`_fmt_factor`) + `−`/`+`/`⟳` + **Sync** (Downbeat neu) + integrierte BPM-Anzeige; klickt einen Faktor → `bus.set_bus_multiplier`, Rolle/Parent via `_ensure_node_config`. Anzeige-Schalter `show_dial/tap/factors/sync/bpm` (= QLC+ „Erscheinungsbild"). Klassische Modi (EXECUTOR/FUNCTION/TEMPO_BUS/TEMPO_BUS_MULT) unverändert (rückwärtskompatibel, `to_dict`/`apply_dict` defaulten auf Master). `VCBpmDisplay` bleibt separat erhalten. Tests: `tests/test_vc_speed_node.py` (9, grün). **Offen in C:** Live-Verifikation im echten Qt-Fenster (GDI-Capture) + ggf. Default-Größe/Auto-Layout-Feinschliff.

### Phase C (Original-Skizze) — QLC+-Speed-Dial-Parität (Risiko: mittel) — VC-Widget
`VCSpeedDial` erweitern (oder neues `VCSpeedWidget`, das `VCSpeedDial` ablöst, mit Back-Compat-`apply_dict`):
- **Multiplikator-Gitter** als echte Buttons (Set konfigurierbar; Default `¼ ½ 1 2 4`, optional `1/16…16` wie QLC+), `-`/`+`-Schritt, `X`-Reset, Mitte zeigt `Nx`.
- **Anzeige-Schalter** (`show_dial`, `show_tap`, `show_mult`, `show_apply`, `show_bpm`, `mode = beats|time`) — spiegelt QLC+ „Erscheinungsbild".
- Faktor wirkt auf **`bus_multiplier`** des Ziel-Subs (Sub-Modus) bzw. auf die Bus-BPM (Master-Modus) bzw. auf `Function.tempo_multiplier` (Effekt-Direktbindung) — je nach Ziel.
- **BPM-Anzeige** integriert/danebenstellbar (`VCBpmDisplay` bleibt eigenständig nutzbar → Wunsch „die digitale behalten").
*Tests: Gitter setzt Faktor; `X` reset; Anzeige-Schalter blenden Teile aus; Round-Trip; alte SpeedDials laden weiter.*

### Phase D — Master/Sub-Konfig-GUI 🟡 TEILWEISE (2026-06-16)
**D1 ✓ Grand-Master-Persistenz (grün):** `TempoBusManager.grandmaster_to_dict()`/`load_grandmaster()`; `show_file.py` speichert/lädt/resettet `tempo_grandmaster` (additiver Block, neue Show kommt nie scharf hoch). Test: `tests/test_tempo_grandmaster.py::test_grandmaster_persistence_roundtrip`.
**D2 ✓ Konfig-Panel (grün):** in `bpm_manager_view.py` (Ctrl+8) Panel „Tempo-Speeds && Grand-Master" — Grand-Master-Zeile (scharf/BPM/Tap/Status), Bus-Tabelle (Bus/Rolle/Folgt/Faktor/BPM, Default zuerst), Master anlegen/benennen/löschen, Editor-Zeile (Rolle/Parent/Faktor → `set_role`/`set_parent`/`set_bus_multiplier`). Live verifiziert (nativer Render). Test: `tests/test_bpm_view_speeds.py` (6). (Pro-Widget-Konfig zusätzlich im Speed-Dial-⚙-Dialog aus Phase C.)

### Phase D (Original-Skizze) — Master/Sub-Konfig-GUI (Risiko: niedrig-mittel)
Eigener Dialog (aus dem Long-Press-/Einstellungs-Menü des Speed-Widgets **und** aus einem Tempo-Übersichts-Tab):
- Knoten als **Master** oder **Sub** deklarieren; bei Sub: **Parent** wählen (Liste aller Master) + Start-Faktor;
- **Faktor-Button-Set** konfigurieren (welche Buttons das Gitter zeigt);
- Master anlegen/benennen/löschen (löst **L3**); Grand-Master scharf/aus + Quelle.
*Tests: Dialog legt Master an, macht Bus zum Sub, ändert Faktor-Set; Persistenz.*

### Phase E — Smart-Drop & Multi-Effekt-Kopplung ✅ FERTIG (2026-06-16, grün, via Subagent)
Umgesetzt: `apply_drop` hängt einen Effekt an ein bereits gebundenes `VCSlider`/`VCSpeedDial` an (Helper `_couple_effect`, dedupe) statt zu ersetzen; `VCButton`/`VCEncoder` auf `function_ids` gehoben (Toggle/Flash/Nudge über alle Ziele); neues `param_keys_per_id: dict[int,str]` auf `VCSlider`/`VCSpeedDial`/`VCEncoder` (je Effekt eigener gesteuerter Parameter, `_apply` nutzt ihn, sonst Default); Eigenschaften-Dialoge bekommen Abschnitt „Gekoppelte Effekte" (Name + Combo Parameter, Optionen aus neuem `vc_effect_meta.mappable_param_choices`/`effect_name`); `SmartDropResult` um `function_ids`/`param_keys_per_id` erweitert, `_build_from_smart_result` wendet sie an. Alles rückwärtskompatibel (Single-Effekt unverändert). Test: `tests/test_vc_multi_effect.py` (18). Verifiziert: 94 VC-/Tempo-Tests grün.

### Phase E (Original-Skizze) — Smart-Drop & Multi-Effekt-Kopplung (Risiko: mittel) — **eigener Subagent**
- `apply_drop` auf ein **bestehendes** Speed-Widget = **anhängen** (in `function_ids`), nicht ersetzen.
- `SmartDropResult` um `function_ids` + `param_keys_per_id: dict[int,str]` erweitern; Dialog-Schritt „weitere Effekte / welcher Parameter je Effekt".
- Einstellungs-Menü (`_open_properties`) der Speed/Slider/Button-Widgets: **Effekt-Liste** mit Spalten *Effekt | gesteuerter Parameter* (QLC+-„Funktionen"-Tabelle nachempfunden); `VCButton`/`VCEncoder` auf `function_ids` heben (heute nur `VCSlider`/`VCSpeedDial`).
- `_apply()` iteriert über `function_ids` × jeweiligen `param_key`.
*Tests: 2 Effekte auf einen Speed-Dial droppen → beide gekoppelt; Parameter-Auswahl je Effekt round-trippt; Tempo-Faktor wirkt auf alle.*

---

## 6. Offene Entscheidungen (vor Phase A klären)

1. **D-A bestätigen:** Master/Sub auf **Bus-Ebene** (empfohlen) — ok? Oder Sub-Verhalten nur über `Function.tempo_multiplier` (kein Bus-Parent)?
2. **Grand-Master-Semantik:** „scharf" zwingt Master auf Grand-**BPM** (Subs bleiben relativ, empfohlen) — oder soll Grand auch Subs hart auf seinen Takt ziehen (Faktoren ignorieren)?
3. **Faktor-Set Default:** `¼ ½ 1 2 4` (sauber harmonisch) als Default, `1/16…16` optional zuschaltbar — passt das, oder von Anfang an das volle QLC+-Set?
4. **Speed-Dial:** bestehendes `VCSpeedDial` **erweitern** (Back-Compat) — oder ein **neues** Widget bauen und SpeedDial als „klassisch" behalten?
5. **Zeit-Modus (`ms`):** brauchst du QLC+'s Stunden/Minuten/Sek/ms-Modus überhaupt, oder reicht der **Beat/BPM-Modus** (Takte)? (Spart Phase-C-Aufwand.)
6. **Beginn:** mit **Phase A** (Engine-Fundament) starten — oder zuerst sichtbar die **Speed-Dial-UI** (Phase C) auf dem schon vorhandenen flachen Bus-Modell?

---

## 7. Betroffene Dateien (Überblick)

| Datei | Änderung |
|---|---|
| `src/core/engine/tempo_bus.py` | `role`/`parent_id`/`bus_multiplier`; `effective_bpm()` (Sub = parent × mult, Phase am Parent); Grand-Master-Flag/BPM; Zyklus-Schutz; `to_dict/from_dict` |
| `src/core/show/show_file.py` | `tempo_buses`-Block um Hierarchie-Header (Grand-Master) erweitern |
| `src/ui/virtualconsole/vc_speedial.py` | Multiplikator-Gitter, `-/+/X`, Anzeige-Schalter, Master/Sub-Ziel, BPM-Integration |
| `src/ui/virtualconsole/vc_bpm_display.py` | bleibt (Wunsch: behalten), evtl. Grand-Master-/Master-Quelle anzeigen |
| `src/ui/virtualconsole/vc_bus_selector.py` | beliebig viele Buses statt fix A–D; Master/Sub-Kennzeichnung |
| `src/ui/virtualconsole/smart_drop_dialog.py` + `vc_effect_meta.py` | Mehrfach-Effekt, `param_keys_per_id`, Anhänge-Schritt |
| `src/ui/virtualconsole/vc_canvas.py` | `apply_drop` = anhängen auf bestehendes Widget; `_build_from_smart_result` |
| `src/ui/virtualconsole/vc_button.py` / `vc_encoder.py` | `function_ids`-Support; Effekt-Liste + Parameter-Auswahl im `_open_properties` |
| `src/ui/views/…` (neuer Tempo-/Master-Tab oder Dialog) | Master/Sub-Konfig-GUI, Master anlegen/benennen, Grand-Master-Schalter |

---

## 8. Rückwärtskompatibilität
- `role` default `master`, `parent_id=""`, `bus_multiplier=1.0` → bestehende Buses verhalten sich **byte-genau** wie heute.
- `tempo_bus_id=""` auf Effekten → Free-Run unverändert (Tempo-Sync-Garantie aus TEMPO_SYNC_PLAN bleibt).
- Speed-Dial-`apply_dict` toleriert fehlende neue Keys (Default = klassisches Verhalten).
- Grand-Master default **aus** → keine Wirkung, bis explizit scharf.
