from __future__ import annotations

from pywizlight import wizlight, PilotBuilder
from pathlib import Path

import asyncio
import logging
import os
DEFAULT_LIGHT_BRIGHTNESS = int(os.getenv("DEFAULT_LIGHT_BRIGHTNESS", 128))
LIGHT_STATE_SETTLE_SECONDS = float(os.getenv("LIGHT_STATE_SETTLE_SECONDS", 1.5))
FREAK_MODE_SONG_PATH = Path("songs/careless_whisper.wav")
LIGHT_TURN_ON_FAILURE_MESSAGE = (
    "Turning on the light failed. Check if the light switch is off, and I'll try again"
)


async def return_light_turn_on_failure(log_message: str, error: Exception | None = None) -> bool:
    from piper_tts import read_out_response

    if error is None:
        logging.warning(log_message)
    else:
        logging.warning("%s Error: %s", log_message, error)
    await asyncio.to_thread(read_out_response, LIGHT_TURN_ON_FAILURE_MESSAGE)
    return False


async def wait_for_light_state_settle() -> None:
    if LIGHT_STATE_SETTLE_SECONDS <= 0:
        return
    await asyncio.sleep(LIGHT_STATE_SETTLE_SECONDS)


def light_is_on(state) -> bool:
    return state is not None and state.get_state() is True


def light_is_off(state) -> bool:
    return state is not None and state.get_state() is False

async def kitchen_light_on():
    # Turn on the kitchen light. Requires no parameters.
    KBULB_IP = os.getenv("KITCHEN_BULB_IP")
    assert KBULB_IP is not None, "KBULB_IP environment variable not set."

    logging.info(f"Turning on kitchen light at IP: {KBULB_IP}")
    light = wizlight(KBULB_IP)
    try:
        await light.turn_on(PilotBuilder(brightness=DEFAULT_LIGHT_BRIGHTNESS))
        await wait_for_light_state_settle()
        state = await light.updateState()  # Update state to ensure command was sent

        if light_is_on(state):
            logging.info("Kitchen light turned on successfully.")
            return True

        return await return_light_turn_on_failure(
            "Failed to turn on kitchen light."
        )
    except Exception as error:
        return await return_light_turn_on_failure("Failed to turn on kitchen light.", error)
    finally:
        await light.async_close()

async def kitchen_light_off():
    # Turn off the kitchen light. Requires no parameters.
    KBULB_IP = os.getenv("KBULB_IP")
    assert KBULB_IP is not None, "KBULB_IP environment variable not set."

    logging.info(f"Turning off kitchen light at IP: {KBULB_IP}")
    light = wizlight(KBULB_IP)
    try:
        await light.turn_off()
        await wait_for_light_state_settle()
        state = await light.updateState()  # Update state to ensure command was sent

        if light_is_off(state):
            logging.info("Kitchen light turned off successfully.")
            return True
        
        logging.warning("Failed to turn off kitchen light.")
        return False
    finally:
        await light.async_close()

async def station_lights_off():
    # Turn off the kitchen light. Requires no parameters.
    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    BULB3_IP = os.getenv("BULB3_IP") 

    assert BULB1_IP and BULB2_IP and BULB3_IP, "BULB1, 2, and 3 IP environment variables must be set."
    logging.info(f"Turning off living room lights at IPs: {BULB1_IP}, {BULB2_IP}, {BULB3_IP}")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)
    light3 = wizlight(BULB3_IP)
    try:
        await light1.turn_off()
        await light2.turn_off()
        await light3.turn_off()
        await wait_for_light_state_settle()
        state1 = await light1.updateState() 
        state2 = await light2.updateState()  
        state3 = await light3.updateState()

        if light_is_off(state1) and light_is_off(state2) and light_is_off(state3):
            logging.info("Living room lights turned off successfully.")
            return True
        
        logging.warning("Failed to turn off living room lights.")
        return False
    finally:
        await light1.async_close()
        await light2.async_close()
        await light3.async_close()

async def station_lights_on():
    # Turn on the living room lights. Requires no parameters.
    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    BULB3_IP = os.getenv("BULB3_IP") 

    assert BULB1_IP and BULB2_IP and BULB3_IP, "BULB1, 2, and 3 IP environment variables must be set."
    logging.info(f"Turning on living room lights at IPs: {BULB1_IP}, {BULB2_IP}, {BULB3_IP}")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)
    light3 = wizlight(BULB3_IP)
    try:
        await light1.turn_on(PilotBuilder(brightness=DEFAULT_LIGHT_BRIGHTNESS))
        await light2.turn_on(PilotBuilder(brightness=DEFAULT_LIGHT_BRIGHTNESS))
        await light3.turn_on(PilotBuilder(brightness=DEFAULT_LIGHT_BRIGHTNESS))
        await wait_for_light_state_settle()
        state1 = await light1.updateState() 
        state2 = await light2.updateState()  
        state3 = await light3.updateState()

        if (
            light_is_on(state1)
            and light_is_on(state2)
            and light_is_on(state3)
        ):
            logging.info("Living room lights turned on successfully.")
            return True

        return await return_light_turn_on_failure("Failed to turn on living room lights.")
    except Exception as error:
        return await return_light_turn_on_failure("Failed to turn on living room lights.", error)
    finally:
        await light1.async_close()
        await light2.async_close()
        await light3.async_close()

