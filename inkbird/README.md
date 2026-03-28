# Inkbird Prometheus Exporter

A Prometheus exporter for Inkbird Bluetooth Low Energy (BLE) temperature sensors.

## Features

- Monitors Inkbird BLE temperature sensors via Bluetooth scanning
- Exposes temperature and battery level as Prometheus metrics
- Configurable scan intervals and device MAC address
- Tracks device availability and last seen timestamps

## Requirements

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Basic usage:

```bash
./inkbird_exporter.py -p 8001
```

### Command Line Options

- `-b, --bind ADDRESS`: Bind address (default: 0.0.0.0)
- `-p, --port PORT`: HTTP server port (default: 8000)
- `-m, --mac MAC_ADDRESS`: Target device MAC address (default: 49:24:03:06:04:28)
- `-i, --interval INTERVAL`: Scan interval in seconds (default: 60)
- `-d, --debug DEBUG`: Enable debug logging (default: false)

### Environment Variables

- `INKBIRD_MAC`: Default MAC address of the Inkbird device
- `SCAN_INTERVAL`: Default scan interval in seconds
- `DEBUG`: Enable debug logging (true/false)

## Example

Monitor a specific device every 30 seconds on port 8001:

```bash
./inkbird_exporter.py -m "AA:BB:CC:DD:EE:FF" -i 30 -p 8001
```

## Prometheus Metrics

The exporter provides the following metrics:

- `inkbird_temperature_celsius{device_mac}`: Temperature in Celsius
- `inkbird_battery_percent{device_mac}`: Battery level percentage
- `inkbird_last_seen_timestamp{device_mac}`: Unix timestamp when device was last seen
- `inkbird_scan_success{device_mac}`: Whether the last scan was successful (1=success, 0=failure)

## Setup

1. Find your Inkbird device MAC address using Bluetooth scanning
2. Configure the MAC address via command line or environment variable
3. Run the exporter
4. Configure Prometheus to scrape `http://your_host:port/metrics`

## Systemd Service

Example systemd service file:

```ini
[Unit]
Description=Inkbird Prometheus Exporter
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/path/to/inkbird
ExecStart=/usr/bin/python3 /path/to/inkbird/inkbird_exporter.py -p 8001
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```
