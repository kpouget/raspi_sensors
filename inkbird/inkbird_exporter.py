#!/usr/bin/env python3
import os
import time
import logging
import argparse
from threading import Thread

from prometheus_client import start_http_server, Gauge
from bleak import BleakScanner

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()],
    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("""inkbird_exporter.py - Expose readings from Inkbird BLE sensor in Prometheus format

Press Ctrl+C to exit!

""")

DEBUG = os.getenv('DEBUG', 'false') == 'true'

# Your device configuration
TARGET_MAC = os.getenv('INKBIRD_MAC', "49:24:03:06:04:28").upper()
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', '60'))  # Seconds

# Prometheus metrics
TEMPERATURE = Gauge('inkbird_temperature_celsius', 'Temperature measured (°C)', ['device_mac'])
BATTERY = Gauge('inkbird_battery_percent', 'Battery level (%)', ['device_mac'])
LAST_SEEN = Gauge('inkbird_last_seen_timestamp', 'Last time the device was seen (unix timestamp)', ['device_mac'])
SCAN_SUCCESS = Gauge('inkbird_scan_success', 'Whether the last scan was successful (1=success, 0=failure)', ['device_mac'])

def get_inkbird_data():
    """Scans briefly to find the target MAC and decode its broadcast."""
    try:
        # We use a short scan (5s) to find the current advertisement packet
        devices = BleakScanner.discover(return_adv=True, timeout=5.0)

        # discover returns a dict: {address: (device, adv_data)}
        # We wrap this in a try/except or helper to run it 'sync'
        import asyncio
        devices_dict = asyncio.run(devices)
    except Exception as e:
        logging.error(f"Error scanning for device: {e}")
        return None, None, None

    # Debug: log all found devices
    if DEBUG:
        found_devices = list(devices_dict.keys())
        logging.info(f"Found {len(found_devices)} devices: {found_devices}")
        logging.info(f"Looking for device: {TARGET_MAC}")

    if TARGET_MAC not in devices_dict:
        return None, None, None

    device, adv_data = devices_dict[TARGET_MAC]
    m_data = adv_data.manufacturer_data

    if not m_data:
        if DEBUG:
            logging.warning(f"No manufacturer data for device {TARGET_MAC}")
        return None, None, None

    for company_id, payload in m_data.items():
        # Our discovered logic: Key is temp, Payload[5] is battery
        temp_c = company_id / 100.0
        battery = payload[5] if len(payload) >= 6 else None

        if DEBUG:
            logging.info(f"Found device {TARGET_MAC}: temp={temp_c:.2f}°C, battery={battery}%")

        return temp_c, battery, time.time()

    return None, None, None

def update_metrics():
    """Update Prometheus metrics with current inkbird data"""
    temp, battery, timestamp = get_inkbird_data()

    if temp is None or timestamp is None:
        SCAN_SUCCESS.labels(device_mac=TARGET_MAC).set(0)
        if DEBUG:
            logging.warning(f"Device {TARGET_MAC} not found in scan")
        return

    TEMPERATURE.labels(device_mac=TARGET_MAC).set(temp)
    LAST_SEEN.labels(device_mac=TARGET_MAC).set(timestamp)
    SCAN_SUCCESS.labels(device_mac=TARGET_MAC).set(1)

    if battery is not None:
        BATTERY.labels(device_mac=TARGET_MAC).set(battery)

    if DEBUG:
        logging.info(f"Updated metrics: temp={temp:.2f}°C, battery={battery}%")

def collect_all_data():
    """Collects all the data currently set"""
    sensor_data = {}
    try:
        sensor_data['temperature'] = TEMPERATURE.labels(device_mac=TARGET_MAC).collect()[0].samples[0].value
        sensor_data['battery'] = BATTERY.labels(device_mac=TARGET_MAC).collect()[0].samples[0].value
        sensor_data['last_seen'] = LAST_SEEN.labels(device_mac=TARGET_MAC).collect()[0].samples[0].value
        sensor_data['scan_success'] = SCAN_SUCCESS.labels(device_mac=TARGET_MAC).collect()[0].samples[0].value
    except (IndexError, AttributeError):
        # Metrics might not be set yet
        pass
    return sensor_data

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
    parser.add_argument("-m", "--mac", metavar='MAC_ADDRESS', default=TARGET_MAC, help=f"Target device MAC address [default: {TARGET_MAC}]")
    parser.add_argument("-i", "--interval", metavar='INTERVAL', default=SCAN_INTERVAL, type=int, help=f"Scan interval in seconds [default: {SCAN_INTERVAL}]")
    parser.add_argument("-d", "--debug", metavar='DEBUG', type=str_to_bool, help="Turns on more verbose logging, showing sensor output [default: false]")
    args = parser.parse_args()

    if args.debug:
        DEBUG = True

    if args.mac:
        TARGET_MAC = args.mac.upper()

    if args.interval:
        SCAN_INTERVAL = args.interval

    # Start up the server to expose the metrics
    start_http_server(addr=args.bind, port=args.port)

    logging.info(f"Monitoring Inkbird device {TARGET_MAC} every {SCAN_INTERVAL}s")
    logging.info("Listening on http://{}:{}".format(args.bind, args.port))

    try:
        while True:
            update_metrics()

            if DEBUG:
                logging.info('Sensor data: {}'.format(collect_all_data()))

            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Stopping inkbird exporter...")
