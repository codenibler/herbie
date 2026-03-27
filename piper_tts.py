import subprocess
import logging
import wave
import sys
import os

from helpers.audio_output import (
    build_wav_playback_command,
    cleanup_temp_wavs,
    prepend_silence_to_wav,
    prepare_wav_for_output_channel_mode,
)
from pathlib import Path
from dotenv import load_dotenv
from piper import PiperVoice, SynthesisConfig
from toolbox import led_strip


load_dotenv(override=True)
voice_model_path = os.getenv("PIPER_VOICE_MODEL_PATH")
voice = PiperVoice.load(voice_model_path) 


def _get_optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return int(value)


def _get_optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return float(value)


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_synthesis_config() -> SynthesisConfig:
    return SynthesisConfig(
        length_scale=_get_optional_float_env("PIPER_LENGTH_SCALE"),
        noise_scale=_get_optional_float_env("PIPER_NOISE_SCALE"),
        noise_w_scale=_get_optional_float_env("PIPER_NOISE_W_SCALE"),
        normalize_audio=_get_bool_env("PIPER_NORMALIZE_AUDIO", True),
        volume=float(os.getenv("PIPER_VOLUME", "1.0")),
    )

def read_out_response(text: str):

    if text is None or len(text) == 0:
        return 

    RESPONSE_AUDIO_DIR = os.getenv("RESPONSE_AUDIO_DIR", "response_audio")

    out_wav = Path(RESPONSE_AUDIO_DIR) / f"{text[:20]}.wav"
    out_wav.parent.mkdir(parents=True, exist_ok=True)  

    logging.debug(f"Synthesizing response to {out_wav}...")

    with wave.open(str(out_wav), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=build_synthesis_config())

    padded_wav = prepend_silence_to_wav(out_wav)
    playback_wav = prepare_wav_for_output_channel_mode(padded_wav)
    led_session_id = led_strip.begin_audio_led_visualizer(playback_wav)
    try:
        playback_command = build_wav_playback_command(playback_wav)
        logging.info(f"Playing audio via preferred USB Audio output: {' '.join(playback_command)}")
        subprocess.run(playback_command, check=False)
    finally:
        led_strip.stop_audio_led_visualizer(led_session_id)
        cleanup_temp_wavs(padded_wav, playback_wav)



def read_out_response_from_file(file_path: str):
    padded_wav = prepend_silence_to_wav(file_path)
    playback_wav = prepare_wav_for_output_channel_mode(padded_wav)
    led_session_id = led_strip.begin_audio_led_visualizer(playback_wav)
    try:
        playback_command = build_wav_playback_command(playback_wav)
        logging.info(f"Playing audio file via preferred USB Audio output: {' '.join(playback_command)}")
        subprocess.run(playback_command, check=False)
    finally:
        led_strip.stop_audio_led_visualizer(led_session_id)
        cleanup_temp_wavs(padded_wav, playback_wav)


if __name__ == "__main__":
    read_out_response(sys.argv[1])
