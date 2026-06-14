# Entry point for the application
from user_listening_loop import listen_for_user_input, calibrate_ambient_noise, calibrate_ambient_noise_async
from piper_tts import (
    PlaybackInterruptedByWakeword,
    read_out_response,
    read_out_response_from_file,
)
from groq_model import (
    build_time_query_response,
    is_background_audio_stop_request,
    is_time_query,
    groq_query,
    warm_up_groq_client_async,
)
from helpers.audio_output import (
    duck_preferred_output_volume_if_playing,
    restore_preferred_output_volume,
    set_preferred_output_volume_percent,
)
from toolbox.background_audio import stop_background_playback
from toolbox import led_strip
from toolbox.led_strip import enable_pi5_led_runtime
from wakeword_loop import initialize_wakeword_loop
from parse_user_input import parse_user_input
from setup.microphone_setup import setup_default_microphone
from setup.log_setup import setup_logging
from dotenv import load_dotenv
from gpiozero import Buzzer
from pathlib import Path

import asyncio
import logging
import random
import time
import os

load_dotenv(override=True)  

AMBIENT_NOISE_VALUE = float(os.getenv("AMBIENT_NOISE_THRESHOLD", 700.0))
RECALIBRATION_INTERVAL = int(os.getenv("RECALIBRATION_INTERVAL", 600))  
LAST_RECALIBRATION_TIME = None
USE_BLUETOOTH_SPEAKER = os.getenv("USE_BLUETOOTH_SPEAKER", "False").lower() == "true"
GREETING_RESPONSES_DIR = Path(os.getenv("GREETING_RESPONSES_DIR", "herbie_responses/greetings"))
STARTUP_OUTPUT_VOLUME_PERCENT = int(os.getenv("STARTUP_OUTPUT_VOLUME_PERCENT", 100))
WAKEWORD_DUCKED_VOLUME_PERCENT = int(os.getenv("WAKEWORD_DUCKED_VOLUME_PERCENT", 20))


def activate_buzzer():
    buzzer = Buzzer(BUZZER_PIN)
    for _ in range(BUZZER_BEEP_COUNT):
        buzzer.on()
        time.sleep(BUZZER_BEEP_ON_SECONDS)
        buzzer.off()
        time.sleep(BUZZER_BEEP_OFF_SECONDS)


async def initialize_startup_tasks():
    logging.info("Starting Groq client validation and ambient noise calibration concurrently.")
    warm_up_task = asyncio.create_task(warm_up_groq_client_async())
    calibrate_task = asyncio.create_task(calibrate_ambient_noise_async())

    ambient_noise_value = await calibrate_task
    await warm_up_task

    return ambient_noise_value, time.time()


def capture_user_text(initial_noise_floor: float) -> str | None:
    interaction_loading_started = led_strip.start_loading_led_animation()
    wav_bytes = listen_for_user_input(initial_noise_floor=initial_noise_floor)
    if not wav_bytes:
        logging.info("No speech detected after wake word.")
        if interaction_loading_started:
            led_strip.stop_loading_led_animation()
        return None

    user_text = parse_user_input(wav_bytes)
    if user_text is not None:
        return user_text

    logging.error("Failed to parse user input. Retrying...")
    wav_bytes = listen_for_user_input(initial_noise_floor=initial_noise_floor)
    if not wav_bytes:
        if interaction_loading_started:
            led_strip.stop_loading_led_animation()
        return None

    user_text = parse_user_input(wav_bytes)
    if user_text is None and interaction_loading_started:
        led_strip.stop_loading_led_animation()
    return user_text


def capture_user_text_after_playback_interrupt(initial_noise_floor: float) -> str | None:
    logging.info(
        "Wakeword detected during playback. Interrupting current message and listening again."
    )
    led_strip.set_idle_led_mode(False)
    return capture_user_text(initial_noise_floor)


def process_user_text(user_text: str, *, background_audio_ducked: bool) -> None:
    if background_audio_ducked and is_background_audio_stop_request(user_text):
        stop_response = stop_background_playback()
        restore_preferred_output_volume()
        led_strip.stop_loading_led_animation()
        read_out_response(stop_response)
        activate_buzzer()
        return

    if is_time_query(user_text):
        if background_audio_ducked:
            restore_preferred_output_volume()
        time_response = build_time_query_response()
        logging.info(f"Responding locally to time query: {time_response}")
        led_strip.stop_loading_led_animation()
        read_out_response(time_response)
        activate_buzzer()
        return

    if background_audio_ducked:
        restore_preferred_output_volume()

    groq_response = groq_query(user_text)
    led_strip.stop_loading_led_animation()
    read_out_response(groq_response)
    activate_buzzer()


def main():
    # Initial setup
    global AMBIENT_NOISE_VALUE, LAST_RECALIBRATION_TIME

    load_dotenv(override=True) # Override environemnt vars with those in .env
    setup_logging() 
    enable_pi5_led_runtime()
    setup_default_microphone()
    led_strip.start_led_strip_controller()
    led_strip.set_idle_led_mode(True)
    if USE_BLUETOOTH_SPEAKER:
        from helpers.set_bluetooth_out import bluetooth_ctl_connect
        bluetooth_ctl_connect()  
    set_preferred_output_volume_percent(STARTUP_OUTPUT_VOLUME_PERCENT)
    AMBIENT_NOISE_VALUE, LAST_RECALIBRATION_TIME = asyncio.run(initialize_startup_tasks())

    while True:
        led_strip.set_idle_led_mode(True)

        if (time.time() - LAST_RECALIBRATION_TIME) >= RECALIBRATION_INTERVAL:
            logging.info("Recalibrating ambient noise level...")
            AMBIENT_NOISE_VALUE = calibrate_ambient_noise()
            LAST_RECALIBRATION_TIME = time.time()

        wakeword_detected = initialize_wakeword_loop() # Returns when heard
        background_audio_ducked = False

        if wakeword_detected:
            led_strip.set_idle_led_mode(False)
            background_audio_ducked = duck_preferred_output_volume_if_playing(
                ducked_volume_percent=WAKEWORD_DUCKED_VOLUME_PERCENT
            )
            user_text: str | None = None
            should_play_greeting = not background_audio_ducked

            while True:
                try:
                    if should_play_greeting:
                        random_herbie_response = random.choice(os.listdir(GREETING_RESPONSES_DIR))
                        logging.info(
                            f"Selected Herbie response: {random_herbie_response}, reading it out."
                        )
                        read_out_response_from_file(GREETING_RESPONSES_DIR / random_herbie_response)
                        should_play_greeting = False
                    elif background_audio_ducked:
                        logging.info(
                            "Background playback detected. Skipping greeting while output is ducked."
                        )
                        should_play_greeting = False

                    if user_text is None:
                        user_text = capture_user_text(AMBIENT_NOISE_VALUE)
                        if user_text is None:
                            if background_audio_ducked:
                                restore_preferred_output_volume()
                            break

                    process_user_text(
                        user_text,
                        background_audio_ducked=background_audio_ducked,
                    )
                    break
                except PlaybackInterruptedByWakeword:
                    led_strip.stop_loading_led_animation()
                    if background_audio_ducked:
                        restore_preferred_output_volume()
                        background_audio_ducked = False
                    should_play_greeting = False
                    user_text = capture_user_text_after_playback_interrupt(
                        AMBIENT_NOISE_VALUE
                    )
                    if user_text is None:
                        break


if __name__ == "__main__":
    main()
