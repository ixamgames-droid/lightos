"""Show-Fixtures muessen trotz abweichender SQLite-Auto-IDs portabel bleiben."""


def test_saved_fixture_identity_remaps_stale_numeric_profile_id():
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine
    from src.core.database.models import FixtureProfile
    from src.core.show.show_file import _patched_fixture_from_data

    with Session(engine()) as session:
        expected = session.execute(
            select(FixtureProfile)
            .where(FixtureProfile.short_name == "ZQ01424")
        ).scalars().first()
        assert expected is not None

    stale_id = 1 if expected.id != 1 else 2
    fixture = _patched_fixture_from_data({
        "fid": 1,
        "fixture_profile_id": stale_id,
        "manufacturer_name": "Generic",
        "fixture_name": "Stage Light ZQ01424",
        "mode_name": "8-Kanal RGBW",
        "channel_count": 8,
    }, 1)

    assert fixture.fixture_profile_id == expected.id
