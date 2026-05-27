from src.core.database.fixture_db import engine
from src.core.database.models import FixtureProfile
from sqlalchemy.orm import Session
from sqlalchemy import select

with Session(engine()) as s:
    fx = s.execute(select(FixtureProfile).where(FixtureProfile.short_name == "ZQ01424")).scalar_one()
    for m in fx.modes:
        print("Modus:", m.name)
        for ch in m.channels:
            ranges_info = ", ".join(
                r.name + "(" + str(r.range_from) + "-" + str(r.range_to) + ")"
                for r in ch.ranges
            )
            print("  CH" + str(ch.channel_number) + ": " + ch.name +
                  " [" + (ranges_info if ranges_info else "keine Ranges") + "]")
