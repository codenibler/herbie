from piper_tts import read_out_response, read_out_response_from_file
from toolbox import lighting
from toolbox import gcalendar
from toolbox import timer
from toolbox import music
from toolbox import volume
from toolbox import background_audio

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import random
import logging
import asyncio
import inspect
import ollama
import os
import re

ACK_TOOL_RESPONSES_DIR = Path(os.getenv("ACK_TOOL_RESPONSES_DIR", "herbie_responses/ack_tool"))
TOOL_COMPLETE_RESPONSES_DIR = Path(os.getenv("TOOL_COMPLETE_RESPONSES_DIR", "herbie_responses/tool_complete"))
SPECIAL_CASE_RESPONSES_DIR = Path(os.getenv("SPECIAL_CASE_RESPONSES_DIR", "herbie_responses/special_cases"))
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Amsterdam")

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
    "play_specific_song": music.play_specific_song,
    "stop_music": music.stop_music,
    "stop_background_playback": background_audio.stop_background_playback,
    "start_timer": timer.start_timer,
    "stop_timer": timer.stop_timer,
    "get_timer_remaining": timer.get_timer_remaining,
    "set_output_volume": volume.set_output_volume,

}
CANON = {
    "lights": "light",
}

TIME_QUERY_PATTERNS = (
    "what time is it",
    "whats the time",
    "what's the time",
    "tell me the time",
    "current time",
)
GENERIC_STOP_QUERY_PATTERNS = (
    "stop",
)
TIMER_STATUS_QUERY_PATTERNS = (
    "time left on timer",
    "time left on the timer",
    "time left on my timer",
    "time left on countdown",
    "time left on the countdown",
    "time remaining on the timer",
    "time remaining on timer",
    "time remaining on my timer",
    "time remaining on countdown",
    "time remaining on the countdown",
    "remaining time on the timer",
    "remaining time on timer",
    "remaining time on my timer",
    "remaining time on countdown",
    "remaining time on the countdown",
    "how much time is left on timer",
    "how much time is left on the timer",
    "how much time is left on my timer",
    "how much time is left on countdown",
    "how much time is left on the countdown",
    "how much time remains on timer",
    "how much time remains on the timer",
    "how much time remains on my timer",
    "how much time remains on countdown",
    "how much time remains on the countdown",
    "how long is left on timer",
    "how long is left on the timer",
    "how long is left on my timer",
    "how long is left on countdown",
    "how long is left on the countdown",
    "how long left on timer",
    "how long left on the timer",
    "how long left on my timer",
    "how long left on countdown",
    "how long left on the countdown",
    "when does the timer end",
    "when will the timer end",
    "when does the countdown end",
    "when will the countdown end",
)
BACKGROUND_AUDIO_STOP_PATTERNS = (
    "stop it",
    "stop that",
    "stop the music",
    "stop the song",
    "turn the speaker off",
    "turn speaker off",
    "stop the speaker",
    "mute the speaker",
    "stop the timer",
    "end the timer",
    "end timer",
    "cancel the timer",
    "cancel timer",
    "stop the countdown",
    "stop countdown",
    "end the countdown",
    "end countdown",
    "cancel the countdown",
    "cancel countdown",
    "stop the timer sound",
    "stop the alarm",
)

""" TO DO: ADD SOME SORT OF CONFIRMATION TTS WHEN TOOL CALLED. """
def ollama_query(user_text):
    # Determine through string matching if tool is usable.
    MODEL = os.getenv("OLLAMA_MODEL_NAME")
    assert MODEL is not None, "OLLAMA_MODEL_NAME environment variable not set."

    tool, user_text = determine_relevent_tool(user_text)  
    if tool is not None:
        logging.info(tool)
        if lighting.station_lights_freaky not in tool: # Special case, own response
            herbie_random_ack_response = random.choice(os.listdir(ACK_TOOL_RESPONSES_DIR))
            read_out_response_from_file(ACK_TOOL_RESPONSES_DIR / herbie_random_ack_response)
            logging.info(f"Tool ack response {herbie_random_ack_response}")
        response = ollama.chat(model=MODEL, messages=[{'role': 'user', 'content':user_text}], tools=tool)  
        logging.info(f"Selected tool for this query: {tool}")
        logging.info(f"Ollama response: {response['message']['content']}")
        if 'tool_calls' in response["message"]:
            clarification_message = execute_tool_calls(response['message']['tool_calls'])
            if clarification_message is not None:
                logging.info(f"Tool clarification requested: {clarification_message}")
                return clarification_message
    else:
        response = ollama.chat(model=MODEL, messages=[{'role': 'user', 'content':user_text}])  
    
    logging.info(f"Ollama response: {response['message']['content']}")
    return response['message']['content']

def normalize_user_text(text: str) -> str:
    return " ".join(re.findall(r"\b[\w']+\b", text.lower()))

