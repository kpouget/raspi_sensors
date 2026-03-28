import time
from bleak import BleakScanner

# Your device configuration
TARGET_MAC = "49:24:03:06:04:28".upper()
INTERVAL = 60 # Seconds

def get_inkbird_data():
    """Scans briefly to find the target MAC and decode its broadcast."""
    # We use a short scan (5s) to find the current advertisement packet
    devices = BleakScanner.discover(return_adv=True, timeout=5.0)
    
    # discover returns a dict: {address: (device, adv_data)}
    # We wrap this in a try/except or helper to run it 'sync'
    import asyncio
    devices_dict = asyncio.run(devices)

    if TARGET_MAC in devices_dict:
        device, adv_data = devices_dict[TARGET_MAC]
        m_data = adv_data.manufacturer_data
        
        for company_id, payload in m_data.items():
            # Our discovered logic: Key is temp, Payload[5] is battery
            temp_c = company_id / 100.0
            battery = payload[5] if len(payload) >= 6 else "N/A"
            return temp_c, battery
            
    return None, None

print(f"--- Monitoring {TARGET_MAC} every {INTERVAL}s ---")

try:
    while True:
        temp, batt = get_inkbird_data()
        
        if temp is not None:
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] Temp: {temp:.2f}°C | Battery: {batt}%")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] Device not found in scan.")
            
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nStopping script...")
