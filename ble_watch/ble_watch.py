#!/usr/bin/env python3

# inspired by https://github.com/madkaye/ble-ls

import sys
import datetime
import json
import logging
logging.getLogger().setLevel(logging.INFO)
import argparse

from bluepy import btle
from bluepy.btle import Scanner, Peripheral, Characteristic, ScanEntry, UUID
import bluepy.btle

import trame


class BLELS:

    SCAN_TIMEOUT = 10
    scanner = None
    publicdevices = []

    def scan(self, process_data, duration=SCAN_TIMEOUT):
        print("scan: starting scan for {}s".format(duration))
        self.scanner = Scanner()
        devices = self.scanner.scan(duration)
        foundDevices = 0
        for dev in devices:
            devname = dev.getValueText(btle.ScanEntry.COMPLETE_LOCAL_NAME)
            if devname is None:
                devname = dev.getValueText(btle.ScanEntry.SHORT_LOCAL_NAME)

            if process_data(devname, dev):
                return True

    def connectandread(self, addr):
        try:

            peri = Peripheral()
            peri.connect(addr)

            print("Listing services...")
            services = peri.getServices()
            for serv in services:
                print("   -- SERVICE: {} [{}]".format(serv.uuid, UUID(serv.uuid).getCommonName()))
                characteristics = serv.getCharacteristics()
                for chara in characteristics:
                    print("   --   --> CHAR: {}, Handle: {} (0x{:04x}) - {} - [{}]".format(chara.uuid,
                                                                                    chara.getHandle(),
                                                                                    chara.getHandle(),
                                                                                    chara.propertiesToString(),
                                                                                    UUID(chara.uuid).getCommonName()))
            print("Listing descriptors...")
            descriptors = peri.getDescriptors()
            for desc in descriptors:
                print("   --  DESCRIPTORS: {}, [{}], Handle: {} (0x{:04x})".format(desc.uuid,
                                                                                    UUID(desc.uuid).getCommonName(),
                                                                                    desc.handle, desc.handle))

            print("Reading characteristics...")
            chars = peri.getCharacteristics()
            for c in chars:
                print("  -- READ: {} [{}] (0x{:04x}), {}, Value: {}".format(c.uuid, UUID(c.uuid).getCommonName(),
                                                                c.getHandle(), c.descs, c.read() if c.supportsRead() else ""))


        except Exception as e:
            print("connectandread: Error,", e)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Xiaomi ATC BLE watcher")
    parser.add_argument("--target", help="Name and MAC of the device")
    parser.add_argument("--mine", help="Show my devices", action="store_true")
    parser.add_argument("--duration", help="Duration of the scan", default=10)
    parser.add_argument("--tries", help="Number of tries to perform before failing", default=3)

    try:
        args, unknown = parser.parse_known_args()
        logging.info(args)

    except argparse.ArgumentError as exc:
        print("%s" % exc, file=sys.stderr)
        sys.exit(ERROR_ARG)

    if args.mine or not args.target:
        print(sys.argv[0], "--target bleu_A4:C1:38:45:AF:D5")
        sys.exit(0)

    logging.info(f"Target: {args.target}")
    location, mac = args.target.split("_")

    print("--- BLE LS Script ---")
    print(f"mac:      {mac}")
    print(f"location: {location}")
    print("--------------------")

    def process_data(devname, dev):
        if dev.addr.lower() != mac.lower():
            return

        bin_data = (b"\x12\x16" + dev.scanData[22])

        data = trame.decode(location, bin_data)

        if not data: return

        data["date"] = str(datetime.datetime.now())
        data["time"] = int(datetime.datetime.utcnow().timestamp())
        dest = f"/tmp/{location}.json"
        logging.info(f"Saving {dest} ...")
        with open(dest, "w") as f:
            json.dump(data, f, indent=4)
            print("", file=f)

        return True

    for i in range(args.tries):
        try:
            if BLELS().scan(process_data, duration=args.duration):
                break
            print("Not found")
        except bluepy.btle.BTLEDisconnectError as e:
            print("Device disconnected ...")
        except Exception as e:
            print(f"Exception {e.__class__.__name__}: {e}")

    else:
        print("Didn't find any match :/")
        sys.exit(1)

    print("--------------------")
