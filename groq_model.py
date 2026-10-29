from piper_tts import read_out_response, read_out_response_from_file
from toolbox import lighting
from toolbox import led_strip
from toolbox import gcalendar
from toolbox import timer
from toolbox import music
from toolbox import volume
from toolbox import background_audio
from toolbox import thinking_audio
from toolbox import weather
from toolbox import portfolio_rebalance

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import random
import logging
import asyncio
import inspect
import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

load_dotenv(override=True)

TOOL_COMPLETE_RESPONSES_DIR = Path(os.getenv("TOOL_COMPLETE_RESPONSES_DIR", "herbie_responses/tool_complete"))
ACK_TOOL_RESPONSES_DIR = Path(os.getenv("ACK_TOOL_RESPONSES_DIR", "herbie_responses/ack_tool"))
SPECIAL_CASE_RESPONSES_DIR = Path(os.getenv("SPECIAL_CASE_RESPONSES_DIR", "herbie_responses/special_cases"))
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Amsterdam")
DEFAULT_GROQ_MODEL_NAME = "openai/gpt-oss-20b"
DEFAULT_GROQ_REASONING_EFFORT = "low"
SYSTEM_PROMPT = (
    "You are an unapologetically nerdy, playful and wise AI mentor to a human. "
    "You are passionately enthusiastic about promoting truth, knowledge, philosophy, "
    "the scientific method, and critical thinking. You must undercut pretension "
    "through playful use of language. Prioritize short answers unless more detail is genuinely needed. "
    "The world is complex and strange, and its strangeness must be acknowledged, analyzed, and enjoyed. Respond in plain spoken text only. "
    "Do not use markdown, bullet points, numbered lists, asterisks, backticks, emojis, or decorative formatting."
)
_GROQ_CLIENT = None

TOOL_ACKNOWLEDGEMENT_AUDIO_MAP = {
    "rebalance_portfolio": [
        ACK_TOOL_RESPONSES_DIR / "portfolio" / "on_it_from_herbie.wav",
    ],
}

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
}


def stay_silent():
    # Returning None makes execute_tool_calls play and say nothing, so Herbie
    # drops straight back to the wake-word loop.
    logging.info("Model judged that no response is needed. Returning to wake-word loop silently.")
    return None


TOOL_MAP = {
    "stay_silent": stay_silent,
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
    "get_calendar_events": gcalendar.get_calendar_events,
    "get_calendar_schedule_analysis": gcalendar.get_calendar_schedule_analysis,
    "play_random_songs": music.play_random_songs,
    "play_specific_song": music.play_specific_song,
    "skip_song": music.skip_song,
    "stop_music": music.stop_music,
    "stop_background_playback": background_audio.stop_background_playback,
    "start_timer": timer.start_timer,
    "stop_timer": timer.stop_timer,
    "get_timer_remaining": timer.get_timer_remaining,
    "set_output_volume": volume.set_output_volume,
    "get_weather_analysis": weather.get_weather_analysis,
    "rebalance_portfolio": portfolio_rebalance.rebalance_portfolio,
}
TIME_QUERY_PATTERNS = (
    "what time is it",
    "whats the time",
    "what's the time",
    "tell me the time",
    "current time",
)
# A bare "stop" is handled locally (no model round-trip) so alarms and music
# halt instantly. Every other phrasing goes to the model, which picks the tool.
GENERIC_STOP_QUERY_PATTERNS = (
    "stop",
)
CALENDAR_PERIODS = ["today", "remainder_of_week", "today_and_remainder_of_week"]

