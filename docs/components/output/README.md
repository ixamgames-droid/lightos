# Output-/DMX-Komponenten (`src/core/dmx`)

Referenz-Docs je Modul unter `src/core/dmx/` — Ausgabe (Enttec / Art-Net / sACN) und
Netzwerk-Eingang. Jede Doc folgt demselben Schema: **Zweck · Konfiguration/Schalter ·
Threading-/Prozessmodell · Fehler-/Watchdog-Verhalten · gekoppelte Module · Tests ·
Quelle (`file:line`)**.

## Datenfluss (Kurzüberblick)

Renderer/Engine schreiben in [`Universe`](universe.md)-Puffer → der
[`OutputManager`](output_manager.md) liest jedes Frame bei 44 Hz und verteilt es an die
je Universe registrierten Ausgabe-Adapter. Netzwerk-Eingänge schreiben über die
AppState-Eingangsschicht zurück in Universen.

## Ausgabe

| Modul | Rolle |
|---|---|
| [`output_manager`](output_manager.md) | Zentraler 44-Hz-Koordinator; Grand Master / Blackout / Submaster; Adapter-Registry je Universe. |
| [`universe`](universe.md) | Thread-sicherer 512-Kanal-DMX-Puffer + Schreib-Protokoll. |
| [`enttec_pro`](enttec_pro.md) | Enttec DMX USB Pro über pyserial (Fehler-Watchdog / Reconnect, OUT-02). |
| [`serial_process`](serial_process.md) | Prozess-isolierte serielle Ausgabe (Access-Violation-Isolation, STAB-08). |
| [`artnet`](artnet.md) | Art-Net-4-UDP-Sender. |
| [`sacn`](sacn.md) | sACN-/E1.31-Sender (UDP Multicast/Unicast, Stream-Termination OUT-06). |

## Eingang

| Modul | Rolle |
|---|---|
| [`artnet_input`](artnet_input.md) | Art-Net-Empfänger + Merge in Universen. |
| [`sacn_input`](sacn_input.md) | sACN-/E1.31-Empfänger (Multicast-Join) + Merge. |

## Verwandte Referenzen

- [`docs/DMX_PROTOCOL.md`](../../DMX_PROTOCOL.md) — Wire-Formate.
- [`docs/ARTNET.md`](../../ARTNET.md) — Art-Net-Details.
- [`docs/OUTPUT_MERGE_CONTRACT.md`](../../OUTPUT_MERGE_CONTRACT.md) — Merge-/Eingangs-Vertrag.
- [`docs/DMX_OUTPUT_AUDIT_2026_07_08.md`](../../DMX_OUTPUT_AUDIT_2026_07_08.md),
  [`docs/DMX_INPUT_AUDIT_2026_07_08.md`](../../DMX_INPUT_AUDIT_2026_07_08.md) — Audits.
