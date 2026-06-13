from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import logging
import os

from dotenv import load_dotenv


load_dotenv(override=True)

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CALENDAR_CLIENT_ID = os.getenv("CALENDAR_CLIENT_ID")
CALENDAR_CLIENT_SECRET = os.getenv("CALENDAR_CLIENT_SECRET")
CALENDAR_TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "Europe/Amsterdam")
CALENDAR_AUTH_HOST = os.getenv("CALENDAR_AUTH_HOST", "localhost")
CALENDAR_AUTH_PORT = int(os.getenv("CALENDAR_AUTH_PORT", "8080"))
CALENDAR_AUTH_OPEN_BROWSER = (
    os.getenv("CALENDAR_AUTH_OPEN_BROWSER", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
CALENDAR_TOKEN_PATH = Path("toolbox/gcalendar_tokens.json")
CALENDAR_MAX_LISTED_EVENTS = 6


@dataclass(frozen=True)
class CalendarWindow:
    period: str
    label: str
    fetch_start: datetime
    analysis_start: datetime
    end: datetime


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    start: datetime
    end: datetime
    is_all_day: bool


def _get_timezone() -> ZoneInfo:
    return ZoneInfo(CALENDAR_TIMEZONE)


def _build_client_config() -> dict[str, object]:
    return {
        "installed": {
            "client_id": CALENDAR_CLIENT_ID,
            "client_secret": CALENDAR_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _calendar_configuration_error() -> str:
    return (
        "Google Calendar is not configured yet. Add CALENDAR_CLIENT_ID and "
        "CALENDAR_CLIENT_SECRET to your .env file, then authenticate once."
    )


def _build_authorization_prompt_message() -> str:
    return (
        "Open this URL in a browser on the machine on the other side of your SSH tunnel:\n"
        "{url}\n"
        f"If needed, forward local port {CALENDAR_AUTH_PORT} to the Pi with:\n"
        f"ssh -L {CALENDAR_AUTH_PORT}:localhost:{CALENDAR_AUTH_PORT} <pi-host>"
    )


def _save_credentials(creds: Credentials) -> None:
    CALENDAR_TOKEN_PATH.write_text(creds.to_json())


def _load_credentials() -> Credentials:
    creds = None

    if CALENDAR_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(CALENDAR_TOKEN_PATH),
            CALENDAR_SCOPES,
        )

    if creds and creds.valid and creds.has_scopes(CALENDAR_SCOPES):
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as error:
            logging.warning("Refreshing Google Calendar credentials failed: %s", error)
            creds = None
        else:
            if creds.valid and creds.has_scopes(CALENDAR_SCOPES):
                _save_credentials(creds)
                return creds

    if not CALENDAR_CLIENT_ID or not CALENDAR_CLIENT_SECRET:
        raise RuntimeError(_calendar_configuration_error())

    flow = InstalledAppFlow.from_client_config(_build_client_config(), CALENDAR_SCOPES)
    logging.info(
        "Starting Google Calendar OAuth on http://%s:%s with open_browser=%s",
        CALENDAR_AUTH_HOST,
        CALENDAR_AUTH_PORT,
        CALENDAR_AUTH_OPEN_BROWSER,
    )
    creds = flow.run_local_server(
        host=CALENDAR_AUTH_HOST,
        port=CALENDAR_AUTH_PORT,
        open_browser=CALENDAR_AUTH_OPEN_BROWSER,
        authorization_prompt_message=_build_authorization_prompt_message(),
    )
    _save_credentials(creds)
    return creds


def get_service():
    creds = _load_credentials()
    return build("calendar", "v3", credentials=creds)


def _normalize_period(period: str) -> str:
    normalized = (period or "today").strip().lower()
    aliases = {
        "today": "today",
        "day": "today",
        "todays": "today",
        "today_and_remainder_of_week": "today_and_remainder_of_week",
        "today and remainder of week": "today_and_remainder_of_week",
        "today and rest of week": "today_and_remainder_of_week",
        "both": "today_and_remainder_of_week",
        "remainder_of_week": "remainder_of_week",
        "rest_of_week": "remainder_of_week",
        "remainder week": "remainder_of_week",
        "rest week": "remainder_of_week",
        "this_week": "remainder_of_week",
        "week": "remainder_of_week",
    }
    resolved = aliases.get(normalized)
    if resolved is None:
        raise ValueError(
            "Calendar period must be today, remainder_of_week, or today_and_remainder_of_week."
        )
    return resolved


def _resolve_window(period: str) -> CalendarWindow:
    timezone = _get_timezone()
    now = datetime.now(timezone)
    normalized = _normalize_period(period)

    if normalized == "today_and_remainder_of_week":
        raise ValueError(
            "Combined calendar periods should be handled before resolving a single window."
        )

    if normalized == "today":
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        return CalendarWindow(
            period=normalized,
            label="today",
            fetch_start=start_of_day,
            analysis_start=now,
            end=end_of_day,
        )

    days_until_next_monday = 7 - now.weekday()
    start_of_next_monday = (now + timedelta(days=days_until_next_monday)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return CalendarWindow(
        period=normalized,
        label="the remainder of the week",
        fetch_start=now,
        analysis_start=now,
        end=start_of_next_monday,
    )


def _parse_event_datetime(raw_value: str, *, is_all_day: bool) -> datetime:
    timezone = _get_timezone()
    if is_all_day:
        return datetime.fromisoformat(raw_value).replace(tzinfo=timezone)

    normalized_value = raw_value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized_value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _normalize_event(raw_event: dict[str, object]) -> CalendarEvent:
    start_data = raw_event.get("start", {})
    end_data = raw_event.get("end", {})

    is_all_day = "date" in start_data
    start_key = "date" if is_all_day else "dateTime"
    end_key = "date" if is_all_day else "dateTime"

    start_value = start_data.get(start_key)
    end_value = end_data.get(end_key)

    if not start_value or not end_value:
        raise ValueError("Calendar event is missing a start or end time.")

    title = str(raw_event.get("summary") or "Untitled event")
    start = _parse_event_datetime(str(start_value), is_all_day=is_all_day)
    end = _parse_event_datetime(str(end_value), is_all_day=is_all_day)

    return CalendarEvent(
        title=title,
        start=start,
        end=end,
        is_all_day=is_all_day,
    )


def _fetch_calendar_events(window: CalendarWindow) -> list[CalendarEvent]:
    service = get_service()
    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=window.fetch_start.isoformat(),
            timeMax=window.end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            showDeleted=False,
        )
        .execute()
    )

    events: list[CalendarEvent] = []
    for raw_event in response.get("items", []):
        try:
            events.append(_normalize_event(raw_event))
        except ValueError as error:
            logging.warning("Skipping malformed Google Calendar event: %s", error)
    return events


def _format_clock(timestamp: datetime) -> str:
    hour = timestamp.hour
    minute = timestamp.minute

    if hour == 0 and minute == 0:
        return "midnight"
    if hour == 12 and minute == 0:
        return "noon"

    if hour < 12:
        daypart = "in the morning"
    elif hour < 17:
        daypart = "in the afternoon"
    elif hour < 21:
        daypart = "in the evening"
    else:
        daypart = "at night"

    spoken_hour = hour % 12 or 12
    if minute == 0:
        return f"{spoken_hour} {daypart}"

    return f"{spoken_hour}:{minute:02d} {daypart}"


def _format_weekday(timestamp: datetime) -> str:
    return timestamp.strftime("%A")


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural or f"{singular}s"


def _format_duration(minutes: int) -> str:
    if minutes <= 0:
        return "less than a minute"

    hours, remaining_minutes = divmod(minutes, 60)
    parts: list[str] = []

    if hours:
        parts.append(f"{hours} {_pluralize(hours, 'hour')}")
    if remaining_minutes:
        parts.append(f"{remaining_minutes} {_pluralize(remaining_minutes, 'minute')}")

    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} and {parts[1]}"


def _format_event_brief(event: CalendarEvent, *, include_day: bool, now: datetime) -> str:
    day_prefix = f"{_format_weekday(event.start)} " if include_day else ""

    if event.is_all_day:
        return f"{day_prefix}{event.title}, all day"

    if event.start <= now < event.end:
        return f"{day_prefix}{event.title}, happening now until {_format_clock(event.end)}"

    return (
        f"{day_prefix}{event.title}, from {_format_clock(event.start)} "
        f"to {_format_clock(event.end)}"
    )


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda interval: interval[0])
    merged = [sorted_intervals[0]]

    for start, end in sorted_intervals[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))

    return merged


