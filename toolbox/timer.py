from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread

import logging
import os
import random

from piper_tts import read_out_response_from_file


TIMER_COMPLETE_RESPONSES_DIR = Path(
    os.getenv("TIMER_COMPLETE_RESPONSES_DIR", "herbie_responses/timer_complete")
)


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


def stop_timer() -> bool:
    return timer_manager.stop_timer()
