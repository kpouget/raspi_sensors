#!/usr/bin/env python3
import os
import time
import logging
import argparse
import subprocess
import json
import sys
from threading import Thread

from prometheus_client import start_http_server, Gauge

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
    """Scans briefly to find the target MAC using subprocess to prevent FD leaks."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    scanner_script = os.path.join(script_dir, "ble_scanner.py")

    try:
        # Run BLE scan in subprocess with timeout
        result = subprocess.run(
            ["python3", scanner_script, TARGET_MAC],
            capture_output=True,
            text=True,
            timeout=25  # 25 second timeout to allow for retries
        )

        if result.returncode != 0:
            logging.error(f"BLE scanner subprocess failed with code {result.returncode}: {result.stderr}")
            return None, None, None

        # Parse JSON result
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse BLE scanner output: {e}")
            return None, None, None

        if data.get("error"):
            if DEBUG:
                logging.warning(f"BLE scan error: {data['error']}")
            return None, None, None

        if not data.get("found"):
            if DEBUG:
                logging.info(f"Device {TARGET_MAC} not found in scan")
            return None, None, None

        temp = data.get("temperature")
        battery = data.get("battery")
        timestamp = data.get("timestamp")

        if DEBUG:
            logging.info(f"Found device {TARGET_MAC}: temp={temp:.2f}°C, battery={battery}%")

        return temp, battery, timestamp

    except subprocess.TimeoutExpired:
        logging.error("BLE scanner subprocess timed out")
        return None, None, None
    except Exception as e:
        logging.error(f"Error running BLE scanner subprocess: {e}")
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

    logging.info(f"Monitoring Inkbird device {TARGET_MAC} every {SCAN_INTERVAL}s")

    if not DEBUG:
        # Start up the server to expose the metrics
        start_http_server(addr=args.bind, port=args.port)
        logging.info("Listening on http://{}:{}".format(args.bind, args.port))

    try:
        while True:
            if DEBUG:
                # In debug mode, just get and print the data directly
                temp, battery, timestamp = get_inkbird_data()
                if temp is not None:
                    time_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
                    print(f"[{time_str}] Temp: {temp:.2f}°C | Battery: {battery}%")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Device not found in scan.")
            else:
                # In production mode, update Prometheus metrics
                update_metrics()

            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Stopping inkbird exporter...")
