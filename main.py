#!/usr/bin/env python3

import time
import colorsys
import os
import sys
import ST7735
import math
try:
    # Transitional fix for breaking change in LTR559
    from ltr559 import LTR559
    ltr559 = LTR559()
except ImportError:
    import ltr559

from bme280 import BME280
from enviroplus import gas
from subprocess import PIPE, Popen
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from fonts.ttf import RobotoMedium as UserFont
import logging

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("""all-in-one.py - Displays readings from all of Enviro plus' sensors
Press Ctrl+C to exit!
""")

# BME280 temperature/pressure/humidity sensor
bme280 = BME280()

# Create ST7735 LCD display class
st7735 = ST7735.ST7735(
    port=0,
    cs=1,
    dc=9,
    backlight=12,
    rotation=270,
    spi_speed_hz=10000000
)

# Initialize display
st7735.begin()

WIDTH = st7735.width
HEIGHT = st7735.height

# Set up canvas and font
img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
path = os.path.dirname(os.path.realpath(__file__))
font_size = 20
font = ImageFont.truetype(UserFont, font_size)

message = ""

# The position of the top bar
top_pos = 25


# Displays data and text on the 0.96" LCD
def display_text(variableKey, data, unit, position):

    variable = variableKey
    variableLength = len(variable)

    firstLetter = position
    lastLetter = position + 20
    
    # Maintain length of list
    values[variable] = values[variableKey][1:] + [data]
    # Scale the values for the variable between 0 and 1
    vmin = min(values[variableKey])
    vmax = max(values[variableKey])
    colours = [(v - vmin + 1) / (vmax - vmin + 1) for v in values[variableKey[0:variableLength]]]
    # Format the variable name and value
    
    messageRaw = "          {:.1f} {}          ".format(data, unit)
    if position == len(messageRaw)+20:
        position = 0
    #print(messageRaw)
    message = messageRaw[firstLetter:lastLetter]

    position += 1
    logging.info(message)
    draw.rectangle((0, 0, WIDTH, HEIGHT), (255, 255, 255))

    for i in range(len(colours)):
        # Convert the values to colours from red to blue
        colour = (1.0 - colours[i]) * 0.6
        r, g, b = [int(x * 255.0) for x in colorsys.hsv_to_rgb(colour, 1.0, 1.0)]
        # Draw a 1-pixel wide rectangle of colour
        draw.rectangle((i, top_pos, i + 1, HEIGHT), (r, g, b))
        # Draw a line graph in black
        line_y = HEIGHT - (top_pos + (colours[i] * (HEIGHT - top_pos))) + top_pos
        draw.rectangle((i, line_y, i + 1, line_y + 1), (0, 0, 0))
    # Write the text at the top in black
    draw.text((0, 0), message, font=font, fill=(0, 0, 0))
    st7735.display(img)
    return position


# Get the temperature of the CPU for compensation
def get_cpu_temperature():
    process = Popen(['vcgencmd', 'measure_temp'], stdout=PIPE, universal_newlines=True)
    output, _error = process.communicate()
    return float(output[output.index('=') + 1:output.rindex("'")])


# Tuning factor for compensation. Decrease this number to adjust the
# temperature down, and increase to adjust up
factor = 2.25

cpu_temps = [get_cpu_temperature()] * 5

delay = 0.5  # Debounce the proximity tap
mode = 0  # The starting mode
last_page = 0
light = 1

# Create a values dict to store the data
variables = ["temperature",
             "pressure",
             "humidity",
             "light",
             "oxidised",
             "reduced",
             "nh3"]

values = {}

switchCounter = 0
position = 0
calibrationRead = 0
runtime = 0
for v in variables:
    values[v] = [1] * WIDTH

# The main loop

while True:
    proximity = ltr559.get_proximity()

    # If the proximity crosses the threshold, toggle the mode
