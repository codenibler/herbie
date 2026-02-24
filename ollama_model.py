import datetime as dt
import logging
import ollama
import os

def ollama_query(user_text):
    # Query the Ollama model with the user's text input
    model = os.getenv("OLLAMA_MODEL_NAME", "marvin")
    # Define herbie's indentity
    response = ollama.chat(model=model, messages=[{'role': 'user', 'content':user_text}])  
    logging.info(f"Ollama response: {response['message']['content']}")
    return response['message']['content']

def warm_up_ollama_model():
    model=os.getenv("OLLAMA_MODEL_NAME", "herbie")
    keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "1h")
    logging.info("Warming up Ollama model...")
    ollama.generate(model=model, keep_alive=keep_alive)
    logging.info("Herbie officially warmed up")