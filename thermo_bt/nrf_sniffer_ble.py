#!/usr/bin/env python3

# Copyright (c) Nordic Semiconductor ASA
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form, except as embedded into a Nordic
#    Semiconductor ASA integrated circuit in a product or a software update for
#    such product, must reproduce the above copyright notice, this list of
#    conditions and the following disclaimer in the documentation and/or other
#    materials provided with the distribution.
#
# 3. Neither the name of Nordic Semiconductor ASA nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
#
# 4. This software, with or without modification, must only be used with a
#    Nordic Semiconductor ASA integrated circuit.
#
# 5. Any software provided in binary form under this license must not be reverse
#    engineered, decompiled, modified and/or disassembled.
#
# THIS SOFTWARE IS PROVIDED BY NORDIC SEMICONDUCTOR ASA "AS IS" AND ANY EXPRESS
# OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
# OF MERCHANTABILITY, NONINFRINGEMENT, AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL NORDIC SEMICONDUCTOR ASA OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
# GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
# OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


"""
Wireshark extcap wrapper for the nRF Sniffer for Bluetooth LE by Nordic Semiconductor.
"""

import threading
import json
import os
import sys
import argparse
import re
import time
import struct
import logging
logging.getLogger().setLevel(logging.INFO)
logging.info("")

import serial

from SnifferAPI import Sniffer, UART, Devices, Pcap, Exceptions

import trame

ERROR_USAGE = 0
ERROR_ARG = 1
ERROR_INTERFACE = 2
ERROR_FIFO = 3
ERROR_INTERNAL = 4

CTRL_CMD_INIT = 0
CTRL_CMD_SET = 1
CTRL_CMD_ADD = 2
CTRL_CMD_REMOVE = 3
CTRL_CMD_ENABLE = 4
CTRL_CMD_DISABLE = 5
CTRL_CMD_STATUSBAR = 6
CTRL_CMD_INFO_MSG = 7
CTRL_CMD_WARN_MSG = 8
CTRL_CMD_ERROR_MSG = 9

CTRL_ARG_DEVICE = 0
CTRL_ARG_KEY_TYPE = 1
CTRL_ARG_KEY_VAL = 2
CTRL_ARG_ADVHOP = 3
CTRL_ARG_HELP = 4
CTRL_ARG_RESTORE = 5
CTRL_ARG_LOG = 6
CTRL_ARG_DEVICE_CLEAR = 7
CTRL_ARG_NONE = 255

CTRL_KEY_TYPE_PASSKEY = 0
CTRL_KEY_TYPE_OOB = 1
CTRL_KEY_TYPE_LEGACY_LTK = 2
CTRL_KEY_TYPE_SC_LTK = 3
CTRL_KEY_TYPE_DH_PRIVATE_KEY = 4
CTRL_KEY_TYPE_IRK = 5
CTRL_KEY_TYPE_ADD_ADDR = 6
CTRL_KEY_TYPE_FOLLOW_ADDR = 7

# Wireshark nRF Sniffer for Bluetooth LE Toolbar will always cache the last used key and adv hop and send
# this when starting a capture. To ensure that the key and adv hop is always shown correctly
# in the Toolbar, even if the user has changed it but not applied it, we send the last used
# key and adv hop back as a default value.
last_used_key_type = CTRL_KEY_TYPE_PASSKEY
last_used_key_val = ""
last_used_advhop = "37,38,39"

zero_addr = "[00,00,00,00,00,00,0]"

# While searching for a selected Device we must not write packets to the pipe until
# the device is found to avoid getting advertising packets from other devices.
write_new_packets = False

# The RSSI capture filter value given from Wireshark.
rssi_filter = 0

# The RSSI filtering is not on when in follow mode.
in_follow_mode = False

# nRF Sniffer for Bluetooth LE interface option to only capture advertising packets
capture_only_advertising = False
capture_only_legacy_advertising = False
capture_scan_response = True
capture_scan_aux_pointer = True
capture_coded = False


def get_baud_rates(interface):
    if not hasattr(serial, "__version__") or not serial.__version__.startswith('3.'):
        raise RuntimeError("Too old version of python 'serial' Library. Version 3 required.")
    return UART.find_sniffer_baudrates(interface)


