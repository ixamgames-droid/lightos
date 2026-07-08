# DMX-Output- & Netzwerk-Sender-Audit (2026-07-08)

**Auftrag:** AUD-03 — verifizierte Bug-/Risiko-Liste für den DMX-Output-Pfad (was tatsächlich an die
Fixtures geht): `src/core/dmx/artnet.py`, `sacn.py`, `output_manager.py` (der 44-Hz-Sendeloop),
`serial_process.py` (Enttec/Serial-Worker).

**Methode:** 5-Dimensionen-Workflow (Protokoll-Framing · Send-Robustheit/Exception-Isolation ·
OutputManager-Lock/Lifecycle · Serial-Lifecycle · Multicast/Broadcast/Binding), jedes Finding
**adversarial gegen den echten Code verifiziert** (je 2 Skeptiker). **19 Agenten, 7 Roh-Befunde →
6 CONFIRMED + 1 PLAUSIBLE, 0 zurückgewiesen.** Nach adversarialer Severity-Korrektur blieb **genau
ein P2** (der Rest P3). Zeilennummern gegen `main` (`5ec18d5`).

## Positiv bestätigt (kein Bug)

- **Bytes auf der Leitung sind spec-konform (beide Protokolle):** ArtNet `_build_artdmx` (Vektoren,
  `<H`-Universe = SubUni/Net-Byte-Reihenfolge, Sequence, 2..512-Länge) und sACN `_pack_framing`
  (Root-/Framing-/DMP-PDU-Längen, `0x7000|len`-Flags, Vektoren, `prop_count=n+1`, Start-Code) sind
  korrekt. **Kein falsches DMX-Paket.**
- **Der 44-Hz-Output-Loop stirbt nicht durch Sende-Fehler (adversarial widerlegt):** `_send_all`
  kapselt jeden Adapter-`send` in try/except (`output_manager.py:307-321`) **und** `_loop` den ganzen
  Frame (`:255-260`). Obwohl `ArtNetSender.send_dmx` selbst kein try/except hat, kann ein `sendto`-Fehler
  den Loop **nicht** beenden — alle anderen Universen laufen weiter.
- **Lock-Disziplin robust:** GIL-atomare Snapshot-Iteration der Registries, Senden unter `_io_lock`,
  race-freies swap-then-close in `_swap_device`. Kein „dict changed size", kein Loop-Tod.
- **Universe→Wire-Abbildung korrekt** (sACN = Universe-Nr, ArtNet = Nr−1) und getestet.

---

## Befunde (nach Severity)

### 🟠 P2

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **OUT-05** | `output_manager.py:163-188` · `app_state.py:754-772` | **Kein Entfernen/Disable eines Adapters pro Universe → Typ-Wechsel & „Disabled" lassen den Alt-Adapter offen und sendend.** `add_enttec/add_artnet/add_sacn` schreiben nur in ihre **eigene** Registry; es gibt **keine** `remove_*`/Disable-API (grep: kein `_artnet_outputs.pop`/`_sacn_outputs.pop`). `apply_output_config` enthält nur `add_*` und **keinen** „Disabled"-Zweig. Folgen: (1) **Typ-Wechsel** (Universe 1 von ArtNet auf sACN) → `_artnet_outputs[1]` bleibt gesetzt → `_send_all` sendet das Universe im nächsten Frame über **beide** Adapter (Doppel-Output; ArtNet flutet weiter das alte Ziel, obwohl abgeschaltet). (2) **„Disabled"** matcht keinen `if/elif` → ein zuvor eingerichteter Enttec bleibt offen und `_send_all` schreibt **weiter physisch DMX** → ein als deaktiviert markiertes Universe gibt real weiter Licht aus, nur per App-Neustart stoppbar. (3) **Ressourcen-Leak:** das Socket/serielle Handle des Alt-Adapters wird nie `close()`t. (Enttec→Enttec auf demselben COM ist via `close_enttec_on_port` abgedeckt; Cross-Typ und „Disabled" nicht.) | `OutputManager.remove_output(universe)`/`disable_universe(universe)`: `_enttec/_artnet/_sacn_outputs[universe]` unter `_io_lock` poppen und die Geräte `close()`en (Muster wie `_swap_device`). `apply_output_config` entfernt vor dem Einrichten des neuen Typs alle Alt-Adapter des Universums und behandelt „Disabled" explizit → pro Universe genau ein (oder kein) Adapter. |

