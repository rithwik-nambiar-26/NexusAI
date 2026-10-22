"""Parsing the time expression in a reminder request.

A reminder is only useful if NexusAI knows *when* it is due, and it must
know that unambiguously. This module turns a phrase such as "7 AM",
"tomorrow at 7", "2026-10-25 09:30" or "in 20 minutes" into a single
instant, in UTC, together with the timezone the user expressed it in.

The module never guesses. When a phrase is missing, ambiguous or already
past, it raises :class:`ReminderTimeError` with a reason and, where two
readings are possible, both of them. The caller reports that to the user
rather than scheduling something the user did not ask for.

The timezone is an IANA name such as "Europe/London". A phrase that
carries no timezone is read in the user's local zone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo

try:  # pragma: no cover - the stdlib module is present on every supported version
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

    class ZoneInfoNotFoundError(Exception):  # type: ignore[no-redef]
        """Raised when a timezone name is not known."""


#: The statuses a reminder can be in.
REMINDER_STATUSES = ("pending", "fired", "cancelled", "missed")


class ReminderTimeError(ValueError):
    """A reminder time that cannot be resolved unambiguously.

    Attributes:
        code: A short machine-readable reason.
        details: Extra context, such as the two readings of an ambiguous
            time.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        super().__init__(message)


@dataclass
class ParsedTime:
    """A resolved reminder time.

    Attributes:
        due_at: The instant the reminder is due, in UTC.
        timezone: The IANA name of the zone the time was expressed in.
        local_due_at: The same instant, expressed in that zone.
        expression: The phrase that was understood.
        notes: Anything worth telling the user about the resolution.
    """

    due_at: datetime
    timezone: str
    local_due_at: datetime
    expression: str
    notes: list[str] = field(default_factory=list)


#: "in 20 minutes", "in 2 hours", "in 1 day".
_RELATIVE_RE = re.compile(
    r"\bin\s+(?P<amount>\d{1,3})\s*"
    r"(?P<unit>minutes?|mins?|hours?|hrs?|days?)\b",
    re.IGNORECASE,
)

#: "2026-10-25", "2026-10-25 09:30", "2026-10-25T09:30:00Z".
_ISO_DATETIME_RE = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:[T ](?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?)?"
    r"\s*(?P<offset>Z|[+-]\d{2}:?\d{2})?",
    re.IGNORECASE,
)

#: "7", "7:30", "07:30", "7 am", "7:30 p.m.".
_CLOCK_RE = re.compile(
    r"(?<![\d:])"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"
    r"\s*(?P<meridiem>a\.?m\.?|p\.?m\.?)?"
    r"(?![\d:])",
    re.IGNORECASE,
)

#: "today", "tomorrow", "tonight".
_DAY_WORD_RE = re.compile(r"\b(today|tomorrow|tonight)\b", re.IGNORECASE)

#: A clock time written with a leading zero is read as a 24-hour time.
_LEADING_ZERO_RE = re.compile(r"(?<!\d)0\d{1,2}(?::\d{2})?")

#: Units in a relative expression, mapped to the delta they represent.
_RELATIVE_UNITS = {
    "minute": "minutes",
    "min": "minutes",
    "minutes": "minutes",
    "hour": "hours",
    "hr": "hours",
    "hours": "hours",
    "day": "days",
    "days": "days",
}

#: The hour that "tonight" means.
_TONIGHT_HOUR = 20


def local_timezone_name() -> str:
    """Return the IANA name of the machine's local timezone.

    ``tzlocal`` is asked first, because it knows how to translate the
    Windows zone names ("India Standard Time") into IANA names
    ("Asia/Calcutta"). When it is unavailable the Windows registry is
    consulted directly, and where that fails too, UTC is used. The caller
    may still supply a zone explicitly.
    """
    name = _tzlocal_timezone_name() or _windows_timezone_name()
    if name and _is_known_zone(name):
        return name
    return "UTC"


def _tzlocal_timezone_name() -> str | None:
    """Return the local IANA zone name reported by ``tzlocal``."""
    try:  # pragma: no cover - depends on the installation
        import tzlocal

        return str(tzlocal.get_localzone_name())
    except Exception:  # pragma: no cover - not installed, or unresolvable
        return None


def _windows_timezone_name() -> str | None:
    """Read the timezone name from the Windows registry."""
    try:  # pragma: no cover - Windows only
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "TimeZoneKeyName")
            return str(value)
    except Exception:  # pragma: no cover - not Windows, or no permission
        return None


def _is_known_zone(name: str) -> bool:
    """Return True when *name* is a timezone this installation knows."""
    if ZoneInfo is None:  # pragma: no cover
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False
    return True


