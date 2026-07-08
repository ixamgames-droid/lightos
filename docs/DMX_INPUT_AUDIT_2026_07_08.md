# DMX-Eingang- & RX-Thread-Audit (2026-07-08)

**Auftrag:** AUD-06 — verifizierte Bug-/Risiko-Liste für den DMX-**Eingang** (empfängt externes
Art-Net/sACN und mischt es in die Show): `src/core/dmx/artnet_input.py`, `sacn_input.py` und der
Merge in `app_state.py` (`apply_input_merge`/`clear_input_merge`, `_render_frame` Schritt 4b-Input).
**Abgrenzung:** die Merge-**Logik** (HTP/LTP/REPLACE) ist via `tests/test_input_layer.py` getestet —
Fokus hier: die **ungetesteten RX-Threads** und der **Quellen-Verlust**.

**Methode:** 5-Dimensionen-Workflow (Stale-Werte/Source-Timeout · RX-Thread-Lifecycle ·
Merge-Config/Multicast-Join · Lock-Disziplin · Paket-Validierung), jedes Finding **adversarial
verifiziert** (je 2 Skeptiker). **15 Agenten, 5 Roh-Befunde → 5 CONFIRMED, 0 zurückgewiesen.**
Zeilennummern gegen `main` (`6d4b8be`).

## Positiv bestätigt (kein Bug)

- **Paket-Validierung robust (beide Parser):** ArtNet verwirft Pakete < 18 B vor jedem `struct.unpack`
  und klemmt `length` gegen die real vorhandenen Bytes + 512; sACN verwirft < 126 B, prüft
  Vector/`prop_count`/Start-Code und klemmt `slots`, der ganze Parse ist in `try/except → None`
  gekapselt. **Kein** manipuliertes/zu kurzes/langes Paket erzeugt negativen Slice, `IndexError`,
  `struct.error`, Thread-Tod oder ein injiziertes Universe.
- **Lock-Disziplin sauber:** Alle Mutatoren (`start/stop/set_merge/subscribe/join_universe`) laufen im
  Qt-UI-Thread; der RX-Thread **liest** nur (`list(_callbacks)`-Snapshot, `_merges.get`) — GIL-atomar,
  keine Race mit beobachtbarem Schaden. `findings: []`.
- **Multicast-Join korrekt (Hypothese widerlegt):** Die ausgelieferte UI (`_apply_sacn_input`) ruft vor
  jedem `set_merge` `start([in_u])` **oder** `join_universe(in_u)` → die Gruppe des konfigurierten
  Eingangs-Universums wird immer gejoint. (`set_merge` ohne Join ist ein API-Footgun ohne Aufrufer.)

---

## Befunde (nach Severity)