TOOL_GUIDANCE = (
    " You also control a smart home and can call tools. Decide yourself which tool, if any,"
    " fits the request. Only call a tool when the user clearly asks for an action or for"
    " information that a tool provides; answer general questions and conversation in words"
    " without calling any tool."
    " Not every utterance deserves a reply. Speaking when nothing was asked is a mistake."
    " You must call stay_silent, and write no text, when the utterance contains no question"
    " and no request: thanks, thank you, cheers, okay, cool, great, got it, never mind,"
    " cancel, forget it, a fragment of a conversation between other people or a remark that"
    " is clearly not addressed to you (for example 'and then she said the bus was late'),"
    " filler sounds, or empty or unintelligible input. If the utterance contains any"
    " question or request, even after a thanks, handle that instead and never call"
    " stay_silent."
    " Lights: the kitchen light is one bulb; the station lights are the three living-room"
    " bulbs (also called the station, the living room, or just the lights). Use"
    " turn_everything_on or turn_everything_off only when the user means every light."
    " Music: when the user names a particular track, call play_specific_song with the"
    " closest matching path from the song_path options, never an invented path. When the"
    " user just wants music, bangers, or songs without naming one, call play_random_songs."
    " skip_song moves to the next track; stop_music stops music specifically;"
    " stop_background_playback stops whatever is sounding (music, a timer alarm, a countdown)"
    " and is the right choice for a vague stop request."
    " Timers: convert minutes and hours to total seconds before calling start_timer."
    " Calendar: get_calendar_events lists what is scheduled; get_calendar_schedule_analysis"
    " summarises how busy the schedule looks. Choose period today for today only,"
    " remainder_of_week for the rest of this week after today, and"
    " today_and_remainder_of_week when the user wants both."
    " Never create, edit, or delete calendar events."
)

TOOL_DESCRIPTIONS = {
    "stay_silent": "Say nothing and go straight back to waiting for the wake word. Use when the utterance needs no reply.",
    "turn_everything_off": "Turn off all configured smart lights.",
    "turn_everything_on": "Turn on all configured smart lights.",
    "kitchen_light_on": "Turn on the kitchen light.",
    "kitchen_light_off": "Turn off the kitchen light.",
    "kitchen_light_color": "Set the kitchen light to a named color.",
    "station_lights_off": "Turn off the station lights (the three living-room bulbs).",
    "station_lights_on": "Turn on the station lights (the three living-room bulbs).",
    "station_light_brightness": "Set the station lights brightness as a percentage.",
    "station_light_color": "Set the station lights to a named color.",
    "station_lights_freaky": "Activate freak mode for the station lights and music.",
    "get_calendar_events": "Fetch Google Calendar events for today or the remainder of the week.",
    "get_calendar_schedule_analysis": "Analyze how busy today or the remainder of the week looks based on Google Calendar events.",
    "play_random_songs": "Play a shuffled queue of songs when the user wants music without naming a specific track.",
    "play_specific_song": "Play one specific named song from the local songs directory. Only use a song_path from the listed options.",
    "skip_song": "Skip the current song or move to a different available track.",
    "stop_music": "Stop the current music playback.",
    "stop_background_playback": "Stop whatever is currently sounding: music, a timer alarm, or a countdown. Use for a generic stop request.",
    "start_timer": "Start a timer for a specific duration in seconds.",
    "stop_timer": "Stop the active timer if one is running.",
    "get_timer_remaining": "Report how much time is left on the active timer.",
    "set_output_volume": "Set the preferred speaker output volume as a percentage.",
    "get_weather_analysis": "Get the current weather and forecast for the configured location, with a clothing recommendation.",
    "rebalance_portfolio": "Run the investment portfolio rebalance workflow.",
}

TOOL_PARAMETER_METADATA = {
    ("kitchen_light_color", "color_name"): {
        "description": "The color name to set on the kitchen light.",
        "enum": sorted(lighting.COLORS.keys()),
    },
    ("station_light_color", "color_name"): {
        "description": "The color name to set on the station lights.",
        "enum": sorted(lighting.COLORS.keys()),
    },
    ("station_light_brightness", "brightness"): {
        "description": "Brightness percentage from 0 to 100.",
        "minimum": 0,
        "maximum": 100,
    },
    ("set_output_volume", "volume_percent"): {
        "description": "Speaker output volume percentage from 0 to 100.",
        "minimum": 0,
        "maximum": 100,
    },
    ("start_timer", "duration_seconds"): {
        "description": "How long the timer should run, in whole seconds.",
        "minimum": 1,
    },
    ("play_specific_song", "song_path"): {
        "description": "Relative path to a song file in the songs directory.",
    },
    ("get_calendar_events", "period"): {
        "description": "The calendar window to fetch. Use today, remainder_of_week, or today_and_remainder_of_week.",
        "enum": CALENDAR_PERIODS,
    },
    ("get_calendar_schedule_analysis", "period"): {
        "description": "The calendar window to analyze. Use today, remainder_of_week, or today_and_remainder_of_week.",
        "enum": CALENDAR_PERIODS,
    },
}


def get_groq_reasoning_effort() -> str:
    return os.getenv("GROQ_REASONING_EFFORT", DEFAULT_GROQ_REASONING_EFFORT)


