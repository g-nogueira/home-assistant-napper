"""Tests for Napper state derivation."""

from datetime import UTC, datetime

from custom_components.napper.models import (
    NapperBaby,
    NapperLog,
    derive_baby_state,
)

BABY = NapperBaby(id="baby-1", name="Test Baby", is_owner=True)


def log(
    category: str,
    start: str,
    *,
    is_open: bool = False,
    end: str | None = None,
    pauses: list[dict[str, str | None]] | None = None,
) -> NapperLog:
    """Create a sanitized log fixture."""
    return NapperLog.from_dict(
        {
            "id": f"{category.lower()}-1",
            "category": category,
            "isOpen": is_open,
            "start": start,
            "end": end,
            "pauses": pauses or [],
        }
    )


def test_active_nap_and_nursing_can_overlap() -> None:
    logs = (
        log("NAP", "2026-09-15T13:00:00+00:00", is_open=True),
        log("NURSING", "2026-09-15T13:10:00+00:00", is_open=True),
    )

    state = derive_baby_state(BABY, logs)

    assert state.sleeping is True
    assert state.napping is True
    assert state.nursing is True
    assert state.sleep_state == "napping"
    assert state.sleep_started_at == datetime(2026, 9, 15, 13, tzinfo=UTC)


def test_paused_nap_is_open_but_not_sleeping() -> None:
    logs = (
        log(
            "NAP",
            "2026-09-15T13:00:00Z",
            is_open=True,
            pauses=[{"start": "2026-09-15T13:20:00Z", "end": None}],
        ),
    )

    state = derive_baby_state(BABY, logs)

    assert state.sleeping is False
    assert state.napping is False
    assert state.nap_paused is True
    assert state.sleep_state == "nap_paused"


def test_latest_night_marker_controls_night_sleep() -> None:
    bedtime = log("BED_TIME", "2026-09-14T19:00:00Z")
    woke_up = log("WOKE_UP", "2026-09-15T06:00:00Z")

    awake = derive_baby_state(BABY, (bedtime, woke_up))

    assert awake.sleeping is False
    assert awake.sleep_state == "awake"


def test_bedtime_without_later_wake_means_night_sleeping() -> None:
    logs = (
        log("WOKE_UP", "2026-09-14T06:00:00Z"),
        log("BED_TIME", "2026-09-14T19:00:00Z"),
    )

    state = derive_baby_state(BABY, logs)

    assert state.sleeping is True
    assert state.sleep_state == "night_sleeping"


def test_open_night_waking_interrupts_night_sleep() -> None:
    logs = (
        log("BED_TIME", "2026-09-14T19:00:00Z"),
        log("NIGHT_WAKING", "2026-09-15T01:00:00Z", is_open=True),
    )

    state = derive_baby_state(BABY, logs)

    assert state.sleeping is False
    assert state.night_waking is True
    assert state.sleep_state == "night_waking"


def test_last_activity_includes_pause_boundaries() -> None:
    logs = (
        log(
            "NAP",
            "2026-09-15T13:00:00Z",
            is_open=True,
            pauses=[
                {
                    "start": "2026-09-15T13:20:00Z",
                    "end": "2026-09-15T13:25:00Z",
                }
            ],
        ),
    )

    state = derive_baby_state(BABY, logs)

    assert state.last_activity_at == datetime(2026, 9, 15, 13, 25, tzinfo=UTC)
