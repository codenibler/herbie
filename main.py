# Entry point for the application
from ollama_model import ollama_query, warm_up_ollama_model
from user_listening_loop import listen_for_user_input
from wakeword_loop import initialize_wakeword_loop
from parse_user_input import parse_user_input
from piper_tts import read_out_response
from log_setup import setup_logging
from dotenv import load_dotenv
from gpiozero import Buzzer
from time import sleep

import logging
import os

BUZZER_PIN = 2

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
    load_dotenv(override=True) # Override environemnt vars with those in .env
    setup_logging() 
    """ TO DO: ADD BACKGROUND NOISE LEVEL CALIBRATOR ASYNCED WHILE WE WARM UP MODEL. """
    warm_up_ollama_model()  # Warm up with system prompt. 

    wakeword_detected = initialize_wakeword_loop() # Returns when heard
    activate_buzzer()  # Buzz to indicate wake word was detected

    """ TO DO : ADD GENERIC HERBIE RESPONSE, LIKE 'HEY BOSS!'"""

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