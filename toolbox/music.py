from __future__ import annotations

from difflib import get_close_matches
from helpers.audio_output import build_wav_playback_command, cleanup_temp_wav, prepend_silence_to_wav
from pathlib import Path
from threading import Event, Lock
from threading import Thread
from toolbox import led_strip

import asyncio
import logging
import random
import re
import subprocess

SONGS_DIR = Path("songs")


class MusicManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._stop_requested = Event()
        self._current_process: subprocess.Popen | asyncio.subprocess.Process | None = None
        self._current_song: Path | None = None
        self._current_led_session_id: int | None = None
        self._is_playing = False
        self._queue_active = False

    def status(self) -> dict[str, str | bool | None]:
        with self._lock:
            return {
                "is_playing": self._is_playing,
                "current_song": str(self._current_song) if self._current_song else None,
                "queue_active": self._queue_active,
            }

    def mark_playing(
        self,
        song_path: Path,
        process: subprocess.Popen | asyncio.subprocess.Process,
        led_session_id: int | None = None,
    ) -> None:
        with self._lock:
            self._stop_requested.clear()
            self._current_song = song_path
            self._current_process = process
            self._current_led_session_id = led_session_id
            self._is_playing = True

    def clear_if_current(
        self,
        process: subprocess.Popen | asyncio.subprocess.Process | None = None,
    ) -> None:
        led_session_id: int | None = None
        with self._lock:
            if process is not None and self._current_process is not process:
                return
            led_session_id = self._current_led_session_id
            self._current_process = None
            self._current_song = None
            self._current_led_session_id = None
            self._is_playing = False

        led_strip.stop_audio_led_visualizer(led_session_id)

    def set_queue_active(self, queue_active: bool) -> None:
        with self._lock:
            self._queue_active = queue_active

    def stop_playback(self) -> bool:
        led_session_id: int | None = None
        with self._lock:
            process = self._current_process
            was_playing = self._is_playing
            led_session_id = self._current_led_session_id
            self._stop_requested.set()
            self._current_process = None
            self._current_song = None
            self._current_led_session_id = None
            self._is_playing = False
            self._queue_active = False

        led_strip.stop_audio_led_visualizer(led_session_id)

        if process is None:
            logging.info("MusicManager received stop request, but nothing is playing.")
            return False

        logging.info("MusicManager stopping active playback.")
        try:
            process.terminate()
        except ProcessLookupError:
            logging.info("Playback process already exited before termination.")
        return was_playing

    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    def reset_stop_request(self) -> None:
        self._stop_requested.clear()

    def skip_current_song(self) -> bool:
        led_session_id: int | None = None
        with self._lock:
            process = self._current_process
            was_playing = self._is_playing
            led_session_id = self._current_led_session_id
            self._current_process = None
            self._current_song = None
            self._current_led_session_id = None
            self._is_playing = False

        led_strip.stop_audio_led_visualizer(led_session_id)

        if process is None:
            logging.info("MusicManager received skip request, but nothing is playing.")
            return False

        logging.info("MusicManager skipping current playback.")
        try:
            process.terminate()
        except ProcessLookupError:
            logging.info("Playback process already exited before termination.")
        return was_playing


music_manager = MusicManager()
MUSIC_MANAGER = music_manager


def _list_song_paths() -> list[Path]:
    if not SONGS_DIR.exists():
        return []
    return sorted(song_path for song_path in SONGS_DIR.iterdir() if song_path.is_file())


