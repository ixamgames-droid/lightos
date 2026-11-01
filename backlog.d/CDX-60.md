ID: CDX-60
Prioritaet: P2
Status: review
Titel: Codex-Befunde zu #1195 (MIDI NRPN)

Codex-Review zu PR #1195 (MIDI-9/11/12/13), alle drei Befunde per Test belegt und behoben. **P1:** Die erste 14-Bit-NRPN-Folge eines Parameters meldet vorlaeufig beim MSB und praezisiert beim LSB; an einer Tasten-Aktion loeste das zweimal aus (GO doppelt, Toggle an und gleich wieder aus). Die Praezisierung traegt jetzt `nrpn_praezisiert`, der Mapper ueberspringt sie bei Tasten, ein Fader nimmt sie weiter. **P2:** „Geraet sendet LSB" galt je Port und Kanal; ein reiner 7-Bit-Parameter verstummte, sobald ein anderer Parameter auf demselben Kanal einen LSB geschickt hatte. Jetzt je Parameter. **P3:** Der MIDI-Monitor drosselte NRPN und rohe CCs gemeinsam; da die Empfangsschleife den NRPN direkt nach seinem CC zustellt, kam er nie an. NRPN hat jetzt eine eigene Drossel. Gilt fuer python-rtmidi und WinMM (gemeinsame Empfangsschleife). Test: `tests/test_cdx60_midi_nrpn.py`.
