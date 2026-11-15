ID: CDX-73
Prioritaet: P2
Status: review
Titel: Codex-Ernte: MVR-Import/-Export (freie Adresse ueber Universum 32 hinaus, Shutter-Bereichsart im GDTF-Export, Fein-Byte-Vorgabe beim GDTF-Import)

**Herkunft:** Kommentare des automatischen Reviewers Codex zu PR #1292 (VIZ-56), im Neuheiten-Audit von Sitzung A am 15.11.2026 bestaetigt. Tests: `tests/test_cdx73_mvr_codex.py`.

**Befund 1 (mittel):** `_Belegung.frei` in `src/core/mvr/importieren.py` begann die Suche bei dem Universum aus der Datei, nach oben unbegrenzt. Ein Geraet auf Universum 100 mit der Wahl „freie Adresse“ bekam bei vollem Patch Universum 33 (gibt es in LightOS nicht) und wurde als anlegbar gefuehrt. **Behebung:** Der Start wird auf 1..32 begrenzt; bei vollem Patch wird das Geraet uebersprungen.

**Befund 2 (niedrig):** Der GDTF-Export schrieb die Art eines Wertebereichs (kind) nicht mit; alle ChannelFunctions eines Kanals tragen dasselbe Attribut, beim Wiedereinlesen wurden zu/Strobe/offen eines Shutters alle zu „offen“. **Behebung:** `gdtf_schreiben` legt die Art im beschreibenden Feld `OriginalAttribute` als `LightOS_kind:<art>` ab, `lesen`/`gdtf_profil` lesen sie zurueck (auch eine leere Art). Fremde GDTF ohne diese Marke werden wie bisher ueber das Attribut eingeordnet.

**Befund 3 (niedrig):** Der GDTF-Import nahm vom Standardwert mehrbytiger Kanaele nur das grobe Byte; der Fein-Kanal bekam immer 0 (Pan 128/127 kam als 128/0 zurueck). **Behebung:** `lesen` behaelt den Rohwert samt Byteanzahl, `gdtf_profil.modus_payload` verteilt ihn auf grob/fein/ultra; weicht die Byteanzahl von der Offsetzahl ab, wird links ausgerichtet.
