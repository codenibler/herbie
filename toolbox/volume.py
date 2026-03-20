from __future__ import annotations

import logging

from helpers.audio_output import set_preferred_output_volume_percent


def set_output_volume(volume_percent: int) -> bool:
    """Set the preferred speaker output volume to a value from 0 to 100 percent."""
    normalized_volume_percent = max(0, min(100, int(volume_percent)))
    logging.info("Setting preferred output volume to %s%%.", normalized_volume_percent)
    return set_preferred_output_volume_percent(normalized_volume_percent)
