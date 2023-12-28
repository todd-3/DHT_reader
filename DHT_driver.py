"""
An interface Library for the adafruit DHT11
* SCRIPT MUST BE RUN AS SUDO TO ALLOW FOR SETTING SCHEDULER PRIORITY *

This code uses read methods from the Adafruit_DHT library which is now deprecated and does not support raspberry pi 4s
Source: https://github.com/adafruit/Adafruit_Python_DHT/blob/master/source/Raspberry_Pi_2/pi_2_dht_read.c

Author: Roman Todd
"""
import RPi.GPIO as gpio
from time import sleep
import logging

logger = logging.getLogger(__name__)  # initiate logger
DHT_pulses = 41  # the DHT sensor sends 1 time pulse and 40 data pulses
DHT_read_timeout = 300

try:  # try to import os.nice and check if script as permissions to set scheduler priority
    from os import nice as cpu_priority
    cpu_priority(-1)
    cpu_priority(1)
except (PermissionError, ImportError) as e:
    if isinstance(e, PermissionError):  # give message for lack of permissions
        logger.warning("Could not set scheduler priority - try running script using 'sudo'")
    elif isinstance(e, ImportError):  # give message for import error
        logger.warning("Method 'nice' could not be found in os library - likely because this is a windows system")

    logger.info("Running script without setting priority")
    def cpu_priority(priority_increment: int):  # spoof priority method to allow continued execution
        return None


class ReadParseError(Exception):
    ...

class ReadTimeoutError(Exception):
    ...

def read_data(pin_num: int) -> tuple[float, float]:
    logger.debug(f"Reading from pin {pin_num}")
    gpio.setmode(gpio.BCM)  # set control mode

    # preparing a list to contain data pulse information
    # creates an array of 0s with length equal to DHT_pulses * 2
    pulse_counter = [0 for i in range(DHT_pulses * 2)]

    # initialize sensor for read
    gpio.setup(pin_num, gpio.OUT)  # set pin to be an output
    gpio.output(pin_num, 1)  # set pin high
    sleep(0.5)  # keep pin high for 500 milliseconds
    gpio.output(pin_num, 0)  # set pin low
    sleep(0.02)  # keep pin low for 20 milliseconds

    # the read operations are very time sensitive
    # as such the script is set to maximum priority to ensure proper readings
    logger.debug("Increasing scheduler priority")
    cpu_priority(-20)

    # wait for sensor to begin data transmission
    gpio.setup(pin_num, gpio.IN)  # set pin to be input
    c = 0  # timeout counter
    while gpio.input(pin_num):  # wait for pin to be pulled low by sensor
        if c == DHT_read_timeout:
            raise ReadTimeoutError("Timed out waiting for sensor to being transmission")
        c += 1

    # record data pulses
    for i in range(0, DHT_pulses * 2, 2):  # loop for expected number of low, high pulse pairs (DHT_pulses * 2)
        e = i + 1
        while not gpio.input(pin_num):  # pin is low
            pulse_counter[i] += 1
            if pulse_counter[i] == DHT_read_timeout:
                raise ReadTimeoutError("Timed out reading data pulse")

        while gpio.input(pin_num):  # pin is high
            pulse_counter[e] += 1
            if pulse_counter[e] == DHT_read_timeout:
                raise ReadTimeoutError("Timed out reading data pulse")

    logger.debug("Data read complete - resetting priority to default")
    cpu_priority(20)  # reading complete, reset to default priority

    # calculate 50 microsecond threshold value for decoding
    threshold = 0
    for i in range(2, DHT_pulses * 2, 2):  # ignore first pulse pair
        threshold += pulse_counter[i]  # sum all low pulses

    threshold //= DHT_pulses  # divide sum by pulse count to get average low pulse length (should be ~50Us)
    logger.debug(f"Using threshold value of {threshold}")

    # decode pulse stream by comparing against 50 microsecond threshold
    # a pulse less than 50us (~28ms) is a 0
    # a pulse great than 50us (~70us) is a 1
    data = [0 for i in range(5)]
    for i in range(3, DHT_pulses * 2, 2):  # start at the first position
        index = (i - 3) // 16
        data[index] <<= 1  # bitshift 1 to the left
        if pulse_counter[i] >= threshold:  # greater than threshold, is a one
            data[index] |= 1  # OR an additional bit
        # no bits added for 0

    logger.debug(f"Data bytes are {', '.join([str(b) for b in data])}")
    # use byte 5 as checksum to verify data
    if data[4] == ((data[0] + data[1] + data[2] + data[3]) & 0xFF):
        humidity = float(data[0])
        temperature = float(data[2])
    else:
        raise ReadParseError("Checksum did not match, data was parsed or received incorrectly")

    return humidity, temperature

if __name__ == "__main__":
    logging.basicConfig(format='%(levelname)s -- %(message)s', level=logging.DEBUG)
    pin = int(input("What pin should be read from?  "))

    while True:
        try:
            hum, temp = read_data(pin)
            print(f"Humidity: {hum}%\nTemperature: {temp} degrees")
        except ReadParseError:
            logger.warning("Data could not be parsed properly")
        except ReadTimeoutError as e:
            logger.warning(e)
        sleep(10)