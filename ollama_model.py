from toolbox import lighting
from toolbox import gcalendar
from toolbox import timer
from toolbox import music

from datetime import datetime
from zoneinfo import ZoneInfo

import logging
import asyncio
import inspect
import ollama
import json
import os
import re

TOOL_MAP = {
    "turn_everything_off": lighting.turn_everything_off,
    "turn_everything_on": lighting.turn_everything_on,
    "kitchen_light_on": lighting.kitchen_light_on,
    "kitchen_light_off": lighting.kitchen_light_off,
    "station_lights_off": lighting.station_lights_off,
    "station_lights_on": lighting.station_lights_on, 
    "station_light_brightness": lighting.station_light_brightness,
    "station_light_color": lighting.station_light_color,
    "station_lights_freaky": lighting.station_lights_freaky,
    "make_calendar_event": gcalendar.make_calendar_event,
    "play_random_songs": music.play_random_songs,
    "play_specific_song": music.play_specific_song

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
        response = ollama.chat(model=MODEL, messages=[{'role': 'user', 'content':user_text}], tools=tool)  
        logging.info(f"Selected tool for this query: {tool}")
        logging.info(f"Ollama response: {response['message']['content']}")
        if 'tool_calls' in response["message"]:
            logging.warning("Tool selected, but Herbie did not call it.")
            execute_tool_calls(response['message']['tool_calls'])
    else:
        response = ollama.chat(model=MODEL, messages=[{'role': 'user', 'content':user_text}])  
    
    logging.info(f"Ollama response: {response['message']['content']}")
    return response['message']['content']

def determine_relevent_tool(user_text):
    """ ALL LIGHTS """
    if one_word_present_in_text(["everything", "every", "on"], user_text.lower()):
        return [lighting.turn_everything_off, lighting.turn_everything_on], user_text

    """ KITCHEN LIGHTING """
    if words_present_in_text(["kitchen", "on"], user_text.lower()):
        return [lighting.kitchen_light_on], user_text
    elif words_present_in_text(["kitchen", "off"], user_text.lower()):
        return [lighting.kitchen_light_off], user_text

    """ MUSIC """ 
    if one_word_present_in_text(["bangers", "song", "music"], user_text.lower()):
        user_text += f"If user wants specific song choice, select from the following options: {os.listdir('songs')}, and send in as the parameter. Otherwise, call play_random_songs with no parameters"
        return [music.play_random_songs, music.play_specific_song], user_text
    if words_present_in_text(["play"], user_text.lower()):
        user_text += f"If user wants specific song choice, select from the following options: {os.listdir('songs')}, and send in as the parameter. Otherwise, call play_random_songs with no parameters"
        return [music.play_specific_song], user_text

    """ LIVING ROOM LIGHTING """
    if words_present_in_text(["station", "on"], user_text.lower()):
        user_text += "Use the station_lights_on tool"
        return [lighting.station_lights_on], user_text
    elif words_present_in_text(["station", "off"], user_text.lower()):
        user_text += "Use the station_lights_off tool"
        return [lighting.station_lights_off], user_text
    elif words_present_in_text(["station", "brightness"], user_text.lower()):
        user_text += "Brightness should be % value between 0 and 100." 
        return [lighting.station_light_brightness], user_text
    elif words_present_in_text(["station", "turn"], user_text.lower()):
        user_text += f"Options for colors are: {sorted(list(lighting.COLORS.keys()))}"
        return [lighting.station_light_color], user_text # Let herbie know specific color options. 
    elif words_present_in_text(["freaky"], user_text.lower()):
        user_text += "Use the station_lights_freaky tool"
        return [lighting.station_lights_freaky], user_text 
    elif words_present_in_text(["station"], user_text.lower()):
        return [lighting.station_lights_on, lighting.station_lights_off, lighting.station_light_brightness, lighting.station_light_color], user_text

    """ GOOGLE CALENDAR """
    if one_word_present_in_text(["schedule", "event"], user_text):
        now = datetime.now(ZoneInfo("Europe/Amsterdam")).isoformat(timespec="seconds")
        user_text += f"Generate a short event title. to_date and from_dates should be in RFC3339 timestamps, \
                        like this example. YYYY-MM-DDTHH:MM:SS±HH:MM. Right now, it is: {now}. If to_date is not mentioned by user, assume 1 hour after from_date"
        return [gcalendar.make_calendar_event], user_text

    """ TO DO: ADD TIMER TOOL """
    """ TO DO: ADD: WHAT TIME IS IT? 
    - Should add as special case right after speech-to-text parse/ """

    """ TO DO: ADD WHAT TIME DOES BUS 18 LEAVE? """

    # Perhaps, depending on the performance impact, add classification one-shot model to see whether or not tool is appplicable to user prompt
    # Or, whether an adequare prompt was skipped.  


    logging.info("No relevant tool found for this query.")
    return None, user_text

def execute_tool_calls(tool_calls):
    for tool_call in tool_calls:
        function_name = tool_call['function']['name']
        function_args = tool_call['function']['arguments']
        # In the case the model nested the arguments inside of an object, we unwrap.
        if "object" in function_args and isinstance(function_args["object"], dict):
            function_args = function_args["object"]
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

def one_word_present_in_text(words, text):
    tokens = re.findall(r'\b\w+\b', text.lower())  # Tokenize
    for token in tokens:
        if token in CANON:
            tokens.append(CANON[token])  # Add canonical forms to tokenizer
    for word in tokens:
        if word in words:
            return True
    return False

""" TO DO: MAKE ASYNC, AS WELL AS MAIN LOOP """
def warm_up_ollama_model():
    
    model=os.getenv("OLLAMA_MODEL_NAME")
    keep_alive=os.getenv("OLLAMA_KEEP_ALIVE")
    assert model is not None, "OLLAMA_MODEL_NAME environment variable not set."
    assert keep_alive is not None, "OLLAMA_KEEP_ALIVE environment variable not set."

    logging.info("Warming up Ollama model...")
    ollama.generate(model=model, keep_alive=keep_alive)
    logging.info("Herbie officially warmed up")