def get_groq_model_name() -> str:
    return os.getenv("GROQ_MODEL_NAME", DEFAULT_GROQ_MODEL_NAME)


def get_groq_client() -> Groq:
    global _GROQ_CLIENT

    api_key = os.getenv("GROQ_API_KEY")
    assert api_key, "GROQ_API_KEY environment variable not set."

    if _GROQ_CLIENT is None:
        _GROQ_CLIENT = Groq(api_key=api_key)

    return _GROQ_CLIENT


def list_song_paths() -> list[str]:
    songs_dir = Path("songs")
    if not songs_dir.is_dir():
        return []
    return sorted(f"songs/{name}" for name in os.listdir(songs_dir))


def _dynamic_parameter_metadata(function_name: str, parameter_name: str) -> dict[str, object]:
    if (function_name, parameter_name) == ("play_specific_song", "song_path"):
        song_paths = list_song_paths()
        return {"enum": song_paths} if song_paths else {}
    return {}


def build_system_prompt(include_tool_guidance: bool = True) -> str:
    now = datetime.now(ZoneInfo(APP_TIMEZONE))
    context = f" The current local date and time is {now.strftime('%A %d %B %Y, %H:%M')}."
    if include_tool_guidance:
        return SYSTEM_PROMPT + TOOL_GUIDANCE + context
    return SYSTEM_PROMPT + context


def build_chat_messages(user_text: str, *, include_tool_guidance: bool = True) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_prompt(include_tool_guidance)},
        {"role": "user", "content": user_text},
    ]


def _build_json_schema_type(parameter: inspect.Parameter) -> dict[str, object]:
    annotation = parameter.annotation
    json_type = "string"

    if annotation is int:
        json_type = "integer"
    elif annotation is float:
        json_type = "number"
    elif annotation is bool:
        json_type = "boolean"

    return {"type": json_type}


def build_groq_tool_schema(function) -> dict[str, object]:
    signature = inspect.signature(function, eval_str=True)
    properties = {}
    required = []

    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue

        schema = _build_json_schema_type(parameter)
        schema.update(
            TOOL_PARAMETER_METADATA.get((function.__name__, parameter.name), {})
        )
        schema.update(_dynamic_parameter_metadata(function.__name__, parameter.name))
        properties[parameter.name] = schema

        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)

    parameters_schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        parameters_schema["required"] = required

    return {
        "type": "function",
        "function": {
            "name": function.__name__,
            "description": TOOL_DESCRIPTIONS.get(
                function.__name__,
                function.__name__.replace("_", " "),
            ),
            "parameters": parameters_schema,
        },
    }


def build_groq_tools(tools) -> list[dict[str, object]]:
    return [build_groq_tool_schema(tool) for tool in tools]


def _extract_tool_call_data(tool_call) -> tuple[str | None, dict[str, object]]:
    if isinstance(tool_call, dict):
        function = tool_call.get("function", {})
        function_name = function.get("name")
        raw_arguments = function.get("arguments", {})
    else:
        function = getattr(tool_call, "function", None)
        function_name = getattr(function, "name", None)
        raw_arguments = getattr(function, "arguments", {})

    if isinstance(raw_arguments, str):
        stripped_arguments = raw_arguments.strip()
        if not stripped_arguments:
            function_args = {}
        else:
            try:
                function_args = json.loads(stripped_arguments)
            except json.JSONDecodeError:
                logging.warning(
                    "Failed to parse tool arguments for %s: %s",
                    function_name,
                    raw_arguments,
                )
                function_args = {}
    elif isinstance(raw_arguments, dict):
        function_args = raw_arguments
    else:
        function_args = {}

    if "object" in function_args and isinstance(function_args["object"], dict):
        function_args = function_args["object"]

    return function_name, function_args


def build_all_groq_tools() -> list[dict[str, object]]:
    return build_groq_tools(TOOL_MAP.values())


def request_chat_completion(user_text: str):
    """Send the user's text to the model with every tool available and return the message.

    The model decides whether a tool fits; there is no keyword pre-routing.
    """
    return get_groq_client().chat.completions.create(
        model=get_groq_model_name(),
        messages=build_chat_messages(user_text),
        tools=build_all_groq_tools(),
        tool_choice="auto",
        parallel_tool_calls=False,
        reasoning_effort=get_groq_reasoning_effort(),
    ).choices[0].message