def string_address(address):
    """Make a string representation of the address"""
    if len(address) < 7:
        return None

    addr_string = ''

    for i in range(5):
        addr_string += (format(address[i], '02x') + ':')
    addr_string += format(address[5], '02x') + ' '

    if address[6]:
        addr_string += ' random '
    else:
        addr_string += ' public '

    return addr_string


def control_write(arg, typ, message):
    """Write the message to the control channel"""
    pass


def capture_write(message):
    """Write the message to the capture pipe"""
    pass


def new_packet(notification):
    """A new Bluetooth LE packet has arrived"""
    if not write_new_packets:
        return

    packet = notification.msg["packet"]

    if not(rssi_filter == 0 or in_follow_mode == True or packet.RSSI > rssi_filter):
        return

    #print("new_packet")

    p = bytes([packet.boardId] + packet.getList())

    handle_packet(p)
    #capture_write(Pcap.create_packet(p, packet.time))

ctrl = threading.Event()
finished = False

mac_addresses = {
    #"bleu": "A4:C1:38:45:AF:D5", # bleu
    #"jaune": "A4:C1:38:63:84:DA", # jaune --> PHONE ONLY
}

mac_filters = {}

def handle_packet(p):
    hex_repr = "".join([m for m in map("{:x}".format, p)]).replace("0x", "")

    found = []
    for location, mac_filter in mac_filters.items():
        if mac_filter not in hex_repr:
            continue

        data = trame.decode(location, p)
        if not data: continue

        found.append(location)
        dest = f"/tmp/{location}.json"
        logging.info(f"Saving {dest} ...")
        with open(dest, "w") as f:
            json.dump(data, f)

    if not found: return
    for location in found:
        del mac_filters[location]

    if not mac_filters:
        logging.info("all done")
        global finished
        finished = True
        ctrl.set()

        while True:
            time.sleep(1)

    pass

def device_added(notification):
    """A device is added or updated"""
    device = notification.msg

    # Only add devices matching RSSI filter
    if not(rssi_filter == 0 or device.RSSI > rssi_filter):
        return

    # Extcap selector uses \0 character to separate value and display value,
    # therefore the display value cannot contain the \0 character as this
    # would lead to truncation of the display value.
    display = (device.name.replace('\0', '\\0') +
               ("  " + str(device.RSSI) + " dBm  " if device.RSSI != 0 else "  ") +
               string_address(device.address))

    message = str(device.address) + '\0' + display
    #print("ctrl: device_added", message)
    #control_write(CTRL_ARG_DEVICE, CTRL_CMD_ADD, message)


def device_removed(notification):
    """A device is removed"""
    device = notification.msg
    display = device.name + "  " + string_address(device.address)

    message = ""
    message += str(device.address)

    #control_write(CTRL_ARG_DEVICE, CTRL_CMD_REMOVE, message)
    print("ctrl: device removed", display)
    logging.info("Removed: " + display)


def devices_cleared(notification):
    """Devices have been cleared"""
    message = ""
    control_write(CTRL_ARG_DEVICE, CTRL_CMD_REMOVE, message)

    control_write(CTRL_ARG_DEVICE, CTRL_CMD_ADD, " " + '\0' + "All advertising devices")
    control_write(CTRL_ARG_DEVICE, CTRL_CMD_ADD, zero_addr + '\0' + "Follow IRK")
    control_write(CTRL_ARG_DEVICE, CTRL_CMD_SET, " ")


def control_write_defaults():
    """Write default control values"""
    control_write(CTRL_ARG_KEY_TYPE, CTRL_CMD_SET, str(last_used_key_type))
    control_write(CTRL_ARG_KEY_VAL, CTRL_CMD_SET, last_used_key_val)
    control_write(CTRL_ARG_ADVHOP, CTRL_CMD_SET, last_used_advhop)


def error_interface_not_found(interface):
    log = "nRF Sniffer for Bluetooth LE could not find interface: " + interface
    control_write(CTRL_ARG_NONE, CTRL_CMD_ERROR_MSG, log)
    logging.fatal(f"Interface not found {interface}")
    sys.exit(ERROR_INTERFACE)


def validate_interface(interface):
    """Check if interface exists"""
    if sys.platform != 'win32' and not os.path.exists(interface):
        error_interface_not_found(interface)


def get_default_baudrate(interface):
    """Return the baud rate that interface is running at, or exit if the board is not found"""
    rates = get_baud_rates(interface)
    if rates is None:
        error_interface_not_found(interface)
    return rates["default"]


