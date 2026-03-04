# Entry point for the application
from user_listening_loop import listen_for_user_input, calibrate_ambient_noise
from piper_tts import read_out_response, read_out_response_from_file
from ollama_model import ollama_query, warm_up_ollama_model
from wakeword_loop import initialize_wakeword_loop
from parse_user_input import parse_user_input
from setup.microphone_setup import setup_default_microphone
from setup.log_setup import setup_logging
from dotenv import load_dotenv
from gpiozero import Buzzer
from pathlib import Path

import logging
import random
import time
import os

load_dotenv(override=True)  

BUZZER_PIN = 2
GENERIC_HERBIE_RESPONSES_DIR = "generic_herbie_responses"
AMBIENT_NOISE_VALUE = 750  # Reclibrated every RECALIBRATION_INTERVAL seconds
RECALIBRATION_INTERVAL = int(os.getenv("RECALIBRATION_INTERVAL", 600))  
LAST_RECALIBRATION_TIME = None

# Testing function for wakeword
def activate_buzzer():
    buzzer = Buzzer(BUZZER_PIN)
    for _ in range(2):
        buzzer.on()
        time.sleep(0.1)
        buzzer.off()
        time.sleep(0.1)

def main():
    # Initial setup
    global AMBIENT_NOISE_VALUE, LAST_RECALIBRATION_TIME

    load_dotenv(override=True) # Override environemnt vars with those in .env
    setup_logging() 
    setup_default_microphone()
    warm_up_ollama_model()  # Warm up with system prompt. 
    AMBIENT_NOISE_VALUE = calibrate_ambient_noise()  # Calibrate ambient noise level on startup.
    LAST_RECALIBRATION_TIME = time.time()

    while True:
        if (time.time() - LAST_RECALIBRATION_TIME) >= RECALIBRATION_INTERVAL:
            logging.info("Recalibrating ambient noise level...")
            AMBIENT_NOISE_VALUE = calibrate_ambient_noise()
            LAST_RECALIBRATION_TIME = time.time()

        wakeword_detected = initialize_wakeword_loop() # Returns when heard
        activate_buzzer()  # Indicate wakeword detection with buzzer
        
        """ DEACTIVATED FOR NOW. NO SPEAKER """
        # herbie_responses = os.listdir(GENERIC_HERBIE_RESPONSES_DIR)
        # random_herbie_response = random.choice(herbie_responses)
        # logging.info(f"Selected Herbie response: {random_herbie_response}, reading it out.")
        # read_out_response_from_file(Path(f"{GENERIC_HERBIE_RESPONSES_DIR}/{random_herbie_response}"))

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