# LightOS — Nächste Schritte / Capabilities-Roadmap

> Stand: 2026-05-30. Priorisierte Liste zum gemeinsamen Abarbeiten.
> Legende: 🟢 klein/schnell · 🟡 mittel · 🔴 größerer Umbau

## A. Live-Bedienung & APC mini
- 🟢 **Pad-Stil pro Button wählbar** (Spiegel / Wechselfarbe / Welle / Puls) — als Eigenschaft am VC-Button + im Effekt-Assistenten.
- 🟢 **„Display-only"-Sperre** fürs Touchpanel (Anzeige- vs. Steuermodus, ein Toggle).
- 🟡 **Page-/Bank-Umschaltung** auf der APC (mehr als 48 Pads nutzen — die 8 Page-Buttons sind schon vom Mapper belegt).
- 🟡 **MIDI-Learn direkt im Live-Betrieb** (Pad/Fader antippen → Funktion zuweisen, ohne Editor).

## B. Effekte
- 🔴 **Freies Effekt-Layering** (zwei Effekte echt übereinander, z. B. Bewegung auf Intensität + Farbe getrennt) — via LayeredEffect/Effekt-Layer.
- 🟡 **Per-Effekt-Intensität & -Speed** (eigener Master pro laufendem Effekt, nicht nur globaler Grand Master).
- 🟡 **Live-Vorschau im Effekt-Assistenten** (Effekt schon beim Einstellen sehen).
- 🟢 **Eigene Effekte als Vorlage speichern** (User-Effekte in einer Bibliothek wiederverwenden).
- 🟢 **Mehr Effekt-Typen** im Assistenten (Comet/Schweif, Chase mit Tail, Random-Strobe, VU-Meter-artig).

## C. Show- & Funktions-Verwaltung
- 🟡 **Executor-/Cue-Bindung persistieren** (MITTEL-Audit-Befund: Executor→Stack-Zuordnung wird nicht in der Show gespeichert → Fader 1-8 bleiben nach Reload leer).
- 🟢 **Snapshots pro Show** statt global (aktuell `snapshots.json` global → fid-Referenzen passen nach Show-Wechsel evtl. nicht).
- 🟢 **Chaser-Editor: Notiz-Spalte zurückschreiben** (MITTEL-Befund, Eingabe geht verloren).
- 🟡 **Funktions-Editor: kein Neuaufbau bei Refresh** (MITTEL-Befund: Eingabe-/Fokusverlust).

## D. Stabilität (offene Audit-Befunde, siehe PROJECT_AUDIT.md)
- 🔴 **sACN (C5)** spec-konform neu (E1.31-Paketaufbau defekt) — nur falls sACN-Ausgabe gebraucht wird. Braucht Hardware-/Wireshark-Test.
- 🟡 **Thread-Disziplin (C8)** — `app_state._emit` ruft UI-Callbacks teils direkt cross-thread (MIDI→ProgrammerView) → in den UI-Thread marshallen.
- 🟢 **ArtNet-Broadcast-Default** `2.255.255.255` scheitert in 192.168-Netzen → konfigurierbar/Auto-IP.
- 🟢 **Output-Konfiguration persistieren + beim Start anwenden** (`data/universes.json` wird nicht automatisch geladen).

## E. Visualizer / Bühne
- 🟡 **Bühnen-Layout der echten Lampen** im Visualizer (Positionen entsprechend der realen Anordnung).
- 🟢 **2D-Top-Down-Ansicht** als schnelle Kontrolle neben der VC.

## F. Kleinere Politur
- 🟢 BPM-Beat-Indikator (oben rechts) größer/deutlicher.
- 🟢 Bessere Default-Farben/Beschriftungen im Panel (laufend).
- 🟢 Status-Zeile „aktiver Effekt: …" im VC.

---
**Empfohlener nächster Block:** A (Pad-Stil + Display-Lock, schnell & sichtbar) ODER
C (Executor-Persistenz → Fader 1-8 funktionieren dauerhaft). B-Layering ist der größte „Wow"-Schritt, aber aufwändiger.
