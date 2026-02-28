from toolbox import tool_functions
import datetime as dt
import logging
import asyncio
import inspect
import ollama
import json
import os

def ollama_query(user_text):
    """ TO DO: FIND BETTER WAY TO STORE THESE """
    tool_map = {
        "kitchen_light_on": tool_functions.kitchen_light_on,
        "kitchen_light_off": tool_functions.kitchen_light_off,
        "station_lights_off": tool_functions.station_lights_off,
        "station_lights_on": tool_functions.station_lights_on
    }

    # Query the Ollama model with the user's text input
    model = os.getenv("OLLAMA_MODEL_NAME")
    tool = determine_relevent_tool(user_text)  # Placeholder for tool selection logic
    if tool is not None:
        response = ollama.chat(model=model, messages=[{'role': 'user', 'content':user_text}], tools=[tool])  
        logging.info(f"Selected tool for this query: {tool}")
        logging.info(f"Ollama response: {response['message']['content']}")
        execute_tool_calls(response['message']['tool_calls'], tool_map)
    else:
        response = ollama.chat(model=model, messages=[{'role': 'user', 'content':user_text}])  
    
    logging.info(f"Ollama response: {response['message']['content']}")
    logging.info(f"Ollama response tool_calls: {response['message']['tool_calls']}")
    return response['message']['content']

def determine_relevent_tool(user_text):
    # Keyword match potential toosl to avoid slow model. 
    """ KITCHEN LIGHTING """
    if words_present_in_text(["kitchen", "light", "on"], user_text.lower()):
        return tool_functions.kitchen_light_on
    elif words_present_in_text(["kitchen", "light", "off"], user_text.lower()):
        return tool_functions.kitchen_light_off

    """ LIVING ROOM LIGHTING """
    if words_present_in_text(["station", "lights", "on"], user_text.lower()):
        return tool_functions.station_lights_on
    elif words_present_in_text(["station", "lights", "off"], user_text.lower()):
        return tool_functions.station_lights_off

    """ TO DO: ADD GOOGLE CALENDAR SCHEDULER TOOL """

    logging.info("No relevant tool found for this query.")
    return None

def execute_tool_calls(tool_calls, tool_map):
    for tool_call in tool_calls:
        function_name = tool_call['function']['name']
        function_args = tool_call['function']['arguments']
        if function_name in tool_map:
            logging.info(f"Executing tool: {function_name}, with arguments: {function_args}")
            if inspect.iscoroutinefunction(tool_map[function_name]):
                tool_response = asyncio.run(tool_map[function_name](**function_args))  # Await if it's a coroutine
            else:   
                tool_response = tool_map[function_name](**function_args)  # Execute the tool function with arguments
            logging.info(f"Tool response: {tool_response}")
        else:
            logging.warning(f"Tool {function_name} not found in tool map.")

def words_present_in_text(words, text):
    return all(word in text for word in words) # Truthy if all present

""" TO DO: MAKE ASYNC, AS WELL AS MAIN LOOP """
def warm_up_ollama_model():
    
    model=os.getenv("OLLAMA_MODEL_NAME")
    keep_alive=os.getenv("OLLAMA_KEEP_ALIVE")
    assert model is not None, "OLLAMA_MODEL_NAME environment variable not set."
    assert keep_alive is not None, "OLLAMA_KEEP_ALIVE environment variable not set."

    logging.info("Warming up Ollama model...")
    ollama.generate(model=model, keep_alive=keep_alive)
    logging.info("Herbie officially warmed up")

