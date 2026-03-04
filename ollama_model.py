from toolbox import tools

import datetime as dt
import logging
import asyncio
import inspect
import ollama
import json
import os
import re


TOOL_MAP = {
    "kitchen_light_on": tools.kitchen_light_on,
    "kitchen_light_off": tools.kitchen_light_off,
    "station_lights_off": tools.station_lights_off,
    "station_lights_on": tools.station_lights_on, 
    "station_light_brightness": tools.station_light_brightness,
    "station_light_color": tools.station_light_color,
}
KEY_VOCAB = {
    "kitchen","station","light","lights","on","off",
    "brightness","color","colors","colored"
}
CANON = {
    "lights": "light",
}

def ollama_query(user_text):
    # Determine through string matching if tool is usable.
    MODEL = os.getenv("OLLAMA_MODEL_NAME")
    assert MODEL is not None, "OLLAMA_MODEL_NAME environment variable not set."

    tool, user_text = determine_relevent_tool(user_text)  
    if tool is not None:
        response = ollama.chat(model=MODEL, messages=[{'role': 'user', 'content':user_text}], tools=[tool])  
        logging.info(f"Selected tool for this query: {tool}")
        logging.info(f"Ollama response: {response['message']['content']}")
        execute_tool_calls(response['message']['tool_calls'])
    else:
        response = ollama.chat(model=MODEL, messages=[{'role': 'user', 'content':user_text}])  
    
    logging.info(f"Ollama response: {response['message']['content']}")
    return response['message']['content']

def determine_relevent_tool(user_text):
    # Keyword match potential toosl to avoid slow model. 
    """ KITCHEN LIGHTING """
    if words_present_in_text(["kitchen", "light", "on"], user_text.lower()):
        return tools.kitchen_light_on, user_text
    elif words_present_in_text(["kitchen", "light", "off"], user_text.lower()):
        return tools.kitchen_light_off, user_text

    """ LIVING ROOM LIGHTING """
    if words_present_in_text(["station", "lights", "on"], user_text.lower()):
        return tools.station_lights_on, user_text
    elif words_present_in_text(["station", "lights", "off"], user_text.lower()):
        return tools.station_lights_off, user_text
    elif words_present_in_text(["station", "light", "brightness"], user_text.lower()):
        user_text += "Brightness should be % value between 0 and 100." 
        return tools.station_light_brightness, user_text
    elif words_present_in_text(["station", "light", "turn"], user_text.lower()):
        user_text += f"Options for colors are: {sorted(list(tools.COLORS.keys()))}"
        return tools.station_light_color, user_text # Let herbie know specific color options. 
    """ ADD MORE ELEGANT CHECK FOR PLURAL OF LIGHTS """

    """ TO DO: ADD GOOGLE CALENDAR SCHEDULER TOOL """
    """ TO DO: ADD TIMER TOOL """

    logging.info("No relevant tool found for this query.")
    return None, user_text

def execute_tool_calls(tool_calls):
    for tool_call in tool_calls:
        function_name = tool_call['function']['name']
        function_args = tool_call['function']['arguments']
        if function_name in TOOL_MAP:
            logging.info(f"Executing tool: {function_name}, with arguments: {function_args}")
            if inspect.iscoroutinefunction(TOOL_MAP[function_name]):
                tool_response = asyncio.run(TOOL_MAP[function_name](**function_args))  # Await if it's a coroutine
            else:   
                tool_response = TOOL_MAP[function_name](**function_args)  # Execute the tool function with arguments
            logging.info(f"Tool response: {tool_response}")
        else:
            logging.warning(f"Tool {function_name} not found in tool map.")

def words_present_in_text(words, text):
    tokens = re.findall(r'\b\w+\b', text.lower())  # Tokenize
    for token in tokens:
        if token in CANON:
            tokens.append(CANON[token])  # Add canonical forms to tokenizer
    return all(word in tokens for word in words) # Truthy if all present

""" TO DO: MAKE ASYNC, AS WELL AS MAIN LOOP """
def warm_up_ollama_model():
    
    model=os.getenv("OLLAMA_MODEL_NAME")
    keep_alive=os.getenv("OLLAMA_KEEP_ALIVE")
    assert model is not None, "OLLAMA_MODEL_NAME environment variable not set."
    assert keep_alive is not None, "OLLAMA_KEEP_ALIVE environment variable not set."

    logging.info("Warming up Ollama model...")
    ollama.generate(model=model, keep_alive=keep_alive)
    logging.info("Herbie officially warmed up")