def is_time_query(user_text: str) -> bool:
    normalized_text = normalize_user_text(user_text)
    return any(pattern in normalized_text for pattern in TIME_QUERY_PATTERNS)

def is_generic_stop_query(user_text: str) -> bool:
    normalized_text = normalize_user_text(user_text)
    return normalized_text in GENERIC_STOP_QUERY_PATTERNS

def build_time_query_response() -> str:
    current_time = datetime.now(ZoneInfo(APP_TIMEZONE))
    formatted_time = current_time.strftime("%I:%M %p")
    return f"It is {formatted_time}."

def is_timer_status_query(user_text: str) -> bool:
    normalized_text = normalize_user_text(user_text)
    return any(pattern in normalized_text for pattern in TIMER_STATUS_QUERY_PATTERNS)

def is_background_audio_stop_request(user_text: str) -> bool:
    normalized_text = normalize_user_text(user_text)
    if normalized_text in GENERIC_STOP_QUERY_PATTERNS:
        return True
    return any(pattern in normalized_text for pattern in BACKGROUND_AUDIO_STOP_PATTERNS)

def determine_relevent_tool(user_text):
    
    """ ALL LIGHTS """
    if (
        one_word_present_in_text(["everything", "every", "all"], user_text.lower())
        and one_word_present_in_text(["on", "off"], user_text.lower())
    ):
        return [lighting.turn_everything_off, lighting.turn_everything_on], user_text

    """ KITCHEN LIGHTING """
    if words_present_in_text(["kitchen", "on"], user_text.lower()):
        return [lighting.kitchen_light_on], user_text
    elif words_present_in_text(["kitchen", "off"], user_text.lower()):
        return [lighting.kitchen_light_off], user_text
    elif one_word_present_in_text(["kitchen"], user_text.lower()):
        return [lighting.kitchen_light_off], user_text 

    """ GENERIC STOP """
    if is_generic_stop_query(user_text):
        user_text += (
            " The user wants to stop any background music, timer countdown, or timer"
            " alarm audio. Call stop_background_playback."
        )
        return [background_audio.stop_background_playback], user_text

    """ MUSIC """ 
    if words_present_in_text(["stop", "music"], user_text.lower()) or words_present_in_text(["stop", "song"], user_text.lower()) or words_present_in_text(["stop", "playing"], user_text.lower()):
        return [music.stop_music], user_text
    if one_word_present_in_text(["bangers", "song", "music"], user_text.lower()):
        song_paths = [f"songs/{song}" for song in os.listdir("songs")]
        user_text += f"If user wants specific song choice, select from the following options: {song_paths}, and send the full path as the parameter. Otherwise, call play_random_songs with no parameters"
        return [music.play_random_songs, music.play_specific_song], user_text
    if words_present_in_text(["play"], user_text.lower()):
        song_paths = [f"songs/{song}" for song in os.listdir("songs")]
        user_text += f"If user wants specific song choice, select from the following options: {song_paths}, and send the full path as the parameter. Otherwise, call play_random_songs with no parameters"
        return [music.play_specific_song], user_text

    """ TIMER """
    if is_timer_status_query(user_text):
        user_text += (
            " The user wants to know how much time is left on the active timer."
            " Call get_timer_remaining."
        )
        return [timer.get_timer_remaining], user_text
    if words_present_in_text(["stop", "timer"], user_text.lower()) or words_present_in_text(["cancel", "timer"], user_text.lower()) or words_present_in_text(["end", "timer"], user_text.lower()):
        return [timer.stop_timer], user_text
    if one_word_present_in_text(["timer", "countdown"], user_text.lower()):
        user_text += (
            " If the user wants to start a timer, call start_timer with duration_seconds"
            " as a positive integer. Convert minutes or hours into total seconds before"
            " calling the tool. If the user wants to stop or cancel a timer, call"
            " stop_timer. If the user wants to know how much time is left on the active"
            " timer, call get_timer_remaining."
        )
        return [timer.start_timer, timer.stop_timer, timer.get_timer_remaining], user_text

    """ SPEAKER VOLUME """
    if one_word_present_in_text(["volume"], user_text.lower()):
        user_text += " If the user wants to change the speaker volume, call set_output_volume with volume_percent as an integer from 0 to 100."
        return [volume.set_output_volume], user_text

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
        read_out_response_from_file(SPECIAL_CASE_RESPONSES_DIR / "just_how_i_like_it.wav")
        return [lighting.station_lights_freaky], user_text 
    elif words_present_in_text(["station"], user_text.lower()):
        return [lighting.station_lights_on, lighting.station_lights_off, lighting.station_light_brightness, lighting.station_light_color], user_text

    """ GOOGLE CALENDAR """
    if one_word_present_in_text(["schedule", "event"], user_text):
        now = datetime.now(ZoneInfo(APP_TIMEZONE)).isoformat(timespec="seconds")
        user_text += f"Generate a short event title. to_date and from_dates should be in RFC3339 timestamps, \
                        like this example. YYYY-MM-DDTHH:MM:SS±HH:MM. Right now, it is: {now}. If to_date is not mentioned by user, assume 1 hour after from_date"
        return [gcalendar.make_calendar_event], user_text

    """ TO DO: ADD WHAT TIME DOES BUS 18 LEAVE? """

    # Perhaps, depending on the performance impact, add classification one-shot model to see whether or not tool is appplicable to user prompt
    # Or, whether an adequare prompt was skipped.  


    logging.info("No relevant tool found for this query.")
    return None, user_text

