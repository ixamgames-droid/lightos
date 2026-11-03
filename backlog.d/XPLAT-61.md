ID: XPLAT-61
Prioritaet: P3
Status: review
Status-Notiz: Diagnose zeigt Rechner- und Python-Architektur getrennt (Prozess aus sysconfig.get_platform(), Rechner aus IsWow64Process2), z. B. 'Windows ARM64, Python x64 (Emulation)'; 'nativ' nur bei gleicher Architektur; Test tests/test_xplat61_diagnose_architektur.py; Gegenprobe am echten ARM-Rechner offen (B)