def _timed_intervals_in_window(
    events: list[CalendarEvent],
    *,
    start_boundary: datetime,
    end_boundary: datetime,
) -> list[tuple[datetime, datetime]]:
    intervals: list[tuple[datetime, datetime]] = []

    for event in events:
        if event.is_all_day:
            continue

        interval_start = max(event.start, start_boundary)
        interval_end = min(event.end, end_boundary)
        if interval_end <= interval_start:
            continue
        intervals.append((interval_start, interval_end))

    return _merge_intervals(intervals)


def _total_busy_minutes(
    events: list[CalendarEvent],
    *,
    start_boundary: datetime,
    end_boundary: datetime,
) -> int:
    merged_intervals = _timed_intervals_in_window(
        events,
        start_boundary=start_boundary,
        end_boundary=end_boundary,
    )
    total_seconds = sum(
        int((end - start).total_seconds())
        for start, end in merged_intervals
    )
    return total_seconds // 60


def _largest_gap(
    events: list[CalendarEvent],
    *,
    start_boundary: datetime,
    end_boundary: datetime,
) -> tuple[int, datetime | None, datetime | None]:
    merged_intervals = _timed_intervals_in_window(
        events,
        start_boundary=start_boundary,
        end_boundary=end_boundary,
    )

    cursor = start_boundary
    largest_gap_minutes = 0
    largest_gap_start = None
    largest_gap_end = None

    for start, end in merged_intervals:
        if start > cursor:
            gap_minutes = int((start - cursor).total_seconds()) // 60
            if gap_minutes > largest_gap_minutes:
                largest_gap_minutes = gap_minutes
                largest_gap_start = cursor
                largest_gap_end = start
        cursor = max(cursor, end)

    if end_boundary > cursor:
        gap_minutes = int((end_boundary - cursor).total_seconds()) // 60
        if gap_minutes > largest_gap_minutes:
            largest_gap_minutes = gap_minutes
            largest_gap_start = cursor
            largest_gap_end = end_boundary

    return largest_gap_minutes, largest_gap_start, largest_gap_end


