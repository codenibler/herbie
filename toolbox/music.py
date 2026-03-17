from time import sleep
from pathlib import Path

import subprocess
import logging
import asyncio
import random
import os


""" TO DO: ADD GLOBAL MUSIC MANAGER """
async def play_random_songs():
    logging.info("Herbie requested for a general mix of songs to be played.")
    for song in os.listdir("songs"):
        if os.getenv("USE_BLUETOOTH_SPEAKER") == True:
            process = await asyncio.create_subprocess_exec(
                "pw-play", f"songs/{song}"
            ) 
        else:
            process = await asyncio.create_subprocess_exec(
                "aplay", f"songs/{song}"
            ) 
        await process.wait()
    """ TO DO: CREATE GLOBAL MUSIC MANAGER """
    sleep(2) # I know this is disgusting. I need to wait for the song to start before returning
    return True

async def play_specific_song(song_path):
    song_path = Path(song_path)
    logging.info(f"Herbie called for specific song at {song_path} to be played.")

    if song_path.exists() and song_path.is_file():
        logging.info(f"Playing {song_path}")
        if os.getenv("USE_BLUETOOTH_SPEAKER") == True:
            subprocess.Popen(["pw-play", str(song_path)])
        else:
            subprocess.Popen(["aplay", str(song_path)])
    else:
        logging.info(f"Song at {song_path} not found.")
        return False
    return True
