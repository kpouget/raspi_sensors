#!/usr/bin/env python3

import argparse
from datetime import datetime
import json
import logging
logging.getLogger().setLevel(logging.INFO)

import sys

import bluepy.btle
import lywsd03mmc

parser = argparse.ArgumentParser()
parser.add_argument('--target', help='target', nargs='?', default="jaune_A4:C1:38:63:84:DA")
parser.add_argument('--tries', help='number of tries', default=3, nargs='?')
args = parser.parse_args()

location, mac = args.target.split("_")
output = f"/tmp/{location}.json"

logging.info(f"Trying to connect to {mac} ...")
client = lywsd03mmc.Lywsd03mmcClient(mac)

for i in range(args.tries):
    try:
        data = client.data
        break
    except bluepy.btle.BTLEDisconnectError:
        logging.warning(f"Try #{i+1}/{args.tries}: failed to connect :/")
else:
    logging.error(f"All the {args.tries} tries failed to connect :/")
    sys.exit(1)

logging.info(f"Got the data {data} ...")
json_data = json.dumps(dict(
    temperature = data.temperature,
    humidity = data.humidity,
    batt_lvl = data.battery,
    batt_mv = data.voltage,
    date = str(datetime.now()),
    time = int(datetime.utcnow().timestamp()),
), indent=4)


if output != "-":
    logging.info(f"Saving it to {output} ...")
    with open(output, "w") as f:
        print(json_data, file=f)
    logging.info("All done :)")
else:
    print(json_data)
