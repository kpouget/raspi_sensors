#! /usr/bin/env python3

import time
import logging
import argparse
from prometheus_client import start_http_server, Gauge, Histogram, generate_latest, CollectorRegistry
registry = CollectorRegistry()

HEATER_ENERGY = Gauge('heater_energy', 'Heater energy', ["location", "type"], registry=registry)

def update_prometheus(show):
    HEATER_ENERGY.labels("pac_interieur", "consumption").set(5)


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


"""
[Unit]
Description=...
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/sensors/...
ExecStart=python3 ./export.py --bind=0.0.0.0 --port=3500n
ExecReload=/bin/kill -HUP $MAINPID

Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
"""
