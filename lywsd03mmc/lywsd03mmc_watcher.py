#!/usr/bin/env python3

import argparse
from datetime import datetime
import json
import logging
logging.getLogger().setLevel(logging.INFO)
import os

import sys

import bluepy.btle
import lywsd03mmc

parser = argparse.ArgumentParser()
parser.add_argument('--target', help='target', nargs='?', default="jaune_A4:C1:38:63:84:DA")
parser.add_argument('--tries', help='number of tries', default=3, nargs='?')
args = parser.parse_args()

location, mac = args.target.split("_")
output = f"/tmp/{location}.json"

logging.info("Restarting the bluetooth hci ...")
os.system("hciconfig hci0 down && hciconfig hci0 up")

logging.info(f"Trying to connect to {mac} ...")
client = lywsd03mmc.Lywsd03mmcClient(mac)

for i in range(args.tries):
    try:
        data = client.data
        break
    except Exception as e:
        logging.warning(f"Try #{i+1}/{args.tries}: failed to connect :/ ({e.__class__.__name__}: {e})")

else:
    logging.error(f"All the {args.tries} tries failed to connect :/")
    sys.exit(1)

logging.info(f"Got the data {data} ...")
json_data = json.dumps(dict(
    temperature = data.temperature,
    humidity = data.humidity,
    batt_lvl = data.battery,
    batt_mv = data.voltage * 1000,
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
