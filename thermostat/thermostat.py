#! /usr/bin/env python3

import logging
import types
import sys
from collections import defaultdict
import urllib
import datetime
import yaml
import pathlib
import time
import argparse

import prometheus_client.parser
from prometheus_client import start_http_server, Gauge

sys.path.insert(0, str(pathlib.Path("./TapoP100").absolute()))
from PyP100 import PyP100

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()],
    datefmt='%Y-%m-%d %H:%M:%S')


HEATER_STATE = Gauge('heater_state', 'Heater state', ["location"])
HEAT_DIFF = Gauge('heat_difference', 'Heat difference', ["location"])

HEAT_TARGET = Gauge('heat_target', 'Heat target', ["location"])
HEAT_LIMIT = Gauge('heat_limit', 'Heat limit', ["location"])

HEAT_CURRENT = Gauge('heat_current', 'Heat current', ["location"])
HEAT_MISSING = Gauge('heat_missing', 'Heat missing', ["location"])
HEAT_AGE = Gauge('heat_age', 'Heat age', ["location"])
HEAT_TOO_OLD = Gauge('heat_too_old', 'Heat too old', ["location"])

# set in load_plugs_config()
PLUGS_CONFIG = None 

def load_plugs_config():
    global PLUGS_CONFIG
    with open("./thermo.yaml") as f:
        PLUGS_CONFIG = yaml.safe_load(f)


def load_thermo_config():
    with open("./config.yaml") as f:
        return yaml.safe_load(f)


def get_plug(location):
    email = PLUGS_CONFIG["email"]
    pwd = PLUGS_CONFIG["password"]

    ip = PLUGS_CONFIG["plugs"][location]
    plug = PyP100.P100(ip, email, pwd)

    try: plug.login() # first try may fail, ignore it
    except Exception: pass
    plug.login()

    return plug


def get_temperatures(locations):
    URL = "http://home.972.ovh:35002"
    metrics = urllib.request.urlopen(URL).read().decode('utf-8')

    now_timestamp = time.time()
    utc_offset = datetime.datetime.fromtimestamp(now_timestamp) - datetime.datetime.utcfromtimestamp(now_timestamp)

    temperatures = defaultdict(types.SimpleNamespace)
    for family in prometheus_client.parser.text_string_to_metric_families(metrics):
        for sample in family.samples:
            location = sample.labels.get("location")
            if not location in locations: continue

            if sample.name == "temperature":
                temperatures[location].value = sample.value
            elif sample.name == "time":
                temperatures[location].time = datetime.datetime.fromtimestamp(sample.value) + utc_offset

    return temperatures


def get_new_heater_state(thermo, target, limit, current_temp, current_state):
    heat_diff = current_temp - target
    location = thermo["location"]
    HEAT_DIFF.labels(location=location).set(heat_diff)
    
    logging.info(f"Room '{location}': {current_temp=:.2f}, {target=:.2f}, diff={heat_diff:.2f} | current={'on' if current_state else 'off'}")


    if heat_diff < 0:
        logging.info(f"Room '{location}' --> too cold (-,-)")
        return True
    elif current_state and current_temp < limit:
        logging.info(f"Room '{location}' --> just above limit, keep heating up (+.+)")
        return True
    else:
        logging.info(f"Room '{location}' --> hot enough (^.^)")
        return False


def set_heater_state(location, current_state, new_state):
    #if new_state == current_state:
    #    logging.info(f"Room '{location}' ==> don't touch the heater (current_state={'on' if new_state else 'off'})")
    #    return new_state

    try:
        plug = get_plug(location)

        if new_state:
            plug.turnOn()
            logging.info(f"Room '{location}' ==> turn the heater on")
        else:
            plug.turnOff()
            logging.info(f"Room '{location}' ==> turn the heater off")

    except Exception as e:
        logging.error(f"Room '{location}' ==> Failed to set the heater state: {e}")
        HEATER_STATE.labels(location=location).set(-1)

        return None

    HEATER_STATE.labels(location=location).set(1 if new_state else 0)

    return new_state


def get_target(thermo):
    current_time = datetime.datetime.now().time().hour

    for schedule_time, schedule_temp in thermo["schedule"].items():
        if schedule_time > current_time:
            return schedule_temp
        
    return 0


def update_one(thermo, temperature, current_state):
    location = thermo["location"]
    target = get_target(thermo)
    limit = target + thermo["threshold"]

    try:
        age = datetime.datetime.now() - temperature.time
    except AttributeError:
        HEAT_AGE.labels(location=location).set(-100)
        return False
    else:
        HEAT_AGE.labels(location=location).set(age.total_seconds())

    heat_too_old = age > datetime.timedelta(minutes=20)
    if heat_too_old:
        HEAT_TOO_OLD.labels(location=location).set(1)
    else:
        HEAT_TOO_OLD.labels(location=location).set(0)

    HEAT_CURRENT.labels(location=location).set(temperature.value)
    HEAT_TARGET.labels(location=location).set(target)
    HEAT_LIMIT.labels(location=location).set(limit)

    new_state = False
    if not heat_too_old:
        new_state = get_new_heater_state(thermo, target, limit, temperature.value, current_state)
    else:
        logging.warning(f"Temperature of '{location}' is outdated (-,-) ({age})")

    final_state = set_heater_state(location, current_state, new_state)

    return final_state


def update_all(thermostats, state):
    locations = [thermo["location"] for thermo in thermostats]
    temperatures = get_temperatures(locations)

    for thermo in thermostats:
        location = thermo["location"]
        try:
            temperature = temperatures[location]
        except KeyError:
            HEAT_MISSING.labels(location=location).set(1)
            continue
        HEAT_MISSING.labels(location=location).set(0)

        old_state = state.get(location)
        new_state = update_one(thermo, temperature, old_state)

        state[location] = new_state

        show_metrics(location)
        logging.info("---")


def show_metrics(location):

    metrics = [metric for metric in prometheus_client.REGISTRY.collect() if not metric.name.startswith("python") and not metric.name.startswith("process")]

    locations = defaultdict(list)
    for metric in metrics:
        for sample in metric.samples:
            locations[sample.labels.get("location")].append(sample)

    for metric_location, metric_samples in locations.items():
        if metric_location != location: continue

        print(location)
        print("-"*len(location))
        for sample in metric_samples:
            print(f"{sample.name} {sample.value:.2f}")
        print()

def main(args):
    load_plugs_config()
    state = {}

    first = True

    while True:
        thermostats = load_thermo_config()
        update_all(thermostats, state)
        logging.info("")
        if first:
            start_http_server(addr=args.bind, port=args.port)
            logging.info("Listening on http://{}:{}".format(args.bind, args.port))
            first = False

        time.sleep(60)


def str_to_bool(value):
    if value.lower() in {'false', 'f', '0', 'no', 'n'}:
        return False
    elif value.lower() in {'true', 't', '1', 'yes', 'y'}:
        return True
    raise ValueError('{} is not a valid boolean value'.format(value))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bind", metavar='ADDRESS', default='0.0.0.0', help="Specify alternate bind address [default: 0.0.0.0]")
    parser.add_argument("-p", "--port", metavar='PORT', default=8000, type=int, help="Specify alternate port [default: 8000]")
    parser.add_argument("-d", "--debug", metavar='DEBUG', type=str_to_bool, help="Turns on more verbose logging, showing sensor output and post responses [default: false]")
    args = parser.parse_args()

    # Start up the server to expose the metrics.

    sys.exit(main(args))
