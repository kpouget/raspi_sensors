#!/usr/bin/env python3
"""
Subprocess BLE scanner for Inkbird devices.
This runs in isolation to prevent file descriptor leaks.
"""
import asyncio
import json
import sys
import time
from bleak import BleakScanner


async def scan_for_device(target_mac, timeout=5.0):
    """Scan for a specific device and return its data."""
    try:
        devices_dict = await BleakScanner.discover(return_adv=True, timeout=timeout)

        if target_mac not in devices_dict:
            return {"found": False, "error": None, "timestamp": time.time()}

        device, adv_data = devices_dict[target_mac]
        m_data = adv_data.manufacturer_data

        if not m_data:
            return {"found": False, "error": "No manufacturer data", "timestamp": time.time()}

        for company_id, payload in m_data.items():
            # Our discovered logic: Key is temp, Payload[5] is battery
            temp_c = company_id / 100.0
            battery = payload[5] if len(payload) >= 6 else None

            return {
                "found": True,
                "temperature": temp_c,
                "battery": battery,
                "timestamp": time.time(),
                "error": None
            }

        return {"found": False, "error": "No valid manufacturer data", "timestamp": time.time()}

    except Exception as e:
        return {"found": False, "error": str(e), "timestamp": time.time()}


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"found": False, "error": "Usage: ble_scanner.py <MAC_ADDRESS>"}))
        sys.exit(1)

    target_mac = sys.argv[1].upper()

    # Retry logic for "Operation already in progress" errors
    max_retries = 3
    for attempt in range(max_retries):
        result = asyncio.run(scan_for_device(target_mac))

        error_msg = result.get("error", "")
        if error_msg and ("InProgress" in error_msg or "Operation already in progress" in error_msg):
            if attempt < max_retries - 1:  # Don't sleep on last attempt
                # Wait progressively longer: 2s, 5s
                wait_time = 2 + (attempt * 3)
                time.sleep(wait_time)
                continue

        # Success or non-retryable error, return result
        break

    print(json.dumps(result))


if __name__ == "__main__":
    main()