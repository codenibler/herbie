from __future__ import annotations

import logging

from helpers.audio_output import stop_active_aplay_playback
from toolbox.music import stop_music
from toolbox.timer import TIMER_MANAGER


def stop_background_playback() -> str:
    stopped_timer = TIMER_MANAGER.stop_timer()
    stopped_music = stop_music()
    stopped_aplay = stop_active_aplay_playback()

    if stopped_timer and (stopped_music or stopped_aplay):
        logging.info("Stopped active timer and background playback.")
        return "Okay, stopping the timer and background audio."

    if stopped_timer:
        return "Okay, stopping the timer."

    if stopped_music or stopped_aplay:
        logging.info("Stopped background playback without an active timer.")
        return "Okay, stopping it."

    return "Nothing is playing right now."
