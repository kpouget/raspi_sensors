#! /usr/bin/env python3

import json
import time
import logging
import argparse
from prometheus_client import start_http_server, Gauge, Histogram, generate_latest, CollectorRegistry
import datetime, dateutil.parser
from collections import defaultdict

import carelink_client2

NaN = float("NaN")

registry = CollectorRegistry()

carelink_exporter_state = Gauge('carelink_exporter_state', 'carelink exporter state', registry=registry)
carelink_in_range = Gauge('carelink_in_range', 'devices in range', ["device"], registry=registry)

sensor_duration_minutes = Gauge('sensor_duration_minutes', 'sensor age in minutes', registry=registry)
reservoir_level_percent = Gauge("reservoir_level_percent", "", registry=registry)
reservoir_remaining_units = Gauge("reservoir_remaining_units", "", registry=registry)
pump_battery_level_percent = Gauge("pump_battery_level_percent", "", registry=registry)
time_in_range_percent = Gauge("time_in_range_percent", "percentage time in range", ["range"], registry=registry)

average_sg = Gauge("average_sg", "average sensor glucose", registry=registry)
last_sg = Gauge("last_sg", "last sensor glucose reading", registry=registry)
last_sg_age = Gauge("last_sg_age", "age of the last sensor glucose reading, in seconds", registry=registry)

sensor_state = Gauge('sensor_state', 'sensor_state', ["state"], registry=registry)
sensor_state_dict = defaultdict(int)


last_sensor_local = None

def update_prometheus(show, from_file):
    if from_file:
        with open(from_file) as f:
            data = json.load(f)
        carelink_exporter_state.set(0)
    else:
        client = carelink_client2.CareLinkClient(tokenFile="logindata.json")
        if not client.init():
            print("Couldn't initialize ...")
            carelink_exporter_state.set(-1)
            return

        carelink_exporter_state.set(1)
        data = client.getRecentData()

        with open("data.json", "w") as f:
            json.dump(data, f)

    patientData = data["patientData"]

    carelink_in_range.labels("conduit").set(1 if patientData["conduitInRange"] else 0)
    carelink_in_range.labels("pump").set(1 if patientData["conduitMedicalDeviceInRange"] else 0)
    carelink_in_range.labels("sensor").set(1 if patientData["conduitSensorInRange"] else 0)

    in_range = patientData["conduitMedicalDeviceInRange"] and patientData["conduitSensorInRange"]

    if in_range:
        reservoir_level_percent.set(patientData["reservoirLevelPercent"])
        reservoir_remaining_units.set(patientData["reservoirRemainingUnits"])
        pump_battery_level_percent.set(patientData["pumpBatteryLevelPercent"])

    if patientData["timeInRange"]:
        time_in_range_percent.labels("hypo").set(patientData["belowHypoLimit"])
        time_in_range_percent.labels("in_range").set(patientData["timeInRange"])
        time_in_range_percent.labels("hyper").set(patientData["aboveHyperLimit"])

    global last_sensor_local
    if in_range:
        last_sensor_local = (patientData["sensorDurationMinutes"], datetime.datetime.now())
        sensor_duration_minutes.set(last_sensor_local[0])
    elif last_sensor_local:
        sensorDurationMinutes = last_sensor_local[0]
        sensorDurationMinutes -= (datetime.datetime.now() - last_sensor_local[1]).total_seconds() / 60
        sensor_duration_minutes.set(sensorDurationMinutes)
    else:
        sensor_duration_minutes.set(NaN)

    average_sg.set(patientData["averageSGFloat"])

    if patientData["lastSG"]["sg"] > 10:
        last_sg.set(patientData["lastSG"]["sg"])
    else:
        last_sg.set(NaN)

    try:
        last_sg_ts = dateutil.parser.parse(patientData["lastSG"]["timestamp"])

        now = datetime.datetime.now()
        age = (now - last_sg_ts).total_seconds()
        last_sg_age.set(age if age > 0 else 0)
    except KeyError:
        last_sg_age.set(NaN)

    for state_name, count in sensor_state_dict.items():
        sensor_state_dict[state_name] = 0

    for sg in patientData["sgs"]:
        try:
            sensor_state_dict[sg["sensorState"]] += 1
        except KeyError:
            sensor_state_dict["NO_STATE"] += 1

    for state_name, count in sensor_state_dict.items():
        sensor_state.labels(state_name).set(count)

    pass

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
    parser.add_argument("-s", "--show", metavar='SHOW', type=str_to_bool, help="Show the data [default: false]")
    parser.add_argument("-f", "--file", metavar='FILE', default=None, help="Reads from a file instead of querying Carelink")

    args = parser.parse_args()

    if args.debug:
        DEBUG = True

    first = True

    while True:
        update_prometheus(args.show, args.file)

        if first and not args.show:
            # Start up the server to expose the metrics.
            start_http_server(addr=args.bind, port=args.port, registry=registry)
            logging.info("Listening on http://{}:{}".format(args.bind, args.port))
            first = False

        if args.show:
            print(generate_latest(registry).decode("ascii"))
            break

        try:
            time.sleep(200)
        except KeyboardInterrupt:
            raise SystemExit(0)