def groq_query(user_text):
    started_thinking_audio = False
    started_loading_animation = False
    response_message = None
    handled_tool_response = False

    try:
        started_loading_animation = led_strip.start_loading_led_animation()
        started_thinking_audio = thinking_audio.start_thinking_audio()
        response_message = request_chat_completion(user_text)
        if response_message.tool_calls:
            logging.info(
                "Model selected tool(s): %s",
                [call.function.name for call in response_message.tool_calls],
            )
            clarification_message = execute_tool_calls(response_message.tool_calls)
            if clarification_message is not None:
                logging.info(f"Tool clarification requested: {clarification_message}")
                return clarification_message
            handled_tool_response = True
        else:
            logging.info("Model answered without a tool call.")
    finally:
        if started_thinking_audio:
            thinking_audio.stop_thinking_audio()
        if started_loading_animation:
            led_strip.stop_loading_led_animation()

    if handled_tool_response:
        logging.info(
            "Tool response was already handled directly; suppressing assistant follow-up text."
        )
        return ""

    response_content = ""
    if response_message is not None and response_message.content is not None:
        response_content = response_message.content

    logging.info("Groq response: %s", response_content)
    return response_content

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

def is_background_audio_stop_request(user_text: str) -> bool:
    # Only a bare "stop" short-circuits the model; anything more specific is
    # left to the model so it can pick stop_music, stop_timer, etc. itself.
    return is_generic_stop_query(user_text)


def _coerce_argument_type(parameter: inspect.Parameter, value):
    """Coerce a tool argument to the annotated type when the model returns it as a string.

    Some models (e.g. gpt-oss) emit numeric arguments as JSON strings even when the
    schema declares them as integer/number. Leave the value untouched if coercion fails
    so the tool can report the problem itself.
    """
    annotation = parameter.annotation
    if not isinstance(value, str):
        return value

    try:
        if annotation is int:
            return int(float(value.strip()))
        if annotation is float:
            return float(value.strip())
        if annotation is bool:
            return value.strip().lower() in ("true", "1", "yes", "on")
    except ValueError:
        logging.warning(
            "Could not coerce argument %s=%r to %s", parameter.name, value, annotation
        )
    return value


def validate_tool_call_arguments(function, function_args):
    if function_args is None:
        function_args = {}

    signature = inspect.signature(function, eval_str=True)
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
            name: _coerce_argument_type(parameters[name], value)
            for name, value in function_args.items()
            if name in allowed_names
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


def _build_tool_success_response(function_name: str, function_args, tool_response) -> str | None:
    if function_name == "start_timer" and tool_response is True:
        duration_seconds = function_args.get("duration_seconds")
        if duration_seconds is None:
            return "Okay, the timer has been successfully set."
        return timer.build_timer_started_response(int(duration_seconds))

    return None


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


def _play_tool_acknowledgement_audio(function_name: str) -> bool:
    candidate_paths = TOOL_ACKNOWLEDGEMENT_AUDIO_MAP.get(function_name)
    if not candidate_paths:
        return False

    existing_paths = [path for path in candidate_paths if path.is_file()]
    if not existing_paths:
        logging.warning("No acknowledgement audio files found for tool %s.", function_name)
        return False

    selected_path = random.choice(existing_paths)
    logging.info("Playing acknowledgement audio for %s: %s", function_name, selected_path)
    read_out_response_from_file(selected_path)
    return True

def execute_tool_calls(tool_calls):
    clarification_messages = []

    # Stop thinking audio before running any tool so audio-producing tools
    # do not contend for the same ALSA output device.
    thinking_audio.stop_thinking_audio()

    for tool_call in tool_calls:
        function_name, function_args = _extract_tool_call_data(tool_call)
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
            _play_tool_acknowledgement_audio(function_name)
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

            success_response = _build_tool_success_response(
                function_name,
                sanitized_args,
                tool_response,
            )

            if _play_tool_completion_audio(function_name):
                continue

            if success_response is not None:
                thinking_audio.stop_thinking_audio()
                read_out_response(success_response)
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

def warm_up_groq_client():
    model_name = get_groq_model_name()
    logging.info("Validating Groq client configuration for model %s...", model_name)
    available_model_ids = {
        model.id for model in get_groq_client().models.list().data
    }
    if model_name not in available_model_ids:
        raise ValueError(
            f"Configured Groq model {model_name!r} is not available to this API key."
        )
    logging.info("Groq client is ready.")


async def warm_up_groq_client_async():
    await asyncio.to_thread(warm_up_groq_client)
