from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread

import logging
import os
import random

from helpers.audio_output import stop_active_aplay_playback
from piper_tts import read_out_response_from_file
from toolbox.music import stop_music


TIMER_COMPLETE_RESPONSES_DIR = Path(
    os.getenv("TIMER_COMPLETE_RESPONSES_DIR", "herbie_responses/timer_complete")
)


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    parts: list[str] = []

    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if remaining_seconds or not parts:
        parts.append(
            f"{remaining_seconds} second{'s' if remaining_seconds != 1 else ''}"
        )

    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{parts[0]}, {parts[1]}, and {parts[2]}"


class TimerManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._stop_event = Event()
        self._timer_thread: Thread | None = None
        self._is_running = False
        self._duration_seconds: int | None = None
        self._ends_at: datetime | None = None
        self._alert_pending = False

    def status(self) -> dict[str, bool | int | str | None]:
        with self._lock:
            return {
                "is_running": self._is_running,
                "duration_seconds": self._duration_seconds,
                "ends_at": self._ends_at.isoformat() if self._ends_at else None,
                "alert_pending": self._alert_pending,
            }

    def start_timer(self, duration_seconds: int) -> bool:
        duration_seconds = int(duration_seconds)
        if duration_seconds <= 0:
            logging.warning("Timer duration must be positive.")
            return False

        self.stop_timer()

        stop_event = Event()
        ends_at = datetime.now() + timedelta(seconds=duration_seconds)
        timer_thread = Thread(
            target=self._run_timer,
            args=(duration_seconds, stop_event),
            daemon=True,
        )

        with self._lock:
            self._stop_event = stop_event
            self._timer_thread = timer_thread
            self._is_running = True
            self._duration_seconds = duration_seconds
            self._ends_at = ends_at
            self._alert_pending = False

        logging.info(f"Starting timer for {duration_seconds} seconds.")
        timer_thread.start()
        return True

    def stop_timer(self) -> bool:
        with self._lock:
            stop_event = self._stop_event
            was_running = self._is_running
            self._is_running = False
            self._duration_seconds = None
            self._ends_at = None
            self._alert_pending = False
            self._timer_thread = None

        stop_event.set()

        if was_running:
            logging.info("Stopping active timer.")
        else:
            logging.info("TimerManager received stop request, but no timer is running.")
        return was_running

    def _run_timer(self, duration_seconds: int, stop_event: Event) -> None:
        was_cancelled = stop_event.wait(timeout=duration_seconds)
        if was_cancelled:
            return

        with self._lock:
            if self._stop_event is not stop_event:
                return
            self._is_running = False
            self._duration_seconds = None
            self._ends_at = None
            self._timer_thread = None
            self._alert_pending = True

        logging.info("Timer finished. Playing timer completion sound.")
        self._play_timer_complete_sound()

    def clear_pending_alert(self) -> bool:
        with self._lock:
            had_alert_pending = self._alert_pending
            self._alert_pending = False
            return had_alert_pending

    def get_timer_remaining(self) -> str:
        with self._lock:
            is_running = self._is_running
            ends_at = self._ends_at
            alert_pending = self._alert_pending

        if not is_running or ends_at is None:
            if alert_pending:
                return "The timer has already finished."
            return "There is no timer running right now."

        remaining_seconds = max(0, int((ends_at - datetime.now()).total_seconds()))
        if remaining_seconds == 0:
            return "Less than 1 second remains on the timer."

        formatted_duration = _format_duration(remaining_seconds)
        if remaining_seconds == 1:
            return f"There is {formatted_duration} remaining on the timer."
        return f"There are {formatted_duration} remaining on the timer."

    def _play_timer_complete_sound(self) -> bool:
        if not TIMER_COMPLETE_RESPONSES_DIR.exists():
            logging.warning(
                "Timer complete responses directory does not exist: %s",
                TIMER_COMPLETE_RESPONSES_DIR,
            )
            return False

        sound_files = [path for path in TIMER_COMPLETE_RESPONSES_DIR.iterdir() if path.is_file()]
        if not sound_files:
            logging.warning(
                "No timer completion sound files found in %s",
                TIMER_COMPLETE_RESPONSES_DIR,
            )
            return False

        selected_sound = random.choice(sound_files)
        logging.info("Playing timer completion sound: %s", selected_sound)
        read_out_response_from_file(selected_sound)
        return True


timer_manager = TimerManager()
TIMER_MANAGER = timer_manager


def start_timer(duration_seconds: int) -> bool:
    return timer_manager.start_timer(duration_seconds)


def stop_timer() -> str:
    stopped_timer = timer_manager.stop_timer()
    if stopped_timer:
        return "Okay, stopping the timer."

    stopped_music = stop_music()
    stopped_aplay = stop_active_aplay_playback()
    if stopped_music or stopped_aplay:
        logging.info(
            "No active timer found. Stopped background playback for timer stop request."
        )
        return "Okay, stopping it."

    return "There is no timer running right now."


def get_timer_remaining() -> str:
    """Report the time remaining on the active timer."""
    return timer_manager.get_timer_remaining()