def _describe_busyness(event_count: int, busy_minutes: int, all_day_count: int) -> str:
    score = event_count + (busy_minutes / 120) + all_day_count

    if score <= 0:
        return "clear"
    if score <= 2.5:
        return "light"
    if score <= 5:
        return "moderate"
    if score <= 8:
        return "busy"
    return "packed"


def _build_calendar_events_response(period: str) -> str:
    try:
        window = _resolve_window(period)
        events = _fetch_calendar_events(window)
    except (RuntimeError, ValueError) as error:
        logging.error("Google Calendar event lookup failed: %s", error)
        return str(error)
    except Exception as error:
        logging.error("Google Calendar event lookup failed unexpectedly: %s", error)
        return "I couldn't fetch your Google Calendar events just now."

    if not events:
        if window.period == "today":
            return "Your calendar is clear today."
        return "The remainder of your week looks clear."

    now = datetime.now(_get_timezone())
    preview_events = events[:CALENDAR_MAX_LISTED_EVENTS]
    include_day = window.period == "remainder_of_week"
    event_lines = [
        _format_event_brief(event, include_day=include_day, now=now)
        for event in preview_events
    ]

    response = (
        f"You have {len(events)} calendar {_pluralize(len(events), 'event')} "
        f"{window.label}. "
        + ". ".join(event_lines)
    )

    remaining_count = len(events) - len(preview_events)
    if remaining_count > 0:
        response += f" And {remaining_count} more after that."

    return response


def get_calendar_events(period: str = "today") -> str:
    try:
        normalized_period = _normalize_period(period)
    except ValueError as error:
        logging.error("Google Calendar event lookup failed: %s", error)
        return str(error)

    if normalized_period == "today_and_remainder_of_week":
        today_response = _build_calendar_events_response("today")
        week_response = _build_calendar_events_response("remainder_of_week")
        return f"{today_response} {week_response}"

    return _build_calendar_events_response(normalized_period)


def _describe_next_event(event: CalendarEvent) -> str:
    if event.is_all_day:
        return f"{event.title} on {_format_weekday(event.start)}, all day"

    return (
        f"{event.title} on {_format_weekday(event.start)} "
        f"at {_format_clock(event.start)}"
    )