### 🔴 P1

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **NET-05** | `app_state.py:1631-1654` (+ `artnet_input.py:151`/`sacn_input.py:169`) | **Kein Source-Timeout → eine still gewordene Art-Net/sACN-Quelle friert Kanäle dauerhaft ein (Strahler bleibt an).** Beide Receiver rufen `apply_input_merge` **nur** beim Paketempfang; hört eine externe Konsole auf zu senden (abgezogen/abgestürzt), spinnt der RX-Loop nur in `except socket.timeout: continue` und mischt nie wieder. Der zuletzt empfangene Wert bleibt in `input_layer[out_univ]` und der 44-Hz-Renderer mischt ihn **jeden Frame weiter** (HTP als unverrückbarer Boden, REPLACE hart überschreibend) → der Kanal hängt permanent, bis App-Neustart oder Rückkehr der Quelle. **Sicherheitsrelevant:** externer Input wird **nicht** vom Submaster/Blackout skaliert (Kommentar `:1628-1629`) → ein normaler Blackout kann den hängenden Kanal nicht herunterziehen. `clear_input_merge` **existiert** und dokumentiert genau diesen Zweck („damit ein weggefallener externer Sender keine eingefrorenen Werte hinterlässt") — wird aber **nirgends** im Produktivcode aufgerufen (grep: nur in Tests). `input_layer` trägt keinen Zeitstempel. Verletzt E1.31-2018 Network-Data-Loss (~2,5 s). | Empfangs-Zeitstempel (`time.monotonic()`) pro `out_univ` in `apply_input_merge` mitschreiben; in `_render_frame` Schritt 4b-Input Universen älter als ~2,5 s überspringen **und** aus `input_layer` verwerfen (bzw. leichter Watchdog-Timer). |

### 🟠 P2

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **NET-06** | `artnet_input.py:153-159` · `sacn_input.py:171-176` | **RX-Thread-Tod lässt `_running=True` → `is_running()` lügt, kein Auto-Restart, Eingang dauerhaft stumm.** Ein transienter `OSError` aus `recvfrom` (Netzwerk-Blip: Adapter-Reset, VPN-Toggle, Kabel raus/rein) trifft `except OSError: break` (bzw. den äußeren `except Exception: break`) und beendet den RX-Thread — **ohne** `self._running=False` zu setzen. Danach gibt `is_running()` (nur `return self._running`, kein `is_alive`) dauerhaft **True** zurück → der UI-Neustart-Guard `if not rx.is_running(): rx.start()` (`output_config.py:402/425`) feuert nie und `start()` no-oppt am `if self._running: return`. Der externe Eingang ist nach dem kurzen Blip **permanent tot**, das Status-Label sagt weiter „Aktiv"; Erholung nur durch manuelles Ab-/Wieder-Anhaken. Beide Protokolle identisch. | In **beiden** `break`-Pfaden `self._running = False` setzen; `is_running()` zusätzlich an `self._thread.is_alive()` koppeln → der UI-Guard startet nach einem Blip korrekt neu (inkl. Multicast-Re-Join). Optional Reconnect-Watchdog. |

### 🟡 P3

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **NET-07** | `app_state.py:1642-1644` | **Merge in ein nicht als Output konfiguriertes `out_universe` wird still verworfen (Status lügt „Aktiv").** `scratch` wird nur aus `self.universes` gebaut; ein Merge-Ziel außerhalb → `scratch.get(univ) is None → continue`, die empfangenen Kanäle verpuffen, während die UI „Aktiv: U5 → U3" zeigt. Nur bei Fehlkonfiguration (Ziel-Spinbox auf ein nicht existierendes Universe). | Beim Konfigurieren prüfen, ob `out_univ` in `self.universes` existiert (Warnung/anlegen), oder Status-Label „out U3 nicht als Output konfiguriert → ohne Wirkung". |
| **NET-08** | `output_config.py:428-429` · `sacn_input.py:126` | **Umkonfigurieren des Eingangs-Universums lässt die alte Merge-Config + den alten Multicast-Join aktiv (alte Quelle mischt weiter).** Beim Umstellen von in U5 auf U7 wird `join_universe(7)` + `set_merge(7,…)` gerufen, aber der alte Eintrag nie entfernt (`remove_merge`/`clear_merges` haben projektweit **keinen** Aufrufer) → `_merges={5:…,7:…}`, beide Gruppen abonniert; sendet die alte Konsole weiter auf U5, mischt sie weiter in dasselbe out-Universe (HTP-Boden/LTP-Kampf). | Vor dem Setzen des neuen Merges den alten Eingang räumen (`remove_merge`/Leave-Multicast bzw. `clear_merges` + Re-Join nur des aktuellen `in_u`). |

---

## Zusammenfassung

Die RX-Parser und die Lock-Disziplin sind **solide** (robust gegen manipulierte Pakete, keine Threads-
Race). Die echten Defekte betreffen den **Quellen-Lebenszyklus**: eine verlorene externe Quelle friert
Kanäle dauerhaft ein (NET-05, **P1**, sicherheitsrelevant — Blackout greift dort nicht) und ein RX-Thread
stirbt nach einem Netzwerk-Blip **still** und meldet weiter „Aktiv" (NET-06, P2). Beides ist genau der
ungetestete „was passiert, wenn der Sender weg ist"-Bereich, den AUD-06 anvisiert. Empfehlung:
**NET-05 zuerst** (P1, Source-Timeout im Renderer/Watchdog), dann **NET-06** (kleiner, sicherer
`_running`-Reset in beiden Receivern), NET-07/08 danach.
