# Entry point for the application
from user_listening_loop import listen_for_user_input, calibrate_ambient_noise, calibrate_ambient_noise_async
from piper_tts import read_out_response, read_out_response_from_file
from ollama_model import ollama_query, warm_up_ollama_model_async
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

BUZZER_PIN = int(os.getenv("BUZZER_PIN", 2))
BUZZER_BEEP_COUNT = int(os.getenv("BUZZER_BEEP_COUNT", 2))
BUZZER_BEEP_ON_SECONDS = float(os.getenv("BUZZER_BEEP_ON_SECONDS", 0.1))
BUZZER_BEEP_OFF_SECONDS = float(os.getenv("BUZZER_BEEP_OFF_SECONDS", 0.1))
AMBIENT_NOISE_VALUE = float(os.getenv("AMBIENT_NOISE_THRESHOLD", 700.0))
RECALIBRATION_INTERVAL = int(os.getenv("RECALIBRATION_INTERVAL", 600))  
LAST_RECALIBRATION_TIME = None
USE_BLUETOOTH_SPEAKER = os.getenv("USE_BLUETOOTH_SPEAKER", "False").lower() == "true"
GREETING_RESPONSES_DIR = Path(os.getenv("GREETING_RESPONSES_DIR", "herbie_responses/greetings"))

# Testing function for wakeword
def activate_buzzer():
    buzzer = Buzzer(BUZZER_PIN)
    for _ in range(BUZZER_BEEP_COUNT):
        buzzer.on()
        time.sleep(BUZZER_BEEP_ON_SECONDS)
        buzzer.off()
        time.sleep(BUZZER_BEEP_OFF_SECONDS)


async def initialize_startup_tasks():
    logging.info("Starting Ollama warm-up and ambient noise calibration concurrently.")
    warm_up_task = asyncio.create_task(warm_up_ollama_model_async())
    calibrate_task = asyncio.create_task(calibrate_ambient_noise_async())

    ambient_noise_value = await calibrate_task
    await warm_up_task

    return ambient_noise_value, time.time()


def main():
    # Initial setup
    global AMBIENT_NOISE_VALUE, LAST_RECALIBRATION_TIME

    load_dotenv(override=True) # Override environemnt vars with those in .env
    setup_logging() 
    setup_default_microphone()
    if USE_BLUETOOTH_SPEAKER:
        from helpers.set_bluetooth_out import bluetooth_ctl_connect
        bluetooth_ctl_connect()  # Connect to Bluetooth speaker if enabled.
    AMBIENT_NOISE_VALUE, LAST_RECALIBRATION_TIME = asyncio.run(initialize_startup_tasks())

    while True:

        """ TO DO: MAKE ASYNC """
        if (time.time() - LAST_RECALIBRATION_TIME) >= RECALIBRATION_INTERVAL:
            logging.info("Recalibrating ambient noise level...")
            AMBIENT_NOISE_VALUE = calibrate_ambient_noise()
            LAST_RECALIBRATION_TIME = time.time()

        wakeword_detected = initialize_wakeword_loop() # Returns when heard
        # activate_buzzer()  # Indicate wakeword detection with buzzer        
        random_herbie_response = random.choice(os.listdir(GREETING_RESPONSES_DIR))
        logging.info(f"Selected Herbie response: {random_herbie_response}, reading it out.")
        read_out_response_from_file(GREETING_RESPONSES_DIR / random_herbie_response)

        if wakeword_detected:
            """ TO DO: SET UP LED ANIMATIONS AND SOUND FOR HERBIE ACTIVATION """
            wav_bytes = listen_for_user_input()
        
        """ TO DO: ADD ERROR LIMIT UPPER BOUND, AND SET THIS UP AS MORE ROBUST SUPERLOOP """
        user_text = parse_user_input(wav_bytes)
        if user_text is None:
            logging.error("Failed to parse user input. Retrying...")
            user_text =listen_for_user_input()  # Optionally, you could add a retry limit here.
        
        ollama_response = ollama_query(user_text)
        read_out_response(ollama_response)  
        activate_buzzer()




if __name__ == "__main__":
    main()
