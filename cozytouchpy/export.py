#! /usr/bin/env python3

import time
import logging
import argparse
import yaml

import json

from prometheus_client import start_http_server, Gauge, Histogram, generate_latest, CollectorRegistry
registry = CollectorRegistry()

from cozytouchpy import CozytouchClient
from cozytouchpy.constant import SUPPORTED_SERVERS

WATER_TEMPERATURE = Gauge('water_temperature', 'Water temperature', ["type"], registry=registry)
WATER_VOLUME = Gauge('water_volume', 'Water volume', ["type"], registry=registry)
TIME_IN_STATE = Gauge('water_heater_time_in_state', 'Water heater time in state', ["type"], registry=registry)
STATUS = Gauge('water_heater_status', 'Water heater status', ["type"], registry=registry)
WATER_HEATER_STATE = Gauge('water_heater_state', 'Water heater state', ["type"], registry=registry)
heating_statuses = set()
HEATER_ENERGY = Gauge('heater_energy', 'Heater energy', ["location", "type"], registry=registry)

with open(".env.yaml") as f:
    env = yaml.safe_load(f)

def update_prometheus(show):
    client = CozytouchClient(
        env["username"], env["password"],
        SUPPORTED_SERVERS["atlantic_cozytouch"]
    )

    client.connect()
    setup = client.get_setup()

    devices = client.get_devices()
    dev = devices[env["device_id"]]

    WATER_TEMPERATURE.labels("target").set(dev.get_state('core:WaterTargetTemperatureState'))
    WATER_TEMPERATURE.labels("targetdhw").set(dev.get_state('core:TargetDHWTemperatureState'))
    WATER_TEMPERATURE.labels("control").set(dev.get_state('core:ControlWaterTargetTemperatureState'))
    TIME_IN_STATE.labels("heat_pump_operating").set(dev.get_state('modbuslink:HeatPumpOperatingTimeState'))
    TIME_IN_STATE.labels("electric_booster_operating").set(dev.get_state('modbuslink:ElectricBoosterOperatingTimeState'))

    heating_status = dev.get_state('core:HeatingStatusState') # Heating, ...
    heating_statuses.add(heating_status)
    for status in heating_statuses:
        WATER_HEATER_STATE.labels(status).set(1 if status == heating_status else 0)

    WATER_VOLUME.labels("hot_water").set(dev.get_state('core:RemainingHotWaterState'))
    STATUS.labels("shower_remaining").set(dev.get_state('core:NumberOfShowerRemainingState'))
    WATER_VOLUME.labels("v40_estimation").set(dev.get_state('core:V40WaterVolumeEstimationState'))
    STATUS.labels("power_heat_electrical").set(dev.get_state('modbuslink:PowerHeatElectricalState'))
    STATUS.labels("power_heat_pump").set(dev.get_state('modbuslink:PowerHeatPumpState'))

    WATER_TEMPERATURE.labels("bottom_tank").set(dev.get_state('core:BottomTankWaterTemperatureState'))
    WATER_TEMPERATURE.labels("middle").set(dev.get_state('modbuslink:MiddleWaterTemperatureState'))
    TIME_IN_STATE.labels("middle_water_temp_in_state").set(dev.get_state('core:MiddleWaterTemperatureInState'))


    sensor = dev.sensors[env["sensor_id"]]
    consumption = sensor.get_state('core:ElectricEnergyConsumptionState')
    HEATER_ENERGY.labels("water_heater", "consumption").set(consumption / 1000)


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
    args = parser.parse_args()

    if args.debug:
        DEBUG = True

    first = True

    while True:
        update_prometheus(args.show)

        if first and not args.show:
            # Start up the server to expose the metrics.
            start_http_server(addr=args.bind, port=args.port, registry=registry)
            logging.info("Listening on http://{}:{}".format(args.bind, args.port))
            first = False

        if args.show:
            print(generate_latest(registry).decode("ascii"))
            break

        try:
            time.sleep(60)
        except KeyboardInterrupt:
            raise SystemExit(0)