def resolve_timezone(name: str | None = None) -> tuple[str, tzinfo]:
    """Resolve a timezone name to a usable zone.

    Args:
        name: An IANA timezone name. When None, the machine's local zone
            is used.

    Returns:
        A tuple of the zone name and the tzinfo object.

    Raises:
        ReminderTimeError: When the name is not a known timezone.
    """
    if name is None:
        resolved = local_timezone_name()
        if resolved == "UTC":
            return "UTC", UTC
        try:
            return resolved, ZoneInfo(resolved)  # type: ignore[misc]
        except Exception:  # pragma: no cover - defensive
            return "UTC", UTC

    cleaned = name.strip()
    if not cleaned:
        return local_timezone_name(), _zone(local_timezone_name())
    if not _is_known_zone(cleaned):
        raise ReminderTimeError(
            f"'{cleaned}' is not a timezone this system knows. "
            "Use an IANA name such as 'Europe/London' or 'UTC'.",
            code="unknown_timezone",
            details={"timezone": cleaned},
        )
    return cleaned, _zone(cleaned)


def _zone(name: str) -> tzinfo:
    """Return the tzinfo for a known zone name."""
    if ZoneInfo is None:  # pragma: no cover
        return UTC
    return ZoneInfo(name)  # type: ignore[misc]


