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

from pyephem_sunpath.sunpath import sunpos

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

_RIVERS = Gauge('river_flow', 'Flow of the river (m3/s)', ["name"])
DORDOGNE = _RIVERS.labels(name="Dordogne")
LOT = _RIVERS.labels(name="Lot")

INFOCLIMAT_GAUGES = {
    'temperature': ("Temperature (in C)", ["mode"]),

    'humidity': "Humidity (in %)",
    'rain': ('Rain (in mm)', ["mode"]),

    'wind': ('Wind speed (in km/h)', ["mode"]),
    'wind_dir': 'Wind direction (in *)',

    'uv_idx': 'UV index',
    'sun_rad': ('Sun radiation', ["mode"]),

    'pressure': "Pression (in hPa)"
}

INFOCLIMAT_PROPS = {
    "temperature": ('temperature', dict(mode="temperature")),
    "dew": ('temperature',  dict(mode="dew_point")),
    "hr": ('humidity', {}),

    "rr1h": ('rain', dict(mode="1h")),
    "rr_since_0H": ('rain', dict(mode="since_0h")),

    "wndavg": ('wind', dict(mode="average")),
    "wndraf": ('wind', dict(mode="rafale")),
    "wnddir": ('wind_dir', {}),

    "uvindex": ('uv_idx', {}),
    "srad": ('sun_rad', dict(mode="actual")),
    "srad_theo": ('sun_rad', dict(mode="theo")),
    "slp": ('pressure', {})
}

def prepare_infoclimat_gauges(gauges_def, infoclimat_props):
    gauges = {}
    labeled_gauges = {}
    for metric, props in gauges_def.items():
        if isinstance(props, str):
            descr = props
            labels = []
        else:
            descr, labels = props

        gauges[metric] = Gauge(metric, descr, labels)

    for key, props in infoclimat_props.items():
        metric, labels = props

        gauge = gauges[metric]

        if labels:
            gauge = gauge.labels(**labels)
        labeled_gauges[key] = gauge

    return labeled_gauges

INFOCLIMAT = prepare_infoclimat_gauges(INFOCLIMAT_GAUGES, INFOCLIMAT_PROPS)

ALTITUDE = Gauge('altitude','Sun altitude (*)')
AZYMUTH = Gauge('azymuth', "Sun azymuth (*)")

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
# ---

def get_infoclimat_data(station_name, station_idx):
    url = f"https://www.infoclimat.fr/observations-meteo/temps-reel/{station_name}/{station_idx}.html?graphiques"
    try:
        req = urllib.request.Request(url,  headers={'User-Agent': 'Mozilla/5.0'})
        content = urllib.request.urlopen(req).read().decode('utf-8', "ignore")
        data = None
        for line in content.split("\n"):
            if not line.strip().startswith("var _data_gr = "):
                continue

            data = line.partition("=")[-1].strip(" ;")
            break
        if not data:
            raise RuntimeError(f"Couldn't find the '_data_gr' anchor in '{url}' ...")
        json_data = json.loads(data)
        return json_data
    except Exception as e:
        logging.error(e)
        return None

def get_infoclimat():
    # https://www.infoclimat.fr/observations-meteo/temps-reel/lhospitalet/000X4.html?graphiques
    data = get_infoclimat_data("lhospitalet", "000X4")
    has_errors = False
    if not data:
        logging.warning(f"No data available at {datetime.datetime.now()}")
        return

    for key, gauge in INFOCLIMAT.items():
        try:
            ts_value = data[key][-1]
        except KeyError:
            logging.warning(f"Key '{key}' is not available at {datetime.datetime.now()}")
            has_errors = True
            continue

        if isinstance(ts_value, dict):
            #_ts = ts_value["x"]
            value = ts_value["y"]

        elif isinstance(ts_value, list) and len(ts_value) == 2:
            _ts, value = ts_value

        else:
            continue

        if value is not None:
            gauge.set(value)

    if has_errors:
        logging.info(f"Available keys: {', '.join(data.keys())}")

# ---

def get_sun_position():
    lat = 44.44
    lon = 1.43

    now = datetime.datetime.now()
    is_dst = time.daylight and time.localtime().tm_isdst > 0
    utc_offset = - (time.altzone if is_dst else time.timezone)
    utc_offset=0
    alt, azm = sunpos(now, lat, lon, tz=utc_offset/3600, dst=is_dst)

    ALTITUDE.set(alt if alt > 0 else 0)
    AZYMUTH.set(azm if alt > 0 else 0)

# ---

def collect_all_data():
    """Collects all the data currently set"""
    sensor_data = {}
    sensor_data['dordogne'] = DORDOGNE.collect()[0].samples[0].value
    sensor_data['lot'] = LOT.collect()[0].samples[0].value

    for key, gauge in INFOCLIMAT.items():
        sensor_data[key] = gauge.collect()[0].samples[0].value

    sensor_data['altitude'] = ALTITUDE.collect()[0].samples[0].value
    sensor_data['azymuth'] = AZYMUTH.collect()[0].samples[0].value

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

    if args.debug:
        DEBUG = True

    first = True
    previous_ts = datetime.datetime.now()
    while True:

        get_infoclimat()
        get_sun_position()
        generate_hauteurs()

        if first:
            # Start up the server to expose the metrics.
            start_http_server(addr=args.bind, port=args.port)
            logging.info("Listening on http://{}:{}".format(args.bind, args.port))
            first = False

        if DEBUG:
            logging.info('Sensor data: {}'.format(collect_all_data()))

        time.sleep(60)
