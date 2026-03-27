from piper_tts import read_out_response, read_out_response_from_file
from toolbox import lighting
from toolbox import led_strip
from toolbox import gcalendar
from toolbox import timer
from toolbox import music
from toolbox import volume
from toolbox import background_audio
from toolbox import thinking_audio

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

TOOL_COMPLETION_AUDIO_MAP = {
    "turn_everything_off": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "all_off.wav",
    ],
    "turn_everything_on": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "everythings_on.wav",
    ],
    "kitchen_light_on": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "done_kitchens_on.wav",
    ],
    "kitchen_light_off": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "kitchens_off.wav",
    ],
    "kitchen_light_color": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "done_kitchens_on.wav",
    ],
    "station_lights_on": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "station_lights_on.wav",
    ],
    "station_lights_off": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "station_lights_off.wav",
    ],
    "station_light_brightness": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "station_lights_on.wav",
    ],
    "station_light_color": [
        TOOL_COMPLETE_RESPONSES_DIR / "lights" / "station_lights_on.wav",
    ],
    "station_lights_freaky": [
        SPECIAL_CASE_RESPONSES_DIR / "just_how_i_like_it.wav",
    ],
    "play_random_songs": [
        TOOL_COMPLETE_RESPONSES_DIR / "music" / "on_shuffle.wav",
    ],
    "play_specific_song": [
        TOOL_COMPLETE_RESPONSES_DIR / "music" / "heres_your_song.wav",
    ],
    "skip_song": [
        TOOL_COMPLETE_RESPONSES_DIR / "music" / "playing_now.wav",
    ],
    "stop_music": [
        TOOL_COMPLETE_RESPONSES_DIR / "music" / "stopped.wav",
    ],
    "stop_background_playback": [
        TOOL_COMPLETE_RESPONSES_DIR / "music" / "stopped.wav",
        TOOL_COMPLETE_RESPONSES_DIR / "timer" / "timer_stopped.wav",
        TOOL_COMPLETE_RESPONSES_DIR / "timer" / "timers_cancelled.wav",
    ],
    "start_timer": [
        TOOL_COMPLETE_RESPONSES_DIR / "timer" / "timers_set.wav",
    ],
    "stop_timer": [
        TOOL_COMPLETE_RESPONSES_DIR / "timer" / "timer_stopped.wav",
        TOOL_COMPLETE_RESPONSES_DIR / "timer" / "timers_cancelled.wav",
    ],
    "set_output_volume": [
        TOOL_COMPLETE_RESPONSES_DIR / "volume" / "volume_set.wav",
        TOOL_COMPLETE_RESPONSES_DIR / "volume" / "done.wav",
    ],
    "make_calendar_event": [
        TOOL_COMPLETE_RESPONSES_DIR / "calendar" / "events_in.wav",
        TOOL_COMPLETE_RESPONSES_DIR / "calendar" / "added_to_your_calendar.wav",
        TOOL_COMPLETE_RESPONSES_DIR / "calendar" / "done_its_on_the_schedule.wav",
    ],
}

