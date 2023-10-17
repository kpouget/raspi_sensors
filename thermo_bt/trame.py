#!/usr/bin/env python3

import struct

first_trame = b"\xbd\x06\x2f\x01\x73\x1b\x06\x0a\x01\x27\x2c\x00\x00\x98\x01\x00" \
    b"\x00\xd6\xbe\x89\x8e\x00\x1c\xd5\xaf\x45\x38\xc1\xa4\x02\x01\x06" \
    b"\x12\x16\x1a\x18\xd5\xaf\x45\x38\xc1\xa4\xfa\x07\x9f\x13\x8d\x0b" \
    b"\x64\xec\x0e\xfd\x92\xc4"

# https://docs.python.org/3/library/struct.html
# https://github.com/pvvx/ATC_MiThermometer#atc1441-format
"""
uint8_t     size;   // = 18
uint8_t     uid;    // = 0x16, 16-bit UUID
uint16_t    UUID;   // = 0x181A, GATT Service 0x181A Environmental Sensing

uint8_t     MAC[6]; // [0] - lo, .. [6] - hi digits

int16_t     temperature;    // x 0.01 degree
uint16_t    humidity;       // x 0.01 %
uint16_t    battery_mv;     // mV
uint8_t     battery_level;  // 0..100 %
uint8_t     counter;        // measurement count
uint8_t     flags;  // GPIO_TRG pin (marking "reset" on circuit board) flags:
                    // bit0: Reed Switch, input
                    // bit1: GPIO_TRG pin output value (pull Up/Down)
                    // bit2: Output GPIO_TRG pin is controlled according to the set parameters
                    // bit3: Temperature trigger event
                    // bit4: Humidity trigger event

"""

START = 0
HEADER_LENGTH = 1+1+2
MAC_LENGTH = 6
DATA_START = START+HEADER_LENGTH+MAC_LENGTH
DATA_LENGTH = 2+2+2+1+1+1
SHOW_HEADERS = False

current_counter = 0

def decode(location, _trame):
    SIZE_UID_UUID = b"\x12\x16\x1a\x18"
    starter, found, content = _trame.partition(SIZE_UID_UUID)
    if not found:
        print(f"{SIZE_UID_UUID} anchor not found in the data trame:/")
        return

    trame = SIZE_UID_UUID + content
    size, uid, uuid = struct.unpack('<BBH', trame[START:START+HEADER_LENGTH])
    mac = struct.unpack('>HHH', trame[START+HEADER_LENGTH:START+HEADER_LENGTH+MAC_LENGTH])
    mac_hexa = "".join(map(hex, mac)).replace("0x", "").upper()
    mac_addr = ":".join(reversed([f"{a}{b}" for a, b in zip(mac_hexa[0::2], mac_hexa[1::2])]))

    keys = ["temperature", "humidity", "batt_mv", "batt_lvl", "counter", "flags"]
    values = struct.unpack('<hHHBBB', trame[DATA_START:DATA_START+DATA_LENGTH])

    kv = dict(zip(keys, values))
    kv["temperature"] /= 100
    kv["humidity"] /= 100
    g = globals()
    g.update(kv)
    kv.pop("flags")
    global current_counter
    import datetime
    print(datetime.datetime.now().time().replace(microsecond=0))
    if current_counter == counter:
        return

    if SHOW_HEADERS:
        print("size\t\t:", size)
        print("uid\t\t:", hex(uid))
        print("uuid\t\t:", hex(uuid))
        print("mac\t\t:", mac_addr)
        print(f"flags\t\t: {bin(flags)}")

    print(f"### {location}")
    print(f"temperature\t: {temperature} degree")
    print(f"humidity\t: {humidity}%")
    print(f"batt_mv\t\t: {batt_mv}mV")
    print(f"batt_lvl\t: {batt_lvl}%")
    print(f"counter\t\t: {counter}")
    print()
    current_counter = counter

    return kv

if __name__ == "__main__":
    #decode(first_trame)
    from scapy.all import *

    MAC = "A4:C1:38:45:AF:D5"

    mac_filter = "".join(reversed(MAC.lower().split(":")))

    packets = rdpcap(sys.argv[1])
    for packet in packets:
        trame = bytes_hex(packet)

        if mac_filter not in str(trame):
            continue

        decode(bytes(packet))

        print("---")