def parse_due_at(
    text: str,
    *,
    now: datetime | None = None,
    timezone: str | None = None,
) -> ParsedTime:
    """Resolve the time a reminder is due.

    Args:
        text: The phrase to read, for example "tomorrow at 7 AM".
        now: The current instant. Defaults to the current UTC time.
        timezone: The IANA zone to read the phrase in. Defaults to the
            machine's local zone.

    Returns:
        The resolved :class:`ParsedTime`.

    Raises:
        ReminderTimeError: When no time, an ambiguous time, an
            unrecognised date, or a time that has already passed.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    zone_name, zone = resolve_timezone(timezone)
    local_now = current.astimezone(zone)

    cleaned = (text or "").strip()
    if not cleaned:
        raise ReminderTimeError(
            "No time was given for the reminder.",
            code="missing_time",
        )

    # 1. A relative expression is the most explicit, so it wins.
    relative = _RELATIVE_RE.search(cleaned)
    if relative:
        amount = int(relative.group("amount"))
        unit = _RELATIVE_UNITS[relative.group("unit").lower()]
        due_local = local_now + timedelta(**{unit: amount})
        expression = relative.group(0)
        notes = [f"Read as {amount} {unit} from now."]
        return _finalise(due_local, zone_name, zone, expression, notes)

    # 2. An explicit date, with or without a time of day.
    working = cleaned
    iso = _ISO_DATETIME_RE.search(working)
    explicit_date = False
    date_part: tuple[int, int, int] | None = None
    fixed_time: tuple[int, int, int] | None = None
    fixed_offset: str | None = None

    if iso:
        working = working[: iso.start()] + " " * (iso.end() - iso.start()) + working[iso.end() :]
        date_part = (
            int(iso.group("year")),
            int(iso.group("month")),
            int(iso.group("day")),
        )
        explicit_date = True
        if iso.group("hour") is not None:
            fixed_time = (
                int(iso.group("hour")),
                int(iso.group("minute")),
                int(iso.group("second") or 0),
            )
        fixed_offset = iso.group("offset")

    if date_part is not None:
        year, month, day = date_part
        try:
            datetime(year, month, day)
        except ValueError as exc:
            raise ReminderTimeError(
                f"'{year}-{month:02d}-{day:02d}' is not a real date.",
                code="invalid_date",
                details={"date": f"{year}-{month:02d}-{day:02d}"},
            ) from exc
        expression = iso.group(0)  # type: ignore[union-attr]

        if fixed_time is not None:
            hour, minute, second = fixed_time
            if hour > 23 or minute > 59 or second > 59:
                raise ReminderTimeError(
                    f"'{hour:02d}:{minute:02d}:{second:02d}' is not a valid time.",
                    code="invalid_time",
                )
            due_local = datetime(
                year, month, day, hour, minute, second, tzinfo=zone
            )
            if fixed_offset:
                due_utc = datetime(
                    year, month, day, hour, minute, second, tzinfo=UTC
                ) - _offset_delta(fixed_offset)
                zone_name = "UTC"
                zone = UTC
                due_local = due_utc.astimezone(zone)
            notes = [f"Read as {due_local.strftime('%Y-%m-%d %H:%M')} ({zone_name})."]
            return _finalise_due(due_local, zone_name, zone, expression, notes)

        if fixed_time is None:
            # A date with no time of day. A reminder needs a time, so this
            # is reported rather than defaulted to midnight.
            raise ReminderTimeError(
                f"'{expression}' names a date but no time. "
                "Add a time, for example '2026-10-25 09:30'.",
                code="missing_time",
                details={"date": expression},
            )

    # 3. A day word, with or without a time of day.
    day_word = _DAY_WORD_RE.search(working)
    day_shift: int | None = None
    if day_word:
        word = day_word.group(1).lower()
        working = (
            working[: day_word.start()]
            + " " * (day_word.end() - day_word.start())
            + working[day_word.end() :]
        )
        day_shift = 1 if word == "tomorrow" else 0
        explicit_date = True

    # 4. A clock time.
    clock = _CLOCK_RE.search(working)
    if not clock:
        raise ReminderTimeError(
            f"No time was found in '{cleaned}'. "
            "Use a time such as '7 AM', 'tomorrow at 7', or '2026-10-25 09:30'.",
            code="missing_time",
            details={"text": cleaned},
        )

    hour = int(clock.group("hour"))
    minute = int(clock.group("minute") or 0)
    meridiem = clock.group("meridiem")
    expression = clock.group(0).strip()
    leading_zero = bool(_LEADING_ZERO_RE.fullmatch(clock.group(0).strip()))

    if meridiem:
        meridiem = meridiem.replace(".", "").lower()
        if hour < 1 or hour > 12:
            raise ReminderTimeError(
                f"'{expression}' is not a valid time.",
                code="invalid_time",
            )
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    elif 1 <= hour <= 12 and not leading_zero:
        if day_word and day_word.group(1).lower() == "tonight":
            # "tonight at 8" is the evening, so the clock reading is a
            # 12-hour reading from the afternoon onwards.
            hour = 12 if hour == 12 else hour + 12
        else:
            # "7" or "7:30" with no am/pm is genuinely ambiguous.
            am = f"{hour:02d}:{minute:02d}"
            pm_hour = 12 if hour == 12 else hour + 12
            pm = f"{pm_hour:02d}:{minute:02d}"
            raise ReminderTimeError(
                f"'{expression}' is ambiguous: it could mean {am} or {pm}. "
                "Say which one, for example '7 AM' or '7 PM'.",
                code="ambiguous_time",
                details={"interpretations": [am, pm]},
            )
    elif hour > 23:
        raise ReminderTimeError(
            f"'{expression}' is not a valid time.",
            code="invalid_time",
        )

    # Resolve the date.
    if day_shift is not None:
        target_date = local_now.date() + timedelta(days=day_shift)
    else:
        target_date = local_now.date()

    due_local = datetime(
        target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=zone
    )

    # A time of day with no date means the next occurrence of that time.
    if not explicit_date and due_local <= local_now:
        due_local += timedelta(days=1)
        notes = ["No date was given, so the next occurrence of that time was used."]
    else:
        notes = []

    if due_local <= local_now and explicit_date and day_shift is None:
        raise ReminderTimeError(
            f"'{expression}' is in the past.",
            code="past_time",
            details={"text": cleaned},
        )

    if day_word and day_word.group(1).lower() == "tonight" and hour < 12:
        due_local = due_local.replace(hour=_TONIGHT_HOUR)
        notes.append("'Tonight' was read as 20:00.")

    return _finalise(due_local, zone_name, zone, expression, notes)


def _offset_delta(offset: str) -> timedelta:
    """Return the UTC offset for a textual offset such as '+05:30'."""
    if offset.upper() == "Z":
        return timedelta(0)
    sign = -1 if offset[0] == "-" else 1
    digits = offset[1:].replace(":", "")
    hours = int(digits[:2])
    minutes = int(digits[2:4]) if len(digits) > 2 else 0
    return sign * timedelta(hours=hours, minutes=minutes)


def _finalise(
    due_local: datetime,
    zone_name: str,
    zone: tzinfo,
    expression: str,
    notes: list[str],
) -> ParsedTime:
    """Turn a local due time into the result object."""
    due_utc = due_local.astimezone(UTC)
    return ParsedTime(
        due_at=due_utc,
        timezone=zone_name,
        local_due_at=due_local,
        expression=expression,
        notes=list(notes),
    )


def _finalise_due(
    due_local: datetime,
    zone_name: str,
    zone: tzinfo,
    expression: str,
    notes: list[str],
) -> ParsedTime:
    """Turn a fixed local due time into the result object."""
    return _finalise(due_local, zone_name, zone, expression, notes)
