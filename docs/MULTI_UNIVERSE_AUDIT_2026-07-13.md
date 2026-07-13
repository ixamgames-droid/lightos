# Multi-Universe- & Mixed-Adapter-Audit (2026-07-13)

**Auftrag:** AUD-01 (P2, reine Doku) — verifizierte Bug-/Risiko-Liste zum Betrieb **mehrerer
Universen mit GEMISCHTEN Ausgabe-Adaptern** (Enttec USB, Art-Net und sACN gleichzeitig auf
verschiedenen Universen). Untersuchte Achsen: **Zuweisung** (welcher Adapter auf welches Universum),
**Persistenz** (`data/universes.json`, `_persist_output`, `AppState.apply_output_config`),
**Rendering** (`OutputManager._send_all`, Grand-Master-Adressmaske pro Universum).

**Scope-Dateien:** `src/core/dmx/output_manager.py` · `src/core/app_state.py` (`apply_output_config`,
`_rebuild_render_plan`, `_build_gm_mask`) · `src/ui/widgets/output_config.py`. Zeilennummern gegen
`main` @ `e7a567a`.

**Methodik:** Statischer Trace jedes Zuweisungs-Pfades (Live-Tabs vs. Universe-Manager vs.
Start-Rehydrierung) → Registry-Zustand im `OutputManager` → Sendeschleife `_send_all`. Für jeden
Verdachtsfall wurde der konkrete Auslöser gegen den echten Code geprüft (belegt/widerlegt). Kein
Code-Change, keine Tests (reine Doku).

## Abgrenzung zu AUD-03 (DMX_OUTPUT_AUDIT_2026_07_08)

[`DMX_OUTPUT_AUDIT_2026_07_08.md`](DMX_OUTPUT_AUDIT_2026_07_08.md) fand mit **OUT-05** den
Doppel-Output beim Typ-Wechsel. Der Fix landete **nur im Rehydrierungs-Pfad**
`apply_output_config` (`app_state.py:810-822`: erst `remove_output(num)`, dann genau ein `add_*`) und
im Universe-Manager-Speichern (`output_config.py:367` ruft `apply_output_config`). **Die drei
Live-„Übernehmen"/„Verbinden"-Buttons wurden NICHT nachgezogen** — dort lebt OUT-05 in einer
gemischten Session weiter (MU-01, unten). Dieses Audit ergänzt AUD-03 um die Mixed-Adapter- und
Multi-Universe-Perspektive.

## Positiv bestätigt (kein Bug)

- **Grand-Master-Maske ist adapter-agnostisch und pro Universum korrekt (Verdacht WIDERLEGT).**
  In `_send_all` wird `data` je Universum **einmal** anhand `self._gm_address_mask.get(univ_num)`
  gedimmt (`output_manager.py:306-321`) und **danach** an alle Adapter dieses Universums geschickt
  (`:328-342`). Die Maske hängt an der Universe-Nummer, nicht am Adaptertyp — ein Universum, das
  gleichzeitig z. B. via Enttec **und** Art-Net ginge, bekäme identisch maskiertes DMX auf beiden
  Wegen. `_build_gm_mask` sät **jedes gepatchte DMX-Universum** (auch leer) als Key
  (`app_state.py:1998-2004`), sodass „gepatcht ohne Intensität" (leere Maske → nichts skalieren)
  sauber von „rohes Universum" (kein Key → global dimmen, `:309-312`) getrennt bleibt. **Für
  gemischte Universen ist die GM-Maske korrekt.**
- **Rehydrierung beim Start ist pro Universum sauber (Verdacht WIDERLEGT).**
  `apply_output_config` (`app_state.py:801-825`) legt fehlende Universen an, ruft **vor** dem
  Einrichten `remove_output(num)` und setzt dann genau einen Adapter — Mixed-Setups
  (U1 Enttec, U2 Art-Net, U3 sACN) werden nach Neustart korrekt getrennt wiederhergestellt.
