import speech_recognition as sr
import logging
import io
import os


""" TO DO: CHANGE THIS TO RUN LOCALLY """
def parse_user_input(wav_bytes):
    recognizer = sr.Recognizer()

    with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
        audio_data = recognizer.record(source)

    """ TO DO: ADD ERROR HANDLING IN CASE WE COULD NOT PROCESS TEXT. DEFAULT HERBIE ASK 'WHAT WAS THAT?' """

    text = recognizer.recognize_google(audio_data)
    logging.info(f"Recognized text: {text}")
    return text