### 🟡 P3

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **NET-04** | `sacn.py:93-100` · `artnet.py:25` | **Kein explizites Egress-Interface / Broadcast-Default → auf Multi-NIC-Venue-PC (WLAN+LAN) gehen Pakete lautlos übers falsche NIC bzw. werden nicht geroutet.** (a) sACN-Multicast setzt **kein** `IP_MULTICAST_IF` → das OS wählt das Egress-Interface per Route (auf WLAN+LAN nicht-deterministisch). (b) ArtNet-Default `255.255.255.255` (Limited Broadcast) ist **nicht routbar** (Node im eigenen L3-Segment bleibt dunkel) + folgt der Default-Route + flutet das L2-Segment 44×/s. In beiden Fällen: `sendto` meldet Erfolg, UI zeigt „Aktiv", Fixtures bleiben schwarz. **Braucht Produkt-Entscheidung** (Interface-Auswahl im Output-Config + sinnvoller Default; kein Limited-Broadcast-Default). User-Workaround heute: Ziel-IP im Patch-Feld (Unicast) eintragen. | `setsockopt(IP_MULTICAST_IF, inet_aton(<NIC-IP>))` + Interface-Auswahl-Feld; ArtNet Unicast/gerichteten Broadcast statt `255.255.255.255`; Socket via `bind()` an die gewählte NIC. |
| **SERIAL-01** | `serial_process.py:167` | **Toter/falscher COM-Port zeigt dauerhaft „Verbunden", Rig bleibt still ohne Fehlersignal.** `EnttecProcessProxy.is_open()` gibt `p.is_alive()` zurück (Prozess lebt) — **ohne** Bezug zum Port-Zustand. Der Worker setzt bei Öffnen-Fehler `ST_DISABLED`, aber `is_disabled()`/`ST_DISABLED` wird von **keinem** UI-Code gelesen; `output_config` zeigt nach `add_enttec`-Erfolg „Verbunden". Der Bediener kann das dunkle Rig nicht diagnostizieren. (Der In-Proc-Fallback würde beim selben Bad-Port sofort „Fehler" zeigen → widersprüchliches Feedback.) | `is_open()`/ein neues `output_live` am `ST_OK/ST_DISABLED`-Status ausrichten; Output-Config `is_disabled()` pollen und „Kein Signal" statt „Verbunden" anzeigen. |
| **SERIAL-02** | `serial_process.py:94` · `enttec_pro.py:131` | **Reconnect ist auf die ursprüngliche COM-Nummer festgenagelt → USB-Replug mit neuer COM-Nummer heilt nie** (widerspricht der „ohne App-Neustart"-Zusage in `enttec_pro.py:48-49`). Worker-Factory und `_try_reconnect` öffnen nur `self.port` erneut; die vorhandene `find_enttec_port()` (VID/PID) wird beim Reconnect **nie** genutzt. (Randfall — FTDI behält meist dieselbe COM-Nr am selben Port.) | Beim Reconnect optional per VID/PID neu auffinden, wenn der konfigurierte Port nicht öffnet; sonst UI-Warnung, dass ein COM-Nummernwechsel manuelles Re-Connect braucht. |
| **OUT-06** | `sacn.py:88` · `close()` | **sACN-Quellen-Lebenszyklus (Interop-Hygiene):** (a) **CID** = `uuid.uuid4().bytes` **neu pro Instanz** (jeder Neustart/Adapter-Swap = neue Quelle für Empfänger, die per CID tracken). (b) `close()` sendet **keine Stream-Termination** → bei Adapter-Wechsel ~2,5 s zwei aktive Quellen gleicher Priorität (kurzes HTP-Merge-Fenster). Beides E1.31-Konformitäts-Lücken, kein falsches Paket. | CID persistieren (Config/Maschinen-ID); beim `close()` ein Paket mit Options-Bit „Stream_Terminated" senden. |

---

## Zusammenfassung

Der Output-Pfad ist **auf der Byte- und Loop-Ebene solide**: korrekte Protokoll-Pakete, ein doppelt
abgesicherter 44-Hz-Loop (kein Loop-Tod durch Sende-Fehler), robuste Locks, korrekte Universe-Abbildung.
Der einzige harte Defekt ist der **Adapter-Lifecycle** (OUT-05, P2): mangels Remove/Disable-API senden
nach einem Typ-Wechsel zwei Adapter parallel und ein „deaktiviertes" Universe gibt weiter Licht aus.
Die übrigen Befunde sind P3 — Netz-Egress-Interface (NET-04, braucht Produkt-Entscheidung),
Serial-Diagnose/Reconnect (SERIAL-01/02) und sACN-Interop-Hygiene (OUT-06). Empfehlung: **OUT-05 zuerst**
(konkreter, testbarer P2), der Rest nach Priorität / Davids Netzwerk-Präferenz.
