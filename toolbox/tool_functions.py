from pywizlight import wizlight, PilotBuilder

import asyncio
import logging
import os

async def kitchen_light_on():
    # Turn on the kitchen light. Requires no parameters.
    KITCHEN_BULB_IP = os.getenv("KITCHEN_BULB_IP")
    assert KITCHEN_BULB_IP is not None, "KITCHEN_BULB_IP environment variable not set."

    logging.info(f"Turning on kitchen light at IP: {KITCHEN_BULB_IP}")
    light = wizlight(KITCHEN_BULB_IP)

    await light.turn_on(PilotBuilder(brightness=128))
    state = await light.updateState()  # Update state to ensure command was sent
    
    brightness = state.get_brightness()
    if brightness == 128:
        logging.info("Kitchen light brightness set to 128 successfully.")
        return True

    logging.warning("Failed to set kitchen light brightness to 128.")
    return False

async def kitchen_light_off():
    # Turn off the kitchen light. Requires no parameters.
    KITCHEN_BULB_IP = os.getenv("KITCHEN_BULB_IP")
    assert KITCHEN_BULB_IP is not None, "KITCHEN_BULB_IP environment variable not set."

    logging.info(f"Turning off kitchen light at IP: {KITCHEN_BULB_IP}")
    light = wizlight(KITCHEN_BULB_IP)

    await light.turn_off()
    state = await light.updateState()  # Update state to ensure command was sent
    
    brightness = state.get_brightness()
    if brightness == 0:
        logging.info("Kitchen light turned off successfully.")
        return True
    
    logging.warning("Failed to turn off kitchen light.")
    return False

async def station_lights_off():
    # Turn off the kitchen light. Requires no parameters.
    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    """ TO DO: ADD BULB3 IP AND FUNCTIONALITY """
    # BULB3_IP = os.getenv("BULB3_IP") 

    assert BULB1_IP and BULB2_IP, "BULB1_IP and BULB2_IP environment variables must be set."
    logging.info(f"Turning off living room lights at IPs: {BULB1_IP}, {BULB2_IP}")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)

    await light1.turn_off()
    await light2.turn_off()
    state1 = await light1.updateState() 
    state2 = await light2.updateState()  

    brightness2 = state2.get_brightness()
    brightness1 = state1.get_brightness()
    if brightness1 == 0 and brightness2 == 0:
        logging.info("Living room lights turned off successfully.")
        return True
    
    logging.warning("Failed to turn off living room lights.")
    return False

async def station_lights_on():
    # Turn on the living room lights. Requires no parameters.
    BULB1_IP = os.getenv("BULB1_IP")
    BULB2_IP = os.getenv("BULB2_IP")
    """ TO DO: ADD BULB3 IP AND FUNCTIONALITY """
    # BULB3_IP = os.getenv("BULB3_IP") 

    assert BULB1_IP and BULB2_IP, "BULB1_IP and BULB2_IP environment variables must be set."
    logging.info(f"Turning on living room lights at IPs: {BULB1_IP}, {BULB2_IP}")

    light1 = wizlight(BULB1_IP)
    light2 = wizlight(BULB2_IP)

    await light1.turn_on(PilotBuilder(brightness=128))
    await light2.turn_on(PilotBuilder(brightness=128))
    state1 = await light1.updateState() 
    state2 = await light2.updateState()  

    brightness2 = state2.get_brightness()
    brightness1 = state1.get_brightness()
    if brightness1 == 128 and brightness2 == 128:
        logging.info("Living room lights turned on successfully.")
        return True
    
    logging.warning("Failed to turn on living room lights.")
    return False


