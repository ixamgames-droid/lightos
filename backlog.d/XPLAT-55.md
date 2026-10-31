ID: XPLAT-55
Prioritaet: P2
Status: review
Status-Notiz: Laufzeit-Teil erledigt (QA-102: Windows im Gate 201-250 s, Limit 300; Linux allein 146 s unter Last), stille Toleranz behoben — `verify_segmented.ps1` zaehlt ein Zeitlimit jetzt ROT, wenn die Datei `pytest.mark.timeout` auf das Segmentlimit oder darueber hebt (Zeitbomben-Waechter: 600); Waechter `tests/test_xplat55_zeitlimit_waechter_rot.py`
