"""CQ6136: nur RGBW bestaetigt — Amber/UV/Strobe entfernen."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.core.database.fixture_db import engine
from src.core.database.models import FixtureProfile, FixtureMode, FixtureChannel

with Session(engine()) as s:
    fx = s.execute(select(FixtureProfile).where(FixtureProfile.name == "Stage Light CQ6136")).scalar_one()
    for m in list(fx.modes):
        s.delete(m)
    s.flush()

    def mode(name, chs):
        m = FixtureMode(fixture=fx, name=name, channel_count=len(chs))
        s.add(m); s.flush()
        for i,(n,a,d,h) in enumerate(chs,1):
            s.add(FixtureChannel(mode=m,channel_number=i,name=n,attribute=a,default_value=d,highlight_value=h))

    mode("4-Kanal RGBW", [
        ("Rot","color_r",0,255), ("Gruen","color_g",0,255),
        ("Blau","color_b",0,255), ("Weiss","color_w",0,255),
    ])
    mode("3-Kanal RGB", [
        ("Rot","color_r",0,255),("Gruen","color_g",0,255),("Blau","color_b",0,255),
    ])
    s.commit()
    print("CQ6136 aktualisiert: 4-Kanal RGBW + 3-Kanal RGB")
