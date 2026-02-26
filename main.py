# Entry point for the application
from piper_tts import read_out_response, read_out_response_from_file
from ollama_model import ollama_query, warm_up_ollama_model
from user_listening_loop import listen_for_user_input
from wakeword_loop import initialize_wakeword_loop
from parse_user_input import parse_user_input
from log_setup import setup_logging
from dotenv import load_dotenv
from gpiozero import Buzzer
from pathlib import Path
from time import sleep

import logging
import random
import os

BUZZER_PIN = 2
GENERIC_MARVIN_RESPONSES_DIR = "generic_marvin_responses"

# Testing function for wakeword
""" NEED TO IMPORT OLLAMA AND START TESTING SPEEDS AND SENDING MESSAGES"""
def activate_buzzer():
    buzzer = Buzzer(BUZZER_PIN)
    for _ in range(2):
        buzzer.on()
        sleep(0.1)
        buzzer.off()
        sleep(0.1)

def main():
    # Initial setup
    load_dotenv(override=True) # Override environemnt vars with those in .env
    setup_logging() 
    """ TO DO: ADD BACKGROUND NOISE LEVEL CALIBRATOR  WHILE WE WARM UP MODEL. """
    """ - Probably not enough to do once on startup, should be more frequent """
    warm_up_ollama_model()  # Warm up with system prompt. 

    while True:
        wakeword_detected = initialize_wakeword_loop() # Returns when heard
        marv_responses = os.listdir(GENERIC_MARVIN_RESPONSES_DIR)
        logging.info(f"Selecting random Marv response from {GENERIC_MARVIN_RESPONSES_DIR}...")
        logging.info("Available Marv responses: " + ", ".join(marv_responses))

        random_marv_response = random.choice(marv_responses)
        read_out_response_from_file(Path(f"{GENERIC_MARVIN_RESPONSES_DIR}/{random_marv_response}"))

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