"""Data models and state derivation for Napper."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def parse_datetime(value: Any) -> datetime | None:
    """Parse an API timestamp without failing the whole coordinator update."""
    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


@dataclass(frozen=True, slots=True)
class NapperTokens:
    """Authentication tokens returned by Napper."""

    account_id: str
    id_token: str
    refresh_token: str
    id_token_expires_at: int | None = None
    refresh_token_expires_at: int | None = None


@dataclass(frozen=True, slots=True)
class NapperBaby:
    """A baby attached to a Napper account."""

    id: str
    name: str
    is_owner: bool

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NapperBaby:
        """Create a baby from an API object."""
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or "Baby"),
            is_owner=bool(data.get("isOwner", False)),
        )


@dataclass(frozen=True, slots=True)
class NapperPause:
    """A pause inside an activity log."""

    start: datetime | None
    end: datetime | None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NapperPause:
        """Create a pause from an API object."""
        return cls(
            start=parse_datetime(data.get("start")),
            end=parse_datetime(data.get("end")),
        )


@dataclass(frozen=True, slots=True)
class NapperLog:
    """An activity log returned by Napper."""

    id: str | None
    category: str
    is_open: bool
    start: datetime | None
    end: datetime | None
    pauses: tuple[NapperPause, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NapperLog:
        """Create a log from an API object."""
        pauses = data.get("pauses")
        return cls(
            id=str(data["id"]) if data.get("id") is not None else None,
            category=str(data.get("category") or "UNKNOWN").upper(),
            is_open=bool(data.get("isOpen", False)),
            start=parse_datetime(data.get("start")),
            end=parse_datetime(data.get("end")),
            pauses=tuple(
                NapperPause.from_dict(item)
                for item in pauses
                if isinstance(item, Mapping)
            )
            if isinstance(pauses, list)
            else (),
        )

    @property
    def is_paused(self) -> bool:
        """Return whether the log has an unfinished pause."""
        return any(pause.end is None for pause in self.pauses)


@dataclass(frozen=True, slots=True)
class NapperBabyState:
    """Home Assistant-facing state for one baby."""

    baby: NapperBaby
    sleeping: bool
    napping: bool
    nap_paused: bool
    nursing: bool
    night_waking: bool
    sleep_state: str
    sleep_started_at: datetime | None
    last_activity_at: datetime | None


def derive_baby_state(baby: NapperBaby, logs: tuple[NapperLog, ...]) -> NapperBabyState:
    """Derive independent activity flags from Napper logs."""
    open_naps = tuple(log for log in logs if log.category == "NAP" and log.is_open)
    active_naps = tuple(log for log in open_naps if not log.is_paused)
    paused_naps = tuple(log for log in open_naps if log.is_paused)

    napping = bool(active_naps)
    nap_paused = bool(paused_naps)
    nursing = any(log.category == "NURSING" and log.is_open for log in logs)
    night_waking = any(log.category == "NIGHT_WAKING" and log.is_open for log in logs)

    night_markers = tuple(
        log
        for log in logs
        if log.category in {"BED_TIME", "WOKE_UP"} and log.start is not None
    )
    latest_night_marker = max(
        night_markers,
        key=lambda log: log.start or datetime.min.replace(tzinfo=UTC),
        default=None,
    )
    night_sleeping = bool(
        latest_night_marker
        and latest_night_marker.category == "BED_TIME"
        and not night_waking
    )
    sleeping = napping or night_sleeping

    if napping:
        sleep_state = "napping"
    elif nap_paused:
        sleep_state = "nap_paused"
    elif night_waking:
        sleep_state = "night_waking"
    elif night_sleeping:
        sleep_state = "night_sleeping"
    else:
        sleep_state = "awake"

    sleep_candidates = [
        log.start for log in (*active_naps, *paused_naps) if log.start is not None
    ]
    if night_sleeping and latest_night_marker and latest_night_marker.start:
        sleep_candidates.append(latest_night_marker.start)

    activity_candidates: list[datetime] = []
    for log in logs:
        if log.start:
            activity_candidates.append(log.start)
        if log.end:
            activity_candidates.append(log.end)
        for pause in log.pauses:
            if pause.start:
                activity_candidates.append(pause.start)
            if pause.end:
                activity_candidates.append(pause.end)

    return NapperBabyState(
        baby=baby,
        sleeping=sleeping,
        napping=napping,
        nap_paused=nap_paused,
        nursing=nursing,
        night_waking=night_waking,
        sleep_state=sleep_state,
        sleep_started_at=max(sleep_candidates, default=None),
        last_activity_at=max(activity_candidates, default=None),
    )