TOOL_MAP = {
    "turn_everything_off": lighting.turn_everything_off,
    "turn_everything_on": lighting.turn_everything_on,
    "kitchen_light_on": lighting.kitchen_light_on,
    "kitchen_light_off": lighting.kitchen_light_off,
    "kitchen_light_color": lighting.kitchen_light_color,
    "station_lights_off": lighting.station_lights_off,
    "station_lights_on": lighting.station_lights_on, 
    "station_light_brightness": lighting.station_light_brightness,
    "station_light_color": lighting.station_light_color,
    "station_lights_freaky": lighting.station_lights_freaky,
    "make_calendar_event": gcalendar.make_calendar_event,
    "play_random_songs": music.play_random_songs,
    "play_specific_song": music.play_specific_song,
    "skip_song": music.skip_song,
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

def ollama_query(user_text):
    # Determine through string matching if tool is usable.
    MODEL = os.getenv("OLLAMA_MODEL_NAME")
    assert MODEL is not None, "OLLAMA_MODEL_NAME environment variable not set."

    tool, user_text = determine_relevent_tool(user_text)
    started_thinking_audio = False
    started_loading_animation = False

    try:
        if tool is not None:
            logging.info(tool)
            if lighting.station_lights_freaky not in tool: # Special case, own response
                herbie_random_ack_response = random.choice(os.listdir(ACK_TOOL_RESPONSES_DIR))
                read_out_response_from_file(ACK_TOOL_RESPONSES_DIR / herbie_random_ack_response)
                logging.info(f"Tool ack response {herbie_random_ack_response}")

            started_loading_animation = led_strip.start_loading_led_animation()
            started_thinking_audio = thinking_audio.start_thinking_audio()
            response = ollama.chat(
                model=MODEL,
                messages=[{'role': 'user', 'content': user_text}],
                tools=tool,
            )
            logging.info(f"Selected tool for this query: {tool}")
            logging.info(f"Ollama response: {response['message']['content']}")
            if 'tool_calls' in response["message"]:
                clarification_message = execute_tool_calls(response['message']['tool_calls'])
                if clarification_message is not None:
                    logging.info(f"Tool clarification requested: {clarification_message}")
                    return clarification_message
        else:
            started_loading_animation = led_strip.start_loading_led_animation()
            started_thinking_audio = thinking_audio.start_thinking_audio()
            response = ollama.chat(model=MODEL, messages=[{'role': 'user', 'content': user_text}])
    finally:
        if started_thinking_audio:
            thinking_audio.stop_thinking_audio()
        if started_loading_animation:
            led_strip.stop_loading_led_animation()
    
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


def _build_song_tool_instruction() -> str:
    song_paths = [f"songs/{song}" for song in os.listdir("songs")]
    return (
        " If the user wants a specific song, call play_specific_song using exactly one"
        f" of these relative paths as song_path: {song_paths}."
        " Do not invent absolute placeholder paths like /path/to/...."
        " If the user does not specify a particular track, call play_random_songs."
    )

def determine_relevent_tool(user_text):
    normalized_user_text = normalize_user_text(user_text)
    
    if (
        one_word_present_in_text(["everything", "every", "all"], user_text.lower())
        and one_word_present_in_text(["on", "off"], user_text.lower())
    ):
        user_text += (
            " If the user wants all lights on, call turn_everything_on."
            " If the user wants all lights off, call turn_everything_off."
        )
        return [lighting.turn_everything_off, lighting.turn_everything_on], user_text

    if one_word_present_in_text(["kitchen"], user_text.lower()):
        user_text += (
            " If the user wants the kitchen light on, call kitchen_light_on."
            " If the user wants the kitchen light off, call kitchen_light_off."
            f" If the user wants to change the kitchen light color, call kitchen_light_color."
            f" The valid colors are: {sorted(list(lighting.COLORS.keys()))}."
        )
        return [
            lighting.kitchen_light_on,
            lighting.kitchen_light_off,
            lighting.kitchen_light_color,
        ], user_text

    if is_generic_stop_query(user_text):
        user_text += (
            " The user wants to stop any background music, timer countdown, or timer"
            " alarm audio. Call stop_background_playback."
        )
        return [background_audio.stop_background_playback], user_text

    if (
        normalized_user_text in {
            "skip",
            "skip please",
            "skip it",
            "skip this",
            "skip song",
            "skip this song",
            "skip track",
            "skip this track",
            "next",
            "next song",
            "next track",
        }
        or words_present_in_text(["skip", "song"], user_text.lower())
        or words_present_in_text(["next", "song"], user_text.lower())
    ):
        return [music.skip_song], user_text
    if words_present_in_text(["stop", "music"], user_text.lower()) or words_present_in_text(["stop", "song"], user_text.lower()) or words_present_in_text(["stop", "playing"], user_text.lower()):
        return [music.stop_music], user_text
    if one_word_present_in_text(["bangers", "song", "music"], user_text.lower()):
        user_text += _build_song_tool_instruction()
        return [music.play_random_songs, music.play_specific_song], user_text
    if words_present_in_text(["play"], user_text.lower()):
        user_text += _build_song_tool_instruction()
        return [music.play_specific_song], user_text

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

    if one_word_present_in_text(["volume"], user_text.lower()):
        user_text += " If the user wants to change the speaker volume, call set_output_volume with volume_percent as an integer from 0 to 100."
        return [volume.set_output_volume], user_text

    if words_present_in_text(["freaky"], user_text.lower()):
        user_text += "Use the station_lights_freaky tool"
        return [lighting.station_lights_freaky], user_text 
    elif words_present_in_text(["station"], user_text.lower()):
        user_text += (
            "Choose the tool most fitting to the request from the following. In the case that the user wishes to change the station light colors," \
            f"the valid colors are: {sorted(list(lighting.COLORS.keys()))}."
        )
        return [
            lighting.station_lights_on,
            lighting.station_lights_off,
            lighting.station_light_brightness,
            lighting.station_light_color,
        ], user_text

    if one_word_present_in_text(["schedule", "event"], user_text):
        now = datetime.now(ZoneInfo(APP_TIMEZONE)).isoformat(timespec="seconds")
        user_text += f"Generate a short event title. to_date and from_dates should be in RFC3339 timestamps, \
                        like this example. YYYY-MM-DDTHH:MM:SS±HH:MM. Right now, it is: {now}. If to_date is not mentioned by user, assume 1 hour after from_date"
        return [gcalendar.make_calendar_event], user_text

    # TO DO: Benchmark with functiongemma as a tool classifier. 
    # TO DO: Fix broken Calendar tool 

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


def _should_read_dynamic_tool_response(function_name: str, tool_response) -> bool:
    if not isinstance(tool_response, str):
        return False

    if function_name == "get_timer_remaining":
        return True

    normalized_response = tool_response.lower()

    if function_name == "stop_timer":
        return "no timer running" in normalized_response or "nothing is playing" in normalized_response

    if function_name == "stop_background_playback":
        return "nothing is playing" in normalized_response

    if function_name == "skip_song":
        return (
            "nothing is playing" in normalized_response
            or "no other song available" in normalized_response
        )

    return function_name not in TOOL_COMPLETION_AUDIO_MAP


def _play_tool_completion_audio(function_name: str) -> bool:
    thinking_audio.stop_thinking_audio()

    if music.MUSIC_MANAGER.status()["is_playing"]:
        logging.info(
            "Skipping completion audio for %s because background music is active.",
            function_name,
        )
        return False

    candidate_paths = TOOL_COMPLETION_AUDIO_MAP.get(function_name)
    if not candidate_paths:
        return False

    existing_paths = [path for path in candidate_paths if path.is_file()]
    if not existing_paths:
        logging.warning("No completion audio files found for tool %s.", function_name)
        return False

    selected_path = random.choice(existing_paths)
    logging.info("Playing completion audio for %s: %s", function_name, selected_path)
    read_out_response_from_file(selected_path)
    return True

def execute_tool_calls(tool_calls):
    clarification_messages = []

    # Stop thinking audio before running any tool so audio-producing tools
    # do not contend for the same ALSA output device.
    thinking_audio.stop_thinking_audio()

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

            if _should_read_dynamic_tool_response(function_name, tool_response):
                thinking_audio.stop_thinking_audio()
                read_out_response(tool_response)
                continue

            if _play_tool_completion_audio(function_name):
                continue

            if isinstance(tool_response, str):
                thinking_audio.stop_thinking_audio()
                read_out_response(tool_response)
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
