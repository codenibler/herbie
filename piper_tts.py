import subprocess
import logging
import wave
import sys
import os
import re
from threading import Event, Thread

from helpers.audio_output import (
    build_wav_playback_command,
    cleanup_temp_wavs,
    prepend_silence_to_wav,
    prepare_wav_for_output_channel_mode,
    stop_active_aplay_playback,
)
from pathlib import Path
from dotenv import load_dotenv
from piper import PiperVoice, SynthesisConfig
from toolbox import led_strip
from wakeword_loop import listen_for_wakeword


load_dotenv(override=True)
voice_model_path = os.getenv("PIPER_VOICE_MODEL_PATH")
voice = PiperVoice.load(voice_model_path) 


class PlaybackInterruptedByWakeword(Exception):
    pass


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


def _sanitize_text_for_tts(text: str) -> str:
    sanitized_text = text.strip()
    if not sanitized_text:
        return ""

    # Convert markdown links to their readable label.
    sanitized_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", sanitized_text)
    # Drop raw URLs rather than reading out long query strings.
    sanitized_text = re.sub(r"https?://\S+", "", sanitized_text)
    # Remove inline code fences and emphasis markers.
    sanitized_text = sanitized_text.replace("`", "")
    sanitized_text = re.sub(r"[*_~#>]+", "", sanitized_text)
    # Remove common list prefixes while keeping the content.
    sanitized_text = re.sub(r"(?m)^\s*[-*+]\s+", "", sanitized_text)
    sanitized_text = re.sub(r"(?m)^\s*\d+\.\s+", "", sanitized_text)
    # Collapse line breaks into sentence-friendly spaces.
    sanitized_text = re.sub(r"\s*\n+\s*", " ", sanitized_text)
    sanitized_text = re.sub(r"\s{2,}", " ", sanitized_text)
    return sanitized_text.strip()


def _monitor_wakeword_during_playback(
    stop_event: Event,
    interrupted_event: Event,
) -> None:
    try:
        wakeword_detected = listen_for_wakeword(
            stop_event=stop_event,
            log_initialization=False,
        )
    except Exception as error:
        logging.warning("Wakeword monitor during playback failed: %s", error)
        return

    if wakeword_detected:
        interrupted_event.set()
        stop_active_aplay_playback()


def _play_wav_with_wakeword_interrupt(playback_wav: Path, log_message: str) -> None:
    playback_command = build_wav_playback_command(playback_wav)
    logging.info("%s %s", log_message, " ".join(playback_command))

    stop_event = Event()
    interrupted_event = Event()
    monitor_thread = Thread(
        target=_monitor_wakeword_during_playback,
        args=(stop_event, interrupted_event),
        name="herbie-playback-wakeword-monitor",
        daemon=True,
    )
    monitor_thread.start()

    try:
        subprocess.run(playback_command, check=False)
    finally:
        stop_event.set()
        monitor_thread.join(timeout=1.0)

    if interrupted_event.is_set():
        raise PlaybackInterruptedByWakeword()

def read_out_response(text: str):

    if text is None or len(text) == 0:
        return 

    sanitized_text = _sanitize_text_for_tts(text)
    if not sanitized_text:
        return

    RESPONSE_AUDIO_DIR = os.getenv("RESPONSE_AUDIO_DIR", "response_audio")

    out_wav = Path(RESPONSE_AUDIO_DIR) / f"{sanitized_text[:20]}.wav"
    out_wav.parent.mkdir(parents=True, exist_ok=True)  

    logging.debug(f"Synthesizing response to {out_wav}...")

    started_loading_animation = led_strip.start_loading_led_animation()
    with wave.open(str(out_wav), "wb") as wav_file:
        try:
            voice.synthesize_wav(sanitized_text, wav_file, syn_config=build_synthesis_config())
            padded_wav = prepend_silence_to_wav(out_wav)
            playback_wav = prepare_wav_for_output_channel_mode(padded_wav)
        finally:
            if started_loading_animation:
                led_strip.stop_loading_led_animation()

    led_session_id = led_strip.begin_audio_led_visualizer(playback_wav)
    try:
        _play_wav_with_wakeword_interrupt(
            playback_wav,
            "Playing audio via preferred USB Audio output:",
        )
    finally:
        led_strip.stop_audio_led_visualizer(led_session_id)
        cleanup_temp_wavs(padded_wav, playback_wav)



def read_out_response_from_file(file_path: str):
    padded_wav = prepend_silence_to_wav(file_path)
    playback_wav = prepare_wav_for_output_channel_mode(padded_wav)
    led_session_id = led_strip.begin_audio_led_visualizer(playback_wav)
    try:
        _play_wav_with_wakeword_interrupt(
            playback_wav,
            "Playing audio file via preferred USB Audio output:",
        )
    finally:
        led_strip.stop_audio_led_visualizer(led_session_id)
        cleanup_temp_wavs(padded_wav, playback_wav)


if __name__ == "__main__":
    read_out_response(sys.argv[1])