async def station_light_brightness(brightness: int):
    # Turn on the living room lights with a specific brightness %. Requires brightness parameter.
    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    BULB3_IP = os.getenv("BULB3_IP") 

    assert BULB1_IP and BULB2_IP and BULB3_IP, "BULB1, 2, and 3 IP environment variables must be set."
    logging.info(f"Changing brightness to {brightness}%: {BULB1_IP}, {BULB2_IP}, {BULB3_IP}")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)
    light3 = wizlight(BULB3_IP)
    try:
        brightness_value = int((brightness / 100) * 255)  # Convert percentage to 0-255 scale
        await light1.turn_on(PilotBuilder(brightness=brightness_value))
        await light2.turn_on(PilotBuilder(brightness=brightness_value))
        await light3.turn_on(PilotBuilder(brightness=brightness_value))
        await wait_for_light_state_settle()
        state1 = await light1.updateState() 
        state2 = await light2.updateState()  
        state3 = await light3.updateState()

        brightness1 = state1.get_brightness()
        brightness2 = state2.get_brightness()
        brightness3 = state3.get_brightness()
        if (
            light_is_on(state1)
            and light_is_on(state2)
            and light_is_on(state3)
            and brightness1 == brightness_value
            and brightness2 == brightness_value
            and brightness3 == brightness_value
        ):
            logging.info(f"Living room lights set to {brightness}% brightness.")
            return True

        return await return_light_turn_on_failure(
            "Failed to set living room lights to specified brightness."
        )
    except Exception as error:
        return await return_light_turn_on_failure(
            "Failed to set living room lights to specified brightness.",
            error,
        )
    finally:
        await light1.async_close()
        await light2.async_close()
        await light3.async_close()

async def station_light_color(color_name: str):
    # Turn on the living room lights with a specific color. Requires color_name parameter.
    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    BULB3_IP = os.getenv("BULB3_IP") 

    assert BULB1_IP and BULB2_IP and BULB3_IP, "BULB1, 2, and 3 IP environment variables must be set."
    logging.info(f"Changing color to {color_name}: {BULB1_IP}, {BULB2_IP}, {BULB3_IP}")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)
    light3 = wizlight(BULB3_IP)
    try:
        color_rgb = COLORS.get(color_name.upper(), (255, 255, 255))  # Default to white if not found
        await light1.turn_on(PilotBuilder(rgb=color_rgb))
        await light2.turn_on(PilotBuilder(rgb=color_rgb))
        await light3.turn_on(PilotBuilder(rgb=color_rgb))
        await wait_for_light_state_settle()
        state1 = await light1.updateState() 
        state2 = await light2.updateState()  
        state3 = await light3.updateState()

        rgb2 = state2.get_rgb()
        rgb1 = state1.get_rgb()
        rgb3 = state3.get_rgb()
        if (
            light_is_on(state1)
            and light_is_on(state2)
            and light_is_on(state3)
            and rgb1 == color_rgb
            and rgb2 == color_rgb
            and rgb3 == color_rgb
        ):
            logging.info(f"Living room lights set to color {color_name}.")
            return True

        return await return_light_turn_on_failure("Failed to set living room lights to specified color.")
    except Exception as error:
        return await return_light_turn_on_failure(
            "Failed to set living room lights to specified color.",
            error,
        )
    finally:
        await light1.async_close()
        await light2.async_close()
        await light3.async_close()
    
async def station_lights_freaky():
    from toolbox.music import play_specific_song

    await play_specific_song(Path(FREAK_MODE_SONG_PATH))

    # Turn on the living room lights to red. 
    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    BULB3_IP = os.getenv("BULB3_IP") 

    assert BULB1_IP and BULB2_IP and BULB3_IP, "BULB1, 2, and 3 IP environment variables must be set."
    logging.info(f"Turning the station to freak mode.")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)
    light3 = wizlight(BULB3_IP)
    try:
        color_rgb = COLORS["DARK_RED"]
        await light1.turn_on(PilotBuilder(rgb=color_rgb))
        await light2.turn_on(PilotBuilder(rgb=color_rgb))
        await light3.turn_on(PilotBuilder(rgb=color_rgb))
        await wait_for_light_state_settle()
        state1 = await light1.updateState()
        state2 = await light2.updateState()
        state3 = await light3.updateState()

        rgb2 = state2.get_rgb()
        rgb1 = state1.get_rgb()
        rgb3 = state3.get_rgb()
        if (
            light_is_on(state1)
            and light_is_on(state2)
            and light_is_on(state3)
            and rgb1 == color_rgb
            and rgb2 == color_rgb
            and rgb3 == color_rgb
        ):
            logging.info("Living room lights set to color Red.")
            return True

        return await return_light_turn_on_failure("Failed to activate freaky mode.")
    except Exception as error:
        return await return_light_turn_on_failure("Failed to activate freaky mode.", error)
    finally:
        await light1.async_close()
        await light2.async_close()
        await light3.async_close()


