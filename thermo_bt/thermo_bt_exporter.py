#!/usr/bin/env python3
import os
import random
import requests
import time
import logging
import argparse
import subprocess
import datetime
import pathlib

from threading import Thread

import json, yaml
import urllib

from prometheus_client import start_http_server, Gauge, Histogram

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("enviroplus_exporter.log"),
              logging.StreamHandler()],
    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("""thermo_exporter.py - Expose thermo_bt.py results

Press Ctrl+C to exit!

""")

DEBUG = os.getenv('DEBUG', 'false') == 'true'

# ---

sensor_data = {}

TEMPERATURE = Gauge('temperature','Temperature measured (*C)', ["location"])
HUMIDITY = Gauge('humidity','Relative humidity measured (%)', ["location"])

DREW_POINT = Gauge('drew_point','Point de rosée (*C)', ["location"])
HUMIDEX = Gauge('humidex','Humidex', ["location"])

BATT_MV = Gauge('batt_mv', 'Battery power (mV)', ["location"])
BATT_LVL = Gauge('batt_lvl', 'Battery level (%)', ["location"])
READ_COUNTER = Gauge('read_counter', 'Device read counter', ["location"])
READ_TIMESTAMP = Gauge('read_timestamp', 'Device read timestamp', ["location"])
TIME = Gauge('time', 'Read timestamp', ["location"])

# ---

def get_data(filename, location):
    if not pathlib.Path(filename).exists():
        logging.info(f"File '{filename}' does not exists.")
        return

    with open(filename) as f:
        data = json.load(f)

    if (temperature := data.get("temperature")) is not None:
        TEMPERATURE.labels(location).set(temperature)

    if (humidity := data.get("humidity")) is not None:
        HUMIDITY.labels(location).set(humidity)

    if (temperature := data.get("temperature")) is not None and (humidity := data.get("humidity")) is not None:
        alpha = math.log(humidite / 100.0) + (17.27 * temperature) / (237.3 + temperature)
        drew = (237.3 * alpha) / (17.27 - alpha)
        humidex = temperature + 0.5555 * (6.11 * math.exp(5417.753 * (1 / 273.16 - 1 / (273.15 + rosee))) - 10)

        DREW_POINT.labels(location).set(drew)
        HUMIDEX.labels(location).set(humidex)

    if (counter := data.get("counter")) is not None:
        READ_COUNTER.labels(location).set(counter)

    if (bat_mv := data.get("batt_mv")) is not None:
        BATT_MV.labels(location).set(bat_mv)

    if (bat_lvl := data.get("batt_lvl")) is not None:
        BATT_LVL.labels(location).set(bat_lvl)

    if (timestamp := data.get("timestamp")) is not None:
        READ_TIMESTAMP.labels(location).set(timestamp)

    if (time := data.get("time")) is not None:
        TIME.labels(location).set(time)
# ---

def collect_all_data():
    """Collects all the data currently set"""

    return sensor_data


def str_to_bool(value):
    if value.lower() in {'false', 'f', '0', 'no', 'n'}:
        return False
    elif value.lower() in {'true', 't', '1', 'yes', 'y'}:
        return True
    raise ValueError('{} is not a valid boolean value'.format(value))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bind", metavar='ADDRESS', default='0.0.0.0', help="Specify alternate bind address [default: 0.0.0.0]")
    parser.add_argument("-p", "--port", metavar='PORT', default=8000, type=int, help="Specify alternate port [default: 8000]")
    parser.add_argument("-d", "--debug", metavar='DEBUG', type=str_to_bool, help="Turns on more verbose logging, showing sensor output and post responses [default: false]")
    args = parser.parse_args()

    # Start up the server to expose the metrics.
    start_http_server(addr=args.bind, port=args.port)
    # Generate some requests.

    THIS_DIR = pathlib.Path(os.path.realpath(__file__)).parent

    if args.debug:
        DEBUG = True


    logging.info("Listening on http://{}:{}".format(args.bind, args.port))

    previous_mapping = ""
    while True:

        with open(THIS_DIR / ".env.yaml") as f:
            env = yaml.safe_load(f)

        mapping = env["mapping"]
        mapping_str = json.dumps(mapping)

        for filename, location in mapping.items():
            if previous_mapping != mapping_str:
                logging.info(f"Watching for {filename} --> {location}")

            get_data(f"/tmp/{filename}.json", location)

        previous_mapping = mapping_str
        if DEBUG:
            logging.info('Sensor data: {}'.format(collect_all_data()))

        time.sleep(120)
