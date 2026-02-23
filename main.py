# Entry point for the application
from wakeword_loop import initialize_wakeword_loop
from log_setup import setup_logging
from dotenv import load_dotenv
from gpiozero import Buzzer
from time import sleep

import logging

BUZZER_PIN = 2  # GPIO pin for the buzzer

# Testing function for wakeword
def activate_buzzer():
    logging.info("Wake word detected. Activating Herbie...")
    # Activate buzzer to indicate wake word detection
    buzzer = Buzzer(BUZZER_PIN)
    buzzer.on()
    sleep(3)
    buzzer.off()

def main():
    # Override existing environment variables with those from the .env file
    load_dotenv(override=True)

    setup_logging()
    wakeword_detected = initialize_wakeword_loop()

    if wakeword_detected:
        activate_buzzer()

if __name__ == "__main__":
    main()