def validate_tool_call_arguments(function, function_args):
    if function_args is None:
        function_args = {}

    signature = inspect.signature(function)
    parameters = signature.parameters
    accepts_var_keyword = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    if accepts_var_keyword:
        sanitized_args = dict(function_args)
        stripped_args = {}
    else:
        allowed_names = {
            name
            for name, parameter in parameters.items()
            if parameter.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
        sanitized_args = {
            name: value for name, value in function_args.items() if name in allowed_names
        }
        stripped_args = {
            name: value for name, value in function_args.items() if name not in allowed_names
        }

    missing_required_args = [
        name
        for name, parameter in parameters.items()
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and parameter.default is inspect.Parameter.empty
        and name not in sanitized_args
    ]

    return sanitized_args, missing_required_args, stripped_args

def _humanize_parameter_name(parameter_name: str) -> str:
    return parameter_name.replace("_", " ")

def build_tool_clarification_message(function_name, missing_required_args, stripped_args):
    function_name_human = function_name.replace("_", " ")
    details = []

    if missing_required_args:
        missing_human = ", ".join(_humanize_parameter_name(arg) for arg in missing_required_args)
        details.append(f"I still need {missing_human}")

    if stripped_args:
        stripped_human = ", ".join(_humanize_parameter_name(arg) for arg in stripped_args.keys())
        details.append(f"I could not use {stripped_human}")

    if not details:
        return None

    return f"I need a bit more detail to {function_name_human}. {' '.join(details)}. Please try again with that information."

def execute_tool_calls(tool_calls):
    clarification_messages = []

    for tool_call in tool_calls:
        function_name = tool_call['function']['name']
        function_args = tool_call['function']['arguments']
        # In the case the model nested the arguments inside of an object, we unwrap.
        if "object" in function_args and isinstance(function_args["object"], dict):
            function_args = function_args["object"]
        if function_name in TOOL_MAP:
            sanitized_args, missing_required_args, stripped_args = validate_tool_call_arguments(
                TOOL_MAP[function_name], function_args
            )
            if stripped_args:
                logging.warning(
                    f"Stripping unsupported arguments for {function_name}: {stripped_args}"
                )
            if missing_required_args or stripped_args:
                logging.warning(
                    f"Missing required arguments for {function_name}: {missing_required_args}"
                )
                clarification_message = build_tool_clarification_message(
                    function_name,
                    missing_required_args,
                    stripped_args,
                )
                if clarification_message is not None:
                    clarification_messages.append(clarification_message)
                continue

            logging.info(f"Executing tool: {function_name}, with arguments: {sanitized_args}")
            if inspect.iscoroutinefunction(TOOL_MAP[function_name]):
                tool_response = asyncio.run(TOOL_MAP[function_name](**sanitized_args))  # Await if it's a coroutine
            else:   
                tool_response = TOOL_MAP[function_name](**sanitized_args)  # Execute the tool function with arguments
            logging.info(f"Tool response: {tool_response}")
            if tool_response is False:
                logging.info(
                    "Skipping tool completion response because %s reported failure.",
                    function_name,
                )
                continue
            if isinstance(tool_response, str):
                read_out_response(tool_response)
                continue

            read_out_response_from_file(
                TOOL_COMPLETE_RESPONSES_DIR / random.choice(os.listdir(TOOL_COMPLETE_RESPONSES_DIR))
            )
        else:
            logging.warning(f"Tool {function_name} not found in tool map.")
            clarification_messages.append(
                f"I could not run {function_name.replace('_', ' ')} because that tool is not available. Please try again."
            )

    if clarification_messages:
        return " ".join(clarification_messages)
    return None

def words_present_in_text(words, text):
    tokens = re.findall(r'\b\w+\b', text.lower())  # Tokenize
    for token in tokens:
        if token in CANON:
            tokens.append(CANON[token])  # Add canonical forms to tokenizer
    return all(word in tokens for word in words) 

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


async def warm_up_ollama_model_async():
    await asyncio.to_thread(warm_up_ollama_model)