async def turn_everything_off():

    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    BULB3_IP = os.getenv("BULB3_IP")
    KBULB_IP = os.getenv("KBULB_IP")

    assert BULB1_IP and BULB2_IP and BULB3_IP and KBULB_IP, "BULB1, BULB2, BULB3 and KBULB_IP must be set."
    logging.info("Turning everything off: BULB1, BULB2, BULB3, and kitchen bulb")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)
    light3 = wizlight(BULB3_IP)
    klight = wizlight(KBULB_IP)
    try:
        # Send off commands in parallel
        await asyncio.gather(
            light1.turn_off(),
            light2.turn_off(),
            light3.turn_off(),
            klight.turn_off(),
        )
        await wait_for_light_state_settle()

        # Update states in parallel
        state1, state2, state3, kstate = await asyncio.gather(
            light1.updateState(),
            light2.updateState(),
            light3.updateState(),
            klight.updateState(),
        )

        if (
            light_is_off(state1)
            and light_is_off(state2)
            and light_is_off(state3)
            and light_is_off(kstate)
        ):
            logging.info("All bulbs turned off successfully.")
            return True

        logging.warning("Not all bulbs reached off state.")
        return False
    finally:
        await light1.async_close()
        await light2.async_close()
        await light3.async_close()
        await klight.async_close()


async def turn_everything_on():

    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    BULB3_IP = os.getenv("BULB3_IP")
    KBULB_IP = os.getenv("KBULB_IP")

    assert BULB1_IP and BULB2_IP and BULB3_IP and KBULB_IP, "BULB1, BULB2, BULB3 and KBULB_IP must be set."
    logging.info("Turning everything on: BULB1, BULB2, BULB3, and kitchen bulb")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)
    light3 = wizlight(BULB3_IP)
    klight = wizlight(KBULB_IP)
    try:
        # Send on commands in parallel.
        await asyncio.gather(
            light1.turn_on(PilotBuilder(brightness=DEFAULT_LIGHT_BRIGHTNESS)),
            light2.turn_on(PilotBuilder(brightness=DEFAULT_LIGHT_BRIGHTNESS)),
            light3.turn_on(PilotBuilder(brightness=DEFAULT_LIGHT_BRIGHTNESS)),
            klight.turn_on(PilotBuilder(brightness=DEFAULT_LIGHT_BRIGHTNESS)),
        )
        await wait_for_light_state_settle()

        # Update states in parallel
        state1, state2, state3, kstate = await asyncio.gather(
            light1.updateState(),
            light2.updateState(),
            light3.updateState(),
            klight.updateState(),
        )

        if (
            light_is_on(state1)
            and light_is_on(state2)
            and light_is_on(state3)
            and light_is_on(kstate)
        ):
            logging.info("All bulbs turned on successfully.")
            return True

        return await return_light_turn_on_failure("Not all bulbs reached the on state.")
    except Exception as error:
        return await return_light_turn_on_failure("Failed to turn everything on.", error)
    finally:
        await light1.async_close()
        await light2.async_close()
        await light3.async_close()
        await klight.async_close()


COLORS = {
    # Base
    "WHITE": (255, 255, 255),    # #FFFFFF
    "RED": (255, 0, 0),          # #FF0000
    "GREEN": (0, 255, 0),        # #00FF00
    "BLUE": (0, 0, 255),         # #0000FF
    "YELLOW": (255, 255, 0),     # #FFFF00
    "ORANGE": (255, 165, 0),     # #FFA500
    "PINK": (255, 105, 180),     # #FF69B4
    "PURPLE": (128, 0, 128),     # #800080
    "VIOLET": (138, 43, 226),    # #8A2BE2
    # Dark
    "DARK_RED": (139, 0, 0),         # #8B0000
    "DARK_GREEN": (0, 100, 0),       # #006400
    "DARK_BLUE": (0, 0, 139),        # #00008B
    "DARK_ORANGE": (255, 140, 0),    # #FF8C00
    "DARK_PURPLE": (48, 25, 52),     # #301934
    # Light
    "LIGHT_RED": (255, 102, 102),    # #FF6666
    "LIGHT_GREEN": (144, 238, 144),  # #90EE90
    "LIGHT_BLUE": (173, 216, 230),   # #ADD8E6
    "LIGHT_YELLOW": (255, 255, 224), # #FFFFE0
}
