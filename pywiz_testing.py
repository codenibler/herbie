import asyncio
from pywizlight import wizlight, PilotBuilder

async def main():
    light = wizlight("192.168.178.88")
    try:
        # turn on + set initial brightness
        await light.turn_on(PilotBuilder(brightness=128))

        # cycle some RGB colors
        colors = [
            ("red",   (255, 0, 0)),
            ("green", (0, 255, 0)),
            ("blue",  (0, 0, 255)),
            ("purple",(160, 0, 255)),
            ("white", (255, 255, 255)),
        ]

        for name, rgb in colors:
            await light.turn_on(PilotBuilder(rgb=rgb, brightness=128))
            await asyncio.sleep(1.0)

        # warm -> cool white via color temperature (Kelvin)
        for k in (2700, 3000, 4000, 5000, 6500):
            await light.turn_on(PilotBuilder(colortemp=k, brightness=128))
            await asyncio.sleep(1.0)

        state = await light.updateState()
        print("final brightness:", state.get_brightness())
        print("final rgb:", state.get_rgb())
        print("final colortemp:", state.get_colortemp())
    finally:
        light._async_close()

asyncio.run(main())