def _normalize_song_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _resolve_song_path(song_reference: str) -> Path | None:
    requested_value = str(song_reference).strip()
    if not requested_value:
        return None

    requested_path = Path(requested_value)
    if requested_path.exists() and requested_path.is_file():
        return requested_path

    direct_candidates = []
    if requested_path.name:
        direct_candidates.append(SONGS_DIR / requested_path.name)
    direct_candidates.append(SONGS_DIR / requested_value)

    for candidate in direct_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    song_paths = _list_song_paths()
    if not song_paths:
        return None

    normalized_requests = {
        _normalize_song_lookup(requested_value),
        _normalize_song_lookup(requested_path.name),
        _normalize_song_lookup(requested_path.stem),
    }
    normalized_requests.discard("")

    exact_matches = [
        song_path
        for song_path in song_paths
        if normalized_requests
        & {
            _normalize_song_lookup(song_path.name),
            _normalize_song_lookup(song_path.stem),
        }
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    partial_matches = []
    for song_path in song_paths:
        normalized_song_stem = _normalize_song_lookup(song_path.stem)
        if any(
            len(request) >= 4 and request in normalized_song_stem
            for request in normalized_requests
        ):
            partial_matches.append(song_path)
    if len(partial_matches) == 1:
        return partial_matches[0]

    for request in sorted(normalized_requests, key=len, reverse=True):
        close_matches = get_close_matches(
            request,
            [_normalize_song_lookup(song_path.stem) for song_path in song_paths],
            n=1,
            cutoff=0.88,
        )
        if not close_matches:
            continue
        matched_key = close_matches[0]
        matched_paths = [
            song_path
            for song_path in song_paths
            if _normalize_song_lookup(song_path.stem) == matched_key
        ]
        if len(matched_paths) == 1:
            return matched_paths[0]

    return None


def _watch_process_exit(process: subprocess.Popen, temp_wav_path: Path | None = None) -> None:
    process.wait()
    music_manager.clear_if_current(process)
    cleanup_temp_wav(temp_wav_path)


def _play_song_queue_worker(song_paths: list[Path]) -> None:
    try:
        for song_path in song_paths:
            if music_manager.stop_requested():
                break

            logging.info("Playing %s", song_path)
            padded_song_path = prepend_silence_to_wav(song_path)
            led_session_id = led_strip.begin_audio_led_visualizer(padded_song_path)
            try:
                process = subprocess.Popen(build_wav_playback_command(padded_song_path))
            except Exception:
                led_strip.stop_audio_led_visualizer(led_session_id)
                cleanup_temp_wav(padded_song_path)
                raise
            music_manager.mark_playing(song_path, process, led_session_id=led_session_id)

            try:
                process.wait()
            finally:
                music_manager.clear_if_current(process)
                cleanup_temp_wav(padded_song_path)

            if music_manager.stop_requested():
                break
    finally:
        music_manager.set_queue_active(False)


def _start_single_song_playback(song_path: Path) -> bool:
    logging.info("Playing %s", song_path)
    padded_song_path = prepend_silence_to_wav(song_path)
    led_session_id = led_strip.begin_audio_led_visualizer(padded_song_path)
    try:
        process = subprocess.Popen(build_wav_playback_command(padded_song_path))
    except Exception:
        led_strip.stop_audio_led_visualizer(led_session_id)
        cleanup_temp_wav(padded_song_path)
        raise
    music_manager.mark_playing(song_path, process, led_session_id=led_session_id)
    Thread(target=_watch_process_exit, args=(process, padded_song_path), daemon=True).start()
    return True


async def play_random_songs() -> bool:
    logging.info("Herbie requested for a general mix of songs to be played.")

    song_paths = _list_song_paths()
    if not song_paths:
        logging.info("No songs found to play.")
        return False

    music_manager.stop_playback()
    music_manager.reset_stop_request()
    music_manager.set_queue_active(True)
    shuffled_song_paths = random.sample(song_paths, k=len(song_paths))
    Thread(target=_play_song_queue_worker, args=(shuffled_song_paths,), daemon=True).start()
    return True


async def play_specific_song(song_path: str) -> bool:
    """Play a song from the local songs directory.

    The argument may be an exact relative path, a filename, or a human-readable
    title. Placeholder absolute paths like /path/to/songs/... are resolved by
    basename against the local songs directory.
    """
    requested_song_path = Path(song_path)
    resolved_song_path = _resolve_song_path(song_path)
    logging.info(
        "Herbie called for specific song at %s to be played. Resolved path: %s",
        requested_song_path,
        resolved_song_path,
    )

    if resolved_song_path is None:
        logging.info("Song at %s not found.", requested_song_path)
        return False

    music_manager.stop_playback()
    music_manager.reset_stop_request()
    music_manager.set_queue_active(False)
    return _start_single_song_playback(resolved_song_path)


def stop_music() -> bool:
    return music_manager.stop_playback()


def skip_song() -> bool | str:
    status = music_manager.status()
    current_song = status["current_song"]

    if not status["is_playing"] or current_song is None:
        return "Nothing is playing right now."

    if status["queue_active"]:
        if music_manager.skip_current_song():
            return True
        return "Nothing is playing right now."

    song_paths = _list_song_paths()
    current_song_path = Path(current_song)
    alternative_song_paths = [song for song in song_paths if song != current_song_path]

    if not alternative_song_paths:
        return "There is no other song available to skip to."

    if not music_manager.skip_current_song():
        return "Nothing is playing right now."
    music_manager.reset_stop_request()
    music_manager.set_queue_active(False)
    next_song_path = random.choice(alternative_song_paths)
    return _start_single_song_playback(next_song_path)