- **Registry-Zugriff ist thread-sicher.** Snapshot-Iteration + `_io_lock` in `_send_all`
  (`output_manager.py:324-342`) und swap-then-close in `_swap_device` (`:149-161`); kein „dict changed
  size" bei gleichzeitigem Zuweisen aus dem UI-Thread.

---

## Befundtabelle

| Nr | Datei:Zeile | Schwere | Beschreibung | Status |
|----|-------------|---------|--------------|--------|
| **MU-01** | `output_config.py:284-289` · `:302-306` · `:383-388` (vs. `app_state.py:816`) | 🟠 P2 | **Live-Tabs erzeugen Doppel-Output/Leak bei Cross-Typ-Wechsel (OUT-05, im Live-Pfad ungefixt).** `_connect_enttec`, `_apply_artnet`, `_apply_sacn` rufen nur `add_enttec/add_artnet/add_sacn` — diese schreiben via `_swap_device` **nur in ihre eigene Registry** (`output_manager.py:184-188`). Ein `remove_output(num)` wie in `apply_output_config` fehlt. **Belegt.** | belegt |
| **MU-02** | `output_config.py:291-294` · `:372-375` | 🟠 P2 | **„Deaktivieren" per Checkbox stoppt die Ausgabe nicht.** Bei nicht gesetzter Checkbox setzt `_apply_artnet`/`_apply_sacn` nur das Status-Label und `return` — ein zuvor eingerichteter Adapter bleibt in der Registry und `_send_all` sendet weiter. Kein `remove_output`. **Belegt.** | belegt |
| **MU-03** | `output_config.py:109-111` (vs. `output_manager.py:335`) | 🟡 P3 | **Totes Bedienfeld „Art-Net Startuniversum".** `_spin_artnet_start_univ` wird angelegt/beschriftet, aber **nirgends gelesen** (repo-weite Suche: nur diese 3 Zeilen). Die externe Art-Net-Universe-Nummer ist in `_send_all` hart `univ_num - 1`. In Multi-Universe-Setups ist die externe Nummerierung damit **nicht konfigurierbar**. **Belegt.** | belegt |
| **MU-04** | `output_config.py:347-363` · `:315-326` (vs. `app_state.py:808`) | 🟡 P3 | **Universe-Nummern-Kollision/-Bereich ungeprüft.** Die `#`-Spalte ist freier Text; `_univ_save` parst `int()` nur mit `ValueError`-Fallback auf `r+1`, **ohne** Bereichsklemme (1–32) und **ohne** Dedup. Zwei Zeilen mit gleicher `num` → in `apply_output_config` gewinnt **still** die letzte (`remove_output` der ersten, dann `add_*` der zweiten); ungültige `num` (z. B. `0`) landet als Dict-Key und geht bei Art-Net als `univ-1 = -1` in `_build_artdmx`. **Belegt.** | belegt |
| **MU-05** | `output_config.py:244` · `:38-54` · `:347-370` | 🟡 P3 | **Live-persistierte Zeilen können vom Universe-Manager überschrieben werden (Reihenfolge/Staleness).** Die Tabelle wird **einmal beim Dialog-Aufbau** aus der Datei geladen (`_univ_load_table` @ `:244`). Verbindet man danach in einem Live-Tab ein neues Universum (`_persist_output` **hängt** eine Zeile an, `:51-53`) und speichert dann im Universe-Manager, schreibt `_univ_save` die **stale** Tabelle zurück → die live angehängte Zeile fehlt und geht in `universes.json` verloren (Adapter läuft bis zum Neustart weiter, wird danach nicht rehydriert). **Belegt.** | belegt |
| **MU-06** | `output_manager.py:335` · `sacn.py:107-132` | ⚪ Info | **Asymmetrische externe Nummerierung Art-Net vs. sACN.** Für dasselbe interne Universum `N` sendet Art-Net auf externem Universum `N-1` (`_send_all`), sACN auf `N` (`sacn.py:108`). Das entspricht der Konvention (Art-Net 0-basiert, sACN 1-basiert), kann in gemischten Setups aber überraschen (interne U1 = Art-Net 0 = sACN 1). Kein Bug, dokumentieren. | widerlegt (by design) |

