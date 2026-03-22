from __future__ import annotations

from helpers.audio_output import build_wav_playback_command, cleanup_temp_wav, prepend_silence_to_wav
from pathlib import Path
from threading import Event, Lock
from threading import Thread

import asyncio
import logging
import random
import subprocess


class MusicManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._stop_requested = Event()
        self._current_process: subprocess.Popen | asyncio.subprocess.Process | None = None
        self._current_song: Path | None = None
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

    def set_queue_active(self, queue_active: bool) -> None:
        with self._lock:
            self._queue_active = queue_active

    def stop_playback(self) -> bool:
        with self._lock:
            process = self._current_process
            was_playing = self._is_playing
            self._stop_requested.set()
            self._current_process = None
            self._current_song = None
            self._is_playing = False
            self._queue_active = False

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
        with self._lock:
            process = self._current_process
            was_playing = self._is_playing
            self._current_process = None
            self._current_song = None
            self._is_playing = False

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
            process = subprocess.Popen(build_wav_playback_command(padded_song_path))
            music_manager.mark_playing(song_path, process)

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
    process = subprocess.Popen(build_wav_playback_command(padded_song_path))
    music_manager.mark_playing(song_path, process)
    Thread(target=_watch_process_exit, args=(process, padded_song_path), daemon=True).start()
    return True


async def play_random_songs() -> bool:
    logging.info("Herbie requested for a general mix of songs to be played.")

    songs_dir = Path("songs")
    song_paths = [song for song in songs_dir.iterdir() if song.is_file()]
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
    song_path = Path(song_path)
    logging.info(f"Herbie called for specific song at {song_path} to be played.")

    if not song_path.exists() or not song_path.is_file():
        logging.info(f"Song at {song_path} not found.")
        return False

    music_manager.stop_playback()
    music_manager.reset_stop_request()
    music_manager.set_queue_active(False)
    return _start_single_song_playback(song_path)


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

    songs_dir = Path("songs")
    song_paths = [song for song in songs_dir.iterdir() if song.is_file()]
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