def sniffer_capture(interface, baudrate):
    """Start the sniffer to capture packets"""
    global write_new_packets

    try:
        logging.info("Log started at %s", time.strftime("%c"))

        validate_interface(interface)
        if baudrate is None:
            baudrate = get_default_baudrate(interface)

        sniffer = Sniffer.Sniffer(interface, baudrate)
        sniffer.subscribe("NEW_BLE_PACKET", new_packet)
        sniffer.subscribe("DEVICE_ADDED", device_added)
        sniffer.subscribe("DEVICE_UPDATED", device_added)
        sniffer.subscribe("DEVICE_REMOVED", device_removed)
        sniffer.subscribe("DEVICES_CLEARED", devices_cleared)
        sniffer.setAdvHopSequence([37, 38, 39])
        #sniffer.setSupportedProtocolVersion(get_supported_protocol_version(extcap_version))
        logging.info("Sniffer created")

        logging.info("Software version: %s" % sniffer.swversion)
        sniffer.getFirmwareVersion()
        sniffer.getTimestamp()
        sniffer.start()
        logging.info("sniffer started")
        sniffer.scan(capture_scan_response, capture_scan_aux_pointer, capture_coded)
        logging.info("scanning started")

        logging.info("")
        # Start receiving packets
        write_new_packets = True
        while not finished:
            # Wait for keyboardinterrupt
            ctrl.wait()
        logging.info("bye bye :)")

    except Exceptions.LockedException as e:
        logging.info('{}'.format(e.message))

    finally:
        # Safe to use logging again.
        logging.info("Tearing down")

        logging.info("Exiting")


import atexit

@atexit.register
def goodbye():
   logging.info("Exiting PID {}".format(os.getpid()))


if __name__ == '__main__':

    # Capture options
    parser = argparse.ArgumentParser(description="Nordic Semiconductor nRF Sniffer for Bluetooth LE extcap plugin")

    parser.add_argument("--target",
                        help="Name and MAC of the device")
    
    parser.add_argument("--name",
                        help="Name of the device")

    parser.add_argument("--mac",
                        help="MAC address of the device")

    parser.add_argument("--mine", help="Show my devices", action="store_true")

    # Extcap Arguments

    parser.add_argument("--device", help="Device", default="/dev/ttyUSB0")

    # Interface Arguments
    parser.add_argument("--baudrate", type=int, help="The sniffer baud rate")
    parser.add_argument("--only-advertising", help="Only advertising packets", action="store_true")
    parser.add_argument("--only-legacy-advertising", help="Only legacy advertising packets", action="store_true")
    parser.add_argument("--scan-follow-rsp", help="Find scan response data ", action="store_true")
    parser.add_argument("--scan-follow-aux", help="Find auxiliary pointer data", action="store_true")
    parser.add_argument("--coded", help="Scan and follow on LE Coded PHY", action="store_true")

    logging.info("Started PID {}".format(os.getpid()))

    try:
        args, unknown = parser.parse_known_args()
        logging.info(args)

    except argparse.ArgumentError as exc:
        print("%s" % exc, file=sys.stderr)
        sys.exit(ERROR_ARG)

    def to_mac_filter(address):
        return "".join(reversed(address.lower().split(":")))

    if args.mine:
        print(sys.argv[0], "--target bleu_A4:C1:38:45:AF:D5")
        print(sys.argv[0], "--name jaune_A4:C1:38:63:84:DA # phone only")
        sys.exit(0)

    if args.target:
        name, mac = args.target.split("_")
        mac_filters[name] = to_mac_filter(mac)
        
    if args.name and args.mac:
        mac_filters[args.name] = to_mac_filter(args.mac)

    if not mac_filters:
        logging.critical("--name and --mac are mandatory")
        exit(1)

    for name, mac in mac_filters.items():
        logging.info(f"Watching for '{name}' --> {mac}")

    interface = args.device

    capture_only_advertising = args.only_advertising
    capture_only_legacy_advertising = args.only_legacy_advertising
    capture_scan_response = args.scan_follow_rsp
    capture_scan_aux_pointer = args.scan_follow_aux
    capture_coded = args.coded

    try:
        logging.info('sniffer capture')
        sniffer_capture(interface, args.baudrate)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        print('internal error: {}'.format(repr(e)))
        sys.exit(ERROR_INTERNAL)

    logging.info('main exit PID {}'.format(os.getpid()))
