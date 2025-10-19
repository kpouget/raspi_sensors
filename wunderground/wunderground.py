#!/usr/bin/env python3
import os
import random
import requests
import time
import logging
import argparse
import subprocess
import datetime

from threading import Thread

import json
import urllib
import yaml

from prometheus_client import start_http_server, Gauge, Histogram

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("enviroplus_exporter.log"),
              logging.StreamHandler()],
    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("""my_exporter.py - Expose readings from the what I'm interested in in Prometheus format

Press Ctrl+C to exit!

""")

DEBUG = os.getenv('DEBUG', 'false') == 'true'

# ---

PRESSURE_OFFSET = 0

# ---

_RIVERS = Gauge('river_flow', 'Flow of the river (m3/s)', ["name"])
DORDOGNE = _RIVERS.labels(name="Dordogne")
LOT = _RIVERS.labels(name="Lot")

# ---

GAUGES = {
    'humidity': ("Humidity (in %)", ["location"]),
    'rain': ('Rain (in mm)', ["mode"]),

    'wind': ('Wind speed (in km/h)', ["mode"]),
    'wind_dir': 'Wind direction (in *)',

    'uv_idx': 'UV index',
    'sun_rad': 'Sun radiation',

    'pressure': "Pression (in hPa)",
    'temperature': ("Temperature", ["mode", "location"]),
}

PROPS = {
    "temp": ('temperature', dict(mode="actual", location="toiture")),
    "dewpt": ('temperature',  dict(mode="dew_point", location="toiture")),
    "heatIndex": ('temperature',  dict(mode="heat_index", location="toiture")),
    "windChill": ('temperature',  dict(mode="wind_chill", location="toiture")),

    "humidity": ('humidity', dict(location="toiture")),

    "precipRate": ('rain', dict(mode="rate")),
    "precipTotal": ('rain', dict(mode="total")),

    "windSpeed": ('wind', dict(mode="speed")),
    "windGust": ('wind', dict(mode="gust")),
    "winddir": ('wind_dir', {}),

    "uv": ('uv_idx', {}),
    "solarRadiation": ('sun_rad', {}),

    "pressure": ('pressure', {}),
}

def prepare_gauges(gauges_def, props_def):
    gauges = {}
    labeled_gauges = {}
    for metric, props in gauges_def.items():
        if isinstance(props, str):
            descr = props
            labels = []
        else:
            descr, labels = props

        gauges[metric] = Gauge(metric, descr, labels)

    for key, props in props_def.items():
        metric, labels = props

        gauge = gauges[metric]

        if labels:
            gauge = gauge.labels(**labels)

        labeled_gauges[key] = gauge

    return labeled_gauges

METRICS = prepare_gauges(GAUGES, PROPS)

# ---

def get_data(station_id, api_key):
    url = f"https://api.weather.com/v2/pws/observations/current?apiKey={api_key}&stationId={station_id}&numericPrecision=decimal&format=json&units=m"

    try:
        req = urllib.request.Request(url,  headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req).read()

        data = json.loads(response)
        data = data["observations"][0]
        mtr = data.pop("metric")
        data.update(mtr)
        return data
    except Exception as e:
        logging.error(e)
        return None

def get_wunderground(station_id, api_key):
    data = get_data(station_id, api_key)
    has_errors = []
    if not data:
        logging.warning(f"No data available at {datetime.datetime.now()}")
        return

    for key, gauge in METRICS.items():
        try:
            value = data[key]
        except KeyError:
            has_errors.append(key)
        if value is None:
            continue
        if key == "pressure":
            value -= PRESSURE_OFFSET
        try:
            gauge.set(value)
        except:
            import pdb;pdb.set_trace()
            pass
    if has_errors:
        logging.info(f"Missing keys: {', '.join(has_errors)}")
        logging.info(f"Available keys: {', '.join(data.keys())}")

# ---
# ---

def collect_all_data():
    """Collects all the data currently set"""
    sensor_data = {}

    for key, gauge in METRICS.items():
        samples = gauge.collect()[0].samples
        if not samples:
            continue
        sensor_data[key] = samples[0].value

    return sensor_data


def str_to_bool(value):
    if value.lower() in {'false', 'f', '0', 'no', 'n'}:
        return False
    elif value.lower() in {'true', 't', '1', 'yes', 'y'}:
        return True
    raise ValueError('{} is not a valid boolean value'.format(value))


def get_level(river_code, serie):
    URL = "https://www.vigicrues.gouv.fr/services/observations.json/index.php?CdStationHydro={}&GrdSerie={}&FormatSortie=simple"

    url = URL.format(river_code, serie)
    try:
        content = urllib.request.urlopen(url).read().decode('utf-8')
        measures = json.loads(content)
        hauteur = measures["Serie"]["ObssHydro"][-1][1]

        return hauteur
    except Exception as e:
        logging.warning(f"get_level(river_code={river_code}, series={Q}): {e.__class__.__name__}: {e}")
        return None


def generate_hauteurs():
    dordogne = get_level("P230001001", "Q")
    if dordogne is not None:
        DORDOGNE.set(dordogne)

    lot = get_level("O823153002", "Q")
    if lot is not None:
        LOT.set(lot)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bind", metavar='ADDRESS', default='0.0.0.0', help="Specify alternate bind address [default: 0.0.0.0]")
    parser.add_argument("-p", "--port", metavar='PORT', default=8000, type=int, help="Specify alternate port [default: 8000]")
    parser.add_argument("-d", "--debug", metavar='DEBUG', type=str_to_bool, help="Turns on more verbose logging, showing sensor output and post responses [default: false]")
    args = parser.parse_args()

    if args.debug:
        DEBUG = True

    with open(".env") as f:
        env = yaml.safe_load(f)
        api_key = env["api_key"]
        station_id = env["station_id"]

    first = True
    previous_ts = datetime.datetime.now()
    while True:
        try:
            get_wunderground(station_id, api_key)
        except Exception as e:
            logging.exception("Failed to generate the wunderground data ...")

        try:
            generate_hauteurs()
        except Exception as e:
            logging.exception("Failed to generate the river hauteurs ...")

        if first:
            # Start up the server to expose the metrics.
            start_http_server(addr=args.bind, port=args.port)
            logging.info("Listening on http://{}:{}".format(args.bind, args.port))
            first = False

        if DEBUG:
            logging.info('Sensor data: {}'.format(collect_all_data()))

        time.sleep(60)