#   if (proximity > 1500 and time.time() - last_page > delay):
#       mode += 1
#       mode %= len(variables)
#       last_page = time.time()

    if (switchCounter > 100):
        #mode += 1
        #mode %= len(variables)
        mode = 5
        last_page = time.time()
        switchCounter = 0
        position = 0

    if runtime > 6000:
        calibrationRead = gas.read_all()
        calibrationRed = calibrationRead.reducing / 1000
        calibrationOx = calibrationRead.oxidising / 1000
        calibrationNH3 = calibrationRead.nh3 / 1000
    else:
        calibrationRead = 1
        calibrationRed = 1
        calibrationOx = 1
        calibrationNH3 = 1
        runtime += 1

    # One mode for each variable
    if mode == 0:
        # variable = "temperature"
        #unit = "C"
        cpu_temp = get_cpu_temperature()
        # Smooth out with some averaging to decrease jitter
        cpu_temps = cpu_temps[1:] + [cpu_temp]
        avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
        raw_temp = bme280.get_temperature()
        data = raw_temp - ((avg_cpu_temp - raw_temp) / factor)
        
        if(data > 30):
            unit = "C, Temperiture exceeds safe value"
            #maybe warn someone here? buzzer??
        elif(data < 13):
            unit = "C, Temperiture below safe value"
            #maybe warn someone here? buzzer??
        else:
            unit = "C, Temperiture at safe levels"

        position = display_text(variables[mode], data, unit, position)

    if mode == 1:
        # variable = "pressure"
        unit = "hPa"
        data = bme280.get_pressure()
        position = display_text(variables[mode], data, unit, position)

    if mode == 2:
        # variable = "humidity"
        #unit = "%"
        data = bme280.get_humidity()
        position = display_text(variables[mode], data, unit, position)

        if(data > 70):
            unit = "%: humidity above safe levels"

        elif(data < 20):
            unit = "%: humidity below safe levels"

        else:
            unit = "%: humidity acceptable"

    if mode == 3:
        # variable = "light"
        unit = "Lux"
        if proximity < 10:
            data = ltr559.get_lux()
        else:
            data = 1
        position = display_text(variables[mode], data, unit, position)

    if mode == 4:
        # variable = "ox"
        #unit = "kOhm" #0.8 - 20 for NO2
        data = gas.read_all()
        data = data.oxidising / 1000

        data = (math.pow(10, -1.25 * math.log10(data/calibrationOx) + 0.64))

        if(data < 10):
            unit = "ppm, NO2 levels are good!"

        elif(data< 20):
            unit = "ppm, NO2 levels are high but still good"

        elif(data>= 20):
            unit = "ppm, NO2 levels are above measurable levels"
        
        position = display_text(variables[mode], (data + 0.05 - 0.8) / 1.9195, unit, position)

    if mode == 5:
        # variable = "red"
        #unit = "kOhm" #100-1500 for CO
        data = gas.read_all()
        data = data.reducing / 1000

        print(math.pow(10, -1.25 * math.log10(data/calibrationRed) + 0.64))
        
        data = math.pow(10, -1.25 * math.log10(data/calibrationRed) + 0.64)

        if (data < 10):
           unit = "ppm CO levels are safe"
        elif (data < 20):
            unit = "ppm CO levels are concerning"
        elif (data < 50):
            unit = "ppm CO levels are not safe, do not spend longer than 30 minutes in here"
        elif (data < 200):
            unit = "ppm CO levels are dangerous"
        elif (data < 400):
            unit = "ppm CO levels are highly dangerous"
        elif (data < 800):
            unit = "ppm leave room immediately"

        position = display_text(variables[mode], data, unit, position)

    if mode == 6:
        # variable = "nh3"
        #unit = "kOhm" #10 - 1500 for NH3 
        data = gas.read_all()
        data = data.nh3 / 1000
        
        data = (math.pow(10, -1.25 * math.log10(data/calibrationNH3) + 0.64))

        if(data < 25):
            unit = "ppm ammonia levels should be safe"
            
        position = display_text(variables[mode], (data - 10) / 4.96666666667, unit, position)

    switchCounter += 1