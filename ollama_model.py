import logging
import asyncio
import ollama
import os

def ollama_query(user_text):
    # Query the Ollama model with the user's text input
    model = os.getenv("OLLAMA_MODEL_NAME", "herbie")
    # Define herbie's indentity
    response = ollama.chat(model=model, messages=[{'role': 'user', 'content': user_text}])  
    logging.info(f"Ollama response: {response['message']['content']}")
    return response['message']['content']

async def warm_up_ollama_model():
    model=os.getenv("OLLAMA_MODEL_NAME", "herbie")
    logging.info("Warming up Ollama model...")
    warmup_task = asyncio.create_task(ollama.AsyncClient().generate(model=model, keep_alive='1h'))
    await warmup_task
    logging.info("Herbie officially warmed up")