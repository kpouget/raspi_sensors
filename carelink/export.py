#! /usr/bin/env python3

import json
import time
import logging
import argparse
from prometheus_client import start_http_server, Gauge, Histogram, generate_latest, CollectorRegistry
import datetime, dateutil.parse

import carelink_client2

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

def update_prometheus(show, from_file):
    if from_file:
        with open("data.json") as f:
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

    sensor_duration_minutes.set(patientData["sensorDurationMinutes"])

    reservoir_level_percent.set(patientData["reservoirLevelPercent"])
    reservoir_remaining_units.set(patientData["reservoirRemainingUnits"])

    pump_battery_level_percent.set(patientData["pumpBatteryLevelPercent"])

    time_in_range_percent.labels("hypo").set(patientData["belowHypoLimit"])
    time_in_range_percent.labels("in_range").set(patientData["timeInRange"])
    time_in_range_percent.labels("hyper").set(patientData["aboveHyperLimit"])

    average_sg.set(patientData["averageSGFloat"])

    last_sg.set(patientData["lastSG"]["sg"])
    last_sg_ts = dateutil.parser.parse(patientData["lastSG"]["timestamp"])

    now = datetime.datetime.now()
    age = (now - dateutil.parser.parse(patientData["lastSG"]["timestamp"])).total_seconds()
    last_sg_age.set(age if age > 0 else 0)

    # for sg in patientData["sgs"]:
    #     print(sg["timestamp"], sg["sensorState"].replace("NO_ERROR_MESSAGE", ""), sg["sg"] or "")

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
