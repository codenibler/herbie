from __future__ import annotations

from pathlib import Path
from threading import Event, Lock
from threading import Thread

import asyncio
import logging
import os
import random
import subprocess


def _use_bluetooth_speaker() -> bool:
    return os.getenv("USE_BLUETOOTH_SPEAKER", "").strip().lower() == "true"


def _playback_command() -> str:
    return "pw-play" if _use_bluetooth_speaker() else "aplay"


class MusicManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._stop_requested = Event()
        self._current_process: subprocess.Popen | asyncio.subprocess.Process | None = None
        self._current_song: Path | None = None
        self._is_playing = False

    def status(self) -> dict[str, str | bool | None]:
        with self._lock:
            return {
                "is_playing": self._is_playing,
                "current_song": str(self._current_song) if self._current_song else None,
            }

    def mark_playing(
        self,
        song_path: Path,
        process: subprocess.Popen | asyncio.subprocess.Process,
    ) -> None:
        with self._lock:
            self._stop_requested.clear()
            self._current_song = song_path
            self._current_process = process
            self._is_playing = True

    def clear_if_current(
        self,
        process: subprocess.Popen | asyncio.subprocess.Process | None = None,
    ) -> None:
        with self._lock:
            if process is not None and self._current_process is not process:
                return
            self._current_process = None
            self._current_song = None
            self._is_playing = False

    def stop_playback(self) -> bool:
        with self._lock:
            process = self._current_process
            was_playing = self._is_playing
            self._stop_requested.set()
            self._current_process = None
            self._current_song = None
            self._is_playing = False

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


music_manager = MusicManager()
MUSIC_MANAGER = music_manager


def _watch_process_exit(process: subprocess.Popen) -> None:
    process.wait()
    music_manager.clear_if_current(process)


async def play_random_songs() -> bool:
    logging.info("Herbie requested for a general mix of songs to be played.")

    songs_dir = Path("songs")
    song_paths = [song for song in songs_dir.iterdir() if song.is_file()]
    if not song_paths:
        logging.info("No songs found to play.")
        return False

    music_manager.stop_playback()
    music_manager.reset_stop_request()
    for song_path in random.sample(song_paths, k=len(song_paths)):
        if music_manager.stop_requested():
            break

        logging.info(f"Playing {song_path}")
        process = await asyncio.create_subprocess_exec(_playback_command(), str(song_path))
        music_manager.mark_playing(song_path, process)

        try:
            await process.wait()
        finally:
            music_manager.clear_if_current(process)

        if music_manager.stop_requested():
            break

    return True


async def play_specific_song(song_path: str) -> bool:
    song_path = Path(song_path)
    logging.info(f"Herbie called for specific song at {song_path} to be played.")

    if not song_path.exists() or not song_path.is_file():
        logging.info(f"Song at {song_path} not found.")
        return False

    music_manager.stop_playback()
    music_manager.reset_stop_request()

    logging.info(f"Playing {song_path}")
    process = subprocess.Popen([_playback_command(), str(song_path)])
    music_manager.mark_playing(song_path, process)
    Thread(target=_watch_process_exit, args=(process,), daemon=True).start()
    return True


def stop_music() -> bool:
    return music_manager.stop_playback()