def _build_calendar_schedule_analysis_response(period: str) -> str:
    try:
        window = _resolve_window(period)
        events = _fetch_calendar_events(window)
    except (RuntimeError, ValueError) as error:
        logging.error("Google Calendar analysis failed: %s", error)
        return str(error)
    except Exception as error:
        logging.error("Google Calendar analysis failed unexpectedly: %s", error)
        return "I couldn't analyze your Google Calendar just now."

    now = datetime.now(_get_timezone())

    if window.period == "today":
        completed_events = [event for event in events if event.end <= now]
        remaining_events = [event for event in events if event.end > now]
        ongoing_events = [event for event in remaining_events if event.start <= now < event.end]
        upcoming_events = [event for event in remaining_events if event.start > now]

        if not events:
            return "Today is clear on your calendar."

        if not remaining_events:
            return (
                f"You already cleared today's calendar. "
                f"There were {len(completed_events)} {_pluralize(len(completed_events), 'event')} earlier, "
                f"and the rest of the day is open."
            )

        all_day_count = sum(1 for event in remaining_events if event.is_all_day)
        busy_minutes = _total_busy_minutes(
            remaining_events,
            start_boundary=now,
            end_boundary=window.end,
        )
        busyness = _describe_busyness(len(remaining_events), busy_minutes, all_day_count)
        response_parts = [
            (
                f"Today looks {busyness}. "
                f"You have {len(remaining_events)} remaining {_pluralize(len(remaining_events), 'event')}"
            )
        ]

        if busy_minutes > 0:
            response_parts.append(f"taking about {_format_duration(busy_minutes)} of scheduled time.")
        else:
            response_parts.append("with no timed blocks left.")

        if ongoing_events:
            current_event = ongoing_events[0]
            response_parts.append(
                f"Right now you're in {current_event.title} until {_format_clock(current_event.end)}."
            )
        elif upcoming_events:
            next_event = upcoming_events[0]
            response_parts.append(
                f"Next up is {next_event.title} at {_format_clock(next_event.start)}."
            )

        timed_remaining_events = [event for event in remaining_events if not event.is_all_day]
        if timed_remaining_events:
            latest_event = max(timed_remaining_events, key=lambda event: event.end)
            response_parts.append(
                f"Your last timed event finishes at {_format_clock(latest_event.end)}."
            )

        gap_minutes, gap_start, gap_end = _largest_gap(
            remaining_events,
            start_boundary=now,
            end_boundary=window.end,
        )
        if gap_minutes >= 60 and gap_start and gap_end:
            response_parts.append(
                f"Your largest free block is about {_format_duration(gap_minutes)}, "
                f"from {_format_clock(gap_start)} to {_format_clock(gap_end)}."
            )

        if all_day_count:
            response_parts.append(
                f"You also have {all_day_count} all-day {_pluralize(all_day_count, 'item')}."
            )

        return " ".join(response_parts)

    if not events:
        return "The remainder of your week is clear on your calendar."

    all_day_count = sum(1 for event in events if event.is_all_day)
    busy_minutes = _total_busy_minutes(
        events,
        start_boundary=window.analysis_start,
        end_boundary=window.end,
    )
    busyness = _describe_busyness(len(events), busy_minutes, all_day_count)

    events_by_day: dict[str, list[CalendarEvent]] = {}
    for event in events:
        day_name = _format_weekday(event.start)
        events_by_day.setdefault(day_name, []).append(event)

    ordered_day_summaries = []
    for day_name, day_events in events_by_day.items():
        ordered_day_summaries.append(
            f"{day_name} has {len(day_events)} {_pluralize(len(day_events), 'event')}"
        )

    next_event = min(events, key=lambda event: event.start)

    response_parts = [
        (
            f"The remainder of your week looks {busyness}. "
            f"You have {len(events)} {_pluralize(len(events), 'event')} across "
            f"{len(events_by_day)} {_pluralize(len(events_by_day), 'day')}."
        )
    ]

    if busy_minutes > 0:
        response_parts.append(f"That's about {_format_duration(busy_minutes)} of scheduled time.")

    response_parts.append(
        f"Your next event is {_describe_next_event(next_event)}."
    )

    max_event_count = max(len(day_events) for day_events in events_by_day.values())
    busiest_days = [
        day_name
        for day_name, day_events in events_by_day.items()
        if len(day_events) == max_event_count
    ]
    if len(busiest_days) == 1:
        response_parts.append(
            f"{busiest_days[0]} is the busiest day with {max_event_count} "
            f"{_pluralize(max_event_count, 'event')}."
        )
    else:
        joined_days = ", ".join(busiest_days)
        response_parts.append(
            f"The load is spread fairly evenly, with {joined_days} each carrying "
            f"{max_event_count} {_pluralize(max_event_count, 'event')}."
        )

    response_parts.append(". ".join(ordered_day_summaries[:4]) + ".")

    if all_day_count:
        response_parts.append(
            f"You also have {all_day_count} all-day {_pluralize(all_day_count, 'item')}."
        )

    return " ".join(response_parts)


def get_calendar_schedule_analysis(period: str = "today") -> str:
    try:
        normalized_period = _normalize_period(period)
    except ValueError as error:
        logging.error("Google Calendar analysis failed: %s", error)
        return str(error)

    if normalized_period == "today_and_remainder_of_week":
        today_response = _build_calendar_schedule_analysis_response("today")
        week_response = _build_calendar_schedule_analysis_response("remainder_of_week")
        return f"{today_response} {week_response}"

    return _build_calendar_schedule_analysis_response(normalized_period)