---

### MU-01 im Detail (belegter Hauptfall)

Ablauf in **einer** laufenden Session (kein Neustart):

1. Enttec-Tab → Universe 1, COM3, „Verbinden": `_connect_enttec` → `om.add_enttec(1, "COM3")`
   → `_enttec_outputs[1] = <EnttecProxy COM3>` (`output_manager.py:163-168`).
2. Art-Net-Tab → Universe 1, „Art-Net aktivieren", „Übernehmen": `_apply_artnet`
   (`output_config.py:302-305`) → `om.add_artnet(1, ip)` → `_swap_device(self._artnet_outputs, 1, …)`
   berührt **nur** `_artnet_outputs`.
3. Ergebnis: `_enttec_outputs[1]` **und** `_artnet_outputs[1]` sind gesetzt. `_send_all`
   (`output_manager.py:328-337`) schickt Universum 1 im nächsten Frame über **beide** Adapter →
   Doppel-Output; das alte Enttec-Handle wird nie `close()`t (Leak), obwohl die Persistenz
   (`_persist_output`) die Zeile korrekt auf `"ArtNet"` umstellt. Erst ein Neustart (→
   `apply_output_config`) räumt auf.

**Regressionstest-Idee:** `OutputManager`-Unit-Test ohne echte Hardware: `add_enttec(1, "COM_FAKE")`
(mit `LIGHTOS_SERIAL_INPROC=1`) bzw. Registries direkt bestücken, dann den Pfad von `_apply_artnet`
nachbilden und asserten, dass nach der Zuweisung **genau ein** Adapter für Universum 1 registriert ist
(`len([r for r in (_enttec_outputs,_artnet_outputs,_sacn_outputs) if 1 in r]) == 1`). Analog MU-02:
nach „Deaktivieren" ist Universum 1 in keiner Registry mehr. Headless möglich (kein Qt-Event-Loop
nötig, wenn man die Adapter-Zuweisung des Buttons in eine testbare Methode zieht).

## Folge-Items (Vorschlag fürs BACKLOG)

- **ENG-xx (MU-01/MU-02, P2):** Live-Buttons `_connect_enttec`/`_apply_artnet`/`_apply_sacn` vor dem
  `add_*` `output_manager.remove_output(univ)` aufrufen lassen und den „deaktivieren"-Zweig ebenfalls
  `remove_output` ausführen — analog zum bereits gefixten `apply_output_config`-Pfad. Damit gilt „ein
  Universum → genau ein aktiver Adapter" auch ohne Neustart.
- **OUT-xx (MU-03, P3):** „Art-Net Startuniversum" verdrahten (externe Universe-Nr pro Universum
  persistieren + im Sendepfad statt `univ_num-1` verwenden) **oder** das tote Feld entfernen.
- **OUT-xx (MU-04, P3):** `_univ_save` auf 1–32 klemmen und Duplikat-`num` beim Speichern
  ablehnen/mergen (klare Meldung statt stillem Last-wins).
- **OUT-xx (MU-05, P3):** Universe-Manager-Tabelle vor dem Speichern gegen die aktuelle
  `universes.json` mergen (statt die beim Öffnen geladene Kopie blind zurückzuschreiben).

## Regressionstest-Idee (Persistenz, MU-04/MU-05)

Reiner Datei-Test ohne Qt: `_persist_output`/`_save_universe_config` in einen Temp-Pfad umlenken,
zwei Zeilen mit gleicher `num` schreiben und prüfen, dass `apply_output_config` deterministisch
genau einen Adapter pro Universum registriert; separat prüfen, dass ein via `_persist_output`
angehängtes Universum nach einem simulierten `_univ_save` mit stale Tabelle **nicht** verloren geht
(erwartet: Merge statt Überschreiben).
