ID: LAS-47
Prioritaet: P3
Status: todo
Titel: SH-LASER3W: Effekt-Ziele, Kanal-Zuordnungen und VC-Bindungen auf laser_twist nach LAS-28 nachziehen (Rest aus CDX-65)

CDX-65 migriert gespeicherte Programmer-, Paletten- und Cue-Werte alter SH-LASER3W-Shows (laser_twist#N -> laser_twist / laser_twist_y). Nicht umsetzbar per Umbenennen und deshalb offen: (1) Effekte (`target_attribute`) und `MappedChannelChange` mit Ziel `laser_twist` schrieben vor LAS-28 auf alle vier Flips, seitdem nur auf die beiden horizontalen; (2) VC-Bindungen an `laser_twist#N` werden nicht umgesetzt; (3) Shows, die zwischen #1211 (01.11.2026) und CDX-65 gespeichert wurden und nur `laser_twist#1` enthalten, werden falsch umgesetzt (kleines Zeitfenster). Klaeren, ob ein Effekt auf „alle Flips“ gewollt ist (Robin), dann gezielt nachziehen.
