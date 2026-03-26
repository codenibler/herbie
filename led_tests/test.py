from rpi_ws281x import PixelStrip, Color, ws
import time

LED_COUNT = 80
LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 80
LED_INVERT = False
LED_CHANNEL = 0
LED_STRIP = ws.WS2811_STRIP_GRB
ON_SECONDS = 1
OFF_SECONDS = 1
ON_COLOR = (255, 0, 0)

strip = PixelStrip(
    LED_COUNT,
    LED_PIN,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_BRIGHTNESS,
    LED_CHANNEL,
    LED_STRIP
)

def fill(r, g, b):
    c = Color(r, g, b)
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, c)
    strip.show()

strip.begin()

print("Blinking LEDs on GPIO18. Press Ctrl+C to stop.")

try:
    while True:
        fill(*ON_COLOR)
        time.sleep(ON_SECONDS)
        fill(0, 0, 0)
        time.sleep(OFF_SECONDS)
except KeyboardInterrupt:
    pass
finally:
    fill(0, 0, 0)
